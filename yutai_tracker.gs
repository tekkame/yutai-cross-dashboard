/**
 * 株主優待クロス在庫トラッカー (Google Sheets + GAS)
 * 情報源A(厳選・優待内容): https://yutai.enjoy-lcl.com/{january..december}-list/
 *   → 銘柄マスタ / 在庫ログ (5社: 楽天・eスマ・日興・SBI信号・GMO上限、1日1スナップショット)
 * 情報源B(網羅・数値在庫): https://gokigen-life.tokyo/ (+ API: /api/00ForWeb/ForZaiko2.php POST month=1..12)
 *   → 在庫ログ_gokigen / 取得メタ_gokigen (7社: 日興・カブコム・楽天・SBI・GMO・松井・マネックスの在庫株数+株価・利回り・逆日歩)
 * 使い方:
 *  1. 新規スプレッドシートを作成 → 拡張機能 > Apps Script にこのファイル全文を貼り付け
 *  2. setupSheets() を1回実行 (タブと見出しを自動作成)
 *  3. fetchAllMonths() と fetchGokigenAll() を1回ずつ手動実行して動作確認
 *  4. トリガー(毎日18:30頃)に fetchAllMonths + fetchGokigenAll を登録
 *
 * 設計方針(12ヶ月対応):
 *  - 銘柄マスタ: code をPK、全月の銘柄を統合 (month列で権利月を保持、カンマ区切りで複数月対応)
 *  - 在庫ログ / 在庫ログ_gokigen: 1行=1銘柄×1取得日時のスナップショット (日時変化の追跡用・アペンドのみ、更新しない)
 *  - ダッシュボード: 最新×前回の差分をQUERYで表示、個別推移はSPARKLINE
 */

// ============ 設定 ============
const MONTHS = [
  { key: '1月',  slug: 'january',   band: null },
  { key: '2月',  slug: 'february',  band: null },
  { key: '3月',  slug: 'march',     band: null },
  { key: '4月',  slug: 'april',     band: null },
  { key: '5月',  slug: 'may',       band: null },
  { key: '6月',  slug: 'june',      band: null },
  { key: '7月',  slug: 'july',      band: null },
  { key: '8月',  slug: 'august',    band: null },
  { key: '9月',  slug: 'september', band: null },
  { key: '10月', slug: 'october',   band: null },
  { key: '11月', slug: 'november',  band: null },
  { key: '12月', slug: 'december',  band: null },
];
const BASE_URL = 'https://yutai.enjoy-lcl.com';
const SHEET_MASTER = '銘柄マスタ';
const SHEET_LOG = '在庫ログ';
const SHEET_DASH = 'ダッシュボード';
const SHEET_CONF = '設定';
// ---- 情報源B (Gokigen Life API) ----
const GOKIGEN_API = 'https://gokigen-life.tokyo/api/00ForWeb/ForZaiko2.php';
const SHEET_GLOG = '在庫ログ_gokigen';
const SHEET_GMETA = '取得メタ_gokigen';
// 毎日取得する権利月。12ヶ月全取得はセル消費が大きい(約5700行/日)ため、
// 直近2ヶ月に絞るのが推奨。必要に応じて '1'〜'12' を追加。
const GOKIGEN_MONTHS = ['9', '10'];

const MASTER_HEADERS = ['code','銘柄名','詳細URL','権利月','投資区分','資金_万円','優待価値_円','優待内容','利回り_%','初回検出日','最終確認日'];
const LOG_HEADERS = ['取得日時','基準日(サイト記載)','権利月','code','銘柄名','投資区分',
  '楽天_raw','楽天_株数','eスマ_raw','eスマ_株数','日興_raw','日興_株数','SBI_信号','GMO_raw','GMO_株数'];
// vol列の対応 (サイト記載7社順と一致): n=日興 k=カブコム(eスマ) r=楽天 s=SBI g=GMO m=松井 x=マネックス
const GLOG_HEADERS = ['取得日時','権利月','code','銘柄名','区分','株価','株数','優待種別','優待内容','利回り',
  'クロス日数','逆日歩日数','理論逆日歩','直近逆日歩','逆日歩規制','逆日歩max5','逆日歩avg5',
  '日興_株数','カブコム_株数','楽天_株数','SBI_株数','GMO_株数','松井_株数','マネックス_株数','権利日','企業URL'];
const GMETA_HEADERS = ['取得日時','権利月','件数','日興更新','カブコム更新','楽天更新','SBI更新','GMO更新','松井更新','マネックス更新'];

// ============ セットアップ ============
function setupSheets() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  ensureSheet_(ss, SHEET_MASTER, MASTER_HEADERS);
  ensureSheet_(ss, SHEET_LOG, LOG_HEADERS);
  ensureSheet_(ss, SHEET_GLOG, GLOG_HEADERS);
  ensureSheet_(ss, SHEET_GMETA, GMETA_HEADERS);
  ensureSheet_(ss, SHEET_CONF, ['slug', 'url', '有効']);
  ensureSheet_(ss, SHEET_DASH, ['使い方']);

  // 設定タブに12ヶ月URLを投入
  const conf = ss.getSheetByName(SHEET_CONF);
  if (conf.getLastRow() <= 1) {
    const rows = MONTHS.map(m => [m.slug, `${BASE_URL}/${m.slug}-list/`, 'TRUE']);
    conf.getRange(2, 1, rows.length, 3).setValues(rows);
  }

  // ダッシュボードに雛形メモと主要式を投入 (A1:A)
  const dash = ss.getSheetByName(SHEET_DASH);
  if (dash.getLastRow() <= 1) {
    dash.getRange('A1').setValue('【使い方】①在庫ログに日々蓄積 ②B列〜に下の式を貼って最新×前回差分を表示 ③条件付き書式で枯渇を赤くする');
    // 最新取得日時の表示
    dash.getRange('A3').setValue('最新取得日時');
    dash.getRange('B3').setFormula(`=MAX('${SHEET_LOG}'!A:A)`);
    dash.getRange('A4').setValue('ログ件数');
    dash.getRange('B4').setFormula(`=COUNTA('${SHEET_LOG}'!A:A)-1`);
    // 直近2回分のcode別最新在庫ピボット例 (9月の例: 権利月で絞る)
    dash.getRange('A6').setValue('code');
    dash.getRange('B6').setValue('銘柄名');
    dash.getRange('C6').setValue('最新_楽天株数');
    dash.getRange('D6').setValue('前回_楽天株数');
    dash.getRange('E6').setValue('増減');
    dash.getRange('F6').setValue('SBI最新');
    dash.getRange('A7').setFormula(
      `=QUERY('${SHEET_LOG}'!C:H,"select D,E,H where C='9月' and A>=datetime '"&TEXT(MAX('${SHEET_LOG}'!A:A)-30,"yyyy-MM-dd HH:mm:ss")&"' group by D,E,H order by D label D 'code',E '銘柄名',H '楽天株数' limit 200")`
    );
    dash.getRange('E7').setFormula(`=IFERROR(C7-D7,)`);
  }
  SpreadsheetApp.getUi().alert('セットアップ完了: 設定タブで対象月をTRUE/FALSE調整してください。');
}

function ensureSheet_(ss, name, headers) {
  let sh = ss.getSheetByName(name);
  if (!sh) sh = ss.insertSheet(name);
  if (sh.getLastRow() === 0) {
    sh.getRange(1, 1, 1, headers.length).setValues([headers]);
    sh.setFrozenRows(1);
  }
  return sh;
}

// ============ メイン: 全月取得 ============
function fetchAllMonths() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const conf = ss.getSheetByName(SHEET_CONF);
  const last = conf.getLastRow();
  if (last < 2) throw new Error('設定タブが空です。setupSheets()を先に実行してください。');
  const rows = conf.getRange(2, 1, last - 1, 3).getValues();
  rows.forEach(([slug, url, enabled]) => {
    if (String(enabled).toUpperCase() !== 'FALSE' && url) {
      try {
        fetchOneMonth(String(slug), String(url));
        Utilities.sleep(1500); // サーバ負荷配慮
      } catch (e) {
        console.error(`[${slug}] 失敗: ${e.message}`);
      }
    }
  });
}

// テスト用: 9月だけ取得
function fetchSeptemberOnly() {
  fetchOneMonth('september', `${BASE_URL}/september-list/`);
}

// ============ 1ヶ月分の取得・解析・書き込み ============
function fetchOneMonth(slug, url) {
  const monthLabel = slugToLabel_(slug);
  const res = UrlFetchApp.fetch(url, { muteHttpExceptions: true, followRedirects: true });
  if (res.getResponseCode() !== 200) throw new Error(`HTTP ${res.getResponseCode()}: ${url}`);
  const html = res.getContentText('UTF-8');

  const sourceDate = extractSourceDate_(html); // 例: 2026年9月11日
  const records = parseMonthHtml_(html, monthLabel);
  if (records.length === 0) throw new Error('表が0件でした。サイト構造変更の可能性あり。');

  const now = new Date();
  appendLog_(records, now, sourceDate, monthLabel);
  upsertMaster_(records, now, monthLabel);
  console.log(`[${monthLabel}] ${records.length}件 logged (基準日:${sourceDate})`);
}

function slugToLabel_(slug) {
  const map = { january:'1月', february:'2月', march:'3月', april:'4月', may:'5月', june:'6月',
    july:'7月', august:'8月', september:'9月', october:'10月', november:'11月', december:'12月' };
  return map[slug] || slug;
}

// ---- 基準日の抽出: 「右5列は、2026年9月11日(金)の〜」「終値は、2026年9月11日」等 ----
function extractSourceDate_(html) {
  const text = html.replace(/<[^>]+>/g, ' ');
  const m = text.match(/(20\d{2}年\d{1,2}月\d{1,2}日)/);
  return m ? m[1] : '';
}

// ---- 6つの投資金額区分テーブルをパース ----
// 前提: <h2>〜10万円以下</h2> の後に <table> が来る構造。各行11列(左6+右5)。
function parseMonthHtml_(html, monthLabel) {
  const out = [];
  // h2見出しとtableをペアで抜く
  const sectionRe = /<h2[^>]*>([\s\S]*?)<\/h2>\s*([\s\S]*?)<table[^>]*>([\s\S]*?)<\/table>/gi;
  let sm;
  while ((sm = sectionRe.exec(html)) !== null) {
    const h2text = stripTags_(sm[1]).replace(/\s+/g, '');
    const band = normalizeBand_(h2text); // 例: 〜10万円 / 10-20万円...
    const tableHtml = sm[3];
    const rowRe = /<tr[^>]*>([\s\S]*?)<\/tr>/gi;
    let rm;
    while ((rm = rowRe.exec(tableHtml)) !== null) {
      const rowHtml = rm[1];
      if (/<th/i.test(rowHtml)) continue; // ヘッダー行はスキップ
      const cells = [];
      const cellRe = /<t[dh][^>]*>([\s\S]*?)<\/t[dh]>/gi;
      let cm;
      while ((cm = cellRe.exec(rowHtml)) !== null) cells.push(cm[1]);
      if (cells.length < 11) continue;
      const rec = buildRecord_(cells, monthLabel, band);
      if (rec) out.push(rec);
    }
  }
  return out;
}

function buildRecord_(cells, monthLabel, band) {
  const code = stripTags_(cells[0]).replace(/\D/g, '');
  if (!/^\d{4}$/.test(code)) return null;
  const nameCell = cells[1];
  const linkM = nameCell.match(/<a[^>]*href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/i);
  const name = stripTags_(linkM ? linkM[2] : nameCell).trim();
  const url = linkM ? linkM[1] : '';
  const funds = num_(stripTags_(cells[2]));
  const value = num_(stripTags_(cells[3]));
  const content = stripTags_(cells[4]).trim();
  const yld = num_(stripTags_(cells[5]));

  const rakutenRaw = stripTags_(cells[6]).trim();
  const esumaRaw = stripTags_(cells[7]).trim();
  const nikkoRaw = stripTags_(cells[8]).trim();
  const sbiRaw = stripTags_(cells[9]).trim();
  const gmoRaw = stripTags_(cells[10]).trim();

  return {
    monthLabel, band, code, name, url, funds, value, content, yld,
    rakutenRaw, rakutenQty: parseQty_(rakutenRaw),
    esumaRaw, esumaQty: parseQty_(esumaRaw),
    nikkoRaw, nikkoQty: parseQty_(nikkoRaw),
    sbi: parseSbi_(sbiRaw),
    gmoRaw, gmoQty: parseQty_(gmoRaw),
  };
}

// ============ 正規化ルール ============
// 「1.1万」→11000 / 「8300」→8300 / 「大量」→null(別途rawで判定) / 「残無」「0」「×」「-」→0 / 空→null
function parseQty_(raw) {
  const s = String(raw || '').replace(/\s/g, '').replace(/,/g, '');
  if (!s || s === ' ' || s === '-') return null;
  if (/大量/.test(s)) return null;      // raw='大量'で判定 (在庫豊富)
  if (/残無/.test(s)) return 0;
  if (s === '×' || s === '✕' || s === '―' || s === 'ー') return 0;
  if (s === '◎' || s === '▲') return null; // 数値列に記号が混入した場合
  const mMan = s.match(/^([\d.]+)万$/);
  if (mMan) return Math.round(parseFloat(mMan[1]) * 10000);
  const mNum = s.match(/^([\d.]+)$/);
  if (mNum) return parseFloat(mNum[1]);
  const mMix = s.match(/([\d.]+)万/); // 「22.4万」等のゆらぎ吸収
  if (mMix) return Math.round(parseFloat(mMix[1]) * 10000);
  return null;
}

// SBI短期列は ◎=在庫十分 / ▲=残少 / ×=なし と推定 (サイトに凡例なしのため信号として保存)
function parseSbi_(raw) {
  const s = String(raw || '').replace(/\s/g, '');
  if (s.includes('◎')) return '◎';
  if (s.includes('▲')) return '▲';
  if (s.includes('×') || s.includes('✕')) return '×';
  return s || '';
}

function normalizeBand_(h2compact) {
  if (/10万円以下/.test(h2compact)) return '〜10万円';
  if (/10万円超/.test(h2compact)) return '10-20万円';
  if (/20万円超/.test(h2compact)) return '20-30万円';
  if (/30万円超/.test(h2compact)) return '30-50万円';
  if (/50万円超/.test(h2compact)) return '50-100万円';
  if (/100万円超/.test(h2compact)) return '100万円超';
  return h2compact.slice(0, 20);
}

function stripTags_(s) {
  return String(s || '').replace(/<br\s*\/?>/gi, ' ').replace(/<[^>]+>/g, '').replace(/&nbsp;/gi, ' ').replace(/&amp;/gi, '&').trim();
}
function num_(s) {
  const t = String(s || '').replace(/,/g, '').match(/[\d.]+/);
  return t ? parseFloat(t[0]) : '';
}

// ============ 書き込み ============
function appendLog_(records, now, sourceDate, monthLabel) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sh = ss.getSheetByName(SHEET_LOG);
  const rows = records.map(r => [now, sourceDate, monthLabel, r.code, r.name, r.band,
    r.rakutenRaw, r.rakutenQty, r.esumaRaw, r.esumaQty, r.nikkoRaw, r.nikkoQty, r.sbi, r.gmoRaw, r.gmoQty]);
  sh.getRange(sh.getLastRow() + 1, 1, rows.length, LOG_HEADERS.length).setValues(rows);
}

function upsertMaster_(records, now, monthLabel) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sh = ss.getSheetByName(SHEET_MASTER);
  const last = sh.getLastRow();
  const existing = last > 1 ? sh.getRange(2, 1, last - 1, MASTER_HEADERS.length).getValues() : [];
  const idx = {};
  existing.forEach((row, i) => { idx[String(row[0])] = i; });

  records.forEach(r => {
    if (idx[r.code] !== undefined) {
      const rowNo = idx[r.code] + 2;
      const cur = sh.getRange(rowNo, 1, 1, MASTER_HEADERS.length).getValues()[0];
      let months = String(cur[3] || '');
      if (!months.includes(monthLabel)) months = months ? `${months},${monthLabel}` : monthLabel;
      sh.getRange(rowNo, 1, 1, MASTER_HEADERS.length).setValues([[
        r.code, r.name, r.url, months, r.band, r.funds, r.value, r.content, r.yld, cur[9] || now, now
      ]]);
    } else {
      sh.appendRow([r.code, r.name, r.url, monthLabel, r.band, r.funds, r.value, r.content, r.yld, now, now]);
      idx[r.code] = (sh.getLastRow() - 2);
    }
  });
}

// ============ 情報源B: Gokigen Life API ============
// 月別リストページはJS生成のためHTMLスクレイピング不可。裏側のJSON APIを直接POSTする。
// 検証済み: month="9" → 473件。レスポンス文字コードは Shift_JIS のため必ず指定すること。
// [0]の code:"0000" 行はダミーで、各社在庫の更新時刻(epoch ms)が nvol〜xvol に入っている。
function fetchGokigenAll() {
  GOKIGEN_MONTHS.forEach(m => {
    try {
      fetchGokigenMonth(String(m));
      Utilities.sleep(1500);
    } catch (e) {
      console.error(`[gokigen ${m}月] 失敗: ${e.message}`);
    }
  });
}

function fetchGokigenMonth(month) {
  const res = UrlFetchApp.fetch(GOKIGEN_API, { method: 'post', payload: { month }, muteHttpExceptions: true });
  if (res.getResponseCode() !== 200) throw new Error(`HTTP ${res.getResponseCode()}`);
  const json = JSON.parse(res.getContentText('Shift_JIS'));
  if (!Array.isArray(json) || json.length === 0) throw new Error('空レスポンス');

  const now = new Date();
  const dummy = json[0] || {};
  const rows = json.filter(r => r && r.code && r.code !== '0000');

  // メタ行: 各社の在庫更新時刻を記録 (いつ時点の在庫かが分かる)
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const meta = ss.getSheetByName(SHEET_GMETA);
  meta.appendRow([now, `${month}月`, rows.length,
    epochMsToDate_(dummy.nvol), epochMsToDate_(dummy.kvol), epochMsToDate_(dummy.rvol),
    epochMsToDate_(dummy.svol), epochMsToDate_(dummy.gvol), epochMsToDate_(dummy.mvol),
    epochMsToDate_(dummy.xvol)]);

  // ログ行: 月まとめて一括書き込み
  const logRows = rows.map(r => [
    now, `${month}月`, String(r.code || ''), String(r.name || ''), String(r.taisyaku || ''),
    toNum_(r.kabuka), toNum_(r.kabusu), String(r.yutai_syubetsu || ''), String(r.yutai || ''),
    toNum_(r.rimawari), toNum_(r.c_nissu), toNum_(r.gyaku_days), toNum_(r.riron_gyaku),
    toNum_(r.recent_gyaku), String(r.recent_gyaku_kisei || ''), toNum_(r.max5_gyaku), toNum_(r.avg5_gyaku),
    toNum_(r.nvol), toNum_(r.kvol), toNum_(r.rvol), toNum_(r.svol),
    toNum_(r.gvol), toNum_(r.mvol), toNum_(r.xvol),
    String(r.d_kenri || '').replace(/<br\s*\/?>/gi, ' / '), String(r.d_curl || ''),
  ]);
  const sh = ss.getSheetByName(SHEET_GLOG);
  sh.getRange(sh.getLastRow() + 1, 1, logRows.length, GLOG_HEADERS.length).setValues(logRows);
  console.log(`[gokigen ${month}月] ${logRows.length}件 logged`);
}

// 個別銘柄の詳細HTMLが必要な場合のみ使用 (大量呼び出しは避けること)
// function fetchGokigenDetail(code) {
//   const res = UrlFetchApp.fetch('https://gokigen-life.tokyo/api/00ForWeb/ForGaiyo.php',
//     { method: 'post', payload: { code: String(code) }, muteHttpExceptions: true });
//   return JSON.parse(res.getContentText('Shift_JIS'))[0]; // {d_content, d_table, ...}
// }

function epochMsToDate_(v) {
  const n = Number(v);
  if (!n || n < 1e12) return ''; // epoch ms(13桁)のみ採用。null/空/0は空欄
  return new Date(n);
}

function toNum_(v) {
  if (v === null || v === undefined || v === '') return '';
  const n = Number(v);
  return isNaN(n) ? '' : n;
}
