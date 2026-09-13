"""月次・年次の完全汎用化: 権利月の自動解決・権利付最終日・残営業日数・URLスラッグ解決。

依存は標準ライブラリ + jpholiday(任意) のみ。config.py から import される側であり、
config を import してはならない (循環参照防止)。
"""
from __future__ import annotations

import datetime as dt
from zoneinfo import ZoneInfo

JST = ZoneInfo("Asia/Tokyo")

# enjoy-lcl 月別スラグ (https://yutai.enjoy-lcl.com/{slug}-list/)
ROUTINE_SLUGS = {
    1: "january", 2: "february", 3: "march", 4: "april",
    5: "may", 6: "june", 7: "july", 8: "august",
    9: "september", 10: "october", 11: "november", 12: "december",
}
ROUTINE_BASE = "https://yutai.enjoy-lcl.com"


def routine_url(year: int, month: int) -> str:
    """ルーティン側の月別URLを解決する。"""
    return f"{ROUTINE_BASE}/{ROUTINE_SLUGS[month]}-list/"


def now_jst() -> dt.datetime:
    return dt.datetime.now(JST)


def config_today() -> dt.date:
    return now_jst().date()


def datetime_from_epoch_ms(ms: int) -> str:
    """epochミリ秒 → 'YYYY-MM-DD HH:mm' (JST)。"""
    return dt.datetime.fromtimestamp(ms / 1000, JST).strftime("%Y-%m-%d %H:%M")


def _holiday_set(years: set[int]) -> set[dt.date]:
    try:
        import jpholiday

        out: set[dt.date] = set()
        for y in years:
            out |= {d for d, _ in jpholiday.year_holidays(y)}
        return out
    except ImportError:
        return set()


def is_business_day(d: dt.date, holidays: set[dt.date]) -> bool:
    return d.weekday() < 5 and d not in holidays


def month_end_kengi(year: int, month: int) -> dt.date:
    """月末権利の権利付最終日を自動算出 (T+2決済: 月末から2営業日遡る)。
    実績: 2026年9月 → 9/30(水)−2営業日 = 9/28(月) でサイト記載と一致。"""
    if month == 12:
        last = dt.date(year, 12, 31)
    else:
        last = dt.date(year, month + 1, 1) - dt.timedelta(days=1)
    holidays = _holiday_set({year, last.year})
    d, back = last, 0
    while back < 2:
        d -= dt.timedelta(days=1)
        if is_business_day(d, holidays):
            back += 1
    return d


def business_days_left(today: dt.date, last_day: dt.date) -> int:
    """取得日→権利付最終日の残り営業日数(D-N)。最終日当日=0。土日+日本の祝日を除外。

    jpholidayが無い環境では土日のみ除外にフォールバックする。
    """
    if today >= last_day:
        return 0
    holidays = _holiday_set({today.year, last_day.year})
    n, d = 0, today + dt.timedelta(days=1)
    while d <= last_day:
        if is_business_day(d, holidays):
            n += 1
        d += dt.timedelta(days=1)
    return n


def resolve_rights(today: dt.date) -> tuple[str, dt.date]:
    """実行日から対象の権利年月と権利付最終日を自動解決。
    当月→翌月の順で、権利付最終日が今日以降の最初の月を返す。"""
    y, m = today.year, today.month
    for _ in range(3):
        kengi = month_end_kengi(y, m)
        if kengi >= today:
            return f"{y}-{m:02d}", kengi
        m += 1
        if m > 12:
            y, m = y + 1, 1
    raise RuntimeError("権利月の解決に失敗")


def get_rights_info(rights: str | None = None,
                    kengi_override: str | None = None) -> dict:
    """rights='YYYY-MM' → {rights, year, month, label, routine_url, api_month, kengi}。
    rights省略時は実行日から自動解決。kengi_override='YYYY-MM-DD'で最終日を上書き可。"""
    if rights:
        y, m = int(rights[:4]), int(rights[5:7])
        rights_str = f"{y}-{m:02d}"
    else:
        rights_str, _auto = resolve_rights(now_jst().date())
        y, m = int(rights_str[:4]), int(rights_str[5:7])
    kengi = (dt.date.fromisoformat(kengi_override) if kengi_override
             else month_end_kengi(y, m))
    return {
        "rights": rights_str, "year": y, "month": m,
        "label": f"{m}月",
        "routine_url": routine_url(y, m),
        "api_month": str(m),
        "kengi": kengi,
    }
