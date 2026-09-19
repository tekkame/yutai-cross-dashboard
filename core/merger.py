# -*- coding: utf-8 -*-
"""
core/merger.py - データマージエンジン (Gokigen最優先在庫マージ & メタ情報補完)

仕様:
1. [在庫情報] は、本日朝リアルタイム更新される [Gokigen Life API] のデータを最優先とする。
   - 日興、楽天、カブ、SBI信号、GMO信号、松井、マネックス等の最新在庫はGokigen側の値を優先採用。
   - ルーティン側は前日静的HTMLスナップショットのため、Gokigenにデータがない場合のフォールバックとして使用。
2. [マスター銘柄情報] は、[ルーティン株主優待] および [Gokigen Life] から包括的に収集。
   - 銘柄名・優待内容はより詳細・明瞭な方を優先採用。
   - 長期優遇、制度信用指標、売建上限等はルーティン側の詳細情報を活用。
3. どちらのサイトからも「必要資金」または「優待価値」が拾えなかった銘柄については、
   優待内容テキスト内の金額から正規表現で自動逆算して補完する。
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
import re
from typing import Any

import config
from scrapers.routine_yutai import extract_yutai_value

# 上場廃止・持株会社統合・TOB成立済みの過去銘柄リスト（config.pyから一元管理）
DELISTED_CODES = config.DELISTED_CODES


def _fmt(v: Any, ndigits: int = 0) -> Any:
    if v is None or v == "":
        return ""
    if isinstance(v, float):
        if ndigits == 0 and v.is_integer():
            return int(v)
        return round(v, ndigits)
    return v


def estimate_cost(
    kabuka: float | None,
    kabusu: float | None,
    cross_days: float | None,
    fallback_days: int,
    annual_rate: float | None = None
) -> float | None:
    rate = config.KASHIKABU_ANNUAL_RATE if annual_rate is None else annual_rate
    try:
        total = float(kabuka or 0) * float(kabusu or 100)
    except (TypeError, ValueError):
        return None
    days = cross_days if cross_days else fallback_days
    if not total or not days:
        return None
    return round(total * rate * float(days) / 365)


def _seido_text(g: dict | None) -> str:
    if not g:
        return ""
    kisei = g.get("recent_gyaku_kisei") or ""
    max_gyaku = g.get("max5_gyaku")
    parts = []
    if kisei:
        parts.append(f"注意喚起:{kisei}")
    if max_gyaku:
        parts.append(f"max逆日歩:{_fmt(max_gyaku)}")
    return " / ".join(parts)


def parse_watch(expr: str):
    """'yield>=1,funds<=30,rakuten>0' → 条件述語"""
    watch_fields = {
        "yield": "total_yield", "funds": "funds_man", "value": "value",
        "rakuten": "rakuten", "nikko": "nikko", "kabu": "kabu",
        "cost": "cost", "maxgyaku": "max_gyaku",
    }
    conds = []
    for tok in (expr or "").split(","):
        tok = tok.strip()
        if not tok:
            continue
        m = re.fullmatch(r"([a-z]+)\s*(>=|<=|>|<|=)\s*([\d.]+)", tok)
        if not m or m.group(1) not in watch_fields:
            continue
        field, op, num = m.group(1), m.group(2), float(m.group(3))
        ops = {
            ">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b,
            ">": lambda a, b: a > b, "<": lambda a, b: a < b, "=": lambda a, b: a == b
        }
        conds.append((watch_fields[field], ops[op], num))

    def pred(row: dict) -> bool:
        for key, op, num in conds:
            v = row.get(key)
            if v is None or v == "":
                return False
            try:
                if not op(float(v), num):
                    return False
            except (TypeError, ValueError):
                return False
        return True

    return pred


def build_rows(
    rights: str,
    today: dt.date,
    stamp: str,
    d_n: int,
    kengi: dt.date,
    routine: list[dict],
    gmap: dict[str, dict]
) -> tuple[list[list], list[dict]]:
    """ルーティン最優先マージで history行 と master行 を生成"""
    history: list[list] = []
    master: list[dict] = []
    cal_days_left = max((kengi - today).days, 0)
    rmap = {r["code"]: r for r in routine}

    all_codes = sorted(set(rmap) | set(gmap))

    for code in all_codes:
        if str(code).strip().zfill(4) in DELISTED_CODES:
            continue
        r = rmap.get(code)
        g = gmap.get(code, {})

        # 1. 銘柄名 (より正式・明瞭な名称を採用)
        name = (g.get("name") if g else None) or (r.get("name") if r else None) or ""
        if not name or name.lower() in ("null", "nan"):
            name = (r.get("name") if r else None) or ""
        if not name or name.lower() in ("null", "nan"):
            continue

        # 2. 優待内容 (より詳細・具体的な方を優先採用)
        r_content = (r.get("yutai_content") if r else "") or ""
        g_content = (g.get("yutai_content") or g.get("yutai") if g else "") or ""
        content = r_content if len(r_content) >= len(g_content) else g_content
        if not content:
            content = r_content or g_content

        # 3. 優待価値 (ルーティン、Gokigen、テキスト逆算の順で有効な正の値を採用)
        yutai_val = (r.get("yutai_value") if r else None)
        if yutai_val is None or yutai_val == 0:
            yutai_val = g.get("yutai_value") if g else None
        if yutai_val is None or yutai_val == 0:
            yutai_val = extract_yutai_value(content, code=code)
        if yutai_val is None or yutai_val == 0:
            yutai_val = extract_yutai_value(r_content, code=code) or extract_yutai_value(g_content, code=code)

        # 4. 必要資金(万円) (Gokigenまたはルーティンから取得、後で株価から再計算)
        funds_man = (r.get("funds_man") if r else None)
        if funds_man is None and g:
            funds_man = g.get("funds_man")

        # 株価・株数
        kabuka = g.get("stock_price") or g.get("kabuka") if g else None
        kabusu = g.get("kabusu") if g else None
        if kabusu is None or kabusu <= 0:
            m_sh = re.search(r"【(\d+)株】", content)
            kabusu = float(m_sh.group(1)) if m_sh else 100.0

        # 株価が空の場合、stock_prices_cache.json から引き当て
        if kabuka is None or kabuka <= 0:
            cache_p = Path("data/stock_prices_cache.json")
            if cache_p.exists():
                try:
                    c_dict = json.loads(cache_p.read_text(encoding="utf-8"))
                    c_norm = str(code).strip().zfill(4)
                    if c_norm in c_dict and c_dict[c_norm] > 0:
                        kabuka = float(c_dict[c_norm])
                except Exception:
                    pass

        if funds_man is None and kabuka and kabuka > 0:
            funds_man = round(kabuka * kabusu / 10000, 2)
        elif kabuka is None and funds_man and funds_man > 0:
            kabuka = round(funds_man * 10000 / kabusu, 1)

        # 5. 利回り (優待価値と必要資金から高精度再計算)
        yield_pct = (r.get("yield_pct") if r else None)
        if yield_pct is None and g:
            yield_pct = g.get("yield_pct")
        if (yield_pct is None or yield_pct == 0) and funds_man and yutai_val and funds_man > 0:
            yield_pct = round((yutai_val / (funds_man * 10000)) * 100, 2)

        # 6. 在庫数値 (★最重要改善: 本日朝リアルタイム更新の Gokigen API を最優先！)
        # ルーティンは1日前の静的HTMLのため、Gokigenに在庫データがない場合のみフォールバック採用
        # 日興
        nikko_qty = None
        if g and g.get("nikko_qty") is not None:
            nikko_qty = g.get("nikko_qty")
        elif r and r.get("nikko_qty") is not None:
            nikko_qty = r.get("nikko_qty")

        # 楽天
        rakuten_qty = None
        if g and g.get("rakuten_qty") is not None:
            rakuten_qty = g.get("rakuten_qty")
        elif r and r.get("rakuten_qty") is not None:
            rakuten_qty = r.get("rakuten_qty")

        # カブ
        kabu_qty = g.get("kabu_qty") if g else None

        # 7. SBI信号 (★最重要改善: 本日朝リアルタイム更新の Gokigen を最優先！)
        sbi_signal = "―"
        if g and g.get("sbi_signal") and g.get("sbi_signal") != "―":
            sbi_signal = g.get("sbi_signal")
        elif r and r.get("sbi_signal") and r.get("sbi_signal") != "―":
            sbi_signal = r.get("sbi_signal")

        # 8. GMO信号 / 売建上限
        gmo_limit = (r.get("gmo_limit") if r else None)
        gmo_signal = "―"
        if g and g.get("gmo_signal") and g.get("gmo_signal") != "―":
            gmo_signal = g.get("gmo_signal")
        elif r and r.get("gmo_qty") is not None:
            gmo_signal = str(_fmt(r.get("gmo_qty")))

        # 9. 松井・マネックス
        matsui_signal = g.get("matsui_signal") or "―" if g else "―"
        monex_signal = g.get("monex_signal") or "―" if g else "―"

        # 貸株コスト試算
        cross_days = g.get("cross_days")
        cost = estimate_cost(kabuka, kabusu, cross_days, cal_days_left)
        max_gyaku = g.get("max5_gyaku")

        # raw_history行 (全20列)
        history.append([
            stamp,
            rights,
            d_n,
            code,
            name,
            _fmt(nikko_qty),
            _fmt(kabu_qty),
            _fmt(rakuten_qty),
            sbi_signal,
            gmo_signal,
            matsui_signal,
            monex_signal,
            _fmt(kabuka),
            _fmt(kabusu),
            _fmt(cross_days),
            _fmt(cost),
            _fmt(max_gyaku),
            _fmt(r.get("rakuten_qty") if r else None),
            _fmt(r.get("nikko_qty") if r else None),
            sbi_signal,
        ])

        # master行
        master.append({
            "watch": False,
            "priority": "",
            "code": code,
            "name": name,
            "content": content,
            "value": _fmt(yutai_val),
            "funds_man": _fmt(funds_man),
            "total_yield": _fmt(yield_pct, 2) if yield_pct is not None else "",
            "gmo_limit": _fmt(gmo_limit),
            "chouki": "",
            "seido": _seido_text(g),
            "rights": rights,
            # auto-watch判定用
            "rakuten": rakuten_qty,
            "nikko": nikko_qty,
            "kabu": kabu_qty,
            "cost": cost,
            "max_gyaku": max_gyaku,
        })

    return history, master


def master_to_rows(master: list[dict]) -> list[list]:
    return [
        [
            m["watch"], m["priority"], m["code"], m["name"], m["content"],
            m["value"], m["funds_man"], m["total_yield"], m["gmo_limit"],
            m["chouki"], m["seido"], m["rights"]
        ]
        for m in master
    ]
