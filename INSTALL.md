# 手動安裝（不想用 AI 的話）

> 推薦做法是把 repo 交給 AI 代理、讓它讀 `AGENTS.md` 帶你做。以下是手動步驟。

## 核心（純網頁儀表板）

1. **Firebase**
   - [Firebase Console](https://console.firebase.google.com) → 建專案 → 建 **Firestore Database**（正式模式）→ **Authentication** 啟用 **Google**。
   - 專案設定 → 新增**網頁 App** → 複製 web config。
2. **填設定**
   - `cp config.example.yaml config.yaml`，填 `owner_email`、`firebase.*`。
   - `cp site/js/firebase-config.example.js site/js/firebase-config.js`，貼上 web config，設好 `OWNER_EMAIL`。
3. **部署規則**
   - 把 `firestore.rules.tmpl` 的 `{{OWNER_EMAIL}}` 換成你的 email → 存成 `firestore.rules`。
   - `npm i -g firebase-tools && firebase login`
   - `firebase deploy --only firestore:rules,firestore:indexes --project <PROJECT_ID>`
   - （或在 Console → Firestore → 規則 貼上發布。）
4. **上線**
   - 獨立站：把 `site/` 丟到 GitHub Pages（或任何靜態主機），開 `dashboard.html`。
   - 或嵌入現有站：見 `embed/EMBED-AND-SECURITY.md`。
5. **驗證**：擁有者登入看得到、別人看不到。開始在網頁點學生「＋新增」記錄。

## 進階（本機同步 / 寄家長 / 提醒）—— 選用

需要 `python3`、`gcloud`（以專案擁有者 `gcloud auth login`）、（寄信）Gmail 應用程式密碼。

1. 填 `config.yaml` 的 `records` / `parents` / `email` 區塊。
2. 學生資料：每位一個 `data/students/<代號>/observations.md`（參考 `templates/observation.example.md`）；名冊 `data/roster.csv`、家長 `data/contacts.csv`（參考 templates）。**都在 `data/`、gitignored。**
3. 設 SMTP 密碼：`export KIT_SMTP_APP_PASSWORD='你的應用程式密碼'`（或寫進 gitignored 的 `.env`）。
4. 指令：
   - 同步：`python3 scripts/sync.py`（`--dry-run` 先看）
   - 待寄清單：`python3 scripts/pending.py`
   - 寄家長：`python3 scripts/parent_email.py --id S-01 --date 2026-09-15 --subject "..." --body-file msg.txt`（先 `--dry-run`）
   - 每月提醒：`python3 scripts/monthly_reminder.py --dry-run`
5. 排程（每日同步 / 每月提醒）：用 cron 或 macOS launchd 定時跑上面指令。

## 隱私檢查（重要）

`git status` 確認 **沒有** 帶到：`config.yaml`、`site/js/firebase-config.js`、`data/`、任何 `*-key.json`、`.env`、`.parent-emails-handled.tsv`。這些都應被 `.gitignore` 擋住。
