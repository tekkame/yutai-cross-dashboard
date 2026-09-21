/**
 * 株主優待クロス 長期蓄積型データベース (Google Sheets + GAS 完全自動化エンジン)
 * 
 * 【特長】
 * 1. 01月〜12月の各権利月シートで長期比較（前年同D-N比較、推移ミニグラフ、枯渇実績）
 * 2. 2大情報源（enjoy-lcl ＋ gokigen-life）をFull Outer Joinし、新規銘柄を自動検知・マスタ追加
 * 3. D-N（権利落ち日までの営業日数）を共通キーとし、年ごとのカレンダーズレを克服
 * 4. GitHub Actions (Python) からの Webhook 受信 (doPost) にも対応
 */

// ============ 設定 ============
// ⚠️ セキュリティ: SpreadsheetID / APIキーはScriptPropertiesで管理してください。
// GASエディタ > [プロジェクトの設定] > [スクリプトプロパティ] に以下を登録:
//   SPREADSHEET_ID = <実際のスプレッドシートID>
//   API_SECRET_KEY = <実際のWebhook認証キー>
const CFG = {
  DEFAULT_SPREADSHEET_ID: PropertiesService.getScriptProperties().getProperty('SPREADSHEET_ID') || 'your_spreadsheet_id_here',
  NIKKO_TH: 10000,       // 日興 在庫アラート閾値 (株)
  RAKUTEN_TH: 5000,      // 楽天 在庫アラート閾値 (株)
  API_SECRET_KEY: PropertiesService.getScriptProperties().getProperty('API_SECRET_KEY') || 'your_secret_key_here', // Webhook 簡易認証キー
};

const ROUTINE_BASE = 'https://yutai.enjoy-lcl.com';
const GOKIGEN_API = 'https://gokigen-life.tokyo/api/00ForWeb/ForZaiko2.php';
const UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36';

const SH_MASTER = 'master_list';
const SH_HISTORY = 'raw_history';
const MONTH_NAMES = ['01月','02月','03月','04月','05月','06月','07月','08月','09月','10月','11月','12月'];
const SLUGS = {1:'january',2:'february',3:'march',4:'april',5:'may',6:'june',7:'july',8:'august',9:'september',10:'october',11:'november',12:'december'};

const MASTER_HEADERS = [
  '監視', '優先度', 'コード', '銘柄名', '優待内容', '優待価値(円)', '必要資金(万)', '総合利回り(%)', '権利月', '年間回数', '前年枯渇タイミング', '初回登録日', '最終確認日'
];

const HISTORY_HEADERS = [
  '取得日時', '権利年月', '残日数(D-N)', 'コード', '銘柄名', '日興在庫', 'カブ在庫', '楽天在庫', 'SBI信号', 'GMO信号', '株価', '株数', '貸株コスト'
];

const MONTH_SHEET_HEADERS = [
  '⭐監視', '判定', 'コード', '銘柄名', '必要資金(万)', '優待内容', '優待価値(円)', '日興最新', 'SBI最新', '日興推移(グラフ)', '【前年実績】日興(同D-N)', '【前年実績】枯渇タイミング', '年間回数', '前日終値'
];

// 日本の祝日（2024〜2032年）
const HOLIDAYS = [
  '2024-01-01','2024-01-08','2024-02-11','2024-02-12','2024-02-23','2024-03-20','2024-04-29','2024-05-03','2024-05-04','2024-05-05','2024-05-06','2024-07-15','2024-08-11','2024-08-12','2024-09-16','2024-09-22','2024-09-23','2024-10-14','2024-11-03','2024-11-04','2024-11-23',
  '2025-01-01','2025-01-13','2025-02-11','2025-02-23','2025-02-24','2025-03-20','2025-04-29','2025-05-03','2025-05-04','2025-05-05','2025-05-06','2025-07-21','2025-08-11','2025-09-15','2025-09-23','2025-10-13','2025-11-03','2025-11-23','2025-11-24',
  '2026-01-01','2026-01-12','2026-02-11','2026-02-23','2026-03-20','2026-04-29','2026-05-03','2026-05-04','2026-05-05','2026-05-06','2026-07-20','2026-08-11','2026-09-21','2026-09-22','2026-09-23','2026-10-12','2026-11-03','2026-11-23',
  '2027-01-01','2027-01-11','2027-02-11','2027-02-23','2027-03-21','2027-03-22','2027-04-29','2027-05-03','2027-05-04','2027-05-05','2027-07-19','2027-08-11','2027-09-20','2027-09-23','2027-10-11','2027-11-03','2027-11-23',
  '2028-01-01','2028-01-10','2028-02-11','2028-02-23','2028-03-20','2028-04-29','2028-05-03','2028-05-04','2028-05-05','2028-07-17','2028-08-11','2028-09-18','2028-09-22','2028-10-09','2028-11-03','2028-11-23'
];

// ============ 日付ユーティリティ ============
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

// ============ シート自動セットアップ ============
function setupLongtermSheets() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  
  // 1. マスタシートの準備
  ensureSheet_(ss, SH_MASTER, MASTER_HEADERS, 2000, MASTER_HEADERS.length);
  
  // 2. 全履歴ログシートの準備
  ensureSheet_(ss, SH_HISTORY, HISTORY_HEADERS, 30000, HISTORY_HEADERS.length);
  
  // 3. 01月〜12月の月別シートの準備
  MONTH_NAMES.forEach(mName => {
    const sh = ensureSheet_(ss, mName, MONTH_SHEET_HEADERS, 800, MONTH_SHEET_HEADERS.length);
    formatMonthSheet_(sh);
  });
  
  SpreadsheetApp.getUi().alert('🎉 長期データベースのセットアップが完了しました！\n01月〜12月シートおよびマスタ・履歴ログが構築されました。');
}

function ensureSheet_(ss, name, headers, rows, cols) {
  let sh = ss.getSheetByName(name);
  if (!sh) {
    sh = ss.insertSheet(name);
  }
  if (sh.getMaxRows() < rows) sh.insertRowsAfter(sh.getMaxRows(), rows - sh.getMaxRows());
  if (sh.getMaxColumns() < cols) sh.insertColumnsAfter(sh.getMaxColumns(), cols - sh.getMaxColumns());
  
  // 見出し行投入
  const r = sh.getRange(1, 1, 1, headers.length);
  r.setValues([headers]);
  r.setBackground('#0f172a').setFontColor('#f1f5f9').setFontWeight('bold').setFontSize(10);
  sh.setFrozenRows(1);
  return sh;
}

function formatMonthSheet_(sh) {
  // A列: チェックボックス
  sh.getRange('A2:A800').setDataValidation(SpreadsheetApp.newDataValidation().requireCheckbox().build());
  
  // 列幅調整
  sh.setColumnWidth(1, 40);  // 監視
  sh.setColumnWidth(2, 75);  // 判定
  sh.setColumnWidth(3, 55);  // コード
  sh.setColumnWidth(4, 120); // 銘柄名
  sh.setColumnWidth(5, 75);  // 必要資金
  sh.setColumnWidth(6, 180); // 優待内容
  sh.setColumnWidth(7, 75);  // 優待価値
  sh.setColumnWidth(8, 80);  // 日興最新
  sh.setColumnWidth(9, 60);  // SBI最新
  sh.setColumnWidth(10, 130); // 推移グラフ
  sh.setColumnWidth(11, 110); // 前年日興(同D-N)
  sh.setColumnWidth(12, 110); // 前年枯渇日
  sh.setColumnWidth(13, 70);  // 年間回数
}

// ============ 日次自動更新エンジン ============
function runDailyUpdate(optMonth) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const today = todayJst_();
  let targetYear = today.getFullYear();
  let targetMonth = optMonth || (today.getMonth() + 1);
  
  const kengi = monthEndKengi_(targetYear, targetMonth);
  const dN = bizDaysLeft_(today, kengi);
  const rightsStr = targetYear + '-' + ('0' + targetMonth).slice(-2);
  const monthTabName = ('0' + targetMonth).slice(-2) + '月';
  
  console.log('[run] 対象権利月=' + rightsStr + ' D-' + dN + ' タブ=' + monthTabName);
  
  // 1. 2サイトからスクレイピング
  let routine = [];
  try {
    routine = fetchRoutine_(targetYear, targetMonth);
  } catch(e) {
    console.warn('Routine fetch warn: ' + e);
  }
  Utilities.sleep(1500);
  const gmap = fetchGokigen_(String(targetMonth));
  
  // 2. Full Outer Join
  const rmap = {};
  routine.forEach(r => { rmap[r.code] = r; });
  const allCodes = Array.from(new Set([...Object.keys(rmap), ...Object.keys(gmap)])).sort();
  console.log('[run] 銘柄総数: ' + allCodes.length);
  
  const stampStr = Utilities.formatDate(new Date(), 'Asia/Tokyo', 'yyyy-MM-dd HH:mm');
  const histRows = [];
  const masterUpdates = [];
  
  allCodes.forEach(code => {
    const r = rmap[code] || {};
    const g = gmap[code] || {};
    const name = r.name || g.name || '';
    if (!name || name.toLowerCase() === 'null') return;
    
    const content = r.yutai_content || g.yutai || '';
    const val = r.yutai_value || g.yutai_value || 0;
    const funds = r.funds_man || g.funds_man || 0;
    const yieldPct = r.yield_pct || g.yield_pct || 0;
    const nikko = r.nikko_qty !== undefined ? r.nikko_qty : (g.nikko_qty !== undefined ? g.nikko_qty : '');
    const kabu = g.kabu_qty !== undefined ? g.kabu_qty : '';
    const rakuten = r.rakuten_qty !== undefined ? r.rakuten_qty : (g.rakuten_qty !== undefined ? g.rakuten_qty : '');
    const sbi = r.sbi_signal || g.sbi_signal || '―';
    const gmo = g.gmo_signal || '―';
    const price = g.stock_price || '';
    const qty = g.kabusu || 100;
    
    histRows.push([
      stampStr, rightsStr, dN, code, name, nikko, kabu, rakuten, sbi, gmo, price, qty, 0
    ]);
    
    masterUpdates.push({
      code: code, name: name, content: content, value: val, funds: funds,
      yield: yieldPct, month: String(targetMonth)
    });
  });
  
  // 3. raw_history にアペンド
  const hSheet = ss.getSheetByName(SH_HISTORY);
  if (hSheet && histRows.length > 0) {
    const startRow = hSheet.getLastRow() + 1;
    hSheet.getRange(startRow, 1, histRows.length, HISTORY_HEADERS.length).setValues(histRows);
  }
  
  // 4. master_list の更新・新銘柄自動追加 (UPSERT)
  upsertMaster_(ss, masterUpdates, String(targetMonth));
  
  // 5. 月別シートの更新・同期
  syncMonthSheet_(ss, monthTabName, rightsStr, dN);
  
  console.log('[run] 完了: ' + monthTabName + ' 更新完了');
}

function upsertMaster_(ss, updates, monthStr) {
  const sh = ss.getSheetByName(SH_MASTER);
  if (!sh) return;
  const data = sh.getDataRange().getValues();
  const codeRowMap = {};
  for (let i = 1; i < data.length; i++) {
    const c = String(data[i][2]);
    if (c) codeRowMap[c] = i + 1;
  }
  
  const todayStr = Utilities.formatDate(new Date(), 'Asia/Tokyo', 'yyyy-MM-dd');
  const newRows = [];
  
  updates.forEach(u => {
    const rowIdx = codeRowMap[u.code];
    if (rowIdx) {
      // 既存銘柄の更新: 権利月リストをマージ (例: "3" に "9" を追加 -> "3,9")
      const curMonthStr = String(data[rowIdx - 1][8] || '');
      const months = new Set(curMonthStr.split(',').map(s => s.trim()).filter(Boolean));
      months.add(monthStr);
      const updatedMonths = Array.from(months).sort((a,b)=>Number(a)-Number(b)).join(',');
      const annualCount = months.size >= 2 ? `年${months.size}回` : '年1回';
      
      sh.getRange(rowIdx, 4).setValue(u.name);
      if (u.content) sh.getRange(rowIdx, 5).setValue(u.content);
      if (u.value > 0) sh.getRange(rowIdx, 6).setValue(u.value);
      if (u.funds > 0) sh.getRange(rowIdx, 7).setValue(u.funds);
      sh.getRange(rowIdx, 9).setValue(updatedMonths);
      sh.getRange(rowIdx, 10).setValue(annualCount);
      sh.getRange(rowIdx, 13).setValue(todayStr); // 最終確認日
    } else {
      // ★新規銘柄の自動追加 (新銘柄自動検出)
      newRows.push([
        false, 5, u.code, u.name, u.content, u.value, u.funds, u.yield,
        monthStr, '年1回', '―', todayStr, todayStr
      ]);
    }
  });
  
  if (newRows.length > 0) {
    const startRow = sh.getLastRow() + 1;
    sh.getRange(startRow, 1, newRows.length, MASTER_HEADERS.length).setValues(newRows);
    console.log('[master] 新規銘柄 ' + newRows.length + '件を自動追加しました！');
  }
}

function syncMonthSheet_(ss, monthTabName, rightsStr, currentDn) {
  const mSheet = ss.getSheetByName(monthTabName);
  const masterSheet = ss.getSheetByName(SH_MASTER);
  if (!mSheet || !masterSheet) return;
  
  const mNum = parseInt(monthTabName.replace('月', ''), 10);
  const mData = masterSheet.getDataRange().getValues();
  
  // 該当月を含む銘柄を抽出
  const targetItems = [];
  for (let i = 1; i < mData.length; i++) {
    const row = mData[i];
    const c = String(row[2]);
    const monthsStr = String(row[8]);
    const mList = monthsStr.split(',').map(s => parseInt(s.trim(), 10));
    if (mList.includes(mNum)) {
      targetItems.push({
        watch: row[0],
        code: c,
        name: row[3],
        content: row[4],
        value: row[5],
        funds: row[6],
        annualCount: row[9] || '年1回',
        prevDeplete: row[10] || '―'
      });
    }
  }
  
  // 資金昇順ソート
  targetItems.sort((a,b) => (Number(a.funds) || 999) - (Number(b.funds) || 999));
  
  // 月別シートへ反映 (A2:N...)
  const rows = [];
  targetItems.forEach((item, idx) => {
    const rowNum = idx + 2;
    // SPARKLINE 式 (raw_history の直近15回の推移)
    const sparkFormula = `=IFERROR(SPARKLINE(INDEX(SORT(SORTN(FILTER({raw_history!A:A, raw_history!F:F}, raw_history!D:D="${item.code}", raw_history!B:B="${rightsStr}"), 15, 0, 1, 0), 1, TRUE), 0, 2), {"charttype","line";"color","#38bdf8";"linewidth",1.5}), "―")`;
    
    // 前年同D-N比較式 (前年の同じ残日数 D-N の在庫を検索)
    const prevYear = parseInt(rightsStr.split('-')[0], 10) - 1;
    const prevRightsStr = prevYear + '-' + rightsStr.split('-')[1];
    const prevDnFormula = `=IFERROR(INDEX(raw_history!F:F, MATCH("${prevRightsStr}|${item.code}|${currentDn}", raw_history!B:B & "|" & raw_history!D:D & "|" & raw_history!C:C, 0)), "―")`;
    
    // 最新日興在庫
    const latestNikkoFormula = `=IFERROR(VLOOKUP("${item.code}", SORT(FILTER({raw_history!D:D, raw_history!F:F, raw_history!A:A}, raw_history!B:B="${rightsStr}"), 3, FALSE), 2, FALSE), "―")`;
    // 最新SBI信号
    const latestSbiFormula = `=IFERROR(VLOOKUP("${item.code}", SORT(FILTER({raw_history!D:D, raw_history!I:I, raw_history!A:A}, raw_history!B:B="${rightsStr}"), 3, FALSE), 2, FALSE), "―")`;
    
    rows.push([
      item.watch,
      `=IF(G${rowNum}="―","⚪枯渇",IF(OR(I${rowNum}="×",I${rowNum}="▲"),"🔴今夜確保",IF(G${rowNum}<10000,"🟡要監視","🟢待機可")))`,
      item.code,
      item.name,
      item.funds || '―',
      item.content || '―',
      item.value || '―',
      latestNikkoFormula,
      latestSbiFormula,
      sparkFormula,
      prevDnFormula,
      item.prevDeplete,
      item.annualCount,
      '―'
    ]);
  });
  
  if (rows.length > 0) {
    mSheet.getRange(2, 1, rows.length, MONTH_SHEET_HEADERS.length).setValues(rows);
  }
}

// ============ Webhook API (Pythonからの受信) ============
function doPost(e) {
  try {
    const postData = JSON.parse(e.postData.contents);
    if (postData.secret !== CFG.API_SECRET_KEY) {
      return ContentService.createTextOutput(JSON.stringify({status: 'error', message: 'Unauthorized'})).setMimeType(ContentService.MimeType.JSON);
    }
    
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    if (postData.action === 'append_history' && Array.isArray(postData.rows)) {
      const hSheet = ss.getSheetByName(SH_HISTORY);
      if (hSheet && postData.rows.length > 0) {
        const startRow = hSheet.getLastRow() + 1;
        hSheet.getRange(startRow, 1, postData.rows.length, postData.rows[0].length).setValues(postData.rows);
      }
      return ContentService.createTextOutput(JSON.stringify({status: 'success', count: postData.rows.length})).setMimeType(ContentService.MimeType.JSON);
    }
    
    if (postData.action === 'run_daily') {
      runDailyUpdate(postData.month);
      return ContentService.createTextOutput(JSON.stringify({status: 'success', message: 'runDaily executed'})).setMimeType(ContentService.MimeType.JSON);
    }
    
    return ContentService.createTextOutput(JSON.stringify({status: 'ignored'})).setMimeType(ContentService.MimeType.JSON);
  } catch(err) {
    return ContentService.createTextOutput(JSON.stringify({status: 'error', message: String(err)})).setMimeType(ContentService.MimeType.JSON);
  }
}

// ============ スクレイピング補助 ============
function fetchRoutine_(year, month) {
  const url = ROUTINE_BASE + '/' + SLUGS[month] + '-list/';
  const res = UrlFetchApp.fetch(url, { muteHttpExceptions: true, followRedirects: true, headers: { 'User-Agent': UA } });
  if (res.getResponseCode() !== 200) throw new Error('routine HTTP ' + res.getResponseCode());
  return parseMonthHtml_(res.getContentText('UTF-8'));
}

function parseMonthHtml_(html) {
  const out = [];
  const sectionRe = /<h2[^>]*>([\s\S]*?)<\/h2>\s*([\s\S]*?)<table[^>]*>([\s\S]*?)<\/table>/gi;
  let sm;
  while ((sm = sectionRe.exec(html)) !== null) {
    const tableHtml = sm[3];
    const trRe = /<tr[^>]*>([\s\S]*?)<\/tr>/gi;
    let trm;
    while ((trm = trRe.exec(tableHtml)) !== null) {
      const tdRe = /<td[^>]*>([\s\S]*?)<\/td>/gi;
      const tds = [];
      let tdm;
      while ((tdm = tdRe.exec(trm[1])) !== null) {
        tds.push(tdm[1].replace(/<[^>]+>/g, '').trim());
      }
      if (tds.length >= 7) {
        const code = (tds[0].match(/\d{4}/) || [])[0];
        if (code) {
          out.push({
            code: code,
            name: tds[1],
            funds_man: parseFloat(tds[2].replace(/[^\d.]/g, '')) || null,
            yutai_value: parseFloat(tds[3].replace(/[^\d.]/g, '')) || null,
            yutai_content: tds[4],
            nikko_qty: parseQty_(tds[5]),
            sbi_signal: tds[6].includes('◎') ? '◎' : (tds[6].includes('▲') ? '▲' : (tds[6].includes('×') ? '×' : '―'))
          });
        }
      }
    }
  }
  return out;
}

function fetchGokigen_(monthStr) {
  const payload = 'month=' + encodeURIComponent(monthStr);
  const opt = {
    method: 'post', contentType: 'application/x-www-form-urlencoded',
    payload: payload, muteHttpExceptions: true, headers: { 'User-Agent': UA }
  };
  const res = UrlFetchApp.fetch(GOKIGEN_API, opt);
  if (res.getResponseCode() !== 200) return {};
  const json = JSON.parse(res.getContentText('Shift_JIS'));
  const list = json.zaikoList || [];
  const map = {};
  list.forEach(item => {
    const c = String(item.code || '');
    if (c) {
      map[c] = {
        name: item.name,
        stock_price: parseFloat(item.stock_price) || null,
        kabusu: parseFloat(item.kabusu) || 100,
        yutai: item.yutai,
        yutai_value: parseFloat(item.yutai_value) || 0,
        funds_man: (parseFloat(item.stock_price) && parseFloat(item.kabusu)) ? Math.round(parseFloat(item.stock_price)*parseFloat(item.kabusu)/10000*10)/10 : null,
        nikko_qty: parseQty_(item.nikko),
        sbi_signal: item.sbi === '◎' ? '◎' : (item.sbi === '▲' ? '▲' : (item.sbi === '×' ? '×' : '―')),
        gmo_signal: item.gmo || '―'
      };
    }
  });
  return map;
}

function parseQty_(s) {
  if (!s || s === '―' || s === '0' || s === '-') return 0;
  const clean = String(s).replace(/,/g, '').replace(/株/g, '').trim();
  const n = parseFloat(clean);
  return isNaN(n) ? 0 : n;
}
