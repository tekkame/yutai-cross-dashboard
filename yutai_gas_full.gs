/**
 * 株主優待クロス在庫トラッカー 完全版 (GAS単体・2サイト網羅・通年汎用)
 *
 * 2つの情報源を Full Outer Join (4桁コードキー・1件も落とさない):
 *  情報源A (厳選・優待内容・売建上限): https://yutai.enjoy-lcl.com/{slug}-list/ (HTML取得)
 *  情報源B (網羅・7社在庫の数値):     https://gokigen-life.tokyo/ の裏側APIへPOST
 *    POST https://gokigen-life.tokyo/api/00ForWeb/ForZaiko2.php (month=1..12, Shift_JIS)
 *    ※一覧APIはGASのUrlFetchApp+POSTで取得可能(検証済み473件)。WAF回避のため1実行1POST・対象月のみ。
 *    ※個別銘柄の詳細API大量呼び出しは403になるため使わない。
 *    ※株数として意味を持つのは 日興/カブ/楽天 のみ。SBI/GMO/松井/マネは 0/1/2 の信号扱い。
 *
 * 使い方 (Google Cloud登録・クレカ登録は一切不要):
 *  1. スプレッドシートで「拡張機能 > Apps Script」を開き、このファイル全文を貼り付けて保存
 *  2. 関数 setupAll を実行 (初回のみ。タブ・見出し・dashboard数式・条件付き書式まで自動構築)
 *  3. 関数 runDaily を実行 (約1〜2分。master_list / raw_history / dashboard が埋まる)
 *  4. 定期化: 左の時計アイコン(トリガー)で runDaily を毎日 17:00 / 20:00 に登録
 *
 * 見る場所: dashboard シート
 *  B列=意思決定シグナル(🔴今夜確保/🔴即確保/🟡要監視/🟢待機可/⚪枯渇)、C列=🔥補充、
 *  Y列=日興推移(直近10回グラフ)、AA列=SBI急変アラート、AE列=日興前日比、F列=日興ヒートマップ。
 *  ※初回実行時は「前回」が無いため AA列は現状表示・C列/AE列は空欄。2回目以降に急変検知が有効化。
 */

// ============ 設定 ============
const CFG = {
  RIGHTS_OVERRIDE: '',   // ''=実行日から自動解決。例 '2026-09' で固定も可
  AUTO_WATCH: true,      // 初回のみ: 総合利回り>=1% かつ 必要資金<=30万円 を自動チェック
  AUTO_WATCH_YIELD: 1,
  AUTO_WATCH_FUNDS_MAN: 30,
  RATE: 0.011,           // 貸株料概算の年率 (年1.1%。厳密計算は各証券会社の料率で要調整)
  NIKKO_TH: 10000,       // 日興在庫の警告閾値 (株)
  RAKUTEN_TH: 5000,      // 楽天在庫の警告閾値 (株)
};
const ROUTINE_BASE = 'https://yutai.enjoy-lcl.com';
const GOKIGEN_API = 'https://gokigen-life.tokyo/api/00ForWeb/ForZaiko2.php';
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36';
const SH_MASTER = 'master_list';
const SH_HISTORY = 'raw_history';
const SH_DASH = 'dashboard';
const MASTER_HEADERS = ['監視','優先度','コード','銘柄名','優待内容','優待価値','必要資金','総合利回り','売建上限','長期優遇','制度信用指標','権利月'];
const HISTORY_HEADERS = ['取得日時','権利年月','残日数(D-N)','コード','銘柄名','日興在庫','カブ在庫','楽天在庫','SBI信号','GMO信号','松井信号','マネ信号','株価','株数','クロス日数','貸株コスト','最大逆日歩','Rtn_楽天','Rtn_日興','Rtn_SBI'];
const DASH_HEADERS = ['注文ステータス','シグナル','補充','コード','銘柄名','日興最新','カブ最新','楽天最新','SBI信号','GMO信号','推移(楽天直近7回)','実質純利益','限界日','合計最新','合計前回'];
const STATUS_OPTIONS = ['未確保', '注文済', '見送り'];
const SLUGS = {1:'january',2:'february',3:'march',4:'april',5:'may',6:'june',7:'july',8:'august',9:'september',10:'october',11:'november',12:'december'};
const BAND_LABELS = ['〜10万円','10-20万円','20-30万円','30-50万円','50-100万円','100万円超'];
// 日本の祝日 (権利付最終日・D-N計算の概算用。年末年始の市場休場は土日に吸収されるため省略)
const HOLIDAYS = ['2026-01-01','2026-01-12','2026-02-11','2026-02-23','2026-03-20','2026-04-29','2026-05-03','2026-05-04','2026-05-05','2026-05-06','2026-07-20','2026-08-11','2026-09-21','2026-09-22','2026-09-23','2026-10-12','2026-11-03','2026-11-23','2027-01-01','2027-01-11','2027-02-11','2027-02-23','2027-03-21','2027-04-29','2027-05-03','2027-05-04','2027-05-05','2027-07-19','2027-08-11','2027-09-20','2027-09-23','2027-10-11','2027-11-03','2027-11-23'];

// ============ 日付 (JST・通年汎用) ============
function todayJst_() {
  const s = Utilities.formatDate(new Date(), 'Asia/Tokyo', 'yyyy-MM-dd');
  const p = s.split('-').map(Number);
  return new Date(p[0], p[1] - 1, p[2]);
}
function iso_(d) {
  return Utilities.formatDate(d, 'Asia/Tokyo', 'yyyy-MM-dd');
}
function isBiz_(d) {
  const wd = d.getDay();
  if (wd === 0 || wd === 6) return false;
  return HOLIDAYS.indexOf(iso_(d)) === -1;
}
function monthEndKengi_(y, m) {
  const last = new Date(y, m, 0); // 月末
  const d = new Date(last.getFullYear(), last.getMonth(), last.getDate());
  let back = 0;
  while (back < 2) { // T+2決済: 月末から2営業日遡る
    d.setDate(d.getDate() - 1);
    if (isBiz_(d)) back++;
  }
  return d;
}
function bizDaysLeft_(today, lastDay) {
  if (today >= lastDay) return 0;
  let n = 0;
  const d = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 1);
  while (d <= lastDay) {
    if (isBiz_(d)) n++;
    d.setDate(d.getDate() + 1);
  }
  return n;
}
function resolveRights_() {
  if (CFG.RIGHTS_OVERRIDE) {
    const p = CFG.RIGHTS_OVERRIDE.split('-').map(Number);
    return { rights: CFG.RIGHTS_OVERRIDE, year: p[0], month: p[1], kengi: monthEndKengi_(p[0], p[1]) };
  }
  const t = todayJst_();
  let y = t.getFullYear(), m = t.getMonth() + 1;
  for (let i = 0; i < 3; i++) {
    const k = monthEndKengi_(y, m);
    const kd = new Date(k.getFullYear(), k.getMonth(), k.getDate());
    if (kd >= t) return { rights: y + '-' + ('0' + m).slice(-2), year: y, month: m, kengi: kd };
    m++;
    if (m > 12) { y++; m = 1; }
  }
  throw new Error('権利月の解決に失敗');
}

// ============ エントリーポイント ============
function setupAll() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  ensureSheet_(ss, SH_MASTER, MASTER_HEADERS, 1000, 14);
  ensureSheet_(ss, SH_HISTORY, HISTORY_HEADERS, 20000, 20);
  const dash = ensureSheet_(ss, SH_DASH, DASH_HEADERS, 1000, 32);
  buildDashboard_(dash, '', true);
  SpreadsheetApp.getUi().alert('セットアップ完了。次に runDaily を実行してください。');
}

function runDaily() {
  const info = resolveRights_();
  const today = todayJst_();
  const dN = bizDaysLeft_(today, info.kengi);
  const calLeft = Math.max(Math.round((info.kengi - today) / 86400000), 0);
  console.log('[run] 権利月=' + info.rights + ' 最終日=' + iso_(info.kengi) + ' D-' + dN);

  const routine = fetchRoutine_(info.year, info.month);
  Utilities.sleep(1500);
  const gmap = fetchGokigen_(String(info.month));
  console.log('[run] routine=' + routine.length + '件 gokigen=' + Object.keys(gmap).length + '件');

  const built = buildRows_(info.rights, dN, calLeft, routine, gmap);
  console.log('[run] join(Full Outer): history ' + built.history.length + '件');

  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const watched = updateMaster_(ss, built.master);
  appendHistory_(ss, built.history);
  const dash = ss.getSheetByName(SH_DASH) || ensureSheet_(ss, SH_DASH, DASH_HEADERS, 1000, 32);
  const needBuild = !dash.getRange('D2').getValue();
  buildDashboard_(dash, info.rights, needBuild);
  SpreadsheetApp.flush();
  console.log('[run] 完了。監視ON=' + watched + '件。dashboardを確認してください。');
}

// ============ 情報源A: ルーティンHTML ============
function fetchRoutine_(year, month) {
  const url = ROUTINE_BASE + '/' + SLUGS[month] + '-list/';
  const res = UrlFetchApp.fetch(url, { muteHttpExceptions: true, followRedirects: true, headers: { 'User-Agent': UA } });
  if (res.getResponseCode() !== 200) throw new Error('routine HTTP ' + res.getResponseCode() + ': ' + url);
  const recs = parseMonthHtml_(res.getContentText('UTF-8'));
  if (recs.length === 0) throw new Error('routine表が0件でした。サイト構造変更の可能性あり。');
  const merged = {};
  recs.forEach(r => { merged[r.code] = r; });
  return Object.keys(merged).map(k => merged[k]);
}
function parseMonthHtml_(html) {
  const out = [];
  const sectionRe = /<h2[^>]*>([\s\S]*?)<\/h2>\s*([\s\S]*?)<table[^>]*>([\s\S]*?)<\/table>/gi;
  let sm;
  while ((sm = sectionRe.exec(html)) !== null) {
    const band = normalizeBand_(stripTags_(sm[1]).replace(/\s+/g, ''));
    if (BAND_LABELS.indexOf(band) === -1) continue;
    const rowRe = /<tr[^>]*>([\s\S]*?)<\/tr>/gi;
    let rm;
    while ((rm = rowRe.exec(sm[3])) !== null) {
      if (/<th/i.test(rm[1])) continue;
      const cells = [];
      const cellRe = /<t[dh][^>]*>([\s\S]*?)<\/t[dh]>/gi;
      let cm;
      while ((cm = cellRe.exec(rm[1])) !== null) cells.push(cm[1]);
      if (cells.length < 11) continue;
      const rec = buildRecord_(cells, band);
      if (rec) out.push(rec);
    }
  }
  return out;
}
function buildRecord_(cells, band) {
  const code = stripTags_(cells[0]).replace(/\D/g, '');
  if (!/^\d{4}$/.test(code)) return null;
  const linkM = cells[1].match(/<a[^>]*href="([^"]+)"[^>]*>([\s\S]*?)<\/a>/i);
  return {
    code: code,
    name: stripTags_(linkM ? linkM[2] : cells[1]).trim(),
    funds_man: num_(stripTags_(cells[2])),
    yutai_value: num_(stripTags_(cells[3])),
    yutai_content: stripTags_(cells[4]).trim(),
    yield_pct: num_(stripTags_(cells[5])),
    rakuten_qty: parseQty_(stripTags_(cells[6])),
    nikko_qty: parseQty_(stripTags_(cells[8])),
    sbi_signal: parseSbi_(stripTags_(cells[9])),
    gmo_limit: parseQty_(stripTags_(cells[10])),
    band: band,
  };
}
function parseQty_(raw) {
  const s = String(raw || '').replace(/\s/g, '').replace(/,/g, '');
  if (!s || s === '-' || s === '―' || s === 'ー') return null;
  if (/大量/.test(s)) return null;
  if (/残無/.test(s)) return 0;
  if (s === '×' || s === '✕') return 0;
  if (s === '◎' || s === '▲') return null;
  let m = s.match(/^([\d.]+)万$/);
  if (m) return Math.round(parseFloat(m[1]) * 10000);
  m = s.match(/^([\d.]+)$/);
  if (m) return parseFloat(m[1]);
  m = s.match(/([\d.]+)万/);
  if (m) return Math.round(parseFloat(m[1]) * 10000);
  return null;
}
function parseSbi_(raw) {
  const s = String(raw || '').replace(/\s/g, '');
  if (s.indexOf('◎') !== -1) return '◎';
  if (s.indexOf('▲') !== -1) return '▲';
  if (s.indexOf('×') !== -1 || s.indexOf('✕') !== -1) return '×';
  return s || '';
}
function normalizeBand_(t) {
  if (/10万円以下/.test(t)) return '〜10万円';
  if (/10万円超/.test(t)) return '10-20万円';
  if (/20万円超/.test(t)) return '20-30万円';
  if (/30万円超/.test(t)) return '30-50万円';
  if (/50万円超/.test(t)) return '50-100万円';
  if (/100万円超/.test(t)) return '100万円超';
  return t.slice(0, 20);
}
function stripTags_(s) {
  return String(s || '').replace(/<br\s*\/?>/gi, ' ').replace(/<[^>]+>/g, '').replace(/&nbsp;/gi, ' ').replace(/&amp;/gi, '&').trim();
}
function num_(s) {
  const t = String(s || '').replace(/,/g, '').match(/[\d.]+/);
  return t ? parseFloat(t[0]) : null;
}

// ============ 情報源B: Gokigen API (POST + Shift_JIS) ============
function fetchGokigen_(apiMonth) {
  const res = UrlFetchApp.fetch(GOKIGEN_API, { method: 'post', payload: { month: apiMonth }, muteHttpExceptions: true, headers: { 'User-Agent': UA } });
  if (res.getResponseCode() !== 200) throw new Error('gokigen HTTP ' + res.getResponseCode());
  const json = JSON.parse(res.getContentText('Shift_JIS'));
  if (!Array.isArray(json) || json.length === 0) throw new Error('gokigen空レスポンス');
  const map = {};
  json.forEach(r => {
    if (!r || !r.code || r.code === '0000') return; // [0]は更新時刻ダミー行
    const code = String(r.code);
    map[code] = {
      name: clean_(r.name),
      kabuka: toNum_(r.kabuka),
      kabusu: toNum_(r.kabusu),
      yutai: clean_(r.yutai),
      rimawari: toNum_(r.rimawari),
      cross_days: toNum_(r.c_nissu),
      kisei: clean_(r.recent_gyaku_kisei),
      max5_gyaku: toNum_(r.max5_gyaku),
      stocks: {
        '日興': toNum_(r.nvol), 'カブ': toNum_(r.kvol), '楽天': toNum_(r.rvol),
        'SBI': toNum_(r.svol), 'GMO': toNum_(r.gvol),
        '松井': toNum_(r.mvol), 'マネ': toNum_(r.xvol),
      },
    };
  });
  return map;
}
function clean_(v) {
  const s = String(v === null || v === undefined ? '' : v);
  return s === 'null' ? '' : s;
}
function toNum_(v) {
  if (v === null || v === undefined || v === '') return null;
  const n = Number(v);
  return isNaN(n) ? null : n;
}

// ============ Full Outer Join ============
function buildRows_(rights, dN, calLeft, routine, gmap) {
  const rmap = {};
  routine.forEach(r => { rmap[r.code] = r; });
  const codes = Array.from(new Set(Object.keys(rmap).concat(Object.keys(gmap)))).sort();
  const now = new Date();
  const history = [];
  const master = [];
  codes.forEach(code => {
    const r = rmap[code] || null;
    const g = gmap[code] || null;
    const st = (g && g.stocks) || {};
    let funds = r ? r.funds_man : null;
    let kabuka = (g && g.kabuka) || (funds ? funds * 10000 / 100 : null);
    const kabusu = (g && g.kabusu) || 100;
    if (funds === null && kabuka) funds = kabuka * kabusu / 10000;
    const days = (g && g.cross_days) || calLeft;
    const cost = (kabuka && days) ? Math.round(kabuka * kabusu * CFG.RATE * days / 365) : null;
    const totalYield = (g && g.rimawari !== null && g.rimawari !== undefined && g.rimawari !== '')
      ? Math.round(g.rimawari * 100 * 100) / 100 : (r ? r.yield_pct : null);
    const seido = [g && g.kisei ? '注意喚起:' + g.kisei : '', g && g.max5_gyaku ? 'max逆日歩:' + g.max5_gyaku : ''].filter(Boolean).join(' / ');
    history.push([now, rights, dN, code, (r && r.name) || (g && g.name) || '',
      nz_(st['日興']), nz_(st['カブ']), nz_(st['楽天']), nz_(st['SBI']), nz_(st['GMO']), nz_(st['松井']), nz_(st['マネ']),
      nz_(kabuka), nz_(kabusu), nz_(g && g.cross_days), nz_(cost), nz_(g && g.max5_gyaku),
      nz_(r && r.rakuten_qty), nz_(r && r.nikko_qty), (r && r.sbi_signal) || '']);
    master.push({
      watch: false, priority: '', code: code,
      name: (r && r.name) || (g && g.name) || '',
      content: (r && r.yutai_content) || (g && g.yutai) || '',
      value: r ? nz_(r.yutai_value) : '',
      funds: funds === null ? '' : Math.round(funds * 100) / 100,
      totalYield: totalYield === null || totalYield === undefined ? '' : totalYield,
      gmoLimit: r ? nz_(r.gmo_limit) : '',
      seido: seido, rights: rights,
    });
  });
  return { history: history, master: master };
}
function nz_(v) {
  return (v === null || v === undefined) ? '' : v;
}

// ============ 書き込み ============
function ensureSheet_(ss, name, headers, rows, cols) {
  let sh = ss.getSheetByName(name);
  if (!sh) sh = ss.insertSheet(name);
  if (sh.getMaxRows() < rows) sh.insertRowsAfter(sh.getMaxRows(), rows - sh.getMaxRows());
  if (sh.getMaxColumns() < cols) sh.insertColumnsAfter(sh.getMaxColumns(), cols - sh.getMaxColumns());
  if (sh.getLastRow() === 0) {
    sh.getRange(1, 1, 1, headers.length).setValues([headers]);
    sh.setFrozenRows(1);
  }
  return sh;
}
function updateMaster_(ss, incoming) {
  const sh = ss.getSheetByName(SH_MASTER);
  const last = sh.getLastRow();
  const old = {}; // key = 権利月|コード
  if (last > 1) {
    const vals = sh.getRange(2, 1, last - 1, MASTER_HEADERS.length).getValues();
    vals.forEach(row => {
      if (String(row[2]).trim() !== '') old[String(row[11]).trim() + '|' + String(row[2]).trim()] = row;
    });
  }
  const watchedCodes = {};
  Object.keys(old).forEach(k => {
    if (old[k][0] === true) watchedCodes[k.split('|')[1]] = true;
  });
  const out = [MASTER_HEADERS];
  const seen = {};
  incoming.forEach(m => {
    const key = m.rights + '|' + m.code;
    seen[key] = true;
    if (old[key]) {
      out.push([old[key][0], old[key][1], m.code, m.name, m.content, m.value, m.funds, m.totalYield, m.gmoLimit, '', m.seido, m.rights]);
    } else {
      let w = false;
      if (CFG.AUTO_WATCH && m.totalYield !== '' && m.funds !== '' && m.totalYield >= CFG.AUTO_WATCH_YIELD && m.funds <= CFG.AUTO_WATCH_FUNDS_MAN) w = true;
      if (!w && watchedCodes[m.code]) w = true;
      out.push([w, m.priority, m.code, m.name, m.content, m.value, m.funds, m.totalYield, m.gmoLimit, '', m.seido, m.rights]);
    }
  });
  Object.keys(old).forEach(k => { // 掲載落ち・他月の行は維持
    if (!seen[k]) {
      const r = old[k].slice(0, MASTER_HEADERS.length);
      while (r.length < MASTER_HEADERS.length) r.push('');
      out.push(r);
    }
  });
  sh.clearContents();
  sh.getRange(1, 1, out.length, MASTER_HEADERS.length).setValues(out);
  sh.getRange('A2:A1000').setDataValidation(SpreadsheetApp.newDataValidation().requireCheckbox().build());
  let n = 0;
  out.slice(1).forEach(r => { if (r[0] === true) n++; });
  console.log('[master] ' + (out.length - 1) + '行 (監視ON: ' + n + ')');
  return n;
}
function appendHistory_(ss, rows) {
  if (rows.length === 0) return;
  const sh = ss.getSheetByName(SH_HISTORY);
  sh.getRange(sh.getLastRow() + 1, 1, rows.length, HISTORY_HEADERS.length).setValues(rows);
  console.log('[history] +' + rows.length + '行追記');
}

// ============ dashboard (数式・書式) ============
function vLatest_(valcol, datecell) {
  const dc = datecell || '$Q$2';
  const table = '{raw_history!B:B&"|"&raw_history!D:D&"|"&raw_history!A:A},{' + valcol + '}';
  return 'VLOOKUP($T$2&"|"&D2:D&"|"&' + dc + ',' + table + ',2,FALSE)';
}
function trendFormula_(valcol, n) {
  return '=MAP(D2:D500,LAMBDA(c,IF(c="","",IFERROR(SPARKLINE(INDEX(SORT(SORTN(' +
    'FILTER({raw_history!A:A,raw_history!' + valcol + ':' + valcol + '},raw_history!D:D=c,raw_history!B:B=$T$2),' +
    n + ',0,1,0),1,TRUE),0,2),{"charttype","line"}),"—"))))';
}
function buildDashboard_(sh, rights, force) {
  if (!force && sh.getRange('D2').getValue()) {
    if (rights && !sh.getRange('T2').getValue()) sh.getRange('T2').setValue(rights);
    return;
  }
  sh.getRange(1, 1, 1, DASH_HEADERS.length).setValues([DASH_HEADERS]);
  const F = {
    'D2': '=INDEX(SORT(FILTER({master_list!C2:C,master_list!B2:B},master_list!A2:A=TRUE,master_list!L2:L=$T$2),2,1,1,1),0,1)',
    'E2': '=ARRAYFORMULA(IF(D2:D="","",IFERROR(VLOOKUP(D2:D,master_list!C:D,2,FALSE),"")))',
    'F2': '=ARRAYFORMULA(IF(D2:D="","",IFERROR(' + vLatest_('raw_history!F:F') + ',"")))',
    'G2': '=ARRAYFORMULA(IF(D2:D="","",IFERROR(' + vLatest_('raw_history!G:G') + ',"")))',
    'H2': '=ARRAYFORMULA(IF(D2:D="","",IFERROR(' + vLatest_('raw_history!H:H') + ',"")))',
    'I2': '=ARRAYFORMULA(IF(D2:D="","",IFERROR(' + vLatest_('raw_history!I:I') + ',"")))',
    'J2': '=ARRAYFORMULA(IF(D2:D="","",IFERROR(' + vLatest_('raw_history!J:J') + ',"")))',
    'B2': '=ARRAYFORMULA(IF(D2:D="","",IF(((AA2:AA="🚨 急変 (◎→▲)")+(AA2:AA="💥 瞬殺 (◎→×)"))*(F2:F<>"")*(N(F2:F)<=$W$2),"🔴今夜確保",IF(N2:N="",IF((M2:M=0)*(I2:I<>2),"⚪枯渇","🟢待機可"),IF((M2:M=0)*(I2:I<>2),"⚪枯渇",IF(M2:M<=N2:N*0.5,"🔴即確保",IF(M2:M<N2:N,"🟡要監視","🟢待機可")))))))',
    'C2': '=ARRAYFORMULA(IF(D2:D="","",IF((N2:N<>"")*(N2:N=0)*(M2:M>0),"🔥補充","")))',
    'K2': '=ARRAYFORMULA(IF(D2:D="","",IF(IFERROR(VLOOKUP(D2:D,master_list!C:F,4,FALSE),0)=0,"—",IFERROR(VLOOKUP(D2:D,master_list!C:F,4,FALSE),0)-IFERROR(' + vLatest_('raw_history!P:P') + ',0))))',
    'L2': '=ARRAYFORMULA(IF(D2:D="","",IFERROR("D-"&INT(IFERROR(VLOOKUP(D2:D,master_list!C:F,4,FALSE),0)*365/(IFERROR(VLOOKUP(D2:D,master_list!C:G,5,FALSE),0)*10000*$P$2)),"—")))',
    'M2': '=ARRAYFORMULA(IF(D2:D="","",N(F2:F)+N(G2:G)+N(H2:H)))',
    'N2': '=ARRAYFORMULA(IF(D2:D="","",IFERROR(' + vLatest_('raw_history!F:F', '$R$2') + ',0)+IFERROR(' + vLatest_('raw_history!G:G', '$R$2') + ',0)+IFERROR(' + vLatest_('raw_history!H:H', '$R$2') + ',0)))',
    'U2': '=ARRAYFORMULA(IF(D2:D="","",IF($V$2="","",IFERROR(VLOOKUP(D2:D&"|"&IFERROR(VLOOKUP($T$2&"|"&D2:D&"|"&$Q$2,{raw_history!B:B&"|"&raw_history!D:D&"|"&raw_history!A:A,raw_history!C:C},2,FALSE),-1),{INDIRECT($V$2&"!D:D")&"|"&INDIRECT($V$2&"!C:C"),INDIRECT($V$2&"!H:H")},2,FALSE),""))))',
    'Z2': '=ARRAYFORMULA(IF(D2:D="","",IFERROR(' + vLatest_('raw_history!T:T') + ',"")))',
    'AA2': '=ARRAYFORMULA(IF(D2:D="","",IF(Z2:Z="","—",IFS((IFERROR(' + vLatest_('raw_history!T:T', '$R$2') + ',"")="◎")*(Z2:Z="▲"),"🚨 急変 (◎→▲)",(IFERROR(' + vLatest_('raw_history!T:T', '$R$2') + ',"")="◎")*(Z2:Z="×"),"💥 瞬殺 (◎→×)",Z2:Z="×","⚪ 枯渇",Z2:Z="▲","▲ 残少",TRUE,"─"))))',
    'AE2': '=ARRAYFORMULA(IF(D2:D="","",IF((F2:F="")+($R$2=""),"",F2:F-IFERROR(' + vLatest_('raw_history!F:F', '$R$2') + ',0))))',
    'AB2': '=ARRAYFORMULA(IF(D2:D="","",TRIM(IF((F2:F<>"")*(N(F2:F)<$W$2),"⚠日興 ","")&IF((H2:H<>"")*(N(H2:H)<$X$2),"⚠楽天 ",""))))',
    'AC2': '=ARRAYFORMULA(IF(D2:D="","",IFERROR(' + vLatest_('raw_history!K:K') + ',"")))',
    'AD2': '=ARRAYFORMULA(IF(D2:D="","",IFERROR(' + vLatest_('raw_history!L:L') + ',"")))',
    'P1': '年率', 'P2': String(CFG.RATE),
    'Q1': '最新取得', 'Q2': '=IFERROR(MAXIFS(raw_history!A:A,raw_history!B:B,$T$2),"")',
    'R1': '前回取得', 'R2': '=IFERROR(MAXIFS(raw_history!A:A,raw_history!B:B,$T$2,raw_history!A:A,"<"&Q2),"")',
    'T1': '対象月', 'V1': '前年シート', 'W1': '日興閾値', 'W2': String(CFG.NIKKO_TH),
    'X1': '楽天閾値', 'X2': String(CFG.RAKUTEN_TH),
  };
  Object.keys(F).forEach(cell => {
    const v = F[cell];
    if (v.charAt(0) === '=') sh.getRange(cell).setFormula(v);
    else sh.getRange(cell).setValue(v);
  });
  sh.getRange('S1').setValue('推移(楽天直近10回)');
  sh.getRange('S2').setFormula(trendFormula_('H', 10));
  sh.getRange('Y1').setValue('推移(日興直近10回)');
  sh.getRange('Y2').setFormula(trendFormula_('F', 10));
  sh.getRange('Z1').setValue('SBI最新');
  sh.getRange('AA1').setValue('SBI急変アラート');
  sh.getRange('AE1').setValue('日興前日比');
  sh.getRange('AB1').setValue('閾値アラート');
  sh.getRange('AC1').setValue('松井最新');
  sh.getRange('AD1').setValue('マネ最新');
  sh.getRange('U1').setValue('前年同D-N(楽天)');
  if (rights) sh.getRange('T2').setValue(rights);
  applyFormatting_();
  console.log('[dashboard] テンプレ投入');
}
function condRule_(range, formula, bg, fg, bold) {
  const b = SpreadsheetApp.newConditionalFormatRule().whenFormulaSatisfied(formula).setRanges([range]);
  if (bg) b.setBackground(bg);
  if (fg) b.setFontColor(fg);
  if (bold) b.setBold(true);
  return b.build();
}
function applyFormatting_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const dash = ss.getSheetByName(SH_DASH);
  dash.clearConditionalFormatRules();
  dash.getRange('A2:A1000').setDataValidation(
    SpreadsheetApp.newDataValidation().requireValueInList(STATUS_OPTIONS, false).setAllowInvalid(true).build());
  const rules = [
    condRule_(dash.getRange('A2:O1000'), '=ISNUMBER(SEARCH("注文済",$A2))', '#d9d9d9'),
    condRule_(dash.getRange('B2:B1000'), '=ISNUMBER(SEARCH("確保",$B2))', '#fad9d9'),
    condRule_(dash.getRange('C2:C1000'), '=$C2="🔥補充"', '#fcebd1'),
    condRule_(dash.getRange('AA2:AA1000'), '=REGEXMATCH($AA2,"急変|瞬殺")', '#ffccbd', '#bf360d', true),
    condRule_(dash.getRange('F2:F1000'), '=AND($F2<>"",$F2=0)', '#e6e6e6'),
    condRule_(dash.getRange('F2:F1000'), '=AND($F2>=1000,$F2<10000)', '#ffface'),
    condRule_(dash.getRange('F2:F1000'), '=$F2>=10000', '#ccffcc'),
    condRule_(dash.getRange('H2:H1000'), '=AND($H2<>"",$H2<$X$2)', '#ffcccc'),
    condRule_(dash.getRange('AE2:AE1000'), '=$AE2<0', null, '#cc0000', true),
    condRule_(dash.getRange('AE2:AE1000'), '=$AE2>0', null, '#008000', false),
  ];
  dash.setConditionalFormatRules(rules);
  console.log('[dashboard] 書式設定を適用');
}
