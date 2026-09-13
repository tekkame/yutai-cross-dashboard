"""共通定数・カラム定義。日付ロジックの実体は utils/dates.py (ここは後方互換の再export)。"""
from __future__ import annotations

import datetime as dt

from utils.dates import (
    JST,
    ROUTINE_BASE,
    ROUTINE_SLUGS,
    business_days_left as _business_days_left,
    config_today,
    datetime_from_epoch_ms,
    get_rights_info,
    is_business_day,
    month_end_kengi,
    now_jst,
    resolve_rights,
    routine_url,
)

# ---- 権利情報 ----
# 既定の権利月。main.py --rights / workflow inputs で上書き可能。省略時は自動解決。
RIGHTS_MONTH = "2026-09"
KENRI_TSUKIHI = dt.date(2026, 9, 28)  # 後方互換の既定値 (9月末権利の実績値)

# enjoy-lcl 月別スラグ・URL解決・権利日計算は utils/dates.py が正規の実体。
# (ROUTINE_SLUGS / ROUTINE_BASE / routine_url / month_end_kengi / resolve_rights / get_rights_info
#  は上記importで再exportしている)

# ---- データソース ----
ROUTINE_URL = f"{ROUTINE_BASE}/september-list/"  # 後方互換の既定値
GOKIGEN_API_URL = "https://gokigen-life.tokyo/api/00ForWeb/ForZaiko2.php"
GOKIGEN_MONTH = "9"  # 後方互換の既定値
GOKIGEN_ENCODING = "shift_jis"


# routine_url は上記importのまま使う (実体はutils.dates.routine_url)


def business_days_left(today: dt.date, last_day: dt.date = KENRI_TSUKIHI) -> int:
    """後方互換ラッパー (既定の最終日つき)。実体はutils.dates.business_days_left。"""
    return _business_days_left(today, last_day)

# ---- Gokigen API volフィールド → 証券会社名 ----
BROKERS = [
    ("nvol", "日興"),
    ("kvol", "カブ"),
    ("rvol", "楽天"),
    ("svol", "SBI"),
    ("gvol", "GMO"),
    ("mvol", "松井"),
    ("xvol", "マネ"),
]

# ---- 貸株コスト試算用 年率 (仮定値: 要調整) ----
# 一般信用の貸株料率は証券会社・信用区分で異なる。ここは概算用の既定値であり、
# 厳密なコスト計算には各証券会社の最新料率への更新を推奨する。
KASHIKABU_ANNUAL_RATE = 0.011  # 年1.1% (概算既定値)

# ---- raw_history カラム ----
# 注意: Gokigen APIで株数が取れるのは日興/カブ/楽天のみ。
# SBI/GMO/松井/マネは 0/1/2 のステータスコード (2=あり濃厚・0=なし濃厚、詳細はREADME) のため「信号」扱い。
HISTORY_HEADERS = [
    "取得日時", "権利年月", "残日数(D-N)", "コード", "銘柄名",
    "日興在庫", "カブ在庫", "楽天在庫", "SBI信号", "GMO信号", "松井信号", "マネ信号",
    "株価", "株数", "クロス日数", "貸株コスト", "最大逆日歩",
    # R〜T: ルーティン側スナップショット (サイト基準日時点。SBI◎▲×はここにしかない)
    "Rtn_楽天", "Rtn_日興", "Rtn_SBI",
]

# ---- master_list カラム (A=監視・B=優先度はユーザー操作領域。コード+権利月がキー) ----
MASTER_HEADERS = [
    "監視", "優先度", "コード", "銘柄名", "優待内容", "優待価値",
    "必要資金", "総合利回り", "売建上限", "長期優遇", "制度信用指標", "権利月",
]

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)


def get_business_days_left(target_date: dt.date | None = None) -> int:
    """仕様名エイリアス。target_date省略時は今日→権利付最終日のD-Nを返す。"""
    return business_days_left(config_today() if target_date is None else target_date)
