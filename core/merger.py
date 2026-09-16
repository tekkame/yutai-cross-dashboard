# -*- coding: utf-8 -*-
"""
core/merger.py - データマージエンジン (ルーティン最優先マージ)

修正仕様 (3):
1. [ルーティン株主優待] の約140〜160銘柄を「最優先マスター（Master A）」とする。
   - コード、銘柄名、資金、優待価値、優待内容、日興、楽天、カブ、SBI(◎▲×)、GMO(売建上限)は
     ルーティン側の値を絶対に優先する。
2. [Gokigen Life] のデータは、ルーティン側に存在しない残りの銘柄の補完、
   および「7社在庫 (松井・マネックス等)」「前日終値」の追加項目としてのみ結合する。
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
        r = rmap.get(code)
        g = gmap.get(code, {})

        # 1. 銘柄名 (ルーティン最優先)
        name = (r.get("name") if r else None) or g.get("name") or ""
        if not name or name.lower() in ("null", "nan"):
            continue

        # 2. 優待内容 (ルーティン最優先)
        content = (r.get("yutai_content") if r else None) or g.get("yutai_content") or g.get("yutai") or ""

        # 3. 優待価値 (ルーティン最優先、なければGokigen、なければテキストから逆算)
        yutai_val = (r.get("yutai_value") if r else None)
        if yutai_val is None or yutai_val == 0:
            yutai_val = g.get("yutai_value")
        if yutai_val is None or yutai_val == 0:
            yutai_val = extract_yutai_value(content)

        # 4. 必要資金(万円) (ルーティン最優先、なければGokigen)
        funds_man = (r.get("funds_man") if r else None)
        if funds_man is None:
            funds_man = g.get("funds_man")

        # 株価・株数
        kabuka = g.get("stock_price") or g.get("kabuka")
        kabusu = g.get("kabusu")
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

        # 5. 利回り (ルーティン最優先)
        yield_pct = (r.get("yield_pct") if r else None)
        if yield_pct is None:
            yield_pct = g.get("yield_pct")
        if (yield_pct is None or yield_pct == 0) and funds_man and yutai_val and funds_man > 0:
            yield_pct = round((yutai_val / (funds_man * 10000)) * 100, 2)

        # 6. 在庫数値 (ルーティン最優先)
        # 日興
        nikko_qty = (r.get("nikko_qty") if r else None)
        if nikko_qty is None and g:
            nikko_qty = g.get("nikko_qty")

        # 楽天
        rakuten_qty = (r.get("rakuten_qty") if r else None)
        if rakuten_qty is None and g:
            rakuten_qty = g.get("rakuten_qty")

        # カブ
        kabu_qty = g.get("kabu_qty")

        # 7. SBI信号 (ルーティン最優先: ◎, ▲, ×)
        sbi_signal = (r.get("sbi_signal") if r else None)
        if not sbi_signal or sbi_signal == "―":
            sbi_signal = g.get("sbi_signal") or "―"

        # 8. GMO信号 / 売建上限
        gmo_limit = (r.get("gmo_limit") if r else None)
        gmo_signal = g.get("gmo_signal") or "―"
        if r and r.get("gmo_qty") is not None:
            gmo_signal = str(_fmt(r.get("gmo_qty")))

        # 9. 松井・マネックス
        matsui_signal = g.get("matsui_signal") or "―"
        monex_signal = g.get("monex_signal") or "―"

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
