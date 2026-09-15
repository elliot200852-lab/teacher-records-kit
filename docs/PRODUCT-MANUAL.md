# Teacher Records Kit 產品手冊

> 適用版本：`3.0.0-alpha.4`（以 repo 根目錄的 `VERSION` 為準）。
> 這份給**買下這套 kit 的老師**讀，從「電腦什麼都沒裝」寫到「期末把評語寫完」。
> 每一條指令與旗標都對過程式碼；文件與程式對不上的時候，**以程式為準**。
>
> 其他文件的分工：`AGENTS.md`＝給 AI 代理讀的安裝腦（步驟 0–11）、`docs/GUIDE.md`＝完全沒碰過 AI
> 的人的入門、`INSTALL.md`＝不用 AI 的純指令版、`docs/PLATFORMS.md`＝平台事實的正本、
> `docs/ARCHITECTURE.md`＝內部怎麼運作、`docs/DATA-CHECKLIST.md`＝安裝前的資料清單。
> 這份手冊把它們串成一條時間線，只指路、不重寫細節。

**目錄**：[1 這是什麼](#1-這是什麼給誰用拿到什麼)｜[2 安裝](#2-安裝從一台什麼都沒裝的電腦開始)｜
[3 日常使用](#3-日常使用)｜[4 期末](#4-期末素材包wordpdf整包匯出)｜
[5 資料在哪裡](#5-資料在哪裡誰看得到)｜[6 升級](#6-升級)｜
[7 疑難排解](#7-疑難排解速查表)｜[8 附錄](#8-附錄)

---

# 1. 這是什麼、給誰用、拿到什麼

## 1.1 一頁摘要

你拿到的是一個資料夾。把它交給你自己訂閱的 AI 代理（Claude Code／OpenAI Codex CLI／Gemini CLI），
說「讀 AGENTS.md，幫我裝起來」，一小時後你會有一個**只有你自己看得到的教學記錄網站**。

| 你拿到什麼 | 一句話 |
|---|---|
| **三個分頁** | 學生記錄、課程記錄、業務記錄。要不要開、裡面記什麼，全部由你勾 |
| **三個垂直方案** | 質性評量自動化／IEP 目標追蹤／SOAP 個案紀錄。方案只是「唸建議給你聽」，一項都不預先幫你勾 |
| **手機隨時記錄** | 網址加到手機主畫面就像一個 App，下課走廊上就能記；沒訊號也開得起來 |
| **資料完全在你自己的 Google 帳號** | Firebase 專案、雲端硬碟、網址全部開在你名下。作者沒有金鑰、沒有帳號、沒有副本 |
| **零個資上雲的代號制** | 記錄正文一律寫 `S-01`，真名只存在你電腦上的 `data/roster.csv` 這一個檔 |
| **期末素材包** | 一行指令把整年的碎片依報告格式分好組，附書寫規則與稽核清單，AI 寫草稿、你定稿 |

**另外有兩個選用的選項**，安裝時自己決定要不要，不要就當它不存在：

| 選項 | 一句話 | 在哪裡決定 |
|---|---|---|
| **本機模式**（`mode: local`） | 完全不碰雲端：沒有 Firebase、沒有網頁、沒有帳單、沒有要填的設定值。紀錄就是你電腦上的文字檔 | 安裝步驟 2 的第一句話（§2.5） |
| **用 LINE 交辦**（無頭交辦） | 在外面對 LINE 講一句話，回家的時候紀錄已經寫好了 | 安裝步驟 11，驗收之後才問（§2.5、§3.8） |

本機模式少的是「手機網頁與雙向同步」，其餘（錄音、Word／PDF、期末素材包、家長信、備份）一項都不少。
LINE 交辦要雲端模式，而且要把 Firebase 升級成 Blaze 方案（綁一張卡，實際用量幾乎一定是 0 元）。

**誰適合用**：一位老師、一台電腦、一個班（或一批個案）。實驗教育與私校的質性評量老師、
特教與早療的 IEP 老師、諮商／教練／社工的個案工作者，是這一版鎖定的三種人。

**這套不做**：多租戶、代管、家長端、網頁錄音、行動 App、自動評量生成、作者對你資料的任何介入
（`docs/ARCHITECTURE.md` §14）。

## 1.2 三個分頁

| 分頁 | 記什麼 | 一張卡 |
|---|---|---|
| **學生記錄** | 你對某一位學生的具體觀察 | 一位學生一張 |
| **課程記錄** | 課本身——講到哪、實際教了什麼、整體反應、下次要調整什麼 | 一門課一張 |
| **業務記錄** | 教學以外你每天在處理的事：班務、公文、會議、輔導個案、研習、報帳 | 一組業務一張 |

學生分頁底下**再分一層「記錄類型」**（`stream`）：質性觀察、導師日常觀察、科任觀察、個案追蹤、
IEP 目標追蹤、會談紀錄（SOAP）是**各自獨立的簿子**，各有欄位、分類詞、與「哪些學生在裡面」。
同一位學生在「導師班級學生紀錄」寫的東西不會出現在「個案追蹤」裡。
學生分頁上方另有**班級整體觀察**（`class`），記整班層次的事，不算在任何一位名下。

三個分頁用「**關聯**」串起來，語法 `<種類>/<對象>/<記錄id>`，例如某一則個案會議填
`students/S-03/2026-09-10`，就接回那位學生那一天的紀錄。

**沒有任何一項是系統替你決定的**：`config/tabs.example.json` 裡 `students.streams` 與
`business.groups` 都是空陣列，你勾了什麼才有什麼，一個都不勾也是合法的結果。

## 1.3 三個垂直方案

決定完紀錄放哪裡（§2.5）之後，精靈問的下一句是「你最像哪一種？」。選完，AI 把那個方案通常會勾的
東西**唸出來**，然後一項都不預先勾；建議清單在附錄 C，機器正本＝`config/verticals.json`。

| 方案 id | 給誰 | 痛點 | 期末產出 |
|---|---|---|---|
| `qualitative-assessment` | 實驗教育／私校老師 | 整年不打分數，期末卻要從一整疊零碎筆記回頭寫出每個孩子的評語 | `--format waldorf-homeroom` |
| `iep-tracking` | 特教／早療 | 目標達成的細節每天都在發生，期末的評鑑格式卻要求逐條交代方式、標準、日期與證據 | `--format iep-tracking` |
| `soap-casework` | 諮商／教練／社工 | 每次會談結束都要補寫 SOAP 或個案紀錄，手寫耗時又漏細節 | `--format case-summary` |

第四個選項是「都不是（我自己勾）」，答案檔寫 `"vertical": "none"`，照樣裝得起來。方案在資料上
只留兩個標記（`config/tabs.json` 的 `vertical` 與 `reportFormat`），不影響資料形狀。

## 1.4 三個入口、代號制、資料歸屬

**三個入口**：網頁（手機或電腦，打開網址登入就記）、本機文字檔（走 `append_record.py`）、
錄音檔（丟進 `inbox/`，AI 轉文字、改寫、念給你確認）。
錄音與逐字稿**全程在你自己的電腦上跑**（whisper.cpp），一個位元組都不外送。

**資料歸屬**：Google 帳號、Firebase 專案、雲端硬碟、網址全部開在你名下，帳單也是你的
（一般老師的用量在 Google 免費額度內）。這套 kit 只有程式碼與範本，零個資。
`scripts/export_records.py` 一行指令就能整包帶走。

**代號不是匿名。** 代號的用處是「這些文字可以安心交給 AI 讀、可以匯出、可以備份到雲端硬碟」；
你自己的名單一對照就知道是誰。真正擋住別人的，是伺服器端那條「只有你的 Google 帳號讀得到」的規則。
擋住真名寫進記錄的有三道：網頁寫入前自動代換、`append_record.py` 出現真名就拒寫（退出碼 5）、
`sync.py` 兩個方向都攔。

## 1.5 期末素材包

`scripts/report_pack.py` 把整年的紀錄依報告格式分好組，輸出兩個檔到 `exports/`：
`<代號>-<格式>-素材包.md`（分好組的事實）與 `<代號>-<格式>-prompt.md`（報告骨架＋書寫規則＋
定稿稽核清單＋一段固定指令）。**這支不呼叫任何 AI、不寫任何一句評語**，
所以同一批資料跑幾次結果都一樣。本文由你的 AI 照 prompt 寫、由你定稿；
`waldorf-homeroom` 的「整體感受」那一段在格式庫裡明寫「AI 不代寫、不潤飾」，留白給你自己寫。

---

# 2. 安裝：從一台什麼都沒裝的電腦開始

四個動作：**①取得資料夾 ②跑 bootstrap ③重開終端機、登入 AI ④第一句話**。
之後 AI 帶你走步驟 0–11，你只要回答關於你自己的問題。整段大約 30–60 分鐘，大半是等程式安裝。

## 2.1 ① 取得資料夾

進到 repo 頁面（[GitHub 連結](https://github.com/elliot200852-lab/teacher-records-kit)）→ 右上方綠色 **`Code`** → 最下面 **`Download ZIP`** → 下載後解壓縮（macOS 點兩下；Windows 右鍵「全部解壓縮」）。

會用 git 的人直接在終端機執行 `git clone https://github.com/elliot200852-lab/teacher-records-kit.git`，結果完全一樣。

**放哪裡**：路徑短、好找、**不要放在會同步的資料夾裡**。

| 平台 | 建議位置 | 不要放 |
|---|---|---|
| macOS | `~/teacher-records-kit` 或桌面 | iCloud Drive 的「桌面與文件」同步夾 |
| Windows | `C:\Users\你的名字\teacher-records-kit` | **OneDrive 底下**（檔案會被鎖、真名名冊會被同步上雲；`doctor.py` 偵測到會警告）、路徑超過 260 字的地方 |

## 2.2 ② 跑 bootstrap

bootstrap 是「Python 都還沒有」的那一層，一個作業系統一支腳本。

| 你的電腦 | 怎麼做 |
|---|---|
| **macOS** | 打開「終端機」（應用程式 → 工具程式）。輸入 `cd ` 空一格，把資料夾拖進視窗、按 Enter。再貼這一行：`bash setup/bootstrap.sh` |
| **Windows** | 打開資料夾裡的 `setup`，對 **`bootstrap.cmd`** 按兩下。黑色視窗會自己跑，跑完停在那裡等你按鍵（腳本最後有 `pause`） |
| Linux | `bash setup/bootstrap.sh`（Debian／Ubuntu 系，走 apt-get） |

**它只問你一題**：你訂的是哪一家 AI？① Claude Code ② OpenAI Codex CLI ③ Gemini CLI
④ 先不要裝。直接按 Enter ＝ ①。接著再問一次「可以開始了嗎」，按 Enter 繼續。

**它會裝什麼**（兩支腳本同一個順序）：Xcode 命令列工具（只有 macOS，會跳出系統視窗）／
Windows 則先確認 winget 在不在 → Homebrew（只有 macOS，含寫進 `~/.zprofile`、`~/.bash_profile` 的
shellenv）→ git、Python 3、Node.js（夠新的跳過；Windows 每裝完一項從登錄檔重讀 PATH）→
你選的那一家 AI 代理 CLI → 回頭跑 `scripts/install_tools.py`（Firebase CLI、gcloud、ffmpeg、
whisper.cpp；Windows 由 `py -3` 接手）→ 跑一次 `scripts/doctor.py` 健檢 →
印出「開新視窗、`cd`、叫 AI」三行。

**對話框**：macOS 的 Xcode 命令列工具會跳出系統視窗，按「安裝」，等它跑完（幾分鐘到十幾分鐘），
**裝完回到終端機把 `bash setup/bootstrap.sh` 再貼一次**——腳本在這裡會刻意停下來。
Homebrew 的官方安裝程式會問你的開機密碼。Windows 上 winget 裝東西時會跳出
「**使用者帳戶控制（UAC）**」，按「是」；不需要系統管理員身分。

**要多久**：網路正常的話 10–25 分鐘。whisper 的語音模型（約 1.6 GB）這時候不會下載，第一次真的轉錄時才抓。

**想先看它會做什麼、一個字都不裝**：`bash setup/bootstrap.sh --dry-run`（Windows：
`powershell -NoProfile -ExecutionPolicy Bypass -File setup\bootstrap.ps1 -DryRun`）。其他旗標：
`--agent claude|codex|gemini|none`（`-Agent`）直接指定、`--yes`／`-y`（`-Yes`）不停下來問。
**失敗的時候**不自動重試、不留裝到一半的狀態——某一項裝不起來就印出官方網址繼續往下走，
最後由 `doctor.py` 說到底缺什麼。重跑 bootstrap 是安全的，裝好的會自動跳過。

**已經有 Python 的電腦**不必走 bootstrap：

```bash
python3 scripts/install_tools.py --dry-run        # 先看會裝什麼
python3 scripts/install_tools.py                  # 真的裝
python3 scripts/install_tools.py --agent claude   # 順便裝 AI 代理的 CLI
python3 scripts/install_tools.py --with-gws       # 備份要走 gws 進階模式才加
python3 scripts/doctor.py                         # 健檢（裝完先重開終端機）
```

## 2.3 ③ 重開終端機、登入你的訂閱

**關掉終端機視窗、重新開一個新的**——PATH 是開視窗當下讀的，剛裝好的程式要新視窗才叫得到。
新視窗裡 `cd` 到資料夾（`cd ` 空一格，把資料夾拖進去，按 Enter），打 `claude`／`codex`／`gemini`
把 AI 叫起來。第一次啟動它會請你登入自己的訂閱帳號（Claude／ChatGPT／Google），在瀏覽器完成授權。

## 2.4 ④ 第一句話

登入完貼這一行（bootstrap 跑完也會把整行印在螢幕上）：

```
claude "請完整讀 AGENTS.md，然後帶我從步驟 0 開始安裝"     # Claude Code
codex  "請完整讀 AGENTS.md，然後帶我從步驟 0 開始安裝"     # OpenAI Codex CLI
gemini -i "請完整讀 AGENTS.md，然後帶我從步驟 0 開始安裝"  # Gemini CLI
```

已經在 AI 裡面了就直接打：**「讀 AGENTS.md，幫我裝起來。」** 三家的第一句話是同一句。
安裝腦只有一份 `AGENTS.md`；`CLAUDE.md`、`GEMINI.md`、`.github/copilot-instructions.md`、
`.cursor/rules/` 都只是指回它的小紙條。

## 2.5 ⑤ AI 精靈的 0–11 步

AI 一次只問一題，每一題都會告訴你去哪裡拿答案。進度記在 `setup/progress.json`，
中途休息明天再接都可以（步驟標題的正本＝`setup.py` 裡的 `STEP_TITLES`，
`setup/progress.example.json` 只是長相範例）。

| 步驟 | AI 做什麼 | **你要準備什麼** |
|---|---|---|
| **0 判斷狀態** | 讀 `VERSION`、`setup/progress.json`、`config/kit.json`，判斷新裝／續裝／從 v2 升級 | 不用準備。它自己看檔案，看完才開口 |
| **1 裝工具** | 跑過 bootstrap 就只跑 `doctor.py` 確認；否則跑 `install_tools.py` | 可能要輸入開機密碼（macOS）或按 UAC「是」（Windows） |
| **2 紀錄放哪裡＋Firebase 專案** | **先問「雲端還是只放這台電腦」**；選雲端才陪你走 Console、收好六個設定值 | **一個能自己開 Firebase 專案的 Google 帳號**（選本機模式完全不用） |
| **3 三個分頁要記什麼** | 先問「你最像哪一種」，再逐項念清單讓你勾 | 記錄類型、課名、業務組；IEP 的目標、SOAP 的概念化 |
| **4 產生設定與規則** | 跑 `setup.py` 寫設定、建 `data/` 骨架，然後**部署安全規則** | 不用準備 |
| **5 上線** | `firebase deploy --only hosting` | 不用準備（走 GitHub Pages 才要 GitHub 帳號） |
| **6 名單與舊資料** | 寫 `data/roster.csv`，舊記錄一則一則走 `append_record.py` | **學生名單**（座號＋姓名就夠）；有舊的電子檔一併給它 |
| **7 備份夾** | 把路徑或資料夾 ID 填進 `config/kit.json`，跑一次 `backup.py` | **裝好並登入「Google 雲端硬碟」桌面程式，在雲端硬碟裡建一個資料夾** |
| **8 排程（選用）** | `schedule.py` 掛每天 07:00 同步、每週日 08:00 備份 | 不用準備 |
| **9 錄音試跑** | `transcribe.py --inbox` 轉逐字稿，改寫後寫進去 | **用手機隨便錄一段三十秒的話**，傳到電腦丟進 `inbox/` |
| **10 驗收** | 九項逐項做、逐項回報 | 你的手機、你的瀏覽器、你的雲端硬碟 |
| **11 用 LINE 交辦（選用）** | 開一個 LINE 官方帳號、部署一支雲端程式、配對你的手機 | **Firebase 升級成 Blaze**、一個 LINE Developers 帳號。不要就直接說不要 |

### 步驟 2 的第一句：你的紀錄要放哪裡

安裝精靈問的第一件實質問題不是信箱，是**這套系統要不要上雲端**。兩個答案都是完整可用的：

| | **雲端**（`cloud`，預設） | **只放這台電腦**（`local`） |
|---|---|---|
| 開 Firebase 專案、填六個設定值 | 要 | **不用** |
| 手機網頁、電腦⇄手機雙向同步 | 有 | **沒有** |
| 用 LINE 交辦（步驟 11） | 可以開 | **不行** |
| 錄音轉逐字稿、Word／PDF、期末素材包、家長信、Drive 備份 | 有 | 有 |
| 帳單 | 你自己的（一般用量在免費額度內） | 沒有 |

「哪個比較安全」沒有標準答案，**兩邊的風險形狀不一樣**：雲端的風險是設定弄錯會外洩，
本機的風險是電腦壞了、丟了就沒了（所以本機模式的 Drive 備份更不能省）。
會在走廊上、車上隨手記的人選雲端；只在自己書桌前寫、而且對雲端就是不安心的人選本機。

**選了本機之後隨時可以改成雲端，既有紀錄一則都不會動**：跟 AI 說「我想改成雲端」，
它會改 `config/kit.json` 的 `mode`、重跑安裝精靈問那六個值、產生並部署規則、上線，
第一次同步把你已經寫的東西整批推上去。
（選本機模式的話，步驟 2 剩下的部分與步驟 4、5、11 會被自動標成「本機模式，略過」。）

### 步驟 2：學校帳號與 iPhone 的坑

**學校帳號常常被鎖住。** 判斷方法是**實際做一次**：用那個帳號登入
https://console.firebase.google.com ，按「建立專案」，輸入名字按下一步。真的建得出來就能用；
看到「你的機構不允許建立專案」或根本沒有建立按鈕就不行。不行的話兩條路：
①用你自己的個人 Gmail（資料在你私人帳號裡，學校換人、你調校都不影響）
②找學校資訊組開權限（資料掛在學校名下，但要等，權限被收回就進不去）。
**選好之後整套安裝從頭到尾都用那一個信箱**：登入 Firebase、設定裡的 `owner_email`、
之後打開網站登入——三處必須是同一個，不然你會看到「無權檢視」。

**iPhone 上登不進去這個坑在這一步先處理。** Console 給的 `authDomain` 預設是
`<專案ID>.firebaseapp.com`，但這套 kit 部署在 Firebase Hosting、網址是 `<專案ID>.web.app`。
兩者不同源，**iOS Safari 的跨網域儲存分區會讓 Google 登入一直失敗**（登入後又跳回未登入）。
所以打算用 Firebase Hosting 的話，`authDomain` 填 **`<專案ID>.web.app`**——
`config/kit.example.json` 的 `auth_domain` 留空即可，`build_config.py` 會自動填。
網站掛在別的網域（GitHub Pages、嵌進現有站）才填你實際打開網頁的那個網域。

### 步驟 3：三個分頁你要想清楚的

| 分頁 | 要想清楚的 |
|---|---|
| **學生** | 要不要這個分頁；班上幾位；代號前綴（預設 `S`，也可以用班級代號如 `5B`）；**要哪幾種記錄類型**；個案型的類型（`case`／`iep`／`soap`）**先列入誰** |
| **課程** | 要不要這個分頁；先建哪幾門（課名＋主課程或科任）。一門都不先建也行 |
| **業務** | 要不要這個分頁；十一組（附錄 D）裡哪幾組是你手上真的在跑的線 |

勾了 `iep` 的，先把該生的目標找出來：**領域／學年目標／學期目標／評量方式／評量標準／期程**，
一條一條講，編號（G1、G2…）AI 來編，寫進學生卡 `data/students/<代號>/card.json` 的 `goals`。
**卡片上沒有的目標編號，`append_record.py` 會當場擋下來。** 領域依鑑定結果填、不要自己改名：
特教＝認知／溝通／行動／情緒行為／社會／生活自理／學業；早療＝認知／語言／動作／社會情緒／生活自理。
勾了 `soap` 的，先想好**個案概念化五格**（主訴／背景／評估假設／處遇目標／結案標準）寫進卡片的
`conceptualization`，結案報告會逐條對照「結案標準」。兩者現在講不出來都可以先空著，之後補。

### 步驟 6：名單長什麼樣

`data/roster.csv`，**三欄**（範本 `templates/roster.example.csv`）：

```
代號,姓名,類型
01,學生甲,
02,學生乙,case
03,學生丙,case;iep
```

- 第一欄可以寫座號（`01`，程式自動接前綴變成 `S-01`），也可以直接寫完整代號。
- 第二欄是真名。**這是整套系統裡唯一有真名的檔**，被 `.gitignore` 擋住。
- 第三欄＝這位學生列入哪幾種**個案型**記錄類型，分號分隔。
  全班型的類型（`qualitative`、`homeroom`、`subject`）不用寫也不要寫。
- 第三欄是**雙向**的：網頁上按「＋ 列入學生」／「移出」，下一次 `sync.py` 會寫回這裡；
  你直接改這一欄，同步時也會推上網頁。兩邊都改過就當衝突處理，不覆蓋任何一邊。

### 步驟 7：備份夾

**預設（desktop 模式，零設定）**：裝並登入「Google 雲端硬碟」桌面程式
（https://www.google.com/drive/download/ ）→ 在雲端硬碟裡建一個資料夾 →
把它在電腦上的完整路徑填進 `config/kit.json` 的 `drive.desktop_dir`。
macOS 通常是 `~/Library/CloudStorage/GoogleDrive-<你的信箱>/My Drive/教學紀錄備份`；
Windows 通常是 `G:\My Drive\教學紀錄備份`（磁碟機代號因人而異，根目錄也可能叫 `我的雲端硬碟`）。
路徑不用自己找：`setup.py` 會自動偵測候選當預設值，`doctor.py` 發現路徑不存在時也會列出候選。

**進階（gws 模式）**：`drive.mode` 改 `gws`，`drive.backup_folder_id` 填資料夾 ID
（瀏覽器打開那個資料夾，網址 `.../folders/XXXX` 的 `XXXX`）。要 `install_tools.py --with-gws`
裝的 `@googleworkspace/cli`（三個平台都是 `npm i -g`）與你自己申請的 OAuth 憑證。

### 步驟 8：排程

預設每天 07:00 同步、每週日 08:00 備份。**排程會靜默失敗**（電腦沒開機、權限被擋、
學校電腦鎖住排程），真正的驗證是隔天看網頁頂端「上次同步 X 天前」有沒有更新，
超過七天會變紅字。詳細旗標見 §3.7。

### 步驟 9：錄音試跑

用手機錄一段三十秒的話，傳到電腦丟進 `inbox/`（macOS 用 AirDrop；Windows 用「手機連結」、
LINE 傳給自己再下載、或 USB 線）。支援格式：`.m4a` `.mp3` `.wav` `.mp4` `.mov` `.aac`
`.flac` `.ogg` `.m4v` `.caf`。跑 `python3 scripts/transcribe.py --inbox`
（第一次會下載約 1.6GB 的語音模型），逐字稿出現在 `inbox/transcripts/`，
原始錄音移到 `inbox/done/`。AI 讀完改寫、念給你確認，你點頭才寫進去。

### 步驟 11：用 LINE 交辦（選用，驗收之後才問）

裝完這一步之後，你在校門口對 LINE 講一句「今天午休 S-01 主動幫忙排椅子」，
電腦醒著的話五分鐘內紀錄就寫好了，手機上會收到一則回報。**不要這個功能完全不影響其他任何事。**

**前提三件**：雲端模式、**Firebase 升級成 Blaze 方案**（Cloud Functions 不跑在免費的 Spark 方案上；
用量幾乎一定是 0 元，但 Google 規定要綁一張卡——建議順手設一個 1 美元的預算提醒）、
你的 AI 代理已經登入過一次（沒登入的話它會停在登入畫面等到逾時）。

完整逐步在 **`docs/HEADLESS.md`**；這裡只講你要準備什麼、AI 會做什麼：

| 誰 | 做什麼 |
|---|---|
| **你** | ①Firebase 升級 Blaze ②到 https://developers.line.biz/console/ 開一個 **Messaging API** 頻道 ③抄 **Channel secret**（Basic settings 分頁）與 **Channel access token**（Messaging API 分頁最下面，按 Issue，**只顯示一次**）④同一頁把「自動回覆訊息」**關掉** ⑤掃 QR code 把這個帳號加為好友 |
| **AI** | 把那兩串金鑰寫進環境變數（不是寫進檔案）、跑安裝精靈、部署雲端程式、把部署後的網址貼回 LINE 主控台的 Webhook URL、打開 Use webhook |
| **你** | 從手機傳一句「哈囉」→ 會收到 `配對碼：Uxxxx…` → 把它貼給 AI |
| **AI** | 把配對碼寫進設定、掛上每 5 分鐘的排程、跑健檢（無頭交辦那五項要全綠）、陪你做一次真的端對端測試 |

幾件你會遇到、但其實是正常的事：

- LINE 主控台那顆 **Verify 按鈕回 `401` 是對的**（它送的是空簽章，本來就該被擋）。只有 404、500 才是真的有問題。
- **配對前那句配對碼，任何人傳訊息都會收到**——那是你拿到自己 LINE id 的唯一辦法，
  所以**配對要當場做完**。配好之後，不是你的帳號傳訊息一律被靜靜丟掉、不會有任何回應。
- 兩串金鑰只住在環境變數與 Google 的 Secret Manager，`config/kit.json` 裡**只有變數的名字**。
  它們要寫進登入時會載入的設定檔（macOS 的 `~/.zshrc`、Windows 的使用者環境變數），
  臨時打的 `export` 五分鐘後跑的排程看不到。

## 2.6 ⑥ 怎麼知道裝好了

`python3 scripts/doctor.py`——第一行印「健檢：`<資料夾>`（kit `<版本>`，`<平台>`）」，接著逐項印：

| 符號 | 意思 |
|---|---|
| 綠色 ✓ | 過了 |
| 紅色 ✗ | 必要項目沒過，底下一行「→」寫怎麼修。全部修完才會退出碼 0 |
| 黃色 ! | **選用**項目沒裝，不算失敗，可以往下走 |
| 灰色 – | 跳過（例如加了 `--skip-network`） |

健檢分六組，照這個順序印：平台與 kit 放的位置、版本比對、外部工具、設定與產生檔、
無頭交辦（沒開就只印一行「關著」）、Drive 備份夾。`--json` 給 AI 讀，`--skip-network` 跳過要連網的項目。
**本機模式下，跟雲端有關的那幾項會印成灰色的「跳過」，那不是失敗。**

**老師要自己動手的九項驗收**（步驟 10）：

| # | 驗什麼 | 誰做 | 怎麼算過 |
|---|---|---|---|
| 1 | 擁有者登入看得到 | 你 | 用你的帳號打開網址，看得到三個分頁 |
| 2 | **別的帳號被拒** | 你 | 無痕視窗或另一個 Google 帳號打開同一個網址 → 顯示「無權檢視」 |
| 3 | 三個分頁各新增一則 | 你 | 學生分頁**你勾的每一種記錄類型各記一則**，重新整理還在 |
| 4 | 三處對得上 | AI | `ledger.py --rebuild` 然後 `ledger.py --check`，退出碼 0 |
| 5 | 備份真的有上去 | 你 | 打開 https://drive.google.com 看到那個 zip |
| 6 | 個資沒帶進 git | AI | `git status` 乾淨 |
| 7 | 健檢全綠 | AI | `doctor.py` 必要項目全過 |
| 8 | 匯出打得開 | 你 | 明細頁按「匯出 ▾ → Word」，下載的 `.doc` 打得開 |
| 9 | 素材包打得開 | 你＋AI | `report_pack.py --format <你的格式> --target <代號>`，`exports/` 裡出現兩個檔 |

**第 2 項沒過是最嚴重的失敗**，停下所有事先修：多半是規則沒部署成功，或規則裡的信箱打錯。

**最後一步：加到手機主畫面。** 用手機打開網址、登入，iPhone（Safari）按分享鍵 →「加入主畫面」，
Android（Chrome）按右上角選單 →「加到主畫面」。之後點桌面圖示就像開一個 App
（`site/manifest.json` 設了 `display: standalone`）。

## 2.7 Windows 差異一表

| 這份手冊裡寫的 | Windows 上換成 |
|---|---|
| `python3 scripts/x.py` | **`py -3 scripts\x.py`**（或 `python scripts\x.py`）。`python3` 在 Windows 常是「打開 Microsoft Store」的假殼 |
| `/tmp/<任何檔>`（`answers.json`、`改寫稿.md`…） | `$env:TEMP\<檔>`——**每一個都要換**，不是只有 `answers.json` |
| `bash setup/bootstrap.sh` | 對 `setup\bootstrap.cmd` **按兩下** |
| `cat`／`ls`／`cp`／`rm` | `Get-Content`（`type`）／`Get-ChildItem`（`dir`）／`Copy-Item`／`Remove-Item` |
| `export KIT_SMTP_APP_PASSWORD='…'` | `$env:KIT_SMTP_APP_PASSWORD = '…'` |
| `~` | `C:\Users\<名字>`（腳本裡的 `~` 三個平台都會展開） |
| 終端機 | **Windows Terminal 或 PowerShell**。不是 cmd、**不是 WSL**、不是 Git Bash |
| 排程機制 | 工作排程器（`\TeacherRecordsKit\Sync`、`\Backup`，開了 §3.8 還有 `\Headless`）；跑的時候會閃一下黑色視窗，正常 |
| 可攜工具放哪 | `%LOCALAPPDATA%\teacher-records-kit\tools\` |

**WSL 直接拒跑**：備份夾與工作排程器都在 Windows 那一邊，WSL 看不到，會靜靜地失效。
完整的平台對照、每一個坑與它們對應的程式碼在 `docs/PLATFORMS.md`。

---

# 3. 日常使用

## 3.1 網頁（手機與電腦）

**登入**：打開網址 → 用 Google 登入 → 只有 `owner_email` 那個帳號進得去，
其他帳號看到「此帳號 `<信箱>` 無權檢視」。想確認網頁本身沒壞又不想動真資料：
網址後面加 **`?demo=1`**，它完全不連 Firebase，用假資料跑一遍，
資料只存在那個瀏覽器的 localStorage，頂端有黃色橫幅說明。

**三個分頁與記錄類型切換**：分頁列由 `config/tabs.json` 決定，你關掉的分頁不會出現。
學生分頁最上面一排是「記錄類型」切換，只顯示你勾的那幾種；全班一覽、「本月已記／未記」標籤、
篩選、新增表單的欄位，全部跟著**當前類型**走。`scope: case` 的類型多兩顆按鈕：
上方的「**＋ 列入學生**」、每張卡上的「**移出**」（移出只改名冊，**一則紀錄都不會刪**，
要按兩下：第一下變成「確定移出？」）。分頁狀態寫在網址的 `#` 後面（`#students`、`#courses`、
`#business`、`#class`、`#s/<代號>`），所以手機的返回鍵是通的。上方另有「📋 班級整體觀察」入口。

**新增／編輯／刪除一則**：點進一位學生／一門課／一組業務 →「**＋新增**」。
表單長相由那一種記錄類型（或那一組業務）的 `fields` 決定，型別有 `text`／`date`／`select`／
`multiselect`／`goal`，每個欄位帶一行提示。**標籤**那排按鈕點一下就加上去。
正文提示字是「記錄內容（客觀描述具體事件；請用代號、勿寫真名）…」；
寫入前網頁會**自動把名冊上的真名換成代號**。

**刪除是兩段式的**（要二次確認）。在網頁上按刪除＝**隱藏起來、並從本機與備份的 md 移除**：
那則會被標成已刪、網頁上不再出現，`sync.py` 下一次會把本機 `data/*.md` 的那個區塊刪掉並寫一筆
進 `data/audit.jsonl`，匯出（Word／PDF／.md）、期末素材包、台帳對帳也都當它不存在。
但**雲端那份原文還留著**（備份 zip 的 `export.json` 裡也還有），為的是防手滑——
真的要抹掉，只有你自己在終端機跑：

```
python3 scripts/purge_deleted.py                  # 先看有哪些（不會印正文、不會刪）
python3 scripts/purge_deleted.py --all --confirm  # 真的刪（不可逆）
```

沒有 `--confirm` 一則都不會刪。**個資法的刪除請求，最終完成點是你跑這一支**——
網頁上按刪除只完成了一半。這支腳本 AI 代理與無頭交辦一律不碰（安全規則也擋不住它，
它走的是你自己的 gcloud 權杖）。刪之前先跑一次 `python3 scripts/backup.py` 比較安心。
**日期改不了**：`date` 欄位與記錄 id 建立後就鎖死（安全規則擋著）。

**學生卡**：明細頁頂端會依當前記錄類型出現兩張卡的其中一張——`iep` 出「**目標清單**」
（`{id, 領域, 學年目標, 學期目標, 評量方式, 評量標準, 期程}` 一條一列），`soap` 出
「**個案概念化**」（主訴／背景／評估假設／處遇目標／結案標準）。這兩塊是「會被回頭改的底稿」，
跟一則一則的記錄分開存（本機 `data/students/<代號>/card.json`，雲端 `students/<代號>`）。
新增 `iep` 記錄時「目標編號」欄從這張卡的目標裡挑；卡上還沒有目標的話，
表單直接寫「先在上方『目標清單』加目標」。

**關聯**：每一則都有「關聯」欄，語法 `<種類>/<對象>/<記錄id>`，分號分隔，
例如 `students/S-03/2026-09-10; courses/fractions/2026-09-09-1435`。
`rid` 在同一位學生底下是唯一的，所以關聯不必也不用指定記錄類型。

**載入更多**：明細頁一次只抓**最近 50 則**，更舊的按「**載入更多（較舊的記錄）**」再往下翻一頁，
底下會寫「目前顯示最近 N 則；匯出與期末素材包一律含全部記錄」。
**匯出與素材包不走這條分頁**，它們本來就要全部。

**離線的時候**：頂端出現藍色的「**離線中，會在連線後送出**」。讀過的東西留在瀏覽器裡
（Firestore 的本機快取），手機在教室沒訊號也打得開；離線時新增的記錄會排隊，連上線自動送出。

**同步狀態列的顏色**——頂端那一行讀的是 Firestore 的 `meta/status`，
由你電腦上的 `sync.py`／`backup.py` 寫：

| 顏色 | 看到什麼 | 意思 | 怎麼辦 |
|---|---|---|---|
| **灰字**（正常） | `上次同步：今天`／`上次備份：3 天前` | 一切正常 | 不用做什麼 |
| **紅字** | `上次同步：9 天前`、`上次同步：還沒有過` | 超過七天沒跑，排程可能停了 | 手動 `python3 scripts/sync.py`，再看排程 |
| **紅字** | `上次同步／備份出錯：<訊息>` | 上一次同步或備份自己出錯了 | 把訊息貼給 AI |
| **紅字** | `讀不到同步狀態` | 暫時連不上，或安全規則還沒讓你讀 `meta/status` | 一直這樣就重新部署規則 |
| **琥珀色**（米黃底方框） | `上次同步有 2 則衝突／1 則真名攔截，尚未寫回電腦` | 上次同步有東西被擋下來，那幾則還留在雲端等你處理 | 跟 AI 說「幫我看同步擋下了什麼」 |

狀態列每五分鐘自己更新一次，切分頁時也會重讀（30 秒內不重複打）。
**正常狀態是灰字，畫面上沒有綠色那一格**（`site/dashboard.html` 的 `.statusbar` 樣式）。

**網頁上臨時加的類型／業務組**：「**＋ 選擇類型**」與「**＋ 新增業務組**」是同一套元件，
加完**只有網頁看得到**。畫面會跳一行提示，`sync.py` 也會印出來——回頭跟 AI 說
「我在網頁上加了○○」，由它寫進 `config/tabs.json` 再跑 `build_config.py`，
本機記錄檔與安全規則才跟得上。`sync.py` 刻意**不會自己動 `config/tabs.json`**。

## 3.2 電腦端：錄音 → 記錄

```
手機錄一段 → inbox/ → transcribe.py --inbox
   （ffmpeg 轉 16kHz 單聲道 wav → whisper.cpp 本機跑）
   → inbox/transcripts/<檔名>.md（每行帶 [HH:MM:SS]），原始錄音移到 inbox/done/
   → ★ AI 讀逐字稿、改寫成記錄、念給你確認 ★
   → append_record.py --source voice … → sync.py
```

`transcribe.py` 旗標：`--inbox`（轉 `inbox/` 裡所有還沒轉過的）、`--keep`（轉完不搬到 `done/`）、
`--lang`（預設看 `config/kit.json` 的 `voice.lang`，通常 `zh`）、`--model`（預設
`ggml-large-v3-turbo`）、`--no-vad`（VAD 模型下載不到時）、`--root`。
也可以直接給檔名：`python3 scripts/transcribe.py 會議.m4a`。

**改寫是 AI 的工作，不在腳本裡。** 四個原則：一律用代號、寫具體事件不寫評語、
口語變書面但不美化、一段話只落在一種記錄類型裡（一口氣講了三個孩子就拆成三則）。
whisper 會把人名、專有名詞、台語詞聽錯，改寫的時候要順手修掉。
三套改寫骨架（正本＝`config/verticals.json` 的 `voiceRule`）：`qualitative` 拆成一則一個具體事件、
先標「面向」（可複選）與「報告維度」；`iep` 先對照該生卡片的 `goals` 分段、一條目標一則、
標「目標編號」與「達成情形」；`soap` 拆成 S／O／A／P 四段、補會談次數、形式、風險評估、下次時間。

### `append_record.py`——唯一的寫入通道

**不要自己編輯 `data/` 底下的 md 檔。** 直接編輯很容易把新的一則插進同一天的舊區塊前面
或整檔重寫，那會讓既有記錄重新編號，下一次同步就把它們當成「舊的刪了、新的加了」，
**雲端那邊的紀錄會被誤刪**。

```bash
python3 scripts/append_record.py --kind students --target S-03 --stream homeroom \
  --date 2026-09-01 --tags "#課堂 #學習態度" --content-file /tmp/一則.md --source file
```

| 旗標 | 說明 |
|---|---|
| `--kind` | **四選一**：`students`／`class`／`courses`／`business` |
| `--target` | 對象代號（`class` 固定 `main`；學生用 `S-03`；課程與業務用設定裡的 id） |
| `--stream` | **`--kind students` 必填**；`--kind class` 也吃（限 `scope: class` 的類型，剛好只有一種時可以不帶）；`courses`／`business` 不准帶 |
| `--content-file` | 正文檔；給 `-` 就是從 stdin 讀 |
| `--date` / `--time` | 預設今天；同日撞號時自動帶現在時間 |
| `--tags` / `--fields-json` / `--related` | 標籤／欄位（複選欄位直接給陣列）／關聯（分號分隔） |
| `--source` / `--task-id` | `web`／`voice`／`file`；語音來源的任務代號（選填） |
| `--sync` / `--json` | 寫完順手同步這個目標／結果輸出 JSON |
| `--allow-names` | 放行真名檢查（極少數情況；**會寫進稽核記錄**） |
| `--root` | 資料根目錄（測試或多帳號才要） |

寫入前四道閘全部跑完才動檔案：

| 閘 | 擋什麼 | 退出碼 |
|---|---|---|
| 旗標檢查 | `--stream` 該帶沒帶／不該帶卻帶了、日期格式、欄位有換行、`目標編號` 填了卡片上沒有的 | **2** |
| 目標白名單 | `--kind`＋`--target`＋`--stream` 在設定裡不存在（含「這位學生有沒有被列入這個個案型類型」） | **3** |
| 真名攔截 | 正文／欄位／標籤出現名冊真名 | **5** |
| 記錄檔不見 | 設定裡有這個目標，但 `data/…` 底下那個 `.md` 被刪掉或還沒建 | **6** |
| id 不變 | 寫前後各解析一次，舊 id 有變就把檔案**截回原長度**再異常退出 | **9** |

最後一道的意思是：**寧可什麼都沒寫，也不留半截。**

**記錄 id 的規則**：當天第一則 ＝ 日期本身（`2026-09-10`）；之後每一則 ＝ 日期＋建立時間
（`2026-09-10-1435`）；同一分鐘再撞就補到秒（`2026-09-10-143512`）。

## 3.3 `sync.py`——雙向同步

```bash
python3 scripts/sync.py --dry-run              # 只看會發生什麼，不寫任何東西
python3 scripts/sync.py                        # 真跑
python3 scripts/sync.py --only students/S-03   # 只同步一個目標
python3 scripts/sync.py --quiet                # 沒事就不出聲（排程用）
```

| 情況 | 做法 |
|---|---|
| 檔案裡有、雲端沒有、以前沒同步過 | 推上去（一定帶 `stream` 與 `sourceFile`） |
| 雲端那則被網頁改過，本機那則自上次同步後沒動 | 寫回檔案（先備份成 `.<檔名>.prev.md`） |
| **兩邊都改** | **不覆蓋**，印出來讓你自己決定 |
| 雲端那則被刪掉（網頁上刪的＝標成已刪，或以前同步過、現在不見了） | 從本機檔也刪掉，寫進 `data/audit.jsonl`（只記 id 與指紋，不記正文）。雲端原文留著，等你自己跑 `purge_deleted.py`。**整檔不見或變空就一律不刪任何東西** |
| 任一方向出現名冊真名 | 攔下不同步 |

學生卡的 `goals`／`conceptualization` 與名冊第三欄走同一條「不覆蓋」規則。
每一個回寫 Firestore 的寫入都帶 `currentDocument.updateTime` 前置條件——你正在手機上打字、
同時電腦的排程跑了一次同步，你打的字不會被靜靜蓋掉。

跑完印一行摘要：`同步 N 個目標：上傳 a、回寫 b、從網頁新增 c、刪除 d、衝突 e、真名攔截 f`。
**衝突與真名攔截都不會自動處理**，腳本會逐則印出來：衝突→打開那個檔案跟網頁比對，
決定留哪一邊，改完再跑一次；真名→把正文裡的姓名改成代號。
這兩種的則數會寫進 `meta/status`，變成網頁頂端那格琥珀色的提示。

## 3.4 `backup.py`——兩種模式

zip 裡有兩樣東西：`data/` 全份，加上 `export.json`（Firestore 全量快照，網頁上打的字也一起備走）。

| 模式 | 怎麼跑 | 適合誰 |
|---|---|---|
| **desktop**（預設、零設定） | 把 zip 複製進「Google 雲端硬碟」桌面程式的同步夾（`drive.desktop_dir`），剩下交給那個程式自己上傳。複製後比對 md5，對不上就把那份刪掉 | 所有人。不用 OAuth |
| **gws**（進階） | 用 `@googleworkspace/cli` 直接上傳到 `drive.backup_folder_id`，上傳後比對 md5 | 已經在用 gws、不想裝桌面程式的人 |

```bash
python3 scripts/backup.py               # 完整備份
python3 scripts/backup.py --local-only  # 只做本機 zip，不碰雲端
python3 scripts/backup.py --no-export   # 不抓資料庫快照（離線時）
python3 scripts/backup.py --quiet       # 排程用
```

本機 zip 放 `backups/teacher-records-<時間戳>.zip`，只保留最近 `drive.keep_backups` 份
（預設 12，Drive 上的不動）。每次備份寫一行進 `data/backups.jsonl`（zip 路徑、md5、Drive file id），
並更新 `meta/status.lastBackupAt`。
**gws 模式有一條鐵則：找不到那個資料夾就停手，絕不自己建一個新的**——
自建的話備份會靜靜地跑到別的地方去，而你以為你有備份。

## 3.5 `ledger.py`——三處對帳

```bash
python3 scripts/ledger.py --rebuild          # 掃 data/ 四種檔重建台帳
python3 scripts/ledger.py --check            # 三處對帳，印三欄表
python3 scripts/ledger.py --check --offline  # 不連網，只比本機與備份
python3 scripts/ledger.py --check --json     # 給 AI 讀
```

`--check` 比對本機、Firestore、與**最近一次備份 zip 裡實際有的東西**（打開 zip 數的），
印出不一致清單：本機有網站無／網站有本機無／內容雜湊不同／最近一次備份缺哪些。
**退出碼 0 ＝ 三處對得上，1 ＝ 有差。**

## 3.6 三支選用的腳本

```bash
python3 scripts/pending.py                              # 有觀察但還沒決定要不要寄家長的
python3 scripts/pending.py --all                        # 連已處理的也列
python3 scripts/pending.py --mark S-01 2026-09-10 skip  # 標記不用再提醒

python3 scripts/parent_email.py --id S-01 --subject "…" --body-file msg.txt --dry-run
python3 scripts/parent_email.py --id S-01 --subject "…" --body-file msg.txt --draft
python3 scripts/monthly_reminder.py --dry-run           # 本月未記名單（先看不寄）
python3 scripts/monthly_reminder.py --month 2026-09
```

`parent_email.py` 把一則已經改寫成家長語氣的訊息寄給某位學生的家長。`--dry-run` 只印不寄；
**`--draft` 一定不寄**——`email.method` 是 `gws` 就存進 Gmail 草稿匣，其他寄法（`smtp`）
落地成 `exports/` 底下的草稿檔。**一律先給老師看稿、他點頭才寄。**
寄信要先設好 `config/kit.json` 的 `email` 區塊與環境變數 **`KIT_SMTP_APP_PASSWORD`**
（Google 帳號 → 安全性 → 兩步驟驗證 → 應用程式密碼）；那串密碼**絕不寫進設定檔**。
家長信箱放 `data/contacts.csv`（欄位位置在 `config/kit.json` 的 `parents`）。

## 3.7 排程與「怎麼看它有沒有跑」

| 平台 | 機制 | 看得到的東西 |
|---|---|---|
| macOS | launchd LaunchAgent | `~/Library/LaunchAgents/com.teacher-records-kit.{sync,backup,headless}.plist` |
| Windows | 工作排程器 | 工作 `\TeacherRecordsKit\Sync`、`\Backup`、`\Headless`；定義檔 `setup/launchers/*.xml`（gitignored） |
| Linux | crontab | `crontab -l` 裡被 `# >>> teacher-records-kit` … `# <<< teacher-records-kit` 包起來的那幾行 |

掛幾支看你裝了什麼，**不是固定兩支**：

| 工作 | 什麼時候會掛 | 頻率 |
|---|---|---|
| 同步 | 只有雲端模式 | 每天 07:00（`--sync-time`） |
| 備份 | 一定有 | 每週日 08:00（`--backup-day`／`--backup-time`） |
| 收 LINE 交辦 | 只有開了 §3.8 那個功能 | **每 5 分鐘** |

log 在 `logs/`，用的是跑 `schedule.py` 當下那個 Python。Windows 的排程只在該使用者登入時執行；
錯過的那次會在下次開機補跑（`StartWhenAvailable`）。macOS 與 Windows 的 `--status`
對你沒開的那幾項會印「（沒開這個功能，本來就不該掛）」，那不是失敗；
Linux 的 `--status` 只列你真的該有的那幾支。

```bash
python3 scripts/schedule.py --dry-run                           # 先看
python3 scripts/schedule.py                                     # 真的掛
python3 scripts/schedule.py --status                            # 掛了沒
python3 scripts/schedule.py --print-cron                        # 只印等效的 crontab（掛幾支就印幾行）
python3 scripts/schedule.py --sync-time 08:30                   # 換同步時間
python3 scripts/schedule.py --backup-day 6 --backup-time 21:00  # 換備份的星期與時間（0＝週日）
python3 scripts/schedule.py --uninstall                         # 移除
```

**`--status` 說掛上了，不等於它有在跑。** 真正的驗證是網頁頂端「上次同步 X 天前」那個數字。

## 3.8 用 LINE 交辦（裝了才有）

裝法在 §2.5 步驟 11，完整版在 `docs/HEADLESS.md`。這一節講**裝好之後怎麼用**。

**你傳什麼**：對那個 LINE 官方帳號傳**文字**或**語音**，一次講一件事，講清楚三件——
**誰**（用代號，`S-03`）、**什麼時候**（沒講就當今天）、**發生什麼**。例如：

```
今天午休 S-01 主動幫忙排椅子，第一次看到他主動
S-05 第三次會談，主訴一樣是睡不著，這次願意講家裡的事
昨天第三節主課程，講到河流地形，全班都很投入
```

**你會收到什麼**：傳出去馬上收到一句「**收到了，電腦醒著時會處理**」——
那只是雲端收到了，**不代表已經寫進去**。真正寫完之後會再收到一則回報，
寫的是它把這件事記到哪裡去了（例如「已記到 S-01 的導師班級學生紀錄，2026-09-12」）。
第一句是雲端當場的回覆，不吃推播額度；第二句才是推播。
**一則交辦只推播這一則**——LINE 免費方案每個帳號每月只有 200 則推播，
所以它不會再推「開始處理了」「逐字稿好了」這種進度。

**它不確定的時候不會猜**。聽不清楚是哪一位學生、或分不出該記成哪一種記錄類型，
它會回報「聽起來像○○，但我不確定，**沒有寫入**」——寧可你回家自己補，也不寫一則錯的進去。
真名也一樣：正文裡出現名冊上的真名會被寫入通道直接擋下來。

**電腦睡著或關機**：訊息就排在雲端，一則都不會掉，也一則都不會被處理。
電腦醒來之後五分鐘內補完，每一則各給你一則回報。所以在外面傳完，回家開電腦就好。

**怎麼看狀況**：

```bash
python3 scripts/headless.py --status            # 還有幾則沒處理、哪幾則失敗了
python3 scripts/headless.py --status --json     # 給 AI 讀
python3 scripts/headless.py --once              # 手動催一次（不等排程）
python3 scripts/headless.py --once --dry-run    # 只印會做什麼，不寫任何東西
python3 scripts/headless.py --retry <事件id>     # 把某一則失敗的重新排隊
python3 scripts/headless.py --pair              # 印出配對碼候選（配對階段用）
```

**失敗不會自動重試。** 這是刻意的：自動重試最糟的情況是同一句話被寫成三則紀錄，
而你得自己找出來刪掉。失敗的那一則會停在那裡，等你看過再 `--retry`。
每一則的處理結果都留一行在 `data/headless-audit.jsonl`，排程的輸出在 `logs/headless.log`。

**要換手機或換 LINE 帳號**：跟 AI 說一聲，它改設定裡的配對碼再跑一次 `--once` 就好，
**不用重新部署**。

---

# 4. 期末：素材包、Word／PDF、整包匯出

## 4.1 `report_pack.py`——素材包＋草稿指令

```bash
python3 scripts/report_pack.py --format waldorf-homeroom --target S-01   # 質性評量：導師評語
python3 scripts/report_pack.py --format subject-4       --target S-01    # 科任評語四項
python3 scripts/report_pack.py --format iep-tracking    --target S-02    # IEP：每目標一表
python3 scripts/report_pack.py --format case-summary    --target S-03    # SOAP：個案摘要／結案
python3 scripts/report_pack.py --format custom          --target S-04    # 學校自己的表格
python3 scripts/report_pack.py --format waldorf-homeroom --all           # 全班一包＋_index.md
```

`--target all` 等同 `--all`。其他旗標：`--stream <類型>`（只拿某一種學生記錄類型，可重複；
不給＝這個格式吃的那幾種）、`--from`／`--to`、`--out <目錄>`（預設 `exports/`）、
`--local`（只讀本機 markdown、絕不連網）、`--root`。

格式清單的正本＝`config/report-formats.library.json`：

| 格式 id | 標題 | 吃哪幾種記錄類型 | 分組依據 | 段落 |
|---|---|---|---|---|
| `waldorf-homeroom` | 導師質性評量 | `qualitative`、`homeroom` | 報告維度 → 面向 → 課程 | 發展樣貌／客觀描述五維度／整體感受／導師建議（8 段） |
| `subject-4` | 科任評語四項 | `subject`、`qualitative` | 觀察向度 → 科目 | 關係／參與／可見的學習證據／下一步 |
| `iep-tracking` | IEP／早療目標追蹤報告 | `iep` | 目標編號 | 現況能力／目標達成情形／評量方式日期與標準／相關服務／行為功能介入／轉銜建議／附個案會議紀錄（7 段） |
| `case-summary` | 個案摘要／結案報告 | `soap`、`case` | 會談次數 | 個案概念化／歷程摘要／進展評估／風險與安全／處遇建議或結案評估（5 段） |
| `custom` | 學校自己的格式 | 由你決定 | 預設「報告維度」 | 你貼進 `config/report-format.custom.json` 的段落 |

`waldorf-homeroom` 的五個報告維度：行為與自我管理／人際互動／學習態度與能力／
內在特質與個人發展／挑戰與方向。

**學校有自己的表格**：`cp templates/report-format.custom.example.json config/report-format.custom.json`
（Windows 用 `Copy-Item`），把校方的報告標題、每段要寫什麼、字數限制貼進去，
`groupBy` 填你記錄時實際用的欄位名（例如「報告維度」「觀察向度」「科目」），
`rules` 留空就用格式庫 `custom` 的通用規則，再跑 `--format custom`。

## 4.2 素材包裡有什麼

| 檔 | 內容 |
|---|---|
| `<代號>-<格式>-素材包.md` | 依格式分好組的**事實**：每一組底下是那幾則紀錄（日期、欄位、正文）、統計，以及**缺漏提示**——`dimensions` 裡沒有紀錄的分組、零紀錄的目標、缺號的會談都會照實列出來 |
| `<代號>-<格式>-prompt.md` | 報告骨架（每一段的標題、提示、字數）＋書寫規則＋定稿前的稽核清單＋最下面一段固定指令 |

`--all` 另出一份 `_index.md` 全班總表（誰還缺什麼一眼看得出來）。
`report_pack.py` 只做四件確定性的事：分組、統計、標出缺漏、附上骨架與規則。

## 4.3 AI 寫草稿、你定稿

1. **把素材包貼給你的 AI，再貼 prompt 最下面那段固定指令。** 那段指令要求：材料只有素材包；
   每一句都要指得出是素材包裡哪一則（哪一天）；素材包裡沒有的事一個字都不補；
   某一段沒有素材就寫「本期未蒐集到紀錄」，不推估。
2. **`waldorf-homeroom` 的「整體感受」那一段留白**，標一行「（這一段請老師自己寫）」。
   那是格式庫裡明寫的規則：AI 不代寫、不潤飾。
3. **草稿寫完先跑 audit 清單**，一條一條對過去，每一條寫「過」或「哪裡不過、我怎麼改的」。
   常見的幾條：每個判斷指不指得出日期與來源；有沒有出現別的學生的姓名；每位是不是只有一個下一步；
   有沒有 AI 對比句與定型語言。IEP 另外對「每一條 goals 都有段落（含零紀錄的）」「達成情形只用五級」；
   SOAP 另外對「會談次數連續」「全文沒有真名」。
4. **最後一版是你的。** 你改完就是定稿，AI 不回頭「順手修正」。

## 4.4 網頁上的同一顆按鈕

| 在哪 | 按鈕 | 下載什麼 |
|---|---|---|
| 學生**明細頁** | 「**產生期末素材 ▾**」 | 一份 `.md`：分好組的素材＋檔尾給 AI 的 prompt |
| 學生**一覽頁** | 「**產生全班期末素材 ▾**」 | 一份 `.md`、每位學生一節，檔尾附同一段 prompt |

下拉列的是格式庫裡 `for` 含當前記錄類型的那幾個格式，預選 `config/tabs.json` 的 `reportFormat`。
腳本端的 `--all` 是**每位學生各一個檔＋一份 `_index.md`**；網頁端的「產生全班期末素材」
是**一份檔、每位學生一節**。內容規則一樣，檔案切法不同。

## 4.5 `export_docs.py`——Word 與 PDF

**網頁端**（零相依、離線可用）：

| 在哪 | 按鈕 | 選項 |
|---|---|---|
| 學生明細頁 | 「**匯出 ▾**」 | Word 與 PDF 各兩項：「只匯出目前這一種記錄類型」或「這位學生全部類型」 |
| 課程／業務組／班級整體觀察明細頁 | 「**匯出 ▾**」 | 「匯出 Word（.doc）」「匯出 PDF（列印）」 |
| 學生一覽頁 | 「**匯出所有學生 ▾**」 | 勾要哪幾種記錄類型、填日期範圍（兩格留空＝全部）、可勾「含班級整體觀察（放在文件最前面）」 |

**Word ＝直接下載一個 `.doc`**（Word、Google 文件、Pages 都打得開），不載任何外部函式庫。
**PDF ＝開一個乾淨的列印版面**，在列印視窗選「儲存為 PDF」——手機的列印／分享選單裡一樣有。
瀏覽器擋掉彈出視窗時，它會改成在同一頁蓋一層列印版面。

**腳本端**（真 `.docx`）：

```bash
python3 scripts/export_docs.py --kind students --target S-03 --docx --pdf         # 一位學生，全部類型
python3 scripts/export_docs.py --kind students --target all --with-class --docx   # 所有學生一份文件
python3 scripts/export_docs.py --kind business --target paperwork --docx --pdf    # 某一組業務
python3 scripts/export_docs.py --kind class --target main --docx                  # 班級整體觀察
```

| 旗標 | 說明 |
|---|---|
| `--kind` / `--target` | `students`／`class`／`courses`／`business`；`all` ＝全部（學生的 `all` ＝所有學生，一份文件每人一節） |
| `--stream 類型` | 只匯出某一種學生記錄類型（可重複） |
| `--from` / `--to` / `--with-class` | 日期範圍／匯出所有學生時把班級整體觀察放最前面 |
| `--docx` / `--no-docx` | `--docx` 不給也會產生 Word；`--no-docx` 是只要 PDF／HTML 時用 |
| `--pdf` / `--html` | 印一份 PDF（要 Chrome／Chromium／Edge）／連排版好的 HTML 一起留下 |
| `--out 目錄` / `--local` / `--root` | 預設 `exports/`／只讀本機 markdown 絕不連網／資料根目錄 |

`.docx` 用標準庫 `zipfile` 直接寫最小的 OOXML，零第三方套件。`.pdf` 借本機的 Chrome
（`--headless=new --print-to-pdf`）；Chrome 不在預設路徑時用環境變數 **`TRK_CHROME`** 指定執行檔。
**Windows 沒裝 Chrome 就自動改用 Microsoft Edge。** 找不到任何一個就退回 HTML，
並印一行「用瀏覽器開這個檔 → 列印 → 儲存為 PDF」，這不算失敗。
匯出學生時，卡片上的 IEP 目標與個案概念化會排在他的紀錄前面。

## 4.6 `export_records.py`——整包帶走

```bash
python3 scripts/export_records.py --out ~/記錄.md               # 全部匯出成一個檔
python3 scripts/export_records.py --kind students --target S-03 # 只要某一位
python3 scripts/export_records.py --stream case                 # 只要某一種記錄類型
python3 scripts/export_records.py --by-tag                      # 依標籤分組
python3 scripts/export_records.py --related                     # 每則後面附上它關聯到的記錄
python3 scripts/export_records.py --split ~/備份                # 每個對象一個資料夾
python3 scripts/export_records.py --json                        # 輸出 JSON
python3 scripts/export_records.py --local                       # 不連網，只讀本機檔
```

`--id` 是 `--target` 的舊別名。匯出是唯讀的，不會動到雲端資料。
這支腳本的存在本身就是一個承諾：**你的資料隨時可以整包帶走，不會被鎖在這個 kit 裡。**

---

# 5. 資料在哪裡、誰看得到

## 5.1 本機 `data/`（整個 gitignored）

```
data/roster.csv                       代號,姓名,類型 —— 唯一有真名的檔
data/contacts.csv                     （選用）家長信箱
data/students/<代號>/observations.md   homeroom（沿用 v2 檔名）
data/students/<代號>/<類型id>.md        其餘每一種類型各一個檔（qualitative.md、iep.md、soap.md…）
data/students/<代號>/card.json         學生卡：IEP 的 goals[]、SOAP 的 conceptualization
data/class/observations.md            班級整體觀察：homeroom
data/class/<類型id>.md                 其餘每一種 scope:class 類型各一個
data/courses/<課程id>/records.md
data/business/<組id>/records.md
data/ledger.jsonl                     台帳
data/audit.jsonl                      寫入稽核＋同步刪除（op:delete）＋清除雲端原文（op:purge）
data/backups.jsonl                    每次備份的 zip 路徑、md5、Drive file id
data/.sync-state.json                 上次同步的基準
```

一則記錄在 markdown 裡長這樣（欄位列用**全形冒號**，`關聯：` 行用分號分隔）：

```
## 2026-09-10 14:35 #親師 #人際
期限：2026-09-20
辦理情形：辦理中
關聯：students/S-03/2026-09-10; courses/fractions/2026-09-09-1435

正文……（可多段）
```

解析器很寬鬆：任何 `鍵：值` 行都收進 `fields`，就算那個鍵不在設定裡也照收。
這是刻意的——`fields` 只是表單建議，**改欄位名不需要 migration**。檔案**只加不刪**。
所有文字寫入一律 LF 換行（不然兩台機器算出的雜湊會不一樣，同步會一直報「內容不同」）。

## 5.2 雲端（你自己的 Firestore）

```
roster/main                       {students:[{id,name,streams:[類型id…]}], protectedPhrases:[]}
students/{代號}                    每生一張卡
students/{代號}/records/{rid}      每則紀錄，必帶 stream（規則擋著）
class-observations/{rid}          班級整體觀察，同樣帶 stream
courses/{課程id}                   {title,kind,season,weeks,teacherName,order}
courses/{課程id}/records/{rid}
business/{組id}                    {label,fields:[...],tags:[...],custom:bool}
business/{組id}/records/{rid}
meta/config                       設定鏡像（version／dataVersion／tabs／studentStreams）
meta/status                       {lastSyncAt,lastBackupAt,lastSyncConflicts,lastSyncPii,lastError}
```

開了 LINE 交辦（§3.8）才會多出三樣，沒開的話它們根本不存在：

```
headless_events/{事件id}           一則交辦，status: pending→processing→done|failed
headless_pairing/{LINE userId}     配對階段看到過的帳號（配好之後就沒用了）
meta/headless                      {ownerUserId, enabled}＝到底哪一個 LINE 帳號是你
```

語音檔另外存在 Cloud Storage 的 `headless-inbox/`，**不會自動刪**——要清就自己到
Firebase Console 的 Storage 刪。上面這三樣與那個資料夾，規則一樣只認你那一個信箱。

## 5.3 安全規則只認一個信箱

`firestore.rules` 由 `build_config.py` 從 `firestore.rules.tmpl` 產生，
把 `{{OWNER_EMAIL}}` 換成你的信箱。核心那一段：

```
request.auth != null
  && request.auth.token.email == '<你的信箱>'
  && request.auth.token.email_verified == true
  && request.auth.token.firebase.sign_in_provider == 'google.com'
```

不符合的一律 deny，**連預設規則都是 `allow read, write: if false`**。
就算有人拿到網址、看了網頁原始碼、抄走那六個 Firebase 設定值，伺服器一樣不回傳任何一個字。
規則另外擋兩件事：**學生紀錄** `create` 時 `stream` 必填、`update` 不准改 `stream`；
學生與班級紀錄的 `update` 都不准改 `date`——所以一則紀錄的日期歸屬事後無法竄改。
（班級整體觀察沒有「必填 stream」這一條，因為它本來就只有一種。）

## 5.4 絕對不要貼出去的東西

| 絕對不要貼 | 為什麼 |
|---|---|
| **應用程式密碼／App Password**（`KIT_SMTP_APP_PASSWORD` 那一串） | 拿到的人可以用你的身分寄你的信 |
| 任何檔名裡有 `key` 的檔案內容（`*-key.json`、`serviceAccount*.json`）、`.env` | 等於整個專案的鑰匙 |
| 你的 Google 帳號密碼 | 任何人任何理由都不會需要它，包括 AI |
| **LINE 的 Channel secret 與 Channel access token**（開了 §3.8 才有） | 拿到的人可以冒充你的 LINE 官方帳號 |
| **`data/roster.csv`** | 整套系統裡唯一有真名的檔 |
| `exports/` 底下的檔 | 匯出檔與素材包**含名冊真名**（那是給你自己看的） |
| `backups/` 的 zip | 裡面就是 `data/` 全份 |
| `config/kit.json`、`setup/progress.json`、答案檔 | 有你的信箱與專案 ID（答案檔**裝完就刪掉**） |

「絕對不要」的範圍是**任何人**：同事、技術論壇、賣你這套 kit 的人、你在別的地方開的 AI 對話視窗。
唯一的例外是你電腦上正在幫你安裝的那個 AI 代理——即使是它，你也不需要主動把密碼貼給它。

**可以貼、不用緊張的**：Firebase 那六個設定值（本來就會出現在網頁原始碼裡）、錯誤訊息（越完整越好）。
上面那些路徑全部在 `.gitignore` 裡，不會進版本控制；動 git 之前先 `git status` 確認一次。

---

# 6. 升級

## 6.1 現在是哪一版

| 問哪裡 | 怎麼看 |
|---|---|
| 這份程式 | `cat VERSION`（唯一的版本來源），或 `python3 scripts/doctor.py` 第一行 |
| 你的資料庫上次用哪一版同步的 | Firestore 的 `meta/config.version`；`doctor.py` 連得上網時自動抓下來跟本機比 |
| 網頁 | **頁尾直接寫著「版本 `<版本字串>`」**。寫「版本未知」＝設定檔是舊的或手寫的 |

`doctor.py` 的版本比對是**選用項目**（黃色驚嘆號，不擋健檢通過）：程式比資料庫新就提醒你
重新部署規則再同步一次；連不上網或還沒同步過就跳過，不算失敗。
真正會擋下操作的是網頁端的即時偵測——新增或刪除被舊規則擋下來時，
畫面直接顯示「你的安全規則還是舊版，請重新部署」。

## 6.2 更新的做法

`git pull`，或重新下載一份 zip。**只覆蓋程式與範本**：

| 可以覆蓋 | **絕對不要覆蓋** |
|---|---|
| `scripts/`、`site/dashboard.html`、`site/js/*.example.js`、`templates/`、`config/*.example.json`、`config/*.library.json`、`config/verticals.json`、`firestore.rules.tmpl`、`firebase.json`、`AGENTS.md`、`README.md`、`docs/` | `config/kit.json`、`config/tabs.json`、`config/report-format.custom.json`、`data/`、`setup/progress.json`、`firestore.rules`、`site/js/kit-config.js`、`site/js/firebase-config.js`、`backups/`、`inbox/`、`exports/` |

更新後一定要跑（新版的設定產生器可能多產了東西）：

```bash
python3 scripts/build_config.py
python3 scripts/doctor.py
```

**`CHANGELOG.md` 那一版標了「規則有動」的話，還要重新部署規則**：
`firebase deploy --only firestore:rules --project <你的專案ID>`。

版本號的意思：**主版本**（3 → 4）＝資料格式或安全規則不相容，升級要跑 `setup.py --upgrade`
並重新部署規則；**次版本**（3.0 → 3.1）＝新功能、舊資料照用；**修訂**（3.0.0 → 3.0.1）＝修 bug。

## 6.3 從 v2 升級

你手上是 v2（有 `config.yaml`、沒有 `config/kit.json`）的時候走這條。**不要重跑新裝流程。**
跟當初一樣，把資料夾交給你的 AI，說：**「讀 AGENTS.md，幫我升級到 v3。」** 它會做五件事：

1. **只覆蓋程式與範本**（清單同 §6.2）。
2. `python3 scripts/setup.py --upgrade`——把 `config.yaml` 的 `owner_email`、`firebase`、`email`
   轉成 `config/kit.json`，並自動跑 `build_config.py`。
3. **重新部署安全規則（不能省）**：`firebase deploy --only firestore:rules --project <專案ID>`
4. **重新部署網站**：`firebase deploy --only hosting --project <專案ID>`
5. `python3 scripts/sync.py --dry-run` 看一次再 `python3 scripts/sync.py`。

**升級的重點只有一句話：光更新程式不夠，安全規則一定要重新部署一次。**
v3 加了業務記錄的區塊，也改成允許你自己刪除記錄。沒重新部署的話，業務分頁讀不到、
刪除鍵按不動——網頁上會直接告訴你該去部署。

**既有記錄不用搬、不會壞。** 升級**只會自動勾一種**學生記錄類型：`homeroom`，因為 v2 的
`data/students/<代號>/observations.md` 正好就是它的檔名，不勾的話舊觀察在網頁上看不見——
這是「全部勾選、沒有預設」原則唯一的例外。其餘類型與業務分頁都不會替你打開，想要就跟 AI 說一聲，
它問完再重跑一次 `setup.py`（既有記錄一則都不會動）。
驗收：舊的學生記錄與課程記錄**張數一則不少**（自己數一位學生的看看）。

---

# 7. 疑難排解速查表

把錯誤訊息**整段**貼給你的 AI 代理，說「這個怎麼辦」——它讀得懂 `doctor.py` 的每一行輸出。

| # | 症狀 | 原因 | 怎麼修 |
|---|---|---|---|
| 1 | 剛裝完工具，`doctor.py` 還是說「找不到」 | PATH 是開視窗當下讀的 | **關掉終端機、開一個新的**，重跑 `python3 scripts/doctor.py` |
| 2 | **iPhone 上登入後一直跳回未登入** | `authDomain` 是 `.firebaseapp.com`，與網址 `.web.app` 不同源，iOS Safari 的跨網域儲存分區擋掉 | 改 `config/kit.json` 的 `firebase.auth_domain` 成 `<專案ID>.web.app` → `build_config.py` → `firebase deploy --only hosting` |
| 3 | **別的帳號打得開、看得到內容** | 規則沒部署成功，或規則裡的信箱打錯 | **停下所有事先修這個。** `build_config.py` → `firebase deploy --only firestore:rules --project <專案ID>`，再用無痕視窗驗一次 |
| 4 | 網頁說「你的安全規則還是舊版」／刪除鍵按不動／業務分頁讀不到 | 升級後沒重新部署規則 | `firebase deploy --only firestore:rules --project <專案ID>` |
| 5 | 部署被拒（`permission denied`） | `firebase login` 用的帳號跟專案擁有者不是同一個 | `firebase logout` → `firebase login`，登入時選對帳號 |
| 6 | `doctor.py` 的「安全規則比設定新」是 ✗ | 改過設定但沒重跑產生器 | `python3 scripts/build_config.py` 再重新部署 |
| 7 | `build_config.py` 說 `owner_email` 還是範本值 | 信箱沒填進去 | 重跑 `python3 scripts/setup.py` |
| 8 | 網頁停在「還沒有設定檔」／頁尾寫「版本未知」 | `site/js/kit-config.js` 沒被部署上去，或設定檔是舊的 | `python3 scripts/build_config.py` 再 `firebase deploy --only hosting` |
| 9 | `append_record.py` 退出碼 **2** | 旗標本身有問題：`--kind students` 沒帶 `--stream`，或對 `courses`／`business` 帶了 `--stream`，或「目標編號」填了卡片上沒有的 | 照訊息列出來的可用類型／可用目標改；訊息會把清單印出來 |
| 10 | `append_record.py` 退出碼 **3** | `--kind`＋`--target`＋`--stream` 在設定裡不存在（打錯代號、那門課還沒建、那位學生沒被列入這個個案型類型） | 對一次代號；要列入學生就改 `data/roster.csv` 第三欄，或網頁上按「＋ 列入學生」 |
| 11 | `append_record.py` 退出碼 **5** | 正文／欄位／標籤出現名冊上的真名 | 把名字換成代號再寫一次。對象根本不是本班學生才用 `--allow-names`（**會寫進稽核記錄**） |
| 12 | `append_record.py` 退出碼 **6** | 設定裡有這個目標，但本機那個 `.md` 不見了 | 重跑 `python3 scripts/setup.py`（只補缺的、不覆蓋已經有的），再寫一次 |
| 13 | `append_record.py` 退出碼 **9** | 寫入前後的編號對不上；腳本已經把檔案還原了，**什麼都沒寫壞** | 把訊息貼給 AI，重試一次 |
| 14 | `sync.py` 印出「**衝突**」 | 同一則在網頁跟本機都改過 | 它**不覆蓋任何一邊**。打開那個檔案跟網頁比對，決定留哪一邊，改完再跑一次 |
| 15 | 網頁頂端「上次同步 X 天前」**變紅字** | 排程沒跑成功（電腦沒開機、權限被擋、學校電腦鎖住排程） | 先手動 `python3 scripts/sync.py` 確認手動是好的，再 `python3 scripts/schedule.py --status` |
| 16 | 網頁頂端出現**琥珀色**「尚未寫回電腦」 | 上次同步有衝突或真名攔截，那幾則還留在雲端 | 跟 AI 說「幫我看同步擋下了什麼」，逐則處理 |
| 17 | **Windows：工作排程器裡工作明明在，卻永遠沒跑、也沒有錯誤訊息** | 排到 Microsoft Store 的 python 假殼 | `schedule.py` 安裝前會偵測並拒絕；已經裝歪就裝 python.org 版 Python（勾 Add to PATH），重開終端機、重掛排程 |
| 18 | **Windows：`whisper-cli.exe` 在，一跑就退出碼 `0xC0000135`** | 缺 VC++ 執行階段（`vcruntime140.dll` 與 `vcruntime140_1.dll` **兩個都要**） | `py -3 scripts\install_tools.py`（它會先裝 `Microsoft.VCRedist.2015+.x64` 再真的跑一次驗證） |
| 19 | **Windows：轉錄說找不到檔，看起來像「這個錄音壞了」** | 使用者名稱是中文 → `%TEMP%` 是非 ASCII 路徑，`whisper-cli.exe` 吃窄字元 argv | 程式已經改放 `%LOCALAPPDATA%\teacher-records-kit\work`（再不行退到 `C:\ProgramData\…`）。還是不行就把訊息貼給 AI |
| 20 | 轉錄卡住／語音模型下載失敗 | 網路，或 VAD 模型抓不到 | 重跑 `python3 scripts/transcribe.py --inbox`（已經轉過的不會重轉）；真的下不到 VAD 模型就加 `--no-vad` |
| 21 | 匯出 PDF 失敗 | 機器上找不到 Chrome／Chromium／Edge | **不算失敗**：會留下排版好的 `.html`，用瀏覽器開 → 列印 → 儲存為 PDF。Chrome 不在預設路徑就設環境變數 `TRK_CHROME` |
| 22 | `doctor.py` 說「Drive 備份資料夾」✗（desktop 模式） | 桌面程式沒登入，或資料夾名打錯（**中文全形空格是常見兇手**） | 照 `doctor.py` 列出來的候選路徑對一次，填回 `drive.desktop_dir`，重跑 `build_config.py` |
| 23 | gws 模式找不到備份資料夾 | 資料夾 ID 貼錯，或資料夾被丟進垃圾桶 | 腳本會**停手，不會自己建一個新的**。重新確認 ID、確認 `trashed` 不是 true |
| 24 | `gcloud`／`firebase`／`gws` 在 PowerShell 打得到，Python 裡說找不到 | `.cmd` 包裝，或剛裝完 PATH 沒更新 | 腳本內部一律經 `hostos.exe()` 處理；仍然不行就重開終端機 |
| 25 | `parent_email.py` 回**退出碼 126** | Windows 上 `.cmd` 的參數含 `& \| < > ^ %` 或換行，會被 `cmd.exe` 重新解析 | 把 `config/kit.json` 的 `email.method` 改成 `smtp` |
| 26 | `doctor.py` 警告「kit 放的位置」 | repo 放在 OneDrive 底下，或路徑超過 260 字 | 搬到 `C:\Users\<名字>\teacher-records-kit` 這種短路徑、OneDrive 外面 |
| 27 | 「gcloud 已登入」✗ | 沒登入或沒裝 gcloud | `gcloud auth login`，用你當初開 Firebase 專案的那個 Google 帳號 |
| 28 | 在 LINE／FB 裡點連結打不開 Google 登入 | App 內建瀏覽器擋的 | 用 Safari／Chrome 打開，並把網址加到手機主畫面 |
| 29 | `ledger.py --check` 退出碼 1 | 三處對不上 | 看它印的不一致清單（本機有網站無／網站有本機無／內容不同／備份缺哪些），先跑 `sync.py --dry-run` 看能不能補上 |
| 30 | 期末素材包跑出來是空的 | 那位學生在那個格式吃的記錄類型底下一則都還沒有 | 素材包照樣會生出來、只是標成缺漏。先補記一則再跑；格式與記錄類型對不上時腳本會直接印出可用的類型 |
| 31 | **LINE 傳出去完全沒有任何回應** | 雲端那支程式沒部署、Webhook URL 沒貼、或「Use webhook」沒打開 | 依序：`firebase deploy --only functions:line-relay --project <專案ID>` → 把它印出來的網址貼回 LINE Developers 的 Messaging API 分頁 → 打開 Use webhook。順便確認「自動回覆訊息」是關的（沒關的話你收到的是 LINE 的罐頭回覆） |
| 32 | **一直收到「配對碼：Uxxxx…」** | 配對碼填了但沒送上雲端 | 把碼填進 `config/kit.json` 的 `headless.line.owner_user_id` → `python3 scripts/build_config.py` → `python3 scripts/headless.py --once` |
| 33 | **收到「收到了」，但第二則回報永遠不來** | 電腦沒醒著、排程沒跑，或兩個 LINE 金鑰的環境變數排程讀不到 | 依序：`python3 scripts/headless.py --status` → `--once` 手動催一次 → `python3 scripts/schedule.py --status` → `python3 scripts/doctor.py` 看無頭那五項。金鑰要寫進 `~/.zshrc` 或 Windows 使用者環境變數，臨時 `export` 排程看不到 |
| 34 | **紀錄寫進去了，但手機沒收到回報** | LINE 推播額度用完（免費方案每月 200 則），或 token 讀不到 | 紀錄是好的，不用重跑。額度看 LINE Official Account Manager；要換 token 就重設環境變數與 `firebase functions:secrets:set` |
| 35 | 部署時整批失敗，錯誤訊息看不出是哪一項 | 跑了無參數的 `firebase deploy` | **一律帶 `--only`**：`--only firestore:rules`、`--only hosting`、`--only storage`、`--only functions:line-relay`，一項一項來 |

---

# 8. 附錄

## 附錄 A：所有腳本一覽

| 腳本 | 一行用途 | 最常用的旗標 |
|---|---|---|
| `scripts/setup.py` | 安裝精靈：問完 → 寫設定 → 建資料骨架 → 產生網頁設定與規則 → 健檢 | `--answers 檔`、`--resume`、`--upgrade`、`--mark-step N [--note 文字]`、`--skip-network`、`--skip-doctor` |
| `scripts/build_config.py` | 唯一的設定產生器：設定與範本進，四個檔出（本機模式只出一個） | `--check`、`--quiet`、`--allow-placeholders`（測試用） |
| `scripts/doctor.py` | 健檢：逐項告訴你什麼好了、沒好的怎麼修 | `--json`、`--skip-network` |
| `scripts/install_tools.py` | 裝齊外部工具，三個平台同一支 | `--dry-run`、`--agent claude\|codex\|gemini`、`--with-gws`、`--json`、`--remove-portable` |
| `scripts/append_record.py` | **唯一被允許寫入記錄檔的通道** | `--kind`、`--target`、`--stream`、`--content-file`、`--fields-json`、`--tags`、`--related`、`--source`、`--sync`、`--json` |
| `scripts/sync.py` | 本機 markdown ⇄ Firestore 雙向同步（衝突不覆蓋） | `--dry-run`、`--only 種類/代號`、`--quiet` |
| `scripts/transcribe.py` | 錄音 → 本機逐字稿（不出本機） | `--inbox`、`--keep`、`--lang`、`--model`、`--no-vad` |
| `scripts/backup.py` | 本機 zip ＋ 上你自己的 Google 雲端硬碟 | `--local-only`、`--no-export`、`--quiet` |
| `scripts/ledger.py` | 台帳：本機／網站／備份三處對帳 | `--rebuild`、`--check`、`--offline`、`--json`、`--quiet` |
| `scripts/report_pack.py` | 期末素材包＋草稿指令（**不寫評語、不呼叫 AI**） | `--format`、`--target`、`--all`、`--stream`、`--from`／`--to`、`--out`、`--local` |
| `scripts/export_docs.py` | 一鍵匯出 Word（`.docx`）與 PDF | `--kind`、`--target`、`--stream`、`--with-class`、`--docx`／`--no-docx`、`--pdf`、`--html`、`--out`、`--local` |
| `scripts/export_records.py` | 整包匯出（期末取材、換系統） | `--kind`、`--target`／`--id`、`--stream`、`--by-tag`、`--related`、`--split`、`--out`、`--json`、`--local` |
| `scripts/headless.py` | （選用）收 LINE 交辦：取件 → 轉逐字稿 → 叫 AI 代理 → 寫入 → 推播回報 | `--once`、`--dry-run`、`--status`、`--json`、`--retry 事件id`、`--pair`、`--quiet` |
| `scripts/schedule.py` | （選用）每日同步、每週備份、每 5 分鐘收 LINE 交辦的排程，三個平台同一支 | `--dry-run`、`--status`、`--print-cron`、`--uninstall`、`--sync-time`、`--backup-day`、`--backup-time` |
| `scripts/monthly_reminder.py` | （選用）本月未記名單寄給你自己 | `--dry-run`、`--month` |
| `scripts/parent_email.py` | （選用）把一則改寫稿寄給家長 | `--id`、`--date`、`--subject`、`--body-file`、`--dry-run`、`--draft` |
| `scripts/pending.py` | （選用）列出還沒決定要不要寄家長的記錄 | `--all`、`--mark 代號 日期 狀態` |
| `scripts/build_preview.py` | 產生單檔離線預覽（給人看示範用） | `--dashboard`、`--config`、`--out` |
| `scripts/hostos.py` | 平台差異只寫在這一支（不單獨執行） | — |
| `scripts/lib.py` | 共用底層（不單獨執行） | — |

除了 `monthly_reminder.py`、`parent_email.py`、`install_tools.py`、`schedule.py`、`build_preview.py`，
其餘都吃 `--root 目錄`（資料根目錄，測試或多帳號才要指定）。

## 附錄 B：答案檔（`answers.json`）欄位速查

免互動安裝用：`python3 scripts/setup.py --answers /tmp/answers.json`。
範本＝`templates/answers.example.json`（每個欄位都有 `_註解_` 說明）。
**裡面有你的信箱與專案 ID，裝完就刪掉。**

| 鍵 | 型別 | 說明 |
|---|---|---|
| `mode` | 字串 | `"cloud"`（預設，要 Firebase）或 `"local"`（只放這台電腦，下面整個 `firebase` 區塊都不用填）。沒寫這個鍵一律當 `cloud` |
| `owner_email` | 字串 | 你的 Google 信箱。只有這個帳號讀寫得到你的資料 |
| `co_owner_emails` | 清單 | 選填。共同擁有者的 Google 信箱，權限跟 `owner_email` 一樣（代管、第二個帳號）。沒有就 `[]`；改了要重跑 `build_config.py` 並重新部署規則 |
| `id_prefix` | 字串 | 學生代號前綴，預設 `S`（代號長成 `S-01`） |
| `vertical` | 字串 | 三個方案 id 之一，或 `"none"`。只是標記，不會替你勾任何一項 |
| `firebase.project_id` | 字串 | Console 網址 `/project/` 後面那一段 |
| `firebase.api_key` | 字串 | Config 六個值之一 |
| `firebase.auth_domain` | 字串 | **留空即可**——會自動填 `<project_id>.web.app`。網站掛在別的網域才填 |
| `firebase.storage_bucket` / `messaging_sender_id` / `app_id` | 字串 | Config 六個值之一 |
| `students.enabled` | 布林 | 要不要學生分頁 |
| `students.count` | 整數 | 班級人數，代號自動生成 `S-01`…`S-NN`（也可改用 `students.ids` 明列） |
| `students.streams` | 陣列 | 勾選的記錄類型 id（`qualitative`／`homeroom`／`subject`／`case`／`iep`／`soap`）。**零預設** |
| `students.extra_fields` | 物件 | `{類型id: [{name, type, options}]}`，那一種你自己要加的欄位 |
| `students.extra_tags` | 物件 | `{類型id: ["#標籤"]}` |
| `students.custom_streams` | 陣列 | 清單外的類型（`id`／`label`／`desc`／`scope`／`fields`／`tags`） |
| `students.members` | 物件 | `{類型id: ["S-02"]}`，個案型類型列入哪些學生（寫進名冊第三欄） |
| `students.cards` | 物件 | `{代號: {goals: [...], conceptualization: {...}}}`。已有內容的那一塊重跑安裝不覆蓋 |
| `courses.enabled` / `courses.list` | 布林／陣列 | 每門課 `{id, title, kind}`；`id` 只能用英數、連字號與底線 |
| `business.enabled` | 布林 | 要不要業務分頁 |
| `business.groups` | 陣列 | 勾選的業務組 id。**零預設** |
| `business.extra_fields` / `extra_tags` | 物件 | 同學生那兩個 |
| `business.custom_groups` | 陣列 | 清單外的業務組（`id`／`label`／`desc`／`fields`／`tags`／`relate_students`） |
| `drive.mode` | 字串 | `desktop`（預設）或 `gws` |
| `drive.desktop_dir` | 字串 | desktop 模式：Google 雲端硬碟同步夾裡那個資料夾的完整路徑 |
| `drive.backup_folder_id` | 字串 | gws 模式：Drive 資料夾 ID |
| `drive.keep_backups` | 整數 | 本機保留幾份 zip（預設 12） |
| `email.method` / `email.smtp_user` | 字串 | 選用。密碼放環境變數 `KIT_SMTP_APP_PASSWORD`，**不寫進檔案** |
| `headless.enabled` | 布林 | 選用，預設 `false`。要用 LINE 交辦（§3.8）才開；本機模式開了會直接報錯 |
| `headless.agent` | 字串 | `claude`／`codex`／`gemini`，收到交辦時要叫哪一支 |
| `headless.timeout_sec` | 整數 | 一則交辦最多讓代理跑多久（預設 1800，最小 60） |
| `headless.line.owner_user_id` | 字串 | 你的 LINE `userId`（＝配對碼）。填錯的人傳訊息會被靜靜丟掉 |
| `headless.line.channel_secret_env` / `channel_token_env` | 字串 | **不是答案檔的鍵**，只在 `config/kit.json` 裡設：放金鑰的**環境變數名字**，預設 `KIT_LINE_CHANNEL_SECRET`／`KIT_LINE_CHANNEL_TOKEN`。金鑰本身永遠不進任何檔案 |

## 附錄 C：三個垂直方案的建議清單與記錄類型

`setup.py` 會把這一行**唸出來**，然後一項都不預先勾。正本＝`config/verticals.json` 的 `suggest`。

| 方案 | 建議記錄類型 | 建議業務組 | 建議期末格式 |
|---|---|---|---|
| ① `qualitative-assessment` 實驗教育／私校：質性評量自動化 | `qualitative`、`subject` | `homeroom`、`parent_comm`、`meetings` | `waldorf-homeroom` |
| ② `iep-tracking` 特教／早療：IEP 目標追蹤 | `iep`、`homeroom` | `special_ed`、`meetings`、`parent_comm` | `iep-tracking` |
| ③ `soap-casework` 諮商／教練／社工：SOAP 個案紀錄 | `soap`、`case` | `guidance`、`meetings` | `case-summary` |

學生記錄類型的完整清單（正本＝`config/student-streams.library.json`）：

| id | 名稱 | 範圍 | 固定欄位 |
|---|---|---|---|
| `qualitative` | 質性評量觀察（不打分數） | 全班每一位 | 面向（複選）、報告維度、課程、證據來源、指標 |
| `homeroom` | 導師班級學生紀錄 | 全班每一位 | （無固定欄位） |
| `subject` | 任課老師學生紀錄 | 全班每一位 | 科目、觀察向度、證據來源 |
| `case` | 個案追蹤（通用） | 只有列入的學生 | 來源、主訴／議題、處遇／介入、追蹤與下次 |
| `iep` | IEP／早療目標追蹤 | 只有列入的學生 | 目標編號、達成情形、證據、支持策略、下一步、會議決議 |
| `soap` | 會談紀錄（SOAP） | 只有列入的學生 | 會談次數、會談形式、S 主觀、O 客觀、A 評估、P 計畫、風險評估、下次時間 |
| `custom` | 清單外的自己開一種 | 你決定 | 你決定（AI 問四件事） |

`soap` 的舊 id 是 `counseling`，靠 `aliases` 相容，檔名仍照舊 id 走，資料不必搬。

## 附錄 D：業務組庫十一組

正本＝`config/business-groups.library.json`；人讀版＝`docs/BUSINESS-GROUPS.md`。

| # | id | 組名 | 固定欄位 | 常用分類詞（部分） |
|---|---|---|---|---|
| 1 | `homeroom` | 導師班務 | 學生/對象、事件、處理、後續 | #親師溝通 #聯絡簿 #班親會 #出缺席 #獎懲 #班費 #營養午餐 |
| 2 | `guidance` | 輔導／個案追蹤 | 個案代號、來源、主訴/議題、晤談摘要、評估、處遇/介入、追蹤與下次 | #初談 #個別晤談 #團體 #家長晤談 #轉介 #通報 #結案 |
| 3 | `special_ed` | 特教／IEP | 個案代號、目標、觀察、調整/支持、會議決議 | #IEP #鑑定 #巡迴 #資源班 #個案會議 #轉銜 |
| 4 | `academic` | 教務 | 事項、期限、狀態、備註 | #課程計畫 #課表 #成績/評量 #教科書 #補救教學 #公開授課 |
| 5 | `student_affairs` | 學務 | （無） | #生活教育 #衛生保健 #體育活動 #校外教學 #防災演練 #安全事件 |
| 6 | `general_affairs` | 總務 | （無） | #設備報修 #採購 #經費/請款 #場地借用 #財產盤點 |
| 7 | `paperwork` | 公文／行政流程 | 公文字號/來源、主旨、承辦、期限、辦理情形 | #公文 #簽呈 #調查表 #計畫申請 #成果報告 |
| 8 | `meetings` | 會議紀錄 | 會議名稱、出席、決議、待辦 | #校務會議 #教師晨會 #年段會議 #課發會 #個案會議 #IEP會議 |
| 9 | `pd` | 研習／專業成長 | （無） | #研習 #共備 #觀議課 #讀書會 #證照/時數 |
| 10 | `parent_comm` | 家長／社區 | （無） | #家長會 #志工 #社區活動 #捐贈 |
| 11 | `personal` | 個人待辦／雜項 | 事項、期限、狀態 | #待辦 #請假 #報帳 #備忘 |

清單外的走第十二個選項 `custom`（AI 問四件事：組名、固定欄位、分類詞、要不要接學生／課程）。

**欄位是建議，不是規格。** 你之後在記錄檔裡多寫一行「承辦人分機：2317」，
解析器照樣把它收進那一則的 `fields`，不用改設定、不用搬資料。

**兩邊怎麼分工**：跟著**某一個孩子**走的紀錄放學生記錄的記錄類型（`case`／`iep`／`soap`）；
**校務層次**的事——個案會議、通報、特教鑑定的行政流程——放業務這一頁的
「輔導／個案追蹤」「特教／IEP」組，兩邊用「關聯」接起來。
期末的 `report_pack.py` 取材的是**學生記錄那一邊**，業務組的紀錄不會進素材包。

## 附錄 E：還沒定案與還沒實測的

**產品上還沒定案的**（repo 裡標成 `[[待確認`）：支援聯絡方式
（`site/dashboard.html` 頁尾），以及**業務組與學生記錄類型清單由 David 逐條校對**
（`docs/BUSINESS-GROUPS.md`、`docs/DATA-CHECKLIST.md`）。那兩份清單是依台灣中小學處室分工與
輔導／特教實務整理的，出自一般校務常識，**尚未經現場逐條校對**。
用起來覺得哪一組不對、少了什麼，直接跟 AI 說，改設定就好——不用改程式，也不用搬資料。

**工程上還沒實測的**。這張表只寫「驗到哪裡」，不寫「應該沒問題」：

| 項目 | 現況 |
|---|---|
| 單元測試 | 268 項，macOS／Ubuntu／Windows 三個平台的 CI 每次推送都跑 |
| **連網路徑**（同步、安全規則、備份、對帳、LINE 交辦的電腦端） | 在 **Firestore 模擬器**（真的 Firestore 引擎）上把老師會走到的路全部走過一遍。**還沒有對真的雲端專案跑過**——作者帳號的 GCP 專案配額已滿，建不了測試專案 |
| **Windows** | **只有 CI 的 `windows-latest` 真機**：可攜工具下載、排程掛上／拆掉、免互動安裝、離線健檢、Edge 印 PDF。**尚未有真人老師在 Windows 上完整裝過一次**——第一位 Windows 使用者就是第一次實測，遇到怪狀先當是我們的問題 |
| **Windows 的 `setup/bootstrap.ps1`** | CI 跑過 dry-run 與真跑。**沒有任何人真的用手按過那顆 `bootstrap.cmd`** |
| **本機模式** | CI 有一支專門的 job：免互動裝一整套本機模式，驗不產規則檔、同步是 no-op、排程只掛備份、健檢項目一項不少 |
| **LINE 交辦的雲端那一半**（`functions/line-relay`） | **從來沒有部署到真的專案過**：沒有真的 Messaging API 頻道、沒有真的 webhook、沒有真的簽章驗證、一則推播都沒有真的送出去過。repo 裡只有靜態把關與模擬器上的文字那條路 |
| **LINE 交辦的語音那條路** | **完全沒跑過**：存進 Firebase 的 Storage、抓回本機、在無頭狀態下轉逐字稿，一項都沒驗 |
| **真的 AI 代理跑無頭交辦** | 沒有。測試與 CI 一律走假代理（`TRK_HEADLESS_AGENT_CMD`），**永不呼叫真的模型** |
| **錄音轉逐字稿** | CI 只驗到 `whisper-cli` 裝得起來、叫得動。repo 裡沒有轉錄的自動化測試，實際轉錄只用測試音檔跑過 |
| **Windows on ARM** | 一切都能用，只有本機語音轉逐字稿（whisper.cpp）沒有官方預編譯檔 |
| **Linux** | 盡力支援；CI `ubuntu-latest`，gcloud 要自己照官方說明裝 |
| **WSL** | 不支援，腳本直接拒跑 |

**所以，如果你是第一批使用者**：雲端模式的文字路徑（網頁、同步、備份、匯出、期末素材包）
是驗得最紮實的一條；本機模式次之；**LINE 交辦要當成 beta**——它的每一行程式都有測試看著，
但它從來沒有真的在網際網路上跑過一次。開了之後第一週請自己對一下
`data/headless-audit.jsonl` 與實際寫進去的紀錄。

版本狀態：`3.0.0-alpha.4`，`CHANGELOG.md` 上 alpha.1 到 alpha.4 都標著「尚未發行」。
每一版改了什麼、哪一版動過安全規則，一律以 `CHANGELOG.md` 為準。
