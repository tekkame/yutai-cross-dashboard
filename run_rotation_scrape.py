# -*- coding: utf-8 -*-
"""
run_rotation_scrape.py - アクセスブロック防止型・負荷分散スクレイピングディスパッチャー

【運用方針】
相手サーバー（enjoy-lcl / gokigen-life）への連続集中アクセスを完全に防ぐため、
実行時刻や曜日に応じて取得対象月を分散・ローテーションします。

1. 夕方・夜 (17:00 / 20:00 JST): 【当月】を必ず取得（最重要・毎日2回）
2. 昼 (12:00 JST): 【翌月】を取得（毎日1回・当月と時間をずらす）
3. 深夜・早朝 (04:00 JST): 【翌々月以降 (2〜12ヶ月先)】を曜日ローテーションで1〜2ヶ月ずつ取得
   - 月曜: 2ヶ月先
   - 火曜: 3ヶ月先
   - 水曜: 4ヶ月先
   - 木曜: 5ヶ月先
   - 金曜: 6ヶ月先
   - 土曜: 7〜8ヶ月先
   - 日曜: 9〜11ヶ月先

手動指定も完全サポート:
  python run_rotation_scrape.py --rights 2026-10     # 特定の月を単独取得
  python run_rotation_scrape.py --mode auto          # 時刻・曜日から自動判定（デフォルト）
  python run_rotation_scrape.py --mode current       # 強制的に当月を取得
  python run_rotation_scrape.py --mode next          # 強制的に翌月を取得
  python run_rotation_scrape.py --mode future        # 強制的に本日の曜日ローテーション月を取得
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import sys
import time
from pathlib import Path

# プロジェクトルートのパス解決
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import config
import main as scraper_main
from utils.dates import now_jst, resolve_rights


def get_month_offset(base_y: int, base_m: int, offset: int) -> str:
    """基準年月から offset ヶ月後の YYYY-MM を返す"""
    total_m = base_m + offset
    y = base_y + (total_m - 1) // 12
    m = (total_m - 1) % 12 + 1
    return f"{y}-{m:02d}"


def decide_target_months(mode: str) -> list[str]:
    """実行モードおよび現在時刻・曜日に基づいてスクレイピング対象の権利月リストを決定"""
    now = now_jst()
    today = now.date()
    current_rights, _ = resolve_rights(today)
    curr_y, curr_m = map(int, current_rights.split("-"))

    if mode == "current":
        return [current_rights]
    elif mode == "next":
        return [get_month_offset(curr_y, curr_m, 1)]
    elif mode == "future":
        weekday = now.weekday()  # 0:月, 1:火, 2:水, 3:木, 4:金, 5:土, 6:日
        # 曜日ごとに2〜11ヶ月先を割り当て
        offset_map = {
            0: [2],        # 月曜: 2ヶ月先
            1: [3],        # 火曜: 3ヶ月先
            2: [4],        # 水曜: 4ヶ月先
            3: [5],        # 木曜: 5ヶ月先
            4: [6],        # 金曜: 6ヶ月先
            5: [7, 8],     # 土曜: 7〜8ヶ月先
            6: [9, 10, 11] # 日曜: 9〜11ヶ月先
        }
        offsets = offset_map.get(weekday, [2])
        return [get_month_offset(curr_y, curr_m, off) for off in offsets]

    # mode == "auto" (時刻に基づく自動判定)
    hour = now.hour
    if 15 <= hour <= 22:
        # 夕方・夜 -> 当月 (争奪戦最重要)
        print(f"[rotation] JST {now.strftime('%H:%M')}: 夕方/夜間スロット -> 当月 ({current_rights}) を選択")
        return [current_rights]
    elif 10 <= hour <= 14:
        # 昼 -> 翌月 (当月と時間を分散)
        next_month = get_month_offset(curr_y, curr_m, 1)
        print(f"[rotation] JST {now.strftime('%H:%M')}: 昼スロット -> 翌月 ({next_month}) を選択")
        return [next_month]
    else:
        # 深夜・早朝 (00:00〜09:00) -> 曜日ローテーション月
        weekday = now.weekday()
        weekday_names = ["月曜", "火曜", "水曜", "木曜", "金曜", "土曜", "日曜"]
        offset_map = {
            0: [2],        # 月曜: 2ヶ月先
            1: [3],        # 火曜: 3ヶ月先
            2: [4],        # 水曜: 4ヶ月先
            3: [5],        # 木曜: 5ヶ月先
            4: [6],        # 金曜: 6ヶ月先
            5: [7, 8],     # 土曜: 7〜8ヶ月先
            6: [9, 10, 11] # 日曜: 9〜11ヶ月先
        }
        offsets = offset_map.get(weekday, [2])
        targets = [get_month_offset(curr_y, curr_m, off) for off in offsets]
        print(f"[rotation] JST {now.strftime('%H:%M')}: 閑散時間スロット ({weekday_names[weekday]}) -> ローテーション月 {targets} を選択")
        return targets


def run_rotation(mode: str = "auto", explicit_rights: str | None = None, out_dir: str = "data") -> int:
    """ローテーションスクレイピングを実行"""
    if explicit_rights:
        targets = [explicit_rights]
    else:
        targets = decide_target_months(mode)

    print(f"=======================================================")
    print(f"  負荷分散型 優待クロスローテーションスクレイパー")
    print(f"  実行日時: {now_jst().strftime('%Y-%m-%d %H:%M:%S')} JST")
    print(f"  対象月リスト: {targets}")
    print(f"=======================================================\n")

    success_count = 0
    total = len(targets)

    for i, r_month in enumerate(targets):
        print(f"[{i+1}/{total}] >>> {r_month} のスクレイピングを開始...")
        try:
            ret = scraper_main.run(
                dry_run=True,
                out_dir=out_dir,
                rights_arg=r_month,
                kengi_arg=None,
                watch_expr=None
            )
            if ret == 0:
                print(f"[{i+1}/{total}] ✅ {r_month} 取得完了")
                success_count += 1
            else:
                print(f"[{i+1}/{total}] ⚠️ {r_month} エラー (code: {ret})", file=sys.stderr)
        except Exception as e:
            print(f"[{i+1}/{total}] ❌ {r_month} 例外発生: {e}", file=sys.stderr)

        # 複数月を連続実行する場合、相手先サーバーへの礼儀として15秒間隔を空ける
        if i < total - 1:
            print("[rotation] 相手先サーバー負荷軽減のため 15秒間 待機中...")
            time.sleep(15)

    print(f"\n=======================================================")
    print(f"  スクレイピング結果: {success_count}/{total} 件 成功")
    print(f"=======================================================")
    return 0 if success_count > 0 else 1


def main() -> None:
    ap = argparse.ArgumentParser(description="アクセスブロック防止型 分散スクレイピングディスパッチャー")
    ap.add_argument("--mode", default="auto", choices=["auto", "current", "next", "future"],
                    help="実行モード (auto: 時刻判定, current: 当月, next: 翌月, future: 曜日ローテーション)")
    ap.add_argument("--rights", default=None, help="対象権利月を個別指定 (例: 2026-10)")
    ap.add_argument("--out-dir", default="data", help="CSV出力先ディレクトリ")
    args = ap.parse_args()
    sys.exit(run_rotation(mode=args.mode, explicit_rights=args.rights, out_dir=args.out_dir))


if __name__ == "__main__":
    main()
