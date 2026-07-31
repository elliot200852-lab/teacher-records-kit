// test_courses_view.mjs — 課程分頁的顯示邏輯迴歸測試。
// 不碰網路、不碰 Firebase：把 dashboard.html 裡的 module script 抽出來，
// 把 firebase 的 import 換成空殼、給一個極簡的假 document，再直接呼叫 renderCourses()。
//
//     node scripts/test_courses_view.mjs
//
// 守的是什麼：**學季（season）是選填的**。這個 kit 給任何學制、任何科目的老師用，
// 不預設四季主課程那一套。沒人填學季就該是一份平鋪清單，填了才分組，
// 混填時沒填的那些要有自己的桶——任何情況下都不准有課程無聲消失。

import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const html = fs.readFileSync(path.join(here, '..', 'site', 'dashboard.html'), 'utf8');

const STUB = `
const noop = () => {};
export const initializeApp = () => ({}), getApps = () => [], getApp = () => ({});
export const getAuth = () => ({});
export class GoogleAuthProvider { addScope(){} setCustomParameters(){} }
export const signInWithPopup = noop, signInWithRedirect = noop;
export const getRedirectResult = () => ({ catch: noop });
export const signOut = noop, onAuthStateChanged = noop;
export const getFirestore = () => ({}), doc = () => ({}), getDoc = noop, setDoc = noop;
export const collection = () => ({}), getDocs = noop, query = () => ({}), orderBy = () => ({});
export const limit = () => ({}), getCountFromServer = noop, updateDoc = noop;
export const serverTimestamp = () => 0;
export const firebaseConfig = {}, OWNER_EMAIL = 'owner@example.com';
`;

let js = html.match(/<script type="module">([\s\S]*?)<\/script>/)[1];
js = js.replace(/import \{[^}]*\}\s*\n?\s*from "https:\/\/www\.gstatic\.com[^"]*";/g, '')
       .replace('import { firebaseConfig, OWNER_EMAIL } from "./js/firebase-config.js";', '');
js = `import {initializeApp,getApps,getApp,getAuth,GoogleAuthProvider,signInWithPopup,
signInWithRedirect,getRedirectResult,signOut,onAuthStateChanged,getFirestore,doc,getDoc,
setDoc,collection,getDocs,query,orderBy,limit,getCountFromServer,updateDoc,serverTimestamp,
firebaseConfig,OWNER_EMAIL} from './stub.mjs';\n` + js
   + '\nexport { renderCourses, courseIdFor, courses };\n';

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'trk-test-'));
fs.writeFileSync(path.join(tmp, 'stub.mjs'), STUB);
fs.writeFileSync(path.join(tmp, 'dash.mjs'), js);

// ── 極簡假 DOM：只夠 renderCourses 跑（建元素、塞 children、讀 innerHTML）──
Object.defineProperty(globalThis, 'navigator', { value: { userAgent: 'node' }, configurable: true });
globalThis.location = { href: 'https://x/', origin: 'https://x', pathname: '/', search: '' };
globalThis.window = { addEventListener() {} };
const mk = () => ({
  children: [], classList: { toggle() {}, add() {} }, style: {}, dataset: {},
  set innerHTML(v) { this._h = v; }, get innerHTML() { return this._h || ''; },
  appendChild(c) { this.children.push(c); }, insertBefore(c) { this.children.unshift(c); },
  addEventListener() {}, querySelector() { return mk(); }, focus() {},
  value: '', textContent: '', hidden: false,
});
const reg = new Map();
globalThis.document = {
  getElementById: id => { if (!reg.has(id)) reg.set(id, mk()); return reg.get(id); },
  createElement: () => mk(),
};

const m = await import(path.join(tmp, 'dash.mjs'));
const sect = document.getElementById('course-sections');

let fails = 0;
const ok = (cond, msg) => { console.log((cond ? '  ✓ ' : '  ✗ ') + msg); if (!cond) fails++; };
function render(list) {
  m.courses.length = 0; list.forEach(c => m.courses.push(c));
  sect.children.length = 0; sect.innerHTML = '';
  m.renderCourses();
  return {
    heads: sect.children.filter(c => c.textContent).map(c => c.textContent),
    cards: sect.children.filter(c => !c.textContent).reduce((n, g) => n + g.children.length, 0),
  };
}
const C = (id, o = {}) => ({ id, title: id, kind: 'main', order: 1, recordCount: 0, ...o });

console.log('課程分組（學季選填）');
let r = render([C('分數'), C('地方探究', { order: 2 }), C('音樂', { kind: 'subject', order: 3 })]);
ok(r.heads.length === 2 && !r.heads.some(x => x.includes('學季')), '沒人填學季 → 平鋪，不出現學季小標');
ok(r.cards === 3, '三張卡都在');

r = render([C('秋-分數', { season: '秋' }), C('春-分數', { season: '春', order: 2 }),
            C('音樂', { kind: 'subject', order: 3 })]);
ok(r.heads.includes('秋') && r.heads.includes('春'), '有人填學季 → 按學季分組');
ok(r.heads.indexOf('秋') < r.heads.indexOf('春'), '學季照 order 排');
ok(r.cards === 3, '三張卡都在');

r = render([C('秋-分數', { season: '秋' }), C('寫作', { order: 2 })]);
ok(r.heads.includes('（未指定學季）'), '混填 → 沒填的有自己的桶');
ok(r.cards === 2, '沒有課程消失');

r = render([C('x', { kind: 'weird' })]);
ok(r.heads.includes('【其他】') && r.cards === 1, '未知 kind 落到【其他】、不無聲消失');

render([]);
ok(sect.innerHTML.includes('還沒有課程'), '空狀態文案');

console.log('課程 id');
for (const [t, s, want] of [['分數', '秋', '秋-分數'], ['音樂', '', '音樂'],
                            ['a/b', '', 'a-b'], ['  空白  ', '', '空白']]) {
  ok(m.courseIdFor(t, s) === want, `courseIdFor(${JSON.stringify(t)}, ${JSON.stringify(s)}) → ${JSON.stringify(want)}`);
}

fs.rmSync(tmp, { recursive: true, force: true });
console.log(fails ? `\n✗ ${fails} 項失敗` : '\n全部通過。');
process.exit(fails ? 1 : 0);
