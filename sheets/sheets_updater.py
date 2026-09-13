"""Google Sheets連携 (gspread)。3シート構成: master_list / raw_history / dashboard。

- master_list: キーは (権利月, コード)。A「監視」・B「優先度」はユーザー操作領域で、
  マージ更新で絶対に上書きしない。新規行の監視初期値は --auto-watch 結果、
  なければ他月の同コードの監視状態を引き継ぐ
- raw_history: Append-only。取得日時は 'YYYY-MM-DD HH:mm' 文字列で書き込み、
  Sheets側で日時として認識される前提 (ロケール日本推奨)。dashboardのMAXIFSが依存
- dashboard: T2の対象月の監視=TRUE銘柄のみ展開 (優先度→コード順) + 判定・グラフは数式。
  テンプレート投入は初回 (または REBUILD_DASHBOARD=1) のみ
- 年末アーカイブ: raw_history を raw_history_YYYY にリネームすると次回自動再作成。
  dashboard V2に旧シート名を入れると U列の前年同D-N比較が有効になる
"""
from __future__ import annotations

import json
import os

import config

MASTER_SHEET = "master_list"
HISTORY_SHEET = "raw_history"
DASH_SHEET = "dashboard"

STATUS_OPTIONS = ["未確保", "注文済", "見送り"]

DASH_HEADERS = [
    "注文ステータス", "シグナル", "補充", "コード", "銘柄名",
    "日興最新", "カブ最新", "楽天最新", "SBI信号", "GMO信号",
    "推移(楽天直近7回)", "実質純利益", "限界日", "合計最新", "合計前回",
]
# dashboard拡張列 (A:Oの表本体とは別エリア)
COL_TREND = "S"   # 推移グラフ本体はK列ではなくS列 (K=実質純利益と衝突回避)
CELL_MONTH = "$T$2"  # 対象権利月 (例: 2026-09)
CELL_PREV_SHEET = "$V$2"  # 前年シート名 (例: raw_history_2025、空なら前年比較off)
CELL_NIKKO_TH = "$W$2"  # 日興在庫の警告閾値 (株数。既定10000)
CELL_RAKUTEN_TH = "$X$2"  # 楽天在庫の警告閾値 (株数。既定5000)

# raw_history列: A日時 B権利年月 C残日数 Dコード E銘柄名 F日興 Gカブ H楽天
# I SBI信号 JGMO信号 K松井信号 Lマネ信号 M株価 N株数 Oクロス日数 P貸株コスト Q最大逆日歩
_F = "raw_history!F:F"
_G = "raw_history!G:G"
_H = "raw_history!H:H"
_I = "raw_history!I:I"
_J = "raw_history!J:J"
_P = "raw_history!P:P"
_K = "raw_history!K:K"  # 松井信号
_L = "raw_history!L:L"  # マネ信号
_RT = "raw_history!T:T"  # Rtn_SBI (ルーティン側SBI信号 ◎▲×)


def _vlookup_latest(valcol: str, datecell: str = "$Q$2", monthcell: str = "$T$2") -> str:
    """対象月の最新スナップショットから値を引くVLOOKUP式を連結で組み立てる。
    キー = 権利年月|コード|取得日時 (f-stringの}}エスケープ問題を避けるため連結方式)。"""
    table = "{raw_history!B:B&\"|\"&raw_history!D:D&\"|\"&raw_history!A:A},{" + valcol + "}"
    return ("VLOOKUP(" + monthcell + "&\"|\"&D2:D&\"|\"&" + datecell + "," + table + ",2,FALSE)")


def _vlookup_dn() -> str:
    """対象月・最新の残日数(D-N)を引く式 (前年比較のキー用)。"""
    table = "{raw_history!B:B&\"|\"&raw_history!D:D&\"|\"&raw_history!A:A,raw_history!C:C}"
    return ("VLOOKUP(" + CELL_MONTH + "&\"|\"&D2:D&\"|\"&$Q$2," + table + ",2,FALSE)")


def _dashboard_formulas() -> dict[str, str]:
    prev_table = ("{INDIRECT(" + CELL_PREV_SHEET + "&\"!D:D\")&\"|\"&INDIRECT("
                  + CELL_PREV_SHEET + "&\"!C:C\"),INDIRECT(" + CELL_PREV_SHEET + "&\"!H:H\")}")
    return {
        # D: 対象月の監視銘柄を優先度→コード順で展開 (順序固定でステータス列との対応を安定化)
        "D2": ("=INDEX(SORT(FILTER({master_list!C2:C,master_list!B2:B},"
               "master_list!A2:A=TRUE,master_list!L2:L=" + CELL_MONTH + "),2,1,1,1),0,1)"),
        # E: 銘柄名 (master: C=コード D=銘柄名)
        "E2": '=ARRAYFORMULA(IF(D2:D="","",IFERROR(VLOOKUP(D2:D,master_list!C:D,2,FALSE),"")))',
        # F〜J: 最新スナップショットの値 (キー=コード|取得日時)
        "F2": '=ARRAYFORMULA(IF(D2:D="","",IFERROR(' + _vlookup_latest(_F) + ',"")))',
        "G2": '=ARRAYFORMULA(IF(D2:D="","",IFERROR(' + _vlookup_latest(_G) + ',"")))',
        "H2": '=ARRAYFORMULA(IF(D2:D="","",IFERROR(' + _vlookup_latest(_H) + ',"")))',
        "I2": '=ARRAYFORMULA(IF(D2:D="","",IFERROR(' + _vlookup_latest(_I) + ',"")))',
        "J2": '=ARRAYFORMULA(IF(D2:D="","",IFERROR(' + _vlookup_latest(_J) + ',"")))',
        # B: 意思決定シグナル。SBI急変(◎→▲/◎→×)かつ日興が閾値以下なら「🔴今夜確保」。
        # 枯渇は3社合計0かつSBI信号<>2のときのみ
        "B2": ('=ARRAYFORMULA(IF(D2:D="","",IF(((AA2:AA="🚨 急変 (◎→▲)")+(AA2:AA="💥 瞬殺 (◎→×)"))'
               '*(F2:F<>"")*(N(F2:F)<=' + CELL_NIKKO_TH + '),"🔴今夜確保",'
               'IF(N2:N="",IF((M2:M=0)*(I2:I<>2),"⚪枯渇","🟢待機可"),'
               'IF((M2:M=0)*(I2:I<>2),"⚪枯渇",IF(M2:M<=N2:N*0.5,"🔴即確保",'
               'IF(M2:M<N2:N,"🟡要監視","🟢待機可")))))))'),
        # C: 在庫復活 (前回0→今回プラスのみ。初回取得時は出さない)
        "C2": ('=ARRAYFORMULA(IF(D2:D="","",IF((N2:N<>"")*(N2:N=0)*(M2:M>0),"🔥補充","")))'),
        # K: 実質純利益 = 優待価値 − 最新貸株コスト。優待価値が無い銘柄は "—"
        # (master: F=優待価値)
        "K2": ('=ARRAYFORMULA(IF(D2:D="","",IF(IFERROR(VLOOKUP(D2:D,master_list!C:F,4,FALSE),0)=0,"—",'
               'IFERROR(VLOOKUP(D2:D,master_list!C:F,4,FALSE),0)-'
               'IFERROR(' + _vlookup_latest(_P) + ',0))))'),
        # L: 赤字転落限界日 D-X = 優待価値*365/(必要資金*年率) (master: G=必要資金)
        "L2": "=ARRAYFORMULA(IF(D2:D=\"\",\"\",IFERROR(\"D-\"&INT(IFERROR(VLOOKUP(D2:D,master_list!C:F,4,FALSE),0)*365/(IFERROR(VLOOKUP(D2:D,master_list!C:G,5,FALSE),0)*10000*$P$2)),\"—\")))",
        # M/N: 判定用3社合計 (最新/前回)
        "M2": '=ARRAYFORMULA(IF(D2:D="","",N(F2:F)+N(G2:G)+N(H2:H)))',
        "N2": ('=ARRAYFORMULA(IF(D2:D="","",IFERROR(' + _vlookup_latest(_F, "$R$2") + ',0)'
               '+IFERROR(' + _vlookup_latest(_G, "$R$2") + ',0)'
               '+IFERROR(' + _vlookup_latest(_H, "$R$2") + ',0)))'),
        # U: 前年同D-Nの楽天在庫 (V2のシート名が空なら非表示。値は当日の初回取得分)
        "U2": ('=ARRAYFORMULA(IF(D2:D="","",IF(' + CELL_PREV_SHEET + '="","",'
               'IFERROR(VLOOKUP(D2:D&"|"&IFERROR(' + _vlookup_dn() + ',-1),' + prev_table + ',2,FALSE),""))))'),
        # Z: SBI最新 (ルーティン側 ◎▲×)
        "Z2": '=ARRAYFORMULA(IF(D2:D="","",IFERROR(' + _vlookup_latest(_RT) + ',"")))',
        # AA: SBI急変アラート (前回→今回のRtn_SBI比較。初回は現状表示のみ)
        # 🚨急変(◎→▲) / 💥瞬殺(◎→×) / ⚪枯渇 / ▲残少 / ─安定
        "AA2": ('=ARRAYFORMULA(IF(D2:D="","",IF(Z2:Z="","—",IFS('
                '(IFERROR(' + _vlookup_latest(_RT, "$R$2") + ',"")="◎")*(Z2:Z="▲"),"🚨 急変 (◎→▲)",'
                '(IFERROR(' + _vlookup_latest(_RT, "$R$2") + ',"")="◎")*(Z2:Z="×"),"💥 瞬殺 (◎→×)",'
                'Z2:Z="×","⚪ 枯渇",Z2:Z="▲","▲ 残少",TRUE,"─"))))'),
        # AE: 日興前日比 = 最新 − 前回 (初回は空欄)
        "AE2": ('=ARRAYFORMULA(IF(D2:D="","",IF((F2:F="")+($R$2=""),"",'
                'F2:F-IFERROR(' + _vlookup_latest(_F, "$R$2") + ',0))))'),
        # AB: 閾値アラート (W2=日興閾値 X2=楽天閾値。空欄は対象外)
        "AB2": ('=ARRAYFORMULA(IF(D2:D="","",TRIM('
                'IF((F2:F<>"")*(N(F2:F)<' + CELL_NIKKO_TH + '),"⚠日興 ","")&'
                'IF((H2:H<>"")*(N(H2:H)<' + CELL_RAKUTEN_TH + '),"⚠楽天 ",""))))'),
        # AC/AD: 松井・マネ信号の最新 (7社在庫の残り2社。A:O本体とは別エリア)
        "AC2": '=ARRAYFORMULA(IF(D2:D="","",IFERROR(' + _vlookup_latest(_K) + ',"")))',
        "AD2": '=ARRAYFORMULA(IF(D2:D="","",IFERROR(' + _vlookup_latest(_L) + ',"")))',
        # パラメータ
        "P1": "年率", "P2": str(config.KASHIKABU_ANNUAL_RATE),
        "Q1": "最新取得",
        "Q2": "=IFERROR(MAXIFS(raw_history!A:A,raw_history!B:B," + CELL_MONTH + '),"")',
        "R1": "前回取得",
        "R2": ("=IFERROR(MAXIFS(raw_history!A:A,raw_history!B:B," + CELL_MONTH
               + ',raw_history!A:A,"<"&Q2),"")'),
        "T1": "対象月",
        "V1": "前年シート",
        "W1": "日興閾値", "W2": "10000",
        "X1": "楽天閾値", "X2": "5000",
    }


def _trend_formula(valcol: str = "H", n: int = 10) -> str:
    # 行単位のFILTERが必要なためMAP+LAMBDA式。対象月に絞って直近n回を時系列表示する。
    # S列=楽天(H)、Y列=日興(F)。日興を主軸に10回表示する。
    return ('=MAP(D2:D500,LAMBDA(c,IF(c="","",IFERROR(SPARKLINE(INDEX(SORT(SORTN('
            'FILTER({raw_history!A:A,raw_history!' + valcol + ':' + valcol
            + '},raw_history!D:D=c,raw_history!B:B=' + CELL_MONTH
            + '),' + str(n) + ',0,1,0),1,TRUE),0,2),'
              '{"charttype","line"}),"—"))))')


def _connect():
    import gspread

    key_json = os.environ.get("GCP_SERVICE_ACCOUNT_KEY", "")
    sheet_id = os.environ.get("SPREADSHEET_ID", "")
    if not key_json or not sheet_id:
        raise RuntimeError("環境変数 GCP_SERVICE_ACCOUNT_KEY / SPREADSHEET_ID が未設定です。")
    gc = gspread.service_account_from_dict(json.loads(key_json))
    return gc.open_by_key(sheet_id)


def _ensure_ws(sh, title: str, headers: list[str], rows: int = 1000, cols: int = 20):
    try:
        return sh.worksheet(title)
    except Exception:
        ws = sh.add_worksheet(title=title, rows=rows, cols=cols)
        ws.update("A1", [headers], value_input_option="USER_ENTERED")
        ws.freeze(rows=1)
        return ws


def _apply_formatting(sh) -> None:
    """入力規則・条件付き書式 (Sheets API batchUpdate直叩き。失敗してもデータ更新は継続)。"""
    try:
        mws = sh.worksheet(MASTER_SHEET)
        dws = sh.worksheet(DASH_SHEET)

        def cond_value(s: str) -> dict:
            return {"userEnteredValue": s}

        sh.batch_update({"requests": [
            {"setDataValidation": {  # master A列: チェックボックス
                "range": {"sheetId": mws.id, "startRowIndex": 1,
                          "startColumnIndex": 0, "endColumnIndex": 1},
                "rule": {"strict": True, "showCustomUi": True,
                         "condition": {"type": "BOOLEAN"}}}},
            {"setDataValidation": {  # dashboard A列: 注文ステータス選択肢
                "range": {"sheetId": dws.id, "startRowIndex": 1, "endRowIndex": 1000,
                          "startColumnIndex": 0, "endColumnIndex": 1},
                "rule": {"strict": False, "showCustomUi": True,
                         "condition": {"type": "ONE_OF_LIST",
                                       "values": [cond_value(o) for o in STATUS_OPTIONS]}}}},
            {"addConditionalFormatRule": {  # 注文済の行をグレーアウト
                "rule": {
                    "ranges": [{"sheetId": dws.id, "startRowIndex": 1, "endRowIndex": 1000,
                                "startColumnIndex": 0, "endColumnIndex": 15}],
                    "booleanRule": {
                        "condition": {"type": "TEXT_CONTAINS",
                                      "values": [cond_value("注文済")]},
                        "format": {"backgroundColor": {"red": 0.85, "green": 0.85, "blue": 0.85}}}},
                "index": 0}},
            {"addConditionalFormatRule": {  # シグナル「確保」系 → 薄赤 (即確保/今夜確保)
                "rule": {
                    "ranges": [{"sheetId": dws.id, "startRowIndex": 1, "endRowIndex": 1000,
                                "startColumnIndex": 1, "endColumnIndex": 2}],
                    "booleanRule": {
                        "condition": {"type": "CUSTOM_FORMULA",
                                      "values": [cond_value('=ISNUMBER(SEARCH("確保",$B2))')]},
                        "format": {"backgroundColor": {"red": 0.98, "green": 0.85, "blue": 0.85}}}},
                "index": 1}},
            {"addConditionalFormatRule": {  # 🔥補充 → 薄橙
                "rule": {
                    "ranges": [{"sheetId": dws.id, "startRowIndex": 1, "endRowIndex": 1000,
                                "startColumnIndex": 2, "endColumnIndex": 3}],
                    "booleanRule": {
                        "condition": {"type": "CUSTOM_FORMULA",
                                      "values": [cond_value('=$C2="🔥補充"')]},
                        "format": {"backgroundColor": {"red": 0.99, "green": 0.92, "blue": 0.82}}}},
                "index": 2}},
            {"addConditionalFormatRule": {  # SBI急変/瞬殺 → 赤橙ハイライト
                "rule": {
                    "ranges": [{"sheetId": dws.id, "startRowIndex": 1, "endRowIndex": 1000,
                                "startColumnIndex": 26, "endColumnIndex": 27}],
                    "booleanRule": {
                        "condition": {"type": "CUSTOM_FORMULA",
                                      "values": [cond_value('=REGEXMATCH($AA2,"急変|瞬殺")')]},
                        "format": {"backgroundColor": {"red": 1, "green": 0.8, "blue": 0.74},
                                   "foregroundColor": {"red": 0.75, "green": 0.21, "blue": 0.05},
                                   "bold": True}}},
                "index": 3}},
            {"addConditionalFormatRule": {  # 日興ヒートマップ: 0 → グレー
                "rule": {
                    "ranges": [{"sheetId": dws.id, "startRowIndex": 1, "endRowIndex": 1000,
                                "startColumnIndex": 5, "endColumnIndex": 6}],
                    "booleanRule": {
                        "condition": {"type": "CUSTOM_FORMULA",
                                      "values": [cond_value('=AND($F2<>"",$F2=0)')]},
                        "format": {"backgroundColor": {"red": 0.9, "green": 0.9, "blue": 0.9}}}},
                "index": 4}},
            {"addConditionalFormatRule": {  # 日興ヒートマップ: 1000〜9999 → 黄色 (注意)
                "rule": {
                    "ranges": [{"sheetId": dws.id, "startRowIndex": 1, "endRowIndex": 1000,
                                "startColumnIndex": 5, "endColumnIndex": 6}],
                    "booleanRule": {
                        "condition": {"type": "CUSTOM_FORMULA",
                                      "values": [cond_value('=AND($F2>=1000,$F2<10000)')]},
                        "format": {"backgroundColor": {"red": 1, "green": 0.98, "blue": 0.77}}}},
                "index": 5}},
            {"addConditionalFormatRule": {  # 日興ヒートマップ: 1万以上 → 緑 (余裕)
                "rule": {
                    "ranges": [{"sheetId": dws.id, "startRowIndex": 1, "endRowIndex": 1000,
                                "startColumnIndex": 5, "endColumnIndex": 6}],
                    "booleanRule": {
                        "condition": {"type": "CUSTOM_FORMULA",
                                      "values": [cond_value('=$F2>=10000')]},
                        "format": {"backgroundColor": {"red": 0.8, "green": 1, "blue": 0.8}}}},
                "index": 6}},
            {"addConditionalFormatRule": {  # 楽天在庫が閾値割れ → 薄赤
                "rule": {
                    "ranges": [{"sheetId": dws.id, "startRowIndex": 1, "endRowIndex": 1000,
                                "startColumnIndex": 7, "endColumnIndex": 8}],
                    "booleanRule": {
                        "condition": {"type": "CUSTOM_FORMULA",
                                      "values": [cond_value("=AND($H2<>\"\",$H2<$X$2)")]},
                        "format": {"backgroundColor": {"red": 1, "green": 0.8, "blue": 0.8}}}},
                "index": 7}},
            {"addConditionalFormatRule": {  # 日興前日比マイナス → 赤字太字
                "rule": {
                    "ranges": [{"sheetId": dws.id, "startRowIndex": 1, "endRowIndex": 1000,
                                "startColumnIndex": 30, "endColumnIndex": 31}],
                    "booleanRule": {
                        "condition": {"type": "CUSTOM_FORMULA",
                                      "values": [cond_value('=$AE2<0')]},
                        "format": {"foregroundColor": {"red": 0.8, "green": 0, "blue": 0},
                                   "bold": True}}},
                "index": 8}},
            {"addConditionalFormatRule": {  # 日興前日比プラス → 緑字
                "rule": {
                    "ranges": [{"sheetId": dws.id, "startRowIndex": 1, "endRowIndex": 1000,
                                "startColumnIndex": 30, "endColumnIndex": 31}],
                    "booleanRule": {
                        "condition": {"type": "CUSTOM_FORMULA",
                                      "values": [cond_value('=$AE2>0')]},
                        "format": {"foregroundColor": {"red": 0, "green": 0.5, "blue": 0}}}},
                "index": 9}},
        ]})
        print("[sheets] 書式設定を適用", flush=True)
    except Exception as e:
        print(f"[sheets] WARN 書式設定スキップ: {e}", flush=True)


def _pad(row: list, n: int) -> list:
    return list(row) + [""] * (n - len(row)) if len(row) < n else list(row[:n])


def _is_true(v) -> bool:
    return str(v).strip().upper() == "TRUE"


def _migrate_legacy_row(row: list) -> list:
    """旧10列レイアウト [監視,コード,銘柄名,...] → 新12列へ移行。
    旧データは2026-09権利月のみ存在した前提で権利月を補完する。"""
    row = _pad(row, 10)
    return [row[0], "", row[1], row[2], row[3], row[4],
            row[5], row[6], row[7], row[8], row[9], config.RIGHTS_MONTH]


def _update_master(ws, master_rows: list[list]) -> None:
    """キーは (権利月, コード)。監視・優先度のユーザー入力を保持してマージ更新。
    新規行の監視初期値: --auto-watch結果、なければ他月の同コードの監視状態を引き継ぐ。
    同月の掲載落ち・他月の行はそのまま残す。"""
    ncol = len(config.MASTER_HEADERS)
    existing = ws.get_all_values()
    legacy = bool(existing) and existing[0] != config.MASTER_HEADERS
    old: dict[tuple[str, str], list] = {}
    if len(existing) > 1:
        for row in existing[1:]:
            body = _migrate_legacy_row(row) if legacy else _pad(row, ncol)
            if len(body) < 3 or not str(body[2]).strip():
                continue
            old[(str(body[11]).strip(), str(body[2]).strip())] = body
    if legacy:
        print("[sheets] 旧レイアウトを移行", flush=True)
    watched_codes = {code for (_, code), r in old.items() if _is_true(r[0])}

    incoming_keys = set()
    out = [config.MASTER_HEADERS]
    for m in master_rows:
        m = _pad(m, ncol)
        key = (str(m[11]).strip(), str(m[2]).strip())
        incoming_keys.add(key)
        if key in old:
            out.append([old[key][0], old[key][1]] + m[2:])
        else:
            watch = bool(m[0]) or (str(m[2]).strip() in watched_codes)
            out.append([watch, m[1]] + m[2:])
    for key, row in old.items():  # 掲載落ち・他月の行は維持
        if key not in incoming_keys:
            out.append(_pad(row, ncol))
    ws.update("A1", out, value_input_option="USER_ENTERED")
    n_watch = sum(1 for r in out[1:] if _is_true(r[0]))
    print(f"[sheets] master_list: {len(out)-1}行 (監視ON: {n_watch})", flush=True)


def _setup_dashboard(ws, rights: str) -> None:
    """dashboardテンプレ投入。既存テンプレがある場合は触らない (REBUILD_DASHBOARD=1で強制)。
    T2(対象月)は初回・強制再構築時のみ既定値を投入し、2回目以降はユーザーの選択を保持する。"""
    rebuild = os.environ.get("REBUILD_DASHBOARD") == "1"
    if not rebuild and ws.acell("D2").value:
        if not ws.acell("T2").value:
            ws.update("T2", [[rights]], value_input_option="USER_ENTERED")
        return
    ws.update("A1", [DASH_HEADERS], value_input_option="USER_ENTERED")
    for cell, formula in _dashboard_formulas().items():
        ws.update(cell, [[formula]], value_input_option="USER_ENTERED")
    ws.update("S1", [["推移(楽天直近10回)"]], value_input_option="USER_ENTERED")
    ws.update("S2", [[_trend_formula("H", 10)]], value_input_option="USER_ENTERED")
    ws.update("Y1", [["推移(日興直近10回)"]], value_input_option="USER_ENTERED")
    ws.update("Y2", [[_trend_formula("F", 10)]], value_input_option="USER_ENTERED")
    ws.update("Z1", [["SBI最新"]], value_input_option="USER_ENTERED")
    ws.update("AA1", [["SBI急変アラート"]], value_input_option="USER_ENTERED")
    ws.update("AE1", [["日興前日比"]], value_input_option="USER_ENTERED")
    ws.update("AB1", [["閾値アラート"]], value_input_option="USER_ENTERED")
    ws.update("AC1", [["松井最新"]], value_input_option="USER_ENTERED")
    ws.update("AD1", [["マネ最新"]], value_input_option="USER_ENTERED")
    ws.update("U1", [["前年同D-N(楽天)"]], value_input_option="USER_ENTERED")
    ws.update("T2", [[rights]], value_input_option="USER_ENTERED")
    ws.freeze(rows=1)
    print("[sheets] dashboardテンプレを投入", flush=True)


def _sanitize(rows: list[list]) -> list[list]:
    return [[("" if v is None else v) for v in row] for row in rows]


def update_spreadsheet(history_rows: list[list], master_rows: list[list], rights: str) -> None:
    sh = _connect()
    mws = _ensure_ws(sh, MASTER_SHEET, config.MASTER_HEADERS, rows=max(len(master_rows) + 10, 500), cols=14)
    hws = _ensure_ws(sh, HISTORY_SHEET, config.HISTORY_HEADERS, rows=20000, cols=20)
    dws = _ensure_ws(sh, DASH_SHEET, DASH_HEADERS, rows=1000, cols=32)

    fresh_master = len(mws.get_all_values()) <= 1
    _update_master(mws, _sanitize(master_rows))
    hws.append_rows(_sanitize(history_rows), value_input_option="USER_ENTERED")
    print(f"[sheets] raw_history: +{len(history_rows)}行追記", flush=True)
    _setup_dashboard(dws, rights)
    if fresh_master or os.environ.get("REBUILD_DASHBOARD") == "1":
        _apply_formatting(sh)
