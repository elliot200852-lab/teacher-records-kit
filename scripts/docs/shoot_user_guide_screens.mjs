#!/usr/bin/env node
/* ══════════════════════════════════════════════════════════════════════
   shoot_user_guide_screens.mjs — 給 docs/USER-GUIDE.md 拍畫面截圖

   為什麼要這支：老師操作書裡的每一張圖都必須是「這一版程式真的長的樣子」。
   手動截圖會過期、會忘了重拍，所以改成一支腳本：
     ① 跑 scripts/build_preview.py 產生單檔離線預覽（示範模式、假資料、不連網）
     ② 用本機 Chrome 無頭開那個檔，走真的 UI（改 hash、點真的按鈕）
     ③ 把每一個畫面存成 PNG

   截圖**不進 repo**（repo 的鐵則：內容檔與二進位不進版本控制），
   所以預設輸出在系統暫存區，要留就自己 --out 到別的地方。

   用法（playwright-core 不裝在這個 repo 裡，用 NODE_PATH 指過去）：

     NODE_PATH=<某個有 playwright-core 的 node_modules> \
       node scripts/docs/shoot_user_guide_screens.mjs [--out <目錄>] [--only 01,05]

   旗標：
     --out <目錄>    PNG 放哪（預設 <暫存區>/trk-user-guide-img）
     --only a,b,c    只拍編號開頭是這幾個的（除錯用）
     --keep-preview  拍完不刪 preview/（預設也不刪，這個旗標只是留著給人看得懂）
     --list          只印會拍哪幾張，不開瀏覽器

   這支腳本**除了 preview/（已被 .gitignore 擋住）以外，不寫 repo 裡任何一個檔**。
   ══════════════════════════════════════════════════════════════════════ */

import { spawnSync } from 'node:child_process';
import { mkdirSync, existsSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..', '..');          // scripts/docs → repo 根目錄
const PREVIEW = path.join(ROOT, 'preview', 'teacher-records-kit-預覽.html');

// ── 旗標 ──────────────────────────────────────────────────────────────
const argv = process.argv.slice(2);
function flag(name, dflt = null) {
  const i = argv.indexOf(name);
  return i >= 0 && argv[i + 1] && !argv[i + 1].startsWith('--') ? argv[i + 1] : dflt;
}
const OUT = path.resolve(flag('--out', path.join(tmpdir(), 'trk-user-guide-img')));
const ONLY = (flag('--only', '') || '').split(',').map(s => s.trim()).filter(Boolean);
const LIST_ONLY = argv.includes('--list');

const DESKTOP = { width: 1280, height: 800 };
const PHONE = { width: 390, height: 844 };

// ── 要拍哪幾張（編號 = 檔名前綴 = USER-GUIDE.md 裡 img/NN-slug.png 的 NN）──
// 每一項：{ name, 說明, 怎麼拍 }
const SHOTS = [
  ['01-desktop-overview', '電腦上的學生記錄一覽（分頁列、記錄類型、學生卡）'],
  ['02-phone-overview', '手機上的學生記錄一覽'],
  ['03-phone-student-detail', '手機上點進一位學生的明細頁'],
  ['04-phone-add-form', '手機上「＋ 新增一則記錄」的表單打開'],
  ['05-tag-chips', '分類詞按鈕（點一下就加上 #標籤）'],
  ['06-pack-menu', '「產生期末素材 ▾」選單打開'],
  ['07-export-menu', '「匯出 ▾」選單打開（Word／PDF）'],
  ['08-course-tab', '課程記錄分頁'],
  ['09-business-tab', '業務記錄分頁'],
  ['10-statusbar', '頂端同步狀態列特寫（灰／紅／琥珀三種顏色同時出現）'],
  ['11-offline-bar', '離線提示條特寫'],
  ['12-demo-banner', '示範模式的黃色橫幅'],
  ['13-iep-goals', 'IEP 學生明細頁上方的「目標清單」卡'],
  ['14-login', '登入畫面（Google 登入）'],
  ['15-no-access', '別的帳號打開時的「無權檢視」畫面'],
];

function wanted(name) {
  return !ONLY.length || ONLY.some(p => name.startsWith(p));
}

if (LIST_ONLY) {
  SHOTS.filter(([n]) => wanted(n)).forEach(([n, d]) => console.log(`${n}.png  ${d}`));
  process.exit(0);
}

// ── ① 產生預覽檔 ──────────────────────────────────────────────────────
console.log('── 產生離線預覽（scripts/build_preview.py）');
const py = spawnSync('python3', [path.join('scripts', 'build_preview.py')], {
  cwd: ROOT, encoding: 'utf8',
});
if (py.status !== 0) {
  console.error(py.stdout || '', py.stderr || '');
  console.error('✗ build_preview.py 失敗，停手。');
  process.exit(1);
}
process.stdout.write(py.stdout);
if (!existsSync(PREVIEW)) {
  console.error('✗ 找不到 ' + PREVIEW);
  process.exit(1);
}

// ── ② 開瀏覽器 ────────────────────────────────────────────────────────
/* playwright-core 不是這個 repo 的相依（repo 裡刻意不跑 npm install），
   所以要從外面指一個 node_modules 進來。ESM 的 import 不吃 NODE_PATH，
   得自己把路徑組出來再用 file:// 載。三條路依序試：
     ① --node-modules <dir>
     ② 環境變數 NODE_PATH（可以用 : 串多個）
     ③ 直接 import（万一哪天真的裝在這裡） */
async function loadPlaywright() {
  const dirs = [];
  const fromFlag = flag('--node-modules', null);
  if (fromFlag) dirs.push(path.resolve(fromFlag));
  (process.env.NODE_PATH || '').split(path.delimiter).filter(Boolean)
    .forEach(d => dirs.push(path.resolve(d)));
  for (const d of dirs) {
    // index.mjs 先試：index.js 是 CommonJS，用 file:// import 進來時
    // 具名匯出（chromium）抓不到，只會掛在 default 上。
    for (const entry of ['playwright-core/index.mjs', 'playwright-core/index.js']) {
      const p = path.join(d, entry);
      if (!existsSync(p)) continue;
      const mod = await import(pathToFileURL(p).href);
      return mod.chromium ? mod : (mod.default || mod);
    }
  }
  return await import('playwright-core');
}

let chromium;
try {
  ({ chromium } = await loadPlaywright());
} catch (err) {
  console.error('✗ 載不到 playwright-core。這個 repo 裡刻意不裝 node 套件，');
  console.error('  請指一個裝了 playwright-core 的 node_modules 進來：');
  console.error('    NODE_PATH=<dir>/node_modules node scripts/docs/shoot_user_guide_screens.mjs');
  console.error('    （或加旗標 --node-modules <dir>/node_modules）');
  console.error('  原始錯誤：' + (err && err.message));
  process.exit(1);
}

mkdirSync(OUT, { recursive: true });
const URL_PREVIEW = pathToFileURL(PREVIEW).href;
const browser = await chromium.launch({ channel: 'chrome', headless: true });

const done = [];
async function shoot(name, target, opts = {}) {
  const file = path.join(OUT, name + '.png');
  await target.screenshot({ path: file, ...opts });
  done.push(name);
  console.log('  ✓ ' + name + '.png');
}

/* 開一頁預覽並等它把示範資料種完。
   clean=true 會先清掉 localStorage 的示範資料，讓每次跑出來的畫面一致。 */
async function open(viewport, hash = '#students', { clean = false } = {}) {
  const ctx = await browser.newContext({ viewport, deviceScaleFactor: 2, locale: 'zh-TW' });
  const page = await ctx.newPage();
  await page.goto(URL_PREVIEW + hash);
  if (clean) {
    await page.evaluate(() => { try { localStorage.clear(); } catch (_) {} });
    await page.reload();
  }
  // 示範模式沒有登入，boot() 直接把 #content 打開；等它畫完再拍
  await page.waitForSelector('#content:not([hidden])', { timeout: 20000 });
  await settle(page);
  return { ctx, page };
}

/* 等當前那一頁真的畫完：一覽頁等學生／課程／業務卡，明細頁等記錄卡。
   「載入中…」那幾個字消失才算數。 */
async function settle(page) {
  await page.waitForSelector(
    '#student-grid .item-card, #course-sections .item-card, #group-sections .item-card, ' +
    '#record-list .record-card, #detail-cards .detail-card',
    { timeout: 20000 }).catch(() => {});
  await page.waitForTimeout(500);
}

/* 換頁（改 hash，跟老師在手機上按返回鍵走的是同一條路） */
async function go(page, hash) {
  await page.evaluate(h => { location.hash = h; }, hash);
  await page.waitForTimeout(400);
  await settle(page);
  await collapseHelp(page);
}

/* 「這一頁需要什麼資料」那個說明框預設是打開的，一屏就被它吃掉一半，
   學生卡反而看不到。截圖前把它收起來（就是點那一顆 toggle，跟老師點的是同一顆）。 */
async function collapseHelp(page) {
  await page.evaluate(() => {
    const body = document.querySelector('#help-body');
    const t = document.getElementById('help-toggle');
    if (body && t && !body.hidden) t.click();
  });
  await page.waitForTimeout(200);
}

try {
  // ── 01 電腦版一覽 ──────────────────────────────────────────────────
  {
    const { ctx, page } = await open(DESKTOP, '#students', { clean: true });
    await collapseHelp(page);
    // 整頁（fullPage）：12 張學生卡都要看得到，一屏裝不下
    if (wanted('01-desktop-overview')) await shoot('01-desktop-overview', page, { fullPage: true });

    // ── 10 狀態列特寫（示範資料刻意做成：同步 2 天前＝灰、備份 9 天前＝紅、
    //      1 則衝突＝琥珀，三種顏色同時在一條列上）──
    if (wanted('10-statusbar')) {
      const bar = await page.$('#statusbar');
      if (bar) await shoot('10-statusbar', bar);
    }

    // ── 12 示範模式橫幅 ──
    if (wanted('12-demo-banner')) {
      const banner = await page.$('#demo-banner');
      if (banner) await shoot('12-demo-banner', banner);
    }

    // ── 11 離線提示條 ──
    // 示範模式刻意不顯示它（renderOfflineBar: el.hidden = DEMO || !offline），
    // 所以這一張把那個真的元素強制顯示出來再拍——文字與樣式都是程式裡的正本。
    if (wanted('11-offline-bar')) {
      await page.evaluate(() => {
        const el = document.getElementById('offline-bar');
        if (el) el.hidden = false;
      });
      const bar = await page.$('#offline-bar');
      if (bar) await shoot('11-offline-bar', bar);
      await page.evaluate(() => {
        const el = document.getElementById('offline-bar');
        if (el) el.hidden = true;
      });
    }

    // ── 08 課程分頁 ／ 09 業務分頁 ──
    if (wanted('08-course-tab')) {
      await go(page, '#courses');
      await shoot('08-course-tab', page, { fullPage: true });
    }
    if (wanted('09-business-tab')) {
      await go(page, '#business');
      await shoot('09-business-tab', page, { fullPage: true });
    }

    // ── 06 產生期末素材 ▾ ／ 07 匯出 ▾ ／ 05 分類詞按鈕：都在學生明細頁上 ──
    await go(page, '#s/S-01/qualitative');
    await page.waitForSelector('#detail:not([hidden])');

    if (wanted('06-pack-menu')) {
      await page.click('#pack-host button');
      await page.waitForTimeout(350);
      await shoot('06-pack-menu', page, {
        clip: await page.evaluate(() => {
          const r = document.querySelector('.detail-head').getBoundingClientRect();
          return { x: 0, y: Math.max(0, r.top - 8), width: 1280, height: 430 };
        }),
      });
      await page.keyboard.press('Escape');
      await page.mouse.click(5, 5);
      await page.waitForTimeout(250);
    }

    if (wanted('07-export-menu')) {
      await page.click('#export-host button');
      await page.waitForTimeout(350);
      await shoot('07-export-menu', page, {
        clip: await page.evaluate(() => {
          const r = document.querySelector('.detail-head').getBoundingClientRect();
          return { x: 0, y: Math.max(0, r.top - 8), width: 1280, height: 430 };
        }),
      });
      await page.mouse.click(5, 5);
      await page.waitForTimeout(250);
    }

    // ── 13 IEP 目標清單卡（示範資料裡 S-07 有兩條目標）──
    if (wanted('13-iep-goals')) {
      await go(page, '#s/S-07/iep');
      await page.waitForSelector('#detail-cards');
      await page.waitForTimeout(600);
      const card = await page.$('#detail-cards');
      if (card) await shoot('13-iep-goals', card);
    }

    // ── 14 登入畫面 ／ 15 無權檢視：示範模式走不到（它不連 Firebase、沒有登入），
    //      所以把 #auth 那兩塊真的畫面直接顯示出來拍。文案是程式裡的正本。
    if (wanted('14-login') || wanted('15-no-access')) {
      await page.evaluate(() => {
        document.getElementById('content').hidden = true;
        document.getElementById('demo-banner').hidden = true;
        // 還沒登入的人本來也讀不到 meta/status，狀態列那條不該出現在這兩張圖裡
        document.getElementById('statusbar').hidden = true;
        document.getElementById('auth').hidden = false;
        document.getElementById('subtitle').textContent =
          '只有擁有者本人能讀寫；資料受 Firestore 伺服器端規則保護。';
      });
      await page.waitForTimeout(250);
      if (wanted('14-login')) {
        await shoot('14-login', page, { clip: { x: 0, y: 0, width: 1280, height: 300 } });
      }
      if (wanted('15-no-access')) {
        await page.evaluate(() => {
          document.getElementById('auth-initial').hidden = true;
          document.getElementById('auth-wrong').hidden = false;
          document.getElementById('wrong-email').textContent = 'someone.else@gmail.com';
        });
        await page.waitForTimeout(250);
        await shoot('15-no-access', page, { clip: { x: 0, y: 0, width: 1280, height: 300 } });
      }
    }
    await ctx.close();
  }

  // ── 手機版 ─────────────────────────────────────────────────────────
  {
    const { ctx, page } = await open(PHONE, '#students');
    await collapseHelp(page);
    // 手機一屏很窄：捲到分頁列，讓「三個分頁＋記錄類型＋學生卡」在同一張圖裡
    if (wanted('02-phone-overview')) {
      await page.evaluate(() => {
        const t = document.getElementById('tab-bar');
        if (t) window.scrollTo(0, Math.max(0, t.getBoundingClientRect().top + window.scrollY - 8));
      });
      await page.waitForTimeout(300);
      await shoot('02-phone-overview', page);
    }

    await go(page, '#s/S-01/qualitative');
    await page.waitForSelector('#detail:not([hidden])');
    await page.waitForTimeout(400);
    if (wanted('03-phone-student-detail')) await shoot('03-phone-student-detail', page);

    if (wanted('04-phone-add-form')) {
      await page.click('#add-record');
      await page.waitForSelector('#add-form:not([hidden])');
      await page.waitForTimeout(400);
      await page.evaluate(() => {
        const f = document.getElementById('add-form');
        if (f) f.scrollIntoView({ block: 'start' });
      });
      await page.waitForTimeout(300);
      await shoot('04-phone-add-form', page);
    }

    // ── 05 分類詞按鈕特寫（在手機寬度下拍，會自己折成三排、看得清楚）──
    if (wanted('05-tag-chips')) {
      if (await page.$('#add-form[hidden]')) {
        await page.click('#add-record');
        await page.waitForSelector('#add-form:not([hidden])');
        await page.waitForTimeout(350);
      }
      const chips = await page.$('#tag-chips');
      if (chips) await shoot('05-tag-chips', chips);
    }
    await ctx.close();
  }
} finally {
  await browser.close();
}

const missing = SHOTS.filter(([n]) => wanted(n)).map(([n]) => n).filter(n => !done.includes(n));
console.log('\n── 完成：%d 張 → %s', done.length, OUT);
if (missing.length) console.log('   沒拍到：' + missing.join('、'));
if (!existsSync(OUT)) rmSync(OUT, { recursive: true, force: true });   // 不留空目錄
