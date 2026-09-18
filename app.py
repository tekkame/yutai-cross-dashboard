# -*- coding: utf-8 -*-
"""
app.py - 株主優待クロス在庫トラッカー ＆ 実戦意思決定ダッシュボード
【監視銘柄ピン留め完全一本化 ＆ 確実な多層クラウド永続化版】
- ⭐ 監視リスト ＝ ピン留めリスト に完全一本化（目的の重複を解消）
- 🎯 画面上部に「⭐ 監視・目標銘柄ハイライト」（拘束資金合計・見込純利益計・対象カード一覧）
- ⚡ 実戦ボード data_editor による「⭐」チェックボックス直接操作（辞書キー比較で確実に検知 ＆ 即座に画面反映）
- 💾 Streamlit Cloud 完全対応の多層永続化（Session + Local File + GitHub API Commit + GitHub Repo Sync）
- 🗓 日時別 在庫推移マトリクス ＆ 📈 日興在庫時系列推移チャート
- 🚀 GitHub Actions 1クリックオンデマンド・スクレイピング起動
"""

from __future__ import annotations

import base64
import calendar
import datetime as dt
import html
import io
import json
import os
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# 日本標準時 (JST = UTC+9) 定義（Streamlit Cloud UTC環境での時刻ズレ完全解消）
JST = dt.timezone(dt.timedelta(hours=9))

def get_now_jst() -> dt.datetime:
    """常に日本標準時（JST）の現在日時（naive datetime）を返す"""
    return dt.datetime.now(JST).replace(tzinfo=None)

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st
from scrapers.routine_yutai import KNOWN_YUTAI_VALUES

# ============================================================
# 1. ページ初期設定 & 超高密度CSS
# ============================================================
st.set_page_config(
    page_title="優待クロス在庫トラッカー",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="auto",
)

ULTRA_COMPACT_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Noto+Sans+JP:wght@400;500;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Noto Sans JP', -apple-system, BlinkMacSystemFont, sans-serif;
    font-size: 12.5px;
    letter-spacing: -0.015em;
}

/* 全体ダークモード基調 */
.stApp {
    background-color: #0b0f19 !important;
    color: #f1f5f9 !important;
}

/* サイドバー */
section[data-testid="stSidebar"] {
    background-color: #0d1322 !important;
    border-right: 1px solid #1e293b !important;
}

section[data-testid="stSidebar"] hr {
    border-color: #1e293b !important;
}

section[data-testid="stSidebar"] .stMarkdown h1,
section[data-testid="stSidebar"] .stMarkdown h2,
section[data-testid="stSidebar"] .stMarkdown h3,
section[data-testid="stSidebar"] .stMarkdown h4,
section[data-testid="stSidebar"] .stMarkdown h5 {
    color: #f8fafc !important;
}

/* メインヘッダー */
header[data-testid="stHeader"] {
    background-color: rgba(11, 15, 25, 0.85) !important;
    backdrop-filter: blur(8px) !important;
    border-bottom: 1px solid #1e293b !important;
}

/* テキスト＆ラベル */
label, .stMarkdown p, .stCaption, span {
    color: #e2e8f0;
}
.stCaption {
    color: #94a3b8 !important;
}

.main .block-container {
    padding-top: 0.4rem !important;
    padding-bottom: 1.2rem !important;
    padding-left: 0.8rem !important;
    padding-right: 0.8rem !important;
    max-width: 100% !important;
}

.status-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: #090d16;
    color: #f8fafc;
    border-radius: 6px;
    padding: 0.35rem 0.8rem;
    margin-bottom: 0.35rem;
    border: 1px solid #1e293b;
}

.status-bar-title {
    font-size: 13.5px;
    font-weight: 700;
    display: flex;
    align-items: center;
    gap: 0.45rem;
}

.status-tags {
    display: flex;
    align-items: center;
    gap: 0.35rem;
    font-size: 11px;
}

.tag {
    padding: 0.12rem 0.4rem;
    border-radius: 4px;
    font-weight: 600;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
}

.tag-blue   { background: #1e3a8a; color: #93c5fd; border: 1px solid #3b82f6; }
.tag-green  { background: #064e3b; color: #6ee7b7; border: 1px solid #10b981; }
.tag-amber  { background: #78350f; color: #fde68a; border: 1px solid #f59e0b; }
.tag-red    { background: #7f1d1d; color: #fca5a5; border: 1px solid #ef4444; }
.tag-purple { background: #581c87; color: #f0abfc; border: 1px solid #a855f7; }
.tag-gray   { background: #1e293b; color: #94a3b8; border: 1px solid #334155; }

/* 監視ハイライト用CSS */
.target-highlight-panel {
    background: linear-gradient(145deg, #1e293b 0%, #0f172a 100%);
    border: 1px solid #fbbf24;
    border-radius: 8px;
    padding: 0.65rem 0.9rem;
    margin-bottom: 0.5rem;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.2), 0 2px 4px -1px rgba(0, 0, 0, 0.1);
}

.target-header {
    color: #fbbf24;
    font-size: 13.5px;
    font-weight: 700;
    margin-bottom: 0.4rem;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    border-bottom: 1px solid #334155;
    padding-bottom: 0.25rem;
}

.target-summary {
    display: flex;
    gap: 1.5rem;
    font-size: 12px;
    color: #e2e8f0;
    margin-bottom: 0.4rem;
}

.target-summary-item span.label {
    color: #94a3b8;
    margin-right: 0.25rem;
}

.target-summary-item span.value {
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
    color: #fff;
}

.target-item-row {
    display: grid;
    grid-template-columns: 46px 110px 65px 90px 75px 160px auto 70px 85px 65px 68px 45px 65px;
    gap: 0.35rem;
    align-items: center;
    padding: 0.2rem 0;
    border-bottom: 1px dashed #334155;
    font-size: 11.5px;
}

.target-item-row:last-child {
    border-bottom: none;
}

.target-code { font-family: 'JetBrains Mono', monospace; color: #93c5fd; font-weight: 600; }
.target-name { color: #f1f5f9; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.target-yutai { color: #cbd5e1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-size: 11px; }

div[data-testid="stVerticalBlock"] > div {
    gap: 0.2rem !important;
}

/* ボタン群 */
div.stButton > button {
    padding: 0.22rem 0.6rem !important;
    font-size: 11.5px !important;
    border-radius: 5px !important;
    min-height: auto !important;
    background-color: #1e293b !important;
    color: #f1f5f9 !important;
    border: 1px solid #334155 !important;
    transition: all 0.15s ease-in-out !important;
    box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.25) !important;
}
div.stButton > button:hover {
    background-color: #2563eb !important;
    color: #ffffff !important;
    border-color: #3b82f6 !important;
    box-shadow: 0 0 8px rgba(59, 130, 246, 0.4) !important;
}
div.stButton > button[kind="primary"] {
    background: linear-gradient(135deg, #2563eb 0%, #1d4ed8 100%) !important;
    color: #ffffff !important;
    border: 1px solid #3b82f6 !important;
    box-shadow: 0 2px 4px rgba(37, 99, 235, 0.3) !important;
}
div.stButton > button[kind="primary"]:hover {
    background: linear-gradient(135deg, #3b82f6 0%, #2563eb 100%) !important;
    box-shadow: 0 0 12px rgba(59, 130, 246, 0.5) !important;
}

/* 入力欄（テキスト・数値） */
div[data-baseweb="input"] {
    background-color: #111827 !important;
    border-color: #334155 !important;
    border-radius: 5px !important;
}
div[data-baseweb="input"] input {
    background-color: transparent !important;
    color: #f8fafc !important;
    font-size: 11.5px !important;
    padding: 0.2rem 0.45rem !important;
}
div[data-baseweb="input"]:focus-within {
    border-color: #38bdf8 !important;
    box-shadow: 0 0 0 1px #38bdf8 !important;
}

/* セレクトボックス & マルチセレクト */
div[data-baseweb="select"] > div {
    background-color: #111827 !important;
    color: #f8fafc !important;
    border-color: #334155 !important;
    border-radius: 5px !important;
    font-size: 11.5px !important;
}
div[data-baseweb="select"] span {
    color: #f8fafc !important;
}
div[data-baseweb="popover"] > div, ul[role="listbox"] {
    background-color: #111827 !important;
    border: 1px solid #334155 !important;
    color: #f8fafc !important;
}
li[role="option"] {
    color: #e2e8f0 !important;
    background-color: transparent !important;
}
li[role="option"]:hover, li[role="option"][aria-selected="true"] {
    background-color: #1e3a8a !important;
    color: #93c5fd !important;
}

/* タブ */
.stTabs [data-baseweb="tab-list"] {
    gap: 0.35rem;
    margin-bottom: 0.35rem;
    border-bottom: 1px solid #1e293b !important;
    background-color: transparent !important;
}
.stTabs [data-baseweb="tab"] {
    padding: 0.35rem 0.85rem !important;
    font-size: 12px !important;
    font-weight: 600 !important;
    color: #94a3b8 !important;
    border-radius: 4px 4px 0 0 !important;
    border: none !important;
    background-color: transparent !important;
    transition: color 0.15s ease !important;
}
.stTabs [data-baseweb="tab"]:hover {
    color: #cbd5e1 !important;
}
.stTabs [data-baseweb="tab"][aria-selected="true"] {
    color: #38bdf8 !important;
    border-bottom: 2px solid #38bdf8 !important;
}

/* エキスパンダー */
div[data-testid="stExpander"] {
    background-color: #0f172a !important;
    border: 1px solid #1e293b !important;
    border-radius: 6px !important;
    margin-bottom: 0.4rem !important;
}
div[data-testid="stExpander"] summary {
    color: #f1f5f9 !important;
    font-weight: 600 !important;
}
div[data-testid="stExpander"] summary:hover {
    color: #38bdf8 !important;
}
div[data-testid="stExpander"] > div[role="region"] {
    border-top: 1px solid #1e293b !important;
    padding-top: 0.5rem !important;
}

/* チェックボックス */
div[data-testid="stCheckbox"] label span[role="checkbox"] {
    background-color: #111827 !important;
    border-color: #475569 !important;
}
div[data-testid="stCheckbox"] label span[role="checkbox"][aria-checked="true"] {
    background-color: #2563eb !important;
    border-color: #3b82f6 !important;
}

/* テーブル & データグリッド */
div[data-testid="stDataFrame"], div[data-testid="stDataEditor"] {
    font-size: 11px !important;
    border-radius: 6px !important;
    border: 1px solid #1e293b !important;
    overflow: hidden;
    background-color: #0f172a !important;
}

/* スクロールバーのダークスタイル */
::-webkit-scrollbar {
    width: 7px;
    height: 7px;
}
::-webkit-scrollbar-track {
    background: #0b0f19;
}
::-webkit-scrollbar-thumb {
    background: #1e293b;
    border-radius: 4px;
}
::-webkit-scrollbar-thumb:hover {
    background: #334155;
}
</style>
"""
st.markdown(ULTRA_COMPACT_CSS, unsafe_allow_html=True)

# ============================================================
# 2. 定数 & ファイルパス
# ============================================================
def safe_get_secret(key: str, default: str = "") -> str:
    """Streamlit Secrets が未設定の環境でも例外を投げずに安全に値を取得"""
    try:
        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.environ.get(key, default)

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
WATCHLIST_FILE = DATA_DIR / "watchlist.json"
SETTINGS_FILE = DATA_DIR / "user_settings.json"
STOCK_PRICES_CACHE_FILE = DATA_DIR / "stock_prices_cache.json"
APP_SECRET_KEY = safe_get_secret("APP_KEY", "yutai777")
APP_VERSION = "v13.2 (Data Freshness Optimization & Dash Elimination & Precision Accuracy)"

# 上場廃止・持株会社統合・TOB成立済みの過去銘柄（画面・分析・集計から完全除外）
DELISTED_CODES = {
    "2352",  # ＷＯＷ　ＷＯＲＬＤ (上場廃止・持株会社化)
    "3254",  # プレサンスコーポレーション (オープンハウスTOB上場廃止)
    "3528",  # ミライノベート (Jトラスト吸収合併上場廃止)
    "3814",  # アルファクス・フード・システム (上場廃止)
    "4333",  # 東邦システムサイエンス (TOB上場廃止)
    "4653",  # ダイオーズ (MBO上場廃止)
    "6628",  # オンキヨー (債務超過上場廃止)
    "7118",  # 伸和ホールディングス (取引不能)
    "8356",  # 十六銀行 (十六FG設立に伴い上場廃止)
    "8397",  # 沖縄海邦銀行 (非対象/統合)
    "8521",  # 長野銀行 (八十二銀行経営統合上場廃止)
    "9014",  # 新京成電鉄 (京成電鉄完全子会社化上場廃止)
    "9266",  # 一休 (TOB上場廃止)
    "9479",  # インプレスホールディングス (TOB上場廃止)
    "9728",  # 日本管財 (日本管財HD[9347]設立に伴い上場廃止)
}

# 日興優待クロス料率 (制度買い現引金利: 約3.55%, 一般信用売り貸株料: 1.9%)
DEFAULT_NIKKO_BUY_RATE = 0.0355
DEFAULT_NIKKO_LEND_RATE = 0.019

# 野村證券担保ローン年利 (2.4%)
DEFAULT_NOMURA_RATE = 0.024

def calc_nikko_cost(
    funds_yen: float,
    lend_days: int,
    buy_rate: float = DEFAULT_NIKKO_BUY_RATE,
    lend_rate: float = DEFAULT_NIKKO_LEND_RATE
) -> int:
    """SMBC日興証券 優待クロスコスト計算
    - 信用取引手数料: 無料 (ダイレクトコース・電子交付)
    - 買建現引金利: 制度信用買い 3.55% (1日分)
    - 貸株料: 一般信用売り 1.9% × lend_days (権利落ち日までの実日数)
    公式数式・enjoy-lcl サイトと1円の狂いもなく完全一致
    """
    if funds_yen is None or funds_yen <= 0 or funds_yen >= 99999990:
        return 0
    days = max(1, int(lend_days))
    buy_interest = funds_yen * buy_rate / 365.0
    lend_fee = funds_yen * lend_rate / 365.0 * days
    return int(round(buy_interest + lend_fee))

def pick_first_valid(*vals: Any) -> Any:
    """falsyな数値（0や0.0等）を落とさずに先頭の有効な値を取得"""
    for v in vals:
        if v is not None:
            s = str(v).strip()
            if s not in ("", "―", "-", "ー", "nan", "None", "null"):
                return v
    return "―"

def calc_nomura_daily_interest(loan_man: float, rate: float = DEFAULT_NOMURA_RATE) -> int:
    """野村證券Web担保ローン 1日あたりの利息 (円)
    - loan_man: 借入金額 (万円)
    - rate: 年利 (デフォルト 2.4%)
    """
    if loan_man is None or loan_man <= 0:
        return 0
    loan_yen = loan_man * 10000.0
    return int(round(loan_yen * rate / 365.0))

def calc_breakeven_wait_days(
    yutai_val: Optional[float],
    funds_yen: Optional[float],
    current_nikko_cost: int,
    nomura_daily_cost: int = 0,
    lend_rate: float = DEFAULT_NIKKO_LEND_RATE
) -> Optional[int]:
    """優待価値に対して、今クロスした場合の損益分岐待機日数（あと何日待てるか）を算出
    ★個別銘柄行では日興信用貸株料の余力を純粋に算出（ポートフォリオ野村利息は総合カードで一括合算）
    - 1日あたり貸株料: funds_yen * 1.9% / 365
    - 残余バッファ = 優待価値 - 現在の日興コスト
    - 待機可能日数 = 残余バッファ / 1日あたり貸株料
    """
    if yutai_val is None or yutai_val <= 0 or funds_yen is None or funds_yen <= 0 or funds_yen >= 99999990:
        return None
    daily_lend_fee = funds_yen * lend_rate / 365.0
    if daily_lend_fee <= 0:
        return None
    rem_margin = yutai_val - current_nikko_cost
    wait_days = int(rem_margin / daily_lend_fee)
    return wait_days

# ============================================================
# 日本の祝日（2024年〜2032年）＆ 東証権利落ち・貸株日数完全自動算出エンジン
# ============================================================
def get_japan_holidays() -> Set[dt.date]:
    """2024年〜2032年の日本の祝日・振替休日・国民の休日一覧（内閣府公表基準）"""
    h: Set[dt.date] = set()
    # 2024年
    h.update([
        dt.date(2024, 1, 1), dt.date(2024, 1, 8), dt.date(2024, 2, 11), dt.date(2024, 2, 12),
        dt.date(2024, 2, 23), dt.date(2024, 3, 20), dt.date(2024, 4, 29), dt.date(2024, 5, 3),
        dt.date(2024, 5, 4), dt.date(2024, 5, 5), dt.date(2024, 5, 6), dt.date(2024, 7, 15),
        dt.date(2024, 8, 11), dt.date(2024, 8, 12), dt.date(2024, 9, 16), dt.date(2024, 9, 22),
        dt.date(2024, 9, 23), dt.date(2024, 10, 14), dt.date(2024, 11, 3), dt.date(2024, 11, 4),
        dt.date(2024, 11, 23)
    ])
    # 2025年
    h.update([
        dt.date(2025, 1, 1), dt.date(2025, 1, 13), dt.date(2025, 2, 11), dt.date(2025, 2, 23),
        dt.date(2025, 2, 24), dt.date(2025, 3, 20), dt.date(2025, 4, 29), dt.date(2025, 5, 3),
        dt.date(2025, 5, 4), dt.date(2025, 5, 5), dt.date(2025, 5, 6), dt.date(2025, 7, 21),
        dt.date(2025, 8, 11), dt.date(2025, 9, 15), dt.date(2025, 9, 23), dt.date(2025, 10, 13),
        dt.date(2025, 11, 3), dt.date(2025, 11, 23), dt.date(2025, 11, 24)
    ])
    # 2026年 (シルバーウィーク: 9/21敬老, 9/22国民の休日, 9/23秋分)
    h.update([
        dt.date(2026, 1, 1), dt.date(2026, 1, 12), dt.date(2026, 2, 11), dt.date(2026, 2, 23),
        dt.date(2026, 3, 20), dt.date(2026, 4, 29), dt.date(2026, 5, 3), dt.date(2026, 5, 4),
        dt.date(2026, 5, 5), dt.date(2026, 5, 6), dt.date(2026, 7, 20), dt.date(2026, 8, 11),
        dt.date(2026, 9, 21), dt.date(2026, 9, 22), dt.date(2026, 9, 23), dt.date(2026, 10, 12),
        dt.date(2026, 11, 3), dt.date(2026, 11, 23)
    ])
    # 2027年
    h.update([
        dt.date(2027, 1, 1), dt.date(2027, 1, 11), dt.date(2027, 2, 11), dt.date(2027, 2, 23),
        dt.date(2027, 3, 21), dt.date(2027, 3, 22), dt.date(2027, 4, 29), dt.date(2027, 5, 3),
        dt.date(2027, 5, 4), dt.date(2027, 5, 5), dt.date(2027, 7, 19), dt.date(2027, 8, 11),
        dt.date(2027, 9, 20), dt.date(2027, 9, 23), dt.date(2027, 10, 11), dt.date(2027, 11, 3),
        dt.date(2027, 11, 23)
    ])
    # 2028年
    h.update([
        dt.date(2028, 1, 1), dt.date(2028, 1, 10), dt.date(2028, 2, 11), dt.date(2028, 2, 23),
        dt.date(2028, 3, 20), dt.date(2028, 4, 29), dt.date(2028, 5, 3), dt.date(2028, 5, 4),
        dt.date(2028, 5, 5), dt.date(2028, 7, 17), dt.date(2028, 8, 11), dt.date(2028, 9, 18),
        dt.date(2028, 9, 22), dt.date(2028, 10, 9), dt.date(2028, 11, 3), dt.date(2028, 11, 23)
    ])
    # 2029年
    h.update([
        dt.date(2029, 1, 1), dt.date(2029, 1, 8), dt.date(2029, 2, 11), dt.date(2029, 2, 12),
        dt.date(2029, 2, 23), dt.date(2029, 3, 20), dt.date(2029, 4, 29), dt.date(2029, 4, 30),
        dt.date(2029, 5, 3), dt.date(2029, 5, 4), dt.date(2029, 5, 5), dt.date(2029, 7, 16),
        dt.date(2029, 8, 11), dt.date(2029, 9, 17), dt.date(2029, 9, 23), dt.date(2029, 9, 24),
        dt.date(2029, 10, 8), dt.date(2029, 11, 3), dt.date(2029, 11, 23)
    ])
    # 2030年
    h.update([
        dt.date(2030, 1, 1), dt.date(2030, 1, 14), dt.date(2030, 2, 11), dt.date(2030, 2, 23),
        dt.date(2030, 2, 24), dt.date(2030, 3, 20), dt.date(2030, 4, 29), dt.date(2030, 5, 3),
        dt.date(2030, 5, 4), dt.date(2030, 5, 5), dt.date(2030, 5, 6), dt.date(2030, 7, 15),
        dt.date(2030, 8, 11), dt.date(2030, 8, 12), dt.date(2030, 9, 16), dt.date(2030, 9, 23),
        dt.date(2030, 10, 14), dt.date(2030, 11, 3), dt.date(2030, 11, 4), dt.date(2030, 11, 23)
    ])
    # 2031年
    h.update([
        dt.date(2031, 1, 1), dt.date(2031, 1, 13), dt.date(2031, 2, 11), dt.date(2031, 2, 23),
        dt.date(2031, 2, 24), dt.date(2031, 3, 21), dt.date(2031, 4, 29), dt.date(2031, 5, 3),
        dt.date(2031, 5, 4), dt.date(2031, 5, 5), dt.date(2031, 5, 6), dt.date(2031, 7, 21),
        dt.date(2031, 8, 11), dt.date(2031, 9, 15), dt.date(2031, 9, 23), dt.date(2031, 10, 13),
        dt.date(2031, 11, 3), dt.date(2031, 11, 23), dt.date(2031, 11, 24)
    ])
    # 2032年 (シルバーウィーク: 9/20敬老, 9/21国民の休日, 9/22秋分)
    h.update([
        dt.date(2032, 1, 1), dt.date(2032, 1, 12), dt.date(2032, 2, 11), dt.date(2032, 2, 23),
        dt.date(2032, 3, 20), dt.date(2032, 4, 29), dt.date(2032, 5, 3), dt.date(2032, 5, 4),
        dt.date(2032, 5, 5), dt.date(2032, 7, 19), dt.date(2032, 8, 11), dt.date(2032, 9, 20),
        dt.date(2032, 9, 21), dt.date(2032, 9, 22), dt.date(2032, 10, 11), dt.date(2032, 11, 3),
        dt.date(2032, 11, 23)
    ])
    return h

JAPAN_HOLIDAYS = get_japan_holidays()

def is_tse_business_day(d: dt.date) -> bool:
    """東証営業日判定（土日・国民の祝日・年末年始 12/31〜1/3 は休業）"""
    if d.weekday() >= 5: return False
    if (d.month == 12 and d.day == 31) or (d.month == 1 and d.day in (1, 2, 3)):
        return False
    if d in JAPAN_HOLIDAYS: return False
    return True

def add_business_days(start_date: dt.date, num_days: int) -> dt.date:
    """東証営業日を加算・減算（土日祝・年末年始を自動スキップ）"""
    cur = start_date
    step = 1 if num_days >= 0 else -1
    rem = abs(num_days)
    while rem > 0:
        cur += dt.timedelta(days=step)
        if is_tse_business_day(cur):
            rem -= 1
    return cur

def get_settlement_date(exec_date: dt.date) -> dt.date:
    """約定日の受渡日 (T+2 営業日後) を算出"""
    return add_business_days(exec_date, 2)

def get_current_execution_date(now_dt: Optional[dt.datetime] = None) -> dt.date:
    """現在日時から今注文を出した場合の東証約定日を判定
    - 平日 15:30 より前: 当日約定
    - 平日 15:30 以降 または 東証休業日: 翌東証営業日約定
    ★Streamlit Cloud (UTC) 環境対策: now_dt が未指定時は常に JST (日本時間) を使用
    """
    if now_dt is None:
        now_dt = get_now_jst()
    today = now_dt.date()
    if is_tse_business_day(today) and now_dt.time() < dt.time(15, 30):
        return today
    cur = today + dt.timedelta(days=1)
    while not is_tse_business_day(cur):
        cur += dt.timedelta(days=1)
    return cur

def parse_rights_month(val: Any, default_month_str: Optional[str] = None) -> Tuple[Optional[int], int, int]:
    """権利年月文字列（例: '2026-09-20', '2026-09', '2027/03/20', '9月20日', '9月', '9', '20日'等）を解析
    戻り値: (year, month, day)
    - year: 西暦年（指定がある場合。未指定なら default_month_str または None）
    - month: 権利月 (1〜12)
    - day: 権利日 (20日権利銘柄は 20, 月末権利銘柄は 0)
    """
    def_y, def_m = None, 9
    if default_month_str:
        m_def = re.search(r"(\d{4})[-/](\d{1,2})", str(default_month_str))
        if m_def:
            def_y, def_m = int(m_def.group(1)), int(m_def.group(2))
        else:
            m_def2 = re.search(r"^(\d{1,2})", str(default_month_str))
            if m_def2:
                def_m = int(m_def2.group(1))

    if val is None or str(val).strip() in ("", "-", "―", "nan", "None"):
        return (def_y, def_m, 0)
    s = str(val).strip()
    
    # 明確に ISO 形式 YYYY-MM-DD や YYYY/MM/DD を抽出
    m_full = re.search(r"(\d{4})[-/](\d{1,2})[-/](\d{1,2})", s)
    if m_full:
        y = int(m_full.group(1))
        m = int(m_full.group(2))
        d_val = int(m_full.group(3))
        d = 20 if d_val == 20 else (0 if d_val >= 28 else d_val)
        return (y, m, d)

    is_20th = bool(
        re.search(r"20\s*日", s) or
        re.search(r"[-/](?:20)(?:[^\d]|$)", s)
    )

    # YYYY-MM または YYYY/MM
    m_ym = re.search(r"(\d{4})[-/](\d{1,2})", s)
    if m_ym:
        y = int(m_ym.group(1))
        m = int(m_ym.group(2))
        d = 20 if is_20th else 0
        return (y, m, d)

    # 4桁年なしの場合: "9月20日", "9月", "9"
    d = 20 if is_20th else 0
    m_m = re.search(r"(\d{1,2})\s*月", s)
    if m_m:
        return (def_y, int(m_m.group(1)), d)
    m_digit = re.search(r"^(\d{1,2})$", s)
    if m_digit:
        return (def_y, int(m_digit.group(1)), d)

    return (def_y, def_m, d)

def get_stock_rights_dates(year: int, month: int, day: int = 0) -> Tuple[dt.date, dt.date, dt.date, dt.date]:
    """対象年月の (権利確定日, 権利付最終売買日, 権利落ち日, 現渡受渡日) を算出"""
    if day == 0:
        _, last_d = calendar.monthrange(year, month)
        target = dt.date(year, month, last_d)
    else:
        target = dt.date(year, month, day)

    # 権利確定日 (休業日の場合は前営業日)
    rec_d = target
    while not is_tse_business_day(rec_d):
        rec_d -= dt.timedelta(days=1)

    # 権利付最終売買日 (T-2営業日)
    last_trade = add_business_days(rec_d, -2)

    # 権利落ち日 (翌営業日)
    drop_d = add_business_days(last_trade, 1)

    # 現渡の受渡日 (権利落ち日の2営業日後 ＝ 信用売建玉返済受渡日)
    close_settle = get_settlement_date(drop_d)

    return rec_d, last_trade, drop_d, close_settle

def calc_stock_lend_days(
    rights_val: Any,
    now_dt: Optional[dt.datetime] = None,
    default_rights_month: Optional[str] = None
) -> Tuple[int, dt.date, dt.date, dt.date]:
    """対象銘柄の権利年月と現在日時から、今約定した場合の【想定貸株日数】を完全自動計算
    戻り値: (lend_days, exec_date, open_settle, close_settle)
    ★致命的バグ修正:
      約定予定日が権利付最終売買日を過ぎている場合、翌年に飛ばさず lend_days = 0（権利落ち済・注文不可）を返す！
    """
    if now_dt is None:
        now_dt = get_now_jst()
    exec_d = get_current_execution_date(now_dt)

    req_year, month, day = parse_rights_month(rights_val, default_month_str=default_rights_month)

    year = req_year if req_year is not None else exec_d.year
    rec_d, last_trade, drop_d, close_settle = get_stock_rights_dates(year, month, day)

    # 新規売建受渡日 (約定日の2営業日後)
    open_settle = get_settlement_date(exec_d)

    # ★ 権利付最終売買日を超過している場合は翌年に送らず権利落ち（0日）とする
    if exec_d > last_trade:
        return 0, exec_d, open_settle, close_settle

    # 日興証券公式ルール: 信用取引貸株料・金利は新規受渡日から返済受渡日までの「両端入れ」
    lend_days = max(1, (close_settle - open_settle).days + 1)
    return lend_days, exec_d, open_settle, close_settle

# ============================================================
# 3. 堅牢なフォーマッター
# ============================================================
def to_float(v: Any) -> Optional[float]:
    if v is None or pd.isna(v) or v == "": return None
    try:
        val = float(v)
        return None if np.isnan(val) else val
    except (ValueError, TypeError): return None

def to_int(v: Any) -> Optional[int]:
    f = to_float(v)
    return int(round(f)) if f is not None else None

def fmt_qty(v: Any) -> str:
    f = to_float(v)
    if f is None: return "取扱無"
    if f >= 9999990: return "大量"
    if f == 0: return "0 (枯渇)"
    if f >= 10000: return f"{f/10000:.1f}万"
    return f"{int(f):,}"

def parse_qty_safe(v: Any) -> Optional[float]:
    if v is None or pd.isna(v): return None
    if isinstance(v, (int, float)):
        val = float(v)
        return None if np.isnan(val) else val
    s = str(v).strip().replace(",", "").replace(" ", "")
    if s in ("", "-", "―", "ー", "null", "None", "nan", "取扱なし", "取扱無"): return None
    if "残無" in s or s in ("×", "✕"): return 0.0
    if "大量" in s: return 9999999.0
    if s in ("◎", "▲"): return None
    m = re.search(r"^([\d.]+)万$", s)
    if m:
        try: return round(float(m.group(1)) * 10000)
        except ValueError: pass
    m = re.search(r"^([\d.]+)$", s)
    if m:
        try: return float(m.group(1))
        except ValueError: pass
    return None

def fmt_code(v: Any) -> str:
    if v is None or pd.isna(v): return ""
    s = str(v).split(".")[0].strip()
    return s.zfill(4) if len(s) <= 4 and s.isdigit() else s

def fmt_signal(v: Any) -> str:
    if v is None or (not isinstance(v, str) and pd.isna(v)): return "取扱無"
    s = str(v).strip()
    if s in ("", "-", "―", "ー", "null", "None", "nan", "取扱なし", "取扱無"): return "取扱無"
    if s in ("2", "2.0", "◎"): return "◎"
    if s in ("1", "1.0", "▲"): return "▲"
    if s in ("0", "0.0", "×", "✕", "残無"): return "×"
    return s

def fmt_funds_man(funds_yen: Any) -> str:
    """最低取得価格を万円単位で簡潔にフォーマット (例: 16.0万, 3.2万)"""
    f = to_float(funds_yen)
    if f is None or f >= 99999990 or f <= 0:
        return "―"
    man = f / 10000.0
    if man >= 100:
        return f"{int(round(man))}万"
    return f"{man:.1f}万"

# ============================================================
# 株価キャッシュ & 自動補完エンジン
# ============================================================
_STOCK_PRICES_CACHE: Dict[str, float] = {}

def get_stock_price(code: str) -> Optional[float]:
    """キャッシュおよび必要に応じて株探から株価を取得（メモリ＋ファイルキャッシュ）"""
    global _STOCK_PRICES_CACHE
    c_norm = str(code).strip().zfill(4)
    if not _STOCK_PRICES_CACHE and STOCK_PRICES_CACHE_FILE.exists():
        try:
            _STOCK_PRICES_CACHE = json.loads(STOCK_PRICES_CACHE_FILE.read_text(encoding="utf-8"))
        except Exception:
            _STOCK_PRICES_CACHE = {}
    if c_norm in _STOCK_PRICES_CACHE and _STOCK_PRICES_CACHE[c_norm] > 0:
        return _STOCK_PRICES_CACHE[c_norm]

    # キャッシュになければ株探から1回だけフェッチ
    url = f"https://kabutan.jp/stock/?code={c_norm}"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=3) as resp:
            html_text = resp.read().decode("utf-8", errors="ignore")
            m = re.search(r'<span class="kabuka">([0-9,.]+)円</span>', html_text)
            if m:
                val = float(m.group(1).replace(",", ""))
                _STOCK_PRICES_CACHE[c_norm] = val
                try:
                    STOCK_PRICES_CACHE_FILE.write_text(json.dumps(_STOCK_PRICES_CACHE, ensure_ascii=False, indent=2), encoding="utf-8")
                except Exception:
                    pass
                return val
    except Exception:
        pass
    return None

def extract_shares(row: Any, m_row: Any, yutai_content: str) -> int:
    """データ行または優待内容テキストから必要株数を抽出（デフォルト100株）"""
    for obj in [row, m_row]:
        if obj is not None:
            s = obj.get("shares") or obj.get("株数")
            if s is not None:
                try:
                    v = int(float(s))
                    if v > 0: return v
                except Exception:
                    pass
    if isinstance(yutai_content, str):
        m = re.search(r'【(\d+)株】', yutai_content)
        if m:
            try: return int(m.group(1))
            except Exception: pass
    return 100

# 主要・人気優待銘柄の正確かつ具体的な優待品名・金額マスタ（補完用）
KNOWN_YUTAI = {
    "1822": "QUOカード 500円分",
    "2267": "ヤクルト「ライト会員」入会権 (約1,000円相当)",
    "2464": "BBT 10%優待割引券",
    "2586": "フルッタフルッタ 公式EC15%割引",
    "2818": "ピエトロ 通信販売10%割引券",
    "3088": "マツキヨ商品券・ポイント 2,000円分",
    "3167": "QUOカード 500円分 (または飲料等)",
    "3529": "アツギ 30%優待割引券",
    "3569": "セーレン 20%優待割引券",
    "3679": "選べるギフトカタログ (約3,000円相当)",
    "3710": "ジョルダン 乗換案内PREMIUM 半年利用権 (約1,980円相当)",
    "4061": "デンカ 化粧品優待価格販売 (約2,000円相当)",
    "4376": "くふうカンパニー グループサービス無料利用券・割引券",
    "4539": "日本ケミファ ヘルスケア商品特別優待販売",
    "4543": "テルモ 自社施設見学会 (抽選)",
    "4658": "QUOカード 1,000円分",
    "4661": "東京ディズニーリゾート 1デーパスポート 1枚 (約8,900円相当)",
    "4719": "アルファS オリジナルカレンダー (約500円相当)",
    "4751": "ABEMAプレミアム 3ヶ月無料 (約3,540円相当)",
    "5262": "QUOカード 1,000円分",
    "6412": "PGMゴルフ割引優待券 2,000円分",
    "7419": "ノジマ買物優待割引券 (10%割引×5枚)",
    "7458": "QUOカード 1,000円分",
    "7513": "ビックカメラ・コジマ共通商品券 1,000円分",
    "7638": "NEW ART HOLDINGS 優待割引カード",
    "8052": "QUOカード 2,000円分",
    "8136": "ピューロランド共通優待券3枚+買物券1,000円",
    "8173": "Joshin買物優待券 5,000円分 (200円引×25枚)",
    "8281": "ゼビオ 買物優待券 (20%引1枚+10%引4枚)",
    "9201": "株主優待割引券 (国内線50%割引)",
    "9202": "株主優待番号ご案内書 (国内線50%割引)",
    "9347": "日本管財 ギフトカタログ 2,000円相当",
    "9405": "QUOカード 500円分",
    "9831": "お買物優待券 1,000円分 (500円引×2枚)",
}

def fmt_yutai_enhanced(content: str, yutai_val: Optional[float] = None, code: str = "") -> str:
    """優待内容に数値（金額・数量）や種類を的確に追加し、簡潔かつ具体的に表示
    ★マスタの最新内容を最優先とし、未取得・空の場合のみ KNOWN_YUTAI で補完する"""
    c = str(code).strip()

    # マスタに有効な優待内容が存在する場合は、それを整形して活用（最新の優待改定に追従）
    if content and not pd.isna(content) and str(content).strip() not in ("", "-", "―", "nan", "None"):
        s = str(content).strip()
        s = re.sub(r"【[\d,]+株[^】]*】", "", s)
        s = re.sub(r"【注：[^】]*】", "", s)
        s = re.sub(r"\[[^\]]*\]", "", s).strip()
        if re.search(r"\d+円|\d+万|相当|割引|無料|株主優待券|\d+枚|\d+kg|ポイント", s):
            return s[:33] + "…" if len(s) > 34 else s
        kind_map = {
            "QUO": "QUOカード", "QUO等": "QUOカード等", "ﾎﾟｲﾝﾄ等": "買物ポイント等",
            "ポイント等": "買物ポイント等", "優待券": "買物・施設優待券", "自社製品": "自社製品詰合せ",
            "割引券": "優待割引券", "お米": "お米ギフト", "カタログ": "グルメ・ギフトカタログ"
        }
        for k, v in kind_map.items():
            if s == k:
                if yutai_val and yutai_val > 0:
                    return f"{v} ({int(round(yutai_val)):,}円相当)"
                return v
        if yutai_val and yutai_val > 0:
            return f"{s} ({int(round(yutai_val)):,}円相当)"
        return s

    # マスタが空・未取得の場合のみ KNOWN_YUTAI で安全に補完
    if c in KNOWN_YUTAI:
        return KNOWN_YUTAI[c]

    if not content or pd.isna(content):
        if yutai_val and yutai_val > 0:
            return f"優待品 ({int(round(yutai_val)):,}円相当)"
        return "―"

    s = str(content).strip()
    # 【100株】等の株数指定を除去
    s = re.sub(r"【[\d,]+株[^】]*】", "", s)
    # 【注：...】などの注記を除去
    s = re.sub(r"【注：[^】]*】", "", s)
    s = re.sub(r"\[[^\]]*\]", "", s).strip()

    # すでに金額・数量等の数値が含まれている場合はそのまま活かす
    if re.search(r"\d+円|\d+万|相当|割引|無料|株主優待券|\d+枚|\d+kg|ポイント", s):
        if len(s) > 34:
            return s[:33] + "…"
        return s

    # 金額が入っていない短い品目名（QUO, 優待券, 自社製品等）の場合、種類を具体化し優待価値で補完
    kind_map = {
        "QUO": "QUOカード",
        "QUO等": "QUOカード等",
        "ﾎﾟｲﾝﾄ等": "買物ポイント等",
        "ポイント等": "買物ポイント等",
        "優待券": "買物・施設優待券",
        "自社製品": "自社製品詰合せ",
        "自Ｇ製品": "自社グループ製品",
        "自社商品": "自社商品詰合せ",
        "カタログ": "カタログギフト",
        "ギフト": "ギフトカード",
        "米": "お米",
        "クーポン": "割引クーポン",
    }
    for k, v in kind_map.items():
        if s == k:
            s = v
            break

    val_str = ""
    if yutai_val and yutai_val > 10:
        val_str = f" ({int(round(yutai_val)):,}円相当)"

    res = f"{s}{val_str}" if val_str else s
    if len(res) > 34:
        return res[:33] + "…"
    return res

def fmt_yutai_compact(content: str, yutai_val: Optional[float] = None, code: str = "") -> str:
    return fmt_yutai_enhanced(content, yutai_val, code)

def build_smart_trend(g_unique: pd.DataFrame, snap_label_map: Dict[str, str]) -> Tuple[str, str]:
    """直感的にトレンドが把握できる見やすい残数推移（クリーンテキスト ＆ HTMLカラーバッジ）を生成"""
    snaps = []
    for _, r_snap in g_unique.iterrows():
        ts = r_snap["timestamp"]
        lbl = snap_label_map.get(ts, "")
        n_val = to_float(r_snap.get("nikko"))
        s_raw = r_snap.get("rtn_sbi") or r_snap.get("sbi") or "―"
        s_sig = fmt_signal(str(s_raw))
        snaps.append((lbl, n_val, s_sig))

    if not snaps:
        return "―", '<span style="color:#64748b;">―</span>'

    # 日興推移
    n_vals = [s[1] for s in snaps if s[1] is not None]
    if not n_vals:
        n_text = "日興: ―"
        n_html = '<span style="color:#64748b;">日興: ―</span>'
    elif len(n_vals) == 1:
        n_text = f"日興 {fmt_qty(n_vals[0])}"
        n_html = f'<span style="color:#94a3b8;">日興</span> <span style="color:#f1f5f9;font-weight:600;">{fmt_qty(n_vals[0])}</span>'
    else:
        prev_v = n_vals[-2]
        now_v = n_vals[-1]
        diff = now_v - prev_v
        if diff < 0:
            if diff <= -3000:
                n_text = f"日興 {fmt_qty(prev_v)} ↘ {fmt_qty(now_v)} (🚨▼{abs(int(diff)):,})"
                n_html = f'<span style="color:#94a3b8;">日興</span> <span style="color:#94a3b8;">{fmt_qty(prev_v)}</span> <span style="color:#f87171;font-weight:bold;">↘</span> <span style="color:#f87171;font-weight:bold;">{fmt_qty(now_v)}</span> <span style="color:#ef4444;font-size:10px;">(▼{abs(int(diff)):,})</span>'
            else:
                n_text = f"日興 {fmt_qty(prev_v)} ↘ {fmt_qty(now_v)}"
                n_html = f'<span style="color:#94a3b8;">日興</span> <span style="color:#94a3b8;">{fmt_qty(prev_v)}</span> <span style="color:#f87171;font-weight:bold;">↘</span> <span style="color:#f87171;font-weight:600;">{fmt_qty(now_v)}</span>'
        elif diff > 0:
            if prev_v == 0:
                n_text = f"日興 0 🔥 {fmt_qty(now_v)} (補充)"
                n_html = f'<span style="color:#94a3b8;">日興</span> <span style="color:#64748b;">0</span> <span style="color:#f59e0b;font-weight:bold;">🔥</span> <span style="color:#34d399;font-weight:bold;">{fmt_qty(now_v)}</span>'
            else:
                n_text = f"日興 {fmt_qty(prev_v)} ↗ {fmt_qty(now_v)} (+{int(diff):,})"
                n_html = f'<span style="color:#94a3b8;">日興</span> <span style="color:#94a3b8;">{fmt_qty(prev_v)}</span> <span style="color:#34d399;font-weight:bold;">↗</span> <span style="color:#34d399;font-weight:600;">{fmt_qty(now_v)}</span>'
        else:
            if now_v == 0:
                n_text = "日興 0 (枯渇)"
                n_html = '<span style="color:#64748b;">日興 0 (枯渇)</span>'
            else:
                n_text = f"日興 {fmt_qty(now_v)} (維持)"
                n_html = f'<span style="color:#94a3b8;">日興</span> <span style="color:#cbd5e1;font-weight:600;">{fmt_qty(now_v)}</span> <span style="color:#64748b;font-size:10px;">(維持)</span>'

    # SBI推移
    s_vals = [s[2] for s in snaps if s[2] not in ("―", "", None)]
    if not s_vals:
        s_text = "SBI ―"
        s_html = '<span style="color:#64748b;">SBI ―</span>'
    elif len(s_vals) == 1:
        s_text = f"SBI {s_vals[0]}"
        s_col = "#a7f3d0" if s_vals[0] == "◎" else ("#f87171" if s_vals[0] in ("×", "▲") else "#94a3b8")
        s_html = f'<span style="color:#94a3b8;">SBI</span> <span style="color:{s_col};font-weight:bold;">{s_vals[0]}</span>'
    else:
        prev_s = s_vals[-2]
        now_s = s_vals[-1]
        if prev_s == now_s:
            s_text = f"SBI {now_s}"
            s_col = "#a7f3d0" if now_s == "◎" else ("#f87171" if now_s in ("×", "▲") else "#94a3b8")
            s_html = f'<span style="color:#94a3b8;">SBI</span> <span style="color:{s_col};font-weight:bold;">{now_s}</span>'
        else:
            if prev_s == "◎" and now_s in ("▲", "×"):
                s_text = f"SBI 🚨{prev_s}➔{now_s}"
                s_html = f'<span style="color:#94a3b8;">SBI</span> <span style="color:#a7f3d0;">{prev_s}</span> <span style="color:#ef4444;font-weight:bold;">➔</span> <span style="color:#f87171;font-weight:bold;background:#7f1d1d;padding:1px 4px;border-radius:3px;">🚨{now_s}</span>'
            elif prev_s == "▲" and now_s == "×":
                s_text = f"SBI 💥{prev_s}➔{now_s}"
                s_html = f'<span style="color:#94a3b8;">SBI</span> <span style="color:#fca5a5;">{prev_s}</span> <span style="color:#ef4444;font-weight:bold;">➔</span> <span style="color:#f87171;font-weight:bold;background:#7f1d1d;padding:1px 4px;border-radius:3px;">💥{now_s}</span>'
            elif prev_s in ("×", "▲") and now_s == "◎":
                s_text = f"SBI 🔥{prev_s}➔{now_s}"
                s_html = f'<span style="color:#94a3b8;">SBI</span> <span style="color:#94a3b8;">{prev_s}</span> <span style="color:#34d399;font-weight:bold;">➔</span> <span style="color:#a7f3d0;font-weight:bold;background:#065f46;padding:1px 4px;border-radius:3px;">🔥◎</span>'
            else:
                s_text = f"SBI {prev_s}➔{now_s}"
                s_html = f'<span style="color:#94a3b8;">SBI</span> <span style="color:#94a3b8;">{prev_s}➔{now_s}</span>'

    clean_combined = f"{n_text}  |  {s_text}"
    html_combined = f"{n_html} &nbsp;|&nbsp; {s_html}"
    return clean_combined, html_combined

def fmt_other_brokers(kabu_now: Any, rakuten_now: Any, gmo_now: str) -> str:
    """カブ・楽天・GMO等のその他証券残数をコンパクトに連結"""
    parts = []
    k = fmt_qty(kabu_now)
    if k != "―": parts.append(f"カブ:{k}")
    r = fmt_qty(rakuten_now)
    if r != "―": parts.append(f"楽天:{r}")
    g = fmt_signal(gmo_now) if gmo_now not in ("―", "") else ""
    if g and g != "―": parts.append(f"GMO:{g}")
    return " | ".join(parts) if parts else "―"


def get_github_token() -> str:
    """Streamlit Secrets, 環境変数, ローカルファイルから安全にGitHubトークンを取得"""
    t = safe_get_secret("GITHUB_TOKEN", "")
    if t: return t
    for p in [
        BASE_DIR / ".github_token",
        Path("C:/Users/tekka/Desktop/antigravity/mitsubishi_hems/.github_token")
    ]:
        if p.exists() and p.is_file():
            try:
                val = p.read_text(encoding="utf-8").strip()
                if val: return val
            except Exception: pass
    return ""

# ============================================================
# 4. アプリ内直接スクレイピング ＆ 日時基準（Daily Snapshot）抽出
# ============================================================
def run_direct_scrape(rights_arg: Optional[str] = None) -> Tuple[bool, str]:
    """Streamlit アプリ内で直接 Gokigen API ＆ Routine優待データをスクレイピングして即時更新
    ★仕様補足: main.run() における `dry_run` 引数は、本システムでは「外部スプレッドシートに触らず、
      ローカルDATA_DIR配下にCSVを出力・保存するモード」を意味します。
      そのため dry_run=True を指定することで、ローカルおよびクラウドのCSVファイルが確実に更新されます。
    """
    try:
        import main as scraper_main
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        before_csvs = set(DATA_DIR.glob("*.csv"))
        ret = scraper_main.run(
            dry_run=True,  # SheetsではなくローカルCSV出力モード
            out_dir=str(DATA_DIR),
            rights_arg=rights_arg,
            kengi_arg=None,
            watch_expr=None
        )
        if ret == 0:
            after_csvs = set(DATA_DIR.glob("*.csv"))
            new_files = after_csvs - before_csvs
            st.cache_data.clear()
            target_str = f"【{rights_arg}】" if rights_arg else "【当月】"
            file_note = f" (新規CSV: {len(new_files)}件保存済)" if new_files else ""
            return True, f"{target_str} の最新在庫データを直接スクレイピング取得しました！{file_note}"
        return False, f"スクレイピング処理でエラーが発生しました (code: {ret})"
    except Exception as e:
        return False, f"スクレイピング実行例外: {e}"

def extract_meaningful_snapshots(df_hist: pd.DataFrame) -> List[Tuple[str, str]]:
    """手動・自動更新のタイミングの不揃いに左右されず、意味のある日付基準（Daily Snapshot）を抽出。
    各過去日付（昨日以前）: その日の最終取得時点を代表値として1件採用。
    本日（最新日）: 直前値と最新値を採用。
    戻り値: [(timestamp, "M/D"), ...] のリスト (時系列昇順)
    """
    if df_hist is None or df_hist.empty or "timestamp" not in df_hist.columns:
        return []

    d = df_hist.dropna(subset=["timestamp"]).copy()
    if "dt" not in d.columns:
        d["dt"] = pd.to_datetime(d["timestamp"], errors="coerce")
    d = d.dropna(subset=["dt"]).sort_values(by="dt", ascending=True)

    d["date_str"] = d["dt"].dt.strftime("%Y-%m-%d")
    unique_dates = d["date_str"].unique().tolist()
    if not unique_dates:
        return []

    latest_date = unique_dates[-1]
    selected: List[Tuple[str, str]] = []

    # 過去日付 (直近最大2日分): 各日の最終スナップショットを採用
    past_dates = [dt_str for dt_str in unique_dates if dt_str != latest_date]
    for dt_str in past_dates[-2:]:
        sub = d[d["date_str"] == dt_str]
        last_row = sub.iloc[-1]
        ts = last_row["timestamp"]
        label = last_row["dt"].strftime("%m/%d").lstrip("0").replace("/0", "/")
        selected.append((ts, label))

    # 本日 (最新日):
    today_sub = d[d["date_str"] == latest_date]
    today_ts_list = today_sub["timestamp"].unique().tolist()
    if len(today_ts_list) >= 2:
        prev_today = today_sub[today_sub["timestamp"] == today_ts_list[-2]].iloc[-1]
        selected.append((today_ts_list[-2], prev_today["dt"].strftime("%H:%M")))

    # 本日最新
    last_today = today_sub[today_sub["timestamp"] == today_ts_list[-1]].iloc[-1]
    selected.append((today_ts_list[-1], "本日" if past_dates else "最新"))

    return selected

def trigger_github_workflow(token: str, repo: str, ref: str = "main") -> Tuple[bool, str]:
    if not token or not repo:
        return False, "GITHUB_TOKEN または GITHUB_REPO が設定されていません。"

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "Streamlit-Yutai-Dashboard"
    }

    url_list = f"https://api.github.com/repos/{repo}/actions/workflows"
    req_list = urllib.request.Request(url_list, headers=headers)
    try:
        with urllib.request.urlopen(req_list, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            workflows = data.get("workflows", [])
    except Exception as e:
        return False, f"GitHubワークフロー取得エラー: {e}"

    if not workflows:
        return False, "リポジトリ内に実行可能なワークフローが見つかりません。"

    target_wf = next((wf for wf in workflows if any(k in wf.get("path", "").lower() for k in ["scrape", "daily", "main"])), workflows[0])
    wf_id = target_wf.get("id")
    wf_name = target_wf.get("name", "Daily Update")

    url_dispatch = f"https://api.github.com/repos/{repo}/actions/workflows/{wf_id}/dispatches"
    payload = json.dumps({"ref": ref}).encode("utf-8")
    req_dispatch = urllib.request.Request(
        url_dispatch, data=payload, headers={**headers, "Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req_dispatch, timeout=6) as resp:
            if resp.status in (204, 200, 201):
                return True, f"「{wf_name}」を起動しました！ クラウド上で最新スクレイピングを開始します。"
            return False, f"起動ステータス: {resp.status}"
    except Exception as e:
        return False, f"送信エラー: {e}"

# ============================================================
# 5. 監視リスト（⭐ピン留め）永続化マネージャー
# ============================================================
DEFAULT_WATCHLIST = ["1822", "3088", "3167", "4658", "4661", "4751", "6412", "8052", "8173", "8281", "9347", "9405", "9831"]

def load_watchlist_from_disk() -> List[str]:
    """ローカル/リポジトリ同梱の watchlist.json から読み込み（厳密にユーザー指定の銘柄のみ）"""
    if WATCHLIST_FILE.exists():
        try:
            codes = json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
            if isinstance(codes, list) and codes:
                return [fmt_code(c) for c in codes if c]
        except Exception: pass
    return DEFAULT_WATCHLIST.copy()

def save_watchlist_to_disk(codes: List[str]):
    """ローカルディスクへ即座に書き込み"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    clean_codes = sorted(list(set(fmt_code(c) for c in codes if c)))
    WATCHLIST_FILE.write_text(json.dumps(clean_codes, ensure_ascii=False, indent=2), encoding="utf-8")

def fetch_watchlist_from_github(token: str, repo: str) -> Optional[List[str]]:
    """GitHub API から直接最新の data/watchlist.json を取得（Cloud再起動時のローカルディスク不整合・キャッシュ切れを防止）"""
    if not repo: return None
    try:
        url = f"https://raw.githubusercontent.com/{repo}/main/data/watchlist.json"
        req = urllib.request.Request(url, headers={"User-Agent": "Streamlit-Yutai-Dashboard"})
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, list) and data:
                return [fmt_code(c) for c in data if c]
    except Exception:
        pass
    return None

def reload_watchlist_fresh() -> List[str]:
    """GitHub API から直接最新の watchlist.json を強制取得し、ローカルディスク＆セッションへ同期（リスト消失を完全防止）"""
    gh_token = get_github_token()
    gh_repo = safe_get_secret("GITHUB_REPO", "tekkame/yutai-cross-dashboard")
    remote_codes = fetch_watchlist_from_github(gh_token, gh_repo)
    if remote_codes is not None and len(remote_codes) > 0:
        save_watchlist_to_disk(remote_codes)
        return remote_codes
    return load_watchlist_from_disk()

WATCH_VERSION = "v13"

def load_initial_watchlist(df_mast: Optional[pd.DataFrame] = None) -> List[str]:
    """監視リストを多層フェイルオーバーで堅牢にロード
    ⓪ 最新バージョンのURLクエリパラメータ (?watch=...&watch_v=v13)
    ① ローカルの data/watchlist.json (サーバー側マスター)
    ② GitHub リポジトリ上の最新 data/watchlist.json
    ③ デフォルト13銘柄
    """
    # 0. URLクエリパラメータ確認（現行バージョン一致時のみURLを信頼し、古いURLによる逆上書きを完全防止）
    try:
        url_v = str(st.query_params.get("watch_v", "")).strip()
        url_watch = str(st.query_params.get("watch", "")).strip()
        if url_v == WATCH_VERSION and url_watch:
            if url_watch.lower() in ("none", "empty", "clear", "0"):
                save_watchlist_to_disk([])
                return []
            codes = [fmt_code(c.strip()) for c in url_watch.split(",") if c.strip()]
            if codes:
                save_watchlist_to_disk(codes)
                return codes
    except Exception:
        pass

    # 1. ローカルディスク確認（サーバー上の最新 data/watchlist.json を最優先）
    local_codes = None
    if WATCHLIST_FILE.exists():
        try:
            codes = json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
            if isinstance(codes, list) and len(codes) > 0:
                local_codes = [fmt_code(c) for c in codes if c]
        except Exception:
            pass

    if local_codes is not None and len(local_codes) > 0:
        return local_codes

    # 2. GitHub リポジトリから直接最新の watchlist.json を取得（Cloudコンテナ再起動対策）
    gh_token = get_github_token()
    gh_repo = safe_get_secret("GITHUB_REPO", "tekkame/yutai-cross-dashboard")
    remote_codes = fetch_watchlist_from_github(gh_token, gh_repo)
    if remote_codes is not None and len(remote_codes) > 0:
        save_watchlist_to_disk(remote_codes)
        return remote_codes

    # 3. デフォルト13銘柄
    return DEFAULT_WATCHLIST.copy()

# --- 非同期同期ワーカー (GitHub API) ---
def _sync_to_github_worker(token: str, repo: str, content_str: str, commit_msg: str, file_path: str = "data/watchlist.json"):
    """Streamlit Cloud 上での変更を GitHub リポジトリへ直接コミットして永久保持（競合リトライ付き）"""
    if not token or not repo: return
    for attempt in range(2):  # 最大2回リトライ（SHA衝突・並行コミット対策）
        try:
            url = f"https://api.github.com/repos/{repo}/contents/{file_path}"
            headers = {
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "User-Agent": "Streamlit-Yutai-Dashboard",
            }
            sha = None
            req_get = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req_get, timeout=5) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    sha = data.get("sha")
            except urllib.error.HTTPError as e:
                if e.code != 404: pass
            except Exception: pass

            b64_content = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")
            payload = {"message": commit_msg, "content": b64_content, "branch": "main"}
            if sha: payload["sha"] = sha

            req_put = urllib.request.Request(
                url, data=json.dumps(payload).encode("utf-8"),
                headers={**headers, "Content-Type": "application/json"}, method="PUT"
            )
            with urllib.request.urlopen(req_put, timeout=6) as resp:
                if resp.status in (200, 201):
                    break  # コミット成功
        except urllib.error.HTTPError as he:
            if he.code == 409:  # Conflict: SHAが他スレッドで更新された場合、次ループで最新SHAを取得して再試行
                continue
            break
        except Exception:
            break

def persist_watchlist(current_list: List[str], gh_token: str, gh_repo: str, trigger_code: str = ""):
    """①ローカル保存 + ②URLクエリパラメータ即時同期 + ③GitHubリポジトリ永続化 を実行（単一コミットで競合根絶）"""
    clean_list = sorted(list(set(fmt_code(c) for c in current_list if c)))
    json_str = json.dumps(clean_list, ensure_ascii=False, indent=2)

    # 1. ローカル保存 (即時)
    save_watchlist_to_disk(clean_list)

    # 2. URLクエリパラメータに即時反映（最新バージョンタグ付き）
    try:
        st.query_params["watch_v"] = WATCH_VERSION
        st.query_params["watch"] = ",".join(clean_list) if clean_list else "none"
    except Exception:
        pass

    # 3. GitHubへの非同期コミット (Streamlit Cloud再起動対策: 1回にまとめて送信)
    if gh_token and gh_repo:
        msg = f"Update watchlist: {len(clean_list)} items (changed: {trigger_code})"
        t_gh = threading.Thread(target=_sync_to_github_worker, args=(gh_token, gh_repo, json_str, msg), daemon=True)
        t_gh.start()

def sync_scraped_data_to_github(target_month: str, gh_token: str, gh_repo: str):
    """直接スクレイピングで生成された最新の history および master CSV を GitHub へ非同期コミット"""
    if not (gh_token and gh_repo):
        return
    try:
        h_csvs = sorted(DATA_DIR.glob(f"history_{target_month}_*.csv"))
        m_csvs = sorted(DATA_DIR.glob(f"master_{target_month}_*.csv"))
        if h_csvs:
            latest_h = h_csvs[-1]
            msg_h = f"Auto update {target_month} stock data via Web UI: {latest_h.name}"
            threading.Thread(
                target=_sync_to_github_worker,
                args=(gh_token, gh_repo, latest_h.read_text(encoding="utf-8-sig"), msg_h, f"data/{latest_h.name}"),
                daemon=True
            ).start()
        if m_csvs:
            latest_m = m_csvs[-1]
            msg_m = f"Auto update {target_month} master data via Web UI: {latest_m.name}"
            threading.Thread(
                target=_sync_to_github_worker,
                args=(gh_token, gh_repo, latest_m.read_text(encoding="utf-8-sig"), msg_m, f"data/{latest_m.name}"),
                daemon=True
            ).start()
    except Exception:
        pass

# --- ユーザー設定（野村担保ローン借入額・日興貸株日数）永続化マネージャー ---
DEFAULT_SETTINGS: Dict[str, Any] = {
    "nomura_loan_man": 0.0,
    "nomura_loan_date": "2026-09-01",
    "nomura_rate": DEFAULT_NOMURA_RATE,
    "nikko_lend_days": 14,
    "nikko_mode": "auto",
    "nikko_buy_rate": DEFAULT_NIKKO_BUY_RATE,
    "nikko_lend_rate": DEFAULT_NIKKO_LEND_RATE,
}

def fetch_user_settings_from_github(token: str, repo: str) -> Optional[Dict[str, Any]]:
    """GitHub API / Raw から直接最新の data/user_settings.json を取得（Cloud再起動時の初期化を防止）"""
    if not repo: return None
    try:
        url = f"https://raw.githubusercontent.com/{repo}/main/data/user_settings.json"
        req = urllib.request.Request(url, headers={"User-Agent": "Streamlit-Yutai-Dashboard"})
        if token:
            req.add_header("Authorization", f"Bearer {token}")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return None

def load_user_settings(gh_token: str = "", gh_repo: str = "") -> Dict[str, Any]:
    """ローカル/GitHub/URLパラメータの多層フェイルオーバーでユーザー設定を確実に復元
    ★レースコンディション防止: ローカル設定が保存されている場合はリモートの古い非同期キャッシュで上書きしない"""
    settings = DEFAULT_SETTINGS.copy()
    has_local_saved = False

    # 1. ローカルディスク確認
    if SETTINGS_FILE.exists():
        try:
            data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data:
                settings.update(data)
                has_local_saved = True
        except Exception:
            pass

    # 2. GitHub リポジトリから取得（ローカルが空またはCloud初起動時のみリモートを採用）
    if gh_repo and not has_local_saved:
        remote_data = fetch_user_settings_from_github(gh_token, gh_repo)
        if remote_data and isinstance(remote_data, dict):
            settings.update(remote_data)
            try:
                SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception: pass

    # 3. URL クエリパラメータから復元（ユーザーの直近のブラウザ操作を最優先保持）
    try:
        params = st.query_params
        if "nomura_loan" in params:
            settings["nomura_loan_man"] = float(params["nomura_loan"])
        if "nomura_date" in params:
            val_date = str(params["nomura_date"]).strip()
            dt.datetime.strptime(val_date, "%Y-%m-%d")
            settings["nomura_loan_date"] = val_date
        if "nomura_rate" in params:
            settings["nomura_rate"] = float(params["nomura_rate"])
        if "nikko_mode" in params:
            settings["nikko_mode"] = str(params["nikko_mode"])
        if "nikko_days" in params:
            settings["nikko_lend_days"] = int(params["nikko_days"])
    except Exception:
        pass

    return settings

def save_user_settings(settings: Dict[str, Any], gh_token: str = "", gh_repo: str = ""):
    """ユーザー設定（野村借入額・起算日等）を即座にローカル＆GitHub＆URLへ永続保存"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    json_str = json.dumps(settings, ensure_ascii=False, indent=2)
    try:
        SETTINGS_FILE.write_text(json_str, encoding="utf-8")
    except Exception:
        pass

    # URL クエリパラメータにも即座に同期（ブラウザリロード・別タブ・再訪問時にも100%保持）
    try:
        st.query_params["nomura_loan"] = str(settings.get("nomura_loan_man", 0.0))
        st.query_params["nomura_date"] = str(settings.get("nomura_loan_date", "2026-09-01"))
        st.query_params["nomura_rate"] = f"{float(settings.get('nomura_rate', DEFAULT_NOMURA_RATE)):.4f}"
        st.query_params["nikko_mode"] = str(settings.get("nikko_mode", "auto"))
        st.query_params["nikko_days"] = str(settings.get("nikko_lend_days", 14))
    except Exception:
        pass

    if gh_token and gh_repo:
        loan_v = settings.get("nomura_loan_man", 0)
        date_v = settings.get("nomura_loan_date", "2026-09-01")
        mode_v = settings.get("nikko_mode", "auto")
        days_v = settings.get("nikko_lend_days", 14)
        msg = f"Save user settings (Nomura Loan: {loan_v}万 on {date_v}, Mode: {mode_v}, Nikko Days: {days_v}d)"
        t_gh = threading.Thread(
            target=_sync_to_github_worker,
            args=(gh_token, gh_repo, json_str, msg, "data/user_settings.json"),
            daemon=True
        )
        t_gh.start()

# ============================================================
# 6. 月別検出 ＆ データローダー (リポジトリ内最新CSV 完全スタンドアロン)
# ============================================================
def get_available_months_info() -> List[Dict[str, Any]]:
    """現在から向こう12ヶ月のリストを生成し、ローカルデータの有無・銘柄数・表示ラベルを付加"""
    today = get_now_jst().date()
    curr_y, curr_m = today.year, today.month
    try:
        from utils.dates import resolve_rights
        resolved_rights, _ = resolve_rights(today)
        curr_y, curr_m = map(int, resolved_rights.split("-"))
    except Exception:
        pass

    info_list = []
    for i in range(12):
        tot_m = curr_m + i
        y = curr_y + (tot_m - 1) // 12
        m = (tot_m - 1) % 12 + 1
        m_str = f"{y}-{m:02d}"

        h_files = sorted([f for f in os.listdir(DATA_DIR) if f.startswith(f"history_{m_str}_") and f.endswith(".csv")]) if DATA_DIR.exists() else []
        m_files = sorted([f for f in os.listdir(DATA_DIR) if f.startswith(f"master_{m_str}_") and f.endswith(".csv")], reverse=True) if DATA_DIR.exists() else []

        has_data = len(h_files) > 0
        tag = "今月" if i == 0 else ("来月" if i == 1 else f"{i}ヶ月先")
        stock_count = 0
        if m_files:
            try:
                with open(DATA_DIR / m_files[0], encoding="utf-8-sig") as fp:
                    stock_count = max(0, sum(1 for _ in fp) - 1)
            except Exception:
                pass

        if has_data:
            label = f"📅 {m_str} ({m}月・{tag}) ➔ ✅ {stock_count}銘柄"
        else:
            label = f"📅 {m_str} ({m}月・{tag}) ➔ ⚠️ 未取得"

        info_list.append({
            "month": m_str,
            "label": label,
            "has_data": has_data,
            "stock_count": stock_count,
            "tag": tag,
        })
    return info_list

@st.cache_data(ttl=30, show_spinner=False)
def load_all_combined_data(target_month: Optional[str] = None) -> Tuple[pd.DataFrame, pd.DataFrame, str]:
    hist_dfs = []
    latest_master = pd.DataFrame()
    data_source_msg = "🔒 セキュア稼働 (GitHub連携)"

    # リポジトリ内の最新CSV (GitHub Actions自動更新データ) を直接高速読込
    if DATA_DIR.exists():
        prefix_h = f"history_{target_month}_" if target_month else "history_"
        prefix_m = f"master_{target_month}_" if target_month else "master_"

        h_files = sorted([DATA_DIR / f for f in os.listdir(DATA_DIR) if f.startswith(prefix_h) and f.endswith(".csv")])
        for hf in h_files:
            try:
                df_tmp = pd.read_csv(hf, encoding="utf-8-sig")
                if not df_tmp.empty: hist_dfs.append(df_tmp)
            except Exception: pass

        m_files = sorted([DATA_DIR / f for f in os.listdir(DATA_DIR) if f.startswith(prefix_m) and f.endswith(".csv")], reverse=True)
        if m_files:
            try: latest_master = pd.read_csv(m_files[0], encoding="utf-8-sig")
            except Exception: pass

    if hist_dfs:
        combined_hist = pd.concat(hist_dfs, ignore_index=True)
        t_col = "取得日時" if "取得日時" in combined_hist.columns else combined_hist.columns[0]
        c_col = "コード" if "コード" in combined_hist.columns else combined_hist.columns[1]
        combined_hist = combined_hist.drop_duplicates(subset=[t_col, c_col], keep="last")
        month_label = f" ({target_month})" if target_month else ""
        return combined_hist, latest_master, f"{data_source_msg}{month_label}"

    return pd.DataFrame(), pd.DataFrame(), f"データなし ({target_month})" if target_month else "データなし"

def normalize_history(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty: return pd.DataFrame()
    d = df.copy()
    col_map = {
        "コード": "code", "銘柄コード": "code", "code": "code",
        "銘柄名": "name", "name": "name", "略称": "name",
        "取得日時": "timestamp", "timestamp": "timestamp", "日時": "timestamp",
        "権利年月": "rights_month", "残日数": "days_left", "残日数(D-N)": "days_left",
        "日興在庫": "nikko", "日興": "nikko", "nikko": "nikko", "Rtn_日興": "rtn_nikko",
        "楽天在庫": "rakuten", "楽天": "rakuten", "rakuten": "rakuten", "Rtn_楽天": "rtn_rakuten",
        "カブ在庫": "kabu", "カブ": "kabu", "kabu": "kabu", "eスマ": "kabu", "eスマ長期": "kabu",
        "SBI在庫": "sbi", "SBI信号": "sbi", "SBI": "sbi", "sbi": "sbi", "Rtn_SBI": "rtn_sbi", "SBI短期": "rtn_sbi",
        "GMO在庫": "gmo", "GMO信号": "gmo", "GMO": "gmo", "gmo": "gmo",
        "松井信号": "matsui", "松井": "matsui", "マネ信号": "monex", "マネックス": "monex",
        "株価": "stock_price", "参考株価(円)": "stock_price", "前日終値": "stock_price",
        "株数": "shares", "株式数": "shares",
        "必要資金": "funds_man", "必要資金(万)": "funds_man", "資金万円": "funds_man", "資金(万)": "funds_man",
        "優待価値": "yutai_value", "優待価値(円)": "yutai_value",
        "優待内容": "yutai_content", "優待": "yutai_content",
        "利回り(%)": "yield_pct", "総合利回り": "yield_pct"
    }
    for orig, standard in col_map.items():
        if orig in d.columns and standard not in d.columns:
            d[standard] = d[orig]

    if "code" in d.columns:
        d["code"] = d["code"].apply(fmt_code)
        d = d[~d["code"].isin(DELISTED_CODES)]

    for col in ["nikko", "rakuten", "kabu"]:
        if col in d.columns:
            d[col] = d[col].apply(parse_qty_safe)
        else:
            d[col] = None

    for col in ["sbi", "rtn_sbi", "gmo", "matsui", "monex"]:
        if col not in d.columns:
            d[col] = None

    if "timestamp" in d.columns:
        d["dt"] = pd.to_datetime(d["timestamp"], errors="coerce")
        d = d.sort_values(by="dt", ascending=True)
        d["timestamp"] = d["dt"].dt.strftime("%Y-%m-%d %H:%M:%S")

    return d

def normalize_master(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty: return pd.DataFrame()
    d = df.copy()
    col_map = {
        "コード": "code", "銘柄名": "name", "優待内容": "yutai_content",
        "優待価値": "yutai_value", "優待価値(円)": "yutai_value",
        "株価": "stock_price", "参考株価(円)": "stock_price", "前日終値": "stock_price",
        "株数": "shares", "株式数": "shares",
        "必要資金": "funds_man", "必要資金(万)": "funds_man", "資金万円": "funds_man",
        "利回り(%)": "yield_pct", "総合利回り": "yield_pct", "売建上限": "gmo_limit",
        "権利年月": "rights_month", "権利確定月": "rights_month", "権利月": "rights_month"
    }
    for orig, standard in col_map.items():
        if orig in d.columns and standard not in d.columns:
            d[standard] = d[orig]

    if "code" in d.columns:
        d["code"] = d["code"].apply(fmt_code)
        d = d[~d["code"].isin(DELISTED_CODES)]
    return d

# ============================================================
# 7. 分析・シグナル算出エンジン
# ============================================================
def analyze_stocks(
    df_hist: pd.DataFrame,
    df_mast: pd.DataFrame,
    watchlist: List[str],
    nikko_th: float = 10000.0,
    annual_rate: float = 0.014,
    nikko_lend_days: Optional[int] = None,
    nomura_rate: float = DEFAULT_NOMURA_RATE,
    has_nomura_loan: bool = False,
    default_rights_month: str = "2026-09",
) -> Tuple[pd.DataFrame, Dict[str, Any], List[str]]:
    if df_hist is None or df_hist.empty:
        return pd.DataFrame(), {}, []

    if "dt" in df_hist.columns:
        valid_dt_df = df_hist.dropna(subset=["dt"]).sort_values(by="dt", ascending=True)
        all_timestamps = valid_dt_df["timestamp"].dropna().unique().tolist()
    else:
        all_timestamps = df_hist["timestamp"].dropna().unique().tolist()
    latest_ts = all_timestamps[-1] if all_timestamps else ""
    prev_ts = all_timestamps[-2] if len(all_timestamps) >= 2 else None

    df_latest = df_hist[df_hist["timestamp"] == latest_ts].copy()
    df_prev = df_hist[df_hist["timestamp"] == prev_ts].copy() if prev_ts else pd.DataFrame()

    prev_map = {r["code"]: r for _, r in df_prev.iterrows()} if not df_prev.empty else {}
    mast_map = {r["code"]: r for _, r in df_mast.iterrows()} if df_mast is not None and not df_mast.empty else {}

    results: List[Dict[str, Any]] = []

    # 日付基準（Daily Snapshot）のスナップショット一覧 [(timestamp, "M/D"), ...] を抽出
    meaningful_snaps = extract_meaningful_snapshots(df_hist)
    snap_ts_list = [ts for ts, _ in meaningful_snaps]
    snap_label_map = {ts: lbl for ts, lbl in meaningful_snaps}

    # 前日（直近の別日）の代表スナップショットを特定（前日比計算用）
    prev_day_ts = None
    if len(meaningful_snaps) >= 2:
        # 最新の直前にある代表スナップショット（前日最終値または本日前回値）
        prev_day_ts = meaningful_snaps[-2][0]
    elif prev_ts:
        prev_day_ts = prev_ts

    df_prev_day = df_hist[df_hist["timestamp"] == prev_day_ts].copy() if prev_day_ts else pd.DataFrame()
    prev_day_map = {r["code"]: r for _, r in df_prev_day.iterrows()} if not df_prev_day.empty else {}

    # 日付ラベル付きの推移マップを事前計算
    trend_map: Dict[str, Dict[str, str]] = {}
    if snap_ts_list and not df_hist.empty:
        df_snaps = df_hist[df_hist["timestamp"].isin(snap_ts_list)].copy()
        for c_grp, g_df in df_snaps.groupby("code"):
            g_sorted = g_df.sort_values(by="dt", ascending=True) if "dt" in g_df.columns else g_df
            g_unique = g_sorted.drop_duplicates(subset=["timestamp"])
            
            clean_str, html_str = build_smart_trend(g_unique, snap_label_map)
            trend_map[str(c_grp)] = {
                "combined": clean_str,
                "html": html_str
            }

    for _, row in df_latest.iterrows():
        code = row.get("code", "")
        if str(code).strip().zfill(4) in DELISTED_CODES:
            continue
        name = row.get("name", "")
        prev_row = prev_map.get(code)
        prev_day_row = prev_day_map.get(code)
        if prev_day_row is None:
            prev_day_row = prev_row
        m_row = mast_map.get(code, {})

        nikko_now = to_float(row.get("nikko"))
        rakuten_now = to_float(row.get("rakuten"))
        kabu_now = to_float(row.get("kabu"))

        sbi_now_raw = str(pick_first_valid(row.get("rtn_sbi"), row.get("sbi"))).strip()
        sbi_now = fmt_signal(sbi_now_raw)

        gmo_now = str(row.get("gmo") or m_row.get("gmo_limit") or "―").strip()

        # 前日（または前回）との比較
        nikko_prev = to_float(prev_day_row.get("nikko")) if prev_day_row is not None else None
        rakuten_prev = to_float(prev_day_row.get("rakuten")) if prev_day_row is not None else None

        sbi_prev_raw = str(pick_first_valid(prev_day_row.get("rtn_sbi"), prev_day_row.get("sbi"))).strip() if prev_day_row is not None else "―"
        sbi_prev = fmt_signal(sbi_prev_raw)

        nikko_diff = (nikko_now - nikko_prev) if (nikko_now is not None and nikko_prev is not None) else None

        # --- SBI 急変・悪化検知 ---
        is_sbi_sudden_drop = False
        sbi_alert_tag = ""
        if sbi_prev != "―" and sbi_now != "―":
            if sbi_prev == "◎" and sbi_now == "▲":
                sbi_change = "🚨急変(◎→▲)"
                sbi_alert_tag = "🚨◎→▲"
                is_sbi_sudden_drop = True
            elif sbi_prev == "◎" and sbi_now == "×":
                sbi_change = "💥瞬殺(◎→×)"
                sbi_alert_tag = "💥◎→×"
                is_sbi_sudden_drop = True
            elif sbi_prev == "▲" and sbi_now == "×":
                sbi_change = "💥枯渇(▲→×)"
                sbi_alert_tag = "💥▲→×"
                is_sbi_sudden_drop = True
            elif sbi_prev != sbi_now:
                sbi_change = f"{sbi_prev}→{sbi_now}"
                sbi_alert_tag = f"{sbi_prev}→{sbi_now}"
            else:
                sbi_change = f"{sbi_now}(維持)"
        else:
            sbi_change = sbi_now if sbi_now != "―" else "―"

        # SBI 表示用（最新 + 変化が一目瞭然）
        if sbi_alert_tag:
            sbi_display = f"{sbi_now} ({sbi_alert_tag})"
        else:
            sbi_display = sbi_now

        # --- 日興 急減検知 ---
        is_nikko_drop = False
        if nikko_diff is not None and nikko_diff < 0:
            if nikko_diff <= -3000:
                is_nikko_drop = True
                nikko_display = f"{fmt_qty(nikko_now)} (🚨▼{abs(int(nikko_diff)):,})"
            else:
                nikko_display = f"{fmt_qty(nikko_now)} (▼{abs(int(nikko_diff)):,})"
        elif nikko_diff is not None and nikko_diff > 0:
            nikko_display = f"{fmt_qty(nikko_now)} (+{int(nikko_diff):,})"
        else:
            nikko_display = fmt_qty(nikko_now)

        is_refill = False
        if prev_ts:
            was_zero = (nikko_prev is not None and nikko_prev == 0) or (rakuten_prev is not None and rakuten_prev == 0)
            now_has = (nikko_now is not None and nikko_now > 0) or (rakuten_now is not None and rakuten_now > 0)
            if was_zero and now_has:
                is_refill = True

        valid_qtys = [q for q in [nikko_now, rakuten_now, kabu_now] if q is not None]
        total_qty = sum(valid_qtys) if valid_qtys else None

        if is_sbi_sudden_drop and (nikko_now is not None and nikko_now <= nikko_th):
            signal = "🔴 今夜確保"
            signal_rank = 1
        elif total_qty is not None and total_qty == 0 and sbi_now in ("×", "―"):
            signal = "⚪ 枯渇"
            signal_rank = 5
        elif total_qty is not None and 0 < total_qty < 1000:
            signal = "🔴 即確保"
            signal_rank = 2
        elif (nikko_now is not None and nikko_now < nikko_th) or is_nikko_drop:
            signal = "🟡 要監視"
            signal_rank = 3
        elif nikko_now is not None and nikko_now >= nikko_th:
            signal = "🟢 待機可"
            signal_rank = 4
        else:
            signal = "⚪ 枯渇" if (total_qty == 0) else "🟡 要監視"
            signal_rank = 3

        yutai_val = to_float(m_row.get("yutai_value") or row.get("yutai_value"))
        funds_man = to_float(m_row.get("funds_man") or row.get("funds_man"))
        stock_price = to_float(row.get("stock_price") or m_row.get("stock_price"))
        y_content_str = str(m_row.get("yutai_content") or row.get("yutai_content") or "")
        req_shares = extract_shares(row, m_row, y_content_str)

        # 株価がない、または0の場合はキャッシュ/株探から自動補完
        if (stock_price is None or stock_price <= 0) and code:
            stock_price = get_stock_price(code)

        # 最低取得価格（funds_man）が空または0の場合、株価×必要株数で自動算出補完
        if (funds_man is None or funds_man <= 0):
            if stock_price is not None and stock_price > 0 and req_shares > 0:
                funds_man = round(stock_price * req_shares / 10000.0, 2)

        funds_yen = int(round(funds_man * 10000)) if (funds_man is not None and funds_man > 0) else 99999999

        if (stock_price is None or stock_price <= 0) and funds_man is not None and req_shares > 0:
            stock_price = round(funds_man * 10000.0 / req_shares)

        days_left_raw = str(row.get("days_left") or "10").replace("D-", "")
        try: d_n = int(days_left_raw)
        except ValueError: d_n = 10

        # 権利月と想定貸株日数の算出 (自動モード時は東証祝日カレンダー・現在日時から完全自動算出)
        rights_val = row.get("rights_month") or m_row.get("rights_month") or default_rights_month
        if nikko_lend_days is not None and nikko_lend_days > 0:
            item_lend_days = int(nikko_lend_days)
            is_auto_days = False
        else:
            item_lend_days, _, _, _ = calc_stock_lend_days(rights_val, default_rights_month=default_rights_month)
            is_auto_days = True

        net_profit = None
        limit_days_int = None
        nikko_cost = 0
        nikko_cost_str = "―"
        net_profit_nikko = None
        net_profit_nikko_str = "―"
        nomura_item_daily_interest = 0

        is_expired = (item_lend_days == 0 and is_auto_days)
        saving_1d = 0
        saving_2d = 0
        saving_str = "―"
        wait_days = None
        wait_label = "―"

        if is_expired:
            signal = "⚪ 権利落済"
            signal_rank = 6
            nikko_cost = 0
            nikko_cost_str = "権利落済"
            net_profit_nikko = None
            net_profit_nikko_str = "―"
            saving_str = "権利落済"
            wait_label = "🏁権利落"
        elif funds_yen < 99999990 and funds_yen > 0:
            nikko_cost = calc_nikko_cost(funds_yen, lend_days=item_lend_days)
            nikko_cost_str = f"¥{nikko_cost:,}"
            effective_yutai_val = yutai_val
            c_norm = fmt_code(code)
            is_estimated_val = False
            if (effective_yutai_val is None or effective_yutai_val <= 0) and c_norm in KNOWN_YUTAI_VALUES:
                effective_yutai_val = KNOWN_YUTAI_VALUES[c_norm]
                is_estimated_val = True

            if effective_yutai_val is not None and effective_yutai_val > 0:
                net_profit_nikko = int(round(effective_yutai_val - nikko_cost))
                if is_estimated_val:
                    net_profit_nikko_str = f"約¥{net_profit_nikko:,} (概算)"
                else:
                    net_profit_nikko_str = f"¥{net_profit_nikko:,}"
                net_profit = net_profit_nikko
            else:
                if "割引" in y_content_str:
                    net_profit_nikko_str = "🎟️ 割引優待"
                    wait_label = "割引優待"
                elif any(k in y_content_str for k in ["自社", "商品", "品", "カタログ"]):
                    net_profit_nikko_str = "🎁 自社品優待"
                    wait_label = "自社品優待"
                elif "カレンダ" in y_content_str:
                    net_profit_nikko_str = "📅 カレンダー"
                    wait_label = "カレンダー"
                else:
                    net_profit_nikko_str = "定性優待"
                    wait_label = "定性優待"

            nomura_item_daily_interest = int(round(funds_yen * nomura_rate / 365.0)) if has_nomura_loan else 0
            if d_n:
                try:
                    daily_cost = funds_yen * annual_rate / 365.0
                    if daily_cost > 0 and effective_yutai_val is not None:
                        limit_days_int = int(round(effective_yutai_val / daily_cost))
                except Exception: pass

            # 待機節約額（あと1日・2日待機した場合に削減できる日興貸株料）
            saving_1d = int(round(funds_yen * DEFAULT_NIKKO_LEND_RATE / 365.0))
            saving_2d = saving_1d * 2
            if saving_1d > 0:
                saving_str = f"1日:-¥{saving_1d:,} (2日:-¥{saving_2d:,})"

            # 損益分岐待機日数（優待価値から現行コストを引いた余力日数）
            if effective_yutai_val is not None and effective_yutai_val > 0:
                wait_days = calc_breakeven_wait_days(
                    yutai_val=effective_yutai_val,
                    funds_yen=funds_yen,
                    current_nikko_cost=nikko_cost,
                    nomura_daily_cost=nomura_item_daily_interest
                )
                if wait_days is not None:
                    if wait_days > 30:
                        wait_label = f"🟢黒字(余裕{wait_days}日)"
                    elif wait_days > 0:
                        wait_label = f"🟢黒字(余力{wait_days}日)"
                    elif wait_days == 0:
                        wait_label = "⚠️損益±0"
                    else:
                        wait_label = f"🚨赤字(あと{abs(wait_days)}日待機)"

        is_watch = (code in watchlist)
        c_trend = trend_map.get(str(code), {})

        results.append({
            "watch": is_watch,
            "watch_rank": 0 if is_watch else 1,  # 監視中フラグ
            "code": code,
            "name": name,
            "stock_price": stock_price,
            "funds_yen": funds_yen,
            "funds_man_str": fmt_funds_man(funds_yen),
            "saving_1d": saving_1d,
            "saving_2d": saving_2d,
            "saving_str": saving_str,
            "signal": signal,
            "signal_rank": signal_rank,
            "sbi_change": sbi_change,
            "sbi_display": sbi_display,
            "is_sbi_drop": is_sbi_sudden_drop,
            "is_nikko_drop": is_nikko_drop,
            "nikko_display": nikko_display,
            "refill": "🔥補充" if is_refill else "",
            "is_refill": is_refill,
            "nikko_now": nikko_now,
            "nikko_diff": nikko_diff,
            "rakuten_now": rakuten_now,
            "kabu_now": kabu_now,
            "sbi_now": sbi_now,
            "gmo_now": gmo_now,
            "other_brokers": fmt_other_brokers(kabu_now, rakuten_now, gmo_now),
            "trend_combined": c_trend.get("combined", "―"),
            "trend_html": c_trend.get("html", "―"),
            "trend_nikko": c_trend.get("nikko", "―"),
            "trend_sbi": c_trend.get("sbi", "―"),
            "total_qty": total_qty,
            "funds_man": funds_man,
            "yutai_value": effective_yutai_val,
            "yutai_content_raw": str(m_row.get("yutai_content") or row.get("yutai_content") or ""),
            "yutai_content": fmt_yutai_enhanced(
                str(m_row.get("yutai_content") or row.get("yutai_content") or ""),
                yutai_val=effective_yutai_val,
                code=code
            ),
            "rights_month": str(rights_val),
            "lend_days": item_lend_days,
            "is_auto_days": is_auto_days,
            "nikko_cost": nikko_cost,
            "nikko_cost_str": nikko_cost_str,
            "net_profit_nikko": net_profit_nikko,
            "net_profit_nikko_str": net_profit_nikko_str,
            "nomura_item_daily_interest": nomura_item_daily_interest,
            "wait_days": wait_days,
            "wait_label": wait_label,
            "yield_pct": (
                to_float(m_row.get("yield_pct") or row.get("yield_pct")) or 
                (round((effective_yutai_val / (funds_man * 10000.0)) * 100, 2) if (effective_yutai_val and funds_man and funds_man > 0) else None)
            ),
            "net_profit": net_profit,
            "limit_days_int": limit_days_int,
            "days_left": d_n,
        })

    df_res = pd.DataFrame(results)
    stats = {
        "latest_ts": latest_ts,
        "prev_ts": prev_ts,
        "total_count": len(df_res),
        "tonight_count": sum(1 for r in results if r["signal"] == "🔴 今夜確保"),
        "sbi_drop_count": sum(1 for r in results if r["is_sbi_drop"]),
        "refill_count": sum(1 for r in results if r["is_refill"]),
        "watch_count": sum(1 for r in results if r["watch"]),
        "empty_count": sum(1 for r in results if r["signal"] == "⚪ 枯渇"),
    }
    return df_res, stats, all_timestamps

# ============================================================
# 8. メインUI
# ============================================================
def main():
    # --- 🔒 プライベート・シークレット認証 ---
    # ユーザー専用キー（URLパラメータ ?key=... または手動入力で認証）
    url_key = st.query_params.get("key", "")
    is_authenticated = st.session_state.get("authenticated", False) or (url_key == APP_SECRET_KEY)

    if not is_authenticated:
        # 未認証時はロック画面のみ表示（データ・設定・サイドバーは一切レンダリングしない）
        st.markdown(
            """
            <div style="text-align:center; padding:3.5rem 1rem 1.5rem 1rem; max-width:460px; margin:auto;">
                <div style="font-size:42px; margin-bottom:0.8rem;">🔒</div>
                <h3 style="color:#f1f5f9; margin-bottom:0.4rem; font-weight:700;">プライベート・ダッシュボード</h3>
                <p style="color:#94a3b8; font-size:12.5px; line-height:1.6; margin-bottom:1.2rem;">
                    この優待クロス在庫トラッカーは非公開の個人専用環境です。<br>
                    アクセス用の合言葉（キー）を入力してください。
                </p>
            </div>
            """,
            unsafe_allow_html=True
        )
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            input_key = st.text_input("合言葉（パスコード）", type="password", placeholder="合言葉を入力", label_visibility="collapsed")
            if st.button("🔓 認証して開く", use_container_width=True, type="primary"):
                if input_key == APP_SECRET_KEY:
                    st.session_state["authenticated"] = True
                    st.query_params["key"] = input_key
                    st.toast("✅ 認証に成功しました！")
                    st.rerun()
                else:
                    st.error("合言葉が正しくありません。")
            st.caption("💡 一度開いた後のURL（?key=... 付き）をブックマーク／スマホのホーム画面に登録すると、次回以降ログイン不要でワンタップ起動できます。")
        return

    # 認証済みの場合、URLパラメータにキーを維持（ブックマーク・リロード時の利便性向上）
    if "key" not in st.query_params or st.query_params.get("key") != APP_SECRET_KEY:
        st.query_params["key"] = APP_SECRET_KEY
    st.session_state["authenticated"] = True

    gh_token = get_github_token()
    gh_repo = safe_get_secret("GITHUB_REPO", "tekkame/yutai-cross-dashboard")

    # 権利月の自動検出と選択肢リスト生成
    available_months_info = get_available_months_info()
    month_options = [m["month"] for m in available_months_info]
    month_labels = {m["month"]: m["label"] for m in available_months_info}
    default_month = month_options[0] if month_options else "2026-09"

    # 権利月選択の単一信頼源（Single Source of Truth）
    url_month = st.query_params.get("month", "")
    if "selected_month" not in st.session_state:
        chosen_month = url_month if url_month in month_options else default_month
        st.session_state["selected_month"] = chosen_month
    else:
        if url_month in month_options and url_month != st.session_state.get("_last_synced_month"):
            st.session_state["selected_month"] = url_month
        chosen_month = st.session_state["selected_month"]

    st.session_state["_last_synced_month"] = chosen_month
    st.query_params["month"] = chosen_month

    # ユーザー設定（野村担保ローン借入額・起算日・日興貸株日数）の読み込み（URLパラメータ + GitHub + ローカル多層復元）
    if "user_settings" not in st.session_state:
        st.session_state["user_settings"] = load_user_settings(gh_token=gh_token, gh_repo=gh_repo)
    current_settings = st.session_state["user_settings"]

    with st.sidebar:
        st.markdown("### 📅 権利月の選択")
        sb_selected = st.selectbox(
            "表示・分析する権利月",
            options=month_options,
            index=month_options.index(chosen_month) if chosen_month in month_options else 0,
            format_func=lambda m: month_labels.get(m, m),
            key=f"sb_month_select_{chosen_month}",
            help="当月・翌月・各月の優待クロス銘柄・在庫状況を切り替えます。"
        )
        if sb_selected != chosen_month:
            st.session_state["selected_month"] = sb_selected
            st.query_params["month"] = sb_selected
            st.rerun()

        st.markdown("---")
        st.markdown("### 🏦 野村證券 担保ローン設定")
        nomura_loan_val = float(current_settings.get("nomura_loan_man", 0.0))
        loan_in = st.number_input(
            "借入金額 (万円)",
            min_value=0.0,
            max_value=50000.0,
            value=nomura_loan_val,
            step=10.0,
            help="野村證券Web担保ローンの借入金額を入力。自動記憶されリロード後も保持されます。"
        )

        stored_loan_date_str = str(current_settings.get("nomura_loan_date", "2026-09-01"))
        try:
            stored_loan_date = dt.datetime.strptime(stored_loan_date_str, "%Y-%m-%d").date()
        except Exception:
            stored_loan_date = dt.date(2026, 9, 1)

        loan_date_in = st.date_input(
            "借入日 (利息起算日)",
            value=stored_loan_date,
            help="野村Webローンで実際に借入を行った（または予定している）日付。利息日数の起算日となります。"
        )
        loan_date_str = loan_date_in.strftime("%Y-%m-%d")

        nomura_rate_val = float(current_settings.get("nomura_rate", DEFAULT_NOMURA_RATE))
        rate_percent_in = st.number_input(
            "担保ローン金利 (%)",
            min_value=0.1,
            max_value=15.0,
            value=float(round(nomura_rate_val * 100.0, 2)),
            step=0.1,
            format="%.2f",
            help="現在の野村證券担保ローン金利 (年利2.40%)"
        )
        rate_val = rate_percent_in / 100.0

        # 設定変更時の自動記憶（URL・GitHub・ローカルの3重同期）
        if (loan_in != nomura_loan_val) or (loan_date_str != stored_loan_date_str) or (abs(rate_val - nomura_rate_val) > 1e-5):
            current_settings["nomura_loan_man"] = loan_in
            current_settings["nomura_loan_date"] = loan_date_str
            current_settings["nomura_rate"] = rate_val
            st.session_state["user_settings"] = current_settings
            save_user_settings(current_settings, gh_token, gh_repo)
            st.toast("💾 借入設定（金額・起算日）を記憶しました")

        nomura_daily = calc_nomura_daily_interest(loan_in, rate=rate_val)
        nomura_monthly = int(round(nomura_daily * 30.0))

        # 経過日数と累計利息の計算 (本日まで / 現渡完了まで - JST基準でUTCズレ防止)
        today_d = get_now_jst().date()
        elapsed_days = max(1, (today_d - loan_date_in).days + 1)
        nomura_accrued = nomura_daily * elapsed_days

        # 選択中の権利月（chosen_month）の現渡受渡日までの総日数・総見込利息を自動算出
        auto_days_month, exec_d_cur, op_s_cur, cl_s_cur = calc_stock_lend_days(chosen_month)
        total_loan_days = max(elapsed_days, (cl_s_cur - loan_date_in).days + 1)
        nomura_expected_total = nomura_daily * total_loan_days

        st.markdown(
            f'<div style="background:#0f172a; border:1px solid #3b82f6; border-radius:6px; padding:0.5rem 0.65rem; margin-bottom:0.6rem;">'
            f'<div style="color:#93c5fd; font-size:11px; font-weight:600;">💡 野村利息シミュレーション ({chosen_month}基準)</div>'
            f'<div style="color:#ffffff; font-size:16px; font-weight:bold; font-family:\'JetBrains Mono\', monospace; margin:2px 0;">¥{nomura_daily:,} <span style="font-size:11px; font-weight:normal; color:#94a3b8;">/日</span></div>'
            f'<div style="color:#cbd5e1; font-size:11px; margin-top:3px;">📅 借入日({loan_date_in.strftime("%m/%d")})〜本日: <b style="color:#38bdf8;">{elapsed_days}日間</b> ➔ <b style="color:#fde68a;">¥{nomura_accrued:,}</b></div>'
            f'<div style="color:#94a3b8; font-size:10.5px; margin-top:2px;">🏁 現渡受渡({cl_s_cur.strftime("%m/%d")})まで: <b>{total_loan_days}日間</b> ➔ <b style="color:#c084fc;">¥{nomura_expected_total:,}</b></div>'
            f'<div style="color:#6ee7b7; font-size:10px; margin-top:3px;">💾 借入条件はクラウド・ローカルに記憶済</div>'
            f'</div>',
            unsafe_allow_html=True
        )

        st.markdown("### ⏱️ 日興優待クロス設定")
        nikko_mode_cur = current_settings.get("nikko_mode", "auto")
        mode_options = ["🤖 銘柄・日時から自動設定 (推奨)", "✏️ 手動で一括指定"]
        mode_idx = 0 if nikko_mode_cur == "auto" else 1
        selected_mode_label = st.radio(
            "貸株日数の算出方式",
            mode_options,
            index=mode_idx,
            horizontal=False,
            help="自動設定: 銘柄の権利月（月末/20日等）と現在日時（平日15:30前後・祝日）から東証休業日カレンダー（2024〜2032年）に基づき日数を完全自動算出します。"
        )
        new_mode = "auto" if "自動" in selected_mode_label else "manual"
        if new_mode != nikko_mode_cur:
            current_settings["nikko_mode"] = new_mode
            st.session_state["user_settings"] = current_settings
            save_user_settings(current_settings, gh_token, gh_repo)

        current_days_val = int(current_settings.get("nikko_lend_days", 14))

        if new_mode == "auto":
            effective_lend_days = None  # None で analyze_stocks に銘柄ごと自動計算させる
            st.markdown(
                f'<div style="background:#0f172a; border:1px solid #10b981; border-radius:6px; padding:0.45rem 0.65rem; margin-bottom:0.5rem;">'
                f'<div style="color:#6ee7b7; font-size:11px; font-weight:600;">🤖 祝日・約定日時 完全自動連動中</div>'
                f'<div style="color:#ffffff; font-size:13px; margin:2px 0;">約定予定日: <b style="color:#38bdf8;">{exec_d_cur.strftime("%m/%d")}</b> (受渡: {op_s_cur.strftime("%m/%d")})</div>'
                f'<div style="color:#cbd5e1; font-size:11px;">{chosen_month}代表: <b style="color:#34d399; font-size:14px;">{auto_days_month}日分</b> (現渡受渡: {cl_s_cur.strftime("%m/%d")})</div>'
                f'<div style="color:#94a3b8; font-size:10px; margin-top:2px;">※20日権利銘柄や月末権利日も個別自動判定</div>'
                f'</div>',
                unsafe_allow_html=True
            )
            st.caption(f"料率: 制度買金利 {DEFAULT_NIKKO_BUY_RATE*100:.2f}% (1日分) + 貸株料 {DEFAULT_NIKKO_LEND_RATE*100:.1f}% × 各銘柄の受渡日数 (手数料無料)")
        else:
            lend_days_in = st.number_input(
                "一括 想定貸株日数 (日)",
                min_value=1,
                max_value=90,
                value=current_days_val,
                step=1,
                help="手動ですべての銘柄に同一の貸株日数を適用します。"
            )
            if lend_days_in != current_days_val:
                current_settings["nikko_lend_days"] = lend_days_in
                st.session_state["user_settings"] = current_settings
                save_user_settings(current_settings, gh_token, gh_repo)
            effective_lend_days = lend_days_in
            st.caption(f"料率: 制度買金利 {DEFAULT_NIKKO_BUY_RATE*100:.2f}% (1日分) + 貸株料 {DEFAULT_NIKKO_LEND_RATE*100:.1f}% × {lend_days_in}日分 (ダイレクトコース手数料無料)")

        st.markdown("---")
        st.markdown("### ⚙️ アプリ設定")
        nikko_th = st.number_input("日興 警戒閾値 (株)", value=10000, step=1000)
        annual_rate = st.number_input("貸株年率 (他社比較用)", value=0.014, step=0.001, format="%.3f")

        st.markdown("##### 💾 永続化ステータス")
        if gh_token:
            st.success("✅ GitHub Token 連携中（クラウド自動保存OK）")
        else:
            st.info("ℹ️ ローカル保存モード")

        c_sync1, c_sync2 = st.columns(2)
        with c_sync1:
            if st.button("📥 監視再読込", use_container_width=True):
                st.session_state["watchlist"] = reload_watchlist_fresh()
                st.session_state["editor_version"] = st.session_state.get("editor_version", 0) + 1
                st.toast("監視リストをGitHub＆ローカルから最新再読込しました")
                st.rerun()
        with c_sync2:
            if st.button("🚀 最新取得", use_container_width=True, type="primary"):
                with st.spinner(f"{chosen_month} の最新データを取得中..."):
                    ok, msg = run_direct_scrape(rights_arg=chosen_month)
                    if ok:
                        sync_scraped_data_to_github(chosen_month, gh_token, gh_repo)
                        st.toast("✅ 最新取得＆クラウド同期完了！")
                        st.rerun()
                    else:
                        st.error(msg)

        st.caption(f"App Version: {APP_VERSION}")

    raw_hist, raw_mast, data_source_msg = load_all_combined_data(target_month=chosen_month)
    if raw_hist is None or raw_hist.empty:
        st.markdown(
            f'<div style="background:#1e293b; border:2px dashed #f59e0b; border-radius:8px; padding:1.5rem; text-align:center; margin:2rem 0;">'
            f'<div style="font-size:22px; font-weight:bold; color:#fde68a; margin-bottom:0.5rem;">📅 {chosen_month} の在庫データはまだ取得されていません</div>'
            f'<div style="color:#cbd5e1; font-size:13px; margin-bottom:1.2rem;">下のボタンを押すと、相手サーバーに配慮した安全な直接スクレイピングを実行し、即座に画面へ反映します。</div>'
            f'</div>',
            unsafe_allow_html=True
        )
        c_btn1, c_btn2, c_btn3 = st.columns([1, 2, 1])
        with c_btn2:
            if st.button(f"🚀 {chosen_month} のデータを今すぐ取得する", use_container_width=True, type="primary"):
                with st.spinner(f"{chosen_month} の優待データをスクレイピング取得中..."):
                    ok, msg = run_direct_scrape(rights_arg=chosen_month)
                    if ok:
                        sync_scraped_data_to_github(chosen_month, gh_token, gh_repo)
                        st.toast(f"✅ {chosen_month} のデータ取得＆クラウド同期完了！")
                        st.rerun()
                    else:
                        st.error(msg)
        return

    df_hist = normalize_history(raw_hist)
    df_mast = normalize_master(raw_mast)

    # 監視リストのロード（ローカル + GitHub API + URLクエリパラメータの多層フェイルオーバー）
    if "watchlist" not in st.session_state:
        st.session_state["watchlist"] = load_initial_watchlist(df_mast=df_mast)

    # URLクエリパラメータに現在リストを常時保持（ブラウザの開き直し・リロード対策）
    current_watch_str = ",".join(st.session_state["watchlist"]) if st.session_state["watchlist"] else "none"
    if st.query_params.get("watch") != current_watch_str:
        try:
            st.query_params["watch"] = current_watch_str
        except Exception:
            pass

    # ブラウザ localStorage 連携スクリプト（素のURLで開き直した際の自動リカバリ＆リアルタイム同期）
    try:
        watch_json_for_js = json.dumps(st.session_state["watchlist"], ensure_ascii=False)
        sync_js = f"""
        <script>
        (function() {{
            try {{
                const KEY = "yutai_watchlist_v13";
                const currentList = {watch_json_for_js};
                
                // 古いキャッシュキーを確実に消去
                try {{ window.parent.localStorage.removeItem("yutai_watchlist_storage"); }} catch(e) {{}}
                try {{ localStorage.removeItem("yutai_watchlist_storage"); }} catch(e) {{}}

                // 1. 現在の有効な監視リストをブラウザの localStorage に永続保存
                if (currentList && currentList.length > 0) {{
                    try {{ window.parent.localStorage.setItem(KEY, JSON.stringify(currentList)); }} catch(e) {{}}
                    try {{ localStorage.setItem(KEY, JSON.stringify(currentList)); }} catch(e) {{}}
                }}

                // 2. URL の watch パラメータをリロードなしで静かに同期
                try {{
                    const pUrl = new URL(window.parent.location.href);
                    const curParam = pUrl.searchParams.get("watch");
                    const targetWatch = (currentList && currentList.length > 0) ? currentList.join(",") : "none";
                    
                    // 初回アクセス時（watchパラメータ未設定でlocalStorageに前データがある場合）のみ自動リカバリ
                    if (!pUrl.searchParams.has("watch")) {{
                        let saved = null;
                        try {{ saved = window.parent.localStorage.getItem(KEY); }} catch(e) {{}}
                        if (!saved) {{
                            try {{ saved = localStorage.getItem(KEY); }} catch(e) {{}}
                        }}
                        if (saved) {{
                            const arr = JSON.parse(saved);
                            if (Array.isArray(arr) && arr.length > 0) {{
                                pUrl.searchParams.set("watch_v", "v13");
                                pUrl.searchParams.set("watch", arr.join(","));
                                window.parent.location.replace(pUrl.toString());
                                return;
                            }}
                        }}
                    }}
                    
                    // 通常時は画面リロードを起こさず、history.replaceState でアドレスバーだけ静かに更新
                    if (curParam !== targetWatch) {{
                        pUrl.searchParams.set("watch_v", "v13");
                        pUrl.searchParams.set("watch", targetWatch);
                        window.parent.history.replaceState({{}}, "", pUrl.toString());
                    }}
                }} catch(e) {{}}
            }} catch(err) {{}}
        }})();
        </script>
        """
        st.components.v1.html(sync_js, height=0, width=0)
    except Exception:
        pass

    df_analyzed, stats, all_timestamps = analyze_stocks(
        df_hist, df_mast,
        watchlist=st.session_state["watchlist"],
        nikko_th=nikko_th,
        annual_rate=annual_rate,
        nikko_lend_days=effective_lend_days,
        nomura_rate=rate_val,
        has_nomura_loan=(loan_in is not None and loan_in > 0),
        default_rights_month=chosen_month
    )

    # サイドバーに監視銘柄のクイック管理（直接コード追加・一覧確認・個別解除）を追加
    with st.sidebar:
        st.markdown("---")
        st.markdown("##### ⭐ 監視銘柄の管理")

        # 全CSVマスタからコード->銘柄名マップを生成（他月銘柄でも名前を確実に表示）
        global_name_map: Dict[str, str] = {}
        if not df_analyzed.empty:
            for _, r in df_analyzed.iterrows():
                global_name_map[str(r["code"])] = str(r["name"])
        if DATA_DIR.exists():
            for mf in sorted(DATA_DIR.glob("master_*.csv")):
                try:
                    m_df = pd.read_csv(mf, usecols=["コード", "銘柄名"], encoding="utf-8-sig")
                    for _, r in m_df.iterrows():
                        c_std = fmt_code(r["コード"])
                        if c_std not in global_name_map:
                            global_name_map[c_std] = str(r["銘柄名"])
                except Exception:
                    pass

        cur_codes_set = set(df_analyzed["code"].tolist()) if not df_analyzed.empty else set()
        cur_month_watched = [c for c in st.session_state["watchlist"] if c in cur_codes_set]
        other_month_watched = [c for c in st.session_state["watchlist"] if c not in cur_codes_set]

        st.caption(f"{chosen_month}対象: **{len(cur_month_watched)}** 銘柄 (全月合計: {len(st.session_state['watchlist'])} 銘柄)")
        
        c_add1, c_add2 = st.columns([3, 2])
        with c_add1:
            new_code_in = st.text_input("コード追加", placeholder="例: 9831", label_visibility="collapsed", key="sidebar_add_code")
        with c_add2:
            if st.button("➕ 追加", use_container_width=True, key="sidebar_btn_add"):
                c_clean = fmt_code(new_code_in.strip())
                if c_clean and c_clean not in st.session_state["watchlist"]:
                    st.session_state["watchlist"].append(c_clean)
                    st.session_state["editor_version"] = st.session_state.get("editor_version", 0) + 1
                    persist_watchlist(st.session_state["watchlist"], gh_token, gh_repo, trigger_code=c_clean)
                    st.toast(f"✅ {c_clean} を監視リストに追加しました")
                    st.rerun()
                elif c_clean in st.session_state["watchlist"]:
                    st.toast("既に監視リストに登録されています")

        if st.session_state["watchlist"]:
            with st.expander(f"登録中銘柄の一覧・解除 ({len(st.session_state['watchlist'])}件)", expanded=False):
                if cur_month_watched:
                    st.markdown(f"**【{chosen_month} 対象銘柄】**")
                    for wc in cur_month_watched:
                        w_name = global_name_map.get(wc, "")
                        c_row1, c_row2 = st.columns([4, 1])
                        with c_row1:
                            st.markdown(f"⭐ **{wc}** {w_name}")
                        with c_row2:
                            if st.button("❌", key=f"del_w_{wc}", help=f"{wc} を監視から解除"):
                                st.session_state["watchlist"].remove(wc)
                                st.session_state["editor_version"] = st.session_state.get("editor_version", 0) + 1
                                persist_watchlist(st.session_state["watchlist"], gh_token, gh_repo, trigger_code=wc)
                                st.toast(f"🗑️ {wc} を解除しました")
                                st.rerun()

                if other_month_watched:
                    st.markdown(f"<div style='font-size:11px; color:#94a3b8; margin-top:0.4rem;'><b>【他月で登録済みの銘柄】</b> (年2回優待等は該当月に自動反映)</div>", unsafe_allow_html=True)
                    for wc in other_month_watched:
                        w_name = global_name_map.get(wc, "")
                        c_row1, c_row2 = st.columns([4, 1])
                        with c_row1:
                            st.markdown(f"<span style='color:#94a3b8;'>○ <b>{wc}</b> {w_name}</span>", unsafe_allow_html=True)
                        with c_row2:
                            if st.button("❌", key=f"del_w_other_{wc}", help=f"{wc} を監視から解除"):
                                st.session_state["watchlist"].remove(wc)
                                st.session_state["editor_version"] = st.session_state.get("editor_version", 0) + 1
                                persist_watchlist(st.session_state["watchlist"], gh_token, gh_repo, trigger_code=wc)
                                st.toast(f"🗑️ {wc} を解除しました")
                                st.rerun()

        # サーバー側マスター（13銘柄）に同期するボタン
        if st.button("🔄 サーバー最新（13銘柄）に同期", use_container_width=True, key="sidebar_btn_sync_server", help="ブラウザキャッシュを破棄し、サーバー/GitHub上の最新リストに強制同期します"):
            fresh_list = reload_watchlist_fresh()
            st.session_state["watchlist"] = fresh_list
            st.session_state["editor_version"] = st.session_state.get("editor_version", 0) + 1
            persist_watchlist(st.session_state["watchlist"], gh_token, gh_repo, trigger_code="server_sync")
            st.toast(f"✅ サーバー最新リスト ({len(fresh_list)}銘柄) に同期しました！")
            st.rerun()

        # 監視リスト一括コピー・復元 (バックアップ・別端末移行用)
        with st.expander("📋 監視リスト一括コピー / 復元", expanded=False):
            st.caption("登録中の銘柄コードをまとめてコピー、または貼り付けて一括反映できます。")
            cur_csv_str = ", ".join(st.session_state["watchlist"])
            bulk_input = st.text_area("銘柄コード（カンマまたは改行区切り）", value=cur_csv_str, height=70, key="sidebar_bulk_watchlist")
            if st.button("💾 まとめて反映", use_container_width=True, key="sidebar_btn_bulk_save"):
                raw_codes = re.findall(r"\d{4}", bulk_input)
                new_clean = sorted(list(set(fmt_code(c) for c in raw_codes if c)))
                st.session_state["watchlist"] = new_clean
                st.session_state["editor_version"] = st.session_state.get("editor_version", 0) + 1
                persist_watchlist(st.session_state["watchlist"], gh_token, gh_repo, trigger_code="bulk")
                st.toast(f"✅ {len(new_clean)} 銘柄を一括保存しました！")
                st.rerun()

    # ステータスバー (インデントなしで安全に描画)
    nikko_status_label = f"銘柄別自動 ({auto_days_month}日等)" if new_mode == "auto" else f"{effective_lend_days}日分"
    nomura_status_str = f"¥{nomura_daily:,}/日 (累計:¥{nomura_accrued:,})" if loan_in > 0 else "借入なし"
    status_bar_html = (
        f'<div class="status-bar">'
        f'<div class="status-bar-title">⚡ <b>優待クロス在庫トラッカー</b> <span style="font-size:11px;font-weight:normal;color:#94a3b8;">({APP_VERSION})</span></div>'
        f'<div class="status-tags">'
        f'<span class="tag tag-amber" style="font-weight:bold; font-size:12px; background:#451a03; border:1px solid #f59e0b; color:#fde68a;">📅 権利月: {chosen_month}</span>'
        f'<span class="tag tag-green">{data_source_msg}</span>'
        f'<span class="tag tag-blue">最新取得: {stats.get("latest_ts", "―")}</span>'
        f'<span class="tag tag-amber">⭐ 監視中: {stats.get("watch_count", 0)}銘柄</span>'
        f'<span class="tag tag-purple">🏦 野村利息: {nomura_status_str}</span>'
        f'<span class="tag tag-gray">⏱️ 日興基準: {nikko_status_label}</span>'
        f'</div>'
        f'</div>'
    )
    st.markdown(status_bar_html, unsafe_allow_html=True)

    # ----------------------------------------------------
    # ★ 監視・目標銘柄ハイライト・パネル (⭐ピン留め一覧)
    # ----------------------------------------------------
    watch_df = df_analyzed[df_analyzed["watch"] == True].copy()

    if not watch_df.empty:
        total_funds = watch_df[watch_df["funds_yen"] < 99999990]["funds_yen"].sum()
        total_nikko_cost = int(watch_df["nikko_cost"].sum())
        total_yutai_val = int(sum(to_float(r.get("yutai_value")) or 0 for _, r in watch_df.iterrows()))
        valid_profits = watch_df["net_profit_nikko"].dropna()
        total_profit = valid_profits.sum() if not valid_profits.empty else None
        total_saving_1d = int(watch_df["saving_1d"].sum()) if "saving_1d" in watch_df.columns else 0
        total_saving_2d = total_saving_1d * 2
        saving_disp = f"-¥{total_saving_1d:,}" if total_saving_1d > 0 else "¥0"

        # 野村利息の合算: 借入がある場合は現渡完了までの総見込利息を適用（借入なしなら0円）
        nomura_cost_applied = int(nomura_expected_total) if loan_in > 0 else 0
        total_combined_cost = total_nikko_cost + nomura_cost_applied
        final_net_profit = (total_yutai_val - total_combined_cost) if total_yutai_val > 0 else (0 - total_combined_cost)

        if total_combined_cost > 0 and total_yutai_val > 0:
            roi_ratio = total_yutai_val / float(total_combined_cost)
            roi_str = f"{roi_ratio:.1f}倍"
        else:
            roi_str = "―"

        if final_net_profit > 0:
            net_profit_color = "#34d399"
            net_profit_badge = f'<span style="background:#065f46; color:#a7f3d0; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:600;">✨ プラス利益 ({roi_str}回収)</span>'
        elif final_net_profit == 0:
            net_profit_color = "#94a3b8"
            net_profit_badge = '<span style="background:#334155; color:#cbd5e1; padding:2px 8px; border-radius:4px; font-size:11px;">±0円</span>'
        else:
            net_profit_color = "#f87171"
            net_profit_badge = '<span style="background:#7f1d1d; color:#fca5a5; padding:2px 8px; border-radius:4px; font-size:11px; font-weight:600;">⚠️ コスト割れ注意</span>'

        funds_disp = f"¥{int(total_funds):,}" if total_funds > 0 else "―"
        cost_disp = f"¥{int(total_nikko_cost):,}" if total_nikko_cost > 0 else "¥0"
        profit_disp = f"¥{int(total_profit):,}" if total_profit is not None else "―"
        cost_sub_label = "銘柄別自動算出" if new_mode == "auto" else f"{effective_lend_days}日分"

        rows_html_list = []
        for _, r in watch_df.sort_values(by="funds_yen").iterrows():
            c = r["code"]
            n = r["name"]
            funds_m = r["funds_man_str"]
            n_disp = r["nikko_display"]
            s_disp = r["sbi_display"]
            trend_str = r["trend_combined"]
            y_val = r["yutai_content"]
            n_cost_val = r["nikko_cost_str"]
            if new_mode == "auto" and r.get("lend_days") and n_cost_val != "―":
                n_cost_str = f"{n_cost_val} ({r['lend_days']}日)"
            else:
                n_cost_str = n_cost_val
            n_net_str = r["net_profit_nikko_str"]
            y_pct = f"{r['yield_pct']:.1f}%" if r["yield_pct"] is not None else "―"
            sig = r["signal"]

            sbi_color = "#f87171" if r["sbi_now"] in ("×", "▲") or r["is_sbi_drop"] else ("#a7f3d0" if r["sbi_now"] == "◎" else "#94a3b8")
            nikko_color = "#f87171" if r["is_nikko_drop"] or (r["nikko_now"] is not None and r["nikko_now"] < nikko_th) else "#a7f3d0"

            trend_plain = r.get("trend_combined", "―")
            trend_html_val = r.get("trend_html") or trend_plain

            c_esc = html.escape(str(c))
            n_esc = html.escape(str(n))
            funds_m_esc = html.escape(str(funds_m))
            n_disp_esc = html.escape(str(n_disp))
            s_disp_esc = html.escape(str(s_disp))
            y_esc = html.escape(str(y_val))
            trend_plain_esc = html.escape(str(trend_plain))
            n_cost_str_esc = html.escape(str(n_cost_str))
            saving_str_esc = html.escape(str(r.get("saving_str", "―")))
            n_net_str_esc = html.escape(str(n_net_str))
            wait_label_esc = html.escape(str(r.get("wait_label", "―")))
            y_pct_esc = html.escape(str(y_pct))
            sig_esc = html.escape(str(sig))

            row_html = (
                f'<tr style="border-bottom: 1px dashed #1e293b;">'
                f'<td style="padding: 4px 6px; font-family:\'JetBrains Mono\',monospace; color:#93c5fd; font-weight:600;">{c_esc}</td>'
                f'<td style="padding: 4px 6px; color:#f1f5f9; font-weight:600; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="{n_esc}">{n_esc}</td>'
                f'<td style="padding: 4px 6px; text-align:right; font-weight:600; color:#fde68a;">{funds_m_esc}</td>'
                f'<td style="padding: 4px 6px; text-align:right; font-weight:600; color:{nikko_color};">{n_disp_esc}</td>'
                f'<td style="padding: 4px 6px; text-align:center; font-weight:600; color:{sbi_color};">{s_disp_esc}</td>'
                f'<td style="padding: 4px 6px; font-size:11px; white-space:nowrap;" title="{trend_plain_esc}">{trend_html_val}</td>'
                f'<td style="padding: 4px 6px; color:#cbd5e1; font-size:11px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;" title="{y_esc}">{y_esc}</td>'
                f'<td style="padding: 4px 6px; text-align:right; font-weight:600; color:#cbd5e1;">{n_cost_str_esc}</td>'
                f'<td style="padding: 4px 6px; text-align:center; font-size:10.5px; font-weight:600; color:#38bdf8; background:rgba(56,189,248,0.08); border-radius:4px;" title="1日待機/2日待機で削減される日興貸株料">{saving_str_esc}</td>'
                f'<td style="padding: 4px 6px; text-align:right; font-weight:600; color:#86efac;">{n_net_str_esc}</td>'
                f'<td style="padding: 4px 6px; text-align:center; font-size:11px; color:#fde68a;">{wait_label_esc}</td>'
                f'<td style="padding: 4px 6px; text-align:right; color:#86efac;">{y_pct_esc}</td>'
                f'<td style="padding: 4px 6px; text-align:center; font-size:11px;">{sig_esc}</td>'
                f'</tr>'
            )
            rows_html_list.append(row_html)

        all_rows_html = "".join(rows_html_list)

        # 総合収支・コスト対効果分析カード
        benefit_summary_card = (
            f'<div style="background: linear-gradient(135deg, #0f172a 0%, #1e1b4b 100%); border: 1px solid #6366f1; border-radius: 8px; padding: 0.65rem 0.9rem; margin-bottom: 0.6rem; box-shadow: 0 4px 12px rgba(0,0,0,0.25);">'
            f'<div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.4rem; border-bottom:1px solid #334155; padding-bottom:0.35rem;">'
            f'<div style="color:#c7d2fe; font-weight:700; font-size:13px; display:flex; align-items:center; gap:6px;">'
            f'💎 <b>優待クロス 総合収支 ＆ コスト対効果分析</b> '
            f'<span style="color:#94a3b8; font-size:10.5px; font-weight:normal;">(日興クロス手数料 ＋ 野村Webローン利息 vs 優待総価値)</span>'
            f'</div>'
            f'<div>{net_profit_badge}</div>'
            f'</div>'
            f'<div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); gap: 0.5rem; text-align:center;">'
            f'<div style="background:rgba(15,23,42,0.6); border:1px solid #334155; border-radius:6px; padding:0.4rem;">'
            f'<div style="font-size:10.5px; color:#94a3b8;">🎁 優待価値 合計</div>'
            f'<div style="font-size:16px; font-weight:bold; color:#fde68a; font-family:\'JetBrains Mono\',monospace;">¥{total_yutai_val:,}</div>'
            f'<div style="font-size:9.5px; color:#64748b;">(監視{len(watch_df)}銘柄)</div>'
            f'</div>'
            f'<div style="background:rgba(15,23,42,0.6); border:1px solid #334155; border-radius:6px; padding:0.4rem;">'
            f'<div style="font-size:10.5px; color:#94a3b8;">⚡ 日興手数料計</div>'
            f'<div style="font-size:16px; font-weight:bold; color:#cbd5e1; font-family:\'JetBrains Mono\',monospace;">¥{total_nikko_cost:,}</div>'
            f'<div style="font-size:9.5px; color:#64748b;">({cost_sub_label})</div>'
            f'</div>'
            f'<div style="background:rgba(15,23,42,0.6); border:1px solid #334155; border-radius:6px; padding:0.4rem;">'
            f'<div style="font-size:10.5px; color:#94a3b8;">🏦 野村利息 (現渡まで)</div>'
            f'<div style="font-size:16px; font-weight:bold; color:#c084fc; font-family:\'JetBrains Mono\',monospace;">¥{nomura_cost_applied:,}</div>'
            f'<div style="font-size:9.5px; color:#64748b;">(本日累計: ¥{nomura_accrued:,})</div>'
            f'</div>'
            f'<div style="background:rgba(15,23,42,0.6); border:1px solid #4338ca; border-radius:6px; padding:0.4rem;">'
            f'<div style="font-size:10.5px; color:#a5b4fc;">💸 コスト総計 (日興+野村)</div>'
            f'<div style="font-size:16px; font-weight:bold; color:#fca5a5; font-family:\'JetBrains Mono\',monospace;">¥{total_combined_cost:,}</div>'
            f'<div style="font-size:9.5px; color:#818cf8;">(実質総費用)</div>'
            f'</div>'
            f'<div style="background:rgba(15,23,42,0.7); border:1px solid {net_profit_color}; border-radius:6px; padding:0.4rem; box-shadow: 0 0 10px rgba(52,211,153,0.15);">'
            f'<div style="font-size:10.5px; color:{net_profit_color}; font-weight:600;">✨ 最終実質純手取</div>'
            f'<div style="font-size:18px; font-weight:bold; color:{net_profit_color}; font-family:\'JetBrains Mono\',monospace;">{"+" if final_net_profit > 0 else ""}¥{final_net_profit:,}</div>'
            f'<div style="font-size:9.5px; color:#94a3b8;">(優待価値 - 総コスト)</div>'
            f'</div>'
            f'</div>'
            f'</div>'
        )

        html_panel = (
            f'{benefit_summary_card}'
            f'<div class="target-highlight-panel">'
            f'<div class="target-header">⭐ 監視・目標銘柄 個別リスト ({len(watch_df)}件ピン留め中)</div>'
            f'<div class="target-summary">'
            f'<div class="target-summary-item"><span class="label">拘束資金合計:</span><span class="value">{funds_disp}</span></div>'
            f'<div class="target-summary-item"><span class="label">日興手数料計:</span><span class="value" style="color:#cbd5e1;">{cost_disp}</span> <span style="font-size:10.5px;color:#94a3b8;">({cost_sub_label})</span></div>'
            f'<div class="target-summary-item"><span class="label">1日待機節約:</span><span class="value" style="color:#38bdf8;">{saving_disp}</span> <span style="font-size:10.5px;color:#94a3b8;">(2日: -¥{total_saving_2d:,})</span></div>'
            f'<div class="target-summary-item"><span class="label">見込実質手取:</span><span class="value" style="color:#86efac;">{profit_disp}</span></div>'
            f'<div class="target-summary-item"><span class="label">野村借入利息:</span><span class="value" style="color:#c084fc;">¥{nomura_daily:,}</span> <span style="font-size:10.5px;color:#94a3b8;">/日</span></div>'
            f'</div>'
            f'<div style="margin-top: 0.35rem; background: #0f172a; border-radius: 6px; padding: 0.2rem 0.4rem; border: 1px solid #1e293b; overflow-x: auto; overflow-y: auto; max-height: 200px;">'
            f'<table style="width: 100%; min-width: 1120px; border-collapse: collapse; font-size: 11.5px; text-align: left;">'
            f'<thead style="position: sticky; top: 0; background: #0f172a; z-index: 5;">'
            f'<tr style="border-bottom: 1px solid #334155; color: #94a3b8; font-weight: bold;">'
            f'<th style="padding: 5px 6px; width: 50px;">コード</th>'
            f'<th style="padding: 5px 6px; width: 120px;">銘柄名</th>'
            f'<th style="padding: 5px 6px; text-align: right; width: 80px;">最低取得価格</th>'
            f'<th style="padding: 5px 6px; text-align: right; width: 80px;">日興最新</th>'
            f'<th style="padding: 5px 6px; text-align: center; width: 60px;">SBI最新</th>'
            f'<th style="padding: 5px 6px; width: 155px;">残数推移 (日興/SBI)</th>'
            f'<th style="padding: 5px 6px; min-width: 180px;">優待内容</th>'
            f'<th style="padding: 5px 6px; text-align: right; width: 90px;">日興手数料</th>'
            f'<th style="padding: 5px 6px; text-align: center; width: 140px; color: #38bdf8;">待機節約 (1日/2日)</th>'
            f'<th style="padding: 5px 6px; text-align: right; width: 80px;">実質手取</th>'
            f'<th style="padding: 5px 6px; text-align: center; width: 85px;">損益分岐</th>'
            f'<th style="padding: 5px 6px; text-align: right; width: 55px;">利回り</th>'
            f'<th style="padding: 5px 6px; text-align: center; width: 75px;">判定</th>'
            f'</tr>'
            f'</thead>'
            f'<tbody>'
            f'{all_rows_html}'
            f'</tbody>'
            f'</table>'
            f'</div>'
            f'</div>'
        )
        st.markdown(html_panel, unsafe_allow_html=True)
    else:
        empty_panel = (
            f'<div class="target-highlight-panel" style="border-color: #334155; opacity: 0.85; padding: 0.5rem 0.8rem;">'
            f'<div class="target-header" style="color: #94a3b8; border-bottom: none; margin-bottom: 0;">'
            f'⭐ 監視銘柄はまだ選択されていません（一覧の最左列「⭐」にチェックを入れるとここにピン留めされます）'
            f'</div>'
            f'</div>'
        )
        st.markdown(empty_panel, unsafe_allow_html=True)

    # ----------------------------------------------------
    # ★ 直近在庫急減・シグナル悪化銘柄の速報アラートバナー
    # ----------------------------------------------------
    alert_stocks = df_analyzed[(df_analyzed["is_nikko_drop"] == True) | (df_analyzed["is_sbi_drop"] == True) | (df_analyzed["signal"] == "🔴 今夜確保")].copy()
    if not alert_stocks.empty:
        alert_chips = []
        for _, ar in alert_stocks.head(6).iterrows():
            c_esc = html.escape(str(ar["code"]))
            n_esc = html.escape(str(ar["name"]))
            raw_drop = ar["nikko_display"] if ar["is_nikko_drop"] else ar["sbi_display"]
            drop_tag_esc = html.escape(str(raw_drop))
            sig_esc = html.escape(str(ar["signal"]))
            alert_chips.append(
                f'<span style="background:rgba(239,68,68,0.18); border:1px solid rgba(239,68,68,0.45); border-radius:4px; padding:2px 7px; font-size:11px; margin-right:4px; display:inline-block;">'
                f'<b style="color:#fecaca;">[{c_esc}] {n_esc}</b>: <span style="color:#f87171;font-weight:600;">{drop_tag_esc}</span> ({sig_esc})'
                f'</span>'
            )
        alert_banner_html = (
            f'<div style="background:#1e1b4b; border:1px solid #6366f1; border-radius:6px; padding:0.35rem 0.65rem; margin-top:0.4rem; margin-bottom:0.2rem; display:flex; align-items:center; flex-wrap:wrap; gap:4px;">'
            f'<span style="font-weight:700; color:#c7d2fe; font-size:11.5px; margin-right:6px;">🚨 在庫急変・シグナル悪化速報:</span>'
            f'{" ".join(alert_chips)}'
            f'</div>'
        )
        st.markdown(alert_banner_html, unsafe_allow_html=True)

    # ----------------------------------------------------
    # メイン画面 権利月クイック切替バー
    # ----------------------------------------------------
    quick_months = month_options[:6]  # 向こう半年分
    quick_labels = {m: f"{m.split('-')[1]}月 ({m})" + (" ✅" if any(x["month"] == m and x["has_data"] for x in available_months_info) else " ⚠️") for m in quick_months}
    if chosen_month not in quick_months:
        quick_months.append(chosen_month)
        quick_labels[chosen_month] = f"{chosen_month.split('-')[1]}月 ({chosen_month})"

    # ----------------------------------------------------
    # メイン画面 権利月クイック切替バー (ステートレス・ピルボタン群で巻き戻りバグ完全根絶)
    # ----------------------------------------------------
    quick_months = month_options[:6]  # 向こう半年分
    if chosen_month not in quick_months:
        quick_months.append(chosen_month)

    c_m0, *c_mb = st.columns([1.1] + [1.5] * len(quick_months))
    with c_m0:
        st.markdown("<div style='font-size:12px; font-weight:600; color:#cbd5e1; padding-top:7px;'>📅 権利月:</div>", unsafe_allow_html=True)
    
    for idx, m in enumerate(quick_months):
        with c_mb[idx]:
            has_data = any(x["month"] == m and x["has_data"] for x in available_months_info)
            badge = "✅" if has_data else "⚠️"
            is_active = (m == chosen_month)
            btn_label = f"{m.split('-')[1]}月 {badge}" if not is_active else f"▶ {m.split('-')[1]}月"
            b_type = "primary" if is_active else "secondary"
            if st.button(btn_label, key=f"quick_btn_m_{m}", type=b_type, use_container_width=True, help=f"{m} の優待在庫画面へ即座に切替"):
                if m != chosen_month:
                    st.session_state["selected_month"] = m
                    st.query_params["month"] = m
                    st.rerun()

    # ----------------------------------------------------
    # コントロールバー
    # ----------------------------------------------------
    c_f1, c_f2, c_f3, c_f4, c_f5, c_f6, c_f7 = st.columns([1.8, 1.3, 0.9, 0.9, 1.6, 1.1, 1.3])
    with c_f1: query = st.text_input("検索", placeholder="コード/銘柄名/優待内容", label_visibility="collapsed")
    with c_f2: signal_filter = st.multiselect("絞込", options=["🔴 今夜確保", "🔥 補充", "🚨 SBI急変", "🔴 即確保", "🟡 要監視", "🟢 待機可", "⚪ 枯渇"], default=[], label_visibility="collapsed")
    with c_f3: only_watch = st.checkbox("⭐ 監視のみ", value=False)
    with c_f4: only_nikko = st.checkbox("日興あり", value=False)
    with c_f5:
        sort_mode = st.selectbox("並び替え", options=[
            "💴 最低取得価格が安い順",
            "💰 最低取得価格が高い順",
            "⚡ シグナル優先",
            "🎁 実質純利益が高い順",
            "📈 利回りが高い順",
            "📉 日興在庫が多い順",
            "🔄 ソートなし (標準)"
        ], index=0, label_visibility="collapsed")
    with c_f6:
        if st.button("🔄 再読込", use_container_width=True):
            st.rerun()
    with c_f7:
        if st.button("🚀 最新取得", use_container_width=True):
            with st.spinner(f"⚡ {chosen_month} の最新在庫データを直接スクレイピング中 (数秒)..."):
                ok, msg = run_direct_scrape(rights_arg=chosen_month)
                if ok:
                    sync_scraped_data_to_github(chosen_month, gh_token, gh_repo)
                    st.toast("✅ " + msg)
                    st.rerun()
                else:
                    ok_gh, msg_gh = trigger_github_workflow(token=gh_token, repo=gh_repo)
                    if ok_gh:
                        st.toast(f"ℹ️ {msg_gh}")
                    else:
                        st.error(f"取得エラー: {msg}")

    # フィルタリング
    filtered_df = df_analyzed.copy()
    if only_watch: filtered_df = filtered_df[filtered_df["watch"] == True]
    if only_nikko: filtered_df = filtered_df[filtered_df["nikko_now"].fillna(0) > 0]
    if signal_filter:
        cond = pd.Series([False] * len(filtered_df), index=filtered_df.index)
        for sig in signal_filter:
            if sig == "🔥 補充": cond |= (filtered_df["is_refill"] == True)
            elif sig == "🚨 SBI急変": cond |= (filtered_df["is_sbi_drop"] == True)
            else: cond |= (filtered_df["signal"] == sig)
        filtered_df = filtered_df[cond]
    if query:
        q = query.strip().lower()
        filtered_df = filtered_df[
            filtered_df["code"].astype(str).str.lower().str.contains(q) |
            filtered_df["name"].astype(str).str.lower().str.contains(q) |
            filtered_df["yutai_content"].astype(str).str.lower().str.contains(q) |
            filtered_df["yutai_content_raw"].astype(str).str.lower().str.contains(q)
        ]

    # ソート: デフォルトは「💴 最低取得価格が安い順」
    # ★重要改善: チェックボックス操作時に行が勝手に最上部に飛んで連続チェックできなくなる不具合を根絶するため、
    # watch_rank による強制並び替えは完全撤廃（監視銘柄は上部ピン留めカードで常時確認可能）。
    if "最低取得価格が安い順" in sort_mode or "取得資金が安い順" in sort_mode:
        filtered_df = filtered_df.sort_values(by=["funds_yen"], ascending=[True], na_position="last")
    elif "最低取得価格が高い順" in sort_mode or "取得資金が高い順" in sort_mode:
        valid_funds = filtered_df[filtered_df["funds_yen"] < 99999990].sort_values(by=["funds_yen"], ascending=[False])
        invalid_funds = filtered_df[filtered_df["funds_yen"] >= 99999990]
        filtered_df = pd.concat([valid_funds, invalid_funds])
    elif "実質純利益が高い順" in sort_mode:
        filtered_df = filtered_df.sort_values(by=["net_profit"], ascending=[False], na_position="last")
    elif "利回りが高い順" in sort_mode:
        filtered_df = filtered_df.sort_values(by=["yield_pct"], ascending=[False], na_position="last")
    elif "日興在庫が多い順" in sort_mode:
        filtered_df = filtered_df.sort_values(by=["nikko_now"], ascending=[False], na_position="last")
    elif "シグナル優先" in sort_mode:
        filtered_df = filtered_df.sort_values(by=["signal_rank", "funds_yen"], ascending=[True, True], na_position="last")
    elif sort_mode == "🔄 ソートなし (標準)":
        pass  # 元の順序（スクレイピング/マスター順）を完全維持

    # ----------------------------------------------------
    # 検索・絞込・ソート変更時の data_editor インデックスズレ防止
    # 行構成が変わる操作を検知した際は editor_version を即時更新し古い行キャッシュを完全消去
    # ----------------------------------------------------
    filter_state_sig = f"{query}_{','.join(sorted(signal_filter))}_{only_watch}_{only_nikko}_{sort_mode}"
    if "last_filter_state_sig" not in st.session_state:
        st.session_state["last_filter_state_sig"] = filter_state_sig
    elif st.session_state["last_filter_state_sig"] != filter_state_sig:
        st.session_state["last_filter_state_sig"] = filter_state_sig
        st.session_state["editor_version"] = st.session_state.get("editor_version", 0) + 1

    # ----------------------------------------------------
    # タブ構成
    # ----------------------------------------------------
    tab1, tab2, tab3, tab4 = st.tabs([
        f"⚡ 実戦ボード ({len(filtered_df)}件)",
        "🗓 日時別 在庫推移マトリクス",
        "📊 日興在庫 時系列グラフ",
        "💡 運用ガイド ＆ 自動実行"
    ])

    # ----------------------------------------------------
    # TAB 1: 実戦ボード (ユーザー指定のカラム順序 ＆ ひと目でわかる残量急変表示)
    # ----------------------------------------------------
    with tab1:
        display_rows = []
        for _, r in filtered_df.iterrows():
            n_cost_val = str(r.get("nikko_cost_str", "―"))
            if new_mode == "auto" and r.get("lend_days") and n_cost_val != "―":
                n_cost_display = f"{n_cost_val} ({r['lend_days']}日)"
            else:
                n_cost_display = n_cost_val

            display_rows.append({
                "⭐": bool(r.get("watch", False)),
                "コード": str(r.get("code", "")),
                "銘柄": str(r.get("name", "")),
                "最低取得価格": str(r.get("funds_man_str", "―")),
                "日興最新": str(r.get("nikko_display", "取扱無")),
                "SBI最新": str(r.get("sbi_display", "取扱無")),
                "残数推移": str(r.get("trend_combined", "―")),
                "優待内容": str(r.get("yutai_content", "―")),
                "日興手数料": n_cost_display,
                "待機節約": str(r.get("saving_str", "―")),
                "実質手取": str(r.get("net_profit_nikko_str", "定性優待")),
                "損益分岐": str(r.get("wait_label", "―")),
                "その他証券": str(r.get("other_brokers", "―")),
                "優待利回り": f"{r['yield_pct']:.1f}%" if (r["yield_pct"] is not None and r["yield_pct"] > 0) else "―",
                "判定": str(r.get("signal", "")),
            })

        df_table = pd.DataFrame(display_rows)

        if not df_table.empty:
            for col in df_table.columns:
                if col != "⭐":
                    df_table[col] = df_table[col].fillna("―").astype(str)
            # ★連鎖ループ防止: エディタキーを動的バージョン化し、編集時にキーを切り替えて古い行インデックスのキャッシュを完全破棄
            if "editor_version" not in st.session_state:
                st.session_state["editor_version"] = 0
            editor_key = f"yutai_data_editor_{chosen_month}_{st.session_state['editor_version']}"

            nikko_col_help = (
                "SMBC日興証券 一般信用売＋制度買現引（ダイレクトコース）。各銘柄の権利確定月・20日権利日・祝日・受渡日を完全自動判定した想定コスト"
                if new_mode == "auto" else
                f"SMBC日興証券 手数料概算（制度買金利3.55% 1日 + 貸株料1.9% × {effective_lend_days}日）"
            )

            edited_table = st.data_editor(
                df_table,
                key=editor_key,
                use_container_width=True,
                hide_index=True,
                height=580,
                column_config={
                    "⭐": st.column_config.CheckboxColumn("⭐", width="small", help="監視・目標銘柄（チェックで上部ピン留めカードに追加＆多層自動保存）"),
                    "コード": st.column_config.TextColumn("コード", width="small"),
                    "銘柄": st.column_config.TextColumn("銘柄", width="medium"),
                    "最低取得価格": st.column_config.TextColumn("最低取得価格", width="small", help="優待取得に必要な概算資金（万円単位）"),
                    "日興最新": st.column_config.TextColumn("日興最新", width="small", help="最新在庫株数。急減時は🚨▼で減少数を強調表示"),
                    "SBI最新": st.column_config.TextColumn("SBI最新", width="small", help="SBI信号（◎▲×）。悪化・急変時は🚨タグを表示"),
                    "残数推移": st.column_config.TextColumn("残数推移 (日興/SBI)", width="medium", help="日興およびSBIの在庫トレンド (↘減少/↗増加/維持/急変)"),
                    "優待内容": st.column_config.TextColumn("優待内容", width="large", help="優待品目・金額・数量"),
                    "日興手数料": st.column_config.TextColumn("日興手数料", width="small", help=nikko_col_help),
                    "待機節約": st.column_config.TextColumn("待機節約 (1日/2日)", width="medium", help="日興一般信用売りをあと1日または2日待機した場合に節約できる貸株料（年1.9%）。在庫に余裕があれば待機することで手数料を低減できます"),
                    "実質手取": st.column_config.TextColumn("実質手取", width="small", help="優待価値(円)から日興優待クロスコストを差し引いた実質純利益"),
                    "損益分岐": st.column_config.TextColumn("損益分岐 (待機可)", width="small", help="日興貸株料＋野村利息が優待価値を超えて赤字転落するまでの限界待機日数"),
                    "その他証券": st.column_config.TextColumn("その他証券", width="small", help="カブ・楽天・GMO等の残数・信号"),
                    "優待利回り": st.column_config.TextColumn("優待利回り", width="small", help="総合利回り(%)"),
                    "判定": st.column_config.TextColumn("判定", width="small", help="意思決定シグナル（今夜確保/要監視/待機可/枯渇）"),
                },
                disabled=[c for c in df_table.columns if c != "⭐"]
            )

            # --- 確実なコードキー差分検知 (列ヘッダーソート時の行番号インデックスズレを完全根絶) ---
            orig_map = dict(zip(df_table["コード"], df_table["⭐"]))
            new_map = dict(zip(edited_table["コード"], edited_table["⭐"]))
            changed_items = []
            for c, new_val in new_map.items():
                old_val = orig_map.get(c)
                if old_val is not None and old_val != new_val:
                    changed_items.append((c, bool(new_val)))

            if changed_items:
                changed_codes = []
                for c, is_watched in changed_items:
                    if is_watched and c not in st.session_state["watchlist"]:
                        st.session_state["watchlist"].append(c)
                        changed_codes.append(c)
                    elif not is_watched and c in st.session_state["watchlist"]:
                        st.session_state["watchlist"].remove(c)
                        changed_codes.append(c)

                if changed_codes:
                    # ★コミット多重起動・競合コンフリクト根絶: ループ外で1回だけまとめて永続化を実行
                    persist_watchlist(
                        st.session_state["watchlist"],
                        gh_token,
                        gh_repo,
                        trigger_code=",".join(changed_codes)
                    )
                    added_c = [c for c, w in changed_items if w]
                    removed_c = [c for c, w in changed_items if not w]
                    if added_c:
                        st.toast(f"⭐ 監視に追加: {', '.join(added_c)} (即時保存済)", icon="⭐")
                    if removed_c:
                        st.toast(f"🗑️ 監視を解除: {', '.join(removed_c)} (即時保存済)", icon="🗑️")

                    # ★操作の瞬間にブラウザの localStorage と URL (history.replaceState) へ直接書き込み！
                    # （st.rerun なしでスクロールは完全静止のまま、ブラウザ側へミリ秒単位で永続保存完了）
                    try:
                        instant_json = json.dumps(st.session_state["watchlist"], ensure_ascii=False)
                        st.components.v1.html(f"""
                        <script>
                        (function() {{
                            try {{
                                const KEY = "yutai_watchlist_v13";
                                const codes = {instant_json};
                                window.parent.localStorage.setItem(KEY, JSON.stringify(codes));
                                const pUrl = new URL(window.parent.location.href);
                                pUrl.searchParams.set("watch_v", "v13");
                                pUrl.searchParams.set("watch", codes.length > 0 ? codes.join(",") : "none");
                                window.parent.history.replaceState({{}}, "", pUrl.toString());
                            }} catch(e) {{}}
                        }})();
                        </script>
                        """, height=0, width=0)
                    except Exception:
                        pass

                # ★最重要改善: チェック操作時は st.rerun() を呼ばない！
                # これによりページ全体のリロードや画面のリセット、スクロールの巻き戻りが一切起きず、
                # ユーザーが現在位置にとどまったまま連続でサクサクとチェックできる！

    # ----------------------------------------------------
    # TAB 2: 日時別 在庫推移マトリクス
    # ----------------------------------------------------
    with tab2:
        st.markdown("##### 🗓 日時別 在庫推移マトリクス")
        st.caption("各社在庫の推移を横並びで比較表示します。列ヘッダーにカーソルを合わせると取得日時が確認できます。")
        BROKER_COLS = {
            "日興": "nikko", "楽天": "rakuten", "カブ": "kabu",
            "SBI": "sbi", "GMO": "gmo", "松井": "matsui", "マネックス": "monex",
        }
        NUMERIC_BROKERS = {"nikko", "rakuten", "kabu"}

        all_ts = (
            df_hist.dropna(subset=["timestamp"])
            .sort_values(["dt", "timestamp"])["timestamp"]
            .drop_duplicates().tolist()
        )
        if len(all_ts) < 2:
            st.info("スナップショットが1件のみのためマトリクスを表示できません。「🚀 最新取得」等で取得を重ねると推移が表示されます。")
        else:
            mx_watch = [c for c in st.session_state["watchlist"] if c in df_analyzed["code"].tolist()]
            if not mx_watch:
                mx_watch = df_analyzed[df_analyzed["nikko_now"].fillna(0) > 0]["code"].head(12).tolist()

            m_c1, m_c2, m_c3 = st.columns([1.0, 1.2, 3.8])
            with m_c1:
                mx_broker = st.selectbox("証券会社", options=list(BROKER_COLS.keys()), index=0)
            with m_c2:
                n_snap = st.slider("表示スナップショット数", min_value=2, max_value=min(30, len(all_ts)), value=min(8, len(all_ts)))
            with m_c3:
                codes_mx = st.multiselect(
                    "銘柄を選択 (複数可)",
                    options=df_analyzed["code"].tolist(),
                    default=mx_watch[:12],
                    format_func=lambda c: f"{c} {df_analyzed[df_analyzed['code']==c]['name'].values[0] if len(df_analyzed[df_analyzed['code']==c])>0 else ''}"
                )

            if codes_mx:
                bcol = BROKER_COLS.get(mx_broker, "nikko")
                if bcol not in df_hist.columns or df_hist[bcol].isna().all():
                    st.info(f"ℹ️ {mx_broker} の在庫・信号データは現在取得されている履歴CSVに含まれていません。")
                else:
                    ts_list = all_ts[-n_snap:]
                    sub = (df_hist[df_hist["code"].isin(codes_mx) & df_hist["timestamp"].isin(ts_list)]
                       [["code", "timestamp", bcol]]
                       .sort_values("timestamp")
                       .drop_duplicates(subset=["code", "timestamp"], keep="last"))
                piv = sub.pivot_table(index="code", columns="timestamp", values=bcol, aggfunc="last", dropna=False)
                piv = piv.reindex(index=codes_mx, columns=ts_list)
                name_map = df_analyzed.drop_duplicates("code").set_index("code")["name"]

                is_numeric = bcol in NUMERIC_BROKERS
                if is_numeric:
                    fmt_mx = piv.apply(lambda col: col.map(fmt_qty))
                else:
                    fmt_mx = piv.apply(lambda col: col.map(fmt_signal))

                latest_ts, prev_ts = ts_list[-1], ts_list[-2]
                mx_rows = []
                for code in codes_mx:
                    name = name_map.get(code, code)
                    latest_v = piv.loc[code, latest_ts]
                    prev_v = piv.loc[code, prev_ts]
                    if is_numeric:
                        latest_s = fmt_qty(latest_v)
                        lf, pf = to_float(latest_v), to_float(prev_v)
                        if lf is None or pf is None: diff_s = "―"
                        elif lf - pf > 0: diff_s = f"+{int(lf - pf):,}"
                        elif lf - pf < 0: diff_s = f"{int(lf - pf):,}"
                        else: diff_s = "±0"
                    else:
                        latest_s = fmt_signal(latest_v)
                        prev_s = fmt_signal(prev_v)
                        diff_s = f"{prev_s}→{latest_s}" if prev_s != latest_s else "維持"
                    row = {"コード": code, "銘柄名": name, "最新": latest_s, "前回比": diff_s}
                    for ts in ts_list:
                        short = ts[5:] if isinstance(ts, str) and len(ts) >= 11 else str(ts)
                        row[short] = fmt_mx.loc[code, ts]
                    mx_rows.append(row)

                df_mx = pd.DataFrame(mx_rows)
                if not df_mx.empty and "コード" in df_mx.columns:
                    df_mx["コード"] = df_mx["コード"].astype(str)
                mx_config = {
                    "コード": st.column_config.TextColumn("コード", width="small"),
                    "銘柄名": st.column_config.TextColumn("銘柄名", width="medium"),
                    "最新": st.column_config.TextColumn("最新", width="small"),
                    "前回比": st.column_config.TextColumn("前回比", width="small"),
                }
                for ts in ts_list:
                    short = ts[5:] if isinstance(ts, str) and len(ts) >= 11 else str(ts)
                    mx_config[short] = st.column_config.TextColumn(short, width="small", help=str(ts))

                st.dataframe(df_mx, use_container_width=True, hide_index=True, height=min(640, 80 + 29 * len(df_mx)), column_config=mx_config)

    # ----------------------------------------------------
    # TAB 3: 日興在庫 時系列グラフ
    # ----------------------------------------------------
    with tab3:
        st.markdown("##### 📈 日興在庫の時系列推移チャート")
        watch_or_top = [c for c in st.session_state["watchlist"] if c in df_analyzed["code"].tolist()]
        if not watch_or_top:
            watch_or_top = df_analyzed[df_analyzed["nikko_now"].fillna(0) > 0]["code"].head(8).tolist()

        codes_plot = st.multiselect(
            "グラフ表示する銘柄を選択 (複数選択可)",
            options=df_analyzed["code"].tolist(),
            default=watch_or_top[:8],
            format_func=lambda c: f"{c} {df_analyzed[df_analyzed['code']==c]['name'].values[0] if len(df_analyzed[df_analyzed['code']==c])>0 else ''}"
        )
        if codes_plot:
            sub = df_hist[df_hist["code"].isin(codes_plot)].copy()
            if not sub.empty:
                if "dt" not in sub.columns or sub["dt"].isna().all():
                    sub["dt"] = pd.to_datetime(sub["timestamp"], errors="coerce")
                
                # ★時系列ソート崩れ完全根絶: dt (日付時刻) で厳密に昇順ソート＆重複排除
                sub = sub.dropna(subset=["dt"]).sort_values(by="dt", ascending=True)
                sub = sub.drop_duplicates(subset=["dt", "code"], keep="last")
                
                # 表示用ラベル (例: "09/14 17:00")
                sub["display_time"] = sub["dt"].dt.strftime("%m/%d %H:%M")
                
                # 時系列順序のソート順リスト（左から右への時系列順を絶対保証）
                sorted_timeline = sub.sort_values(by="dt")["display_time"].unique().tolist()

                # ★銘柄名の完全補完 (df_analyzed から確実に補完し、name 欠落時の折れ線結合を完全防止)
                code_to_name = dict(zip(df_analyzed["code"].astype(str), df_analyzed["name"].astype(str)))
                sub["code_str"] = sub["code"].astype(str)
                sub["name"] = sub["code_str"].map(code_to_name).fillna(sub.get("name", "")).fillna(sub["code_str"])
                sub["stock_label"] = "[" + sub["code_str"] + "] " + sub["name"]

                chart = alt.Chart(sub).mark_line(point=True).encode(
                    x=alt.X(
                        "display_time:O",
                        sort=sorted_timeline,
                        title="取得日時 (時系列昇順)",
                        axis=alt.Axis(labelAngle=-40)
                    ),
                    y=alt.Y("nikko:Q", title="日興在庫数 (株)"),
                    color=alt.Color("stock_label:N", title="銘柄"),
                    detail="code_str:N",
                    tooltip=[
                        alt.Tooltip("stock_label:N", title="銘柄"),
                        alt.Tooltip("code_str:N", title="コード"),
                        alt.Tooltip("timestamp:N", title="取得日時"),
                        alt.Tooltip("nikko:Q", title="日興在庫(株)", format=","),
                        alt.Tooltip("sbi:N", title="SBI"),
                        alt.Tooltip("rakuten:Q", title="楽天(株)", format=",")
                    ]
                ).properties(height=400)
                st.altair_chart(chart, use_container_width=True)

    # ----------------------------------------------------
    # TAB 4: 運用ガイド ＆ 自動実行
    # ----------------------------------------------------
    with tab4:
        st.markdown(f"""
        ### ⚡ 完全サーバーレス自動運用の仕組み ＆ 永続化仕様

        1. **「⭐ 監視（ピン留め）」の多層永続化**:
           - 画面左側のチェックボックス（`⭐`）を切り替えると、即座に画面へ反映され、以下の3つのレイヤーで自動保存されます：
             - **① セッションキャッシュ**: 同一ブラウザ操作中は待ち時間ゼロ（0.01秒）で高速反映。
             - **② ローカルファイル**: `data/watchlist.json` にローカル即時保存。
             - **③ Googleスプレッドシート/GAS**: 指定されたGAS URLへ非同期送信。
             - **④ GitHubリポジトリ永続化**: `GITHUB_TOKEN` を使用してリポジトリ本体（`data/watchlist.json`）に自動コミット。Streamlit Cloudがスリープ・再起動しても設定が永久に保持されます。
        2. **定期自動巡回**:
           - 平日毎日 **17:00** および **20:00**（JST）に GitHub Actions が自動起動し、最新の一般信用在庫を追記コミットします。
        3. **「🚀 最新取得」ボタン（オンデマンド実行）**:
           - 画面上部のボタンを押すと GitHub Actions が直接起動し、1〜2分で最新データが蓄積されます。
        """)

if __name__ == "__main__":
    main()