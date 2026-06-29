// 複製成 firebase-config.js 後填入你的 Firebase「網頁 App」設定。
// firebase-config.js 已被 .gitignore 擋住，不會進 git。
// 取得位置：Firebase Console → 專案設定（齒輪）→ 一般 → 你的應用程式 → SDK 設定與配置。

export const firebaseConfig = {
  apiKey: "",
  authDomain: "YOUR_PROJECT.firebaseapp.com",
  projectId: "YOUR_PROJECT",
  storageBucket: "YOUR_PROJECT.firebasestorage.app",
  messagingSenderId: "",
  appId: ""
};

// 只有這個 Google 帳號會被視為擁有者（要與 firestore.rules 裡的一致）
export const OWNER_EMAIL = "you@example.com";
