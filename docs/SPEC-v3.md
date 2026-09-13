# Teacher Records Kit v3 — 設計規格（建置 SSOT）

> 2026-09-10 起。本檔是 v3 的唯一設計正本：程式、文件、引導流程都照這裡做；改設計先改這裡。
> 讀者：建置 v3 的 AI 代理與 David。使用者（老師）不必讀本檔，他們讀 `README.md` 與 `docs/GUIDE.md`。

## 0. 定位（與 v2 的差別）

| | v2（公開） | v3（私有、收費） |
|---|---|---|
| 取得方式 | 任何人 clone | David 邀請成為 repo 協作者後下載 |
| 分頁 | 學生觀察、課程紀錄 | **學生記錄、課程記錄、業務記錄**（＋每頁內建「這頁需要什麼資料」說明） |
| 儲存 | Firestore | Firestore（網站）＋本機 markdown（累積）＋ **Google Drive 備份**，三處以「台帳」對得起來 |
| 輸入 | 網頁打字、本機 md | 網頁、本機 md、**錄音檔**（本機 whisper 轉錄→AI 改寫→只走 `append_record.py` 寫入） |
| 業務 | 無 | 勾選「業務組」→ 每組一個面版；不在清單的走開放選項，AI 問清楚後設計 |
| 引導 | AGENTS.md 五步 | AGENTS.md 精靈：每步「AI 主動問→使用者去哪拿（連結）→做→驗證」，進度記在 `setup/progress.json` |
| 授權 | MIT | 專屬授權（條款待 David 定，先放 placeholder） |

**獨立性鐵則**：一切帳號（Google、Firebase、Drive、GitHub）都是使用者自己的。David 不代管、不持有金鑰、看不到資料。repo 只有程式與範本，零個資。

## 1. 使用者體驗（老師視角）

1. 收到 David 的邀請信 → 下載 repo（zip 或 `git clone`）。
2. 打開自己的 AI 代理（Claude Code 等），說：「讀 AGENTS.md，幫我裝起來。」
3. AI 一次只問一件事：你的 Google 帳號？要不要業務記錄？勾哪些業務組？學生名單在哪？……每一題都附「去哪裡拿、怎麼做」的連結。
4. 裝好後：手機或電腦開網站登入，三個分頁記錄；或把錄音檔丟進 `inbox/` 跟 AI 說「整理成○○記錄」。
5. 本機每日同步、每週備份到自己的 Google Drive；隨時可跑 `ledger.py --check` 看三處對不對得上。
6. （選用）**本機模式**＝完全不碰雲端，只有第 2、5 點沒有；（選用）**無頭交辦**＝在外面對 LINE 講一句話，回家紀錄已經寫好了。兩個都見 §13。

## 2. 儲存架構（三處一台帳）

```
網站（Firestore，老師的 Firebase 專案）
  roster/main                       {students:[{id,name}], protectedPhrases:[]}
  students/{id}                     卡：{goals:[...]（iep）, conceptualization:{...}（soap）}；本機 data/students/<id>/card.json
  students/{id}/records/{rid}
  class-observations/{rid}
  courses/{courseId}                {title,kind,season,weeks,teacherName,order}
  courses/{courseId}/records/{rid}
  business/{groupId}                {label,fields:[...],tags:[...],custom:bool}
  business/{groupId}/records/{rid}
  meta/config                       {version, tabs:[...]}（唯讀鏡像，供網頁顯示說明）

本機（repo 內 data/，gitignored）
  data/roster.csv                   代號,姓名（唯一有真名的地方）
  data/contacts.csv                 （選用）家長信箱
  data/students/<id>/observations.md
  data/class/observations.md
  data/courses/<courseId>/records.md
  data/business/<groupId>/records.md
  data/ledger.jsonl                 台帳（由 ledger.py 重建；每則一行）
  data/audit.jsonl                  append_record.py 的寫入稽核
  data/backups.jsonl                每次備份的 zip 路徑、md5、Drive file id

Google Drive（老師自己的雲端硬碟；folder ID 錨定）
  <backup_folder_id>/teacher-records-<YYYY-MM-DD-HHMM>.zip   = data/ 全份 + export.json
```

### 2.1 記錄（四種來源共用同一形狀）

```json
{
  "date": "2026-09-10",
  "tags": ["#人際", "#親師"],
  "body": "……（去識別化正文）",
  "fields": {"期限": "2026-09-20", "狀態": "進行中"},   // 只有業務記錄有；鍵＝該組 fields 名
  "related": ["students/S-03/2026-09-10", "courses/fractions/2026-09-09-1435"],
  "source": "web" | "voice" | "file",
  "sourceFile": "business/guidance/records.md",
  "contentHash": "sha256[:16] of tags|fields|related|body",
  "editedOnWeb": false, "webEditedAt": null,
  "taskId": "voice-2026-09-10-001"                          // 語音來源才有
}
```

- **rid**：當天第一則＝`YYYY-MM-DD`；之後＝`YYYY-MM-DD-HHMM`（撞再補秒 `-HHMMSS`）。id 建立後不改、date 不改（規則擋）。沿用 v2。
- **related 語法**：`<kind>/<target>/<rid>`，kind ∈ `students|class|courses|business`（class 的 target 固定 `main`）。這是「三個台帳對在一起」的鍵。
- **去識別化**：學生一律代號（預設 `S-01`…，可自訂前綴）；正文出現名冊真名 → `append_record.py` 攔下、網頁寫入前自動代換成代號（v2 行為保留）。

### 2.2 本機 markdown 區塊格式（四種檔共用）

```
## 2026-09-10 14:35 #親師 #人際
期限：2026-09-20
狀態：進行中
關聯：students/S-03/2026-09-10; courses/fractions/2026-09-09-1435

正文……（可多段）
```

- 標題列：`## 日期 [時間] #tags…`（第一則無時間；解析 regex 沿用 `lib.DATE_RE`）。
- 欄位列（只在業務檔）：緊接標題、每行 `欄位名：值`（全形冒號）。**解析器寬鬆**：任何 `鍵：值` 行都收進 `fields`，不因為鍵不在該組 `fields` 就拒絕（紅隊 #13：組的 fields 只是表單建議，不是 schema 閘；改欄位名不需要 migration）。
- `關聯：` 行：分號分隔。
- 空一行後是正文。只加不刪。

### 2.3 台帳 `data/ledger.jsonl`

每則一行：`{"kind","target","rid","date","tags","hash","source","related","local":true,"cloud":true|false|null,"backup":{"zip","md5","driveFileId"}|null}`。

`scripts/ledger.py`：
- `--rebuild`：掃 data/ 四種檔重建本機欄位。
- `--check`：對 Firestore（需登入）與 `data/backups.jsonl` 比對，印三欄表（本機／網站／Drive）＋不一致清單（本機有網站無、網站有本機無、hash 不同、最近一次備份缺哪些）。exit 0＝全對；1＝有差。
- `--related <kind>/<target>/<rid>`：列出該則的所有關聯（雙向：被誰關聯也列）。

## 3. 三個分頁的向度

### 3.1 學生記錄（仿 David 5A 現制，**再分「記錄類型」**）

David 2026-09-10 追加：學生記錄不能混在一起——純班級學生紀錄、個案紀錄、導師學生紀錄、任課老師學生紀錄要分得清楚。所以學生分頁內再分 **記錄類型（stream）**，每一種各有自己的欄位、分類詞與「哪些學生在裡面」。

- **記錄類型庫** `config/student-streams.library.json`（安裝時勾選，**沒有預設勾任何一種**；正本＝該 JSON，本表只列骨架，欄位細節見 §3.6 與 JSON）：

| id | label | 範圍 scope | 誰用 | 備註 |
|---|---|---|---|---|
| `qualitative` | 質性評量觀察 | `class` | 實驗教育／私校導師（方案①） | 面向／報告維度／課程／證據來源／指標 |
| `homeroom` | 導師班級學生紀錄 | `class` | 一般導師 | 只有 tags，無固定欄位 |
| `subject` | 任課老師學生紀錄 | `class` | 科任 | 科目、觀察向度、證據來源 |
| `case` | 個案追蹤（通用） | `case` | 導師／個管 | 來源、主訴／議題、處遇／介入、追蹤與下次 |
| `iep` | IEP／早療追蹤 | `case` | 特教／早療（方案②） | 學生卡 goals；目標編號／達成情形／證據／支持策略／下一步／會議決議 |
| `soap` | SOAP 個案紀錄 | `case` | 諮商／教練／社工（方案③） | 學生卡 conceptualization；S／O／A／P、會談形式、次數、風險評估、下次時間；`aliases:["counseling"]` |
| `custom` | 我的學生紀錄類型不在清單裡 | 開放選項 | — | AI 問四件事後產生 |

- **記錄形狀**：`students/{id}/records/{rid}` 多一個必填 `stream: "<id>"`；欄位／關聯照 §2.1。規則 `create` 要求 `stream is string && size() > 0`。
- **本機檔**：每位學生、每種類型一檔 `data/students/<id>/<streamId>.md`（`homeroom` 沿用舊檔名 `observations.md` 以相容 v2）。區塊格式照 §2.2。
- **哪些學生在哪種類型**：`scope: class` 的類型自動包含名冊全部學生；`scope: case` 的類型由 `data/roster.csv` 第三欄起的 `streams` 欄（分號分隔，如 `case;iep`）決定，網頁也可在該類型下「＋ 列入學生」（寫 `roster/main.students[].streams`）。
- **網頁**：學生分頁頂端一排「記錄類型」切換（只顯示安裝時勾的）；全班一覽、本月已記／未記、明細與新增表單都**依當前類型**過濾與帶欄位；一位學生的明細頁可切看他在各類型的紀錄。班級整體觀察仍只掛在 `homeroom`／`subject` 這類 `class` 範圍類型下。
- 每一種類型都可加自訂欄位／分類詞（與業務組同一套兩層開放選項）。
- 名冊需要的資料（引導時要問）：代號（或座號）、姓名；選填：學號、性別、家長信箱（寄信才要）、哪些學生列入哪些個案型類型。

### 3.2 課程記錄（仿 David 現制）
- 課程卡：`title`（必填）、`kind`（主課程／科任）、`season`、`weeks`、`teacherName`、`order`（皆選填）。網頁可直接建卡。
- 明細新增時正文預先帶四段骨架（可刪）：`### 課程進度`、`### 今天實際教了什麼`、`### 學生整體反應`、`### 下次要調整的`。
- 預設 tags：`#進度 #教學內容 #學生反應 #調整 #亮點 #卡點 #規劃`。
- 提及個別學生一律代號，並可加 `related` 連到該生記錄。

### 3.3 業務記錄（通用框架、可擴充）
- **業務組庫** `config/business-groups.library.json`：每組 `{id,label,desc,fields:[{name,type:text|date|select,options?}],tags:[...]}`。**安裝時全部由老師勾選，沒有預設勾任何一組**（David 2026-09-10）。內建 11 組：導師班務／輔導與個案追蹤／特教與 IEP／教務／學務／總務／公文與行政流程／會議紀錄／研習與專業成長／家長與社區／個人待辦。
- **兩層開放選項（David 2026-09-10 指示）**：
  1. 每一組都可加「自訂欄位」「自訂標籤」（勾選時 AI 要問：「這組還有沒有你自己要記的欄位？」）。
  2. 清單外的業務 → 選「我的業務不在清單裡」→ AI 問四件事（這項業務叫什麼、每次要記哪些固定欄位、常用分類詞、和學生／課程有沒有關聯）→ 產生一組 `custom:true` 寫進 `config/tabs.json`。
- 網頁：業務分頁列出已啟用的組（卡片＝組名＋N 則＋最後日期）；「＋ 新增業務組」可從庫勾選或自訂（寫 `business/{id}` 卡，並提示回頭叫 AI 同步進 `config/tabs.json`，因為本機檔與規則以 config 為準）。
- 明細：欄位表單（依該組 fields 動態生成）＋ tags 快速鍵＋正文＋關聯輸入（打 `S-03` 自動補成 `students/S-03/…` 建議）。
- 建置時把本建議清單當草稿，David 校對後才定案（網搜當次不可用，清單出自校務常識）。


### 3.6 學生記錄收斂為三個高痛點垂直方案（David 2026-09-10 追加）

學生記錄類型庫改以三個垂直方案為主幹；每個方案＝「一種記錄類型（含引導欄位）＋一種期末產出格式＋語音改寫規則」。安裝精靈先問「你是哪一種角色／最痛的是什麼」，AI 唸出該方案**建議**勾的類型與業務組，老師逐項確認（仍是零預設）。校內評量標準來源＝WTOS `ai-core/skills/assessment-system.md`、`write-assessments.md`＋overlays、G5 教師檢核-課程觀察指標；已抽成下面的通用結構。

| 方案 | 記錄類型 id | 痛點 | 記錄時的引導（fields） | 期末一鍵產出 |
|---|---|---|---|---|
| ① 質性評量自動化（實驗教育／私校） | `qualitative`（取代 homeroom 作為華德福建議；homeroom 保留給一般班務） | 不打分數，期末要從零碎筆記回溯寫評語 | `面向`（多選：頭·思考／心·情感／手·意志／社群·人際）、`報告維度`（單選：①行為與自我管理 ②人際互動 ③學習態度與能力 ④內在特質與個人發展 ⑤挑戰與方向）、`課程`（courseId 或科目）、`證據來源`（工作本／課堂觀察／口說／身體／作品／親師）、`指標`（選填：「第N條 可獨立完成｜需輔助完成｜尚無法完成」——情意類永不打等級） | **質性評量素材包**＋評語草稿：`report_pack.py --format waldorf-homeroom`（發展樣貌／客觀描述五維度／整體感受／導師建議約100字）或 `subject-4`（關係／參與／可見的學習證據／下一步；320–450字）或 `custom`（老師貼校方格式） |
| ② IEP／早療追蹤 | `iep` | 目標達成細節多、評鑑格式繁瑣 | 學生卡多 **`goals[]`**（`{id, 領域, 學年目標, 學期目標, 評量方式, 評量標準, 期程}`；領域＝特教：認知／溝通／行動／情緒行為／社會／生活自理／學業；早療：認知／語言／動作／社會情緒／生活自理）；每則 `目標編號`（從該生 goals 選）、`達成情形`（未開始／初步／部分達成／達成／類化）、`證據`（觀察／作品／測驗／家長回報）、`支持策略`、`下一步`、`會議決議` | **IEP 追蹤報告**：`report_pack.py --format iep-tracking` → 每目標一表（目標／評量方式與標準／日期序達成情形／證據／摘要）＋期末總評段；會議紀錄沿用三段式（述說前提／會議重點／日後發展目標） |
| ③ 諮商／教練／社工 SOAP | `soap`（取代 counseling） | 會談後要寫 SOAP 或個案紀錄，手寫耗時漏細節 | 個案卡多 **`conceptualization`**（主訴／背景／評估假設／處遇目標／結案標準）；每則 `S 主觀`、`O 客觀`、`A 評估`、`P 計畫`、`會談形式`、`會談次數`、`風險評估`（無／低／中／高）、`下次時間`；每個欄位有一行提示（S＝個案的話與主觀感受；O＝可觀察的行為與事實；A＝專業評估與假設；P＝下一步處遇） | **個案摘要／結案報告**：`report_pack.py --format case-summary` → 個案概念化＋歷程摘要（依次數）＋進展評估＋處遇建議／結案評估 |

- **語音改寫規則**（AGENTS.md §錄音）：逐字稿 → 依方案的欄位骨架改寫（質性評量：每則一個具體事件＋面向＋報告維度；IEP：先對 goals 分段，每段一則、標目標編號與達成情形；SOAP：四段拆分，個案的話進 S、可觀察行為進 O）→ `append_record.py --fields-json`。
- **素材包與草稿分工**（維護成本最低）：`scripts/report_pack.py` 只做確定性的事——依格式把該生所有記錄分組（報告維度／面向／課程／目標／次數）、附統計、附**校方格式骨架與書寫規則**（稱名不稱全名、人稱「他」、先事實後判斷、每則只一個下一步、禁「不是A而是B」等對比句、禁定型語言）成 `exports/<學生>-素材包.md`＋`-prompt.md`；**評語本文由老師的 AI 代理寫**（AGENTS.md 給它固定流程與檢核清單）；`--all` 全班一包。網頁端「產生期末素材」按鈕做同一件事（下載 .md）。
- **格式庫** `config/report-formats.library.json`：`waldorf-homeroom`、`subject-4`、`iep-tracking`、`case-summary`、`custom`（老師貼自己學校的格式標題，AI 依樣產）。每個格式＝`{id,label,sections:[{title,hint,length}],rules:[...]}`。
- **方案庫** `config/verticals.json`：三方案（`qualitative-assessment`／`iep-tracking`／`soap-casework`）各列 `label`、`pain`、`suggest{streams,groups,format}`、`voiceRule`（語音改寫規則），供精靈唸給老師聽；只是建議，不預勾。老師選的方案與格式寫進 `config/tabs.json` 頂層 `vertical`／`reportFormat`（answers 鍵 `vertical`／`report_format`）。
- 類型庫調整：`counseling` 併入 `soap`（保留別名讀舊資料）；`case` 保留為通用個案追蹤；`iep` 依上表擴欄；新增 `qualitative`。

### 3.4 每頁「這頁需要什麼資料」
每個分頁頂端一個可收合說明框，內容來自 `config/tabs.json` 的 `help`（安裝時 AI 依老師的回答寫進去），示範模式顯示預設文案。內容分三行：這頁記什麼／新增前你要準備什麼／AI 可以幫你做什麼（例：「把錄音檔放進 inbox/ 跟 AI 說『整理成課程記錄』」）。


### 3.5 一鍵匯出 Word／PDF（David 2026-09-10 追加）

每一位學生、每一個業務組、每一門課程，以及「所有學生」都要能一鍵匯出成 Word 與 PDF。

- **網頁端（零相依、離線可用）**：
  - 學生明細頁「匯出」→ Word／PDF；可選「只匯出目前類型」或「這位學生全部類型」。
  - 業務組明細頁、課程明細頁同樣「匯出」→ Word／PDF。
  - 學生分頁一覽頁「匯出所有學生」→ Word／PDF；可選類型與日期範圍（預設全部）；輸出一份文件、每位學生一節（含名冊姓名＋代號，這是老師自己看的）。
  - **Word**＝瀏覽器直接組出 `.doc`（Word 相容 HTML，`application/msword`）並下載，不載任何外部函式庫；檔名 `<對象>-<類型>-<日期>.doc`。
  - **PDF**＝開一個乾淨的列印版面（只有標題、記錄、欄位表；有 `@media print` 樣式）並呼叫 `window.print()`，老師在列印對話框選「儲存為 PDF」；手機上同樣可行。
  - 排版共用同一個 `renderExportHtml(kind, target, opts)`，Word 與 PDF 只差外殼。
- 班級整體觀察明細頁同樣有「匯出 ▾」；彈出視窗被擋時改成同頁列印覆蓋層。
- **腳本端（正式版、給期末或大量用）**：`scripts/export_docs.py --kind students|class|courses|business --target <id>|all [--stream X] [--from --to] [--with-class] --docx [--pdf] [--html]`：`.docx` 用標準庫 `zipfile` 直接寫最小 OOXML（零相依）；`.pdf` 若機器上有 Chrome／Chromium（或環境變數 `TRK_CHROME` 指定）就 `--headless=new --print-to-pdf`，沒有就把 HTML 留在 `exports/` 並印「用瀏覽器開這個檔→列印→儲存為 PDF」。輸出到 `exports/`（gitignored）。網頁端版面正本是 `buildExport()`（`renderExportHtml` 為薄包裝、`renderExportUI` 生選單）。
- 匯出內容一律去識別化正文＋名冊姓名（因為是老師自己用），檔案落地在老師機器；文件與 README 要提醒「匯出檔含真名，別放到公開的地方」。

### 3.7 跨平台層（David 2026-09-10 拍板）

- **`scripts/hostos.py` 是唯一的平台模組**：工具怎麼裝、執行檔怎麼找（`.cmd`／`.bat`）、主控台編碼、
  Drive 同步夾候選、Chrome／Edge 候選、排程機制——平台差異只寫在這一支，其他腳本一律經它。
- **`docs/PLATFORMS.md` 是唯一的人讀正本**：支援等級、指令對照、每個平台的坑、排程機制。
  其他文件只放一行對照與連結，不重複表格。
- 支援等級：macOS 與 Windows 10／11 正式支援、Linux 盡力、**WSL 直接拒跑**。
- CI（`.github/workflows/ci.yml`）三平台跑單元測試，另有 windows-latest 真機 smoke：
  安裝腳本、工作排程器掛上／拆掉、免互動安裝、Edge 印 PDF。
- **連網路徑的驗證＝Firestore 模擬器**（`scripts/tests/emulator_smoke.py`，CI 的 `emulator` job）：
  sync 的推、回寫、衝突、網頁新增／刪除，backup、ledger、doctor 讀雲端版本，以及安全規則本身
  （擁有者可讀寫、陌生人 403、少 stream 建不進去）。腳本認標準環境變數 `FIRESTORE_EMULATOR_HOST`。
  帶前置條件的寫入一律走 `documents:commit`，前置條件失敗認 400 FAILED_PRECONDITION／409／412。
  仍未對真的雲端專案跑過（作者帳號 GCP 專案配額已滿）。
- **Windows 尚未有真人老師實測過**；第一位 Windows 使用者的怪狀先當是我們的問題。
- 所有文字寫入一律 LF（`newline="\n"`，有測試守著），`.gitattributes` 鎖 LF。

## 4. 設定檔（單一產生器、三個輸出）

- `config/kit.json`（**JSON，不再自寫 YAML 解析器**——紅隊 #10）：`owner_email`、`id_prefix`、`firebase{project_id,api_key,auth_domain,storage_bucket,messaging_sender_id,app_id}`、`drive{mode:"desktop"|"gws", desktop_dir, backup_folder_id, keep_backups}`、`voice{model,lang}`、`email{...}`。v2 的 `config.yaml` 由 `setup.py --upgrade` 一次轉成 JSON。
- `config/tabs.json`（分頁與向度）：
  ```json
  {"version":3,
   "students":{"enabled":true,"streams":[{"id":"homeroom","label":"導師班級學生紀錄","scope":"class","fields":[],"tags":["#課堂",...],"custom":false}],"help":{...}},
   "courses":{"enabled":true,"categories":[...],"skeleton":["### 課程進度",...],"help":{...}},
   "business":{"enabled":true,"groups":[{"id":"guidance","label":"輔導／個案追蹤","fields":[...],"tags":[...],"custom":false}],"help":{...}}}
  ```
- `scripts/build_config.py` 讀上面兩份，產生：`site/js/kit-config.js`（`window.KIT = {...}`）、`site/js/firebase-config.js`、`firestore.rules`（換 `{{OWNER_EMAIL}}`，信箱一律去空白轉小寫並跳脫後才插進規則字串）。三個輸出都 gitignored。`auth_domain` 留空時預設 `<專案id>.web.app`。
- 範本：`config/kit.example.json`、`config/tabs.example.json`、`setup/progress.example.json`。
- **安裝是確定性的**（紅隊 #3）：`scripts/setup.py` 互動問答（可用 `--answers file.json` 免互動）負責產檔、換規則、自檢；AI 代理只負責解釋題目、幫老師找答案、讀錯誤訊息。規則檔**永遠由腳本產生**，AGENTS.md 禁止 AI 手寫 `firestore.rules`。

### 4.1 「全部勾選、沒有預設」原則（David 2026-09-10）
安裝精靈對三個分頁都問「要不要」，對學生記錄類型與業務組都列清單讓老師勾，**一個都不預設勾**；`config/tabs.example.json` 只當形狀範本，示範模式的種子資料另外在網頁內。

## 5. 網站 `site/dashboard.html`

- 單檔、無框架、無建置步驟；Firebase 用 **動態 `import()`** 只在非示範模式載入；設定以傳統 `<script src="js/kit-config.js">` 載入（`window.KIT`）。
- **儲存介面** `Store`：`roster()`, `listCards(kind)`, `setCard(kind,id,data)`, `listRecords(kind,target)`, `getRecord`, `createRecord`, `updateRecord`。兩個實作：`FirestoreStore`、`DemoStore`（種子資料＋localStorage 持久化；頂端黃色橫幅「示範模式：資料只存在這個瀏覽器」）。
- 示範模式觸發：`KIT.demo === true` 或網址 `?demo=1`。
- `scripts/build_preview.py` 把 `dashboard.html` ＋ `config/tabs.example.json` 內聯成**單一可離線開啟的 HTML**（無外部 script、無 module import，file:// 可開）→ `preview/teacher-records-kit-預覽.html`。這就是給 David 驗收的檔。
- 登入防呆、手機返回鍵、rid 配置、去識別化、規則過舊偵測：v2 行為全部保留。
- 分頁狀態在 `location.hash`：`#students` `#courses` `#business` `#class` `#s/<id>` `#c/<courseId>` `#b/<groupId>`。
- 每則記錄卡顯示 `related` 為可點連結；業務記錄卡顯示欄位表；每則可「刪除」（二次確認）。
- 頂端狀態列讀 `meta/status`：`上次同步 X 天前・上次備份 Y 天前`，任一超過 7 天顯示紅字（示範模式顯示假數字）。
- 不做：影音上傳到網頁、搜尋引擎、多租戶。

## 6. 腳本（`scripts/`，Python 3 標準庫為主；對外只靠 gcloud / firebase / gws / whisper-cli / ffmpeg）

| 腳本 | 用途 | 關鍵行為 |
|---|---|---|
| `lib.py` | 共用 | 沿用 v2；新增 `parse_block_fields()`（欄位列＋關聯列）、`targets(cfg, tabs)` 產四種目標清單 |
| `setup.py` | **確定性安裝精靈** | 互動問答（或 `--answers`）→ 寫 `config/kit.json`、`config/tabs.json` → 呼叫 build_config → 跑 doctor；`--upgrade` 把 v2 的 config.yaml 轉過來（零預設的唯一例外：自動勾 `homeroom`，否則舊 observations.md 看不見）；`--resume` 讀 `setup/progress.json` 續做；**不部署規則、不標第 4 步**，AI 在 `firebase deploy` 成功後跑 `--mark-step 4 --note ...` |
| `build_config.py` | 產生三個 gitignored 輸出 | 見 §4；`--check` 只驗不寫；設定裡還留著範本值（`you@example.com`、`your-firebase-project-id`、空白金鑰）一律 exit 1，測試／預覽要跑得過就加 `--allow-placeholders`（`setup.py` 內部呼叫時帶它）|
| `doctor.py` | 健檢 | 逐項 ✓／✗：工具在不在、config 齊不齊、gcloud／firebase／gws 登入了沒、Drive 夾 ID 存在且 `trashed=false`、whisper 模型在不在；每個 ✗ 附「怎麼修」與連結；`--json` 給 AI 讀 |
| `install_tools.py` | 裝依賴 | 三個平台同一支：macOS 走 Homebrew、Windows 走 winget（失敗退可攜版）、Linux 走 apt／官方說明，裝的都是 `node`、`firebase-tools`、`google-cloud-sdk`、`whisper-cpp`、`ffmpeg`（`gws` 選用，一律 `npm i -g @googleworkspace/cli`）；每步先印「要裝什麼、為什麼」，不重試、不留半裝狀態；`--dry-run`、`--with-gws`、`--json`、`--remove-portable`。每個平台的細節見 `docs/PLATFORMS.md` |
| `sync.py` | 本機 ↔ Firestore 雙向 | 通用化到四種目標；衝突不覆蓋；回寫前備 `.prev.md`；`--dry-run`；結束寫 `.sync-last-status` 與 Firestore `meta/status.lastSyncAt`。**每個 PATCH 必帶 `currentDocument.updateTime` 前置條件**（紅隊 #9：v2 的無條件回寫會在老師同時編輯時靜默蓋掉他的字）；前置條件不成立（400 FAILED_PRECONDITION／409／412）就當衝突處理、不重試覆寫；帶前置條件的寫入走 `documents:commit` |
| `append_record.py` | **唯一寫入通道** | `--kind students|class|courses|business --target ID --date --tags --content-file --fields-json --related --source voice|file --task-id`；O_APPEND；寫前後 rid 斷言；名冊真名攔下；審計 `data/audit.jsonl`；`--sync` 順手跑 sync |
| `transcribe.py` | 錄音 → 逐字稿 | 單檔或 `--inbox`（掃 `inbox/*.m4a|mp3|wav|mp4`）；ffmpeg 轉 16k wav → `whisper-cli -m ~/.cache/whisper-cpp/ggml-large-v3-turbo.bin -l zh`（模型缺就從 Hugging Face 下載並印進度）；輸出 `inbox/transcripts/<檔名>.md`，處理完原檔移到 `inbox/done/`；結尾印「接下來請 AI 讀逐字稿、改寫成○○記錄、再用 append_record.py 寫入」；逐字稿永不出本機。**AI 改寫不在腳本裡**（見 AGENTS.md §錄音） |
| `backup.py` | 本機＋Drive 備份 | zip `data/`＋`export.json`（Firestore 全量）→ `backups/`；**兩種 Drive 模式**（紅隊 #4）：`desktop`（預設）＝把 zip 複製進「Google 雲端硬碟」桌面程式的同步夾 `drive.desktop_dir`（零 OAuth、Windows 也行）；`gws`（進階）＝`gws drive files create --json '{"name":..,"parents":[id]}' --upload <cwd 相對路徑>`（先 `gws drive files get --params '{"fileId":..,"fields":"id,name,trashed"}'` 驗存在且 `trashed=false`，找不到就停、**不自建夾**；上傳後比 md5Checksum）。兩種都寫 `data/backups.jsonl` 與 Firestore `meta/status.lastBackupAt`；保留最近 N 份 |
| `ledger.py` | 台帳 | 見 §2.3（`--rebuild`、`--check`；`--related` 延後） |
| `export_records.py` | 匯出取材（Markdown／JSON） | 通用化四種；`--by-tag`、`--related`（把關聯記錄一起帶出）、`--stream`（只匯某一種學生記錄類型） |
| `report_pack.py` | 期末素材包＋草稿 prompt | 見 §3.6；`--format waldorf-homeroom|subject-4|iep-tracking|case-summary|custom`、`--target <id>|all`（＝`--all`）、`--stream`；輸出 `exports/` |
| `export_docs.py` | 匯出 Word／PDF | 見 §3.5；`.docx` 標準庫 zipfile、`.pdf` 走 headless Chrome（沒有就給 HTML） |
| `schedule.py` | 排程（選用） | 三個平台同一支：macOS 產 launchd plist、Windows 用工作排程器 XML 定義檔註冊、Linux 寫 crontab 區塊。**掛幾支由 `wanted_jobs()` 決定，不是固定兩支**：`sync`（每日 07:00，只有 cloud 模式）、`backup`（每週日 08:00，一定有）、`headless`（每 5 分鐘，只有開了無頭交辦；macOS 用 `StartInterval: 300`、Windows 用 `Repetition PT5M`、Linux 是 `*/5 * * * *`）。`--uninstall` 一律全清、`--status` 對沒開的那幾項印「本來就不該掛」；`--dry-run`、`--status`、`--print-cron`、`--uninstall`、`--sync-time`、`--backup-day`、`--backup-time`。**失敗要看得見**（紅隊 #11）：網頁頂端讀 `meta/status`，上次同步／備份超過 7 天就顯示紅字 |
| `parent_email.py`、`pending.py`、`monthly_reminder.py` | 選用 | 沿用 v2 |
| `tests/` | 零網路測試 | 區塊解析、rid、欄位列、關聯、ledger rebuild、build_config 輸出、demo store 種子 |

## 7. 安全規則 `firestore.rules.tmpl`

v2 全部保留，新增：
```
match /business/{groupId} { allow read, write: if isOwner();
  match /records/{recordId} { …與 students/{id}/records 同款… } }
match /meta/{doc} { allow read, write: if isOwner(); }
```
**v3 改為允許擁有者刪除**（紅隊 #6：未成年人個資必須能應家長要求刪除），alpha.5 起改成**兩段式**：網頁刪除＝軟刪（二次確認後 `updateDoc({deleted:true, deletedAt, deletedBy})`，規則的 `delete` 一律拒，真刪只走 Admin SDK／使用者權杖），sync 把它當「雲端已刪」傳播到本機檔（整檔遺失時不刪，沿用 David 5A 規則）並記 `{op:"delete", kind, target, rid, hash, at}`；雲端原文保留到老師自己在終端機跑 `scripts/purge_deleted.py --confirm`（不可逆，另記 `{op:"purge", …}`）——個資法刪除請求的最終完成點在那一步。匯出、素材包、台帳一律排除軟刪的則；`backup.py` 的 `export.json` 故意保留（Drive 快照裡還有＝可接受）。

## 8. 引導流程 `AGENTS.md`（精靈）

- 開頭「你是誰在讀」：假設讀者是 Claude Code 等最高等級代理；**一次只問一題**；每題附「去哪裡拿」連結；問完做、做完驗、驗完由 `setup.py` 寫 `setup/progress.json`（gitignored）再往下。**AI 不手寫任何產生檔**（規則、firebase-config、kit-config）——一律跑腳本。
- 前置條件先講清楚（紅隊 #1）：macOS 或 Windows 10／11（David 2026-09-10 拍板支援 Windows；Linux 盡力、WSL 拒絕，見 `docs/PLATFORMS.md`）、能開 Firebase 專案的 Google 帳號（學校配發帳號常被管理員鎖住 Cloud Console，GUIDE 要教怎麼判斷、以及改用個人帳號的取捨）、已裝好的 AI 代理。
- 「去哪裡拿」寫**目標＋驗證**而不是逐畫面截圖（紅隊 #2：Console 畫面會改版，AI 自己會找路）。
- 步驟：0 判斷新裝／升級／續裝（讀 progress） → 1 裝工具（跑 `install_tools.py` 與 `doctor.py`） → 2 Google 帳號與 Firebase 專案（console 連結、逐畫面指引、取 web config） → 3 分頁與向度（學生：名冊來源；課程：先建幾門；業務：勾組＋兩層開放選項） → 4 產生設定與規則（`build_config.py`、`firebase deploy`） → 5 上線（Firebase Hosting 預設；GitHub Pages 備選；嵌入現有站見 embed/） → 6 學生名單與既有資料匯入 → 7 Google Drive 備份夾（老師自己建夾→貼網址→AI 抽 ID→`doctor.py` 驗） → 8 排程 → 9 錄音檔試跑一次 → 10 驗收清單 → **11 無頭交辦（選用，驗收之後才問；本機模式不問）**。
- 每步固定四段：**AI 要問的話**／**使用者去哪裡拿（連結＋畫面路徑）**／**AI 要做的事（指令）**／**怎麼驗證＋失敗時怎麼辦**。
- 升級路徑 v2→v3：保留設定與 data、跑 `build_config.py`、重新部署規則、`sync.py --dry-run`。
- 錄音流程、日常使用、每月／期末取材各一節。

## 9. 文件

- `README.md`：私有、邀請制、三分頁、獨立性聲明、怎麼開始、授權（placeholder）。
- `docs/GUIDE.md`：給完全沒碰過 AI 的老師：從「什麼是 AI 代理、怎麼裝 Claude Code」到「怎麼跟它說話」，每步附連結與畫面。
- `docs/DATA-CHECKLIST.md`：三分頁各自「你要準備什麼資料、格式、範例」。
- `docs/BUSINESS-GROUPS.md`：業務組庫人讀版＋開放選項說明。
- `docs/ARCHITECTURE.md`：三處一台帳、安全、同步與備份、錄音管線（取代 REPORT.md 前 9 節；REPORT.md 只留變更紀錄）。
- `LICENSE`：專屬授權 placeholder（`[[待 David 定案]]`）。
- 去識別化在文件裡的定位（紅隊 #7）：**它是「紀錄文字可以安心交給 AI、匯出、備份」的做法，不是安全機制**；安全靠規則與老師自己的帳號。文件不得宣稱代號＝匿名。

## 10. Placeholder 標記

尚未確定的資料一律寫成 `[[待確認：…]]`，建置後 `grep -rn "\[\[待確認" .` 就是待辦清單。目前已知待確認：授權條款與價格、支援聯絡方式、業務組清單校對、示範資料的班級人數。

## 11. 不做（v3 範圍外）

多租戶／代管、家長端、網頁錄音、行動 App、自動評量生成、David 帳號的任何介入。


## 12. 紅隊裁決（2026-09-10，Stage 2）

Stage 1 由 fresh opus 攻擊 15 條；裁決如下（成立的已寫回上面各節）：

| # | 攻擊 | 裁決 | 落地 |
|---|---|---|---|
| 3 | AI 安裝不確定 | **成立** | `setup.py` 確定性精靈；AI 禁手寫產生檔（§4、§8） |
| 4 | `brew install gws` 撞名、需自建 OAuth client | **成立** | 當時的解法＝改用 formula `googleworkspace-cli`（**v3.0.0-alpha.2 起改走 npm**：`npm i -g @googleworkspace/cli`，三個平台同一種裝法）；備份預設走 Drive 桌面同步夾，gws 為進階（§6 backup） |
| 6 | 不可刪除的未成年人紀錄 | **成立** | 規則允許 owner 刪除＋審計（§7） |
| 9 | 無前置條件 PATCH 靜默蓋字 | **成立** | 回寫必帶 `currentDocument.updateTime`（§6 sync） |
| 10 | 自寫 YAML 解析器 | **成立** | 設定全改 JSON（§4） |
| 11 | 排程靜默死掉 | **成立** | `meta/status`＋網頁紅字（§5、§6） |
| 13 | 動態欄位 schema 演化 | **部分成立** | 欄位寬鬆解析、不當閘（§2.2） |
| 1、2、5、12 | 零基礎老師裝不起來／Console 改版／學校帳號／Windows | **成立但屬產品決策** | 前置條件寫進 README／GUIDE；（2026-09-10：Windows 已支援，見 `docs/PLATFORMS.md`；CI windows-latest 真機驗，但尚無真人老師實測） |
| 7 | 代號＝安全劇場 | **理論性**：代號的目的是讓紀錄文字能交給 AI 與匯出，不是匿名 | 文件改口徑（§9） |
| 8 | 三處一台帳太複雜 | **不成立**：David 5A 已跑一年、語音→本機→網站需要雙向；Drive 只是單向備份 | 維持，但 #9 修好後風險才可接受 |
| 14 | 程式量太大／lock-in | **部分成立** | 砍 `voice_intake.py`（併入 transcribe）、`ledger --related` 延後；`export_records.py` 保證資料可整包帶走 |
| 15 | 值錢的是方法論不是程式 | **交 David**：與陪跑有償化是同一條線 | 寫進給 David 的精進建議 |

## 13. 兩個選用的安裝選項（v3.0.0-alpha.4 追加）

### 13.1 模式 `mode: "cloud" | "local"`

- 住在 `config/kit.json` 頂層；預設 `cloud`；**沒有這個鍵的舊設定一律當 `cloud`**（相容性硬規定）。
  腳本一律經 `lib.mode()` 與 `lib.is_local()` 判斷（唯一例外＝`build_config.py`，
  它要在讀進來的當下驗值合不合法，所以直接讀原始鍵）。
  也鏡射到 `window.KIT.mode` 與 `doctor.py --json` 的頂層 `mode`。
- `local` ＝沒有 Firebase 專案、沒有那六個設定值、沒有網頁、沒有同步、沒有帳單、不能開無頭交辦；
  錄音、Word／PDF、期末素材包、家長信、Drive 備份全部照用。紀錄只有 `data/**/*.md` 一處。
- 分支行為（規格）：`build_config.py` 只產 `site/js/kit-config.js`（不產規則與 firebase-config，
  舊產生檔只提醒不刪，`headless.enabled` 為真直接報錯）；`sync.py` 印一行就 return **退出碼 0**；
  `ledger.py` 自動 offline 只比兩處；`schedule.py` 只掛 backup；`headless.py` 拒跑（退出碼 0）；
  **`doctor.py` 保留每一個 key、雲端項標 `skipped`**（不刪項目——CI 與 AI 代理靠固定 key 清單判斷）。
- 安裝精靈**第 2 步的第一句**就問（`setup.py` 的 `STEP_TITLES` 現在是 0–11）；
  選 local 會自動把第 2、4、5、11 步標成完成，備註「本機模式，略過」。
- local → cloud：改 `mode` → `setup.py` 問六個值 → `build_config.py` → 部署規則與 hosting →
  第一次 `sync.py` 整批推上去。**既有紀錄一則都不會動。**

### 13.2 無頭交辦（LINE）

只有 cloud 模式能開，**需要 Firebase Blaze**（Cloud Functions 不跑在 Spark 方案上）。

- 鏈路：LINE webhook → `functions/line-relay`（Cloud Functions v2／`asia-east1`／Node 20，
  相依只准 `firebase-admin` 與 `firebase-functions` 兩個）→ Firestore
  `headless_events/{webhookEventId}`（語音另存 Storage `headless-inbox/<messageId>.m4a`）→
  relay 只回一句「收到了，電腦醒著時會處理」→ 本機 `scripts/headless.py --once`（每 5 分鐘）
  認領、轉逐字稿、叫 AI 代理 CLI → `append_record.py`（**仍然是唯一寫入通道**）→ `sync.py` →
  LINE 推播一則回報 → `data/headless-audit.jsonl` 一行。
- 事件文件用 `create()` 不用 `set()`：LINE 重送撞 `ALREADY_EXISTS` 成為 no-op（去重，
  而且重送不會把工作端改過的 `status` 蓋回 `pending`）。狀態機 `pending → processing → done|failed`，
  認領用 `currentDocument.updateTime` 前置條件（兩台電腦同時跑也不重複處理）。
- 安全：`firestore.rules.tmpl` 新增 `headless_events`、`headless_pairing` 兩個 `match`，皆
  `allow read, write: if isOwner()`；新增 `storage.rules.tmpl`（預設整份拒絕，`headless-inbox/**`
  那一段只有開了才寫進去）。**relay 走 Admin SDK、完全繞過規則**，它的身分驗證靠
  `x-line-signature`（對 `req.rawBody` 算 HMAC-SHA256，`timingSafeEqual` 比，不合回 401——
  LINE 主控台的 Verify 按鈕送空簽章，回 401 是對的）。金鑰雲端走 `defineSecret`、
  本機走環境變數，`config/kit.json` **只存變數名稱**（有測試守著）。
- 配對碼＝老師自己的 LINE `userId`：未配對前 relay 對任何人都回配對碼（那是唯一拿得到的辦法），
  配好之後不合的 `userId` 靜默丟掉、不回話。真相住 `meta/headless.ownerUserId`，改手機不用重新部署。
- 刻意的設計：**不自動重試**（只認 `--retry <事件id>`，自動重試最糟是同一句話寫成三則）；
  代理沒回 `<<REPORT>>…<<END>>` 就算失敗（rc 0 也不算成功）；
  **一則交辦只推播一次**（LINE 免費方案每月 200 則），失敗也推；推不出去不算整件事失敗。
- `AGENTS-HEADLESS.md` 是無頭代理的行為守則（只走 `append_record.py`、只用代號、不問問題、
  不確定就回報「我沒有寫入」、不碰 `config/`／`setup/`／規則／`site/`／`functions/`），
  由 `headless.py` **整份內嵌進提示詞**——無頭代理不保證會去讀檔案。
- 驗證邊界：模擬器只驗文字那條路；**relay 從未部署到真的專案**，語音那條路（Storage、
  `headless-inbox/**` 規則、抓音檔、無頭裡轉逐字稿）完全沒跑過；測試與 CI 一律走
  `TRK_HEADLESS_AGENT_CMD` 假代理，**永不叫真的模型**。
