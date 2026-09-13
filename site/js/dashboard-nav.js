/* 嵌入用：只有「擁有者」登入時，才在你現有網站的導覽列注入一個「學生紀錄」分頁；
   對其他所有人（含未登入訪客）都不存在。
   ⚠️ 這只是介面隱藏——真正的保護在 Firestore 規則（只有擁有者讀得到資料）。

   用法：在你網站的頁面裡，**先**載入 build_config.py 產生的設定，**再**載入本檔：
     <script src="js/firebase-config.js"></script>
     <script type="module" src="js/dashboard-nav.js"
             data-nav-selector="nav ul" data-href="dashboard.html" data-label="學生紀錄"></script>

   v3 起本檔讀的是 window.FIREBASE_CONFIG / window.OWNER_EMAIL（＝build_config.py 真正寫出來的東西），
   不再 import { firebaseConfig, OWNER_EMAIL }——那是 v2 的寫法，v3 的設定檔沒有 export，
   照舊寫法會整支 module 掛掉（而且是靜默的：導覽列上什麼都不會出現）。
*/
import { initializeApp, getApps, getApp } from "https://www.gstatic.com/firebasejs/10.13.0/firebase-app.js";
import { getAuth, onAuthStateChanged } from "https://www.gstatic.com/firebasejs/10.13.0/firebase-auth.js";

const me = document.currentScript || document.querySelector('script[src$="dashboard-nav.js"]');
const NAV_SEL = me?.dataset.navSelector || "nav ul";
const HREF = me?.dataset.href || "dashboard.html";
const LABEL = me?.dataset.label || "學生紀錄";

const lc = (s) => String(s ?? "").trim().toLowerCase();

function ownerEmail(u) {
  if (!u) return null;
  return u.email || u.providerData?.find(p => p.providerId === "google.com")?.email || null;
}

function start() {
  const cfg = window.FIREBASE_CONFIG;
  const owners = (window.OWNER_EMAILS || [window.OWNER_EMAIL]).map(lc).filter(Boolean);
  if (!cfg || !cfg.projectId || !owners.length) {
    // module 是 defer 的，正常情況設定早就載好了；真的沒有就安靜收手，
    // 只在主控台留一句——別把別人網站的導覽列弄壞。
    console.warn("[dashboard-nav] 找不到 window.FIREBASE_CONFIG / window.OWNER_EMAIL，" +
      "請確認 js/firebase-config.js（build_config.py 產生的那份）在本檔之前載入。");
    return;
  }
  const app = getApps().length ? getApp() : initializeApp(cfg);
  const auth = getAuth(app);

  onAuthStateChanged(auth, (user) => {
    const ul = document.querySelector(NAV_SEL);
    if (!ul) return;
    let li = document.getElementById("nav-records");
    const isOwner = owners.includes(lc(ownerEmail(user)));   // 信箱大小寫不敏感；含 co_owner_emails
    if (isOwner) {
      if (!li) {
        li = document.createElement("li");
        li.id = "nav-records";
        const a = document.createElement("a");
        a.href = HREF; a.textContent = LABEL;
        li.appendChild(a); ul.appendChild(li);
      }
      li.hidden = false;
    } else if (li) {
      li.hidden = true;
    }
  });
}

// 設定檔萬一被放在本檔之後（或用 async 載），再給它一次機會。
if (window.FIREBASE_CONFIG || document.readyState === "complete") start();
else window.addEventListener("load", start, { once: true });
