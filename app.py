# -*- coding: utf-8 -*-
"""
app.py - 株主優待クロス在庫トラッカー ＆ 実戦意思決定ダッシュボード
プロフェッショナル仕様・超高密度（Compact Trading UI）
"""

from __future__ import annotations

import datetime as dt
import io
import os
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

# ============================================================
# 1. ページ初期設定 & 超高密度CSS (Compact FinTech UI)
# ============================================================
st.set_page_config(
    page_title="優待クロス在庫トラッカー",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="collapsed",
)

COMPACT_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;600;700&family=Noto+Sans+JP:wght@400;500;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Noto Sans JP', -apple-system, BlinkMacSystemFont, sans-serif;
    font-size: 13px;
    letter-spacing: -0.01em;
}

/* 全体のパディングを極小化 */
.main .block-container {
    padding-top: 0.6rem !important;
    padding-bottom: 1.5rem !important;
    padding-left: 1rem !important;
    padding-right: 1rem !important;
    max-width: 100% !important;
}

/* トップステータスバー（1行集約） */
.top-bar {
    display: flex;
    justify-content: space-between;
    align-items: center;
    background: #0f172a;
    color: #f8fafc;
    border-radius: 8px;
    padding: 0.45rem 0.9rem;
    margin-bottom: 0.5rem;
    border: 1px solid #1e293b;
    box-shadow: 0 1px 3px rgba(0,0,0,0.2);
}

.top-bar-title {
    font-size: 14px;
    font-weight: 700;
    display: flex;
    align-items: center;
    gap: 0.5rem;
    white-space: nowrap;
}

.top-bar-tags {
    display: flex;
    align-items: center;
    gap: 0.4rem;
    flex-wrap: wrap;
    font-size: 11px;
}

.tag-badge {
    padding: 0.15rem 0.45rem;
    border-radius: 4px;
    font-weight: 600;
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
}

.tag-blue   { background: #1e3a8a; color: #93c5fd; border: 1px solid #2563eb; }
.tag-green  { background: #064e3b; color: #6ee7b7; border: 1px solid #059669; }
.tag-amber  { background: #78350f; color: #fde68a; border: 1px solid #d97706; }
.tag-red    { background: #7f1d1d; color: #fca5a5; border: 1px solid #dc2626; }
.tag-purple { background: #581c87; color: #f0abfc; border: 1px solid #9333ea; }
.tag-gray   { background: #334155; color: #cbd5e1; border: 1px solid #475569; }

/* KPIミニバー */
.kpi-row {
    display: flex;
    gap: 0.4rem;
    margin-bottom: 0.6rem;
    flex-wrap: wrap;
}

.kpi-chip {
    flex: 1;
    min-width: 130px;
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 0.35rem 0.65rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

@media (prefers-color-scheme: dark) {
    .kpi-chip {
        background: #1e293b;
        border-color: #334155;
    }
}

.kpi-chip-label {
    font-size: 11px;
    font-weight: 600;
    color: #64748b;
}

.kpi-chip-val {
    font-size: 15px;
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
}

/* Streamlitデフォルト要素の余白圧縮 */
div[data-testid="stVerticalBlock"] > div {
    gap: 0.3rem !important;
}

.stTabs [data-baseweb="tab-list"] {
    gap: 0.3rem;
    margin-bottom: 0.4rem;
}

.stTabs [data-baseweb="tab"] {
    padding: 0.3rem 0.75rem !important;
    font-size: 12px !important;
    font-weight: 600 !important;
}

div.stButton > button {
    padding: 0.25rem 0.6rem !important;
    font-size: 12px !important;
    border-radius: 5px !important;
    min-height: auto !important;
    line-height: 1.4 !important;
}

div[data-baseweb="input"] input {
    font-size: 12px !important;
    padding: 0.25rem 0.5rem !important;
}

div[data-baseweb="select"] {
    font-size: 12px !important;
}

/* テーブルフォント縮小 */
div[data-testid="stDataFrame"] {
    font-size: 11.5px !important;
}
</style>
"""
st.markdown(COMPACT_CSS, unsafe_allow_html=True)

# ============================================================
# 2. 定数 & 既定値
# ============================================================
DEFAULT_SPREADSHEET_ID = "175sKtMVVp6IgqrzLcRtO5tX7t-wiEKQrrfagfRoH1gM"
APP_VERSION = "v2.1 (Compact Engine)"

# ============================================================
# 3. 堅牢な数値変換・フォーマットユーティリティ (ValueError防止)
# ============================================================
def to_float(v: Any) -> Optional[float]:
    """任意の型から安全にfloatを取得。NaNや不正文字列はNone"""
    if v is None or pd.isna(v) or v == "":
        return None
    try:
        val = float(v)
        return None if np.isnan(val) else val
    except (ValueError, TypeError):
        return None

def fmt_int(v: Any) -> str:
    """安全な整数カンマ区切りフォーマット"""
    f = to_float(v)
    return f"{int(round(f)):,}" if f is not None else "―"

def fmt_float(v: Any, digits: int = 1) -> str:
    """安全な小数フォーマット"""
    f = to_float(v)
    return f"{f:.{digits}f}" if f is not None else "―"

def fmt_qty(v: Any) -> str:
    """株数の見やすい表記 (1万以上は万表記)"""
    f = to_float(v)
    if f is None:
        return "―"
    if f >= 10000:
        return f"{f/10000:.1f}万"
    return f"{int(f):,}"

def parse_qty_safe(v: Any) -> Optional[float]:
    """株数表記（万単位、残無、記号など）を数値化"""
    if v is None or pd.isna(v):
        return None
    if isinstance(v, (int, float)):
        val = float(v)
        return None if np.isnan(val) else val
    s = str(v).strip().replace(",", "").replace(" ", "")
    if s in ("", "-", "―", "ー", "null", "None", "取扱なし"):
        return None
    if "残無" in s or s in ("×", "✕"):
        return 0.0
    if "大量" in s or s in ("◎", "▲"):
        return None
    m = re.search(r"^([\d.]+)万$", s)
    if m:
        try:
            return round(float(m.group(1)) * 10000)
        except ValueError:
            pass
    m = re.search(r"^([\d.]+)$", s)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    return None

def fmt_code(v: Any) -> str:
    """4桁ゼロ埋め文字列に正規化"""
    if v is None or pd.isna(v):
        return ""
    s = str(v).split(".")[0].strip()
    return s.zfill(4) if len(s) <= 4 and s.isdigit() else s

# ============================================================
# 4. データ読み込み（Googleスプレッドシート & ローカルCSV）
# ============================================================
@st.cache_data(ttl=60, show_spinner=False)
def fetch_sheet_csv(sheet_name: str, spreadsheet_id: str = DEFAULT_SPREADSHEET_ID) -> Optional[pd.DataFrame]:
    """gviz/tq 経由でGoogleスプレッドシートからCSV取得"""
    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/gviz/tq?tqx=out:csv&sheet={urllib.parse.quote(sheet_name)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            content = resp.read()
            df = pd.read_csv(io.BytesIO(content))
            return df
    except Exception:
        return None

def load_data(sheet_id: str) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """リポジトリ内の data/ や out/ のCSV、およびGoogleスプレッドシートから柔軟にデータをロード"""
    hist_dfs = []
    raw_mast = None

    # 1. リポジトリ内 / ローカルの data/ および out/ ディレクトリを探索
    for dpath in ["data", "out"]:
        if os.path.exists(dpath):
            h_files = sorted([os.path.join(dpath, f) for f in os.listdir(dpath) if f.startswith("history_") and f.endswith(".csv")])
            for hf in h_files:
                try:
                    df_tmp = pd.read_csv(hf)
                    if not df_tmp.empty:
                        hist_dfs.append(df_tmp)
                except Exception:
                    pass
            m_files = sorted([os.path.join(dpath, f) for f in os.listdir(dpath) if f.startswith("master_") and f.endswith(".csv")], reverse=True)
            if m_files and raw_mast is None:
                try:
                    raw_mast = pd.read_csv(m_files[0])
                except Exception:
                    pass

    # 2. Googleスプレッドシートからも取得
    sheet_hist = fetch_sheet_csv("raw_history", spreadsheet_id=sheet_id)
    if sheet_hist is not None and not sheet_hist.empty:
        hist_dfs.append(sheet_hist)

    if raw_mast is None or raw_mast.empty:
        raw_mast = fetch_sheet_csv("master_list", spreadsheet_id=sheet_id)

    if hist_dfs:
        combined_hist = pd.concat(hist_dfs, ignore_index=True)
        time_col = "取得日時" if "取得日時" in combined_hist.columns else combined_hist.columns[0]
        code_col = "コード" if "コード" in combined_hist.columns else combined_hist.columns[3]
        combined_hist = combined_hist.drop_duplicates(subset=[time_col, code_col], keep="last")
        return combined_hist, (raw_mast if raw_mast is not None else pd.DataFrame())

    return pd.DataFrame(), (raw_mast if raw_mast is not None else pd.DataFrame())

def normalize_history(df: pd.DataFrame) -> pd.DataFrame:
    """旧形式(13列)・新形式(20列)の両形式を統一スキーマへ正規化"""
    if df is None or df.empty:
        return pd.DataFrame()
    d = df.copy()

    col_map = {
        "コード": "code", "銘柄名": "name", "取得日時": "timestamp",
        "権利年月": "rights_month", "残日数": "days_left", "残日数(D-N)": "days_left",
        "日興在庫": "nikko", "楽天在庫": "rakuten", "カブ在庫": "kabu",
        "SBI在庫": "sbi", "SBI信号": "sbi", "GMO在庫": "gmo", "GMO信号": "gmo",
        "松井信号": "matsui", "マネ信号": "monex",
        "売建上限": "gmo_limit", "資金(万)": "funds_man", "必要資金(万)": "funds_man",
        "優待価値": "yutai_value", "株価": "kabuka", "株数": "kabusu",
        "Rtn_楽天": "rtn_rakuten", "Rtn_日興": "rtn_nikko", "Rtn_SBI": "rtn_sbi"
    }
    for orig, standard in col_map.items():
        if orig in d.columns and standard not in d.columns:
            d[standard] = d[orig]

    if "code" in d.columns:
        d["code"] = d["code"].apply(fmt_code)

    for col in ["nikko", "rakuten", "kabu"]:
        if col in d.columns:
            d[col] = d[col].apply(parse_qty_safe)
        else:
            d[col] = None

    if "timestamp" in d.columns:
        d["dt"] = pd.to_datetime(d["timestamp"], errors="coerce")
        d = d.sort_values(by="dt", ascending=True)

    return d

def normalize_master(df: pd.DataFrame) -> pd.DataFrame:
    """master_list の正規化"""
    if df is None or df.empty:
        return pd.DataFrame()
    d = df.copy()
    col_map = {
        "監視": "watch", "優先度": "priority", "コード": "code", "銘柄名": "name",
        "優待内容": "yutai_content", "優待価値": "yutai_value", "優待価値(円)": "yutai_value",
        "必要資金": "funds_man", "必要資金(万)": "funds_man", "利回り(%)": "yield_pct",
        "総合利回り": "yield_pct", "売建上限": "gmo_limit", "権利月": "rights_month"
    }
    for orig, standard in col_map.items():
        if orig in d.columns and standard not in d.columns:
            d[standard] = d[orig]

    if "code" in d.columns:
        d["code"] = d["code"].apply(fmt_code)
    if "watch" in d.columns:
        d["watch"] = d["watch"].astype(str).str.upper().isin(["TRUE", "1", "YES"])
    else:
        d["watch"] = True

    return d

# ============================================================
# 5. 分析 & シグナル算出エンジン
# ============================================================
def analyze_stocks(
    df_hist: pd.DataFrame,
    df_mast: Optional[pd.DataFrame] = None,
    nikko_th: float = 10000.0,
    annual_rate: float = 0.011,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    if df_hist is None or df_hist.empty:
        return pd.DataFrame(), {}

    all_timestamps = df_hist["timestamp"].dropna().unique().tolist()
    latest_ts = all_timestamps[-1] if all_timestamps else ""
    prev_ts = all_timestamps[-2] if len(all_timestamps) >= 2 else None

    df_latest = df_hist[df_hist["timestamp"] == latest_ts].copy()
    df_prev = df_hist[df_hist["timestamp"] == prev_ts].copy() if prev_ts else pd.DataFrame()

    prev_map = {r["code"]: r for _, r in df_prev.iterrows()} if not df_prev.empty else {}
    mast_map = {r["code"]: r for _, r in df_mast.iterrows()} if df_mast is not None and not df_mast.empty else {}

    results: List[Dict[str, Any]] = []

    for _, row in df_latest.iterrows():
        code = row.get("code", "")
        name = row.get("name", "")
        prev_row = prev_map.get(code)
        m_row = mast_map.get(code, {})

        nikko_now = to_float(row.get("nikko"))
        rakuten_now = to_float(row.get("rakuten"))
        kabu_now = to_float(row.get("kabu"))
        sbi_now = str(row.get("rtn_sbi") or row.get("sbi") or "―").strip()
        gmo_now = str(row.get("gmo") or "―").strip()
        matsui_now = str(row.get("matsui") or "―").strip()
        monex_now = str(row.get("monex") or "―").strip()

        nikko_prev = to_float(prev_row.get("nikko")) if prev_row is not None else None
        rakuten_prev = to_float(prev_row.get("rakuten")) if prev_row is not None else None
        sbi_prev = str(prev_row.get("rtn_sbi") or prev_row.get("sbi") or "―").strip() if prev_row is not None else "―"

        # 1. 日興前日比
        nikko_diff = (nikko_now - nikko_prev) if (nikko_now is not None and nikko_prev is not None) else None

        # 2. SBI急変検知
        sbi_alert = "─"
        is_sbi_sudden_drop = False
        if prev_ts and sbi_prev in ("◎", "2") and sbi_now in ("▲", "1"):
            sbi_alert = "🚨急変(◎→▲)"
            is_sbi_sudden_drop = True
        elif prev_ts and sbi_prev in ("◎", "2") and sbi_now in ("×", "0", "残無"):
            sbi_alert = "💥瞬殺(◎→×)"
            is_sbi_sudden_drop = True
        elif sbi_now in ("▲", "1"):
            sbi_alert = "▲残少"
        elif sbi_now in ("×", "0", "残無"):
            sbi_alert = "⚪枯渇"

        # 3. 補充検知
        is_refill = False
        if prev_ts:
            was_zero = (nikko_prev is not None and nikko_prev == 0) or (rakuten_prev is not None and rakuten_prev == 0)
            now_has = (nikko_now is not None and nikko_now > 0) or (rakuten_now is not None and rakuten_now > 0)
            if was_zero and now_has:
                is_refill = True

        # 4. 合計在庫
        valid_qtys = [q for q in [nikko_now, rakuten_now, kabu_now] if q is not None]
        total_qty = sum(valid_qtys) if valid_qtys else None

        # 5. シグナル判定
        if is_sbi_sudden_drop and (nikko_now is not None and nikko_now <= nikko_th):
            signal = "🔴 今夜確保"
            signal_rank = 1
        elif total_qty is not None and total_qty == 0 and sbi_now in ("×", "0", "残無", "―"):
            signal = "⚪ 枯渇"
            signal_rank = 5
        elif total_qty is not None and 0 < total_qty < 1000:
            signal = "🔴 即確保"
            signal_rank = 2
        elif (nikko_now is not None and nikko_now < nikko_th) or (nikko_diff is not None and nikko_diff < -3000):
            signal = "🟡 要監視"
            signal_rank = 3
        elif nikko_now is not None and nikko_now >= nikko_th:
            signal = "🟢 待機可"
            signal_rank = 4
        else:
            signal = "⚪ 枯渇" if (total_qty == 0) else "🟡 要監視"
            signal_rank = 3

        # 6. コスト & 実質純利益 & 限界日
        yutai_val = to_float(row.get("yutai_value") or m_row.get("yutai_value"))
        funds_man = to_float(row.get("funds_man") or m_row.get("funds_man"))
        days_left_raw = str(row.get("days_left") or "10").replace("D-", "")
        try:
            d_n = int(days_left_raw)
        except ValueError:
            d_n = 10

        kabuka = to_float(row.get("kabuka")) or ((funds_man * 10000 / 100) if funds_man else None)
        kabusu = to_float(row.get("kabusu")) or 100.0

        cost = None
        net_profit = None
        limit_days = None

        if kabuka and kabusu and d_n:
            try:
                principal = kabuka * kabusu
                daily_cost = principal * annual_rate / 365.0
                cost = round(daily_cost * d_n)
                if yutai_val is not None:
                    net_profit = round(yutai_val - cost)
                    if daily_cost > 0:
                        limit_days = int(yutai_val / daily_cost)
            except Exception:
                pass

        watch = bool(m_row.get("watch", True))
        priority = m_row.get("priority", 1)

        results.append({
            "code": code,
            "name": name,
            "signal": signal,
            "signal_rank": signal_rank,
            "refill": "🔥補充" if is_refill else "",
            "is_refill": is_refill,
            "sbi_alert": sbi_alert,
            "is_sbi_drop": is_sbi_sudden_drop,
            "nikko_now": nikko_now,
            "nikko_prev": nikko_prev,
            "nikko_diff": nikko_diff,
            "rakuten_now": rakuten_now,
            "kabu_now": kabu_now,
            "sbi_now": sbi_now,
            "gmo_now": gmo_now,
            "matsui_now": matsui_now,
            "monex_now": monex_now,
            "total_qty": total_qty,
            "funds_man": funds_man,
            "yutai_value": yutai_val,
            "yutai_content": str(m_row.get("yutai_content") or ""),
            "yield_pct": to_float(m_row.get("yield_pct")),
            "net_profit": net_profit,
            "cost": cost,
            "limit_days": limit_days,
            "days_left": d_n,
            "rights_month": str(row.get("rights_month") or m_row.get("rights_month") or "2026-09"),
            "watch": watch,
            "priority": priority,
        })

    df_res = pd.DataFrame(results)
    stats = {
        "latest_ts": latest_ts,
        "prev_ts": prev_ts,
        "total_count": len(df_res),
        "tonight_count": sum(1 for r in results if r["signal"] == "🔴 今夜確保"),
        "refill_count": sum(1 for r in results if r["is_refill"]),
        "sbi_drop_count": sum(1 for r in results if r["is_sbi_drop"]),
        "empty_count": sum(1 for r in results if r["signal"] == "⚪ 枯渇"),
        "watch_count": sum(1 for r in results if r["watch"]),
    }
    return df_res, stats

# ============================================================
# 6. メインUIレンダリング (高密度・1画面情報集約)
# ============================================================
def main():
    # サイドバー設定 (最小限)
    with st.sidebar:
        st.markdown("### ⚙️ 設定")
        sheet_id = st.text_input("スプレッドシートID", value=DEFAULT_SPREADSHEET_ID)
        nikko_th = st.number_input("日興 警戒閾値 (株)", min_value=1000, max_value=100000, value=10000, step=1000)
        annual_rate = st.number_input("貸株年率", min_value=0.001, max_value=0.05, value=0.011, step=0.001, format="%.3f")
        st.caption(f"Yutai Cross {APP_VERSION}")

    # データロード
    raw_hist, raw_mast = load_data(sheet_id)
    if raw_hist is None or raw_hist.empty:
        st.error(f"⚠️ データを取得できませんでした (ID: `{sheet_id}`)。共有設定を確認してください。")
        return

    df_hist = normalize_history(raw_hist)
    df_mast = normalize_master(raw_mast) if raw_mast is not None else None
    df_analyzed, stats = analyze_stocks(df_hist, df_mast, nikko_th=nikko_th, annual_rate=annual_rate)

    # 1. コンパクト・トップステータスバー (1行集約)
    st.markdown(f"""
    <div class="top-bar">
        <div class="top-bar-title">
            <span>📈 優待クロス在庫トラッカー</span>
        </div>
        <div class="top-bar-tags">
            <span class="tag-badge tag-blue">権利月: 2026-09</span>
            <span class="tag-badge tag-green">最新: {stats.get('latest_ts', '―')}</span>
            {f"<span class='tag-badge tag-gray'>前回: {stats.get('prev_ts')}</span>" if stats.get('prev_ts') else ""}
            <span class="tag-badge tag-purple">追跡: {stats.get('total_count', 0)}銘柄</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 2. KPIミニバー (横並びチップ形式)
    t_cnt = stats.get('tonight_count', 0)
    r_cnt = stats.get('refill_count', 0)
    s_cnt = stats.get('sbi_drop_count', 0)
    w_cnt = stats.get('watch_count', 0)
    e_cnt = stats.get('empty_count', 0)

    st.markdown(f"""
    <div class="kpi-row">
        <div class="kpi-chip" style="{ 'border-color: #ef4444; background: #fef2f2;' if t_cnt > 0 else '' }">
            <span class="kpi-chip-label" style="{ 'color: #dc2626;' if t_cnt > 0 else '' }">🔴 今夜確保</span>
            <span class="kpi-chip-val" style="{ 'color: #dc2626;' if t_cnt > 0 else '' }">{t_cnt}</span>
        </div>
        <div class="kpi-chip" style="{ 'border-color: #ec4899; background: #fdf2f8;' if r_cnt > 0 else '' }">
            <span class="kpi-chip-label" style="{ 'color: #db2777;' if r_cnt > 0 else '' }">🔥 在庫補充</span>
            <span class="kpi-chip-val" style="{ 'color: #db2777;' if r_cnt > 0 else '' }">{r_cnt}</span>
        </div>
        <div class="kpi-chip">
            <span class="kpi-chip-label">🚨 SBI急変</span>
            <span class="kpi-chip-val">{s_cnt}</span>
        </div>
        <div class="kpi-chip">
            <span class="kpi-chip-label">⭐ 監視中</span>
            <span class="kpi-chip-val">{w_cnt}</span>
        </div>
        <div class="kpi-chip">
            <span class="kpi-chip-label">⚪ 枯渇</span>
            <span class="kpi-chip-val" style="color: #94a3b8;">{e_cnt}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 3. 検索 & フィルターバー (インライン超集約)
    f1, f2, f3, f4, f5 = st.columns([2.5, 2, 1.2, 1.2, 0.8])
    with f1:
        query = st.text_input("🔍 検索", placeholder="コード・銘柄名・優待内容", label_visibility="collapsed")
    with f2:
        signal_filter = st.multiselect(
            "シグナル絞込",
            options=["🔴 今夜確保", "🔥 補充", "🚨 SBI急変", "🔴 即確保", "🟡 要監視", "🟢 待機可", "⚪ 枯渇"],
            default=[],
            placeholder="全シグナル表示",
            label_visibility="collapsed"
        )
    with f3:
        only_watch = st.checkbox("監視中のみ", value=False)
    with f4:
        only_nikko = st.checkbox("日興あり", value=False)
    with f5:
        if st.button("🔄 更新", use_container_width=True):
            st.cache_data.clear()
            st.rerun()

    # フィルタリング適用
    filtered_df = df_analyzed.copy()
    if only_watch:
        filtered_df = filtered_df[filtered_df["watch"] == True]
    if only_nikko:
        filtered_df = filtered_df[filtered_df["nikko_now"].fillna(0) > 0]
    if signal_filter:
        cond = pd.Series([False] * len(filtered_df), index=filtered_df.index)
        if "🔴 今夜確保" in signal_filter: cond |= (filtered_df["signal"] == "🔴 今夜確保")
        if "🔥 補充" in signal_filter: cond |= (filtered_df["is_refill"] == True)
        if "🚨 SBI急変" in signal_filter: cond |= (filtered_df["is_sbi_drop"] == True)
        if "🔴 即確保" in signal_filter: cond |= (filtered_df["signal"] == "🔴 即確保")
        if "🟡 要監視" in signal_filter: cond |= (filtered_df["signal"] == "🟡 要監視")
        if "🟢 待機可" in signal_filter: cond |= (filtered_df["signal"] == "🟢 待機可")
        if "⚪ 枯渇" in signal_filter: cond |= (filtered_df["signal"] == "⚪ 枯渇")
        filtered_df = filtered_df[cond]
    if query:
        q = query.strip().lower()
        filtered_df = filtered_df[
            filtered_df["code"].astype(str).str.lower().str.contains(q) |
            filtered_df["name"].astype(str).str.lower().str.contains(q) |
            filtered_df["yutai_content"].astype(str).str.lower().str.contains(q)
        ]

    # メインタブ (実戦テーブルを最上部に最大化)
    tab1, tab2, tab3, tab4 = st.tabs([
        f"⚡ 実戦テーブル ({len(filtered_df)}件)",
        "📊 日興在庫推移",
        "🚨 急変・補充リスト",
        "⚙️ GitHub自動実行設定"
    ])

    # ----------------------------------------------------
    # TAB 1: 実戦テーブル (超高密度・全情報俯瞰)
    # ----------------------------------------------------
    with tab1:
        display_rows = []
        for _, r in filtered_df.iterrows():
            diff = r["nikko_diff"]
            if diff is None:
                diff_str = "―"
            elif diff > 0:
                diff_str = f"+{int(diff):,}"
            elif diff < 0:
                diff_str = f"{int(diff):,}"
            else:
                diff_str = "±0"

            display_rows.append({
                "コード": r["code"],
                "銘柄名": r["name"],
                "シグナル": r["signal"],
                "補充": r["refill"],
                "SBI変化": r["sbi_alert"],
                "日興": fmt_qty(r["nikko_now"]),
                "前日比": diff_str,
                "カブ": fmt_qty(r["kabu_now"]),
                "楽天": fmt_qty(r["rakuten_now"]),
                "SBI": r["sbi_now"],
                "GMO": r["gmo_now"],
                "純利益": fmt_int(r["net_profit"]),
                "限界日": f"D-{r['limit_days']}" if r["limit_days"] is not None else "―",
                "優待価値": fmt_int(r["yutai_value"]),
                "資金(万)": fmt_float(r["funds_man"], 1),
                "利回り": f"{fmt_float(r['yield_pct'], 1)}%" if r["yield_pct"] is not None else "―",
                "優待内容": r["yutai_content"][:35] if r["yutai_content"] else "―"
            })

        df_table = pd.DataFrame(display_rows)
        st.dataframe(
            df_table,
            use_container_width=True,
            hide_index=True,
            height=620,
            column_config={
                "コード": st.column_config.TextColumn("コード", width="small"),
                "銘柄名": st.column_config.TextColumn("銘柄名", width="medium"),
                "シグナル": st.column_config.TextColumn("シグナル", width="small"),
                "補充": st.column_config.TextColumn("補充", width="small"),
                "SBI変化": st.column_config.TextColumn("SBI変化", width="small"),
                "日興": st.column_config.TextColumn("日興", width="small"),
                "前日比": st.column_config.TextColumn("前日比", width="small"),
                "カブ": st.column_config.TextColumn("カブ", width="small"),
                "楽天": st.column_config.TextColumn("楽天", width="small"),
                "SBI": st.column_config.TextColumn("SBI", width="small"),
                "GMO": st.column_config.TextColumn("GMO", width="small"),
                "純利益": st.column_config.TextColumn("純利益(円)", width="small"),
                "限界日": st.column_config.TextColumn("限界日", width="small"),
                "優待価値": st.column_config.TextColumn("優待(円)", width="small"),
                "資金(万)": st.column_config.TextColumn("資金(万)", width="small"),
                "利回り": st.column_config.TextColumn("利回り", width="small"),
                "優待内容": st.column_config.TextColumn("優待内容", width="large"),
            }
        )

        # 選択銘柄クイック詳細
        if not filtered_df.empty:
            st.markdown("<div style='height: 4px;'></div>", unsafe_allow_html=True)
            sel_c1, sel_c2 = st.columns([2, 5])
            with sel_c1:
                target_code = st.selectbox(
                    "銘柄詳細・推移確認",
                    options=filtered_df["code"].tolist(),
                    format_func=lambda c: f"{c} {filtered_df[filtered_df['code']==c]['name'].values[0] if len(filtered_df[filtered_df['code']==c])>0 else ''}"
                )
            with sel_c2:
                if target_code:
                    st_sub = df_hist[df_hist["code"] == target_code]
                    if len(st_sub) > 1:
                        chart = alt.Chart(st_sub).mark_line(point=True).encode(
                            x=alt.X("timestamp:N", title=None),
                            y=alt.Y("nikko:Q", title="日興在庫"),
                            tooltip=["timestamp", "nikko", "rakuten", "kabu"]
                        ).properties(height=110)
                        st.altair_chart(chart, use_container_width=True)

    # ----------------------------------------------------
    # TAB 2: 日興在庫推移
    # ----------------------------------------------------
    with tab2:
        st.markdown("##### 📈 日興在庫 推移トラッキング")
        codes_to_plot = st.multiselect(
            "表示銘柄 (複数可)",
            options=df_analyzed["code"].tolist(),
            default=df_analyzed[df_analyzed["nikko_now"].fillna(0) > 0]["code"].head(6).tolist(),
            format_func=lambda c: f"{c} {df_analyzed[df_analyzed['code']==c]['name'].values[0] if len(df_analyzed[df_analyzed['code']==c])>0 else ''}"
        )
        if codes_to_plot:
            sub = df_hist[df_hist["code"].isin(codes_to_plot)]
            if not sub.empty:
                chart_multi = alt.Chart(sub).mark_line(point=True).encode(
                    x=alt.X("timestamp:N", title="取得日時"),
                    y=alt.Y("nikko:Q", title="日興在庫 (株)"),
                    color=alt.Color("name:N", title="銘柄名"),
                    tooltip=["name", "code", "timestamp", "nikko", "rakuten"]
                ).properties(height=380)
                st.altair_chart(chart_multi, use_container_width=True)

    # ----------------------------------------------------
    # TAB 3: 急変・補充リスト
    # ----------------------------------------------------
    with tab3:
        ca1, ca2 = st.columns(2)
        with ca1:
            st.markdown("##### 🚨 SBI急変・瞬殺")
            df_sbi = df_analyzed[df_analyzed["is_sbi_drop"] == True]
            if not df_sbi.empty:
                st.dataframe(df_sbi[["code", "name", "sbi_alert", "nikko_now", "rakuten_now"]], hide_index=True)
            else:
                st.caption("現在、急変銘柄はありません。")
        with ca2:
            st.markdown("##### 🔥 在庫補充検知")
            df_ref = df_analyzed[df_analyzed["is_refill"] == True]
            if not df_ref.empty:
                st.dataframe(df_ref[["code", "name", "refill", "nikko_now", "rakuten_now"]], hide_index=True)
            else:
                st.caption("現在、直近の補充はありません。")

    # ----------------------------------------------------
    # TAB 4: GitHub自動実行設定ガイド
    # ----------------------------------------------------
    with tab4:
        st.markdown("""
        ##### 💡 GitHub Actionsだけで完全サーバーレス化する方針
        
        現在、データはGoogleスプレッドシート（GAS）に蓄積していますが、
        **GitHub Actions でPythonスクレイパーを平日17:00/20:00に定期実行し、CSVを本リポジトリに自動保存**すれば、
        **GoogleスプレッドシートもGASも不要で、GitHub単体で完全自動化**が可能です！

        ###### 移行手順（希望する場合）:
        1. GitHubリポジトリ（[tekkame/yutai-cross-dashboard](https://github.com/tekkame/yutai-cross-dashboard)）の画面を開く
        2. 「Add file」 > 「Create new file」をクリック
        3. ファイル名に `.github/workflows/daily_update.yml` と入力
        4. 以下のYAMLを貼り付けて「Commit changes」をクリック
        
        ```yaml
        name: daily_scraper
        on:
          schedule:
            - cron: '0 8,11 * * 1-5'  # 平日JST 17:00 / 20:00
          workflow_dispatch:
        permissions:
          contents: write
        jobs:
          scrape:
            runs-on: ubuntu-latest
            steps:
              - uses: actions/checkout@v4
              - uses: actions/setup-python@v5
                with:
                  python-version: '3.11'
              - run: pip install -r requirements.txt
              - run: python main.py --dry-run --out-dir out
              - name: Commit and Push
                run: |
                  git config user.name "github-actions[bot]"
                  git config user.email "github-actions[bot]@users.noreply.github.com"
                  git add out/
                  git commit -m "Auto update stock data [skip ci]" || exit 0
                  git push
        ```
        これだけで、自宅PCの電源OFFでもGitHubが自動スクレイピングし、Streamlit Cloudが最新データを即時反映します。
        """)

if __name__ == "__main__":
    main()
