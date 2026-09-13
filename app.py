# -*- coding: utf-8 -*-
"""
app.py - 株主優待クロス在庫トラッカー ＆ 実戦意思決定ダッシュボード
自宅サーバーレス（Google Apps Script / GitHub Actions）で定期蓄積された
一般信用売り在庫データを可視化し、「今夜確保すべき銘柄」を一目で判断。
"""

from __future__ import annotations

import datetime as dt
import io
import re
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

# ============================================================
# 1. ページ初期設定 & カスタムモダンCSS (Modern Web Aesthetics)
# ============================================================
st.set_page_config(
    page_title="優待クロス在庫トラッカー | 実戦ダッシュボード",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)

CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Noto+Sans+JP:wght@400;500;700;900&display=swap');

html, body, [class*="css"] {
    font-family: 'Inter', 'Noto Sans JP', -apple-system, BlinkMacSystemFont, sans-serif;
}

/* アプリケーション全体コンテナの余白最適化 */
.main .block-container {
    padding-top: 1.2rem;
    padding-bottom: 3rem;
    padding-left: 2rem;
    padding-right: 2rem;
    max-width: 1440px;
}

/* ヘッダーバナー */
.header-container {
    background: linear-gradient(135deg, #1e293b 0%, #0f172a 100%);
    border: 1px solid #334155;
    border-radius: 16px;
    padding: 1.5rem 2rem;
    margin-bottom: 1.5rem;
    box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.2), 0 8px 10px -6px rgba(0, 0, 0, 0.2);
    color: #ffffff;
}

.header-title {
    font-size: 1.8rem;
    font-weight: 800;
    letter-spacing: -0.02em;
    margin: 0;
    display: flex;
    align-items: center;
    gap: 0.75rem;
    color: #f8fafc;
}

.header-subtitle {
    font-size: 0.92rem;
    color: #94a3b8;
    margin-top: 0.4rem;
    line-height: 1.5;
}

.badge-tag {
    display: inline-flex;
    align-items: center;
    padding: 0.25rem 0.65rem;
    border-radius: 9999px;
    font-size: 0.75rem;
    font-weight: 700;
    letter-spacing: 0.03em;
    margin-right: 0.5rem;
}

.badge-primary { background: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid rgba(59, 130, 246, 0.4); }
.badge-success { background: rgba(34, 197, 94, 0.2); color: #4ade80; border: 1px solid rgba(34, 197, 94, 0.4); }
.badge-warning { background: rgba(245, 158, 11, 0.2); color: #fbbf24; border: 1px solid rgba(245, 158, 11, 0.4); }
.badge-danger  { background: rgba(239, 68, 68, 0.25); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.45); }

/* KPIカードスタイル */
.metric-card {
    background: #ffffff;
    border: 1px solid #e2e8f0;
    border-radius: 12px;
    padding: 1.1rem 1.3rem;
    box-shadow: 0 1px 3px rgba(0,0,0,0.05);
    transition: all 0.2s ease;
    height: 100%;
}

@media (prefers-color-scheme: dark) {
    .metric-card {
        background: #1e293b;
        border-color: #334155;
    }
}

.metric-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 8px 16px -4px rgba(0, 0, 0, 0.08);
}

.metric-label {
    font-size: 0.8rem;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #64748b;
    margin-bottom: 0.35rem;
}

.metric-value {
    font-size: 1.85rem;
    font-weight: 800;
    line-height: 1.2;
    color: #0f172a;
}

@media (prefers-color-scheme: dark) {
    .metric-value { color: #f8fafc; }
}

.metric-sub {
    font-size: 0.78rem;
    color: #94a3b8;
    margin-top: 0.3rem;
}

/* シグナルピル */
.pill {
    display: inline-block;
    padding: 0.2rem 0.55rem;
    border-radius: 6px;
    font-size: 0.78rem;
    font-weight: 700;
    text-align: center;
    white-space: nowrap;
}
.pill-tonight { background: #fee2e2; color: #b91c1c; border: 1px solid #f87171; }
.pill-urgent  { background: #ffedd5; color: #c2410c; border: 1px solid #fb923c; }
.pill-watch   { background: #fef3c7; color: #b45309; border: 1px solid #fcd34d; }
.pill-wait    { background: #dcfce7; color: #15803d; border: 1px solid #86efac; }
.pill-empty   { background: #f1f5f9; color: #64748b; border: 1px solid #cbd5e1; }
.pill-refill  { background: #fdf2f8; color: #be185d; border: 1px solid #f472b6; font-weight: 800; }

/* テーブルの行装飾 */
.row-ordered {
    background-color: rgba(148, 163, 184, 0.15) !important;
    opacity: 0.65;
}

/* ボタン調整 */
div.stButton > button:first-child {
    border-radius: 8px;
    font-weight: 600;
    transition: all 0.15s ease;
}
</style>
"""
st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

# ============================================================
# 2. 定数 & 既定設定
# ============================================================
DEFAULT_SPREADSHEET_ID = "175sKtMVVp6IgqrzLcRtO5tX7t-wiEKQrrfagfRoH1gM"
APP_VERSION = "v2.0.0-Cloud"

# ============================================================
# 3. ユーティリティ & データ正規化
# ============================================================
def parse_qty_safe(v: Any) -> Optional[float]:
    """在庫表記を株数に正規化。万単位、記号、文字列表記に対応。"""
    if v is None or pd.isna(v):
        return None
    if isinstance(v, (int, float)):
        return float(v)
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
    """コードを4桁ゼロ埋め文字列に正規化"""
    if v is None or pd.isna(v):
        return ""
    s = str(v).split(".")[0].strip()
    return s.zfill(4) if len(s) <= 4 and s.isdigit() else s

def fmt_qty(v: Optional[float]) -> str:
    """株数の見やすいフォーマット"""
    if v is None or pd.isna(v):
        return "―"
    v = float(v)
    if v >= 10000:
        return f"{v/10000:.1f}万"
    return f"{int(v):,}"

# ============================================================
# 4. データ読み込み（Googleスプレッドシート & オンデマンド実行）
# ============================================================
@st.cache_data(ttl=60, show_spinner=False)
def fetch_sheet_csv(sheet_name: str, spreadsheet_id: str = DEFAULT_SPREADSHEET_ID) -> Optional[pd.DataFrame]:
    """Googleスプレッドシートから gviz/tq でCSVを認証不要で直接取得"""
    url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/gviz/tq?tqx=out:csv&sheet={urllib.parse.quote(sheet_name)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            content = resp.read()
            df = pd.read_csv(io.BytesIO(content))
            return df
    except Exception:
        return None

def normalize_history(df: pd.DataFrame) -> pd.DataFrame:
    """旧形式(13列)・新形式(20列)の両形式を統一スキーマへ正規化"""
    if df is None or df.empty:
        return pd.DataFrame()
    d = df.copy()

    # カラム名マッピング（日本語揺れ吸収）
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

    # コード正規化
    if "code" in d.columns:
        d["code"] = d["code"].apply(fmt_code)

    # 数値在庫の正規化
    for col in ["nikko", "rakuten", "kabu"]:
        if col in d.columns:
            d[col] = d[col].apply(parse_qty_safe)
        else:
            d[col] = None

    # 日時ソート用
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
# 5. 分析・シグナル算出エンジン
# ============================================================
def analyze_stocks(
    df_hist: pd.DataFrame,
    df_mast: Optional[pd.DataFrame] = None,
    nikko_th: float = 10000.0,
    annual_rate: float = 0.011,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """最新スナップショットと前回値からシグナル・急変・前日比を総合算出"""
    if df_hist is None or df_hist.empty:
        return pd.DataFrame(), {}

    # ユニークな取得日時を取得 (最新2回分)
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

        # 各社最新在庫
        nikko_now = row.get("nikko")
        rakuten_now = row.get("rakuten")
        kabu_now = row.get("kabu")
        sbi_now = str(row.get("rtn_sbi") or row.get("sbi") or "―").strip()
        gmo_now = str(row.get("gmo") or "―").strip()
        matsui_now = str(row.get("matsui") or "―").strip()
        monex_now = str(row.get("monex") or "―").strip()

        # 各社前回在庫
        nikko_prev = prev_row.get("nikko") if prev_row is not None else None
        rakuten_prev = prev_row.get("rakuten") if prev_row is not None else None
        sbi_prev = str(prev_row.get("rtn_sbi") or prev_row.get("sbi") or "―").strip() if prev_row is not None else "―"

        # 1. 日興前日比（最新 - 前回）
        if nikko_now is not None and nikko_prev is not None:
            nikko_diff = nikko_now - nikko_prev
        else:
            nikko_diff = None

        # 2. SBI急変検知 (◎→▲ / ◎→×)
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

        # 3. 補充検知 (前回0 → 今回プラス)
        is_refill = False
        if prev_ts:
            was_zero = (nikko_prev is not None and nikko_prev == 0) or (rakuten_prev is not None and rakuten_prev == 0)
            now_has = (nikko_now is not None and nikko_now > 0) or (rakuten_now is not None and rakuten_now > 0)
            if was_zero and now_has:
                is_refill = True

        # 4. 日興ヒートマップ判定
        if nikko_now is None:
            nikko_heat = "none"
        elif nikko_now >= 10000:
            nikko_heat = "rich"    # 緑
        elif nikko_now >= 1000:
            nikko_heat = "medium"  # 黄
        elif nikko_now > 0:
            nikko_heat = "low"     # 橙
        else:
            nikko_heat = "zero"    # グレー

        # 5. 合計在庫
        valid_qtys = [q for q in [nikko_now, rakuten_now, kabu_now] if q is not None]
        total_qty = sum(valid_qtys) if valid_qtys else None

        # 6. 意思決定シグナル判定
        # 🔴今夜確保: SBI急変/瞬殺 かつ 日興 <= 閾値
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
            signal = "⚪ 枯渇" if total_qty == 0 else "🟡 要監視"
            signal_rank = 3

        # 7. 貸株コスト & 実質純利益 & 限界日
        yutai_val = row.get("yutai_value") or m_row.get("yutai_value")
        funds_man = row.get("funds_man") or m_row.get("funds_man")
        days_left_raw = str(row.get("days_left") or "10").replace("D-", "")
        try:
            d_n = int(days_left_raw)
        except ValueError:
            d_n = 10

        kabuka = row.get("kabuka") or ((float(funds_man) * 10000 / 100) if funds_man else None)
        kabusu = row.get("kabusu") or 100

        cost = None
        net_profit = None
        limit_days = None

        if kabuka and kabusu and d_n:
            try:
                principal = float(kabuka) * float(kabusu)
                daily_cost = principal * annual_rate / 365.0
                cost = round(daily_cost * d_n)
                if yutai_val and float(yutai_val) > 0:
                    net_profit = round(float(yutai_val) - cost)
                    if daily_cost > 0:
                        limit_days = int(float(yutai_val) / daily_cost)
            except Exception:
                pass

        # 監視・優先度
        watch = bool(m_row.get("watch", True))
        priority = m_row.get("priority", 1)

        results.append({
            "code": code,
            "name": name,
            "signal": signal,
            "signal_rank": signal_rank,
            "refill": "🔥 補充" if is_refill else "",
            "is_refill": is_refill,
            "sbi_alert": sbi_alert,
            "is_sbi_drop": is_sbi_sudden_drop,
            "nikko_now": nikko_now,
            "nikko_prev": nikko_prev,
            "nikko_diff": nikko_diff,
            "nikko_heat": nikko_heat,
            "rakuten_now": rakuten_now,
            "kabu_now": kabu_now,
            "sbi_now": sbi_now,
            "gmo_now": gmo_now,
            "matsui_now": matsui_now,
            "monex_now": monex_now,
            "total_qty": total_qty,
            "funds_man": float(funds_man) if funds_man and not pd.isna(funds_man) else None,
            "yutai_value": float(yutai_val) if yutai_val and not pd.isna(yutai_val) else None,
            "yutai_content": m_row.get("yutai_content") or "",
            "yield_pct": float(m_row.get("yield_pct")) if m_row.get("yield_pct") and not pd.isna(m_row.get("yield_pct")) else None,
            "net_profit": net_profit,
            "cost": cost,
            "limit_days": limit_days,
            "days_left": d_n,
            "rights_month": row.get("rights_month") or m_row.get("rights_month") or "",
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
        "watch_count": sum(1 for r in results if r["watch"]),
    }
    return df_res, stats

# ============================================================
# 6. メインUIレンダリング
# ============================================================
def main():
    # サイドバー設定
    with st.sidebar:
        st.markdown("### ⚙️ 設定 & フィルター")
        sheet_id = st.text_input("Google スプレッドシートID", value=DEFAULT_SPREADSHEET_ID)

        st.markdown("---")
        st.markdown("#### 🎯 実戦シグナル絞り込み")
        signal_filter = st.multiselect(
            "シグナル選択",
            options=["🔴 今夜確保", "🔥 補充", "🚨 SBI急変", "🔴 即確保", "🟡 要監視", "🟢 待機可", "⚪ 枯渇"],
            default=[]
        )

        only_watch = st.checkbox("監視中のみ表示 (master_list)", value=False)
        only_nikko_has = st.checkbox("日興在庫ありのみ", value=False)

        st.markdown("---")
        st.markdown("#### 📊 資金・利回り条件")
        max_funds = st.slider("必要資金 上限 (万円)", min_value=1, max_value=200, value=100, step=5)
        min_yield = st.slider("利回り 下限 (%)", min_value=0.0, max_value=10.0, value=0.0, step=0.2)

        st.markdown("---")
        st.markdown("#### ⚙️ 判定閾値")
        nikko_th = st.number_input("日興 警戒閾値 (株)", min_value=1000, max_value=100000, value=10000, step=1000)
        annual_rate = st.number_input("貸株料率 (年率)", min_value=0.001, max_value=0.05, value=0.011, step=0.001, format="%.3f")

        st.markdown("---")
        st.caption(f"Yutai Cross Tracker {APP_VERSION}")

    # データ読み込み
    with st.spinner("スプレッドシートより最新データを取得中..."):
        raw_hist = fetch_sheet_csv("raw_history", spreadsheet_id=sheet_id)
        raw_mast = fetch_sheet_csv("master_list", spreadsheet_id=sheet_id)

    if raw_hist is None or raw_hist.empty:
        st.error(f"⚠️ スプレッドシート (ID: `{sheet_id}`) から `raw_history` を取得できませんでした。共有設定（リンクを知っている全員が閲覧可）を確認してください。")
        return

    df_hist = normalize_history(raw_hist)
    df_mast = normalize_master(raw_mast) if raw_mast is not None else None

    # 分析エンジン実行
    df_analyzed, stats = analyze_stocks(df_hist, df_mast, nikko_th=nikko_th, annual_rate=annual_rate)

    # ヘッダー領域
    st.markdown(f"""
    <div class="header-container">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 1rem;">
            <div>
                <h1 class="header-title">📈 株主優待クロス在庫トラッカー</h1>
                <div class="header-subtitle">日興主軸推移 × SBI急変検知 × 2大優待サイト網羅による今夜確保の意思決定支援</div>
            </div>
            <div style="text-align: right;">
                <span class="badge-tag badge-primary">権利年月: 2026-09</span>
                <span class="badge-tag badge-success">最新取得: {stats.get('latest_ts', '―')} JST</span>
                {f"<span class='badge-tag badge-warning'>前回取得: {stats.get('prev_ts', '―')} JST</span>" if stats.get('prev_ts') else ""}
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # アクションバー (リフレッシュ & リアルタイムスクレイピング)
    c_btn1, c_btn2, c_space = st.columns([1.5, 2, 4])
    with c_btn1:
        if st.button("🔄 キャッシュ更新", use_container_width=True):
            st.cache_data.clear()
            st.rerun()
    with c_btn2:
        if st.button("⚡ オンデマンド即時スクレイピング", use_container_width=True, help="Streamlit Cloud上で直接routine & gokigenから最新在庫を取得"):
            with st.spinner("各サイトから最新データを取得中..."):
                try:
                    import config as cfg
                    from scrapers.routine_yutai import fetch_routine
                    from scrapers.gokigen_life import fetch_gokigen
                    from core.merger import build_rows
                    info = cfg.get_rights_info(None, None)
                    r_data, _ = fetch_routine(info["routine_url"])
                    g_data, _ = fetch_gokigen(info["api_month"])
                    st.success(f"取得成功！ (ルーティン: {len(r_data)}件, Gokigen: {len(g_data)}件)")
                    st.info("※定期実行はGASトリガー（毎日17:00/20:00）でスプレッドシートへ自動保存されます。")
                except Exception as ex:
                    st.error(f"即時取得エラー: {ex}")

    # KPIサマリーカード
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        t_cnt = stats.get('tonight_count', 0)
        st.markdown(f"""
        <div class="metric-card" style="{ 'border-color: #ef4444; background: #fff5f5;' if t_cnt > 0 else '' }">
            <div class="metric-label" style="{ 'color: #dc2626;' if t_cnt > 0 else '' }">🔴 今夜確保アラート</div>
            <div class="metric-value" style="{ 'color: #dc2626;' if t_cnt > 0 else '' }">{t_cnt} <span style="font-size: 1rem; font-weight: 500;">銘柄</span></div>
            <div class="metric-sub">SBI急変/瞬殺 かつ 日興残少</div>
        </div>
        """, unsafe_allow_html=True)

    with k2:
        r_cnt = stats.get('refill_count', 0)
        st.markdown(f"""
        <div class="metric-card" style="{ 'border-color: #ec4899; background: #fdf2f8;' if r_cnt > 0 else '' }">
            <div class="metric-label" style="{ 'color: #db2777;' if r_cnt > 0 else '' }">🔥 在庫補充検知</div>
            <div class="metric-value" style="{ 'color: #db2777;' if r_cnt > 0 else '' }">{r_cnt} <span style="font-size: 1rem; font-weight: 500;">銘柄</span></div>
            <div class="metric-sub">前回0 → 今回プラス復活</div>
        </div>
        """, unsafe_allow_html=True)

    with k3:
        s_cnt = stats.get('sbi_drop_count', 0)
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">🚨 SBI急変・瞬殺</div>
            <div class="metric-value">{s_cnt} <span style="font-size: 1rem; font-weight: 500;">銘柄</span></div>
            <div class="metric-sub">◎→▲ (急変) / ◎→× (瞬殺)</div>
        </div>
        """, unsafe_allow_html=True)

    with k4:
        st.markdown(f"""
        <div class="metric-card">
            <div class="metric-label">総追跡 / 監視中銘柄</div>
            <div class="metric-value">{stats.get('total_count', 0)} <span style="font-size: 1rem; font-weight: 500;">件</span></div>
            <div class="metric-sub">監視ON: {stats.get('watch_count', 0)} 件</div>
        </div>
        """, unsafe_allow_html=True)

    st.markdown("<div style='height: 15px;'></div>", unsafe_allow_html=True)

    # フィルタリング処理
    filtered_df = df_analyzed.copy()

    if only_watch:
        filtered_df = filtered_df[filtered_df["watch"] == True]

    if only_nikko_has:
        filtered_df = filtered_df[filtered_df["nikko_now"].fillna(0) > 0]

    if max_funds < 200:
        filtered_df = filtered_df[filtered_df["funds_man"].fillna(0) <= max_funds]

    if min_yield > 0:
        filtered_df = filtered_df[filtered_df["yield_pct"].fillna(0) >= min_yield]

    if signal_filter:
        cond = pd.Series([False] * len(filtered_df), index=filtered_df.index)
        if "🔴 今夜確保" in signal_filter:
            cond |= (filtered_df["signal"] == "🔴 今夜確保")
        if "🔥 補充" in signal_filter:
            cond |= (filtered_df["is_refill"] == True)
        if "🚨 SBI急変" in signal_filter:
            cond |= (filtered_df["is_sbi_drop"] == True)
        if "🔴 即確保" in signal_filter:
            cond |= (filtered_df["signal"] == "🔴 即確保")
        if "🟡 要監視" in signal_filter:
            cond |= (filtered_df["signal"] == "🟡 要監視")
        if "🟢 待機可" in signal_filter:
            cond |= (filtered_df["signal"] == "🟢 待機可")
        if "⚪ 枯渇" in signal_filter:
            cond |= (filtered_df["signal"] == "⚪ 枯渇")
        filtered_df = filtered_df[cond]

    # メインタブ
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📋 実戦ダッシュボード",
        "📊 日興推移チャート",
        "🚨 急変・補充ピックアップ",
        "📁 全履歴・マスタ検索",
        "☁️ 自宅サーバーレス運用",
    ])

    # ----------------------------------------------------
    # TAB 1: 実戦ダッシュボード
    # ----------------------------------------------------
    with tab1:
        st.markdown("#### ⚡ 優待クロス意思決定テーブル")

        # 検索ボックス & 並び順
        col_s1, col_s2, col_s3 = st.columns([3, 2, 2])
        with col_s1:
            query = st.text_input("🔍 銘柄検索 (コード・銘柄名・優待内容)", placeholder="例: 9831, ヤマダ, ギフトカード...")
        with col_s2:
            sort_by = st.selectbox("並び順", [
                "シグナル優先度 (今夜確保→即確保)",
                "日興在庫が多い順",
                "日興在庫が少ない順 (枯渇寸前)",
                "利回りが高い順",
                "必要資金が少ない順",
                "コード順"
            ])
        with col_s3:
            st.metric("該当銘柄数", f"{len(filtered_df)} 件")

        # 検索適用
        if query:
            q = query.strip().lower()
            filtered_df = filtered_df[
                filtered_df["code"].astype(str).str.lower().str.contains(q) |
                filtered_df["name"].astype(str).str.lower().str.contains(q) |
                filtered_df["yutai_content"].astype(str).str.lower().str.contains(q)
            ]

        # ソート適用
        if sort_by == "シグナル優先度 (今夜確保→即確保)":
            filtered_df = filtered_df.sort_values(by=["signal_rank", "nikko_now"], ascending=[True, True])
        elif sort_by == "日興在庫が多い順":
            filtered_df = filtered_df.sort_values(by="nikko_now", ascending=False)
        elif sort_by == "日興在庫が少ない順 (枯渇寸前)":
            filtered_df = filtered_df.sort_values(by="nikko_now", ascending=True)
        elif sort_by == "利回りが高い順":
            filtered_df = filtered_df.sort_values(by="yield_pct", ascending=False)
        elif sort_by == "必要資金が少ない順":
            filtered_df = filtered_df.sort_values(by="funds_man", ascending=True)
        elif sort_by == "コード順":
            filtered_df = filtered_df.sort_values(by="code", ascending=True)

        # 表示用DataFrameの成形
        display_rows = []
        for _, r in filtered_df.iterrows():
            # 日興前日比の表記
            diff = r["nikko_diff"]
            if diff is None:
                diff_str = "―"
            elif diff > 0:
                diff_str = f"🟢 +{int(diff):,}"
            elif diff < 0:
                diff_str = f"🔴 {int(diff):,}"
            else:
                diff_str = "±0"

            display_rows.append({
                "コード": r["code"],
                "銘柄名": r["name"],
                "意思決定シグナル": r["signal"],
                "補充": r["refill"],
                "SBI急変": r["sbi_alert"],
                "日興最新": fmt_qty(r["nikko_now"]),
                "日興前日比": diff_str,
                "カブ最新": fmt_qty(r["kabu_now"]),
                "楽天最新": fmt_qty(r["rakuten_now"]),
                "SBI": r["sbi_now"],
                "GMO": r["gmo_now"],
                "優待価値(円)": f"{int(r['yutai_value']):,}" if r["yutai_value"] else "―",
                "資金(万)": f"{r['funds_man']:.1f}" if r["funds_man"] else "―",
                "純利益(円)": f"{int(r['net_profit']):,}" if r["net_profit"] is not None else "―",
                "限界日": f"D-{r['limit_days']}" if r["limit_days"] is not None else "―",
                "優待内容": r["yutai_content"][:30] if r["yutai_content"] else "―"
            })

        df_table = pd.DataFrame(display_rows)
        st.dataframe(
            df_table,
            use_container_width=True,
            hide_index=True,
            height=580,
            column_config={
                "コード": st.column_config.TextColumn("コード", width="small"),
                "銘柄名": st.column_config.TextColumn("銘柄名", width="medium"),
                "意思決定シグナル": st.column_config.TextColumn("シグナル", width="medium"),
                "補充": st.column_config.TextColumn("補充", width="small"),
                "SBI急変": st.column_config.TextColumn("SBI急変", width="medium"),
                "日興最新": st.column_config.TextColumn("日興最新", width="small"),
                "日興前日比": st.column_config.TextColumn("日興前日比", width="small"),
                "カブ最新": st.column_config.TextColumn("カブ", width="small"),
                "楽天最新": st.column_config.TextColumn("楽天", width="small"),
                "SBI": st.column_config.TextColumn("SBI", width="small"),
                "GMO": st.column_config.TextColumn("GMO", width="small"),
            }
        )

        # 選択銘柄の詳細ドリルダウン
        st.markdown("---")
        st.markdown("#### 🔍 銘柄ドリルダウン詳細")
        target_code = st.selectbox("詳細を表示する銘柄を選択", options=filtered_df["code"].tolist(), format_func=lambda c: f"{c} - {filtered_df[filtered_df['code']==c]['name'].values[0] if len(filtered_df[filtered_df['code']==c]) > 0 else ''}")
        if target_code:
            st_data = filtered_df[filtered_df["code"] == target_code].iloc[0]
            d1, d2, d3, d4 = st.columns(4)
            d1.metric("日興最新在庫", fmt_qty(st_data["nikko_now"]), delta=st_data["nikko_diff"])
            d2.metric("楽天在庫", fmt_qty(st_data["rakuten_now"]))
            d3.metric("カブコム在庫", fmt_qty(st_data["kabu_now"]))
            d4.metric("SBI信号", st_data["sbi_now"], delta=st_data["sbi_alert"])

            # 過去履歴チャート
            hist_sub = df_hist[df_hist["code"] == target_code].copy()
            if not hist_sub.empty and len(hist_sub) > 1:
                chart = alt.Chart(hist_sub).mark_line(point=True).encode(
                    x=alt.X("timestamp:N", title="取得日時"),
                    y=alt.Y("nikko:Q", title="日興在庫 (株)"),
                    tooltip=["timestamp", "nikko", "rakuten", "kabu"]
                ).properties(title=f"{st_data['name']} ({target_code}) 在庫推移", height=240)
                st.altair_chart(chart, use_container_width=True)

    # ----------------------------------------------------
    # TAB 2: 日興推移チャート
    # ----------------------------------------------------
    with tab2:
        st.markdown("#### 📈 日興在庫 推移トラッキング（直近履歴）")
        st.caption("直近スナップショットにおける日興在庫の変化を可視化します。")

        # 複数銘柄の比較
        multi_codes = st.multiselect(
            "推移グラフに表示する銘柄を選択 (複数可)",
            options=df_analyzed["code"].tolist(),
            default=df_analyzed[df_analyzed["nikko_now"].fillna(0) > 0]["code"].head(5).tolist(),
            format_func=lambda c: f"{c} - {df_analyzed[df_analyzed['code']==c]['name'].values[0] if len(df_analyzed[df_analyzed['code']==c])>0 else ''}"
        )

        if multi_codes:
            sub = df_hist[df_hist["code"].isin(multi_codes)].copy()
            if not sub.empty:
                chart_multi = alt.Chart(sub).mark_line(point=True).encode(
                    x=alt.X("timestamp:N", title="取得日時"),
                    y=alt.Y("nikko:Q", title="日興在庫 (株)"),
                    color=alt.Color("name:N", title="銘柄名"),
                    tooltip=["name", "code", "timestamp", "nikko", "rakuten"]
                ).properties(height=420)
                st.altair_chart(chart_multi, use_container_width=True)
            else:
                st.info("選択された銘柄の履歴データがありません。")

    # ----------------------------------------------------
    # TAB 3: 急変・補充ピックアップ
    # ----------------------------------------------------
    with tab3:
        st.markdown("#### 🚨 SBI急変・瞬殺 ＆ 🔥 在庫補充 特集")
        st.caption("在庫の急減や急な復活が発生した「今アクションすべき」注目銘柄一覧です。")

        c_alert1, c_alert2 = st.columns(2)
        with c_alert1:
            st.markdown("##### 🚨 SBI急変・瞬殺 銘柄")
            df_sbi_drop = df_analyzed[df_analyzed["is_sbi_drop"] == True]
            if not df_sbi_drop.empty:
                for _, r in df_sbi_drop.iterrows():
                    st.markdown(f"""
                    <div style="background: #fff5f5; border: 1px solid #fecaca; border-radius: 8px; padding: 0.9rem; margin-bottom: 0.8rem;">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-weight: 700; font-size: 1.05rem;">{r['code']} {r['name']}</span>
                            <span class="pill pill-tonight">{r['sbi_alert']}</span>
                        </div>
                        <div style="margin-top: 0.4rem; font-size: 0.88rem; color: #475569;">
                            日興最新: <b>{fmt_qty(r['nikko_now'])}</b> (前日比: {r['nikko_diff'] or '―'}) | 楽天: {fmt_qty(r['rakuten_now'])}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("現在、SBI急変・瞬殺のアラートはありません。")

        with c_alert2:
            st.markdown("##### 🔥 在庫補充 銘柄")
            df_refill = df_analyzed[df_analyzed["is_refill"] == True]
            if not df_refill.empty:
                for _, r in df_refill.iterrows():
                    st.markdown(f"""
                    <div style="background: #fdf2f8; border: 1px solid #fbcfe8; border-radius: 8px; padding: 0.9rem; margin-bottom: 0.8rem;">
                        <div style="display: flex; justify-content: space-between; align-items: center;">
                            <span style="font-weight: 700; font-size: 1.05rem;">{r['code']} {r['name']}</span>
                            <span class="pill pill-refill">🔥 補充検知</span>
                        </div>
                        <div style="margin-top: 0.4rem; font-size: 0.88rem; color: #475569;">
                            日興最新: <b>{fmt_qty(r['nikko_now'])}</b> | 楽天: {fmt_qty(r['rakuten_now'])}
                        </div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("現在、直近での在庫補充はありません。")

    # ----------------------------------------------------
    # TAB 4: 全履歴・マスタ検索
    # ----------------------------------------------------
    with tab4:
        st.markdown("#### 📁 全履歴データ & CSVエクスポート")
        st.dataframe(df_hist.drop(columns=["dt"], errors="ignore"), use_container_width=True, height=450)

        csv_buf = io.StringIO()
        df_analyzed.to_csv(csv_buf, index=False, encoding="utf-8-sig")
        st.download_button(
            label="📥 分析済みデータをCSVダウンロード",
            data=csv_buf.getvalue(),
            file_name=f"yutai_cross_analyzed_{dt.datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
        )

    # ----------------------------------------------------
    # TAB 5: 自宅サーバーレス運用ガイド
    # ----------------------------------------------------
    with tab5:
        st.markdown("#### ☁️ 自宅サーバーレス運用の仕組み")
        st.markdown("""
        当システムは、自宅PCの電源が切れていても**クラウド上で全自動・完全無料**で動作します。

        ##### 1. 定期自動実行（Google Apps Script: GAS）
        - **実行エンジン**: Google Apps Script (`yutai_gas_full.gs`)
        - **トリガー**: 平日毎日 17:00 / 20:00 JST (市場終了後・夜間争奪戦前)
        - **蓄積先**: Google スプレッドシート (`raw_history` タブへ自動追記)
        - **費用**: 完全無料・クレカ登録不要

        ##### 2. Webダッシュボード（Streamlit Cloud）
        - **URL**: `https://share.streamlit.io` から誰でもスマホ・PCで常時閲覧可能
        - **データ連携**: Googleスプレッドシートの `gviz/tq` API（認証不要・60秒キャッシュ）

        ##### 3. スプレッドシートへの直接リンク
        - [Google スプレッドシートを開く](https://docs.google.com/spreadsheets/d/175sKtMVVp6IgqrzLcRtO5tX7t-wiEKQrrfagfRoH1gM/edit)
        """)

if __name__ == "__main__":
    main()
