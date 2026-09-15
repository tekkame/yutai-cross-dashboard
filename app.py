# -*- coding: utf-8 -*-
"""
app.py - 株主優待クロス在庫トラッカー ＆ 実戦意思決定ダッシュボード
プロ仕様・超高密度（Compact Trading UI）
- デフォルトソート: 取得参考価格が安い順 (¥50,000 -> ¥100,000 ...)
- NumberColumn(format="¥%,d") による美しい通貨表示
- 限界日は D-XX (整数) 表記
- 高速ウォッチリスト切り替え & フリーズ完全根絶
"""

from __future__ import annotations

import datetime as dt
import io
import json
import os
import re
import subprocess
import sys
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
    page_icon="📈",
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
    padding-top: 0.5rem !important;
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
    margin-bottom: 0.4rem;
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
.tag-purple { background: #581c87; color: #f0abfc; border: 1px solid #9333ea; }
.tag-gray   { background: #1e293b; color: #94a3b8; border: 1px solid #334155; }

.alert-banner-danger {
    background: #450a0a;
    border: 1px solid #dc2626;
    color: #fecaca;
    padding: 0.35rem 0.75rem;
    border-radius: 6px;
    margin-bottom: 0.4rem;
    font-size: 12px;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 0.5rem;
}

.alert-banner-safe {
    background: #022c22;
    border: 1px solid #059669;
    color: #a7f3d0;
    padding: 0.25rem 0.65rem;
    border-radius: 6px;
    margin-bottom: 0.4rem;
    font-size: 11.5px;
    display: flex;
    align-items: center;
    gap: 0.4rem;
}

.kpi-row {
    display: flex;
    gap: 0.35rem;
    margin-bottom: 0.45rem;
    flex-wrap: wrap;
}

.kpi-card {
    flex: 1;
    min-width: 115px;
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
    gap: 0.25rem !important;
}

.stTabs [data-baseweb="tab-list"] {
    gap: 0.25rem;
    margin-bottom: 0.3rem;
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
APP_VERSION = "v2.3 (Precision Pipeline)"

# ============================================================
# 3. 堅牢なフォーマッター
# ============================================================
def to_float(v: Any) -> Optional[float]:
    if v is None or pd.isna(v) or v == "":
        return None
    try:
        val = float(v)
        return None if np.isnan(val) else val
    except (ValueError, TypeError):
        return None

def to_int(v: Any) -> Optional[int]:
    f = to_float(v)
    return int(round(f)) if f is not None else None

def fmt_int(v: Any) -> str:
    i = to_int(v)
    return f"{i:,}" if i is not None else "―"

def fmt_float(v: Any, digits: int = 1) -> str:
    f = to_float(v)
    return f"{f:.{digits}f}" if f is not None else "―"

def fmt_qty(v: Any) -> str:
    f = to_float(v)
    if f is None:
        return "―"
    if f >= 9999990:
        return "大量"
    if f >= 10000:
        return f"{f/10000:.1f}万"
    return f"{int(f):,}"

def parse_qty_safe(v: Any) -> Optional[float]:
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
    if "大量" in s:
        return 9999999.0
    if s in ("◎", "▲"):
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
    if v is None or pd.isna(v):
        return ""
    s = str(v).split(".")[0].strip()
    return s.zfill(4) if len(s) <= 4 and s.isdigit() else s

def fmt_signal(v: Any) -> str:
    """SBI/GMO等の信号セルを正規化（旧CSVの 0.0/1.0/2.0 → ×/▲/◎）"""
    if v is None or (not isinstance(v, str) and pd.isna(v)):
        return "―"
    s = str(v).strip()
    if s in ("", "-", "―", "ー", "null", "None", "nan"):
        return "―"
    if s in ("2", "2.0", "◎"):
        return "◎"
    if s in ("1", "1.0", "▲"):
        return "▲"
    if s in ("0", "0.0", "×", "✕"):
        return "×"
    return s

# ============================================================
# 4. ウォッチリスト管理
# ============================================================
def load_watchlist() -> List[str]:
    if WATCHLIST_FILE.exists():
        try:
            codes = json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
            if isinstance(codes, list):
                return [fmt_code(c) for c in codes]
        except Exception:
            pass
    return ["9831", "8136", "7513", "3679", "7458", "3778", "7419", "3844"]

def save_watchlist(codes: List[str]):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    clean_codes = sorted(list(set(fmt_code(c) for c in codes if c)))
    WATCHLIST_FILE.write_text(json.dumps(clean_codes, ensure_ascii=False, indent=2), encoding="utf-8")

# ============================================================
# 4b. 手動スクレイピング実行ヘルパー
# ============================================================
def run_scraper(out_dir: Path = DATA_DIR, timeout_sec: int = 300) -> Tuple[bool, str]:
    """main.py をサブプロセスで実行し、在庫CSVを再取得する。戻り値: (成功, メッセージ)"""
    out_dir.mkdir(parents=True, exist_ok=True)
    before = {p.name for p in out_dir.glob("history_*.csv")}
    try:
        proc = subprocess.run(
            [sys.executable, "main.py", "--dry-run", "--out-dir", str(out_dir)],
            cwd=BASE_DIR,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout_sec,
        )
    except subprocess.TimeoutExpired:
        return False, f"タイムアウト（{timeout_sec}秒）: 取得元サイトの応答が遅い可能性があります"
    except OSError as e:
        return False, f"実行失敗: {e}"
    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()
        detail = "\n".join(tail[-8:]) if tail else "詳細不明"
        return False, f"スクレイピング失敗 (exit={proc.returncode}):\n{detail}"
    new_files = sorted({p.name for p in out_dir.glob("history_*.csv")} - before)
    if not new_files:
        return False, "CSVが新規作成されませんでした"
    return True, f"取得完了: {', '.join(new_files)}"

# ============================================================
# 5. データローダー
# ============================================================
@st.cache_data(ttl=60, show_spinner=False)
def load_all_local_data() -> Tuple[pd.DataFrame, pd.DataFrame]:
    hist_dfs = []
    latest_master = pd.DataFrame()

    if DATA_DIR.exists():
        h_files = sorted([DATA_DIR / f for f in os.listdir(DATA_DIR) if f.startswith("history_") and f.endswith(".csv")])
        for hf in h_files:
            try:
                df_tmp = pd.read_csv(hf)
                if not df_tmp.empty:
                    hist_dfs.append(df_tmp)
            except Exception:
                pass

        m_files = sorted([DATA_DIR / f for f in os.listdir(DATA_DIR) if f.startswith("master_") and f.endswith(".csv")], reverse=True)
        if m_files:
            try:
                latest_master = pd.read_csv(m_files[0])
            except Exception:
                pass

    if hist_dfs:
        combined_hist = pd.concat(hist_dfs, ignore_index=True)
        t_col = "取得日時" if "取得日時" in combined_hist.columns else combined_hist.columns[0]
        c_col = "コード" if "コード" in combined_hist.columns else combined_hist.columns[3]
        combined_hist = combined_hist.drop_duplicates(subset=[t_col, c_col], keep="last")
        return combined_hist, latest_master

    return pd.DataFrame(), pd.DataFrame()

def normalize_history(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    d = df.copy()
    col_map = {
        "コード": "code", "銘柄名": "name", "取得日時": "timestamp",
        "権利年月": "rights_month", "残日数": "days_left", "残日数(D-N)": "days_left",
        "日興在庫": "nikko", "楽天在庫": "rakuten", "カブ在庫": "kabu",
        "SBI在庫": "sbi", "SBI信号": "sbi", "GMO在庫": "gmo", "GMO信号": "gmo",
        "松井信号": "matsui", "マネ信号": "monex",
        "株価": "kabuka", "株数": "kabusu", "貸株コスト": "cost",
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
    if df is None or df.empty:
        return pd.DataFrame()
    d = df.copy()
    col_map = {
        "コード": "code", "銘柄名": "name", "優待内容": "yutai_content",
        "優待価値": "yutai_value", "優待価値(円)": "yutai_value",
        "必要資金": "funds_man", "必要資金(万)": "funds_man",
        "利回り(%)": "yield_pct", "総合利回り": "yield_pct", "売建上限": "gmo_limit"
    }
    for orig, standard in col_map.items():
        if orig in d.columns and standard not in d.columns:
            d[standard] = d[orig]

    if "code" in d.columns:
        d["code"] = d["code"].apply(fmt_code)
    return d

# ============================================================
# 6. 分析・シグナル算出エンジン
# ============================================================
def analyze_stocks(
    df_hist: pd.DataFrame,
    df_mast: pd.DataFrame,
    watchlist: List[str],
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

        sbi_now_raw = str(row.get("sbi") or row.get("rtn_sbi") or "―").strip()
        sbi_now = "◎" if "◎" in sbi_now_raw or sbi_now_raw == "2" else ("▲" if "▲" in sbi_now_raw or sbi_now_raw == "1" else ("×" if "×" in sbi_now_raw or "✕" in sbi_now_raw or sbi_now_raw == "0" else sbi_now_raw))

        gmo_now = str(row.get("gmo") or m_row.get("gmo_limit") or "―").strip()
        matsui_now = str(row.get("matsui") or "―").strip()
        monex_now = str(row.get("monex") or "―").strip()

        nikko_prev = to_float(prev_row.get("nikko")) if prev_row is not None else None
        rakuten_prev = to_float(prev_row.get("rakuten")) if prev_row is not None else None

        sbi_prev_raw = str(prev_row.get("sbi") or prev_row.get("rtn_sbi") or "―").strip() if prev_row is not None else "―"
        sbi_prev = "◎" if "◎" in sbi_prev_raw or sbi_prev_raw == "2" else ("▲" if "▲" in sbi_prev_raw or sbi_prev_raw == "1" else ("×" if "×" in sbi_prev_raw or "✕" in sbi_prev_raw or sbi_prev_raw == "0" else sbi_prev_raw))

        # 1. 日興前日比 & 推移
        nikko_diff = (nikko_now - nikko_prev) if (nikko_now is not None and nikko_prev is not None) else None
        nikko_trend_str = f"{fmt_qty(nikko_prev)} → {fmt_qty(nikko_now)}" if prev_ts else fmt_qty(nikko_now)

        # 2. SBI急変検知
        is_sbi_sudden_drop = False
        if prev_ts:
            if sbi_prev == "◎" and sbi_now == "▲":
                sbi_change = "🚨急変(◎→▲)"
                is_sbi_sudden_drop = True
            elif sbi_prev == "◎" and sbi_now == "×":
                sbi_change = "💥瞬殺(◎→×)"
                is_sbi_sudden_drop = True
            elif sbi_prev != sbi_now and sbi_prev != "―":
                sbi_change = f"{sbi_prev}→{sbi_now}"
            else:
                sbi_change = f"{sbi_now}(維持)" if sbi_now in ("◎", "▲", "×") else sbi_now
        else:
            sbi_change = sbi_now

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

        # 6. コスト & 実質純利益 & 限界日
        yutai_val = to_float(m_row.get("yutai_value") or row.get("yutai_value"))
        funds_man = to_float(m_row.get("funds_man") or row.get("funds_man"))

        # 取得参考価格 (円単位の純粋な整数)
        funds_yen = int(round(funds_man * 10000)) if funds_man is not None and funds_man > 0 else 99999999

        days_left_raw = str(row.get("days_left") or "10").replace("D-", "")
        try:
            d_n = int(days_left_raw)
        except ValueError:
            d_n = 10

        kabuka = to_float(row.get("kabuka")) or ((funds_man * 10000 / 100) if funds_man else None)
        kabusu = to_float(row.get("kabusu")) or 100.0

        net_profit = None
        limit_days_int = None

        if kabuka and kabusu and d_n:
            try:
                principal = kabuka * kabusu
                daily_cost = principal * annual_rate / 365.0
                cost = round(daily_cost * d_n)
                if yutai_val is not None:
                    net_profit = int(round(yutai_val - cost))
                    if daily_cost > 0:
                        limit_days_int = int(round(yutai_val / daily_cost))
            except Exception:
                pass

        is_watched = (code in watchlist)

        results.append({
            "code": code,
            "name": name,
            "is_watched": is_watched,
            "signal": signal,
            "signal_rank": signal_rank,
            "sbi_change": sbi_change,
            "is_sbi_drop": is_sbi_sudden_drop,
            "refill": "🔥補充" if is_refill else "",
            "is_refill": is_refill,
            "nikko_now": nikko_now,
            "nikko_diff": nikko_diff,
            "nikko_trend_str": nikko_trend_str,
            "rakuten_now": rakuten_now,
            "kabu_now": kabu_now,
            "sbi_now": sbi_now,
            "gmo_now": gmo_now,
            "matsui_now": matsui_now,
            "monex_now": monex_now,
            "total_qty": total_qty,
            "funds_man": funds_man,
            "funds_yen": funds_yen,
            "yutai_value": yutai_val,
            "yutai_content": str(m_row.get("yutai_content") or ""),
            "yield_pct": to_float(m_row.get("yield_pct")),
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
        "watch_count": sum(1 for r in results if r["is_watched"]),
        "empty_count": sum(1 for r in results if r["signal"] == "⚪ 枯渇"),
    }
    return df_res, stats

# ============================================================
# 7. メインUIレンダリング
# ============================================================
def main():
    if "watchlist" not in st.session_state:
        st.session_state["watchlist"] = load_watchlist()

    # サイドバー
    with st.sidebar:
        st.markdown("### ⚙️ 監視設定 ＆ 判定条件")
        nikko_th = st.number_input("日興 警戒閾値 (株)", min_value=1000, max_value=100000, value=10000, step=1000)
        annual_rate = st.number_input("貸株年率", min_value=0.001, max_value=0.05, value=0.011, step=0.001, format="%.3f")

        st.markdown("---")
        st.markdown("#### ⭐ 監視銘柄一括管理")
        raw_h, raw_m = load_all_local_data()
        all_codes = sorted(raw_h["コード"].astype(str).unique().tolist()) if not raw_h.empty else []

        selected_watches = st.multiselect(
            "監視銘柄の選択・解除",
            options=all_codes,
            default=[c for c in st.session_state["watchlist"] if c in all_codes],
            format_func=lambda c: f"{fmt_code(c)}"
        )
        if st.button("💾 監視リストを保存", use_container_width=True):
            st.session_state["watchlist"] = selected_watches
            save_watchlist(selected_watches)
            st.success("監視リストを更新しました！")
            st.rerun()

        st.caption(f"Yutai Cross Tracker {APP_VERSION}")

    # データロード
    raw_hist, raw_mast = load_all_local_data()
    if raw_hist is None or raw_hist.empty:
        st.warning("⚠️ 在庫データがまだ生成されていません。「⚡ 今すぐスクレイピング」を押してください。")
        if st.button("⚡ 今すぐスクレイピング実行"):
            with st.spinner("取得中（1〜2分かかります）..."):
                ok, msg = run_scraper()
                st.cache_data.clear()
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)
        return

    df_hist = normalize_history(raw_hist)
    df_mast = normalize_master(raw_mast)
    df_analyzed, stats = analyze_stocks(
        df_hist, df_mast,
        watchlist=st.session_state["watchlist"],
        nikko_th=nikko_th,
        annual_rate=annual_rate
    )

    # 1. ナビステータスバー
    st.markdown(f"""
    <div class="status-bar">
        <div class="status-bar-title">
            <span>📈 優待クロス在庫トラッカー</span>
        </div>
        <div class="status-tags">
            <span class="tag tag-blue">権利月: 2026-09</span>
            <span class="tag tag-green">最新: {stats.get('latest_ts', '―')}</span>
            {f"<span class='tag tag-gray'>前回: {stats.get('prev_ts')}</span>" if stats.get('prev_ts') else ""}
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
            <span>🚨 <b>【今夜確保アラート】</b> SBI急変＆日興残少: {items}</span>
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
            <span>✅ <b>急変アラートなし:</b> 現在、SBI証券の急激な在庫蒸発（◎→▲/◎→×）は検知されていません。待機可能です。</span>
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
            <span class="kpi-title" style="{ 'color: #fb923c;' if s_cnt > 0 else '' }">🚨 SBI急変・瞬殺</span>
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

    # 4. クイック操作バー
    c_f1, c_f2, c_f3, c_f4, c_f5, c_f6 = st.columns([2.3, 2.0, 1.2, 1.1, 0.7, 0.7])
    with c_f1:
        query = st.text_input("検索", placeholder="🔍 コード・銘柄名・優待内容 (例: 9831, ヤマダ, ギフト)", label_visibility="collapsed")
    with c_f2:
        signal_filter = st.multiselect(
            "シグナル絞込",
            options=["🔴 今夜確保", "🔥 補充", "🚨 SBI急変", "🔴 即確保", "🟡 要監視", "🟢 待機可", "⚪ 枯渇"],
            default=[],
            placeholder="全シグナル表示",
            label_visibility="collapsed"
        )
    with c_f3:
        view_mode = st.radio("表示対象", ["⭐ 監視のみ", "全銘柄"], horizontal=True, label_visibility="collapsed")
    with c_f4:
        only_nikko = st.checkbox("日興あり", value=False)
    with c_f5:
        if st.button("🔄 更新", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
    with c_f6:
        if st.button("⚡ 取得", use_container_width=True):
            with st.spinner("取得中（1〜2分）..."):
                ok, msg = run_scraper()
                st.cache_data.clear()
            if ok:
                st.success(msg)
                st.rerun()
            else:
                st.error(msg)

    # フィルタリング
    filtered_df = df_analyzed.copy()

    if view_mode == "⭐ 監視のみ":
        filtered_df = filtered_df[filtered_df["is_watched"] == True]

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

    # デフォルトソート: 取得参考価格が安い順 (5万→10万→20万...)
    filtered_df = filtered_df.sort_values(by="funds_yen", ascending=True)

    # タブ
    tab1, tab2, tab3, tab4 = st.tabs([
        f"⚡ 実戦ボード ({len(filtered_df)}件)",
        "📊 日興在庫 推移チャート",
        "🗓 日時別マトリクス",
        "💡 運用ガイド"
    ])

    # ----------------------------------------------------
    # TAB 1: 実戦ボード
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

            # 限界日: 整数または ―
            limit_str = f"D-{r['limit_days_int']}" if r["limit_days_int"] is not None else "―"

            # 取得最低価格 (純粋なint)
            p_yen = int(r["funds_yen"]) if r["funds_yen"] < 99999990 else None

            display_rows.append({
                "⭐": "⭐" if r["is_watched"] else "―",
                "コード": r["code"],
                "銘柄名": r["name"],
                "取得最低価格": p_yen,
                "優待内容": r["yutai_content"][:35] if r["yutai_content"] else "―",
                "意思決定": r["signal"],
                "SBI変化": r["sbi_change"],
                "日興最新": fmt_qty(r["nikko_now"]),
                "前日比": diff_str,
                "日興推移": r["nikko_trend_str"],
                "カブ最新": fmt_qty(r["kabu_now"]),
                "楽天最新": fmt_qty(r["rakuten_now"]),
                "SBI": r["sbi_now"],
                "GMO": r["gmo_now"],
                "純利益": to_int(r["net_profit"]),
                "限界日": limit_str,
                "優待価値": to_int(r["yutai_value"]),
                "利回り": f"{fmt_float(r['yield_pct'], 1)}%" if r["yield_pct"] is not None else "―",
                "補充": r["refill"],
            })

        df_table = pd.DataFrame(display_rows)

        st.dataframe(
            df_table,
            use_container_width=True,
            hide_index=True,
            height=620,
            column_config={
                "⭐": st.column_config.TextColumn("⭐", width="small"),
                "コード": st.column_config.TextColumn("コード", width="small"),
                "銘柄名": st.column_config.TextColumn("銘柄名", width="medium"),
                "取得最低価格": st.column_config.NumberColumn("取得最低価格", format="¥%,d", width="medium"),
                "優待内容": st.column_config.TextColumn("優待内容", width="large"),
                "意思決定": st.column_config.TextColumn("意思決定", width="small"),
                "SBI変化": st.column_config.TextColumn("SBI変化", width="medium"),
                "日興最新": st.column_config.TextColumn("日興最新", width="small"),
                "前日比": st.column_config.TextColumn("前日比", width="small"),
                "日興推移": st.column_config.TextColumn("日興推移", width="medium"),
                "カブ最新": st.column_config.TextColumn("カブ", width="small"),
                "楽天最新": st.column_config.TextColumn("楽天", width="small"),
                "SBI": st.column_config.TextColumn("SBI", width="small"),
                "GMO": st.column_config.TextColumn("GMO", width="small"),
                "純利益": st.column_config.NumberColumn("純利益", format="¥%,d", width="small"),
                "限界日": st.column_config.TextColumn("限界日", width="small"),
                "優待価値": st.column_config.NumberColumn("優待(円)", format="¥%,d", width="small"),
                "利回り": st.column_config.TextColumn("利回り", width="small"),
                "補充": st.column_config.TextColumn("補充", width="small"),
            }
        )

        # 選択銘柄クイック詳細 & 監視ON/OFFトグル (差分1行のみ即座に保存・フリーズゼロ)
        if not filtered_df.empty:
            st.markdown("<div style='height: 2px;'></div>", unsafe_allow_html=True)
            d_col1, d_col2 = st.columns([2.5, 4.5])
            with d_col1:
                target_code = st.selectbox(
                    "銘柄を選択して推移を確認 / 監視切替",
                    options=filtered_df["code"].tolist(),
                    format_func=lambda c: f"{c} {filtered_df[filtered_df['code']==c]['name'].values[0] if len(filtered_df[filtered_df['code']==c])>0 else ''}"
                )
                if target_code:
                    is_in_watch = (target_code in st.session_state["watchlist"])
                    btn_label = "⭐ 監視リストから外す" if is_in_watch else "⭐ この銘柄を監視に追加"
                    if st.button(btn_label, use_container_width=True):
                        if is_in_watch:
                            st.session_state["watchlist"].remove(target_code)
                        else:
                            st.session_state["watchlist"].append(target_code)
                        save_watchlist(st.session_state["watchlist"])
                        st.rerun()

            with d_col2:
                if target_code:
                    sub_h = df_hist[df_hist["code"] == target_code].copy()
                    if not sub_h.empty:
                        h_disp = sub_h[["timestamp", "nikko", "rakuten", "kabu", "sbi", "gmo"]].copy()
                        h_disp.columns = ["取得日時", "日興", "楽天", "カブ", "SBI", "GMO"]
                        for col in ["日興", "楽天", "カブ"]:
                            h_disp[col] = h_disp[col].apply(fmt_qty)
                        st.dataframe(h_disp, hide_index=True, use_container_width=True, height=130)

    # ----------------------------------------------------
    # TAB 2: 日興在庫 推移チャート
    # ----------------------------------------------------
    with tab2:
        st.markdown("##### 📈 日興在庫の時系列推移チャート")
        watch_or_top = [c for c in st.session_state["watchlist"] if c in df_analyzed["code"].tolist()]
        if not watch_or_top:
            watch_or_top = df_analyzed[df_analyzed["nikko_now"].fillna(0) > 0]["code"].head(6).tolist()

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
                    y=alt.Y("nikko:Q", title="日興在庫 (株)"),
                    color=alt.Color("name:N", title="銘柄名"),
                    tooltip=["name", "code", "timestamp", "nikko", "rakuten"]
                ).properties(height=380)
                st.altair_chart(chart, use_container_width=True)

    # ----------------------------------------------------
    # TAB 3: 日時別 在庫推移マトリクス
    # ----------------------------------------------------
    with tab3:
        st.markdown("##### 🗓 日時別 在庫推移マトリクス")
        st.caption("1日2回取得で15日分≒30スナップショット。取得を重ねるほど列が増えます（列ヘッダーにカーソルでフル日時表示）。")
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
            st.info("スナップショットが1件のみのためマトリクスを表示できません。「⚡ 取得」で取得を重ねると推移が表示されます。")
        else:
            mx_watch = [c for c in st.session_state["watchlist"] if c in df_analyzed["code"].tolist()]
            if not mx_watch:
                mx_watch = df_analyzed[df_analyzed["nikko_now"].fillna(0) > 0]["code"].head(12).tolist()

            m_c1, m_c2, m_c3 = st.columns([1.0, 1.2, 3.8])
            with m_c1:
                mx_broker = st.selectbox("証券会社", options=list(BROKER_COLS.keys()), index=0)
            with m_c2:
                n_snap = st.slider("表示スナップショット数", min_value=2,
                                   max_value=min(30, len(all_ts)),
                                   value=min(8, len(all_ts)))
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
                piv = sub.pivot_table(index="code", columns="timestamp",
                                      values=bcol, aggfunc="last", dropna=False)
                piv = piv.reindex(index=codes_mx, columns=ts_list)
                # 銘柄名は最新スナップショットの表記に統一（スナップショット間でroutine名/gokigen名が揺れるため）
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
                        if lf is None or pf is None:
                            diff_s = "―"
                        elif lf - pf > 0:
                            diff_s = f"+{int(lf - pf):,}"
                        elif lf - pf < 0:
                            diff_s = f"{int(lf - pf):,}"
                        else:
                            diff_s = "±0"
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
                # 実戦ボードと同じ取得最低価格順に並べ替え
                order = df_analyzed.sort_values("funds_yen")["code"].tolist()
                df_mx["コード"] = pd.Categorical(df_mx["コード"], categories=order, ordered=True)
                df_mx = df_mx.sort_values("コード").reset_index(drop=True)

                mx_config = {
                    "コード": st.column_config.TextColumn("コード", width="small"),
                    "銘柄名": st.column_config.TextColumn("銘柄名", width="medium"),
                    "最新": st.column_config.TextColumn("最新", width="small"),
                    "前回比": st.column_config.TextColumn("前回比", width="small"),
                }
                for ts in ts_list:
                    short = ts[5:] if isinstance(ts, str) and len(ts) >= 11 else str(ts)
                    mx_config[short] = st.column_config.TextColumn(short, width="small", help=str(ts))
                st.dataframe(
                    df_mx,
                    use_container_width=True,
                    hide_index=True,
                    height=min(640, 80 + 29 * len(df_mx)),
                    column_config=mx_config,
                )

    # ----------------------------------------------------
    # TAB 4: 運用ガイド
    # ----------------------------------------------------
    with tab4:
        st.markdown("""
        ### 💡 完全サーバーレス自動運用の仕組み

        - **定期自動実行**: 平日 毎日 **17:00** および **20:00**（JST）に GitHub Actions が自動で動き、最新在庫を追記保存します。
        - **UIの改修**: 画面の変更や調整は `app.py` のみを書き換えて GitHub にプッシュするだけで数秒で反映されます。
        """)

if __name__ == "__main__":
    main()