# 變更紀錄（Changelog）

版本號照 [語意化版本](https://semver.org/lang/zh-TW/)：`主版本.次版本.修訂`。
- **主版本**（3 → 4）：資料格式或安全規則不相容，升級一定要跑 `setup.py --upgrade` 並重新部署規則。
- **次版本**（3.0 → 3.1）：新功能，舊資料照用；升級＝拉新程式＋`build_config.py`＋（若規則有動）重新部署。
- **修訂**（3.0.0 → 3.0.1）：修 bug，只換檔案。

每次發版：改 `VERSION`、在本檔加一段、`git tag v<版本>`。`VERSION` 是唯一的版本來源：
`build_config.py` 把它寫進 `window.KIT.version`（網頁顯示用）、`doctor.py` 開頭印它、
`sync.py` 把它寫進 Firestore `meta/config.version`（＝這個資料庫最後一次是哪一版同步／部署的），
`doctor.py` 連得上網時會拿兩邊比對，程式比資料庫新就提醒重新部署規則。

## v3.0.0-alpha.5 — 2026-09-13（尚未發行）

> **規則有動——要重新部署 `firestore.rules`（與啟用無頭時的 `storage.rules`）。**
> 升級步驟：`python3 scripts/build_config.py` → `firebase deploy --only firestore:rules --project <專案ID>`。

### 共同擁有者 `co_owner_emails`

- `config/kit.json` 多一個選填欄位 `co_owner_emails`（清單，預設 `[]`）。清單裡的 Google 帳號
  跟 `owner_email` 權限完全一樣：安全規則放行、網頁登得進去、匯出與同步的資料都看得到。
  用途＝請人代管紀錄、或老師自己有第二個帳號。**不是分權**：這套設計仍是「擁有者本人」。
- 規則樣板的判斷從 `email == '...'` 改成 `email in ['...', '...']`；每個信箱一樣走
  `EMAIL_RE` 嚴格驗證＋`_rules_literal` 跳脫（惡意字串進清單一樣擋，不是清單也擋）。
  沒填共同擁有者的話規則裡只有一個人，行為跟 alpha.4 一致。
- `build_config.py` 另外輸出 `window.KIT.ownerEmails` 與 `window.OWNER_EMAILS`；
  `dashboard.html` 與 `dashboard-nav.js` 改查清單；`doctor.py` 檢查清單裡每個信箱都在規則檔裡；
  `setup.py --answers` 可帶 `co_owner_emails`（安裝精靈不問這題）。
- 已知：`monthly_reminder.py` 的月報仍只寄給 `owner_email`。

## v3.0.0-alpha.4 — 2026-09-12（尚未發行）

> **規則有動——要重新部署 `firestore.rules`（與啟用無頭時的 `storage.rules`、`functions`）。**
> 升級步驟：`python3 scripts/build_config.py` → `firebase deploy --only firestore:rules --project <專案ID>`。
> 這一版的 `firestore.rules.tmpl` 多了 `headless_events`、`headless_pairing` 兩個集合，
> 而且規則裡的信箱改成「一律轉小寫＋跳脫後才插進去」，字面值跟舊的不一樣——沒重新部署的話，
> 無頭交辦的紀錄擁有者自己也讀不到。另外新增了 `storage.rules`（沒開無頭交辦時它是整份拒絕）。
> **部署一律帶 `--only`**，不要跑無參數的 `firebase deploy`：那會連 hosting、storage、functions
> 一起送，其中一項沒設好就整批失敗，而且錯誤訊息指不到真正的原因。

### 安裝：從一台什麼都沒裝的電腦開始

- **多了一層 bootstrap**。在這一版之前，`install_tools.py` 有三個隱含前提：電腦上已經有 Python、
  已經有 Homebrew／winget、而且老師已經有一個 AI 代理。現在這三件事它自己處理：
  - `setup/bootstrap.sh`（macOS／Linux，只要 bash 與 curl）：Xcode 命令列工具 → Homebrew
    （含 `~/.zprofile`／`~/.bash_profile` 的 shellenv，Apple Silicon 與 Intel 路徑都認）→
    git／Python／Node.js（夠新的跳過）→ AI 代理 CLI → 回頭跑 `install_tools.py` 與 `doctor.py`。
  - `setup/bootstrap.ps1` ＋ **按兩下就會跑的 `setup/bootstrap.cmd`**（Windows 原生，PowerShell 5.1 以上）：
    winget 在不在 → git／Python／Node.js（Microsoft Store 的 python 假殼用退出碼 9009 認出來、
    winget 的「已經裝好了」當成功）→ 每裝完一項從登錄檔重讀 PATH → AI 代理 CLI → `py -3` 接手。
  - 兩支都吃 `--dry-run`／`-DryRun`（印出每一步會跑什麼、**一個字都不裝**）與 `--yes`／`-Yes`；
    失敗哲學與 `install_tools.py` 相同：不重試、不留半套，印官方網址繼續往下走。
  - 最後印出老師真正要做的三件事：**開一個新終端機視窗、`cd` 到資料夾、
    貼 `claude "請完整讀 AGENTS.md，然後帶我從步驟 0 開始安裝"`**（codex／gemini 各有自己的那一行）。
- **AI 代理的 CLI 也由 kit 裝**：新增 `hostos.AGENT_CLIS`（claude／codex／gemini，
  每個平台的安裝方式、備案、啟動指令、起手提示詞與無頭叫法都在這張表裡），
  `install_tools.py --agent claude|codex|gemini`（已經有 Python 的電腦不必走 bootstrap，`--json` 也會回報），
  `doctor.py` 多一行「AI 代理的 CLI」告訴你這台電腦找得到哪幾支（**只是報告，不是必要項目**）。
- **平台事實仍然只住兩處**（`scripts/hostos.py` 與 `docs/PLATFORMS.md`），
  bootstrap 那兩支 shell 腳本是**唯一被記錄在案的例外**——Python 還沒裝好，讀不到 `hostos.py`，
  所以它們是那張表的手抄本。`scripts/tests/test_platform.py` 新增 `Bootstrap` 一組測試對帳：
  表裡每一家在每個平台要裝的東西（含備案）都必須出現在對應的腳本裡，漂掉就紅。
- 安裝步驟從 0–10 變成 **0–11**（第 11 步是選用的無頭交辦）；`setup/progress.example.json`、
  `setup.py` 的 `STEP_TITLES`、`AGENTS.md`、`INSTALL.md` 一起對齊。

### 兩個新選項

這兩個都是**選用**的，不選就跟以前一模一樣。

- **本機模式（`mode: "local"`）——不上雲端也裝得起來。** 安裝精靈的**第 2 步第一句**就問
  「你的紀錄要放哪裡」：`cloud`（預設，跟以前一樣）或 `local`。選 `local` 的話：
  沒有 Firebase 專案、沒有六個設定值、沒有手機網頁、沒有同步、沒有帳單，紀錄只在 `data/**/*.md`。
  錄音轉逐字稿、Word／PDF 匯出、期末素材包、家長信、Drive 備份**全部照用**。
  - `build_config.py` 在本機模式**只產 `site/js/kit-config.js`**，不產 `firestore.rules`、
    `storage.rules`、`site/js/firebase-config.js`（以前留下來的舊產生檔會提醒，但**不刪**）。
  - `sync.py` 印一行說明就 `return`（退出碼 0，排程與 `append_record --sync` 都叫得動它）；
    `ledger.py` 自動只比對本機與備份兩處；`schedule.py` 只掛備份那一支；
    `doctor.py` **保留每一個檢查項目的 key，只是標成 `skipped`**（不是刪掉、不是 ✗——
    CI 與 AI 代理靠固定 key 清單判斷，項目消失會被誤判成健檢壞了），`--json` 頂層多出 `mode` 與 `headless`。
  - **之後要改成 cloud**：把 `config/kit.json` 的 `mode` 改成 `"cloud"`（或重跑一次安裝精靈）→
    `setup.py` 問那六個值 → `build_config.py` → 部署規則與 hosting → 第一次 `sync.py` 把既有紀錄
    全部推上去。**既有紀錄一則都不會動。**
- **無頭交辦（LINE）——在外面用手機講一句話，回家紀錄已經寫好了。** 只有 cloud 模式能開。
  ```
  手機 LINE → Cloud Functions 的 line-relay → Firestore headless_events
           → 本機 headless.py（每 5 分鐘）→ AI 代理 CLI → append_record.py → LINE 推播回報
  ```
  - 新增 `functions/line-relay`（Cloud Functions v2、`asia-east1`、Node 20、只有
    `firebase-admin` 與 `firebase-functions` 兩個相依）：驗 `x-line-signature`
    （`crypto.timingSafeEqual`，對 `req.rawBody` 算 HMAC-SHA256），把事件寫進
    `headless_events/{webhookEventId}`（用 `create()` 不用 `set()`——LINE 重送就撞
    `ALREADY_EXISTS` 變成 no-op，天然去重），語音存進 Storage 的 `headless-inbox/<messageId>.m4a`，
    然後**只回一句**「收到了，電腦醒著時會處理」。
  - 新增 `scripts/headless.py`：`--once`（排程跑的就是它）、`--dry-run`、`--status`、`--json`、
    `--pair`、`--retry <事件id>`、`--quiet`。取件用前置條件 PATCH 認領（兩台電腦同時跑也不會重複處理）、
    語音走本機 whisper、把 `AGENTS-HEADLESS.md` 整份內嵌進提示詞丟給代理、要求代理回
    `<<REPORT>>…<<END>>`（**沒有這段就算失敗**，rc 0 也不算成功），最後推一則回報並寫
    `data/headless-audit.jsonl`。
  - **不自動重試**：失敗就停在 `failed`，等老師自己 `--retry`。自動重試最糟的情況是同一句話
    被寫成三則紀錄，而老師得自己找出來刪掉。
  - **一則交辦只推播一次**（不推「開始處理了」「轉逐字稿完成了」）——LINE 免費方案每個帳號
    每月只有 200 則推播。HTTP 429 會被翻成「推播額度用完了」。
  - 電腦睡著或關機：訊息就排在 Firestore 裡，一則都不會掉；電腦醒來五分鐘內補完，每一則各推一次回報。
    macOS 的排程刻意用 `StartInterval: 300` 而不是 `StartCalendarInterval`（後者睡醒不補跑）。
  - 配對碼**就是老師自己的 LINE `userId`**：還沒配對前 relay 對任何人都回配對碼（那是老師唯一
    拿得到自己 id 的辦法），配好之後不合的 `userId` 一律**靜默丟掉、不回任何話**。
  - 金鑰只住兩個地方：雲端走 Functions 的 `defineSecret`（`KIT_LINE_CHANNEL_SECRET`／
    `KIT_LINE_CHANNEL_TOKEN`），本機走環境變數。`config/kit.json` 只存**變數名稱**，
    有一條測試守著「金鑰本身永遠不進任何檔案」。
  - **需要 Firebase Blaze（綁信用卡）**——Cloud Functions 在免費的 Spark 方案上不會跑。
    實際用量幾乎一定是 0 元，文件建議設一個 1 美元的預算提醒。
  - `schedule.py` 從固定兩支變成 `wanted_jobs()` 決定的 1–3 支：`backup`（一定有）、
    `sync`（只有 cloud）、`headless`（只有開了才掛，每 5 分鐘）。
  - `doctor.py` 新增無頭交辦五項（開關與逾時、兩個環境變數讀不讀得到、配對碼填了沒、
    代理 CLI 找不找得到、雲端 `meta/headless` 對不對得上），沒開就只留一行「關著」，不吵人。
  - 新增 `AGENTS-HEADLESS.md`＝無頭代理的行為守則（只走 `append_record.py`、只用代號、不問問題、
    不確定就回報「我沒有寫入」），由 `headless.py` 整份內嵌進提示詞——無頭代理不保證會去讀檔案。

### 修正

四輪對抗式審查抓出來的，將近五十處。

**同步與資料**

- `sync.py` 的同步狀態把「其實沒推上去」的 rid 也記成已同步：被真名閘攔下、被前置條件擋下的那幾則，
  下一輪會被判成「網頁刪掉了」→ **把老師本機的紀錄區塊刪掉**。現在只記 PATCH 真的成功的 rid，
  `--dry-run` 那條路也不再汙染狀態。
- `sync.py --dry-run` 提早 return，卡片摘要那段預演訊息印不出來（抽出 `accumulate_card()`，兩條路都跑）。
- 學生卡片**第一次同步永遠報衝突**：基準線是空字串，跟雲端的「空卡片」指紋永遠不相等，
  IEP 目標與個案概念化從來上不去。現在拿空卡片的指紋來比：雲端空就推上去、本機空就寫回來。
- **同一天兩種記錄類型會撞紀錄 id**：rid 只在單一 md 檔內唯一，雲端卻是同一位學生所有類型共用一個集合。
  取號時改成連同集合裡的兄弟檔一起避開；明確指定 `--time` 撞到的話直接擋下並說明撞到哪一個集合。
  同步的 409 訊息也補上這個可能原因。
- 欄位值含換行會變成正文的一部分（回讀少一個欄位、雜湊跟著變）→ 寫入前擋下並建議改用全形分號或 `--content-file`。
- 唯一走 `os.write` 的附加通道在 Windows 會把 `\n` 變成 `\r\n` → 補 `O_BINARY`。
- 備份檔名戳記只到分鐘，同一分鐘跑兩次會蓋掉前一份 → 補到秒。
- **雲端備份失敗、同步有衝突，網頁狀態列照樣綠燈**：現在 `meta/status` 多寫
  `lastSyncConflicts`／`lastSyncPii`／`lastError`，備份失敗也把原因寫上去。
- `ledger.py --check` 不管有沒有真的比到網站與備份都印「三處對得上」→ 改成只有三處都比過才那樣說，
  否則印出這次比了哪幾處、漏了哪幾處。
- 名冊代號沒有正規化：老師手打的 `S-1` 與程式產的 `S-01` 被當成兩個人，姓名對不上，
  真名閘與網頁顯示會靜默漏人；重複代號還會靜默覆蓋＝少一位學生。現在一律補零對齊，重複代號直接報第幾列。
- 寫回 `data/roster.csv` 會把老師自己加的第四欄以後（學號、性別、家長信箱）洗掉 → 原樣保留；
  另外輸出改成帶 BOM，zh-TW 版 Excel 打開不再是亂碼。
- 記事本／Excel 存出的 JSON 與 md 帶 BOM，讀第一個字元就炸 → 一律 `utf-8-sig`。
- SMTP 連線沒有逾時，學校網路丟包時排程那支會變成永不結束的行程 → `timeout=30`。

**設定產生與安全規則**

- **範本值會安靜地裝完**：`owner_email` 還是 `you@example.com`、專案 id 還是範本值的時候，
  `build_config.py` 照樣產三個檔、印「下一步：部署安全規則」然後 **exit 0**——
  老師與 AI 都以為裝好了，實際上規則鎖的是別人的信箱。現在**直接 exit 1**；
  測試與 `build_preview.py` 用新的 `--allow-placeholders` 降級成提醒。
- **規則注入**：`owner_email` 以前是原樣字串替換，而信箱格式檢查寬鬆到放行
  `x'||true||'someone@a.bc` 這種值——貼進規則之後 `isOwner()` 恆真，**整個資料庫誰都寫得進去**。
  現在字元集收緊，另外加第二道防線把值跳脫後才插進規則字串。
- `owner_email` 一律去空白轉小寫（規則、`kit-config.js`、`firebase-config.js` 三處一致）；
  `doctor.py` 比對規則裡的信箱也改成不分大小寫——以前大小寫不同會明明產對了卻報「規則裡沒有你的信箱」。
- **`authDomain` 預設改成 `<專案id>.web.app`**（以前是 Console 給的 `.firebaseapp.com`，
  跟 Firebase Hosting 的網址不同源，iOS Safari 的跨網域儲存分區會讓 Google 登入一直跳回未登入）。
  留空是合法的，`templates/answers.example.json` 與 `config/kit.example.json` 的預設值都改成 `""`。
- 課程 id 完全沒驗字元集，`../../oops` 這種 id 會讓記錄檔寫到 `data/` 外面（業務組早就有這個檢查）
  → `build_config.py` 補上 `^[A-Za-z0-9_-]+$` 的檢查，不合就 exit 1；
  `setup.py` 的 `build_data()` 在建任何資料夾之前也先驗一次（課程／業務組／記錄類型／學生代號），
  所以走答案檔硬塞 `../../oops` 不會先把資料夾建出來。
- `--draft` 在 `email.method` 是 `smtp` 的時候會掉下去**真的把信寄給家長** → `--draft` 一律不寄，
  非 gws 就落地成 `exports/` 底下的草稿檔（信箱遮罩）。
- 家長信箱比對用「代號裡的數字」當座號，`id_prefix` 本身含數字時（`6B-01` → `601`）永遠比不到 → 先切前綴再取數字。
- 重跑安裝精靈會把老師手填的 `email`／`voice`／`parents`／備份夾設定默默清掉 →
  改成「範本 ← 既有設定 ← 本次答案」逐層疊；v2 升級也補搬 `parents` 的欄位位置。
- 學生人數填了非數字直接 traceback → 改成好好說話。
- `doctor.py` 宣稱「Python 3.8 以上」但實際底線是 3.9；VC++ 只驗一個 dll，
  只裝舊版的機器會健檢通過然後 `whisper-cli.exe` 一跑就 `0xC0000135` → 兩個 dll 都驗，兩支腳本共用同一份判斷。

**跨平台**

- **可攜工具下載一律驗 sha256**：三個 whisper 包在 `hostos.DOWNLOADS` 裡釘死雜湊，
  邊下載邊算，對不上就刪掉 `.part` 直接失敗——不解壓、不留殘骸。
  （ffmpeg 那條是滾動網址，刻意留 `None` 並在 CI 印出它是 `rolling`。）
- **`kill_tree`**：印 PDF 只殺 Chrome／Edge 的父行程，renderer 子行程還抓著暫存 profile，
  Windows 上刪不掉，`%TEMP%` 留一地 `trk-chrome-*`。新增 `hostos.kill_tree()`
  （Windows 走 `taskkill /T /F`、POSIX 走 `killpg`），印 PDF 與無頭代理逾時都用它。
- `py -3` 判斷只看 `which("py")`：Store 假殼、或「裝了啟動器沒裝直譯器」（退出碼 103）的機器上，
  文件照印就是死路 → 改成**真的跑一次**才認，結果全行程快取。
- winget 的「沒事」退出碼漏掉 `0x8A150061`（已經裝好了）與 `3010`（要重開機，VC++ 常回）→ 補齊並做 32 位正規化。
- Windows 使用者名稱是中文時 `%TEMP%` 是非 ASCII 路徑，`whisper-cli.exe` 回報「找不到檔案」，
  看起來像「這個錄音壞了」→ 新增 `hostos.work_dir()` 保證 ASCII 工作區。
- `transcribe.py` 的 ffmpeg／ffprobe／whisper 全部沒有逾時，卡住就整條管線靜默停住 →
  補上逾時並給專屬訊息（whisper 那條建議改小模型）。
- macOS 上 Claude Code 原生安裝程式把 `claude` 放 `~/.local/bin`，`exe()` 找不到 → 補進候選目錄。
- Windows 的 Google 雲端硬碟偵測只掃固定磁碟機代號 → 改讀 `HKCU\Software\Google\DriveFS` 的掛載點。
- 代理安裝的備案寫成兩個 `if`，同一支備案安裝程式會被連跑兩次 → 合併成一個分支，備案只走一次。

**網頁**

- **導覽列整支靜默掛掉**：`site/js/dashboard-nav.js` 還在用 v2 的
  `import { firebaseConfig } from "./firebase-config.js"`，但 v3 的設定檔是 `window.XXX` 沒有 export。
  改讀 `window.FIREBASE_CONFIG`／`window.OWNER_EMAIL`，缺設定只 `console.warn`，不弄壞別人網站的導覽列。
- 擁有者信箱比對**大小寫敏感**：Google 回 `Teacher@Gmail.com` 而設定寫小寫就被擋在門外 → 兩邊都轉小寫再比。
- 狀態列讀不到的時候整條藏起來——「什麼都沒有」跟「一切正常」長得一模一樣，排程掛了沒人發現 →
  改成顯示紅字「讀不到同步狀態」加可能原因；另外新增衝突／真名攔截的琥珀色提示與錯誤行，
  並且每 5 分鐘自動重讀（以前只在登入當下讀一次，早上開著的分頁整天顯示同一句）。
- **離線可用**：Firestore 改用 `persistentLocalCache` ＋ 多分頁管理（退不到就退
  `enableIndexedDbPersistence`，再退記憶體快取），所有寫入包一層 `offlineAware()`——
  以前離線時畫面會永遠停在「儲存中…」。新增離線提示條、`site/manifest.json` 與 `site/icon.svg`
  （純 SVG，repo 不收二進位）讓它加得到手機主畫面。**刻意不裝 service worker**，
  離線交給 Firestore 管，免得改了設定還是看到舊頁面；`firebase.json` 配套加 `no-cache` 標頭。
- 明細頁一次抓整本：帶三年的學生幾百則，手機開一次就是幾百次讀取 → 改成一頁 50 則＋「載入更多」，
  卡片一覽最多掃 150 則（超過顯示成 `150+ 則`）。刻意不用 `where` ＋ `orderBy` 組合，
  免得逼老師去 Console 建複合索引。
- 記錄類型標籤與 `#標籤` 共用同一個 class，編輯存檔時**順手把類型標籤也刪掉** → 拆成獨立 class。
- 關聯連結指到比第一頁更舊的那一則時會誤判成「屬於別的記錄類型」而切走 → 找不到就往下翻，最多十頁。
- 一頁刪光時「載入更多」會被「還沒有記錄」整段蓋掉（其實後面還有更舊的）→ 補回來。
- 手機上編輯／刪除／分類詞那幾顆按鈕太小點不到 → 窄螢幕一律 `min-height: 40px`。

**CI**

- **doctor 怎麼壞都不會被發現**：Windows 那一步無條件吞掉失敗退出碼。現在改讀 `--json`，
  斷言固定 key 集合一個都沒少（防改名），而且必要項目一項都不能紅。
- PowerShell 的 step 外部指令失敗不會中止整個 step（等於白跑）→ 補 `$ErrorActionPreference = 'Stop'`。
- runner 預裝 ffmpeg，winget 那條安裝路徑從來沒被真的走過 → 先移掉 chocolatey 的 shim 再裝。
- 印完 PDF 檢查 `%TEMP%` 有沒有殘留 `trk-chrome-*`（驗 `kill_tree`）。
- `urls` job 改掃 `hostos.ALL_URLS()`（含 whisper 模型與 VAD 模型），並印出每一項是 pinned 還是 rolling。
- Python 版本矩陣加上 3.14；3.9 是底線。
- 新增兩個 job：`bootstrap`（macOS／Ubuntu／Windows 三台真機各跑一次 dry-run 再真跑，
  裝完那支代理要叫得出 `--version`；挑 gemini 與 codex 是因為它們裝完不登入也能回版本，**CI 永遠不做登入**）、
  `local-mode`（免互動裝一套本機模式，斷言不產規則檔、`sync.py` 是 no-op、排程只有備份、
  doctor 的 key 一個不少且雲端項全是 `skipped`）。既有的 `windows-smoke` job 多一步：
  在真的工作排程器上**註冊一次** `\TeacherRecordsKit\Headless` 再拆掉。
  `emulator` job 也加上無頭交辦的電腦端
  （走 `TRK_HEADLESS_AGENT_CMD` 假代理，**CI 永遠不叫真的模型**）。

### 文件

- 新增 `docs/PRODUCT-MANUAL.md`（產品手冊：從空機器寫到期末評語，含疑難排解速查表與四個附錄）。
- 新增 `docs/HEADLESS.md`（無頭交辦：LINE Developers 主控台逐步走法、Blaze、部署、配對、排錯）
  與 `AGENTS-HEADLESS.md`（無頭代理的行為守則）。
- `docs/GUIDE.md` 改寫成「從 bootstrap 開始」的順序（以前假設老師已經有 AI 代理）。
- `README.md` 最上面新增「從一台什麼都沒裝的電腦開始（三步）」、`INSTALL.md` 新增第 1 步與本機模式對照表、
  `docs/PLATFORMS.md` 新增「bootstrap 層」與「AI 代理的 CLI 怎麼來」兩節
  （含 Windows 的三個坑：Git for Windows 供 Claude Code 的指令工具用、Codex／Gemini 走 npm 要 Node 20 以上、
  Gemini CLI 官方列的 Windows 支援是 11 24H2 以上）。
- `AGENTS.md` 前置條件多一列、步驟 1 註明跑過 bootstrap 就不用重裝只要健檢、
  新增步驟 2-0（先問 cloud 還是 local）與步驟 11（無頭交辦）。
- `docs/ARCHITECTURE.md` 新增 §11（兩種模式）與 §12（無頭交辦）兩節，`docs/SPEC-v3.md` 新增 §13 一節。

### 這一版驗到哪裡（沒驗到的也寫清楚）

| 項目 | 驗到哪裡 |
|---|---|
| 單元測試 | 268 項，三個平台的 CI 都跑 |
| 連網路徑（同步、規則、備份、對帳、無頭的電腦端） | **只在 Firestore 模擬器上**（真的 Firestore 引擎，不碰任何雲端專案）。**還沒有對真的雲端專案跑過**——作者帳號的 GCP 專案配額已滿 |
| Windows | **只有 CI 的 `windows-latest`**：可攜工具、排程掛上／拆掉、免互動安裝、Edge 印 PDF、headless 排程真註冊。**尚未有真人老師在 Windows 上完整裝過一次** |
| `setup/bootstrap.ps1` | CI 跑過 dry-run 與真跑；**沒有任何人真的用手按過那顆 `.cmd`** |
| LINE relay（`functions/line-relay`） | **從來沒有部署到真的專案過**：沒有真的 Messaging API 頻道、沒有真的 webhook、沒有真的簽章驗證、一則推播都沒有真的送出去過。repo 裡只有靜態把關（測試檢查簽章驗證、region、集合名稱、相依只有兩個）與模擬器上的文字那條路 |
| 無頭交辦的語音那條路 | **完全沒跑過**：relay 存 Storage、`headless-inbox/**` 的規則、抓音檔、在無頭裡轉逐字稿，一項都沒驗 |
| 真的 AI 代理跑無頭 | 沒有。測試與 CI 一律走 `TRK_HEADLESS_AGENT_CMD` 假代理 |
| 錄音轉逐字稿 | CI 只驗到 `whisper-cli` 裝得起來、叫得動。repo 裡沒有轉錄的自動化測試 |

### 補記（tag 之後同一天）
- `docs/USER-GUIDE.md`：給不懂電腦老師的圖文操作書；截圖與 PDF 由 `scripts/docs/shoot_user_guide_screens.mjs`＋
  `build_user_guide_pdf.sh` 重現產生（PNG 不進 repo）。工程師版仍是 `docs/PRODUCT-MANUAL.md`。
- `site/dashboard.html` 匯出樣板裡的 `</body></html>`／`</style></head>` 字串改寫成 `<\/…>`——
  任何會後處理 HTML 的托管（例如把工具列注到第一個 `</body>` 前的靜態站建置）都不會再把腳本切斷。
- v3.0.0-alpha.4 這個 tag 打在 Windows CI 還紅的 commit 上；紅的是三個測試本身的 Windows 假設
  （測試 helper 寫成 CRLF、`bash -n` 在 Windows 的 WSL 殼、headless 子行程主控台編碑）與 CI 閘那一步的
  stdout 編碼，程式本體沒改。修正在下一個 commit，三平台全綠；tag 不動。

## v3.0.0-alpha.3 — 2026-09-11（尚未發行）

- **連網路徑第一次真的跑過**：`scripts/tests/emulator_smoke.py` 在 Firestore 模擬器（真的 Firestore 引擎，
  不碰任何雲端專案）上把老師會走到的路全部走一遍——推上去、網頁改了回寫、兩邊都改報衝突且兩邊都不動、
  網頁新增／刪除傳回本機並留稽核、備份 zip 進同步夾、三處對帳、健檢讀雲端版本、匯出、素材包，
  以及**安全規則本身**（擁有者可讀寫、陌生人與未登入 403、少了 stream 或 id 與日期不符的紀錄建不進去）。
  CI 新增 `emulator` job，每次 push 都跑。
- 這一跑抓到一個正式環境也會中的 bug：帶前置條件的 PATCH 失敗時 Firestore 回的是 **400 FAILED_PRECONDITION／409
  ALREADY_EXISTS**，程式只認 412，所以「網頁在同步途中改過」那條衝突路從來沒被走到過、會直接當機。
  現在帶前置條件的寫入一律走 `documents:commit`（前置條件放 body，正式環境與模擬器行為一致），三種狀態碼都認。
- 腳本支援標準環境變數 `FIRESTORE_EMULATOR_HOST`（設了就打本機模擬器、權杖用 owner；正式使用永遠不設）。
- 規則沒有動，不需要重新部署規則。仍未做過的：對**真的雲端專案**跑一次（作者帳號的 GCP 專案配額已滿，
  建不了測試專案）。

## v3.0.0-alpha.2 — 2026-09-10（尚未發行）

- **跨平台**：macOS 與 Windows 10／11（x64）都是正式支援，Linux 盡力支援，**WSL 直接拒跑**
  （備份夾與工作排程器都在 Windows 那一邊，WSL 看不到）。支援等級、指令對照、每個平台的坑
  一律寫在新增的 `docs/PLATFORMS.md`。
- **移除 `scripts/install_tools.sh` 與 `scripts/schedule.sh`**，改成三個平台同一支的 Python：
  - `python3 scripts/install_tools.py`：`--dry-run`、`--with-gws`、`--json`、`--remove-portable`
  - `python3 scripts/schedule.py`：`--dry-run`、`--status`、`--print-cron`、`--uninstall`、
    `--sync-time HH:MM`、`--backup-day 0-6`、`--backup-time HH:MM`（`--status` 是新的）
- **新模組 `scripts/hostos.py`**：平台差異只寫在這一支（工具怎麼裝、執行檔怎麼找、路徑、排程），
  其他腳本一律經它。
- **Windows 細節**：`.cmd`／`.bat` 的參數含 `& | < > ^ % !` 時直接拒跑（避免被 cmd.exe 重新解析）、
  主控台強制 UTF-8、排程用工作排程器的 XML 定義檔註冊（避開 `/TR` 261 字上限、錯過會補跑）、
  沒有 Chrome 時自動改用 Microsoft Edge 印 PDF、Drive 桌面同步夾自動偵測
  （`My Drive` 與「我的雲端硬碟」兩種根目錄名都找，`doctor.py` 找不到會列出候選）。
- **gws 改走 npm**：三個平台都是 `npm i -g @googleworkspace/cli`（不再用 Homebrew formula）。
- **所有文字寫入鎖 LF**（`newline="\n"`，有測試守著），`.gitattributes` 一起鎖；
  不然同一則記錄在兩台機器上的雜湊對不起來。
- **多 AI 入口檔**：安裝腦仍然只有 `AGENTS.md`（OpenAI Codex CLI 原生讀它），
  `CLAUDE.md`、`GEMINI.md`＋`.gemini/settings.json`、`.github/copilot-instructions.md`、
  `.cursor/rules/` 都只是指回 `AGENTS.md` 的小紙條。
- **CI**：`.github/workflows/ci.yml` 在 ubuntu／macos／windows 三個平台跑單元測試，
  另有 windows-latest 真機 smoke（安裝腳本、工作排程器掛上／拆掉、免互動安裝、Edge 印 PDF），
  以及每週檢查釘死的下載網址還活著。
- **規則沒有動，不需要重新部署規則。**
- **Windows 尚未經真人老師實測**——第一位 Windows 使用者就是第一次實測，遇到怪狀先當是我們的問題。

## v3.0.0-alpha.1 — 2026-09-10（尚未發行；只有 David 驗收用）

- repo 轉為私有、邀請制、收費（授權條款 placeholder，見 `LICENSE`）。
- 三個分頁：學生記錄／課程記錄／業務記錄；每頁內建「這一頁需要什麼資料」說明框。
- **學生記錄收斂為三個高痛點垂直方案**（David 2026-09-10）：①實驗教育／私校的**質性評量自動化**
  （新類型 `qualitative`）②特教／早療的 **IEP 目標追蹤**（`iep` 擴欄，掛在學生卡片的 `goals[]` 下）
  ③諮商／教練／社工的 **SOAP 個案紀錄**（`soap`，`counseling` 併進來、靠 `aliases` 讀舊設定）。
  每個方案＝一種記錄類型（欄位都有一行 `hint` 引導、`type` 分 text／date／select／multiselect／goal）
  ＋一種期末產出格式＋一條語音改寫規則。安裝精靈在學生段之前先問「你最像哪一種」，**唸出**建議的
  類型、業務組與格式，**一項都不預先勾**（`config/verticals.json`；答案檔用 `vertical` 鍵）。
- **學生卡片 `data/students/<代號>/card.json`**（雲端＝`students/<代號>`）：多 `goals[]`
  （id／領域／學年目標／學期目標／評量方式／評量標準／期程）與 `conceptualization`
  （主訴／背景／評估假設／處遇目標／結案標準）。`sync.py` 雙向同步這兩塊——只有一邊改就照那一邊、
  兩邊都改就印出來讓老師自己決定，跟記錄同一條「不覆蓋」規則。`append_record.py` 的「目標編號」
  必須是卡片上真的有的目標，填錯會被擋下來並列出可用目標；複選欄位可以直接給陣列，用「／」串起來寫檔。
- **期末一鍵素材包 `scripts/report_pack.py`**：`--format waldorf-homeroom|subject-4|iep-tracking|
  case-summary|custom --target <代號>|--all`。依格式把整年的紀錄分好組（質性＝報告維度→面向→課程；
  IEP＝每目標一表、日期序達成情形、零紀錄目標會提示；SOAP＝依會談次數的 S／O／A／P 與風險趨勢），
  附統計與缺漏，輸出 `exports/<代號>-<格式>-素材包.md` 與 `-prompt.md`（校方格式骨架＋書寫規則＋
  定稿稽核清單＋一段固定指令）。`--all` 另出 `_index.md` 全班總表。**這支不呼叫任何 LLM、不生成
  任何評語**——本文由老師的 AI 代理照 prompt 寫、由老師定稿，所以每次跑出來都一樣。
- **格式庫 `config/report-formats.library.json`**：五種格式，每種帶 `sections`（標題／提示／字數）、
  `rules`（稱名不稱全名、人稱一律「他」、先事實後判斷、每則一個下一步、禁「不是A而是B」等對比句、
  禁定型語言、困難要交代情境與支持、情意觀察不打等級）與 `audit`（定稿前的全班稽核清單）。
  結構取自使用者現行的評量系統與書寫準則、IEP 法定內容與 SOAP 慣例——**只抄結構，零學生內容**。
  `custom` 讓老師把校方格式貼進 `config/report-format.custom.json`（範本在 `templates/`）。
- `export_docs.py` 匯出學生時，卡片上的 IEP 目標與個案概念化排在他的紀錄前面。
- **學生記錄再分「記錄類型」**（導師班級學生紀錄／任課老師學生紀錄／個案追蹤／IEP／輔導晤談＋清單外開放選項）：
  一種類型一組欄位與分類詞、一個本機檔（`data/students/<代號>/<類型>.md`，導師班級紀錄沿用 v2 的
  `observations.md`）；雲端同一個集合靠必填的 `stream` 欄位分流；`scope:case` 的類型只涵蓋
  `data/roster.csv` 第三欄列入的學生（名冊改成 `代號,姓名,類型` 三欄，網頁上的「列入／移出」會回寫第三欄）。
- **全部勾選、沒有預設**：三個分頁都問「要不要」，記錄類型與業務組都列清單讓老師勾，一個都不預設勾；
  `config/tabs.example.json` 的 `students.streams` 與 `business.groups` 都是空陣列。
- 業務記錄＝業務組庫（11 組）＋每組自訂欄位與分類詞＋清單外開放選項。
- 三處一台帳：Firestore（網站）＋本機 markdown＋Google Drive 備份（桌面同步夾預設、gws 進階），`ledger.py --check` 對帳。
- 錄音檔：`inbox/` → 本機 whisper 轉錄 → AI 改寫 → `append_record.py` 唯一寫入通道。
- 確定性安裝精靈 `setup.py`；AI 代理不再手寫任何產生檔。安裝精靈不部署規則，所以第 4 步不標完成、
  只記「設定已產生，規則尚未部署」；AI 部署完跑 `setup.py --mark-step 4` 標記。
- 版本顯示：`VERSION` → `window.KIT.version`（網頁）、`doctor.py` 標頭、Firestore `meta/config.version`；
  `doctor.py` 會比對本機與資料庫的版本（連不上就跳過）。`meta/config` 另存 `dataVersion: 3`（資料格式版本）。
- v2 的 `config.example.yaml` 移到 `docs/legacy-config.example.yaml`（只當 `--upgrade` 的格式參考；
  老師自己的 `config.yaml` 仍放 repo 根目錄）。
- 安全規則：新增 `business/**`、`meta/**`；擁有者可刪除（配合個資法刪除請求）。
- 設定檔改 JSON（`config/kit.json`、`config/tabs.json`），移除自寫 YAML 解析器。
- **一鍵匯出 Word／PDF**（網頁端 .doc＋列印；腳本端 `export_docs.py` 真 .docx＋Chrome PDF）：
  每一位學生、每一門課程、每一個業務組、班級整體觀察與「所有學生」都能一鍵出文件；腳本端 `.docx`
  用標準庫 zipfile 直接寫最小 OOXML（零相依），`.pdf` 借本機 Chrome headless 印，沒有 Chrome 就
  留下排版好的 HTML 讓老師自己列印成 PDF。輸出在 `exports/`（已加進 `.gitignore`，因為含名冊真名）。
- 同步回寫加 `currentDocument.updateTime` 前置條件，不再靜默覆蓋網頁上剛改的字；卡片摘要（課程卡／
  業務組卡／學生卡）同樣先讀 updateTime 再帶前置條件，而且只推統計欄位——課名與組名以網頁為準。
- 設計正本：`docs/SPEC-v3.md`（含紅隊裁決）。

## v2 — 2026-07-31、v1 — 2026-07-14

見 `docs/REPORT.md` 第 10 節（MIT 公開版）。
