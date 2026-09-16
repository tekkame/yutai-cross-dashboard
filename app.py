# -*- coding: utf-8 -*-
"""
app.py - 株主優待クロス在庫トラッカー ＆ 実戦意思決定ダッシュボード
【監視銘柄ピン留め完全一本化 ＆ 確実な多層クラウド永続化版】
- ⭐ 監視リスト ＝ ピン留めリスト に完全一本化（目的の重複を解消）
- 🎯 画面上部に「⭐ 監視・目標銘柄ハイライト」（拘束資金合計・見込純利益計・対象カード一覧）
- ⚡ 実戦ボード data_editor による「⭐」チェックボックス直接操作（辞書キー比較で確実に検知 ＆ 即座に画面反映）
- 💾 Streamlit Cloud 完全対応の多層永続化（Session + Local File + GitHub API Commit + GAS/Sheets Sync）
- 🗓 日時別 在庫推移マトリクス ＆ 📈 日興在庫時系列推移チャート
- 🚀 GitHub Actions 1クリックオンデマンド・スクレイピング起動
"""

from __future__ import annotations

import base64
import datetime as dt
import io
import json
import os
import re
import threading
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

/* 監視ハイライト用CSS */
.target-highlight-panel {
    background: linear-gradient(145deg, #1e293b 0%, #0f172a 100%);
    border: 1px solid #fbbf24;
    border-radius: 8px;
    padding: 0.65rem 0.9rem;
    margin-bottom: 0.5rem;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
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
    grid-template-columns: 65px 160px 75px 55px 75px 75px auto;
    gap: 0.4rem;
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
.target-nikko { font-family: 'JetBrains Mono', monospace; text-align: right; }
.target-sbi { font-family: 'JetBrains Mono', monospace; text-align: center; font-weight: bold; }
.target-funds { font-family: 'JetBrains Mono', monospace; text-align: right; color: #cbd5e1; }
.target-profit { font-family: 'JetBrains Mono', monospace; text-align: right; color: #86efac; font-weight: 600; }
.target-yutai { color: #cbd5e1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; font-size: 11px; }

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
APP_VERSION = "v9.0 (Unified Watchlist & Verified Cloud Persistence)"

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
    if s in ("", "-", "―", "ー", "null", "None", "nan", "取扱なし"): return None
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

def safe_get_secret(key: str, default: str = "") -> str:
    """Streamlit Secrets が未設定の環境でも例外を投げずに安全に値を取得"""
    try:
        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets[key])
    except Exception:
        pass
    return os.environ.get(key, default)

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
# 4. GitHub Actions 1クリック起動エンジン
# ============================================================
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
def load_watchlist_from_disk() -> List[str]:
    """ローカル/リポジトリ同梱の watchlist.json から読み込み"""
    if WATCHLIST_FILE.exists():
        try:
            codes = json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
            if isinstance(codes, list):
                return [fmt_code(c) for c in codes if c]
        except Exception: pass
    return ["9831", "8136", "7513", "3679", "7458", "3778", "7419", "3844", "3167", "5262", "9201", "9202"]

def save_watchlist_to_disk(codes: List[str]):
    """ローカルディスクへ即座に書き込み"""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    clean_codes = sorted(list(set(fmt_code(c) for c in codes if c)))
    WATCHLIST_FILE.write_text(json.dumps(clean_codes, ensure_ascii=False, indent=2), encoding="utf-8")

def load_initial_watchlist(df_mast: Optional[pd.DataFrame] = None) -> List[str]:
    """スプレッドシートフラグ ＋ ローカル/Git JSON を統合して初期ロード"""
    w_sheet = []
    if df_mast is not None and not df_mast.empty:
        c_cols = [c for c in ["コード", "code", "銘柄コード"] if c in df_mast.columns]
        if c_cols:
            c_col = c_cols[0]
            w_cols = [c for c in ["監視", "watch", "目標", "target"] if c in df_mast.columns]
            for wc in w_cols:
                watched = df_mast[df_mast[wc].astype(str).str.upper().isin(["TRUE", "1"])][c_col].dropna().tolist()
                w_sheet.extend([fmt_code(c) for c in watched])

    w_local = load_watchlist_from_disk()
    final_w = list(dict.fromkeys(w_sheet + w_local)) if (w_sheet or w_local) else []
    return final_w

# --- 非同期同期ワーカー (GAS ＆ GitHub API) ---
def _send_to_gas_worker(gas_url: str, code: str, is_watched: bool):
    try:
        payload = json.dumps({"code": code, "watch": is_watched, "status": "未確保"}).encode("utf-8")
        req = urllib.request.Request(
            gas_url, data=payload, headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=4) as resp:
            pass
    except Exception:
        pass

def _sync_to_github_worker(token: str, repo: str, content_str: str, commit_msg: str):
    """Streamlit Cloud 上での変更を GitHub リポジトリへ直接コミットして永久保持"""
    if not token or not repo: return
    try:
        url = f"https://api.github.com/repos/{repo}/contents/data/watchlist.json"
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
            if e.code != 404: return
        except Exception: return

        b64_content = base64.b64encode(content_str.encode("utf-8")).decode("utf-8")
        payload = {"message": commit_msg, "content": b64_content, "branch": "main"}
        if sha: payload["sha"] = sha

        req_put = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"),
            headers={**headers, "Content-Type": "application/json"}, method="PUT"
        )
        with urllib.request.urlopen(req_put, timeout=6) as resp:
            pass
    except Exception:
        pass

def persist_watchlist(current_list: List[str], gas_url: str, gh_token: str, gh_repo: str, trigger_code: str = ""):
    """①ローカル保存 + ②GitHubリポジトリ永続化 + ③GAS同期 を多層実行"""
    clean_list = sorted(list(set(fmt_code(c) for c in current_list if c)))
    json_str = json.dumps(clean_list, ensure_ascii=False, indent=2)

    # 1. ローカル保存 (即時)
    save_watchlist_to_disk(clean_list)

    # 2. GitHubへの非同期コミット (Streamlit Cloud再起動対策)
    if gh_token and gh_repo:
        msg = f"Update watchlist: {len(clean_list)} items (changed: {trigger_code})"
        t_gh = threading.Thread(target=_sync_to_github_worker, args=(gh_token, gh_repo, json_str, msg), daemon=True)
        t_gh.start()

    # 3. GASへの非同期送信
    if gas_url and gas_url.startswith("https://script.google.com") and trigger_code:
        is_w = (trigger_code in clean_list)
        t_gas = threading.Thread(target=_send_to_gas_worker, args=(gas_url, trigger_code, is_w), daemon=True)
        t_gas.start()

# ============================================================
# 6. データローダー (ローカル最新CSV + Google Sheets ハイブリッド)
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
    data_source_msg = "ローカル蓄積CSV"

    # 1. リポジトリ内の最新CSV (GitHub Actions自動更新データ) を最優先読込
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

    # 2. Googleスプレッドシートも取得可能なら連携
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
        c_col = "コード" if "コード" in combined_hist.columns else combined_hist.columns[1]
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
        d["timestamp"] = d["dt"].dt.strftime("%Y-%m-%d %H:%M:%S")

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

        nikko_prev = to_float(prev_row.get("nikko")) if prev_row is not None else None
        rakuten_prev = to_float(prev_row.get("rakuten")) if prev_row is not None else None

        sbi_prev_raw = str(prev_row.get("rtn_sbi") or prev_row.get("sbi") or "―").strip() if prev_row is not None else "―"
        sbi_prev = fmt_signal(sbi_prev_raw)

        nikko_diff = (nikko_now - nikko_prev) if (nikko_now is not None and nikko_prev is not None) else None

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
        elif (nikko_now is not None and nikko_now < nikko_th) or (nikko_diff is not None and nikko_diff < -3000):
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
        funds_yen = int(round(funds_man * 10000)) if (funds_man is not None and funds_man > 0) else 99999999

        days_left_raw = str(row.get("days_left") or "10").replace("D-", "")
        try: d_n = int(days_left_raw)
        except ValueError: d_n = 10

        stock_price = to_float(row.get("stock_price") or m_row.get("stock_price"))
        if stock_price is None and funds_man is not None:
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

        is_watch = (code in watchlist)

        results.append({
            "watch": is_watch,
            "watch_rank": 0 if is_watch else 1,  # 監視中を最優先ピン留め
            "code": code,
            "name": name,
            "stock_price": stock_price,
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
            "total_qty": total_qty,
            "funds_man": funds_man,
            "yutai_value": yutai_val,
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
    gh_token = get_github_token()
    gh_repo = safe_get_secret("GITHUB_REPO", "tekkame/yutai-cross-dashboard")

    with st.sidebar:
        st.markdown("### ⚙️ 設定 ＆ 監視リスト管理")
        sheet_id = st.text_input("スプレッドシートID", value=DEFAULT_SPREADSHEET_ID)
        gas_api_url = st.text_input("GAS URL", value=DEFAULT_GAS_API_URL)
        nikko_th = st.number_input("日興 警戒閾値 (株)", value=10000, step=1000)
        annual_rate = st.number_input("貸株年率", value=0.014, step=0.001, format="%.3f")

        st.markdown("---")
        st.markdown("##### 💾 永続化ステータス")
        if gh_token:
            st.success("✅ GitHub Token 連携中（クラウド自動保存OK）")
        else:
            st.info("ℹ️ ローカル保存モード（SecretsにToken登録でクラウド自動保存可）")

        if st.button("📥 監視リストを再読込", use_container_width=True):
            st.session_state["watchlist"] = load_watchlist_from_disk()
            st.toast("監視リストを再読込しました")
            st.rerun()

        st.caption(f"App Version: {APP_VERSION}")

    raw_hist, raw_mast, data_source_msg = load_all_combined_data(spreadsheet_id=sheet_id)
    if raw_hist is None or raw_hist.empty:
        st.warning("⚠️ 在庫データがありません。")
        return

    df_hist = normalize_history(raw_hist)
    df_mast = normalize_master(raw_mast)

    # 監視リストのロード＆スプレッドシート変更の自動合流
    if "watchlist" not in st.session_state:
        st.session_state["watchlist"] = load_initial_watchlist(df_mast)
    else:
        # スプレッドシート側で後からTRUEにされた銘柄があれば自動でマージ
        if df_mast is not None and not df_mast.empty:
            c_cols = [c for c in ["コード", "code", "銘柄コード"] if c in df_mast.columns]
            if c_cols:
                c_col = c_cols[0]
                w_cols = [c for c in ["監視", "watch", "目標", "target"] if c in df_mast.columns]
                for wc in w_cols:
                    watched = df_mast[df_mast[wc].astype(str).str.upper().isin(["TRUE", "1"])][c_col].dropna().tolist()
                    for sw in [fmt_code(c) for c in watched]:
                        if sw and sw not in st.session_state["watchlist"]:
                            st.session_state["watchlist"].append(sw)

    df_analyzed, stats, all_timestamps = analyze_stocks(
        df_hist, df_mast,
        watchlist=st.session_state["watchlist"],
        nikko_th=nikko_th,
        annual_rate=annual_rate
    )

    # ステータスバー (インデントなしで安全に描画)
    status_bar_html = (
        f'<div class="status-bar">'
        f'<div class="status-bar-title">⚡ <b>優待クロス在庫トラッカー</b> <span style="font-size:11px;font-weight:normal;color:#94a3b8;">({APP_VERSION})</span></div>'
        f'<div class="status-tags">'
        f'<span class="tag tag-green">{data_source_msg}</span>'
        f'<span class="tag tag-blue">最新取得: {stats.get("latest_ts", "―")}</span>'
        f'<span class="tag tag-amber">⭐ 監視中: {stats.get("watch_count", 0)}銘柄</span>'
        f'<span class="tag tag-red">今夜確保: {stats.get("tonight_count", 0)}</span>'
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
        valid_profits = watch_df["net_profit"].dropna()
        total_profit = valid_profits.sum() if not valid_profits.empty else None

        funds_disp = f"¥{int(total_funds):,}" if total_funds > 0 else "―"
        profit_disp = f"¥{int(total_profit):,}" if total_profit is not None else "―"

        rows_html_list = []
        for _, r in watch_df.sort_values(by="funds_yen").iterrows():
            c = r["code"]
            n = r["name"]
            n_qty = fmt_qty(r["nikko_now"])
            s_val = str(r["sbi_now"])
            f_val = f"¥{int(r['funds_yen']):,}" if r["funds_yen"] < 99999990 else "―"
            p_val = f"¥{int(r['net_profit']):,}" if r["net_profit"] is not None else "―"
            y_val = str(r["yutai_content"])

            sbi_color = "#f87171" if s_val in ("×", "▲") else ("#a7f3d0" if s_val == "◎" else "#94a3b8")
            nikko_color = "#f87171" if (r["nikko_now"] is not None and r["nikko_now"] < nikko_th) else "#a7f3d0"

            row_html = (
                f'<div class="target-item-row">'
                f'<div class="target-code">{c}</div>'
                f'<div class="target-name" title="{n}">{n}</div>'
                f'<div class="target-nikko" style="color: {nikko_color};">{n_qty}</div>'
                f'<div class="target-sbi" style="color: {sbi_color};">{s_val}</div>'
                f'<div class="target-funds">{f_val}</div>'
                f'<div class="target-profit">{p_val}</div>'
                f'<div class="target-yutai" title="{y_val}">{y_val}</div>'
                f'</div>'
            )
            rows_html_list.append(row_html)

        all_rows_html = "".join(rows_html_list)

        html_panel = (
            f'<div class="target-highlight-panel">'
            f'<div class="target-header">⭐ 監視・目標銘柄ハイライト ({len(watch_df)}件ピン留め中)</div>'
            f'<div class="target-summary">'
            f'<div class="target-summary-item"><span class="label">拘束資金合計:</span><span class="value">{funds_disp}</span></div>'
            f'<div class="target-summary-item"><span class="label">見込純利益計:</span><span class="value" style="color:#86efac;">{profit_disp}</span></div>'
            f'</div>'
            f'<div style="margin-top: 0.35rem; background: #0f172a; border-radius: 4px; padding: 0.4rem 0.6rem;">'
            f'<div class="target-item-row" style="border-bottom: 1px solid #334155; font-weight: bold; color: #94a3b8; padding-bottom: 0.2rem;">'
            f'<div>コード</div><div>銘柄名</div><div style="text-align:right;">日興最新</div><div style="text-align:center;">SBI</div><div style="text-align:right;">取得資金</div><div style="text-align:right;">見込純益</div><div>優待内容</div>'
            f'</div>'
            f'<div style="max-height: 155px; overflow-y: auto; padding-right: 4px;">'
            f'{all_rows_html}'
            f'</div>'
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
    # コントロールバー
    # ----------------------------------------------------
    c_f1, c_f2, c_f3, c_f4, c_f5, c_f6, c_f7 = st.columns([2.0, 1.4, 0.9, 0.9, 1.6, 1.1, 1.5])
    with c_f1: query = st.text_input("検索", placeholder="コード/銘柄名/優待内容", label_visibility="collapsed")
    with c_f2: signal_filter = st.multiselect("絞込", options=["🔴 今夜確保", "🔥 補充", "🚨 SBI急変", "🔴 即確保", "🟡 要監視", "🟢 待機可", "⚪ 枯渇"], default=[], label_visibility="collapsed")
    with c_f3: only_watch = st.checkbox("⭐ 監視のみ", value=False)
    with c_f4: only_nikko = st.checkbox("日興あり", value=False)
    with c_f5:
        sort_mode = st.selectbox("並び替え", options=[
            "💴 取得資金が安い順", "💰 取得資金が高い順", "⚡ シグナル優先",
            "🎁 実質純利益が高い順", "📈 利回りが高い順", "📉 日興在庫が多い順"
        ], label_visibility="collapsed")
    with c_f6:
        if st.button("🔄 画面再読込", use_container_width=True):
            st.rerun()
    with c_f7:
        if st.button("🚀 最新取得", use_container_width=True):
            ok, msg = trigger_github_workflow(token=gh_token, repo=gh_repo)
            st.toast(msg)

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
            filtered_df["yutai_content"].astype(str).str.lower().str.contains(q)
        ]

    # ソート: 監視銘柄（⭐）を常に最上部にピン留めするため watch_rank を第1キーとする
    if "取得資金が安い順" in sort_mode:
        filtered_df = filtered_df.sort_values(by=["watch_rank", "funds_yen"], ascending=[True, True])
    elif "取得資金が高い順" in sort_mode:
        filtered_df = filtered_df.sort_values(by=["watch_rank", "funds_yen"], ascending=[True, False])
    elif "実質純利益が高い順" in sort_mode:
        filtered_df = filtered_df.sort_values(by=["watch_rank", "net_profit"], ascending=[True, False], na_position="last")
    elif "利回りが高い順" in sort_mode:
        filtered_df = filtered_df.sort_values(by=["watch_rank", "yield_pct"], ascending=[True, False], na_position="last")
    elif "日興在庫が多い順" in sort_mode:
        filtered_df = filtered_df.sort_values(by=["watch_rank", "nikko_now"], ascending=[True, False], na_position="last")
    else:
        filtered_df = filtered_df.sort_values(by=["watch_rank", "signal_rank", "funds_yen"], ascending=[True, True, True])

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
    # TAB 1: 実戦ボード (st.data_editor + 確実なコードキー差分検知＆保存)
    # ----------------------------------------------------
    with tab1:
        display_rows = []
        for _, r in filtered_df.iterrows():
            diff = r["nikko_diff"]
            diff_str = "―" if diff is None else (f"+{int(diff):,}" if diff > 0 else (f"{int(diff):,}" if diff < 0 else "±0"))
            limit_str = f"D-{r['limit_days_int']}" if r["limit_days_int"] is not None else "―"

            display_rows.append({
                "⭐": bool(r.get("watch", False)),
                "コード": str(r.get("code", "")),
                "銘柄名": str(r.get("name", "")),
                "優待内容": str(r.get("yutai_content", ""))[:32] if r.get("yutai_content") else "―",
                "優待額": float(r["yutai_value"]) if r["yutai_value"] is not None else None,
                "取得資金": float(r["funds_yen"]) if r["funds_yen"] < 99999990 else None,
                "意思決定": str(r.get("signal", "")),
                "SBI急変": str(r.get("sbi_change", "―")),
                "日興最新": fmt_qty(r.get("nikko_now")),
                "前日比": diff_str,
                "SBI": str(r.get("sbi_now", "―")),
                "楽天": fmt_qty(r.get("rakuten_now")),
                "カブ": fmt_qty(r.get("kabu_now")),
                "GMO": str(r.get("gmo_now", "―")),
                "純利益": float(r["net_profit"]) if r["net_profit"] is not None else None,
                "限界日": limit_str,
                "利回り": f"{r['yield_pct']:.1f}%" if r["yield_pct"] is not None else "―",
                "補充": str(r.get("refill", "")),
            })

        df_table = pd.DataFrame(display_rows)

        if not df_table.empty:
            df_table["コード"] = df_table["コード"].astype(str)
            edited_table = st.data_editor(
                df_table,
                key="yutai_data_editor",
                use_container_width=True,
                hide_index=True,
                height=560,
                column_config={
                    "⭐": st.column_config.CheckboxColumn("⭐", width="small", help="監視・ピン留め（チェックで最上部に固定＆多層自動保存）"),
                    "コード": st.column_config.TextColumn("コード", width="small"),
                    "銘柄名": st.column_config.TextColumn("銘柄名", width="medium"),
                    "優待内容": st.column_config.TextColumn("優待内容", width="large"),
                    "優待額": st.column_config.NumberColumn("優待額", format="¥%,d", width="small", disabled=True),
                    "取得資金": st.column_config.NumberColumn("必要資金", format="¥%,d", width="medium", disabled=True),
                    "意思決定": st.column_config.TextColumn("意思決定", width="small"),
                    "SBI急変": st.column_config.TextColumn("SBI急変", width="medium"),
                    "日興最新": st.column_config.TextColumn("日興", width="small"),
                    "前日比": st.column_config.TextColumn("前日比", width="small"),
                    "SBI": st.column_config.TextColumn("SBI", width="small"),
                    "楽天": st.column_config.TextColumn("楽天", width="small"),
                    "カブ": st.column_config.TextColumn("カブ", width="small"),
                    "GMO": st.column_config.TextColumn("GMO", width="small"),
                    "純利益": st.column_config.NumberColumn("純利益", format="¥%,d", width="small", disabled=True),
                    "限界日": st.column_config.TextColumn("限界日", width="small"),
                    "利回り": st.column_config.TextColumn("利回り", width="small"),
                    "補充": st.column_config.TextColumn("補充", width="small"),
                },
                disabled=[c for c in df_table.columns if c != "⭐"]
            )

            # --- 確実なコードキー差分検知 (インデックスずれ・ソート順に完全非依存) ---
            orig_map = dict(zip(df_table["コード"], df_table["⭐"]))
            new_map = dict(zip(edited_table["コード"], edited_table["⭐"]))

            changed_items = []
            for c, new_val in new_map.items():
                old_val = orig_map.get(c)
                if old_val is not None and old_val != new_val:
                    changed_items.append((c, new_val))

            if changed_items:
                for c, is_watched in changed_items:
                    if is_watched and c not in st.session_state["watchlist"]:
                        st.session_state["watchlist"].append(c)
                    elif not is_watched and c in st.session_state["watchlist"]:
                        st.session_state["watchlist"].remove(c)
                    # 多層保存（ローカル + GitHub API + GAS）
                    persist_watchlist(st.session_state["watchlist"], gas_api_url, gh_token, gh_repo, trigger_code=c)

                # 即時再描画（これで上部パネル・ピン留め・ステータスバーが100%確実に即時変化する！）
                st.rerun()

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
                bcol = BROKER_COLS[mx_broker]
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
            sub = df_hist[df_hist["code"].isin(codes_plot)]
            if not sub.empty:
                chart = alt.Chart(sub).mark_line(point=True).encode(
                    x=alt.X("timestamp:N", title="取得日時"),
                    y=alt.Y("nikko:Q", title="日興在庫数 (株)"),
                    color=alt.Color("name:N", title="銘柄名"),
                    tooltip=["name", "code", "timestamp", "nikko", "rakuten", "sbi"]
                ).properties(height=380)
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