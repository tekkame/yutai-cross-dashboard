"""メインオーケストレーション: 取得→結合→履歴/マスター行の生成→Sheets更新 or CSV出力。

使い方:
  python main.py --dry-run                      # 権利月自動解決 + CSV出力
  python main.py --rights 2026-10               # 10月権利を指定
  python main.py --rights 2026-10 --kengi 2026-10-29  # 権利付最終日を上書き
  python main.py --auto-watch "yield>=1,funds<=30,rakuten>0"  # 新規行の監視を自動ON
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys

import config
from core.merger import build_rows, master_to_rows, parse_watch
from scrapers.gokigen_life import fetch_gokigen
from scrapers.routine_yutai import fetch_routine


def run(dry_run: bool, out_dir: str, rights_arg: str | None,
        kengi_arg: str | None, watch_expr: str | None) -> int:
    info = config.get_rights_info(rights_arg, kengi_arg)
    rights, kengi = info["rights"], info["kengi"]
    today = config.now_jst().date()
    stamp = config.now_jst().strftime("%Y-%m-%d %H:%M")
    d_n = config.business_days_left(today, kengi)

    print(f"[main] {stamp} JST 権利月={rights} 権利付最終日={kengi} D-{d_n}", flush=True)
    try:
        routine, rmeta = fetch_routine(info["routine_url"], timeout=20)
        print(f"[main] routine: {len(routine)}件 (サイト基準日={rmeta.get('base_date')})", flush=True)
    except Exception as e:
        print(f"[main] WARN routine取得失敗(海外IPブロック等のためgokigenのみで継続): {e}", file=sys.stderr)
        routine, rmeta = [], {}

    try:
        gokigen, gmeta = fetch_gokigen(info["api_month"])
        print(f"[main] gokigen: {gmeta['count']}件", flush=True)
    except Exception as e:
        print(f"[main] WARN gokigen取得失敗(在庫なしで継続): {e}", file=sys.stderr)
        gokigen, gmeta = [], {}

    gmap = {g["code"]: g for g in gokigen}
    history, master = build_rows(rights, today, stamp, d_n, kengi, routine, gmap)
    print(f"[main] join(Full Outer): history {len(history)}件 "
          f"(routine {len(routine)}件中 gokigen突合 {sum(1 for r in routine if r['code'] in gmap)}件, "
          f"gokigen-only {len(gmap) - sum(1 for r in routine if r['code'] in gmap)}件含む)",
          flush=True)

    if watch_expr:
        pred = parse_watch(watch_expr)
        n = sum(1 for m in master if pred(m))
        for m in master:
            m["watch"] = bool(pred(m))
        print(f"[main] auto-watch: {n}件を監視ON", flush=True)

    if dry_run:
        import pandas as pd

        if not history:
            print("[main] ERROR: 取得レコードが0件のためCSVを出力しません"
                  "（両ソースの取得失敗の可能性。直前のWARNを確認してください）",
                  file=sys.stderr, flush=True)
            return 2
        os.makedirs(out_dir, exist_ok=True)
        tag = config.now_jst().strftime("%Y%m%d-%H%M")
        pd.DataFrame(history, columns=config.HISTORY_HEADERS).to_csv(
            f"{out_dir}/history_{rights}_{tag}.csv", index=False, encoding="utf-8-sig")
        pd.DataFrame(master_to_rows(master), columns=config.MASTER_HEADERS).to_csv(
            f"{out_dir}/master_{rights}_{tag}.csv", index=False, encoding="utf-8-sig")
        print(f"[main] dry-run: CSV出力 → {out_dir}/", flush=True)
        return 0

    from sheets.updater import update_spreadsheet
    update_spreadsheet(history, master_to_rows(master), rights)
    print("[main] sheets更新完了", flush=True)
    return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="Sheetsに触らずCSV出力のみ")
    ap.add_argument("--out-dir", default="out")
    ap.add_argument("--rights", default=None, help="対象権利月 YYYY-MM (省略時は自動解決)")
    ap.add_argument("--kengi", default=None, help="権利付最終日 YYYY-MM-DD (省略時は自動算出)")
    ap.add_argument("--auto-watch", default=None,
                    help="新規行の監視自動ON条件 (例: 'yield>=1,funds<=30,rakuten>0')")
    args = ap.parse_args()
    sys.exit(run(args.dry_run, args.out_dir, args.rights, args.kengi, args.auto_watch))


if __name__ == "__main__":
    main()
