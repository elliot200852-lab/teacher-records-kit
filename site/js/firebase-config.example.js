// 複製成 firebase-config.js 後填入你的 Firebase「網頁 App」設定。
// firebase-config.js 已被 .gitignore 擋住，不會進 git。
// 取得位置：Firebase Console → 專案設定（齒輪）→ 一般 → 你的應用程式 → SDK 設定與配置。

// ⚠️ iOS Safari 重要：authDomain 建議與「你實際打開這個頁面的網域」同源。
//   若你用 Firebase Hosting（<project>.web.app），把 authDomain 設成同一個 <project>.web.app，
//   可避開 iOS Safari 的跨網域儲存分區（storage partitioning）造成的登入失敗。
//   詳見 docs/REPORT.md 的 Troubleshooting。
export const firebaseConfig = {
  apiKey: "",
  authDomain: "YOUR_PROJECT.firebaseapp.com",   // iOS 上若登入壞掉，改成你的 hosting 網域（如 YOUR_PROJECT.web.app）
  projectId: "YOUR_PROJECT",
  storageBucket: "YOUR_PROJECT.firebasestorage.app",
  messagingSenderId: "",
  appId: ""
};

// 只有這個 Google 帳號會被視為擁有者（要與 firestore.rules 裡的一致）
export const OWNER_EMAIL = "you@example.com";
