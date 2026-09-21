# 引継ぎメモ：株主優待クロス在庫トラッカー

最終更新：2026-09-21（JST）。このファイルは別セッション・別モデルへの申し送り用。
技術詳細は `README.md`、実装は各ソースを参照。


## 1. 作りたいもの・目的

株主優待クロス取引の実戦用に、**一般信用売り在庫の日時変化を自動追跡・蓄積し、
「今夜確保すべき銘柄」を一目で判断できるダッシュボード**を Google スプレッドシート上に構築する。

要求の中核（ユーザー提案の採用レイアウト）：

- **日興主軸**：日興在庫の推移グラフ（直近10回）＋前日比＋残量ヒートマップ
- **SBI急変検知**：SBI信号 ◎→▲（急変）／◎→×（瞬殺）を検知し、日興残少と連動して「🔴今夜確保」を点灯
- **2大優待サイトの完全網羅**（下記2ソースの和集合、1件も落とさない）
- **通年汎用**：毎月・毎年そのまま使える（権利月の自動解決）

## 2. データソース（2サイト）

| ソース | URL・方式 | 内容 |
|---|---|---|
| routine（厳選） | `https://yutai.enjoy-lcl.com/{slug}-list/` 静的HTML | 約160銘柄。資金・優待価値・利回り・GMO売建上限＋5社在庫概数。SBI列は ◎▲× の信号のみ（凡例なし、分布からの推定） |
| gokigen（網羅） | `POST https://gokigen-life.tokyo/api/00ForWeb/ForZaiko2.php`（`month=1..12`） | 約470銘柄。7社在庫・株価・逆日歩実績。一覧ページ自体はJS生成のためHTML不可だが**裏側APIで一括取得できる** |

実測上の重要制約：

- gokigen応答は **Shift_JIS**（UTF-8で読むと文字化け）。
- 株数として意味を持つのは **日興・カブ・楽天のみ**。SBI・GMO・松井・マネは **0/1/2 のステータスコード**（2=あり濃厚・0=なし濃厚）で信号扱い。
- 応答先頭 `code:"0000"` 行はダミー（各社在庫の更新時刻 epoch ms 入り）。
- 文字列 `"null"` が混入することがある→空文字化。
- **短時間の連打はWAFで403**。1実行1POST・低頻度運用。個別銘柄の詳細API（`ForGaiyo.php`）大量呼び出しは禁止。
- `haito`・長期優遇の確定フィールドはAPIに存在しない。
- **gokigenはGASからも取得可能**（`UrlFetchApp` POST＋`getContentText('Shift_JIS')`、検証済み473件）。
  「GASではできない」は誤解。できないのは詳細APIの大量呼び出しのみ。

## 3. 処理フロー

```text
utils/dates.py： 権利月自動解決 → 権利付最終日(T+2: 月末から2営業日遡算) → D-N(残営業日)
scrapers/：      routine HTML取得 ＋ gokigen API取得(1POST)
core/merger.py： 4桁コードキーで Full Outer Join → history行(20列) / master行(12列)
sheets/：        master_list更新(監視・優先度のユーザー入力は保持) ＋ raw_history追記 ＋ dashboard数式投入
```

- 1回の実行で取得するのは**対象権利月のみ**（12ヶ月一括ではない。WAF回避＋実戦は当月に集中するため）。
- 他月は `--rights YYYY-MM`（Python）／ `CFG.RIGHTS_OVERRIDE`（GAS）で指定可。
- 権利付最終日の実績：2026年9月 → 9/28（月）でサイト記載と一致。

## 4. dashboard仕様（32列 A〜AF）

- A 注文ステータス（未確保/注文済/見送り。注文済は行グレーアウト）
- **B シグナル**：`🔴今夜確保`（SBI急変・瞬殺かつ日興≦W2）／`🔴即確保`／`🟡要監視`／`🟢待機可`／`⚪枯渇`
- **C 補充**：前回0→今回プラスで `🔥補充`（初回は出さない）
- D コード／E 銘柄名（監視=TRUEのみ、優先度→コード順で展開）
- **F 日興最新**（ヒートマップ：1万以上=緑・1000〜9999=黄・0=グレー）
- G カブ最新／H 楽天最新／I SBI信号／J GMO信号／AC 松井最新／AD マネ最新
- K 実質純利益（優待価値−貸株コスト。優待価値なしは"—"）／L 限界日D-X
- M/N 3社合計（最新/前回）
- **Y 日興推移**（直近10回SPARKLINE、日興主軸）／S 楽天推移
- Z SBI最新（routine側◎▲×）／**AA SBI急変アラート**（🚨急変◎→▲／💥瞬殺◎→×／⚪枯渇／▲残少／─）
- **AE 日興前日比**（最新−前回。マイナス赤字・プラス緑字）
- AB 閾値アラート（⚠日興／⚠楽天）
- パラメータ：P2 年率(0.011)／Q2 最新取得／R2 前回取得／T2 対象月／W2 日興閾値(10000)／X2 楽天閾値(5000)
- 初回実行時は前回がないため AA=現状表示のみ、C/AE=空欄。**2回目以降に急変検知が有効化**。

## 5. どこまで作られているか（2026-09-13時点）

### 完成・検証済み

- Python一式（`main.py` `config.py` `utils/dates.py` `core/merger.py` `scrapers/` `sheets/`）：dry-run検証済み。
- GAS完全版 **`yutai_gas_full.gs`**（本ファイルと同等機能の単体スクリプト、構文チェック済み）。旧 `yutai_tracker.gs`（取得のみ、dashboardなし）は残置。
- Actions定義（平日JST 17:00/20:00＋手動 year/month 指定）、`README.md` 整備済み。
- オフライン検証スクリプト通過（dates/merger/数式32セル）、`dashboard_preview.xlsx` で表示確認済み。

### 検証実績（2026-09-13 dry-run＋監査）

- routine 164件（基準日2026-09-11）／gokigen 472件／突合162件／**history 474件**。
- routine-only 2件（3964 オークネット、7595 アルゴＧ）はgokigen 9月・10月どちらにも不在＝**gokigen側の未掲載**。Full Outerでroutine値保持のため追跡可。
- gokigen-only 310件はroutine厳選漏れで、全て行化される。→ **両サイト×対象月の網羅性は確認済み**。
- 日興在庫の分布：10000株以上=17件／1000〜9999=70件／0=122件／取扱なし=209件。

## 6. 実行方法（現行方針：GAS方式）

当初は Python＋GitHub Actions 方式だったが、**Google Cloud登録（$300クレジットの期限消費を避けたい）を使わない方針に切替**。
GASは完全無料・クレカ登録不要のため、現行の実行手段はGAS。

1. 対象スプレッドシート（ID: `175sKtMVVp6IgqrzLcRtO5tX7t-wiEKQrrfagfRoH1gM`）で「拡張機能＞Apps Script」
2. `yutai_gas_full.gs` 全文を貼り付け保存
3. `setupAll` を実行（承認あり）→ `runDaily` を実行（約1〜2分）
4. トリガーで `runDaily` を毎日 17:00／20:00 に登録

Python版の live 実行（`python main.py`）には環境変数 `GCP_SERVICE_ACCOUNT_KEY`／`SPREADSHEET_ID` が必要だが、
**現環境には未設定**（空確認済み）。dry-run（CSV出力）は認証不要で動作する。

## 7. 残タスク・要判断事項

1. **GAS初回実行待ち**（ユーザー環境）。live描画（AA急変・B今夜確保・CF・SPARKLINE）の目視確認が未了。
2. **routine-only 2件のフォールバック式**：dashboardの日興最新・推移はgokigen数値を使うため2件は空欄になる。
   F列が空なら `Rtn_日興` で補完する案を提示し、**ユーザーの要否回答待ち**。
3. **20日権利銘柄の別枠表示は保留**：gokigenの権利日フィールドは空欄で返り（472件全て空）、routine 9月ページにも20日記述なし。
   今回対象に20日銘柄混入の証拠なし。
4. `out/*.csv` は検証用の一時出力。コミット不要。

## 8. 決定事項ログ（蒸し返し防止）

- Playwright不使用：一覧APIの1POSTで全件取れるため（11ページ巡回より高速・低負荷）。
- SPARKLINEの「万」変換は不採用：history取得時に数値化済みのため不要で、文字列変換は誤変換の元。
- SBI急変のQUERY文字列照合は不採用：コード列の型問題を避け、時刻キー（Q2/R2）方式を採用。
- Google Cloud登録は行わない（ユーザー判断）。そのため Actions 方式は待機、GAS方式が現行。
- auto-watch既定：`yield>=1,funds<=30`（利回り1%以上・資金30万円以下）。GAS初回は約59件ONになる見込み。
- 貸株料年率は仮定値 1.1%（`KASHIKABU_ANNUAL_RATE`／GAS側 `CFG.RATE`）。厳密化は将来課題。

---

## 9. セキュリティ監査・環境変数移行（2026-09-21 実施済み）

### 実施内容サマリー

OpenCode等の外部AIエージェントによるリポジトリ読み取りリスクへの対応として、ワークスペース全体のシークレット監査・サニタイズ・Windows環境変数への移行を実施。

### 検出・対応済みシークレット一覧

| ファイル | 変数名 | 対応内容 |
|---|---|---|
| `yutai_longterm_db.gs` | `DEFAULT_SPREADSHEET_ID` | ハードコードを除去 → `PropertiesService.getScriptProperties()` 経由に変更 |
| `yutai_longterm_db.gs` | `API_SECRET_KEY` | 同上 |
| `app.py` L386 | `APP_SECRET_KEY` fallback値 | `"yutai777"` → `"your_secret_key_here"` に変更 |
| `sheets/push_to_sheets.py` | `secret` デフォルト引数 | `"yutai777"` → `os.environ.get("APP_KEY")` に変更 |
| **git remote URL** | `GITHUB_TOKEN` (PAT) | **URLに直埋めされていたPATを除去**。トークンなしURLに変更 |

### Windows ユーザー環境変数（登録済み）

以下の `.NET API` 構文で永続登録済み（`setx` の1024文字制限を回避）:

```powershell
[System.Environment]::SetEnvironmentVariable('SPREADSHEET_ID', '175sKtMVVp6IgqrzLcRtO5tX7t-wiEKQrrfagfRoH1gM', 'User')
[System.Environment]::SetEnvironmentVariable('APP_KEY',        'yutai777', 'User')
[System.Environment]::SetEnvironmentVariable('GITHUB_TOKEN',   'ghp_Hdg...cfK6j', 'User')  # 実値はOS内のみ
```

**注意**: 新しいターミナルを開くと自動で反映。既存ターミナルでは以下で即時反映:
```powershell
$env:SPREADSHEET_ID = [System.Environment]::GetEnvironmentVariable('SPREADSHEET_ID','User')
$env:APP_KEY        = [System.Environment]::GetEnvironmentVariable('APP_KEY','User')
$env:GITHUB_TOKEN   = [System.Environment]::GetEnvironmentVariable('GITHUB_TOKEN','User')
```

### GitHub / Streamlit Cloud デプロイ状況

- **GitHubリポジトリ**: `tekkame/yutai-cross-dashboard` — 正常稼働
- **GitHub Actions (`daily_scraper`)**: 毎日JST 17:00/20:00に自動実行中。直近3回は全て `success`
  - 最終成功: 2026-09-21 06:09 JST（コミット `5191078`）
- **Streamlit Cloud**: `https://tekkame-yutai-cross-dashboard-app-uhssit.streamlit.app/` のような形でデプロイ中と推定。**実際のURLはStreamlit CloudのダッシュボードでGitHub連携を確認すること**（ログイン認証が必要なため自動確認不可）
- **サニタイズコミット**: `013f943` `security: sanitize hardcoded secrets - move to env vars / GAS ScriptProperties` がmainにマージ済み

### GAS 側の残手動作業（未完了）

`yutai_longterm_db.gs` を `PropertiesService.getScriptProperties()` 経由に変更済みだが、**GASエディタ側にプロパティ値を登録する必要がある**:

1. [GASエディタ](https://script.google.com/) → 対象プロジェクト → [プロジェクトの設定] → [スクリプトプロパティ]
2. 以下を追加:
   - `SPREADSHEET_ID` = `175sKtMVVp6IgqrzLcRtO5tX7t-wiEKQrrfagfRoH1gM`
   - `API_SECRET_KEY` = `yutai777`

### 読み込み互換性（確認済み）

全Pythonファイルが `os.environ.get()` でOS環境変数を直接参照。`python-dotenv` は不使用。`.env` ファイルも存在しない。**dotenv移行は不要**。

### `.gitignore` 追加推奨（任意）

現在 `.gs` ファイルはgitignore対象外。今後GAS内にシークレットを書かないルールを徹底するか、`.gs` をgitignore対象にすることを検討。

