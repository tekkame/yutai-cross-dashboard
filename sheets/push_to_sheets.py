# -*- coding: utf-8 -*-
"""
sheets/push_to_sheets.py - スプレッドシート長期DB同期マネージャー
GitHub Actions または ローカル実行後に、最新の在庫データを Google スプレッドシートへ自動反映します。
"""

from __future__ import annotations

import json
import os
import sys
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8')

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"

def push_latest_to_gas(gas_url: str, secret: str = "yutai777") -> bool:
    """最新の history CSV を読み込んで GAS Webhook 経由でスプレッドシートに反映"""
    if not gas_url:
        print("[SHEETS] GAS_WEBHOOK_URL が設定されていないためスキップします。")
        return False

    h_files = sorted([DATA_DIR / f for f in os.listdir(DATA_DIR) if f.startswith("history_") and f.endswith(".csv")])
    if not h_files:
        print("[SHEETS] 送信対象の history CSV がありません。")
        return False

    latest_file = h_files[-1]
    print(f"[SHEETS] 最新ファイル {latest_file.name} をスプレッドシートへ送信中...")

    import pandas as pd
    df = pd.read_csv(latest_file)
    rows = df.fillna("").values.tolist()

    payload = json.dumps({
        "secret": secret,
        "action": "append_history",
        "rows": rows
    }).encode("utf-8")

    req = urllib.request.Request(
        gas_url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "YutaiSheetsPusher"}
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            print(f"[SHEETS] ✅ 送信成功: {res_data}")
            return True
    except Exception as e:
        print(f"[SHEETS] ⚠️ 送信失敗: {e}")
        return False

if __name__ == "__main__":
    url = os.environ.get("GAS_WEBHOOK_URL", "")
    push_latest_to_gas(url)
