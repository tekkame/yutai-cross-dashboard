# 株主優待 一般信用在庫DB＆実戦ダッシュボード

株主優待クロス取引向けに、一般信用売り在庫の日時変化を自動追跡・蓄積し、
Googleスプレッドシート上で意思決定ダッシュボードを提供するシステム。
平日17:00 / 20:00(JST)にGitHub Actionsで定期実行します。
**毎月・毎年の継続利用を前提とした設計**で、権利月は指定または自動解決します。

## データソースと役割

| ソース | 役割 | 取得方式 |
|---|---|---|
| [ルーティン株主優待 9月リスト](https://yutai.enjoy-lcl.com/september-list/) | 厳選約160銘柄の基本情報（資金・優待価値・利回り・GMO売建上限）＋5社在庫概数 | 静的HTMLテーブル解析 |
| [Gokigen Life 9月リスト](https://gokigen-life.tokyo/201909yutai-all-list/) | 全約470銘柄の7社在庫・株価・逆日歩実績 | 裏側JSON APIへPOST（`month=9`）。ページはJS生成のためHTMLスクレイピング不可、Playwright不要 |

### 実測で判明した仕様上の注意（重要）

- Gokigen APIの文字コードは **Shift_JIS**。UTF-8で読むと文字化けします。
- 在庫株数として意味を持つのは **日興・カブ・楽天** の3社のみ。
  **SBI・GMO・松井・マネックスは 0/1/2 のステータスコード**（分布上 2=あり濃厚・0=なし濃厚）のため、
  `raw_history` では「○○信号」列として記録し、数値在庫には混ぜていません。
  厳密な意味付けはサイト表示との突合で確認してください。
- Gokigen API応答の先頭 `code:"0000"` 行はダミーで、各社在庫の更新時刻（epochミリ秒）が入っています。
- 文字列フィールドに文字通り `"null"` が入ることがあるため空文字化しています。
- Gokigen側ホスティングのWAFにより**短時間の連打は403**になります。1実行1POST・低頻度運用が前提です。
  個別銘柄の詳細API（`ForGaiyo.php`）の大量呼び出しは実装していません。
- SBI列（ルーティン側）は数値ではなく ◎▲× の信号のみです（サイトに凡例なし、分布からの推定: ◎=在庫十分・▲=残少・×=なし）。
- `haito`（配当）・長期優遇フラグに該当する確定フィールドはAPIにないため、`master_list` の長期優遇列は空欄、総合利回りは優待利回りのみで算出しています。
- 貸株コスト試算の年率は `config.py` の `KASHIKABU_ANNUAL_RATE`（既定1.1%・概算）を使用。厳密計算には各証券会社の最新料率への更新を推奨します。
- `get_business_days_left` は `jpholiday` が無い環境では土日のみ除外にフォールバックします（Actions環境では祝日除外が有効）。

## 構成

```text
├── .github/workflows/daily_update.yml
├── scrapers/
│   ├── routine_yutai.py
│   └── gokigen_life.py
├── core/
│   └── merger.py        # Full Outer Joinでhistory/master行を生成
├── utils/
│   └── dates.py         # 権利月・権利付最終日・D-N・URL解決の正規実体
├── sheets/
│   ├── updater.py       # 仕様パス (実体はsheets_updater.pyへ委譲)
│   └── sheets_updater.py
├── config.py            # 定数＋後方互換 (日付ロジックはutils/datesへ委譲)
├── main.py              # オーケストレーション (結合はcore/mergerへ委譲)
├── requirements.txt
└── README.md
```

## ローカル実行

```bash
pip install -r requirements.txt
python main.py --dry-run --out-dir out   # Sheetsに触らずCSV出力のみ（権利月は自動解決）
python main.py --rights 2026-10          # 10月権利を指定
python main.py --rights 2026-10 --kengi 2026-10-29   # 権利付最終日を上書き
python main.py --auto-watch "yield>=1,funds<=30,rakuten>0"  # 新規行の監視を条件で自動ON
python main.py                            # Sheets更新（要 環境変数）
```

`--auto-watch` の条件キー: `yield`(総合利回り%) `funds`(必要資金・万円) `value`(優待価値・円)
`rakuten`/`nikko`/`kabu`(在庫株数) `cost`(貸株コスト試算) `maxgyaku`(最大逆日歩)。
カンマ区切りはAND。適用は新規行のみで、既存行のチェックは変更しません。

## 毎月の運用（ Month rollover ）

1. 実行日が権利付最終日を過ぎると、次月が自動解決されます（手動の `--rights` 指定も可）。
2. 新月の初回実行で `master_list` に新月行が追加されます。新規行の監視初期値は `--auto-watch`
   の結果、なければ前月以前の同コードの監視状態を引き継ぎます。
3. `dashboard` の **T2（対象月）** を新月に切り替えると表示が切り替わります（初回構築時は自動設定）。
4. 権利付最終日は月末から2営業日遡って自動算出（T+2決済前提、祝日考慮）します。
   月末権利でない銘柄・特例日程の月は `--kengi` で上書きしてください。

## 監視銘柄の選び方

- `master_list` のA列チェックが基本。B列「優先度」（1〜3の数字・任意）でdashboardの並び順を制御できます。
- 月初の一括候補抽出には `--auto-watch`（例: `yield>=1,funds<=30`）を使うと、新規行に自動チェックが入ります。
- `dashboard` では注文ステータス（未確保/注文済/見送り）を管理。注文済の行は自動でグレーアウトします。

## 長期運用（年越し・アーカイブ）

- `raw_history` はAppend-onlyで2年以上蓄積可能（年間約8万行・170万セル程度で上限1000万セルに余裕あり）。
  動作が重くなったら年末に `raw_history` を `raw_history_2026` 等にリネームしてください。
  次回実行で空の `raw_history` が自動再作成され、dashboard数式は新シートを参照します。
- リネームした旧シート名を `dashboard` の **V2（前年シート）** に入れると、U列「前年同D-N(楽天)」
  に前年同一残日数の在庫が表示され、前年枯渇ペースとの比較ができます（値は当日の初回取得分）。

## セットアップ手順（初回のみ）

### 1. Google Cloudでサービスアカウント発行

1. [Google Cloud Console](https://console.cloud.google.com/) でプロジェクト作成（既存可）。
2. 「APIとサービス」→「ライブラリ」で **Google Sheets API** と **Google Drive API** を有効化。
3. 「IAMと管理」→「サービスアカウント」→「作成」。名前は任意（例: `yutai-updater`）。
4. 作成したアカウントの「キー」→「鍵を追加」→「JSON」で秘密鍵をダウンロード。

### 2. スプレッドシートの作成と共有

1. 空のスプレッドシートを新規作成（IDはURLの `/d/<ここ>/edit` 部分）。
2. 「共有」からサービスアカウントのメールアドレス（`xxx@xxx.iam.gserviceaccount.com`）を**編集者**として追加。

### 3. GitHub Secretsの登録

リポジトリの Settings → Secrets and variables → Actions で以下を登録：

- `GCP_SERVICE_ACCOUNT_KEY`: ダウンロードしたJSONファイルの中身全文
- `SPREADSHEET_ID`: スプレッドシートID

初回実行で `master_list` / `raw_history` / `dashboard` の3シート・数式・入力規則・条件付き書式まで自動構築されます。

## シート仕様

- **master_list**: キーは（権利月, コード）。A列「監視」・B列「優先度」はユーザー操作領域で、
  2回目以降の更新でも保持されます。新規行は `--auto-watch` または他月の同コードの状態を引き継ぎます。
  掲載落ち・他月の行も残ります。
- **raw_history**: 実行ごとに全銘柄のスナップショットを最下行へ追記（Append-only）。
- **dashboard**: T2の対象月の監視=TRUE銘柄のみ自動展開（優先度→コード順）。
  日興最新・カブ最新・楽天最新・SBI信号・GMO信号・松井最新(AC)・マネ最新(AD)の7社表示、
  シグナル（🔴今夜確保/🔴即確保/🟡要監視/🟢待機可/⚪枯渇。枯渇は3社合計0かつSBI信号≠2のとき）、
  🔥補充、SPARKLINE推移（楽天・日興の2本、直近10回・対象月に絞り込み）、
  実質純利益（優待価値が無い銘柄は "—"）、限界日D-X、日興前日比(AE)、前年同D-Nは数式で自動計算。
- **閾値アラート**: W2（日興閾値・既定10000株）・X2（楽天閾値・既定5000株）を下回ると
  AB列に「⚠日興」「⚠楽天」と表示され、該当セルが薄赤にハイライトされます。閾値は直接編集可。
- **SBI急変検知**: Z列にルーティン側SBI信号（◎▲×）の最新値、AA列「SBI急変アラート」に
  前回→今回の変化を表示（`🚨 急変 (◎→▲)` / `💥 瞬殺 (◎→×)` / `⚪ 枯渇` / `▲ 残少` / `─`）。
  急変・瞬殺は赤橙ハイライト。初回取得時は現状表示のみで、2回目以降の取得で変化検知が有効になります。
- **日興トラッキング**: Y列に日興在庫の直近10回SPARKLINE、AE列「日興前日比」（最新−前回、
  マイナス赤字・プラス緑字）。F列「日興最新」は残量ヒートマップ
  （1万以上=緑・1000〜9999=黄・0=グレー）。
- **意思決定シグナル連携**: SBI急変・瞬殺かつ日興最新がW2閾値以下の銘柄はB列が `🔴今夜確保` になります。
- **データ結合**: history/masterは両サイトの和集合（Full Outer Join）で生成。
  gokigenにしか無い銘柄も行化されます（優待内容=gokigen文面、必要資金=株価×株数で補完、売建上限は空欄）。
- **Playwright不使用の理由**: Gokigen一覧ページはJS生成のためHTMLスクレイピング不可ですが、
  裏側JSON APIへの1POSTで全件取得できるため、11ページ巡回より高速・低負荷です。
  取得方式の詳細は `scrapers/gokigen_life.py` のdocstringを参照。
  ※Rtn_楽天/Rtn_日興/Rtn_SBIはルーティンサイト基準日（取得日より数日古い場合あり）時点の値です。
  取得日時は `YYYY-MM-DD HH:mm` 形式で書き込み、Sheets側で日時認識される前提（ロケール日本推奨）。
  テンプレ再投入が必要な場合のみ `REBUILD_DASHBOARD=1` を付けて実行してください
 （T2/V2などユーザーが変更した値は保持されます）。

## スケジュール

`cron: '0 8,11 * * 1-5'`（平日 JST 17:00 / 20:00）＋手動実行（workflow_dispatch）。
手動実行は `rights`（YYYY-MM、例: `2026-09`）または `kengi`（YYYY-MM-DD、例: `2026-10-29`）で
対象月・権利付最終日を指定可能（どちらも空欄なら自動解決）。
