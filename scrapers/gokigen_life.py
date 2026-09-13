"""Gokigen Life .TOKYO の在庫JSON APIを直接取得する。

一覧ページ (https://gokigen-life.tokyo/201909yutai-all-list/) 自体は
Stencil製WebComponentが Now Loading 後に描画するためHTMLスクレイピング不可。
裏側のAPIへPOSTすることで全件を一括取得できる (ページング不要・実測9月473件)。

- 一覧: POST https://gokigen-life.tokyo/api/00ForWeb/ForZaiko2.php (payload: month=1..12)
- 文字コード: Shift_JIS (UTF-8で読むと文字化けする)
- [0]の code:"0000" 行はダミーで、nvol〜xvolに各社在庫の更新時刻(epoch ms)が入る
- vol対応 (サイトの会社列挙順と一致): n=日興 k=カブコム r=楽天 s=SBI g=GMO m=松井 x=マネックス
- 実測上の注意: 株数として意味を持つのは n/k/r のみ。
  s/g/m/x は 0/1/2 のステータスコード (分布上 2=あり濃厚・0=なし濃厚) のため数値在庫に混ぜないこと
- 文字列フィールドに文字通り "null" が入ることがあるため空文字化する
- ホスティング側WAFにより短時間の連打は403になる。1実行1POST・低頻度で使うこと
"""
from __future__ import annotations

import json
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

import config


def _session() -> requests.Session:
    s = requests.Session()
    s.headers.update({"User-Agent": config.USER_AGENT})
    retry = Retry(total=3, backoff_factor=2, status_forcelist=[429, 500, 502, 503, 504])
    s.mount("https://", HTTPAdapter(max_retries=retry))
    return s


def _to_num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
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
    """APIが null を文字列 "null" で返す場合があるため空文字化する。"""
    if v is None:
        return ""
    s = str(v).strip()
    return "" if s.lower() in ("", "null", "none") else s


def fetch_gokigen(month: str = config.GOKIGEN_MONTH, timeout: int = 60) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """(レコード一覧, メタ情報) を返す。レコードは code!='0000' のみ。"""
    try:
        resp = _session().post(config.GOKIGEN_API_URL, data={"month": str(month)}, timeout=timeout)
        resp.raise_for_status()
    except requests.HTTPError as e:
        status = e.response.status_code if e.response is not None else "?"
        hint = (" (WAFによるアクセス制限の可能性。短時間の連打を避け、時間をおいて再実行してください)"
                if status == 403 else "")
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
        if not isinstance(r, dict) or not r.get("code") or r.get("code") == "0000":
            continue
        stocks = {label: _to_num(r.get(field)) for field, label in config.BROKERS}
        records.append({
            "code": str(r.get("code")),
            "name": _clean_str(r.get("name")),
            "taisyaku": _clean_str(r.get("taisyaku")),
            "kabuka": _to_num(r.get("kabuka")),
            "kabusu": _to_num(r.get("kabusu")),
            "yutai_type": _clean_str(r.get("yutai_syubetsu")),
            "yutai": _clean_str(r.get("yutai")),
            "rimawari": _to_num(r.get("rimawari")),
            "cross_days": _to_num(r.get("c_nissu")),
            "gyaku_days": _to_num(r.get("gyaku_days")),
            "riron_gyaku": _to_num(r.get("riron_gyaku")),
            "recent_gyaku": _to_num(r.get("recent_gyaku")),
            "recent_gyaku_date": _to_ms_datetime(r.get("recent_gyaku_date")),
            "recent_gyaku_kisei": _clean_str(r.get("recent_gyaku_kisei")),
            "max5_gyaku": _to_num(r.get("max5_gyaku")),
            "avg5_gyaku": _to_num(r.get("avg5_gyaku")),
            "haito": _to_num(r.get("haito")),
            "kenri": _clean_str(r.get("d_kenri")).replace("<br>", " / "),
            "stocks": stocks,
        })
    if not records:
        raise ValueError("Gokigen APIから有効レコードを0件しか取得できませんでした。")
    meta["count"] = len(records)
    return records, meta
