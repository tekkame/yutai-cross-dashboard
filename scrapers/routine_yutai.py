# -*- coding: utf-8 -*-
"""
scrapers/routine_yutai.py - ルーティン株主優待 (yutai.enjoy-lcl.com) の静的HTMLテーブル高精度パーサー

修正仕様 (1):
- cells[0]: 銘柄コード (4桁半角数字 ^\\d{4}$ で厳密判定)
- cells[1]: 銘柄名 (略称、aタグや余分なテキストを除去して純粋な文字列化)
- cells[2]: 資金万円 (数値化して funds_man)
- cells[3]: 優待価値円 (数値化して yutai_value、空欄時は優待内容テキストから自動逆算補完)
- cells[4]: 優待内容 (yutai_content)
- cells[5]: 利回り％ (yield_pct)
- cells[6]: 楽天無期在庫 (株数または大量/0)
- cells[7]: eスマ長期在庫 (株数または残無/0)
- cells[8]: 日興在庫 (株数または0、「1.1万」は 11000 に正規化)
- cells[9]: SBI短期 (◎, ▲, × を確実に保持)
- cells[10]: GMO在庫 (株数または ◎, ▲, ×)
- cells[11]: 売建上限株数 (存在する場合。gmo_limit)
"""

from __future__ import annotations

import re
from typing import Any

import requests
from bs4 import BeautifulSoup
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import config

BAND_LABELS = ["〜10万円", "10-20万円", "20-30万円", "30-50万円", "50-100万円", "100万円超"]


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": config.USER_AGENT})
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def _clean_text(td) -> str:
    """HTMLセルから純粋なテキストを抽出"""
    if td is None:
        return ""
    # aタグがある場合はaタグ優先
    a = td.find("a")
    text = a.get_text(strip=True) if a else td.get_text(" ", strip=True)
    return text.replace("\xa0", " ").replace("　", " ").strip()


def parse_qty(raw: str) -> float | None:
    """在庫表記を株数に正規化。「1.1万」→11000、残無/0/×→0、空→None。"""
    s = (raw or "").replace(" ", "").replace(",", "").replace("　", "").strip()
    if not s or s in ("-", "―", "ー", "null", "None", "取扱なし"):
        return None
    if "大量" in s:
        return 9999999.0  # 大量の内部マーカー
    if "残無" in s or s in ("×", "✕", "0"):
        return 0.0
    if s in ("◎", "▲"):
        return None
    m = re.match(r"^([\d.]+)万$", s)
    if m:
        try:
            return round(float(m.group(1)) * 10000)
        except ValueError:
            pass
    m = re.match(r"^([\d.]+)$", s)
    if m:
        try:
            return float(m.group(1))
        except ValueError:
            pass
    m = re.search(r"([\d.]+)万", s)
    if m:
        try:
            return round(float(m.group(1)) * 10000)
        except ValueError:
            pass
    return None


def parse_sbi(raw: str) -> str:
    """SBI列の ◎, ▲, × を厳密に判定"""
    s = (raw or "").replace(" ", "").strip()
    if "◎" in s or "2" in s:
        return "◎"
    if "▲" in s or "1" in s:
        return "▲"
    if "×" in s or "✕" in s or "0" in s or "残無" in s:
        return "×"
    return s if s else "―"


def _num(raw: str) -> float | None:
    """数値文字列からfloatを抽出"""
    s = (raw or "").replace(",", "").replace(" ", "").strip()
    m = re.search(r"[\d.]+", s)
    return float(m.group(0)) if m else None


# 既知の定性優待・割引券・非金銭優待の標準想定価値（円換算フォールバック用）
KNOWN_YUTAI_VALUES: dict[str, float] = {
    "2267": 1000.0,  # ヤクルト本社 (ライト会員入会権)
    "2464": 1000.0,  # Aoba-BBT (割引券10%)
    "2586": 1000.0,  # フルッタフルッタ (EC15%割引)
    "2818": 1000.0,  # ピエトロ (通信販売10%割引)
    "3529": 1000.0,  # アツギ (割引券30%)
    "3569": 1500.0,  # セーレン (割引券20%)
    "3710": 1980.0,  # ジョルダン (乗換案内PREMIUM半年利用権)
    "3769": 1000.0,  # GMOペイメントゲートウェイ (ビットコイン付与)
    "3861": 2000.0,  # 王子HD (植林活動イベント)
    "4051": 1000.0,  # GMOフィナンシャルゲート (ビットコイン付与)
    "4061": 2000.0,  # デンカ (化粧品優待価格販売)
    "4376": 1000.0,  # くふうカンパニーHD (電子利用券・割引券)
    "4539": 1000.0,  # 日本ケミファ (ヘルスケア特別販売)
    "4543": 1000.0,  # テルモ (施設見学会)
    "4719": 500.0,   # アルファS (カレンダー)
    "7638": 1000.0,  # NEW ART HOLDINGS (割引カード)
    "7578": 2000.0,  # ニチリョク (自社商品割引)
    "7752": 1500.0,  # リコー (特別価格販売)
}

def extract_yutai_value(content: str, code: str = "") -> float | None:
    """優待内容テキストから金額（円相当）を自動逆算。既知銘柄コードのフォールバック付き"""
    c_norm = str(code).strip().zfill(4) if code else ""
    if c_norm in KNOWN_YUTAI_VALUES:
        return KNOWN_YUTAI_VALUES[c_norm]

    if not content:
        return None
    t = content.replace(",", "").replace(" ", "").replace("　", "")
    patterns = [
        r"(\d+)円相当",
        r"(\d+)円分",
        r"(\d+)円分",
        r"(\d+)円の?買物券",
        r"(\d+)円の?商品券",
        r"(\d+)円の?ギフト券",
        r"(\d+)円",
        r"(\d+)ポイント",
        r"(\d+)P",
        r"QUO.*?(\d+)円",
        r"クオ.*?(\d+)円",
    ]
    for p in patterns:
        m = re.search(p, t)
        if m:
            try:
                v = float(m.group(1))
                if 100 <= v <= 1000000:
                    return v
            except ValueError:
                pass
    return None


def fetch_routine(url: str = config.ROUTINE_URL, timeout: int = 20) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """全銘柄レコードとメタ情報(基準日など)を高精度パース"""
    resp = _session().get(url, timeout=timeout)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "lxml")
    full_text = soup.get_text(separator=" ")

    m = re.search(r"(20\d{2})年(\d{1,2})月(\d{1,2})日", full_text)
    base_date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else ""
    meta: dict[str, Any] = {"base_date": base_date, "url": url}

    records: list[dict[str, Any]] = []

    for table in soup.find_all("table"):
        for tr in table.find_all("tr"):
            cells = tr.find_all(["td", "th"])
            if len(cells) < 10:
                continue

            # cells[0]: 銘柄コード (4桁半角数字 ^\d{4}$ で厳密判定)
            raw_code = _clean_text(cells[0])
            code_match = re.search(r"^\d{4}$", raw_code)
            if not code_match:
                # 数字のみ抽出して再検証
                digit_only = re.sub(r"\D", "", raw_code)
                if len(digit_only) == 4:
                    code = digit_only
                else:
                    continue
            else:
                code = raw_code

            # cells[1]: 銘柄名
            name = _clean_text(cells[1])
            # ヘッダー行をスキップ
            if name in ("略称 詳細 記事", "銘柄名", "略称"):
                continue

            # cells[2]: 資金万円
            funds_man = _num(_clean_text(cells[2]))

            # cells[4]: 優待内容
            yutai_content = _clean_text(cells[4]) if len(cells) > 4 else ""

            # cells[3]: 優待価値円 (空欄時は自動逆算)
            yutai_value = _num(_clean_text(cells[3])) if len(cells) > 3 else None
            if yutai_value is None:
                yutai_value = extract_yutai_value(yutai_content)

            # cells[5]: 利回り％
            yield_pct = _num(_clean_text(cells[5])) if len(cells) > 5 else None
            # 利回りから優待価値を逆算できる場合 (資金×利回り)
            if yutai_value is None and funds_man and yield_pct and yield_pct > 0:
                yutai_value = round(funds_man * 10000 * (yield_pct / 100))

            # cells[6]: 楽天無期在庫
            rakuten_raw = _clean_text(cells[6]) if len(cells) > 6 else ""
            rakuten_qty = parse_qty(rakuten_raw)

            # cells[7]: eスマ長期在庫
            esuma_raw = _clean_text(cells[7]) if len(cells) > 7 else ""
            esuma_qty = parse_qty(esuma_raw)

            # cells[8]: 日興在庫
            nikko_raw = _clean_text(cells[8]) if len(cells) > 8 else ""
            nikko_qty = parse_qty(nikko_raw)

            # cells[9]: SBI短期 (◎, ▲, × を確実に保持)
            sbi_raw = _clean_text(cells[9]) if len(cells) > 9 else ""
            sbi_signal = parse_sbi(sbi_raw)

            # cells[10]: GMO在庫
            gmo_raw = _clean_text(cells[10]) if len(cells) > 10 else ""
            gmo_qty = parse_qty(gmo_raw)

            # cells[11]: 売建上限株数 (存在する場合)
            if len(cells) > 11:
                gmo_limit_raw = _clean_text(cells[11])
                gmo_limit = parse_qty(gmo_limit_raw)
            else:
                # 11列テーブルの場合、cells[10]に数値があれば上限株数
                gmo_limit = gmo_qty

            records.append({
                "code": code,
                "name": name,
                "funds_man": funds_man,
                "yutai_value": yutai_value,
                "yutai_content": yutai_content,
                "yield_pct": yield_pct,
                "rakuten_raw": rakuten_raw,
                "rakuten_qty": rakuten_qty,
                "esuma_raw": esuma_raw,
                "esuma_qty": esuma_qty,
                "nikko_raw": nikko_raw,
                "nikko_qty": nikko_qty,
                "sbi_signal": sbi_signal,
                "gmo_raw": gmo_raw,
                "gmo_qty": gmo_qty,
                "gmo_limit": gmo_limit,
            })

    if not records:
        raise ValueError("ルーティン株主優待から銘柄テーブルを0件しか取得できませんでした。")

    # 重複コードは後勝ち統合
    merged: dict[str, dict[str, Any]] = {}
    for r in records:
        merged[r["code"]] = r

    return list(merged.values()), meta
