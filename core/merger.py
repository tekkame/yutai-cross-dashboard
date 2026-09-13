"""データマージエンジン: 4桁コードをキーに Full Outer Join。

- ベースはルーティン側 (厳選銘柄の資金・優待価値・利回り・GMO売建上限)。
- Gokigen側があれば7社在庫・株価・逆日歩実績で補完。売建上限はルーティン側からのみ付与。
- どちらのサイトにも載る銘柄を1件も落とさない ( routine-only / gokigen-only も両方行化 )。
- レコードごとに [取得日時(JST), 権利年月(YYYY-MM), 残日数(D-N)] を付与 (呼び出し側がstamp/d_nを渡す)。
"""
from __future__ import annotations

import datetime as dt
import re

import config


def _fmt(v, ndigits: int = 0):
    if v is None or v == "":
        return ""
    if isinstance(v, float) and ndigits == 0 and v.is_integer():
        return int(v)
    return round(v, ndigits) if isinstance(v, float) else v


def estimate_cost(kabuka, kabusu, cross_days, fallback_days: int,
                  annual_rate: float | None = None) -> float | None:
    """今日クロスした場合の貸株料概算 = 株価格×株数×年率×日数/365。"""
    rate = config.KASHIKABU_ANNUAL_RATE if annual_rate is None else annual_rate
    try:
        total = float(kabuka) * float(kabusu or 100)
    except (TypeError, ValueError):
        return None
    days = cross_days if cross_days else fallback_days
    if not total or not days:
        return None
    return round(total * rate * float(days) / 365)


WATCH_FIELDS = {
    "yield": "total_yield", "funds": "funds_man", "value": "yutai_value",
    "rakuten": "rakuten", "nikko": "nikko", "kabu": "kabu",
    "cost": "cost", "maxgyaku": "max_gyaku",
}


def parse_watch(expr: str):
    """'yield>=1,funds<=30,rakuten>0' → すべて満たせばTrueの述語。"""
    conds = []
    for tok in (expr or "").split(","):
        tok = tok.strip()
        if not tok:
            continue
        m = re.fullmatch(r"([a-z]+)\s*(>=|<=|>|<|=)\s*([\d.]+)", tok)
        if not m or m.group(1) not in WATCH_FIELDS:
            raise ValueError(f"--auto-watch の条件が不正: {tok} (例: yield>=1,funds<=30)")
        field, op, num = m.group(1), m.group(2), float(m.group(3))
        ops = {">=": lambda a, b: a >= b, "<=": lambda a, b: a <= b,
               ">": lambda a, b: a > b, "<": lambda a, b: a < b, "=": lambda a, b: a == b}
        conds.append((WATCH_FIELDS[field], ops[op], num))

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


def _seido_text(g: dict | None) -> str:
    kisei = (g.get("recent_gyaku_kisei") or "") if g else ""
    max_gyaku = (g.get("max5_gyaku") if g else None)
    return " / ".join(x for x in [
        f"注意喚起:{kisei}" if kisei else "",
        f"max逆日歩:{_fmt(max_gyaku)}" if max_gyaku else "",
    ] if x)


def build_rows(rights: str, today: dt.date, stamp: str, d_n: int, kengi: dt.date,
               routine: list[dict], gmap: dict[str, dict]) -> tuple[list[list], list[list]]:
    """history行とmaster行を生成する。コードの和集合で回す Full Outer Join。

    rmap: routineレコード、gmap: gokigenレコード。gokigen-only銘柄は
    優待内容=gokigenのyutai文面、必要資金=株価×株数、利回り=rimawariで補完する。
    """
    history: list[list] = []
    master: list[list] = []
    cal_days_left = max((kengi - today).days, 0)
    rmap = {r["code"]: r for r in routine}
    for code in sorted(set(rmap) | set(gmap)):
        r = rmap.get(code)
        g = gmap.get(code, {})
        stocks = g.get("stocks", {}) if g else {}
        funds_man = r["funds_man"] if r else None
        kabuka = (g.get("kabuka") if g else None) or (
            (funds_man * 10000 / 100) if funds_man else None)
        kabusu = (g.get("kabusu") if g else None) or 100
        if funds_man is None and kabuka:
            try:
                funds_man = kabuka * float(kabusu or 100) / 10000
            except (TypeError, ValueError):
                funds_man = None
        cross_days = g.get("cross_days") if g else None
        cost = estimate_cost(kabuka, kabusu, cross_days, cal_days_left)
        rimawari = g.get("rimawari") if g else None
        total_yield = (round(rimawari * 100, 2) if rimawari
                       else (r["yield_pct"] if r else None))
        max_gyaku = (g.get("max5_gyaku") if g else None)
        name = (r["name"] if r else None) or (g.get("name") if g else "") or ""
        history.append([
            stamp, rights, d_n, code, name,
            _fmt(stocks.get("日興")), _fmt(stocks.get("カブ")), _fmt(stocks.get("楽天")),
            _fmt(stocks.get("SBI")), _fmt(stocks.get("GMO")),
            _fmt(stocks.get("松井")), _fmt(stocks.get("マネ")),
            _fmt(kabuka), _fmt(kabusu), _fmt(cross_days), _fmt(cost), _fmt(max_gyaku),
            _fmt(r["rakuten_qty"]) if r else "",
            _fmt(r["nikko_qty"]) if r else "",
            r["sbi_signal"] if r else "",
        ])
        master.append({
            "watch": False, "priority": "",
            "code": code, "name": name,
            "content": (r["yutai_content"] if r else None) or (g.get("yutai") if g else "") or "",
            "value": _fmt(r["yutai_value"]) if r else "",
            "funds_man": _fmt(funds_man),
            "total_yield": total_yield if total_yield not in (None, "") else "",
            "gmo_limit": _fmt(r["gmo_limit"]) if r else "",
            "chouki": "", "seido": _seido_text(g),
            "rights": rights,
            # auto-watch判定用
            "rakuten": stocks.get("楽天"), "nikko": stocks.get("日興"),
            "kabu": stocks.get("カブ"), "cost": cost, "max_gyaku": max_gyaku,
        })
    return history, master


def master_to_rows(master: list[dict]) -> list[list]:
    return [[m["watch"], m["priority"], m["code"], m["name"], m["content"],
             m["value"], m["funds_man"], m["total_yield"], m["gmo_limit"],
             m["chouki"], m["seido"], m["rights"]] for m in master]
