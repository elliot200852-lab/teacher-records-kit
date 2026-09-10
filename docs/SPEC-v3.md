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

## 2. 儲存架構（三處一台帳）

```
網站（Firestore，老師的 Firebase 專案）
  roster/main                       {students:[{id,name}], protectedPhrases:[]}
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

- **記錄類型庫** `config/student-streams.library.json`（安裝時勾選，**沒有預設勾任何一種**）：

| id | label | 範圍 scope | 誰用 | 固定欄位 fields | 常用分類詞 tags |
|---|---|---|---|---|---|
| `homeroom` | 導師班級學生紀錄 | `class`（全班每位學生） | 導師 | （無） | #課堂 #主課程 #學習態度 #專注意志 #人際 #情緒 #突破 #親師 #生活 |
| `subject` | 任課老師學生紀錄 | `class` | 科任／任課老師 | 科目 | #課堂 #學習態度 #作業 #專注 #人際 #亮點 #卡點 |
| `case` | 個案追蹤 | `case`（只有被列入的學生） | 導師／輔導／個管 | 來源、主訴／議題、處遇／介入、追蹤與下次 | #初談 #個別晤談 #家長晤談 #轉介 #通報 #結案 |
| `iep` | IEP 個案追蹤 | `case` | 特教／導師 | 本期目標、觀察、調整／支持、會議決議 | #IEP #鑑定 #資源班 #巡迴 #個案會議 #轉銜 |
| `counseling` | 輔導晤談紀錄 | `case` | 輔導老師 | 晤談形式、摘要、評估、下次 | #個別 #團體 #家長 #教師諮詢 #危機 |
| `custom` | 我的學生紀錄類型不在清單裡 | 開放選項 | — | AI 問四件事後產生 | — |

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
| ② IEP／早療追蹤 | `iep` | 目標達成細節多、評鑑格式繁瑣 | 學生卡多 **`goals[]`**（`{id, 領域, 學年目標, 學期目標, 評量方式, 評量標準, 期程}`；領域＝特教：認知／溝通／行動／情緒行為／社會／生活自理／學業；早療：認知／語言／動作／社會情緒／生活自理）；每則 `目標編號`（從該生 goals 選）、`達成情形`（未開始／初步／部分達成／達成／類化）、`證據`（觀察／作品／測驗／家長回報）、`支持策略`、`下一步` | **IEP 追蹤報告**：`report_pack.py --format iep-tracking` → 每目標一表（目標／評量方式與標準／日期序達成情形／證據／摘要）＋期末總評段；會議紀錄沿用三段式（述說前提／會議重點／日後發展目標） |
| ③ 諮商／教練／社工 SOAP | `soap`（取代 counseling） | 會談後要寫 SOAP 或個案紀錄，手寫耗時漏細節 | 個案卡多 **`conceptualization`**（主訴／背景／評估假設／處遇目標／結案標準）；每則 `S 主觀`、`O 客觀`、`A 評估`、`P 計畫`、`會談形式`、`會談次數`、`風險評估`（無／低／中／高）、`下次時間`；每個欄位有一行提示（S＝個案的話與主觀感受；O＝可觀察的行為與事實；A＝專業評估與假設；P＝下一步處遇） | **個案摘要／結案報告**：`report_pack.py --format case-summary` → 個案概念化＋歷程摘要（依次數）＋進展評估＋處遇建議／結案評估 |

- **語音改寫規則**（AGENTS.md §錄音）：逐字稿 → 依方案的欄位骨架改寫（質性評量：每則一個具體事件＋面向＋報告維度；IEP：先對 goals 分段，每段一則、標目標編號與達成情形；SOAP：四段拆分，個案的話進 S、可觀察行為進 O）→ `append_record.py --fields-json`。
- **素材包與草稿分工**（維護成本最低）：`scripts/report_pack.py` 只做確定性的事——依格式把該生所有記錄分組（報告維度／面向／課程／目標／次數）、附統計、附**校方格式骨架與書寫規則**（稱名不稱全名、人稱「他」、先事實後判斷、每則只一個下一步、禁「不是A而是B」等對比句、禁定型語言）成 `exports/<學生>-素材包.md`＋`-prompt.md`；**評語本文由老師的 AI 代理寫**（AGENTS.md 給它固定流程與檢核清單）；`--all` 全班一包。網頁端「產生期末素材」按鈕做同一件事（下載 .md）。
- **格式庫** `config/report-formats.library.json`：`waldorf-homeroom`、`subject-4`、`iep-tracking`、`case-summary`、`custom`（老師貼自己學校的格式標題，AI 依樣產）。每個格式＝`{id,label,sections:[{title,hint,length}],rules:[...]}`。
- **方案庫** `config/verticals.json`：三方案各列「建議記錄類型」「建議業務組」「建議格式」「一句話痛點」，供精靈唸給老師聽；只是建議，不預勾。
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

## 4. 設定檔（單一產生器、三個輸出）

- `config/kit.json`（**JSON，不再自寫 YAML 解析器**——紅隊 #10）：`owner_email`、`id_prefix`、`firebase{project_id,api_key,auth_domain,storage_bucket,messaging_sender_id,app_id}`、`drive{mode:"desktop"|"gws", desktop_dir, backup_folder_id, keep_backups}`、`voice{model,lang}`、`email{...}`。v2 的 `config.yaml` 由 `setup.py --upgrade` 一次轉成 JSON。
- `config/tabs.json`（分頁與向度）：
  ```json
  {"version":3,
   "students":{"enabled":true,"streams":[{"id":"homeroom","label":"導師班級學生紀錄","scope":"class","fields":[],"tags":["#課堂",...],"custom":false}],"help":{...}},
   "courses":{"enabled":true,"categories":[...],"skeleton":["### 課程進度",...],"help":{...}},
   "business":{"enabled":true,"groups":[{"id":"guidance","label":"輔導／個案追蹤","fields":[...],"tags":[...],"custom":false}],"help":{...}}}
  ```
- `scripts/build_config.py` 讀上面兩份，產生：`site/js/kit-config.js`（`window.KIT = {...}`）、`site/js/firebase-config.js`、`firestore.rules`（換 `{{OWNER_EMAIL}}`）。三個輸出都 gitignored。
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
| `build_config.py` | 產生三個 gitignored 輸出 | 見 §4；`--check` 只驗不寫 |
| `doctor.py` | 健檢 | 逐項 ✓／✗：工具在不在、config 齊不齊、gcloud／firebase／gws 登入了沒、Drive 夾 ID 存在且 `trashed=false`、whisper 模型在不在；每個 ✗ 附「怎麼修」與連結；`--json` 給 AI 讀 |
| `install_tools.sh` | 裝依賴 | macOS：Homebrew → `node`、`firebase-tools`、`google-cloud-sdk`、`gws`、`whisper-cpp`、`ffmpeg`；每步先印「要裝什麼、為什麼」；Windows／Linux 印說明不硬裝 |
| `sync.py` | 本機 ↔ Firestore 雙向 | 通用化到四種目標；衝突不覆蓋；回寫前備 `.prev.md`；`--dry-run`；結束寫 `.sync-last-status` 與 Firestore `meta/status.lastSyncAt`。**每個 PATCH 必帶 `currentDocument.updateTime` 前置條件**（紅隊 #9：v2 的無條件回寫會在老師同時編輯時靜默蓋掉他的字）；412 就當衝突處理、不重試覆寫 |
| `append_record.py` | **唯一寫入通道** | `--kind students|class|courses|business --target ID --date --tags --content-file --fields-json --related --source voice|file --task-id`；O_APPEND；寫前後 rid 斷言；名冊真名攔下；審計 `data/audit.jsonl`；`--sync` 順手跑 sync |
| `transcribe.py` | 錄音 → 逐字稿 | 單檔或 `--inbox`（掃 `inbox/*.m4a|mp3|wav|mp4`）；ffmpeg 轉 16k wav → `whisper-cli -m ~/.cache/whisper-cpp/ggml-large-v3-turbo.bin -l zh`（模型缺就從 Hugging Face 下載並印進度）；輸出 `inbox/transcripts/<檔名>.md`，處理完原檔移到 `inbox/done/`；結尾印「接下來請 AI 讀逐字稿、改寫成○○記錄、再用 append_record.py 寫入」；逐字稿永不出本機。**AI 改寫不在腳本裡**（見 AGENTS.md §錄音） |
| `backup.py` | 本機＋Drive 備份 | zip `data/`＋`export.json`（Firestore 全量）→ `backups/`；**兩種 Drive 模式**（紅隊 #4）：`desktop`（預設）＝把 zip 複製進「Google 雲端硬碟」桌面程式的同步夾 `drive.desktop_dir`（零 OAuth、Windows 也行）；`gws`（進階）＝`gws drive files create --json '{"name":..,"parents":[id]}' --upload <cwd 相對路徑>`（先 `gws drive files get --params '{"fileId":..,"fields":"id,name,trashed"}'` 驗存在且 `trashed=false`，找不到就停、**不自建夾**；上傳後比 md5Checksum）。兩種都寫 `data/backups.jsonl` 與 Firestore `meta/status.lastBackupAt`；保留最近 N 份 |
| `ledger.py` | 台帳 | 見 §2.3（`--rebuild`、`--check`；`--related` 延後） |
| `export_records.py` | 匯出取材（Markdown／JSON） | 通用化四種；`--by-tag`、`--related`（把關聯記錄一起帶出）、`--stream`（只匯某一種學生記錄類型） |
| `report_pack.py` | 期末素材包＋草稿 prompt | 見 §3.6；`--format waldorf-homeroom|subject-4|iep-tracking|case-summary|custom`、`--target <id>|all`、`--stream`；輸出 `exports/` |
| `export_docs.py` | 匯出 Word／PDF | 見 §3.5；`.docx` 標準庫 zipfile、`.pdf` 走 headless Chrome（沒有就給 HTML） |
| `schedule.sh` | 排程（選用） | 產生 launchd plist（每日 sync、每週 backup）到 `~/Library/LaunchAgents/`，或印 cron 行；`--uninstall`。**失敗要看得見**（紅隊 #11）：網頁頂端讀 `meta/status`，上次同步／備份超過 7 天就顯示紅字 |
| `parent_email.py`、`pending.py`、`monthly_reminder.py` | 選用 | 沿用 v2 |
| `tests/` | 零網路測試 | 區塊解析、rid、欄位列、關聯、ledger rebuild、build_config 輸出、demo store 種子 |

## 7. 安全規則 `firestore.rules.tmpl`

v2 全部保留，新增：
```
match /business/{groupId} { allow read, write: if isOwner();
  match /records/{recordId} { …與 students/{id}/records 同款… } }
match /meta/{doc} { allow read, write: if isOwner(); }
```
**v3 改為允許擁有者刪除**（`allow delete: if isOwner();`，紅隊 #6：未成年人個資必須能應家長要求刪除）。網頁刪除要二次確認；sync 把刪除傳播到本機檔（整檔遺失時不刪，沿用 David 5A 規則）；`data/audit.jsonl` 記一筆 `{op:"delete", kind, target, rid, at}`。

## 8. 引導流程 `AGENTS.md`（精靈）

- 開頭「你是誰在讀」：假設讀者是 Claude Code 等最高等級代理；**一次只問一題**；每題附「去哪裡拿」連結；問完做、做完驗、驗完由 `setup.py` 寫 `setup/progress.json`（gitignored）再往下。**AI 不手寫任何產生檔**（規則、firebase-config、kit-config）——一律跑腳本。
- 前置條件先講清楚（紅隊 #1）：macOS（Windows 待 David 定案 `[[待確認：Windows 支援]]`）、能開 Firebase 專案的 Google 帳號（學校配發帳號常被管理員鎖住 Cloud Console，GUIDE 要教怎麼判斷、以及改用個人帳號的取捨）、已裝好的 AI 代理。
- 「去哪裡拿」寫**目標＋驗證**而不是逐畫面截圖（紅隊 #2：Console 畫面會改版，AI 自己會找路）。
- 步驟：0 判斷新裝／升級／續裝（讀 progress） → 1 裝工具（跑 `install_tools.sh` 與 `doctor.py`） → 2 Google 帳號與 Firebase 專案（console 連結、逐畫面指引、取 web config） → 3 分頁與向度（學生：名冊來源；課程：先建幾門；業務：勾組＋兩層開放選項） → 4 產生設定與規則（`build_config.py`、`firebase deploy`） → 5 上線（Firebase Hosting 預設；GitHub Pages 備選；嵌入現有站見 embed/） → 6 學生名單與既有資料匯入 → 7 Google Drive 備份夾（老師自己建夾→貼網址→AI 抽 ID→`doctor.py` 驗） → 8 排程 → 9 錄音檔試跑一次 → 10 驗收清單。
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

尚未確定的資料一律寫成 `[[待確認：…]]`，建置後 `grep -rn "\[\[待確認" .` 就是待辦清單。目前已知待確認：授權條款與價格、支援聯絡方式、Windows 支援、業務組清單校對、示範資料的班級人數。

## 11. 不做（v3 範圍外）

多租戶／代管、家長端、網頁錄音、行動 App、自動評量生成、David 帳號的任何介入。


## 12. 紅隊裁決（2026-09-10，Stage 2）

Stage 1 由 fresh opus 攻擊 15 條；裁決如下（成立的已寫回上面各節）：

| # | 攻擊 | 裁決 | 落地 |
|---|---|---|---|
| 3 | AI 安裝不確定 | **成立** | `setup.py` 確定性精靈；AI 禁手寫產生檔（§4、§8） |
| 4 | `brew install gws` 撞名、需自建 OAuth client | **成立** | 正確 formula＝`googleworkspace-cli`；備份預設走 Drive 桌面同步夾，gws 為進階（§6 backup） |
| 6 | 不可刪除的未成年人紀錄 | **成立** | 規則允許 owner 刪除＋審計（§7） |
| 9 | 無前置條件 PATCH 靜默蓋字 | **成立** | 回寫必帶 `currentDocument.updateTime`（§6 sync） |
| 10 | 自寫 YAML 解析器 | **成立** | 設定全改 JSON（§4） |
| 11 | 排程靜默死掉 | **成立** | `meta/status`＋網頁紅字（§5、§6） |
| 13 | 動態欄位 schema 演化 | **部分成立** | 欄位寬鬆解析、不當閘（§2.2） |
| 1、2、5、12 | 零基礎老師裝不起來／Console 改版／學校帳號／Windows | **成立但屬產品決策** | 前置條件寫進 README／GUIDE；Windows 與陪跑搭配交 David 決定（§10 待確認） |
| 7 | 代號＝安全劇場 | **理論性**：代號的目的是讓紀錄文字能交給 AI 與匯出，不是匿名 | 文件改口徑（§9） |
| 8 | 三處一台帳太複雜 | **不成立**：David 5A 已跑一年、語音→本機→網站需要雙向；Drive 只是單向備份 | 維持，但 #9 修好後風險才可接受 |
| 14 | 程式量太大／lock-in | **部分成立** | 砍 `voice_intake.py`（併入 transcribe）、`ledger --related` 延後；`export_records.py` 保證資料可整包帶走 |
| 15 | 值錢的是方法論不是程式 | **交 David**：與陪跑有償化是同一條線 | 寫進給 David 的精進建議 |
