# 嵌入現有網站 + 安全（「加密」）說明

如果你已經有自己的網站（班網、個人站…），可以把學生紀錄儀表板**嵌進去**，
而且**只有你登入時看得到入口**，對其他所有訪客都不存在。

## 先講清楚「加密 / 保護」是什麼

這套的保護**不是把檔案加密**，而是**伺服器端的存取控制（登入閘）**：

- 資料存在 Google Firestore，規則寫死「**只有擁有者本人**（你的 Google 帳號、已驗證）能讀寫」。
- 任何其他人——訪客、家長、同事、就算他拿到 `dashboard.html` 的網址、就算他看你網站的原始碼——**伺服器一律拒絕回傳資料**。
- 「在導覽列隱藏入口」只是**介面層的方便**（不讓別人看到那個連結），**不是**安全機制本身。真正的牆是 Firestore 規則。

換句話說：**入口藏不藏無所謂，資料本身別人就是讀不到。** 這比「把連結藏起來」可靠得多。

## 嵌入步驟

1. **先完成第 1、2 步**（Firebase 專案 + 部署 `firestore.rules`，見 `AGENTS.md` / `INSTALL.md`）。
2. 把這三個檔放進你網站可服務的位置（**三個都要**，缺一個網頁會停在「還沒有設定檔」）：
   - `site/dashboard.html` → 例如你網站的 `/records/dashboard.html`
   - `site/js/kit-config.js`（`scripts/build_config.py` 產生的那份，分頁與向度都在裡面）
   - `site/js/firebase-config.js`（同樣由 `build_config.py` 產生）
   後兩個都放在 dashboard.html 隔壁的 `js/` 底下（預設就是 `./js/kit-config.js`、`./js/firebase-config.js`）。

   > **v3 起載入方式改了**：這兩個設定檔不再是 ES module，而是普通的 `<script src>`，
   > 載完之後只是在頁面上放了 `window.KIT`、`window.FIREBASE_CONFIG`、`window.OWNER_EMAIL`。
   > Firebase SDK 本身改成在網頁裡用動態 `import()` 載——**只有非示範模式才會載**。
   > 這樣做的好處：`scripts/build_preview.py` 可以把整個儀表板壓成一個單檔 HTML，
   > 老師點兩下就能離線看示範版；壞處是設定檔如果你自己手寫，記得寫 `window.XXX = {...}`
   > 而不是 `export const`（v2 是 export，直接照抄會壞）。
3. **（選用）隱形入口**：在你網站每頁的導覽列引入 `site/js/dashboard-nav.js`。
   這一支**還是 ES module**（它自己 import Firebase），所以標籤要留 `type="module"`，
   而且它讀的是舊式的 `export const firebaseConfig`。若你的 `firebase-config.js` 是
   `build_config.py` 產生的 v3 版（`window.FIREBASE_CONFIG`），請在同一個檔案末尾補一行
   `export const firebaseConfig = window.FIREBASE_CONFIG, OWNER_EMAIL = window.OWNER_EMAIL;`
   ——兩種寫法可以並存，`dashboard.html` 只吃 `window.*`，導覽列那支只吃 `export`。
   ```html
   <script type="module" src="/records/js/dashboard-nav.js"
           data-nav-selector="nav ul"
           data-href="/records/dashboard.html"
           data-label="教學記錄"></script>
   ```
   - `data-nav-selector`：你導覽列 `<ul>` 的 CSS 選擇器。
   - 只有你（擁有者）登入時，它才會把「學生紀錄」這個 `<li>` 加進去；其他人完全看不到。
   - 它會重用你網站上已初始化的 Firebase（若有），不會重複初始化。
4. **若你的網站本來就有登入機制**：仍建議用上面的 Firebase Google 登入來「認誰是擁有者」，因為 Firestore 規則是看 Firebase 的登入身分。兩套登入可並存（你的站登你的、Firebase 登 Google）。

## 驗證

- 用**擁有者帳號**在你網站登入 → 出現「教學記錄」入口 → 點進去看得到三個分頁的資料。
- 用**別的帳號 / 無痕視窗** → 看不到入口；就算直接開 `dashboard.html` → 顯示「無權檢視」、讀不到任何資料。
- 打開瀏覽器主控台（Console）看有沒有 404：少了 `js/kit-config.js` 會停在「還沒有設定檔」，
  少了 `js/firebase-config.js` 則會停在「載入 Firebase 失敗」。
- 想確認網頁本身沒壞、又不想動到真資料：在網址後面加 `?demo=1`，
  它會完全不連 Firebase，只用瀏覽器裡的假資料跑一遍。

## 進一步鎖緊（選用）

- 在 Firebase Console → Authentication → Settings，限制允許登入的網域。
- 在 Firestore 規則裡，`owner_email` 只留你一個；要多人協作再逐一加（但這套預設是「單一擁有者」）。
