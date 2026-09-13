# -*- coding: utf-8 -*-
"""
scrapers/gokigen_life.py - Gokigen Life .TOKYO 在庫API高精度パーサー

修正仕様 (2):
- 銘柄コード: 4桁数字 (9266, 8356等で銘柄名が取れない不正行は除外)
- 銘柄名: 正式名称 (nan/nullを完全根絶)
- 前日終値: stock_price (kabuka)
- 必要金額: funds_man (株価×株数/10000)
- 優待内容: yutai_content (yutaiフィールド)
- 優待利回り: yield_pct (rimawari * 100)
- 7社在庫状況:
  - 日興(nvol), カブ(kvol), 楽天(rvol) -> 株数数値
  - SBI(svol), GMO(gvol), 松井(mvol), マネックス(xvol) -> 2=◎, 1=▲, 0=×, 数値=◎ (XXXX株)
- 優待価値: public_value/gl_value または優待内容から自動逆算補完
"""

from __future__ import annotations

import json
import re
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import config


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": config.USER_AGENT})
    retry = Retry(total=3, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def _to_num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        val = float(v)
        return None if val != val else val
    except (TypeError, ValueError):
        return None


def _to_ms_datetime(v: Any) -> str:
    """epochミリ秒(13桁)→ 'YYYY-MM-DD HH:mm'。不正値は空文字。"""
    try:
        n = int(float(v))
    except (TypeError, ValueError):
        return ""
    if n < 1_000_000_000_000:
        return ""
    return config.datetime_from_epoch_ms(n)


def _clean_str(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() in ("", "null", "none", "nan") else s


def parse_signal(v: Any) -> str:
    """0/1/2 ステータスコードまたは文字列表記を ◎ / ▲ / × に正規化"""
    if v is None:
        return "―"
    s = str(v).strip()
    if not s or s.lower() in ("null", "none", "nan", "-"):
        return "―"
    if s in ("2", "◎", "短◎"):
        return "◎"
    if s in ("1", "▲", "短▲"):
        return "▲"
    if s in ("0", "×", "✕", "短×", "短✕", "残無"):
        return "×"
    try:
        num = float(s)
        if num >= 100:
            return f"◎ ({int(num):,}株)"
        if num == 2:
            return "◎"
        if num == 1:
            return "▲"
        if num == 0:
            return "×"
    except ValueError:
        pass
    return s


def extract_value_from_text(content: str) -> float | None:
    """優待内容テキストから金額（円相当）を自動逆算"""
    if not content:
        return None
    t = content.replace(",", "").replace(" ", "")
    patterns = [
        r"(\d+)円相当",
        r"(\d+)円分",
        r"(\d+)円",
        r"(\d+)ポイント",
        r"(\d+)P",
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


def fetch_gokigen(month: str = config.GOKIGEN_MONTH, timeout: int = 40) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Gokigen API から全銘柄データを取得・高精度正規化"""
    try:
        resp = _session().post(config.GOKIGEN_API_URL, data={"month": str(month)}, timeout=timeout)
        resp.raise_for_status()
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else "?"
        hint = (" (WAFによるアクセス制限の可能性)" if status == 403 else "")
        raise RuntimeError(f"Gokigen API HTTP {status}{hint}") from e

    data = json.loads(resp.content.decode(config.GOKIGEN_ENCODING))
    if not isinstance(data, list) or not data:
        raise ValueError("Gokigen APIの応答が空でした。")

    dummy = data[0] if isinstance(data[0], dict) else {}
    broker_updated = {label: _to_ms_datetime(dummy.get(field)) for field, label in config.BROKERS}
    meta: dict[str, Any] = {
        "month": str(month),
        "count": 0,
        "broker_updated": broker_updated,
    }

    records: list[dict[str, Any]] = []
    for r in data:
        if not isinstance(r, dict):
            continue

        raw_code = str(r.get("code") or "").strip()
        # 0000ヘッダーや4桁数字以外は除外
        if not re.match(r"^\d{4}$", raw_code):
            continue

        # 銘柄名が取得できない不正行は除外 (nan/null根絶)
        name = _clean_str(r.get("name"))
        if not name:
            continue

        kabuka = _to_num(r.get("kabuka"))
        kabusu = _to_num(r.get("kabusu")) or 100.0

        # 必要金額(万円) = 株価 * 株数 / 10000
        funds_man = None
        if kabuka and kabuka > 0:
            funds_man = round(kabuka * kabusu / 10000, 2)

        # 優待内容
        yutai = _clean_str(r.get("yutai"))

        # 優待価値
        yutai_val = _to_num(r.get("public_value")) or _to_num(r.get("gl_value"))
        if yutai_val is None or yutai_val == 0:
            yutai_val = extract_value_from_text(yutai)

        # 利回り
        rimawari = _to_num(r.get("rimawari"))
        yield_pct = round(rimawari * 100, 2) if rimawari is not None else None
        if (yield_pct is None or yield_pct == 0) and funds_man and yutai_val and funds_man > 0:
            yield_pct = round((yutai_val / (funds_man * 10000)) * 100, 2)

        # 在庫
        nvol = _to_num(r.get("nvol"))
        kvol = _to_num(r.get("kvol"))
        rvol = _to_num(r.get("rvol"))

        sbi_signal = parse_signal(r.get("svol"))
        gmo_signal = parse_signal(r.get("gvol"))
        matsui_signal = parse_signal(r.get("mvol"))
        monex_signal = parse_signal(r.get("xvol"))

        records.append({
            "code": raw_code,
            "name": name,
            "stock_price": kabuka,
            "kabuka": kabuka,
            "kabusu": kabusu,
            "funds_man": funds_man,
            "yutai_content": yutai,
            "yutai": yutai,
            "yutai_value": yutai_val,
            "yield_pct": yield_pct,
            "rimawari": rimawari,
            "nikko_qty": nvol,
            "kabu_qty": kvol,
            "rakuten_qty": rvol,
            "sbi_signal": sbi_signal,
            "gmo_signal": gmo_signal,
            "matsui_signal": matsui_signal,
            "monex_signal": monex_signal,
            "stocks": {
                "日興": nvol, "カブ": kvol, "楽天": rvol,
                "SBI": sbi_signal, "GMO": gmo_signal,
                "松井": matsui_signal, "マネ": monex_signal,
            },
            "taisyaku": _clean_str(r.get("taisyaku")),
            "cross_days": _to_num(r.get("c_nissu")),
            "max5_gyaku": _to_num(r.get("max5_gyaku")),
            "recent_gyaku_kisei": _clean_str(r.get("recent_gyaku_kisei")),
        })

    if not records:
        raise ValueError("Gokigen APIから有効レコードを0件しか取得できませんでした。")

    meta["count"] = len(records)
    return records, meta
