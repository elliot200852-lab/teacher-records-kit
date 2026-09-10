/* ══════════════════════════════════════════════════════════════════════
   firebase-config.example.js — Firebase 設定範本
   ──────────────────────────────────────────────────────────────────────
   複製成 firebase-config.js 後填入你的 Firebase「網頁 App」設定
   （或直接跑 scripts/build_config.py，它會從 config/kit.json 產生這個檔）。
   firebase-config.js 已被 .gitignore 擋住，不會進 git。

   取得位置：Firebase Console → 專案設定（齒輪）→ 一般 → 你的應用程式
            → SDK 設定與配置。

   ⚠️ v3 起本檔**不是 module**：dashboard.html 用傳統 <script src> 載入它，
      Firebase SDK 本身才用動態 import() 載（這樣示範模式與離線預覽
      不必連網、file:// 也開得起來）。所以這裡用 window.XXX，不要寫 export。

   ⚠️ iOS Safari 重要：authDomain 建議與「你實際打開這個頁面的網域」同源。
      若你用 Firebase Hosting（<project>.web.app），把 authDomain 設成同一個
      <project>.web.app，可避開 iOS Safari 的跨網域儲存分區造成的登入失敗。
   ══════════════════════════════════════════════════════════════════════ */

window.FIREBASE_CONFIG = {
  apiKey: "",
  authDomain: "YOUR_PROJECT.firebaseapp.com",   // iOS 上若登入壞掉，改成你的 hosting 網域（如 YOUR_PROJECT.web.app）
  projectId: "YOUR_PROJECT",
  storageBucket: "YOUR_PROJECT.firebasestorage.app",
  messagingSenderId: "",
  appId: ""
};

// 只有這個 Google 帳號會被視為擁有者（要與 firestore.rules 及 kit-config.js 的 ownerEmail 一致）
window.OWNER_EMAIL = "you@example.com";
