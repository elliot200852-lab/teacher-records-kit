/* 嵌入用：只有「擁有者」登入時，才在你現有網站的導覽列注入一個「學生紀錄」分頁；
   對其他所有人（含未登入訪客）都不存在。
   ⚠️ 這只是介面隱藏——真正的保護在 Firestore 規則（只有擁有者讀得到資料）。

   用法：在你網站的頁面引入本檔（type="module"），並確保導覽列有一個 <ul>。
   可用 data 屬性自訂：
     <script type="module" src="js/dashboard-nav.js"
             data-nav-selector="nav ul" data-href="dashboard.html" data-label="學生紀錄"></script>
*/
import { initializeApp, getApps, getApp } from "https://www.gstatic.com/firebasejs/10.13.0/firebase-app.js";
import { getAuth, onAuthStateChanged } from "https://www.gstatic.com/firebasejs/10.13.0/firebase-auth.js";
import { firebaseConfig, OWNER_EMAIL } from "./firebase-config.js";

const me = document.currentScript || document.querySelector('script[src$="dashboard-nav.js"]');
const NAV_SEL = me?.dataset.navSelector || "nav ul";
const HREF = me?.dataset.href || "dashboard.html";
const LABEL = me?.dataset.label || "學生紀錄";

const app = getApps().length ? getApp() : initializeApp(firebaseConfig);
const auth = getAuth(app);

function ownerEmail(u) {
  if (!u) return null;
  return u.email || u.providerData?.find(p => p.providerId === "google.com")?.email || null;
}

onAuthStateChanged(auth, (user) => {
  const ul = document.querySelector(NAV_SEL);
  if (!ul) return;
  let li = document.getElementById("nav-records");
  const isOwner = ownerEmail(user) === OWNER_EMAIL;
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
