# AGENTS.md — AI 安裝大腦

你（AI 代理）正在幫一位老師把 **Teacher Records Kit** 裝起來。目標：讓這位老師擁有一個
**只有他本人看得到**的學生紀錄儀表板，每月方便記錄、檢視、編輯每位學生的觀察，並（選用）
把某則寄給家長。

## 鐵則（先讀）

1. **一步一步、每步先問再做。** 不要一次問完，也不要替老師假設答案。每個步驟：①問清楚需要的資料 → ②做 → ③驗證 → ④告訴他結果與下一步。
2. **隱私第一。** 老師的真實資料（學生紀錄、名冊、家長 email）一律放 `data/`、設定放 `config.yaml`、金鑰放 `.env` 或 `*-key.json`——**這些都已被 `.gitignore` 擋住，絕不可 commit / push 到這個 public repo**。動 git 前先確認沒帶到它們。
3. **去識別化。** 紀錄內容一律用代號（如 `S-01`），不寫真名。真名只存在本機名冊 `data/roster.csv`（gitignored）。
4. **副作用前先說明。** 部署、寄信、commit 等動作前先講你要做什麼、讓老師確認。

## 第 0 步：確認範圍

問老師要哪一種：
- **核心（最簡單，多數人夠用）**：純網頁儀表板（新增/編輯/檢視，只有他看得到）。只需要一個 Firebase 專案，不用裝任何命令列工具。→ 做第 1、2、3、4 步。
- **進階（選用）**：再加「本機 markdown 檔同步」「寄家長信」「每月提醒」。需要 `firebase` CLI、`gcloud`（或服務帳號）、Gmail App Password。→ 核心做完再做第 5 步。

也問他：**這個儀表板要獨立成一個網站，還是嵌進他現有的網站？**（影響第 3 步。）

## 第 1 步：Firebase（資料庫 + 登入）

1. 問老師的**擁有者 Google email**（之後只有這個帳號能讀寫）。
2. 引導他到 [Firebase Console](https://console.firebase.google.com)：建立專案（或用現有的）→ 建立 **Firestore Database**（正式模式）→ 在 **Authentication** 啟用 **Google** 登入。
3. 在專案設定加一個**網頁 App**，取得 web config（apiKey 等）。
   - ⚠️ **iOS Safari 防坑**：若老師會用 Firebase Hosting 上線（第 3 步 A 的變體 / `<project>.web.app`），建議把 `authDomain` 設成**與 hosting 同源**的網域（如 `<project>.web.app`）。否則 iOS Safari 的跨網域儲存分區會讓 Google 登入壞掉。見 `docs/REPORT.md` Troubleshooting。
4. 把資料寫進兩個檔（都 gitignored）：
   - `cp config.example.yaml config.yaml`，填 `owner_email`、`firebase.*`。
   - `cp site/js/firebase-config.example.js site/js/firebase-config.js`，貼上 web config + `OWNER_EMAIL`。
5. 驗證：`firebaseConfig.projectId` 與 `OWNER_EMAIL` 都已填、與 config.yaml 一致。

## 第 2 步：安全規則（只有他看得到）

1. 讀 `firestore.rules.tmpl`，把 `{{OWNER_EMAIL}}` 換成老師的 email，存成 `firestore.rules`。
2. 部署（需 `firebase` CLI；`npm i -g firebase-tools` + `firebase login`）：
   ```
   firebase deploy --only firestore:rules,firestore:indexes --project <PROJECT_ID>
   ```
   （沒裝 CLI 也可在 Firebase Console → Firestore → 規則 貼上 `firestore.rules` 內容後發布。）
3. 驗證：規則裡的 email 與 `OWNER_EMAIL` 相同；非擁有者讀取會被拒。

## 第 3 步：上線

**A. 獨立網站（GitHub Pages）**
- 把 `site/` 推到一個 repo，開 GitHub Pages 指向它，打開 `dashboard.html`。
- 用擁有者帳號 Google 登入 → 應看到空的儀表板；換別的帳號 → 顯示「無權檢視」。

**B. 嵌進現有網站** → 改讀 `embed/EMBED-AND-SECURITY.md`，照那份做（放 `dashboard.html` + `firebase-config.js`，並用 `dashboard-nav.js` 注入「只有你看得到」的入口）。

## 第 4 步：學生資料

1. 問老師：**已經有學生觀察紀錄了嗎？放在哪？**
   - 有 → 確認格式（每位學生一個 `## YYYY-MM-DD #tag` 區塊）；協助匯入 Firestore（進階才需腳本，否則他可直接在網頁新增）。
   - 沒有 → 幫他建立：
     - 問班級人數、要用什麼代號（預設 `S-01`、`S-02`…）。
     - 建 `data/roster.csv`（代號,姓名；參考 `templates/roster.example.csv`）——**這檔含真名、gitignored**。
     - 為每位學生建 `data/students/<代號>/observations.md`（參考 `templates/observation.example.md`）。
2. **提醒老師哪些還沒做**：列出目前沒有任何紀錄的學生，建議先從幾位開始。
3. 告訴他：之後要記錄，可直接在**網頁儀表板**點學生「＋新增」，或（進階）寫進本機 `observations.md` 再同步。
4. 順帶告訴他兩個好用功能：
   - **題材分類快速鍵**：新增紀錄時，內容框上方有一排 `#標籤` 按鈕，點一下即加入（可改成適合他科目的分類——在 `site/dashboard.html` 的 `CATEGORIES` 陣列）。
   - **全班觀察紀錄**：全班一覽頁右上「📋 全班觀察紀錄」記錄不針對單一學生的整班層次觀察，資料模型與學生紀錄相同。

## 第 5 步（選用·進階）：本機同步 + 寄家長 + 提醒

只有老師選了「進階」才做。先 `cp config.example.yaml config.yaml` 填好 `records` / `parents` / `email` 區塊。

- **本機 ↔ Firestore 雙向同步**：`python3 scripts/sync.py`（需 `gcloud` 以擁有者身分登入：`gcloud auth login`）。把 `observations.md` 鏡像到 Firestore，並把網頁的新增/編輯寫回檔案（衝突不覆蓋）。可用 launchd/cron 每日跑。
- **寄家長信**：問家長 email 來源 → 填 `data/contacts.csv`（參考 `templates/contacts.example.csv`）+ 設定 `email`（SMTP App Password 放環境變數 `KIT_SMTP_APP_PASSWORD` 或 `.env`）。寄信用 `python3 scripts/parent_email.py --id S-01 --date <日期> --subject ... --body-file ...`；**一律先把改寫稿給老師看、確認才寄**。
- **待寄提醒**：`python3 scripts/pending.py` 列出有觀察但還沒處理寄家長的紀錄；老師說不用就 `python3 scripts/pending.py --mark <代號> <日期> skip`。
- **每月提醒**：`python3 scripts/monthly_reminder.py` 把本月未記名單寄給老師。
- **期末匯出取材**：`python3 scripts/export_records.py`（讀 `config.yaml` 的 `firebase.project_id`，需 `gcloud auth login`）。把全班歷次觀察＋全班觀察匯出成 Markdown，供撰寫期末評量。常用旗標：`--out FILE` 寫檔、`--json` 結構化、`--by-tag` 依題材分組、`--id S-01` 只抓一位、`--split DIR` 逐生備份（含 `roster.md`）。這是「拿資料去寫評量」，唯讀不會動到雲端資料。

## 完成檢查

- [ ] 擁有者登入看得到儀表板；別的帳號被拒。
- [ ] `config.yaml` / `firebase-config.js` / `data/` / 金鑰都沒被 commit（`git status` 確認）。
- [ ] 紀錄內容無真名（真名只在 `data/roster.csv`）。
- [ ] 告訴老師日常怎麼用、（進階）怎麼觸發寄家長。
