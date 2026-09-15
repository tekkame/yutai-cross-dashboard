# -*- coding: utf-8 -*-
"""
app.py - 株主優待クロス在庫トラッカー ＆ 実戦意思決定ダッシュボード
【GitHub Actions 1クリック即時スクレイピング ＆ 優待・残数集中レイアウト完全統合版】
- 🚀 GITHUB_TOKEN による画面からの完全オンデマンド・スクレイピング起動
- 🎁 優待内容・優待額・取得資金の左側集中配置
- 📊 証券各社（日興・前日比・SBI・楽天・カブ・GMO）残数の1箇所集中集約
- ⚡ 最左列の監視チェックボックス直接操作（0.05秒高速保存・フリーズゼロ）
"""

from __future__ import annotations

import datetime as dt
import io
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

# ============================================================
# 1. ページ初期設定 & 超高密度CSS
# ============================================================
st.set_page_config(
    page_title="優待クロス在庫トラッカー",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

ULTRA_COMPACT_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Noto+Sans+JP:wght@400;500;700&display=swap');

html, body, [class*="css"] {
    font-family: 'Noto Sans JP', -apple-system, BlinkMacSystemFont, sans-serif;
    font-size: 12.5px;
    letter-spacing: -0.015em;
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

.alert-banner-danger {
    background: #450a0a;
    border: 1px solid #dc2626;
    color: #fecaca;
    padding: 0.35rem 0.75rem;
    border-radius: 6px;
    margin-bottom: 0.35rem;
    font-size: 12px;
    font-weight: 600;
}

.alert-banner-safe {
    background: #022c22;
    border: 1px solid #059669;
    color: #a7f3d0;
    padding: 0.25rem 0.65rem;
    border-radius: 6px;
    margin-bottom: 0.35rem;
    font-size: 11.5px;
}

.alert-banner-info {
    background: #0c4a6e;
    border: 1px solid #0284c7;
    color: #e0f2fe;
    padding: 0.4rem 0.8rem;
    border-radius: 6px;
    margin-bottom: 0.35rem;
    font-size: 12px;
}

.kpi-row {
    display: flex;
    gap: 0.35rem;
    margin-bottom: 0.4rem;
    flex-wrap: wrap;
}

.kpi-card {
    flex: 1;
    min-width: 110px;
    background: #ffffff;
    border: 1px solid #cbd5e1;
    border-radius: 5px;
    padding: 0.25rem 0.55rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
}

@media (prefers-color-scheme: dark) {
    .kpi-card {
        background: #111827;
        border-color: #374151;
    }
}

.kpi-title {
    font-size: 11px;
    font-weight: 600;
    color: #64748b;
}

.kpi-num {
    font-size: 14px;
    font-weight: 700;
    font-family: 'JetBrains Mono', monospace;
}

div[data-testid="stVerticalBlock"] > div {
    gap: 0.2rem !important;
}

.stTabs [data-baseweb="tab-list"] {
    gap: 0.25rem;
    margin-bottom: 0.25rem;
}

.stTabs [data-baseweb="tab"] {
    padding: 0.25rem 0.65rem !important;
    font-size: 11.5px !important;
    font-weight: 600 !important;
}

div.stButton > button {
    padding: 0.2rem 0.55rem !important;
    font-size: 11.5px !important;
    border-radius: 4px !important;
    min-height: auto !important;
}

div[data-baseweb="input"] input {
    font-size: 11.5px !important;
    padding: 0.2rem 0.45rem !important;
}

div[data-baseweb="select"] {
    font-size: 11.5px !important;
}

div[data-testid="stDataFrame"] {
    font-size: 11px !important;
}
</style>
"""
st.markdown(ULTRA_COMPACT_CSS, unsafe_allow_html=True)

# ============================================================
# 2. 定数 & ファイルパス
# ============================================================
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
WATCHLIST_FILE = DATA_DIR / "watchlist.json"
DEFAULT_SPREADSHEET_ID = "175sKtMVVp6IgqrzLcRtO5tX7t-wiEKQrrfagfRoH1gM"
DEFAULT_GAS_API_URL = "https://script.google.com/macros/s/AKfycbwKopml2DIZcM_92GhuyP9R06MzqtyaYCda8STyWSiPz46vnfZfpnmyoUy8W5bI681FAQ/exec"
APP_VERSION = "v5.0 (On-Demand Dispatch & Concentrated UX)"

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
    if f is None: return "―"
    if f >= 9999990: return "大量"
    if f >= 10000: return f"{f/10000:.1f}万"
    return f"{int(f):,}"

def parse_qty_safe(v: Any) -> Optional[float]:
    if v is None or pd.isna(v): return None
    if isinstance(v, (int, float)):
        val = float(v)
        return None if np.isnan(val) else val
    s = str(v).strip().replace(",", "").replace(" ", "")
    if s in ("", "-", "―", "ー", "null", "None", "取扱なし"): return None
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
    if v is None or (not isinstance(v, str) and pd.isna(v)): return "―"
    s = str(v).strip()
    if s in ("", "-", "―", "ー", "null", "None", "nan"): return "―"
    if s in ("2", "2.0", "◎"): return "◎"
    if s in ("1", "1.0", "▲"): return "▲"
    if s in ("0", "0.0", "×", "✕"): return "×"
    return s

# ============================================================
# 4. GitHub Actions 1クリック起動エンジン
# ============================================================
def trigger_github_workflow(token: str, repo: str, ref: str = "main") -> Tuple[bool, str]:
    """GitHub API を叩いて、クラウド上で本物のスクレイピングを実行させる"""
    if not token or not repo:
        return False, "GITHUB_TOKEN または GITHUB_REPO が Streamlit Secrets に未設定です。"

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "User-Agent": "Streamlit-Yutai-Dashboard"
    }

    # 1. ワークフロー一覧を取得して対象を探す
    url_list = f"https://api.github.com/repos/{repo}/actions/workflows"
    req_list = urllib.request.Request(url_list, headers=headers)
    try:
        with urllib.request.urlopen(req_list, timeout=6) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            workflows = data.get("workflows", [])
    except urllib.error.HTTPError as e:
        return False, f"GitHub認証エラー ({e.code}): トークン権限（repo, workflow）を確認してください。"
    except Exception as e:
        return False, f"通信エラー: {e}"

    if not workflows:
        return False, "リポジトリ内に実行可能なワークフローが見つかりません。"

    # スクレイピング用ワークフローを特定
    target_wf = None
    for wf in workflows:
        path = wf.get("path", "").lower()
        name = wf.get("name", "").lower()
        if any(k in path or k in name for k in ["scrape", "stock", "daily", "inventory", "main"]):
            target_wf = wf
            break
    if not target_wf:
        target_wf = workflows[0]

    wf_id = target_wf.get("id")
    wf_name = target_wf.get("name", "Scraper")

    # 2. workflow_dispatch を送信
    url_dispatch = f"https://api.github.com/repos/{repo}/actions/workflows/{wf_id}/dispatches"
    payload = json.dumps({"ref": ref}).encode("utf-8")
    req_dispatch = urllib.request.Request(
        url_dispatch,
        data=payload,
        headers={**headers, "Content-Type": "application/json"},
        method="POST"
    )
    try:
        with urllib.request.urlopen(req_dispatch, timeout=6) as resp:
            if resp.status in (204, 200, 201):
                return True, f"「{wf_name}」を起動しました！ クラウド上で巡回スクレイピングを開始します。"
            return False, f"起動ステータス: {resp.status}"
    except urllib.error.HTTPError as e:
        return False, f"ディスパッチ失敗 ({e.code}): ymlファイルに `on: workflow_dispatch` が記述されているか確認してください。"
    except Exception as e:
        return False, f"送信エラー: {e}"

# ============================================================
# 5. ウォッチリスト管理 & GASリアルタイム単一行同期
# ============================================================
def load_watchlist() -> List[str]:
    if WATCHLIST_FILE.exists():
        try:
            codes = json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
            if isinstance(codes, list):
                return [fmt_code(c) for c in codes]
        except Exception: pass
    return ["9831", "8136", "7513", "3679", "7458", "3778", "7419", "3844", "3167", "5262", "9201", "9202"]

def save_watchlist(codes: List[str]):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    clean_codes = sorted(list(set(fmt_code(c) for c in codes if c)))
    WATCHLIST_FILE.write_text(json.dumps(clean_codes, ensure_ascii=False, indent=2), encoding="utf-8")

def sync_single_to_google_sheet(gas_url: str, code: str, watch: bool, status: str = "未確保") -> bool:
    if not gas_url or not gas_url.startswith("https://script.google.com"): return False
    try:
        payload = json.dumps({"code": code, "watch": watch, "status": status}).encode("utf-8")
        req = urllib.request.Request(
            gas_url, data=payload, headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            return resp.status in (200, 302)
    except Exception:
        return False

# ============================================================
# 6. データローダー（Google Sheets ＆ ローカルCSV 完全統合）
# ============================================================
@st.cache_data(ttl=30, show_spinner=False)
def fetch_sheet_csv(sheet_name: str, spreadsheet_id: str = DEFAULT_SPREADSHEET_ID) -> Optional[pd.DataFrame]:
    if not spreadsheet_id: return None
    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/gviz/tq?tqx=out:csv&sheet={urllib.parse.quote(sheet_name)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=4) as resp:
            return pd.read_csv(io.BytesIO(resp.read()))
    except Exception:
        return None

@st.cache_data(ttl=30, show_spinner=False)
def load_all_combined_data(spreadsheet_id: str = DEFAULT_SPREADSHEET_ID) -> Tuple[pd.DataFrame, pd.DataFrame, str]:
    hist_dfs = []
    latest_master = pd.DataFrame()
    data_source_msg = "ローカルCSV"

    if DATA_DIR.exists():
        h_files = sorted([DATA_DIR / f for f in os.listdir(DATA_DIR) if f.startswith("history_") and f.endswith(".csv")])
        for hf in h_files:
            try:
                df_tmp = pd.read_csv(hf)
                if not df_tmp.empty: hist_dfs.append(df_tmp)
            except Exception: pass

        m_files = sorted([DATA_DIR / f for f in os.listdir(DATA_DIR) if f.startswith("master_") and f.endswith(".csv")], reverse=True)
        if m_files:
            try: latest_master = pd.read_csv(m_files[0])
            except Exception: pass

    sheet_hist = fetch_sheet_csv("raw_history", spreadsheet_id=spreadsheet_id)
    if sheet_hist is not None and not sheet_hist.empty:
        hist_dfs.append(sheet_hist)
        data_source_msg = "Googleスプレッドシート連携中"

    sheet_mast = fetch_sheet_csv("master_list", spreadsheet_id=spreadsheet_id)
    if sheet_mast is not None and not sheet_mast.empty:
        latest_master = sheet_mast

    if hist_dfs:
        combined_hist = pd.concat(hist_dfs, ignore_index=True)
        t_col = "取得日時" if "取得日時" in combined_hist.columns else combined_hist.columns[0]
        c_col = "コード" if "コード" in combined_hist.columns else combined_hist.columns
        combined_hist = combined_hist.drop_duplicates(subset=[t_col, c_col], keep="last")
        return combined_hist, latest_master, data_source_msg

    return pd.DataFrame(), pd.DataFrame(), "データなし"

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
    if df is None or df.empty: return pd.DataFrame()
    d = df.copy()
    col_map = {
        "コード": "code", "銘柄名": "name", "優待内容": "yutai_content",
        "優待価値": "yutai_value", "優待価値(円)": "yutai_value",
        "必要資金": "funds_man", "必要資金(万)": "funds_man", "資金万円": "funds_man",
        "利回り(%)": "yield_pct", "総合利回り": "yield_pct", "売建上限": "gmo_limit"
    }
    for orig, standard in col_map.items():
        if orig in d.columns and standard not in d.columns:
            d[standard] = d[orig]

    if "code" in d.columns:
        d["code"] = d["code"].apply(fmt_code)
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
) -> Tuple[pd.DataFrame, Dict[str, Any], List[str]]:
    if df_hist is None or df_hist.empty:
        return pd.DataFrame(), {}, []

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

        sbi_now_raw = str(row.get("rtn_sbi") or row.get("sbi") or "―").strip()
        sbi_now = fmt_signal(sbi_now_raw)

        gmo_now = str(row.get("gmo") or m_row.get("gmo_limit") or "―").strip()
        matsui_now = str(row.get("matsui") or "―").strip()
        monex_now = str(row.get("monex") or "―").strip()

        nikko_prev = to_float(prev_row.get("nikko")) if prev_row is not None else None
        rakuten_prev = to_float(prev_row.get("rakuten")) if prev_row is not None else None

        sbi_prev_raw = str(prev_row.get("rtn_sbi") or prev_row.get("sbi") or "―").strip() if prev_row is not None else "―"
        sbi_prev = fmt_signal(sbi_prev_raw)

        # 日興前日比
        nikko_diff = (nikko_now - nikko_prev) if (nikko_now is not None and nikko_prev is not None) else None

        # SBI急変検知
        is_sbi_sudden_drop = False
        if prev_ts and sbi_prev != "―" and sbi_now != "―":
            if sbi_prev == "◎" and sbi_now == "▲":
                sbi_change = "🚨急変(◎→▲)"
                is_sbi_sudden_drop = True
            elif sbi_prev == "◎" and sbi_now == "×":
                sbi_change = "💥瞬殺(◎→×)"
                is_sbi_sudden_drop = True
            elif sbi_prev != sbi_now:
                sbi_change = f"{sbi_prev}→{sbi_now}"
            else:
                sbi_change = f"{sbi_now}(維持)"
        else:
            sbi_change = sbi_now if sbi_now != "―" else "―"

        # 補充検知
        is_refill = False
        if prev_ts:
            was_zero = (nikko_prev is not None and nikko_prev == 0) or (rakuten_prev is not None and rakuten_prev == 0)
            now_has = (nikko_now is not None and nikko_now > 0) or (rakuten_now is not None and rakuten_now > 0)
            if was_zero and now_has:
                is_refill = True

        valid_qtys = [q for q in [nikko_now, rakuten_now, kabu_now] if q is not None]
        total_qty = sum(valid_qtys) if valid_qtys else None

        # シグナル判定
        if is_sbi_sudden_drop and (nikko_now is not None and nikko_now <= nikko_th):
            signal = "🔴 今夜確保"
            signal_rank = 1
        elif total_qty is not None and total_qty == 0 and sbi_now in ("×", "―"):
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

        # 優待情報・コスト算出
        yutai_val = to_float(m_row.get("yutai_value") or row.get("yutai_value"))
        funds_man = to_float(m_row.get("funds_man") or row.get("funds_man"))
        funds_yen = int(round(funds_man * 10000)) if funds_man is not None and funds_man > 0 else 99999999

        days_left_raw = str(row.get("days_left") or "10").replace("D-", "")
        try: d_n = int(days_left_raw)
        except ValueError: d_n = 10

        stock_price = to_float(row.get("stock_price") or m_row.get("stock_price"))
        if stock_price is None and funds_man:
            stock_price = round(funds_man * 10000 / 100.0)

        net_profit = None
        limit_days_int = None

        if funds_yen < 99999990 and d_n:
            try:
                daily_cost = funds_yen * annual_rate / 365.0
                cost = round(daily_cost * d_n)
                if yutai_val is not None:
                    net_profit = int(round(yutai_val - cost))
                    if daily_cost > 0:
                        limit_days_int = int(round(yutai_val / daily_cost))
            except Exception: pass

        is_watched = (code in watchlist)

        results.append({
            "watch": is_watched,
            "code": code,
            "name": name,
            "stock_price": to_int(stock_price),
            "funds_yen": funds_yen,
            "signal": signal,
            "signal_rank": signal_rank,
            "sbi_change": sbi_change,
            "is_sbi_drop": is_sbi_sudden_drop,
            "refill": "🔥補充" if is_refill else "",
            "is_refill": is_refill,
            "nikko_now": nikko_now,
            "nikko_diff": nikko_diff,
            "rakuten_now": rakuten_now,
            "kabu_now": kabu_now,
            "sbi_now": sbi_now,
            "gmo_now": gmo_now,
            "matsui_now": matsui_now,
            "monex_now": monex_now,
            "total_qty": total_qty,
            "funds_man": funds_man,
            "yutai_value": to_int(yutai_val),
            "yutai_content": str(m_row.get("yutai_content") or row.get("yutai_content") or ""),
            "yield_pct": to_float(m_row.get("yield_pct") or row.get("yield_pct")),
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
    if "watchlist" not in st.session_state:
        st.session_state["watchlist"] = load_watchlist()

    # Secrets から GitHub 設定を安全に読込
    gh_token = st.secrets.get("GITHUB_TOKEN", "")
    gh_repo = st.secrets.get("GITHUB_REPO", "tekkame/yutai-cross-dashboard")

    # サイドバー
    with st.sidebar:
        st.markdown("### ⚙️ ターミナル設定")
        sheet_id = st.text_input("スプレッドシートID", value=DEFAULT_SPREADSHEET_ID)
        gas_api_url = st.text_input("GAS WebApp同期URL", value=DEFAULT_GAS_API_URL)
        nikko_th = st.number_input("日興 警戒閾値 (株)", min_value=1000, max_value=100000, value=10000, step=1000)
        annual_rate = st.number_input("貸株年率 (日興=1.4%)", min_value=0.001, max_value=0.05, value=0.014, step=0.001, format="%.3f")
        st.caption(f"GitHub: `{gh_repo}` ({'認証設定済 ✅' if gh_token else 'Token未設定 ⚠️'})")
        st.caption(f"Yutai Cross {APP_VERSION}")

    # データ読み込み
    raw_hist, raw_mast, data_source_msg = load_all_combined_data(spreadsheet_id=sheet_id)
    if raw_hist is None or raw_hist.empty:
        st.warning("⚠️ 在庫データがありません。スプレッドシートIDを確認するか、右上の「🔄 画面再読込」を実行してください。")
        if st.button("🔄 画面再読込", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
        return

    df_hist = normalize_history(raw_hist)
    df_mast = normalize_master(raw_mast)
    df_analyzed, stats, all_timestamps = analyze_stocks(
        df_hist, df_mast,
        watchlist=st.session_state["watchlist"],
        nikko_th=nikko_th,
        annual_rate=annual_rate
    )

    # 1. ナビステータスバー
    st.markdown(f"""
    <div class="status-bar">
        <div class="status-bar-title">
            <span>⚡ <b>優待クロス在庫トラッカー</b> [9月優待]</span>
        </div>
        <div class="status-tags">
            <span class="tag tag-green">{data_source_msg}</span>
            <span class="tag tag-blue">最新取得: {stats.get('latest_ts', '―')}</span>
            <span class="tag tag-gray">履歴: {len(all_timestamps)}回分</span>
            <span class="tag tag-amber">追跡: {stats.get('total_count', 0)}銘柄</span>
            <span class="tag tag-purple">監視中: {stats.get('watch_count', 0)}件</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 2. 緊急アラート速報バナー
    tonight_df = df_analyzed[df_analyzed["signal"] == "🔴 今夜確保"]
    sbi_drop_df = df_analyzed[df_analyzed["is_sbi_drop"] == True]

    if not tonight_df.empty:
        items = " / ".join([f"<b>{r['code']} {r['name']}</b> ({r['sbi_change']}, 日興:{fmt_qty(r['nikko_now'])})" for _, r in tonight_df.iterrows()])
        st.markdown(f"""
        <div class="alert-banner-danger">
            <span>🚨 <b>【最優先・今夜確保】</b> SBI急変＆日興残少: {items}</span>
        </div>
        """, unsafe_allow_html=True)
    elif not sbi_drop_df.empty:
        items = " / ".join([f"<b>{r['code']} {r['name']}</b> ({r['sbi_change']})" for _, r in sbi_drop_df.iterrows()])
        st.markdown(f"""
        <div class="alert-banner-danger">
            <span>🚨 <b>【SBI急変検知】</b> {items}</span>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="alert-banner-safe">
            <span>✅ <b>急変なし:</b> SBI証券の在庫急変（◎→▲/◎→×）は検知されていません。待機可能です。</span>
        </div>
        """, unsafe_allow_html=True)

    # 3. KPIミニチップ
    t_cnt = stats.get('tonight_count', 0)
    s_cnt = stats.get('sbi_drop_count', 0)
    r_cnt = stats.get('refill_count', 0)
    w_cnt = stats.get('watch_count', 0)
    e_cnt = stats.get('empty_count', 0)

    st.markdown(f"""
    <div class="kpi-row">
        <div class="kpi-card" style="{ 'border-color: #ef4444; background: #450a0a;' if t_cnt > 0 else '' }">
            <span class="kpi-title" style="{ 'color: #f87171;' if t_cnt > 0 else '' }">🔴 今夜確保</span>
            <span class="kpi-num" style="{ 'color: #f87171;' if t_cnt > 0 else '' }">{t_cnt}</span>
        </div>
        <div class="kpi-card" style="{ 'border-color: #f97316; background: #431407;' if s_cnt > 0 else '' }">
            <span class="kpi-title" style="{ 'color: #fb923c;' if s_cnt > 0 else '' }">🚨 SBI急変</span>
            <span class="kpi-num" style="{ 'color: #fb923c;' if s_cnt > 0 else '' }">{s_cnt}</span>
        </div>
        <div class="kpi-card" style="{ 'border-color: #ec4899; background: #500724;' if r_cnt > 0 else '' }">
            <span class="kpi-title" style="{ 'color: #f472b6;' if r_cnt > 0 else '' }">🔥 在庫補充</span>
            <span class="kpi-num" style="{ 'color: #f472b6;' if r_cnt > 0 else '' }">{r_cnt}</span>
        </div>
        <div class="kpi-card">
            <span class="kpi-title">⭐ 監視銘柄</span>
            <span class="kpi-num" style="color: #fbbf24;">{w_cnt}</span>
        </div>
        <div class="kpi-card">
            <span class="kpi-title">⚪ 枯渇銘柄</span>
            <span class="kpi-num" style="color: #94a3b8;">{e_cnt}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 4. 操作＆スクレイピング起動バー
    c_f1, c_f2, c_f3, c_f4, c_f5, c_f6, c_f7 = st.columns([2.0, 1.4, 0.9, 0.9, 1.6, 1.1, 1.5])
    with c_f1:
        query = st.text_input("検索", placeholder="🔍 コード・銘柄名・優待内容 (例: 3167, ヤマダ, ギフト)", label_visibility="collapsed")
    with c_f2:
        signal_filter = st.multiselect(
            "シグナル絞込",
            options=["🔴 今夜確保", "🔥 補充", "🚨 SBI急変", "🔴 即確保", "🟡 要監視", "🟢 待機可", "⚪ 枯渇"],
            default=[],
            placeholder="全シグナル表示",
            label_visibility="collapsed"
        )
    with c_f3:
        only_watch = st.checkbox("⭐ 監視のみ", value=False)
    with c_f4:
        only_nikko = st.checkbox("日興あり", value=False)
    with c_f5:
        sort_mode = st.selectbox(
            "並び替え",
            options=[
                "💴 取得資金が安い順 (〜10万, 20万...)",
                "💰 取得資金が高い順",
                "⚡ シグナル優先 (今夜確保→急変)",
                "🎁 実質純利益が高い順",
                "📈 利回りが高い順",
                "📉 日興在庫が多い順"
            ],
            index=0,
            label_visibility="collapsed"
        )
    with c_f6:
        if st.button("🔄 画面再読込", use_container_width=True, help="最新のCSV/スプレッドシートデータを画面に反映（0.5秒）"):
            st.cache_data.clear()
            st.toast("⚡ 最新データを画面に反映しました！")
            st.rerun()
    with c_f7:
        # 【新機能】GitHub Actions を1クリックで即時起動させるボタン
        if st.button("🚀 最新スクレイピング", use_container_width=True, help="クラウドサーバーを起動して両サイトを今すぐ巡回（1〜2分）"):
            with st.spinner("GitHub Actions にスクレイピング開始を要請中..."):
                ok, msg = trigger_github_workflow(token=gh_token, repo=gh_repo)
            if ok:
                st.session_state["dispatch_msg"] = msg
                st.rerun()
            else:
                st.error(msg)

    # スクレイピング起動中の案内バナー
    if "dispatch_msg" in st.session_state:
        st.markdown(f"""
        <div class="alert-banner-info">
            <span>🚀 <b>{st.session_state['dispatch_msg']}</b><br>
            👉 <a href="https://github.com/{gh_repo}/actions" target="_blank" style="color: #67e8f9; text-decoration: underline; font-weight: bold;">ここをクリックして GitHub Actions の進行状況を確認する</a><br>
            ※巡回（約1〜2分）が完了したら、左隣の「🔄 画面再読込」ボタンを押してください。</span>
        </div>
        """, unsafe_allow_html=True)

    # フィルタリング
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

    # ソート順
    if "取得資金が安い順" in sort_mode:
        filtered_df = filtered_df.sort_values(by="funds_yen", ascending=True)
    elif "取得資金が高い順" in sort_mode:
        filtered_df = filtered_df.sort_values(by="funds_yen", ascending=False)
    elif "実質純利益が高い順" in sort_mode:
        filtered_df = filtered_df.sort_values(by="net_profit", ascending=False, na_position="last")
    elif "利回りが高い順" in sort_mode:
        filtered_df = filtered_df.sort_values(by="yield_pct", ascending=False, na_position="last")
    elif "日興在庫が多い順" in sort_mode:
        filtered_df = filtered_df.sort_values(by="nikko_now", ascending=False, na_position="last")
    else:
        filtered_df = filtered_df.sort_values(by=["signal_rank", "nikko_now"], ascending=[True, True])

    # タブ
    tab1, tab2, tab3 = st.tabs([
        f"⚡ 実戦ボード ({len(filtered_df)}件)",
        f"📊 日時別 在庫時系列 (全{len(all_timestamps)}回分)",
        "💡 運用ガイド ＆ 自動実行"
    ])

    # ----------------------------------------------------
    # TAB 1: 実戦ボード (優待情報 ＆ 各社残数を完全集中配置)
    # ----------------------------------------------------
    with tab1:
        display_rows = []
        for _, r in filtered_df.iterrows():
            diff = r["nikko_diff"]
            if diff is None: diff_str = "―"
            elif diff > 0: diff_str = f"+{int(diff):,}"
            elif diff < 0: diff_str = f"{int(diff):,}"
            else: diff_str = "±0"

            limit_str = f"D-{r['limit_days_int']}" if r["limit_days_int"] is not None else "―"
            p_yen = int(r["funds_yen"]) if r["funds_yen"] < 99999990 else None

            # 人間の判断動線に沿った集中配置：
            # [監視] [コード] [銘柄名] -> [優待内容] [優待額] [必要資金] -> [意思決定] [SBI急変] -> [各社残数] -> [純利益] [期限]
            display_rows.append({
                "監視": bool(r.get("watch", False)),
                "コード": str(r.get("code", "")),
                "銘柄名": str(r.get("name", "")),
                "優待内容": str(r.get("yutai_content", "")[:32]),
                "優待価値": r.get("yutai_value"),
                "取得資金": p_yen,
                "意思決定": str(r.get("signal", "")),
                "SBI急変": str(r.get("sbi_change", "―")),
                "日興": fmt_qty(r.get("nikko_now")),
                "前日比": diff_str,
                "SBI": str(r.get("sbi_now", "―")),
                "楽天": fmt_qty(r.get("rakuten_now")),
                "カブ": fmt_qty(r.get("kabu_now")),
                "GMO": str(r.get("gmo_now", "―")),
                "実質純利益": r.get("net_profit"),
                "限界日": limit_str,
                "利回り": f"{r['yield_pct']:.1f}%" if r.get("yield_pct") is not None else "―",
            })

        df_table = pd.DataFrame(display_rows)

        if not df_table.empty:
            edited_table = st.data_editor(
                df_table,
                use_container_width=True,
                hide_index=True,
                height=560,
                column_config={
                    "監視": st.column_config.CheckboxColumn("監視", help="クリックで即座に監視リストへ保存", width="small"),
                    "コード": st.column_config.TextColumn("コード", width="small", disabled=True),
                    "銘柄名": st.column_config.TextColumn("銘柄名", width="medium", disabled=True),
                    # ★優待情報集中エリア（左側）
                    "優待内容": st.column_config.TextColumn("🎁 優待内容", width="large", disabled=True, help="株主優待の品目・内容"),
                    "優待価値": st.column_config.NumberColumn("優待額", format="¥%,d", width="small", disabled=True),
                    "取得資金": st.column_config.NumberColumn("必要資金", format="¥%,d", width="medium", disabled=True),
                    # 意思決定
                    "意思決定": st.column_config.TextColumn("意思決定", width="small", disabled=True),
                    "SBI急変": st.column_config.TextColumn("SBI急変", width="small", disabled=True),
                    # ★各社残数集中エリア（中央）
                    "日興": st.column_config.TextColumn("日興在庫", width="small", disabled=True),
                    "前日比": st.column_config.TextColumn("前日比", width="small", disabled=True),
                    "SBI": st.column_config.TextColumn("SBI", width="small", disabled=True),
                    "楽天": st.column_config.TextColumn("楽天", width="small", disabled=True),
                    "カブ": st.column_config.TextColumn("カブ", width="small", disabled=True),
                    "GMO": st.column_config.TextColumn("GMO", width="small", disabled=True),
                    # 収支・期限（右側）
                    "実質純利益": st.column_config.NumberColumn("純利益", format="¥%,d", width="small", disabled=True),
                    "限界日": st.column_config.TextColumn("限界日", width="small", disabled=True),
                    "利回り": st.column_config.TextColumn("利回り", width="small", disabled=True),
                },
                disabled=[col for col in df_table.columns if col != "監視"]
            )

            # 差分1行のみ即座に保存・同期（0.05秒フリーズ完全根絶）
            diff_mask = (edited_table["監視"] != df_table["監視"])
            diff_rows = edited_table[diff_mask]

            if not diff_rows.empty:
                for _, erow in diff_rows.iterrows():
                    c = str(erow["コード"])
                    w = bool(erow["監視"])
                    if w and c not in st.session_state["watchlist"]:
                        st.session_state["watchlist"].append(c)
                    elif not w and c in st.session_state["watchlist"]:
                        st.session_state["watchlist"].remove(c)

                    if gas_api_url:
                        sync_single_to_google_sheet(gas_api_url, c, w)

                save_watchlist(st.session_state["watchlist"])
                st.toast("✅ 監視リストを更新しました！")
                st.rerun()

            # ----------------------------------------------------
            # 選択銘柄の超詳細インスペクター
            # ----------------------------------------------------
            st.markdown("<div style='height: 4px;'></div>", unsafe_allow_html=True)
            insp_c1, insp_c2 = st.columns([3.8, 6.2])
            with insp_c1:
                sel_code = st.selectbox(
                    "🔍 銘柄詳細インスペクター（選択すると全社在庫推移を表示）",
                    options=filtered_df["code"].tolist(),
                    format_func=lambda c: f"{c} {filtered_df[filtered_df['code']==c]['name'].values[0]}"
                )
                if sel_code:
                    sel_r = filtered_df[filtered_df["code"] == sel_code].iloc[0]
                    st.markdown(f"""
                    **【{sel_r['code']} {sel_r['name']}】**
                    * **優待内容**: `{sel_r['yutai_content']}`
                    * **優待価値**: ¥{sel_r['yutai_value']:,}相当 ｜ **必要資金**: ¥{sel_r['funds_yen']:,} ｜ **利回り**: {sel_r['yield_pct']}%
                    * **手残り純利益**: ¥{sel_r['net_profit']:,} (限界日: D-{sel_r['limit_days_int']})
                    """)
            with insp_c2:
                if sel_code:
                    sub_h = df_hist[df_hist["code"] == sel_code].copy()
                    if not sub_h.empty and "timestamp" in sub_h.columns:
                        h_disp = sub_h[["timestamp", "nikko", "rakuten", "kabu", "sbi", "gmo"]].copy()
                        h_disp.columns = ["取得日時", "日興", "楽天", "カブ", "SBI", "GMO"]
                        for col in ["日興", "楽天", "カブ"]:
                            h_disp[col] = h_disp[col].apply(fmt_qty)
                        st.dataframe(h_disp.tail(6), hide_index=True, use_container_width=True, height=135)
        else:
            st.info("条件に一致する銘柄がありません。")

    # ----------------------------------------------------
    # TAB 2: 日時別 在庫時系列 (マトリクス)
    # ----------------------------------------------------
    with tab2:
        st.markdown(f"##### 📅 日時別 在庫推移マトリクス ({len(all_timestamps)}回分 スナップショット)")
        target_codes_hist = st.session_state["watchlist"]
        if not target_codes_hist:
            target_codes_hist = df_analyzed["code"].head(10).tolist()

        sub_hist = df_hist[df_hist["code"].isin(target_codes_hist)].copy()
        if not sub_hist.empty and "timestamp" in sub_hist.columns and "code" in sub_hist.columns:
            sub_hist["qty_disp"] = sub_hist["nikko"].apply(fmt_qty)
            pivot_df = sub_hist.pivot_table(
                index=["code", "name"],
                columns="timestamp",
                values="qty_disp",
                aggfunc="last"
            ).fillna("―")

            pivot_df = pivot_df.reset_index()
            pivot_df.columns = [str(col) for col in pivot_df.columns]
            st.dataframe(pivot_df, hide_index=True, use_container_width=True)

            st.markdown("##### 📈 日興在庫 時系列グラフ")
            chart = alt.Chart(sub_hist).mark_line(point=alt.OverlayMarkDef(filled=True, size=70)).encode(
                x=alt.X("timestamp:N", title="取得日時", sort=None),
                y=alt.Y("nikko:Q", title="日興在庫数 (株)"),
                color=alt.Color("name:N", title="銘柄名"),
                tooltip=["name", "code", "timestamp", "nikko", "rakuten", "sbi"]
            ).properties(height=360)
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("過去の時系列ログがまだ十分に蓄積されていません。")

    # ----------------------------------------------------
    # TAB 3: 運用ガイド ＆ 自動実行
    # ----------------------------------------------------
    with tab3:
        st.markdown(f"""
        ### ⚡ 運用 ＆ オンデマンド実行の仕組み

        1. **「🚀 最新スクレイピング」ボタン（画面右上）**:
           - 押すと GitHub Actions の API を叩き、Microsoft/GitHub のサーバー上で両サイトの巡回（約1〜2分）が開始されます。
           - Streamlit Cloud のスリープ状態に一切邪魔されず、完全に独立して最新化されます。
        2. **定期自動更新（完全放置運用）**:
           - 平日毎日 **17:00** および **20:00**（JST）に GitHub Actions が自動起動し、最新在庫を追記します。
        3. **「🔄 画面再読込」ボタン**:
           - 巡回完了後、このボタンを押すだけで最新データが画面に即時反映されます。
        """)

if __name__ == "__main__":
    main()
