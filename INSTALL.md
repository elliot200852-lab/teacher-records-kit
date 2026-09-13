# 手動安裝（不用 AI 的話）

> 推薦做法還是把資料夾交給 AI 代理、讓它讀 `AGENTS.md` 帶你做——它會一次問一題，
> 每一題告訴你去哪裡拿答案。這份是同一套流程的**純指令版**，步驟編號與 `AGENTS.md` 一一對應。
> 每一步「為什麼要這樣做、怎麼驗證、失敗怎麼辦」都寫在 `AGENTS.md` 對應的那一步。

前置條件：macOS 或 Windows 10／11（Linux 盡力支援，WSL 不行）、一個能自己開 Firebase 專案的
Google 帳號、套件管理程式（macOS＝Homebrew，https://brew.sh ；Windows＝系統內建的 winget）。
**什麼都還沒裝的電腦**（連 Python、git、AI 代理都沒有）先跑第 1 步的 `setup/bootstrap.sh`
（Windows 按兩下 `setup\bootstrap.cmd`），它會把這些地基連同 Homebrew 一起裝好。
支援等級與每個平台的坑見 `docs/PLATFORMS.md`。

> **Windows**：這份文件裡的 `python3` 一律換成 `py -3`（或 `python`），路徑的 `/` 換成 `\`；
> 細節見 `docs/PLATFORMS.md`。

## v3.0.0-alpha.5 新增（`CHANGELOG.md` 是正本，這裡只列一行一項）

- **共同擁有者 `co_owner_emails`**：`config/kit.json` 多一個信箱清單，裡面的帳號跟 `owner_email` 權限完全一樣；`setup.py --answers` 可以帶，安裝精靈本身不問這一題。
- **匯出 Markdown（.md，給 AI）**：明細頁「匯出 ▾」、全班面板、課程一覽都多一項／一顆按鈕；正文代號、真名只在檔尾附錄。
- **整體課程紀錄**：每門課多一段不分天的總說明（`courses/{id}.overview`），本機也有對應檔 `data/courses/<id>/card.json`，雙向同步。
- **兩段式刪除（規則有動）**：網頁上刪除是軟刪，規則的 `delete` 一律拒絕；真刪只有老師本人在終端機跑 `scripts/purge_deleted.py --confirm` 才做得到。

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

電腦上**還沒有 Python／git／Node.js**（或還沒有 AI 代理的 CLI）的話，先跑一次 bootstrap，
它會把這些地基裝好，最後自己接著跑下面這幾行：

```bash
bash setup/bootstrap.sh                 # macOS／Linux；--dry-run 只看不裝、--agent claude 指定代理
```

```powershell
# Windows：對 setup\bootstrap.cmd 按兩下，或
powershell -NoProfile -ExecutionPolicy Bypass -File setup\bootstrap.ps1 -Agent claude
```

已經有 Python 的話直接從這裡開始（bootstrap 跑過了就不用再跑一次）：

```bash
python3 scripts/install_tools.py --dry-run     # 先看會裝什麼
python3 scripts/install_tools.py               # 真的裝
python3 scripts/install_tools.py --with-gws    # 備份要走 gws 進階模式才加這個
python3 scripts/install_tools.py --agent claude # 順便裝 AI 代理的 CLI（claude／codex／gemini）
python3 scripts/install_tools.py --json        # 要機器讀的輸出
python3 scripts/doctor.py                      # 健檢（裝完工具先重開終端機）
```

## 2. 先決定：雲端，還是只放這台電腦

安裝精靈（第 4 步）的第一題就是這個，決定後面要不要做第 2、4（部署）、5 步。

| | **雲端（cloud，預設）** | **只放這台電腦（local）** |
|---|---|---|
| 要申請什麼 | 一個你自己的 Firebase 專案（免費），填六個設定值 | 什麼都不用 |
| 手機上記一則 | ✔ 有一頁網頁 | ✘ 沒有網頁（回電腦上跟 AI 說） |
| 電腦 ⇄ 手機同步 | ✔ | ✘（沒有第二個地方要同步） |
| 備份到雲端硬碟 | ✔ | ✔ |
| 匯出 Word／PDF、期末素材包、家長信、錄音轉逐字稿 | ✔ | ✔ |
| 無頭交辦（第 11 步） | ✔ | ✘ |
| 帳單 | 你的（一般用量在免費額度內） | 沒有 |

答案寫進 `config/kit.json` 的 `mode`（答案檔同名鍵）。**哪天要換就改那個值重跑一次第 4 步**，
既有紀錄一則都不會動（改成 cloud 的話第一次同步會把它們全部推上去）。

**選 local 的人**：跳過這一步剩下的全部與第 5 步，第 4 步只跑 `setup.py` 與 `build_config.py`
（本機模式根本不產生 `firestore.rules`，所以沒有東西要部署）；
`setup.py` 會自動把第 2、4、5 步標成「本機模式，略過」。第 10 步的驗收改成在本機做
（`append_record.py` 各記一則、`export_docs.py` 匯出一次、`ledger.py --check` 自動只比兩處）。

**選 cloud 的人**，往下：

在 https://console.firebase.google.com 用你的 Google 帳號完成四件事：

1. 建立專案（Analytics 可以關掉）
2. 建立 **Firestore Database**，模式選**正式版／Production**（不要選測試模式）
3. **Authentication** → Sign-in method → 啟用 **Google**
4. 專案設定（左上齒輪）→ 一般 → 你的應用程式 → 加**網頁應用程式** → SDK 設定與配置 → **Config**
   → 抄下六個值：`projectId`、`apiKey`、`authDomain`、`storageBucket`、`messagingSenderId`、`appId`

**iOS Safari 防坑**：`authDomain` 這一格**留空就好**——`build_config.py` 會自動填
`<專案ID>.web.app`，那正是 Firebase Hosting 的網址。Console 給的預設值是
`<專案ID>.firebaseapp.com`，跟網頁不同源，iPhone 上 Google 登入會一直失敗。
網站要掛在別的網域（GitHub Pages、嵌進現有站）才填你實際打開網頁的那個網域。

## 3. 想清楚三個分頁要記什麼

**三個分頁都要自己決定要不要，清單裡的東西一個都不會預先幫你勾**——
`setup.py` 把清單列出來讓你選，你選了什麼才有什麼。

- **先選方案（選填）**：`setup.py` 第一句問「你最像哪一種？」，
  三個垂直方案在 `config/verticals.json`：
  `qualitative-assessment`（實驗教育／私校老師：質性評量自動化）、
  `iep-tracking`（特教／早療：IEP 目標追蹤）、
  `soap-casework`（諮商／教練／社工：SOAP 個案紀錄）。
  它只會**唸出**那個方案建議的類型、業務組與期末格式，**一項都不預先勾**；
  答案檔的鍵是 `vertical`，都不是就填 `"none"` 或整個鍵拿掉。
- **學生**：要不要這個分頁、班上幾位、代號前綴（預設值 `S`）；
  再從 `config/student-streams.library.json` 的記錄類型挑：
  `qualitative` 質性評量觀察（不打分數）／`homeroom` 導師班級學生紀錄／
  `subject` 任課老師學生紀錄／`case` 個案追蹤（通用）／`iep` IEP／早療目標追蹤／
  `soap` 會談紀錄（SOAP，舊 id `counseling` 相容）。每種可以加自己的欄位與分類詞；
  清單外的自己開一種要準備四件事（類型名稱、固定欄位、分類詞、
  是全班每一位還是只有你列入的學生）。
  `case`／`iep`／`soap` 這種「只有列入的學生」的類型，還要想好先列入誰。
  勾了 `iep` 要先備好該生的目標（領域／學年目標／學期目標／評量方式／評量標準／期程），
  勾了 `soap` 要備好個案概念化五格（主訴／背景／評估假設／處遇目標／結案標準）——
  兩者都寫進學生卡 `data/students/<代號>/card.json`（範本 `templates/card.example.json`，
  答案檔寫在 `students.cards.<代號>`），先空著也可以。
  人讀版說明在 `docs/DATA-CHECKLIST.md`。
- **課程**：要不要這個分頁、先建哪幾門（課名＋主課程或科任＋一個英數短名）
- **業務**：要不要這個分頁、從 `docs/BUSINESS-GROUPS.md` 那十一組挑；每組要不要加自己的欄位與分類詞；
  清單外的業務要準備四件事（組名、固定欄位、分類詞、要不要接學生／課程）

## 4. 產生設定與安全規則

```bash
python3 scripts/setup.py                                  # 互動安裝，一次問一題
# 或免互動：
cp templates/answers.example.json /tmp/answers.json       # 改成你自己的答案
python3 scripts/setup.py --answers /tmp/answers.json
# Windows（PowerShell）：
#   Copy-Item templates\answers.example.json $env:TEMP\answers.json
#   py -3 scripts\setup.py --answers $env:TEMP\answers.json
```

答案檔裡有你的信箱與專案 ID，**裝完就刪掉**（`rm /tmp/answers.json`；Windows `Remove-Item $env:TEMP\answers.json`）。
文件裡其他 `/tmp/…` 的檔在 Windows 上一律換成 `$env:TEMP\…`（對照表在 `docs/PLATFORMS.md`）。

其他旗標：`--resume`（續裝）、`--upgrade`（轉 v2 設定）、`--skip-network`、`--skip-doctor`、
`--root`、`--mark-step N`（＋選填的 `--note 文字`）。

`setup.py` 會自動呼叫 `build_config.py`。手改過 `config/kit.json` 或 `config/tabs.json` 之後要單獨重跑：

```bash
python3 scripts/build_config.py            # 產生三個檔
python3 scripts/build_config.py --check    # 只驗設定，不寫檔
```

**部署安全規則是你自己要做的一步——`setup.py` 不會部署**，
所以它跑完不會把第 4 步標成完成，只在 `setup/progress.json` 留一行「設定已產生，規則尚未部署」：

```bash
firebase login
firebase deploy --only firestore:rules --project <你的專案ID>
```

沒裝 CLI：`cat firestore.rules` 印出來，到 Console → Firestore Database → 規則 → 全選貼上 → 發布。

**部署成功之後**（兩條路都一樣）把第 4 步標起來，續裝時才不會又跑一次：

```bash
python3 scripts/setup.py --mark-step 4 --note "已部署規則"
```

`--mark-step` 只動 `setup/progress.json`，不碰其他任何檔案。步驟編號跟這份檔一致（0–11，
第 11 步「無頭交辦」是選用的，不裝就不用標）。

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

`data/roster.csv`，**三欄**（格式看 `templates/roster.example.csv`；第一欄可以是座號或完整代號）：

```
代號,姓名,類型
01,學生甲,
02,學生乙,case
03,學生丙,case;iep
```

第三欄＝這位學生列入哪幾種「只有列入的學生」的記錄類型（`case`／`iep`／`soap`
或你自訂的 case 型），分號分隔，沒有就留空。全班型的類型（`qualitative`、`homeroom`、`subject`）不用寫。
這一欄是**雙向**的：網頁上「＋ 列入學生」／「移出」的結果，下一次同步會寫回這裡；
兩邊都改過就當衝突處理，不覆蓋任何一邊。

```bash
python3 scripts/sync.py --dry-run     # 先看會發生什麼
python3 scripts/sync.py               # 真跑
python3 scripts/sync.py --only students/S-03    # 只同步一個目標
```

匯入舊記錄一律走唯一寫入通道，**不要自己編輯 `data/` 底下的 md 檔**：

```bash
python3 scripts/append_record.py --kind students --target S-03 --stream homeroom \
  --date 2026-09-01 --tags "#課堂 #學習態度" --content-file 一則.md --source file
```

`--kind` 四選一：`students` / `class` / `courses` / `business`。
**`--kind students` 一定要帶 `--stream <記錄類型>`**（`qualitative`／`homeroom`／`subject`／
`case`／`iep`／`soap`／你自訂的短名）——一位學生每一種類型各一個檔，不講是哪一種就不知道要寫哪裡；
漏帶會以退出碼 2 拒寫，並把可用的類型列出來。`--kind class` 也吃 `--stream`
（只收全班型的類型；剛好只有一種時可以不帶），`courses` 與 `business` 不能帶。

其他旗標：`--time`、`--fields-json`、`--related`、`--task-id`、`--sync`、`--json`、`--allow-names`、`--root`。

## 7. 備份到你自己的 Google 雲端硬碟

**預設（desktop 模式）**：裝「Google 雲端硬碟」桌面程式（https://www.google.com/drive/download/ ）→ 登入
→ 在雲端硬碟裡建一個資料夾 → 把它在電腦上的路徑填進 `config/kit.json` 的 `drive.desktop_dir`
（macOS 通常是 `~/Library/CloudStorage/GoogleDrive-<你的信箱>/My Drive/<資料夾名>`；
Windows 通常是 `G:\My Drive\<資料夾名>`，根目錄也可能叫 `我的雲端硬碟`）。
`setup.py` 會自動偵測這台電腦上的候選路徑當預設值，`doctor.py` 找不到設定的路徑時也會列出候選。

**進階（gws 模式）**：`drive.mode` 改 `gws`，`drive.backup_folder_id` 填資料夾 ID
（在瀏覽器打開那個資料夾，網址 `.../folders/XXXX` 的 `XXXX`）。需要用 `python3 scripts/install_tools.py --with-gws` 裝的 `@googleworkspace/cli`（三個平台都走
`npm i -g @googleworkspace/cli`）與你自己的 OAuth 憑證。

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
python3 scripts/schedule.py --dry-run                   # 先看
python3 scripts/schedule.py                             # 每天 07:00 同步、每週日 08:00 備份
                                                        #（本機模式不掛同步；開了無頭交辦會多一個每 5 分鐘的）
python3 scripts/schedule.py --sync-time 08:30           # 換同步時間
python3 scripts/schedule.py --backup-day 6 --backup-time 21:00   # 換備份的星期與時間（0＝週日）
python3 scripts/schedule.py --status                    # 現在掛了什麼
python3 scripts/schedule.py --print-cron                # 只印等效的 crontab
python3 scripts/schedule.py --uninstall                 # 移除
```

三個平台各自的排程機制（launchd／工作排程器／crontab）見 `docs/PLATFORMS.md`；
Windows 跑的時候會閃一下黑色視窗，正常。
排程會靜默失敗。**真正的驗證是隔天看網頁頂端「上次同步 X 天前」有沒有更新**，超過七天會變紅字。

## 9. 錄音

```bash
# 把錄音檔（m4a/mp3/wav/mp4/mov/aac/flac/ogg/m4v/caf）丟進 inbox/
python3 scripts/transcribe.py --inbox        # 第一次會下載約 1.6GB 的模型
python3 scripts/transcribe.py 會議.m4a       # 或指定單檔
```

逐字稿出現在 `inbox/transcripts/`，原始錄音移到 `inbox/done/`（`--keep` 可以不搬）。
其他旗標：`--lang`、`--model`、`--no-vad`、`--root`。

（下面幾個範例裡的 `/tmp/改寫稿.md` 在 Windows 上是 `$env:TEMP\改寫稿.md`，`Copy-Item`／`Set-Content` 都寫得出來。）

逐字稿讀完自己改寫（提到學生一律換成代號），再走 `append_record.py` 寫入
（學生記錄記得帶 `--stream`：這一段是日常觀察還是會談，落點不一樣），最後 `sync.py`。

**三套改寫骨架**（正本＝`config/verticals.json` 的 `voiceRule`；欄位正本＝`config/student-streams.library.json`）：

- **質性評量（`qualitative`）**：一則一個具體事件，先標「面向」（可複選）與「報告維度」，再寫課程、證據來源；正文只留看得到的事實與他說的話。
- **IEP／早療（`iep`）**：先對照該生 `card.json` 的 `goals` 分段，一條目標一則，標「目標編號」與「達成情形」（未開始／初步／部分達成／達成／類化）。
- **會談紀錄（`soap`）**：拆成 S／O／A／P 四段，再補會談次數、形式、風險評估（無／低／中／高）與下次時間。

```bash
python3 scripts/append_record.py --kind students --target S-01 --stream qualitative \
  --fields-json '{"面向":["手·意志","社群·人際"],"報告維度":"人際互動","課程":"main-block","證據來源":"課堂觀察"}' \
  --content-file /tmp/改寫稿.md --source voice

python3 scripts/append_record.py --kind students --target S-02 --stream iep \
  --fields-json '{"目標編號":"G1","達成情形":"部分達成","證據":"觀察"}' \
  --content-file /tmp/改寫稿.md --source voice

python3 scripts/append_record.py --kind students --target S-03 --stream soap \
  --fields-json '{"會談次數":"3","會談形式":"個別","風險評估":"低","下次時間":"2026-09-24"}' \
  --content-file /tmp/改寫稿.md --source voice
```

「目標編號」一定要是那位學生卡片上真的有的目標，否則以退出碼 2 拒寫並列出可用的目標。

## 9.5 期末產出：素材包＋草稿指令

```bash
python3 scripts/report_pack.py --format waldorf-homeroom --target S-01   # 質性評量：導師評語
python3 scripts/report_pack.py --format iep-tracking --target S-02       # IEP：每目標一表
python3 scripts/report_pack.py --format case-summary --target S-03       # SOAP：個案摘要／結案
python3 scripts/report_pack.py --format waldorf-homeroom --all           # 全班一包＋_index.md
```

其他旗標：`--stream`（只拿某一種記錄類型，可重複）、`--from`／`--to`、`--out`、`--local`、`--root`；
`--target all` 等同 `--all`。格式清單在 `config/report-formats.library.json`：
`waldorf-homeroom`／`subject-4`／`iep-tracking`／`case-summary`／`custom`。

輸出兩個檔到 `exports/`：`<代號>-<格式>-素材包.md`（分好組的事實）與
`<代號>-<格式>-prompt.md`（報告骨架＋書寫規則＋定稿稽核清單＋一段固定指令）。
**這支不呼叫任何 AI、不寫評語**——把素材包貼給你的 AI、再貼 prompt 最下面那段固定指令，
它寫草稿、你定稿；`waldorf-homeroom` 的「整體感受」那一段一律自己寫，不讓 AI 代筆。
寫完照 prompt 裡的稽核清單逐條檢查一次。

學校有自己的格式：`cp templates/report-format.custom.example.json config/report-format.custom.json`
（Windows：`Copy-Item templates\report-format.custom.example.json config\report-format.custom.json`），
把校方的標題貼進去，再跑 `--format custom`。
網頁上同一件事＝學生明細頁的「產生期末素材 ▾」、一覽頁的「產生全班期末素材 ▾」。
`exports/` 含名冊真名，已被 `.gitignore` 擋住，別放到公開的地方。

## 10. 驗收

```bash
python3 scripts/ledger.py --rebuild
python3 scripts/ledger.py --check          # 退出碼 0 ＝ 三處對得上
python3 scripts/ledger.py --check --offline   # 不連網，只比本機與備份
python3 scripts/doctor.py
git status
```

手動要做的五件：①你的帳號登入看得到 ②別的帳號（無痕視窗）打開顯示「無權檢視」
③三個分頁各新增一則（學生分頁**你勾的每一種記錄類型各記一則**），重新整理還在
④打開 Google 雲端硬碟看得到備份 zip
⑤**產生一份素材包打得開**：`python3 scripts/report_pack.py --format <你的格式> --target <代號>`，
`exports/` 裡出現 `-素材包.md` 與 `-prompt.md`，打開看得到剛剛記的那一則與報告骨架。

`git status` 不該出現：`data/`、`config/kit.json`、`config/tabs.json`、`setup/progress.json`、
`site/js/kit-config.js`、`site/js/firebase-config.js`、`firestore.rules`、`storage.rules`、
`inbox/`、`backups/`、`*-key.json`、`.env`。

---

## 11. 無頭交辦（選用；只有 cloud 模式有）

手機上對自己的 LINE 官方帳號講一段話 → 電腦醒著時自動變成一則紀錄 → 回你一句「記好了什麼」。

**要 Firebase 的 Blaze（隨用隨付）方案**——這個用量幾乎一定是 0 元，但要綁信用卡。
不想綁卡就不要做這一步，其他功能完全不受影響。

**完整步驟（LINE 頻道怎麼開、每一個畫面要按什麼、卡住怎麼查）寫在 `docs/HEADLESS.md`**，
這裡只列指令：

```bash
# ① Firebase 升到 Blaze；② 在 LINE Developers 開 Messaging API 頻道，拿 secret 與 token
#    （順便把 Auto-reply messages 關掉、用手機加那個帳號為好友）
# ③ 兩個金鑰寫進「登入時會載入」的設定檔（~/.bashrc / ~/.zshrc；Windows 走系統環境變數）
export KIT_LINE_CHANNEL_SECRET='…'
export KIT_LINE_CHANNEL_TOKEN='…'

# ④ 打開這個功能（setup 會問「無頭交辦」那一題）
python3 scripts/setup.py
python3 scripts/build_config.py

# ⑤ 金鑰交給 Cloud Function，部署收件端（一律用 --only，不要跑沒參數的 firebase deploy）
firebase functions:secrets:set KIT_LINE_CHANNEL_SECRET
firebase functions:secrets:set KIT_LINE_CHANNEL_TOKEN
firebase deploy --only storage --project <你的專案id>
firebase deploy --only functions:line-relay --project <你的專案id>

# ⑥ 把部署印出來的網址填回 LINE 的 Webhook URL、打開 Use webhook；
#    用手機傳一句話，它會回「配對碼：Uxxxx…」。填進 kit.json 的 headless.line.owner_user_id 之後：
python3 scripts/build_config.py
python3 scripts/headless.py --once      # 把配對碼送上雲端，relay 從此只認你
python3 scripts/headless.py --pair      # （沒收到配對碼時用這個查）

# ⑦ 掛排程（會多一個每 5 分鐘的工作）＋ 驗收
python3 scripts/schedule.py
python3 scripts/doctor.py               # 「無頭交辦」那一區五項要全綠
```

真正的驗收是**自己傳一則**：先收到「收到了」（雲端收到），五分鐘內收到「已記到…」（真的寫好了）。

無頭模式下 AI 要遵守的作業指示在 `AGENTS-HEADLESS.md`，你可以改它。
失敗**不會自動重試**（重試會把同一段話寫成好幾則）：`headless.py --status` 看、`--retry <id>` 重排。

---

## 從 v2 升級

1. `git pull`（或重新下載）。**只覆蓋** `scripts/`、`site/dashboard.html`、`site/js/*.example.js`、
   `templates/`、`config/*.example.json`、`firestore.rules.tmpl`、`storage.rules.tmpl`、
   `firebase.json`、`functions/`、文件。
   **絕對不要覆蓋** `config/kit.json`、`config/tabs.json`、`data/`、`setup/progress.json`、
   `firestore.rules`、`storage.rules`、`site/js/kit-config.js`、`site/js/firebase-config.js`、
   `backups/`、`inbox/`。

2. ```bash
   python3 scripts/setup.py --upgrade
   ```
   把 `config.yaml` 的 `owner_email`、`firebase`、`email` 轉成 `config/kit.json`，並自動跑 `build_config.py`。
   升級**只會自動勾一種**學生記錄類型：`homeroom`（導師班級學生紀錄），
   因為 v2 的 `data/students/<代號>/observations.md` 就是它的檔名，不勾的話舊觀察在網頁上看不見。
   其餘的類型（`qualitative`、`subject`、`case`、`iep`、`soap`）不會勾，業務記錄分頁也會先關著——要就照第 3 步想清楚，
   再重跑一次 `python3 scripts/setup.py`（既有記錄一則都不會動）。

3. **重新部署安全規則（不能省）**：
   ```bash
   firebase deploy --only firestore:rules --project <你的專案ID>
   ```
   升到 `v3.0.0-alpha.5` 或更新版本格外不能省——這一版把刪除改成兩段式（軟刪，真刪只走
   `scripts/purge_deleted.py`）、又加了 `co_owner_emails`，兩者都動了規則字串，
   沒重新部署的話刪除鍵會失敗、共同擁有者也登不進去。

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
python3 scripts/schedule.py --status                      # 排程現況
python3 scripts/schedule.py --uninstall                   # 拆掉排程
python3 scripts/ledger.py --check                         # 三處對帳
python3 scripts/doctor.py                                 # 健檢
python3 scripts/monthly_reminder.py --dry-run             # 本月未記名單（先看不寄）
python3 scripts/export_records.py --out ~/記錄.md          # 期末取材
python3 scripts/export_records.py --stream case            # 只要某一種學生記錄類型
python3 scripts/export_records.py --by-tag                # 依標籤分組
python3 scripts/export_records.py --split ~/備份           # 每個對象一個資料夾
python3 scripts/export_docs.py --kind students --target S-03 --docx --pdf        # 一位學生匯出 Word＋PDF
python3 scripts/export_docs.py --kind students --target all --with-class --docx  # 所有學生一份 Word
python3 scripts/export_docs.py --kind business --target paperwork --docx         # 某一組業務
python3 scripts/report_pack.py --format waldorf-homeroom --target S-01            # 期末素材包（質性評量）
python3 scripts/report_pack.py --format iep-tracking --target S-02               # 期末素材包（IEP）
python3 scripts/report_pack.py --format case-summary --target S-03               # 期末素材包（SOAP）
python3 scripts/report_pack.py --format waldorf-homeroom --all                   # 全班一包＋_index.md
python3 scripts/pending.py                                # 還沒決定要不要寄家長的
python3 scripts/parent_email.py --id S-01 --subject "…" --body-file msg.txt --dry-run
python3 scripts/build_preview.py                          # 產生單檔離線示範
python3 scripts/headless.py --status                      # 無頭交辦：待處理／失敗幾則（選用功能）
python3 scripts/headless.py --once                        # 無頭交辦：立刻收一次，不等排程
```
