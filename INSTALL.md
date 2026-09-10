# 手動安裝（不用 AI 的話）

> 推薦做法還是把資料夾交給 AI 代理、讓它讀 `AGENTS.md` 帶你做——它會一次問一題，
> 每一題告訴你去哪裡拿答案。這份是同一套流程的**純指令版**，步驟編號與 `AGENTS.md` 一一對應。
> 每一步「為什麼要這樣做、怎麼驗證、失敗怎麼辦」都寫在 `AGENTS.md` 對應的那一步。

前置條件：macOS、一個能自己開 Firebase 專案的 Google 帳號、Homebrew（https://brew.sh ）。
Windows：`[[待確認：Windows 支援]]`。

---

## 0. 判斷你現在的狀態

```bash
cat VERSION
cat setup/progress.json 2>/dev/null || echo "沒有進度檔＝新裝"
ls config/kit.json config.yaml 2>/dev/null
```

- 什麼都沒有 → 從第 1 步開始
- 有 `setup/progress.json` → 從第一個 `"done": false` 的步驟接著做
- 有 `config.yaml`、沒有 `config/kit.json` → 你是 v2，跳到本檔最後的「從 v2 升級」

## 1. 裝工具

```bash
bash scripts/install_tools.sh --dry-run     # 先看會裝什麼
bash scripts/install_tools.sh               # 真的裝
bash scripts/install_tools.sh --with-gws    # 備份要走 gws 進階模式才加這個
python3 scripts/doctor.py                   # 健檢
```

## 2. Firebase 專案

在 https://console.firebase.google.com 用你的 Google 帳號完成四件事：

1. 建立專案（Analytics 可以關掉）
2. 建立 **Firestore Database**，模式選**正式版／Production**（不要選測試模式）
3. **Authentication** → Sign-in method → 啟用 **Google**
4. 專案設定（左上齒輪）→ 一般 → 你的應用程式 → 加**網頁應用程式** → SDK 設定與配置 → **Config**
   → 抄下六個值：`projectId`、`apiKey`、`authDomain`、`storageBucket`、`messagingSenderId`、`appId`

**iOS Safari 防坑**：打算用 Firebase Hosting 上線的話，`authDomain` 填 `<專案ID>.web.app`
（不要用 Console 預設的 `.firebaseapp.com`），否則 iPhone 上 Google 登入會一直失敗。

## 3. 想清楚三個分頁要記什麼

- 學生：班上幾位、代號前綴（預設 `S`）
- 課程：先建哪幾門（課名＋主課程或科任＋一個英數短名）
- 業務：從 `docs/BUSINESS-GROUPS.md` 那十一組挑；每組要不要加自己的欄位與分類詞；
  清單外的業務要準備四件事（組名、固定欄位、分類詞、要不要接學生／課程）

## 4. 產生設定與安全規則

```bash
python3 scripts/setup.py                                  # 互動安裝，一次問一題
# 或免互動：
cp templates/answers.example.json /tmp/answers.json       # 改成你自己的答案
python3 scripts/setup.py --answers /tmp/answers.json
```

其他旗標：`--resume`（續裝）、`--upgrade`（轉 v2 設定）、`--skip-network`、`--skip-doctor`、`--root`。

`setup.py` 會自動呼叫 `build_config.py`。手改過 `config/kit.json` 或 `config/tabs.json` 之後要單獨重跑：

```bash
python3 scripts/build_config.py            # 產生三個檔
python3 scripts/build_config.py --check    # 只驗設定，不寫檔
```

部署安全規則：

```bash
firebase login
firebase deploy --only firestore:rules --project <你的專案ID>
```

沒裝 CLI：`cat firestore.rules` 印出來，到 Console → Firestore Database → 規則 → 全選貼上 → 發布。

## 5. 上線

`firebase.json` 已經設好 hosting，**不用跑 `firebase init hosting`**：

```bash
firebase deploy --only hosting --project <你的專案ID>
```

網址是 `https://<專案ID>.web.app`。

備選：把 `site/` 丟到 GitHub Pages（`site/js/kit-config.js` 與 `site/js/firebase-config.js`
是 gitignored 的產生檔，走這條路要另外放上去，而且那個 repo 要設 private）。
嵌進現有網站：見 `embed/EMBED-AND-SECURITY.md`。

## 6. 名單與既有資料

`data/roster.csv`（格式看 `templates/roster.example.csv`；第一欄可以是座號或完整代號）：

```
編號,姓名
01,學生甲
02,學生乙
```

```bash
python3 scripts/sync.py --dry-run     # 先看會發生什麼
python3 scripts/sync.py               # 真跑
python3 scripts/sync.py --only students/S-03    # 只同步一個目標
```

匯入舊記錄一律走唯一寫入通道，**不要自己編輯 `data/` 底下的 md 檔**：

```bash
python3 scripts/append_record.py --kind students --target S-03 \
  --date 2026-09-01 --tags "#課堂 #學習態度" --content-file 一則.md --source file
```

`--kind` 四選一：`students` / `class` / `courses` / `business`。
其他旗標：`--time`、`--fields-json`、`--related`、`--task-id`、`--sync`、`--json`、`--allow-names`、`--root`。

## 7. 備份到你自己的 Google 雲端硬碟

**預設（desktop 模式）**：裝「Google 雲端硬碟」桌面程式（https://www.google.com/drive/download/ ）→ 登入
→ 在雲端硬碟裡建一個資料夾 → 把它在電腦上的路徑填進 `config/kit.json` 的 `drive.desktop_dir`
（通常是 `~/Library/CloudStorage/GoogleDrive-<你的信箱>/My Drive/<資料夾名>`）。

**進階（gws 模式）**：`drive.mode` 改 `gws`，`drive.backup_folder_id` 填資料夾 ID
（在瀏覽器打開那個資料夾，網址 `.../folders/XXXX` 的 `XXXX`）。需要用 `bash scripts/install_tools.sh --with-gws` 裝的 `googleworkspace-cli` 與你自己的 OAuth 憑證。

```bash
python3 scripts/build_config.py
python3 scripts/doctor.py
python3 scripts/backup.py                 # 真的備份一次
python3 scripts/backup.py --local-only    # 只做本機 zip
python3 scripts/backup.py --no-export     # 不抓資料庫快照（離線時）
```

驗證：打開 https://drive.google.com 看得到那個 zip。

## 8. 排程（選用）

```bash
bash scripts/schedule.sh --dry-run      # 先看
bash scripts/schedule.sh                # 每天 07:00 同步、每週日 08:00 備份
bash scripts/schedule.sh --print-cron   # 只印等效的 crontab 兩行
bash scripts/schedule.sh --uninstall    # 移除
```

排程會靜默失敗。**真正的驗證是隔天看網頁頂端「上次同步 X 天前」有沒有更新**，超過七天會變紅字。

## 9. 錄音

```bash
# 把錄音檔（m4a/mp3/wav/mp4/mov/aac/flac/ogg/m4v/caf）丟進 inbox/
python3 scripts/transcribe.py --inbox        # 第一次會下載約 1.6GB 的模型
python3 scripts/transcribe.py 會議.m4a       # 或指定單檔
```

逐字稿出現在 `inbox/transcripts/`，原始錄音移到 `inbox/done/`（`--keep` 可以不搬）。
其他旗標：`--lang`、`--model`、`--no-vad`、`--root`。

逐字稿讀完自己改寫（提到學生一律換成代號），再走 `append_record.py` 寫入，最後 `sync.py`。

## 10. 驗收

```bash
python3 scripts/ledger.py --rebuild
python3 scripts/ledger.py --check          # 退出碼 0 ＝ 三處對得上
python3 scripts/ledger.py --check --offline   # 不連網，只比本機與備份
python3 scripts/doctor.py
git status
```

手動要做的四件：①你的帳號登入看得到 ②別的帳號（無痕視窗）打開顯示「無權檢視」
③三個分頁各新增一則，重新整理還在 ④打開 Google 雲端硬碟看得到備份 zip。

`git status` 不該出現：`data/`、`config/kit.json`、`config/tabs.json`、`setup/progress.json`、
`site/js/kit-config.js`、`site/js/firebase-config.js`、`firestore.rules`、`inbox/`、`backups/`、`*-key.json`、`.env`。

---

## 從 v2 升級

1. `git pull`（或重新下載）。**只覆蓋** `scripts/`、`site/dashboard.html`、`site/js/*.example.js`、
   `templates/`、`config/*.example.json`、`firestore.rules.tmpl`、`firebase.json`、文件。
   **絕對不要覆蓋** `config/kit.json`、`config/tabs.json`、`data/`、`setup/progress.json`、
   `firestore.rules`、`site/js/kit-config.js`、`site/js/firebase-config.js`、`backups/`、`inbox/`。

2. ```bash
   python3 scripts/setup.py --upgrade
   ```
   把 `config.yaml` 的 `owner_email`、`firebase`、`email` 轉成 `config/kit.json`，並自動跑 `build_config.py`。
   業務記錄分頁預設關著，要開就照第 3 步問完再重跑一次 `python3 scripts/setup.py`。

3. **重新部署安全規則（不能省）**：
   ```bash
   firebase deploy --only firestore:rules --project <你的專案ID>
   ```

4. ```bash
   firebase deploy --only hosting --project <你的專案ID>
   python3 scripts/sync.py --dry-run
   python3 scripts/sync.py
   ```

---

## 日常指令速查

```bash
python3 scripts/sync.py                                   # 同步
python3 scripts/backup.py                                 # 備份
python3 scripts/ledger.py --check                         # 三處對帳
python3 scripts/doctor.py                                 # 健檢
python3 scripts/monthly_reminder.py --dry-run             # 本月未記名單（先看不寄）
python3 scripts/export_records.py --out ~/記錄.md          # 期末取材
python3 scripts/export_records.py --by-tag                # 依標籤分組
python3 scripts/export_records.py --split ~/備份           # 每個對象一個資料夾
python3 scripts/pending.py                                # 還沒決定要不要寄家長的
python3 scripts/parent_email.py --id S-01 --subject "…" --body-file msg.txt --dry-run
python3 scripts/build_preview.py                          # 產生單檔離線示範
```
