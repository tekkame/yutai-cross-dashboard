"""ルーティン株主優待 (yutai.enjoy-lcl.com) の静的HTMLテーブルをパースする。

ページ構成 (実測):
- 投資金額帯別の <h2>見出し + <table> が6組 (〜10万 / 10〜20万 / ... / 100万超)
- 各行11列: コード / 銘柄名(+詳細リンク) / 資金(万円) / 優待価値(円) /
  優待内容 / 利回り(%) / 楽天在庫 / eスマ在庫 / 日興在庫 / SBI信号(◎▲×) / GMO売建上限
- 右5列は取得日16時台のスナップショット概数。SBI列は数値ではなく ◎=在庫十分 /
  ▲=残少 / ×=なし の信号 (サイトに凡例なし、分布からの推定)。
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
    retry = Retry(total=3, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def _cell_text(td) -> str:
    return td.get_text(separator=" ", strip=True).replace("\xa0", "").strip()


def parse_qty(raw: str) -> float | None:
    """在庫表記を株数に正規化。大量→None(豊富)、残無/0/×→0、空→None。"""
    s = (raw or "").replace(" ", "").replace(",", "").replace("　", "")
    if not s or s in ("-", "―", "ー"):
        return None
    if "大量" in s:
        return None
    if "残無" in s or s in ("×", "✕"):
        return 0
    if s in ("◎", "▲"):
        return None
    m = re.match(r"^([\d.]+)万$", s)
    if m:
        return round(float(m.group(1)) * 10000)
    m = re.match(r"^([\d.]+)$", s)
    if m:
        return float(m.group(1))
    m = re.search(r"([\d.]+)万", s)
    if m:
        return round(float(m.group(1)) * 10000)
    return None


def parse_sbi(raw: str) -> str:
    s = (raw or "").replace(" ", "")
    if "◎" in s:
        return "◎"
    if "▲" in s:
        return "▲"
    if "×" in s or "✕" in s:
        return "×"
    return s


def _num(raw: str) -> float | None:
    m = re.search(r"[\d.]+", (raw or "").replace(",", ""))
    return float(m.group(0)) if m else None


def _band_label(h2text: str) -> str:
    t = re.sub(r"\s+", "", h2text)
    if "10万円以下" in t:
        return "〜10万円"
    if "10万円超" in t:
        return "10-20万円"
    if "20万円超" in t:
        return "20-30万円"
    if "30万円超" in t:
        return "30-50万円"
    if "50万円超" in t:
        return "50-100万円"
    if "100万円超" in t:
        return "100万円超"
    return t[:20]


def fetch_routine(url: str = config.ROUTINE_URL, timeout: int = 30) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """全銘柄レコードとメタ情報(基準日など)を返す。"""
    html = _session().get(url, timeout=timeout).text
    soup = BeautifulSoup(html, "lxml")
    text = soup.get_text(separator=" ")

    m = re.search(r"(20\d{2})年(\d{1,2})月(\d{1,2})日", text)
    base_date = f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else ""
    meta: dict[str, Any] = {"base_date": base_date, "url": url}

    records: list[dict[str, Any]] = []
    for h2 in soup.find_all("h2"):
        label = _band_label(h2.get_text())
        if label not in BAND_LABELS:
            continue
        table = h2.find_next("table")
        if table is None:
            continue
        for tr in table.find_all("tr"):
            if tr.find("th"):
                continue
            tds = tr.find_all(["td", "th"])
            if len(tds) < 11:
                continue
            code = re.sub(r"\D", "", _cell_text(tds[0]))
            if not re.fullmatch(r"\d{4}", code):
                continue
            a = tds[1].find("a", href=True)
            name = _cell_text(a) if a else _cell_text(tds[1])
            detail_url = a["href"] if a else ""
            rakuten_raw = _cell_text(tds[6])
            esuma_raw = _cell_text(tds[7])
            nikko_raw = _cell_text(tds[8])
            sbi_raw = _cell_text(tds[9])
            gmo_raw = _cell_text(tds[10])
            records.append({
                "code": code,
                "name": name,
                "detail_url": detail_url,
                "band": label,
                "funds_man": _num(_cell_text(tds[2])),
                "yutai_value": _num(_cell_text(tds[3])),
                "yutai_content": _cell_text(tds[4]),
                "yield_pct": _num(_cell_text(tds[5])),
                "rakuten_raw": rakuten_raw,
                "rakuten_qty": parse_qty(rakuten_raw),
                "esuma_raw": esuma_raw,
                "esuma_qty": parse_qty(esuma_raw),
                "nikko_raw": nikko_raw,
                "nikko_qty": parse_qty(nikko_raw),
                "sbi_signal": parse_sbi(sbi_raw),
                "gmo_raw": gmo_raw,
                "gmo_limit": parse_qty(gmo_raw),
            })
    if not records:
        raise ValueError("銘柄テーブルを0件しか取得できませんでした。サイト構造変更の可能性あり。")
    # コード重複があれば後勝ちで統合
    merged = {r["code"]: r for r in records}
    return list(merged.values()), meta
