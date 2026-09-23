# 這套系統怎麼運作

給想弄懂內部的人讀：資料放在哪、誰寫得進去、同步怎麼判斷、備份怎麼跑、
安全靠什麼撐住。老師不必讀這份（要裝起來讀 `AGENTS.md`／`docs/GUIDE.md` 就夠）。

設計的正本是 `docs/SPEC-v3.md`（含紅隊裁決）。這份是它的人讀版。
每一版改了什麼看 `CHANGELOG.md`。

腳本全部是 Python 3、三個平台同一份（macOS／Windows／Linux）。**平台差異只寫在
`scripts/hostos.py` 這一支**：工具怎麼裝、執行檔怎麼找、主控台編碼、Drive 同步夾與
Chrome／Edge 的候選、排程掛在哪——其他腳本一律經它，人讀的那一份是 `docs/PLATFORMS.md`。

那一層還管兩件跟「別留下爛攤子」有關的事：

- **下載的可攜工具驗 sha256。** `hostos.DOWNLOADS` 每一項帶一個雜湊，
  `download()` 邊下載邊算，對不上就刪掉 `.part` 直接失敗——不解壓、不留半套。
  少數滾動網址（ffmpeg 的 `ffmpeg-release-essentials.zip`，同一個網址永遠指向最新版）刻意留空，
  CI 的 `urls` job 會把它印成 `rolling`，
  讓「哪幾項沒釘住」永遠是看得見的，而不是被忘掉的。
- **`hostos.kill_tree()` 殺的是整群行程，不是父行程。** Chrome／Edge 印 PDF 會生 renderer 子行程，
  無頭代理會生它自己的子行程；只殺父行程的話，子行程還抓著暫存 profile 目錄，
  Windows 上刪不掉，暫存區留一地垃圾。Windows 走 `taskkill /T /F`、POSIX 走 `killpg`
  （所以那幾支 `Popen` 在 POSIX 上都帶 `start_new_session=True`），失敗才退回單行程 kill。
所有腳本寫出來的文字檔一律用 LF 換行（`newline="\n"`，有測試守著），`.gitattributes` 也鎖 LF；
不然同一則記錄在兩台機器上算出的雜湊會不一樣，同步會一直報「內容不同」。

---

## 1. 三處一台帳

同一則記錄同時活在三個地方，第四個東西負責證明它們對得起來。

```
   ┌──────────────────────────────────────────────────────────────┐
   │                     老師的三個入口                             │
   │                                                              │
   │   網頁打字            本機文字檔            錄音檔              │
   │   （手機/電腦）        （data/*.md）        （inbox/）          │
   └───────┬──────────────────┬──────────────────────┬────────────┘
           │                  │                      │
           │                  │                 transcribe.py
           │                  │                （whisper，本機）
           │                  │                      │
           │                  │                  逐字稿 .md
           │                  │                      │
           │                  │                 AI 讀了改寫
           │                  │                      │
           │                  └──────┬───────────────┘
           │                         │
           │                  append_record.py
           │                 （唯一寫入通道）
           │                         │
           ▼                         ▼
   ┌───────────────┐          ┌──────────────┐
   │  Firestore    │◄────────►│   data/      │
   │（老師自己的     │  sync.py │（本機 md）    │
   │  Firebase）    │  雙向     │              │
   └───────┬───────┘          └──────┬───────┘
           │                         │
           │                    backup.py（每週）
           │                         │
           │  export.json 併進 zip   ▼
           └───────────────►  ┌──────────────────┐
                              │ Google 雲端硬碟   │
                              │（老師自己的）      │
                              └──────────────────┘

           三處各記各的，ledger.py --check 負責對帳
```

三個地方各自的角色：

| 地方 | 角色 | 誰寫 |
|---|---|---|
| **Firestore**（老師自己的 Firebase 專案） | 隨時打得開的那一份；手機上看到的就是它 | 網頁、`sync.py` |
| **本機 `data/`** | 純文字、可以直接讀、可以交給 AI、可以 grep | `append_record.py`、`sync.py` 的回寫 |
| **Google 雲端硬碟** | 單向備份，出事的時候的救命稻草 | `backup.py` |
| **`data/ledger.jsonl`** | 台帳。每一則一行，記它在三處各自的狀態 | `ledger.py --rebuild` |

**為什麼要三處？** 因為三個入口的性質不同：網頁隨手記、文字檔可以整批處理與版本比對、
錄音是最省力的輸入。要讓這三者同時存在，就得有一個機制證明它們沒有分岔——那就是台帳。

---

## 2. 資料模型

### 學生記錄再分一層：記錄類型（stream）

學生記錄不是一個平面。期末要寫評語的質性觀察、導師的日常觀察、科任老師的課堂觀察、
個案追蹤、IEP／早療的目標追蹤、會談紀錄是**各自獨立的簿子**，
各有自己的欄位、分類詞、與「哪些學生在裡面」。這一層叫**記錄類型（`stream`）**：

- **可選清單**：`config/student-streams.library.json`（`qualitative` / `homeroom` /
  `subject` / `case` / `iep` / `soap` ＋ 清單外的開放選項 `custom`）。**這份庫只是選單**，
  安裝時列出來讓老師勾，**一種都不預先勾**；改它不影響已經在跑的資料。
- **舊 id 靠 `aliases` 相容**：v3 alpha 把 `counseling` 併進 `soap`，舊設定寫 `counseling`
  照樣讀得到（檔名仍照舊 id 走，資料不必搬）。
- **`vertical`**：`qualitative` / `iep` / `soap` 這三種各掛一個垂直方案 id
  （見下面「三個垂直方案」），只是標記，不影響資料形狀。
- **`card`**：一種類型可以宣告它需要學生卡上多帶什麼——`{"goals":true}`（`iep`）、
  `{"conceptualization":true}`（`soap`）。網頁依這個決定明細頁頂端出不出「目標清單」／「個案概念化」卡。
- **`fields[].type`**：`text` / `date` / `select` / `multiselect`（寫檔時用「／」串起來）/
  `goal`（從該生卡片的 `goals` 選一條）。每個欄位都帶一行 `hint`，網頁當表單提示、
  AI 改寫語音時當骨架。
- **老師勾了什麼**：`config/tabs.json` 的 `students.streams`，每一筆
  `{id,label,desc,scope,fields,tags,custom}`。
- **`scope`** 只有兩種：`class`＝名冊上每一位學生都在這個類型裡；
  `case`＝只有被列入的學生才在。
- **雲端不分集合**：同一位學生所有類型的紀錄都在 `students/<代號>/records`，
  靠文件裡**必填的 `stream` 欄位**分流（安全規則要求 `create` 時 `stream` 是非空字串，
  且 `update` 不准改它）。v2 留下來、沒有 `stream` 的舊紀錄一律當 `homeroom`。
- **本機一種類型一個檔**：`data/students/<代號>/<類型id>.md`，
  `homeroom` 例外——沿用 v2 的 `observations.md`，所以舊資料原地可用。
- **班級整體觀察**也跟著分：每一種 `scope: class` 的類型各一個
  `data/class/<類型id>.md`（`homeroom` 同樣是 `observations.md`）；
  雲端仍是同一個 `class-observations` 集合，一樣靠 `stream` 分流。
- **目標清單**由 `lib.targets()` 產：students ← 每位學生 × 他所屬的每一種類型各一個目標；
  class ← 每一種 `class` 型類型各一個。同步、台帳、匯出共用這份清單。

業務記錄的「業務組」是同一套機制的另一個實例（庫＋勾選＋兩層開放選項），
差別只在業務組沒有 `scope`、也不牽涉名冊。

### 三個垂直方案（`vertical`）與期末格式（`reportFormat`）

`config/verticals.json` 是**方案庫**：三個方案各帶 `label`、`pain`（一句話痛點）、
`suggest`（建議的 `streams` / `groups` / `format`）與 `voiceRule`（語音逐字稿要改寫成什麼骨架）。
安裝精靈在學生段之前先問一句「你最像哪一種？」，**把建議唸出來，一項都不預先勾**
（`setup.py` 的 `ask_vertical()`；答案檔的鍵是 `vertical`，`"none"` ＝都不是）。

方案在資料上只留兩個標記，都在 `config/tabs.json`：

| 鍵 | 意思 | 誰讀 |
|---|---|---|
| `tabs.vertical` | 這位老師最像哪一種（或空字串） | `setup.py` 收尾印摘要；`build_config.py` 鏡像到 `window.KIT.vertical`；網頁的方案卡只加一個「建議」徽章 |
| `tabs.reportFormat` | 期末的**預設**格式 id | 網頁的「產生期末素材」預選它；`report_pack.py --format` 隨時可以換 |

**方案不是勾選。** 老師勾了什麼仍以 `students.streams` / `business.groups` 為準——
選了方案卻一種都沒勾，是合法的結果。

`config/report-formats.library.json` 是**格式庫**：一種格式＝
`{id, label, for:[stream id…], groupBy, dimensions, sections:[{title,hint,length}], rules:[…], audit:[…]}`。
`build_config.py` 把整份格式庫鏡像進 `window.KIT.reportFormats`，網頁才知道當前記錄類型
吃得到哪幾個格式。`custom` 多一個 `customFile`，指向老師自己貼的 `config/report-format.custom.json`。

### 學生卡（`data/students/<代號>/card.json` ⇄ `students/<代號>`）

卡片放的是**會被回頭改的底稿**，不是一則一則的記錄（記錄仍然只走 `append_record.py` 寫進 `.md`）：

| 欄位 | 誰用 | 形狀 |
|---|---|---|
| `goals[]` | `iep` | `{id, 領域, 學年目標, 學期目標, 評量方式, 評量標準, 期程}`，`id` 就是記錄裡「目標編號」欄填的值 |
| `conceptualization` | `soap` | 五格：`主訴` / `背景` / `評估假設` / `處遇目標` / `結案標準` |

- **`goal` 型欄位是真的閘**：`append_record.py` 會拿「目標編號」去比對卡片上的 `goals[].id`，
  對不上就退出碼 2 並列出可用的目標——這是全系統唯一會擋下來的欄位（其餘欄位都只是表單建議）。
- 範本＝`templates/card.example.json`；安裝時可由答案檔的 `students.cards.<代號>` 帶進來，
  **卡片已經有內容的那一塊，重跑安裝不會覆蓋**。

### 整體課程紀錄（`data/courses/<課程id>/card.json` ⇄ `courses/{課程id}`，alpha.5）

課程也有一張同類型的卡，只放一個欄位：`overview`（純字串，上限 20000 字）＋
`overviewUpdatedAt`（伺服器時間）。逐日紀錄回答「這一天教了什麼」，`overview` 回答
「這門課整體是什麼樣子」——不分天，期末課程總結、明年再開同一門課時看的是它。
雙向同步走跟學生卡一樣的「不覆蓋」規則（§5）；PATCH 只帶 `updateMask=["overview"]`。
Word／PDF／Markdown 匯出都把它放在逐日紀錄最前面；課程一覽卡寫過的顯示「整體紀錄 ✓」。

### 雲端（Firestore）

```
roster/main                       {students:[{id,name,streams:[類型id…]}], protectedPhrases:[]}
students/{代號}                    每生一張卡
students/{代號}/records/{rid}      每則紀錄，必帶 stream: "<類型id>"（規則擋著）
class-observations/{rid}          班級整體觀察，同樣帶 stream
courses/{課程id}                   {title,kind,season,weeks,teacherName,order,
                                   overview,overviewUpdatedAt}   ← 整體課程紀錄（alpha.5）
courses/{課程id}/records/{rid}
business/{組id}                    {label,fields:[...],tags:[...],custom:bool}
business/{組id}/records/{rid}
meta/config                       設定鏡像（sync.py 寫 version／dataVersion／tabs；
                                   網頁上臨時加的記錄類型寫進 studentStreams）
meta/status                       {lastSyncAt,lastBackupAt}（網頁頂端讀它）
```

**軟刪（alpha.5）**：任何一則 `records/{rid}`（含 `class-observations`）被網頁刪除時不會真的消失，
只多蓋三個欄位 `deleted:true`／`deletedAt`／`deletedBy`；規則的 `delete` 一律拒絕，
真刪只有 `scripts/purge_deleted.py` 走 Admin SDK／使用者權杖做得到（見 §3「可以刪除」）。

### 本機（`data/`，全部 gitignored）

```
data/roster.csv                   代號,姓名,類型 —— 唯一有真名的檔；第三欄＝這位學生列入
                                  哪幾種 scope:case 的類型，分號分隔（case;iep）
data/contacts.csv                 （選用）家長信箱
data/students/<代號>/observations.md    homeroom（沿用 v2 檔名）
data/students/<代號>/<類型id>.md         其餘每一種類型各一個檔（qualitative.md、iep.md、soap.md…）
data/students/<代號>/card.json          學生卡：IEP 的 goals[]、SOAP 的 conceptualization
data/class/observations.md              班級整體觀察：homeroom
data/class/<類型id>.md                   其餘每一種 scope:class 類型各一個
data/courses/<課程id>/records.md
data/courses/<課程id>/card.json         整體課程紀錄：overview（純字串，不分天）
data/business/<組id>/records.md
data/ledger.jsonl                 台帳
data/audit.jsonl                  append_record.py 的寫入稽核＋同步刪除的稽核
data/backups.jsonl                每次備份的 zip 路徑、md5、Drive file id
data/.sync-state.json             上次同步時每個目標有哪些 rid（含名冊第三欄的基準）
data/.auto-dim-tags.json          （選用）評量維度補標判斷過哪幾則：目標 → rid → 正文雜湊
```

### 一則記錄長什麼樣

四種來源（網頁、文字檔、錄音、匯入）產出的形狀完全一樣：

```json
{
  "date": "2026-09-10",
  "stream": "case",
  "tags": ["#人際", "#親師"],
  "body": "……（去識別化正文）",
  "fields": {"期限": "2026-09-20", "辦理情形": "辦理中"},
  "related": ["students/S-03/2026-09-10", "courses/fractions/2026-09-09-1435"],
  "source": "web" | "voice" | "file",
  "contentHash": "……",
  "editedOnWeb": false,
  "deleted": true,               // 軟刪才有這三個欄位（alpha.5）；一般紀錄沒有
  "deletedAt": "……",
  "deletedBy": "<uid 或 null>"
}
```

`deleted`／`deletedAt`／`deletedBy` 只在這一則被**軟刪**時才存在；一般存活的紀錄沒有這三個欄位。
`stream` 只有 `students` 與 `class` 這兩種記錄會有，而且**必填**（規則擋著）。
`fields` 業務記錄與有固定欄位的記錄類型（`qualitative`、`subject`、`case`、`iep`、`soap`）都會有。
`related` 是三個分頁串起來的鍵；`rid` 在同一位學生底下是唯一的，
所以關聯只寫 `students/<代號>/<rid>`，不用也不必指定類型。

### 記錄 id（`rid`）的規則

- 當天**第一則** ＝ 日期本身：`2026-09-10`
- **之後每一則** ＝ 日期＋建立時間：`2026-09-10-1435`
- 同一分鐘再撞 → 補到秒：`2026-09-10-143512`

**id 一旦建立就不能改，`date` 欄位也不准改**（安全規則擋著）。
所以「這一則是哪天記的」事後無法竄改。

### 本機 markdown 的區塊格式

```
## 2026-09-10 14:35 #親師 #人際
期限：2026-09-20
辦理情形：辦理中
關聯：students/S-03/2026-09-10; courses/fractions/2026-09-09-1435

正文……（可多段）
```

- 標題列：`## 日期 [時間] #標籤…`，當天第一則不帶時間。
- 欄位列（業務檔，以及有固定欄位的記錄類型——`qualitative`、`subject`、`case`、`iep`、`soap`）：
  緊接標題，每行 `鍵：值`（全形冒號）。
  **解析器很寬鬆**——任何 `鍵：值` 行都收進 `fields`，就算那個鍵不在該組／該類型設定的欄位裡也照收。
  這是刻意的：`fields` 只是表單建議，不是 schema 閘，**改欄位名不需要 migration**。
- `關聯：` 行用分號分隔。
- 空一行之後是正文。**檔案只加不刪**。
- 每個檔的檔頭（front matter）記著它是哪一種：`kind`、`stream`，
  所以檔案自己就說得出「我是 S-03 的個案追蹤」。

範例看 `templates/observation.example.md`（全班型的記錄類型）、
`templates/case-records.example.md`（個案型的記錄類型）、
`templates/course-records.example.md`、`templates/business-records.example.md`。

---

## 3. 安全

### 真正的牆在伺服器端

資料存在**老師自己的** Firebase 專案，`firestore.rules` 寫死：

```
request.auth != null
  && request.auth.token.email == '<擁有者信箱>'
  && request.auth.token.email_verified == true
  && request.auth.token.firebase.sign_in_provider == 'google.com'
```

不符合的一律 deny，**連預設規則都是 `allow read, write: if false`**。
所以就算有人拿到網址、看了網頁原始碼、抄走那六個 Firebase 設定值，
伺服器一樣不回傳任何一個字。

「把入口藏起來」只是介面層的方便，不是安全機制（`embed/EMBED-AND-SECURITY.md` 講得更細）。

### 代號的定位——講對這件事

**代號不是匿名機制。**

代號存在的理由是：**這些文字要能安心交給 AI 讀、能匯出、能備份到雲端硬碟。**
記錄裡寫 `S-03` 而不是真名，這幾件事才做得下去。

但 `data/roster.csv` 一對照就知道 `S-03` 是誰。所以：

- **不要**跟老師說「就算外流也認不出是誰」。
- **要**說「保護你資料的是伺服器規則與你自己的帳號；代號讓你可以放心把文字拿去用」。
- `data/roster.csv` 本身要當成個資看待——它 gitignored、不進備份以外的任何地方。

### 三道防線擋住真名寫進記錄

1. **網頁**：寫入前把名冊上的真名自動代換成代號。
2. **`append_record.py`**：正文／欄位／標籤出現名冊真名就**拒寫**（退出碼 5）。
   極少數情況（對象根本不是本班學生）可以用 `--allow-names` 放行，**會寫進稽核記錄**。
3. **`sync.py`**：兩個方向都攔——本機要推上去、雲端要寫回來，出現真名都擋下不同步。

### 可以刪除（兩段式，alpha.5 起）

理由是未成年人的紀錄必須能應家長要求刪除，但「前端一鍵真刪」風險太大，所以拆成兩段：

- **網頁上的刪除＝軟刪**：二次確認後寫的是 `{deleted:true, deletedAt, deletedBy}`，文件留在
  Firestore；規則的 `delete` **一律拒絕**（`allow delete: if false;`），前端沒有辦法真刪。
- `sync.py` 把「雲端那則被軟刪」當成「雲端已刪」傳播到本機檔，並寫一筆進 `data/audit.jsonl`
  （`op:"delete"`，只記 rid 與內容指紋，不留正文）；同步、匯出、素材包、台帳一律排除軟刪的則
  （例外是 `backup.py` 的 `export.json`，故意保留，萬一是誤刪還找得回來）。
- **整個檔案不見或變成空的時候一律不刪任何東西**——那多半是檔案出事，不是老師要刪。
- **真刪只有一條路**：老師本人在終端機跑 `scripts/purge_deleted.py --rid <id> --target <種類/代號>
  --confirm`（或 `--all --confirm` 全刪），走 `gcloud` 使用者權杖，安全規則管不到它，**不可逆**；
  每刪一則另記一筆 `{op:"purge", …}`。無頭交辦永遠不准跑這一支（`AGENTS-HEADLESS.md` 第 5 條）。
  個資法的刪除請求，最終完成點就是這一步。

---

## 4. 寫入為什麼只有一條通道

`scripts/append_record.py` 是唯一被允許寫入本機記錄檔的東西。**AI 代理不准直接編輯 `data/` 底下的 md。**

原因：AI 直接編輯很容易「把新的一則插進同一天的舊區塊前面」或整檔重寫。
那會讓既有記錄的 id 重新編號，下一次同步就把它們當成「舊的刪了、新的加了」——
**雲端那邊的紀錄會被誤刪**。

所以四道閘全部在動檔案之前跑完：

| 閘 | 擋什麼 | 失敗的退出碼 |
|---|---|---|
| 旗標檢查 | `--kind students` 一定要帶 `--stream`（`--kind class` 只在剛好只有一種全班型類型時自動帶）；`courses`／`business` 不准帶 `--stream` | 2 |
| 目標白名單 | `--kind` ＋ `--target` ＋ `--stream` 必須是設定裡真的存在的目標（含「這位學生有沒有被列入這個個案型類型」） | 3 |
| 真名攔截 | 正文／欄位／標籤出現名冊真名 | 5 |
| 只追加 | `O_APPEND` 從檔尾追加，不 seek、不重寫、不插入 | — |
| id 不變 | 寫前後各解析一次，斷言「舊 id 一個都沒變、剛好多一則」；違反就把檔案**截回原長度**再異常退出 | 9 |

最後一道的意思是：**寧可什麼都沒寫，也不留半截。**

---

## 5. 同步與衝突

`scripts/sync.py`，本機 markdown ⇄ Firestore 雙向。四種記錄共用同一套邏輯
（目標清單由 `lib.targets()` 產生）。

規則（每一條都是為了「不要弄丟老師的字」）：

| 情況 | 做法 |
|---|---|
| 檔案裡有、雲端沒有、而且以前沒同步過 | 推上去（推的時候一定帶 `stream` 與 `sourceFile`） |
| 雲端那則被網頁改過（`editedOnWeb`）、本機那則自上次同步後沒動 | 寫回檔案（先備份成 `.<檔名>.prev.md`）；寫回哪個檔看那則的 `stream` |
| **兩邊都改** | **不覆蓋**，印出來讓老師自己決定 |
| 雲端那則被刪掉（以前同步過、現在不見了） | 從本機檔也刪掉，寫進 `data/audit.jsonl`。但整檔不見／變空就一律不刪 |
| 雲端那則被**軟刪**（`deleted:true`，alpha.5） | 視同「雲端已刪」，走上面同一條路；本機原本沒有那一則（例如網頁新增後立刻刪）就什麼都不做 |
| 只有本機課程卡 `overview` 改，或只有網頁「整體課程紀錄」卡改（alpha.5） | 跟學生卡同一套「不覆蓋」規則（§2「整體課程紀錄」）；兩邊都改就都不動、記一筆 note |
| 任一方向出現名冊真名 | 攔下不同步 |
| 開了 `auto_dim_tags`，自動推導維度的學生紀錄沒有任何代表標籤（alpha.6） | 上面全部做完之後請 AI 代理判斷，**只加不刪**地補上代表標籤（見下面「評量維度補標」） |

**已知限制：本機檔整檔重寫時的並發寫入（這一版不修）。** 上表裡「寫回檔案」「網頁新增」「網頁刪除」三條，
`sync.py` 的 `sync_target` 都是「讀進整個 md → 改 → 整檔寫回」，中間沒有鎖、也沒有重讀比對。
這段期間若 `append_record.py` 剛好往同一個檔追加一則（最可能是無頭交辦或另一個終端機同時在記），
**那一則會被整檔寫回蓋掉，`.prev.md` 備份裡也沒有它**。窗口是毫秒級（讀檔到寫檔之間沒有網路呼叫），
但不是零。評量維度補標換檔前會重讀比對、不同就不換（見下面那一節），只剩「重讀到 `os.replace`」的極短窗口。

### 學生卡也是雙向的（`goals` / `conceptualization`）

卡片上的兩塊底稿跟記錄走同一條「不覆蓋」規則（`sync.py` 的 `sync_student_card()`）：

| 情況 | 做法 |
|---|---|
| 只有本機 `card.json` 改 | 推上雲端 `students/<代號>` |
| 只有網頁改（明細頁的「目標清單」／「個案概念化」卡） | 寫回 `data/students/<代號>/card.json` |
| **兩邊都改** | **不覆蓋**，印出來叫老師打開檔案跟網頁比對後留一邊 |

基準是上次同步時存下來的卡片指紋（`.sync-state.json` 的 `_cards`），所以判斷得出「誰改過」。
`--dry-run` 也會跑這一段，只是不寫。

**推上去的 PATCH 只帶 `updateMask=["goals","conceptualization"]`。**
`students/<代號>` 這張卡上還有別的東西（姓名鏡像、網頁自己寫的統計欄位），
無 mask 的整份 PATCH 會把它們靜默清掉——跟 `roster/main` 要留 `protectedPhrases` 是同一個理由。

### 名冊第三欄是雙向的

「哪些學生列入哪些個案型記錄類型」兩邊都能改：本機是 `data/roster.csv` 的第三欄，
雲端是 `roster/main.students[].streams`（網頁上按「＋ 列入學生」／「移出」就是在改它）。
`sync.py` 拿上次同步的狀態當基準做三方比對：

| 情況 | 做法 |
|---|---|
| 只有本機改 | 推上雲端 |
| 只有網頁改 | 回寫 `data/roster.csv` 第三欄，並印一行說改了誰 |
| **兩邊都改** | **不覆蓋**，雲端維持原樣、印出來讓老師決定 |
| 網頁上有這位學生、本機名冊沒有 | 印一行提醒，不自動加（名冊是唯一有真名的檔，不能靠同步長出人來） |

姓名永遠以本機 `data/roster.csv` 為準——雲端的名字只是鏡像。

### 網頁上臨時加的記錄類型／業務組：只提示，不改 config

網頁的「＋ 選擇類型」與「＋ 新增業務組」只寫到雲端（`meta/config.studentStreams`、
`business/<組id>` 卡）。`sync.py` 每次跑會比對 `config/tabs.json`，
發現雲端有、設定沒有的，就印一行「請跟 AI 說要加進去」——**它不會自己動 `config/tabs.json`**。

理由：`config/tabs.json` 是本機記錄檔與安全規則的依據，改它是有後果的事
（會多出資料夾、會影響規則），必須由 AI 明確地做，不能當成同步的副作用。
網頁那邊加完也會跳同樣的提示。

### 評量維度補標（`auto_dim_tags`，alpha.6，選用）

網頁的五維度小籤是讀取時用格式庫的 `tagMap`＋`keywords` 當場推的、不寫回；關鍵詞也會漏。
開了 `config/kit.json` 的 `auto_dim_tags`，`sync.py` 在**上面全部做完之後**叫 `scripts/auto_dim_tags.py`
（`--no-auto-tags` 跳過；`--dry-run` 只列會送判斷的則數、不叫 AI）：

| 環節 | 做法 |
|---|---|
| 適用範圍 | 只看學生紀錄；只看 `dashboard.html` `deriveFormatFor()` 會推導的類型（沒有「報告維度」欄位、不是帶目標清單／個案概念化卡片的、格式庫有帶推導表的格式吃它）。維度、說明（`sections` 的 hint）、代表標籤（`tagMap` 裡各維度排第一個的標）全從 `config/report-formats.library.json` 讀 |
| 挑哪些 | 雲端那份在、沒軟刪、沒 `editedOnWeb`、`contentHash` 與本機一致；正文不空；標籤裡沒有任何代表標籤（黏在一起的標拆開比）；正文過真名攔截（只比對名冊全名，只寫名攔不到）；標題列能只在尾端接上標籤（試接後讀回對得上）；「目標＋rid＋正文雜湊」不在 `data/.auto-dim-tags.json`。本機 md、`.prev.md`、所在資料夾任一寫不進去，或 md 是捷徑（symlink）→ 整個目標不送 AI。沒補成過的排到最後 |
| 送出去什麼 | 一批最多 30 則、每次同步最多 `max_batches` 批（預設 2），剩下的印「還有 N 則等下次同步」；只有 `代號/rid` 與正文，提示詞走 stdin；不含名冊、欄位、原標籤 |
| 收回來什麼 | 一個 JSON 物件（容忍前後的程式碼框）；只認這一批的 id × 格式裡的維度名，值不合格的那一則整則不收、沒回的當沒判斷 |
| 失敗 | JSON 壞、逾時（`timeout_sec`，殺整棵行程樹）、非 0 結束、找不到 CLI → 這一批零寫入、印一行警告、不記判斷、後面批次不跑；`auto_dim_tags.run()` 不丟例外、不 `die()`，退出碼不變 |
| 寫雲端 | 先重讀一次雲端與本機，確認 AI 判斷期間兩邊都沒動；`PATCH` 只帶 `updateMask=[tags, contentHash]` 與 `currentDocument.updateTime`。前置條件不成立 → 跳過、不記、下次再來。`editedOnWeb` 不碰 |
| 寫本機 | 雲端成功之後才寫；**只在那一則的標題列尾端接上缺的代表標籤**，其他每一行逐位元組不動（標題列非標籤文字、重複鍵欄位列、`\r`、BOM 都留著——不用 `render_block` 整則重畫）。接完用 `lib.parse_block` 讀回驗 tags／欄位／正文雜湊，不符不寫。先備份 `.<檔名>.prev.md`（這一輪同步已經回寫過這個檔的話，保留同步前那一份），**換檔前重讀一次、跟一開始讀到的逐位元組比**，不同（例如 `append_record.py` 剛好追加了一則）就不換、當成本機沒寫成；相同才暫存檔＋`os.replace` 換新。標題列尾端只去半形空白，全形空白留著。寫完重新解析，雜湊對得上才記為判斷過 |
| 本機沒寫成 | 用剛才 PATCH 回傳（`documents:commit` 的 `writeResults[].updateTime`）的 updateTime 當前置條件，把雲端 `tags`／`contentHash` 改回原值；回滾也失敗 → 印警告（網頁同時改過的話下一輪會報衝突，要老師比對）。記一次沒補成 |
| 一直沒補成 | AI 給不出能用的判斷（JSON 壞、維度名不對、沒回）或本機沒寫成，在判斷檔 `failures` 記一次（rid＋正文雜湊；正文改了歸零）；**同一份正文滿 2 次就記成看不出維度、不再送**並印警告。找不到 CLI、逾時、非 0 結束是環境問題，不記。接不上標籤的檔（例如只用 `\r` 換行）同一份內容只警告一次（記在 `unfit`） |
| 判斷紀錄 | `data/.auto-dim-tags.json`：目標 → rid → 正文雜湊。判定零個維度也記；正文改了才重判；老師自己拿掉補上的標而正文沒改，不會再補回去 |
| 下一輪 | 雲端 `contentHash` 已經是新標籤的指紋，本機也是 → 零推送、零回寫、零衝突；新標籤裡有代表標籤 → 不會再送 AI |

**先雲端、後本機**：反過來的話，雲端前置條件不成立時本機已經改了，下一輪就變成「兩邊都改」的衝突。
雲端寫成、本機寫入失敗時，當場用 PATCH 回傳的 updateTime 把雲端改回原樣，那一則不記判斷、之後重判；
叫 AI 之前已經先確認檔案寫得進去，所以不會每次同步都「補上、寫不進、改回」白叫一次 AI。
回滾也失敗、或行程剛好在兩者之間被殺：網頁沒動過的話，下一輪同步照本機那一份把雲端蓋回去
（少了補的標、老師的字一個不少）；網頁剛好也改過就會報衝突，照衝突的規矩讓老師比對。
**已知沒修**：補標換檔前重讀比對之後，「重讀到 `os.replace`」之間的極短窗口仍擋不掉並發追加；`sync.py` 本來的回寫連重讀比對都沒有（見本節開頭的「已知限制」）。

AI 代理叫起來的同步（無頭交辦照 `AGENTS-HEADLESS.md` 跑的 `sync.py`，或補標代理自己）帶環境變數
`TRK_NO_AUTO_TAGS`，那一次不補標——不讓 AI 再叫 AI、把一則交辦拖過逾時。
三家代理的非互動叫法（不給工具、提示詞走 stdin）住 `hostos.AGENT_CLIS[*]["oneshot"]`，人讀版在 `docs/PLATFORMS.md`。

### 前置條件式寫回（這條特別重要）

每一個回寫 Firestore 的 PATCH **都帶 `currentDocument.updateTime` 前置條件**。
雲端在我們讀完之後又被改過，伺服器會拒絕這次寫入（400 FAILED_PRECONDITION；要求不存在但已存在則是 409），`sync.py` 就把它當衝突處理，
**不重試、不覆寫**。

沒有這一條的話：老師正在手機上打字，同時電腦上的排程跑了一次同步——他打的字會被靜靜蓋掉。

同步完會寫兩個地方：本機 `.sync-last-status`，以及 Firestore 的 `meta/status.lastSyncAt`。

### 排程失敗要看得見

排程由 `scripts/schedule.py` 掛：macOS 是 launchd LaunchAgent、Windows 是工作排程器（XML 定義檔）、
Linux 是 crontab 區塊（三個平台的細節與移除方式見 `docs/PLATFORMS.md`）。

掛幾支由 `wanted_jobs()` 決定，**不是固定兩支**：

| 工作 | 什麼時候會掛 | 頻率 | 跑什麼 |
|---|---|---|---|
| `sync` | 只有 cloud 模式 | 每天 07:00 | `sync.py` |
| `backup` | 一定有 | 每週日 08:00 | `backup.py --quiet` |
| `headless` | 只有開了無頭交辦 | **每 5 分鐘** | `headless.py --once --quiet` |

`--uninstall` 不管開了哪幾項都一律清乾淨；`--status` 對沒開的那幾項印
「（沒開這個功能，本來就不該掛）」，免得看起來像掛失敗。

三種排程都會靜默死掉——電腦沒開機、權限被擋、學校電腦鎖住排程。
所以網頁頂端讀 `meta/status`，顯示「上次同步 X 天前・上次備份 Y 天前」，
**任一超過 7 天就顯示紅字**。

驗證排程有沒有生效，**看那個數字，不要看排程有沒有掛上**。

---

## 6. 備份的兩種模式

`scripts/backup.py`。zip 裡有兩樣東西：`data/` 全份，加上 `export.json`
（Firestore 全量快照——網頁上打的字也一起備走）。

| 模式 | 怎麼跑 | 適合誰 |
|---|---|---|
| **desktop**（預設、零設定） | 把 zip 複製進「Google 雲端硬碟」桌面程式的同步資料夾（`drive.desktop_dir`），剩下交給那個程式自己上傳 | 所有人。不用 OAuth |
| **gws**（進階） | 用 `@googleworkspace/cli` 直接上傳到指定的 Drive 資料夾，上傳後比對 md5 | 已經在用 gws、不想裝桌面程式的人 |

同步夾的根目錄名稱與位置不固定：可能叫 `My Drive` 也可能叫 `我的雲端硬碟`；
macOS 在 `~/Library/CloudStorage/GoogleDrive-<信箱>/` 底下，Windows 常掛成磁碟機代號
（`G:\My Drive\教學紀錄備份`）或家目錄下的資料夾。`setup.py` 靠 `hostos.drive_desktop_candidates()`
自動偵測候選當預設值，`doctor.py` 發現設定的路徑不存在時會把候選列出來。

**gws 模式有一條鐵則：找不到那個資料夾就停手，絕不自己建一個新的。**
自建的話備份會靜靜地跑到別的地方去，而老師以為他有備份。
上傳前先驗那個資料夾存在且 `trashed=false`。

兩種模式都會寫 `data/backups.jsonl`（zip 路徑、md5、Drive file id）
與 Firestore 的 `meta/status.lastBackupAt`，並只保留最近 `drive.keep_backups` 份本機 zip
（Drive 上的不動）。

### 台帳對帳

```
python3 scripts/ledger.py --rebuild    # 掃 data/ 四種檔重建台帳
python3 scripts/ledger.py --check      # 三處對帳，印三欄表
```

`--check` 比對本機、Firestore、與**最近一次備份 zip 裡實際有的東西**（是打開 zip 數的，不是猜的），
印出不一致清單：本機有網站無／網站有本機無／內容 hash 不同／最近一次備份缺哪些。
**退出碼 0 ＝ 三處對得上，1 ＝ 有差。**
`--offline` 不連網只比本機與備份，`--json` 給 AI 讀。

---

## 7. 錄音管線

```
老師錄一段     →  inbox/*.m4a
                     │
             transcribe.py --inbox
                     │
         ffmpeg 轉 16kHz 單聲道 wav（暫存，用完就刪）
                     │
         whisper.cpp（本機跑，模型在 ~/.cache/whisper-cpp/）
                     │
         inbox/transcripts/<檔名>.md（每行帶 [HH:MM:SS]）
         原始錄音移到 inbox/done/
                     │
             ★ AI 讀逐字稿，改寫成記錄 ★   ← 這一步不在腳本裡
                     │
         append_record.py --source voice --task-id …
                     │
                  sync.py
```

**幾件要講清楚的：**

- **全程在老師自己的電腦上跑。** 錄音與逐字稿都不出本機，`inbox/` 整個是 gitignored 的。
- **改寫不在腳本裡，是 AI 的工作。** 腳本只負責把聲音變成文字；
  「這段話該整理成哪一種記錄、寫成什麼樣子」是判斷，交給 AI，而且**改完要念給老師確認才寫入**。
- 改寫的三個原則：一律用代號、寫具體事件不寫評語、口語變書面但不美化。
- 模型第一次會自動從 Hugging Face 下載（約 1.6GB，有進度條）。
- whisper 會把人名、專有名詞、台語詞聽錯——**AI 改寫的時候要順手修掉**，
  不要把錯字原封不動寫進記錄。

---

## 8. 設定：一個產生器，五個輸出

```
config/kit.json            ──┐
config/tabs.json           ──┤
config/business-groups.    ──┤
  library.json             ──┤
config/student-streams.    ──┼──►  build_config.py  ──►  site/js/kit-config.js
  library.json             ──┤                          site/js/firebase-config.js
config/report-formats.     ──┤                          firestore.rules
  library.json             ──┤                          storage.rules
config/verticals.json      ──┤                          .firebaserc
firestore.rules.tmpl       ──┤
storage.rules.tmpl         ──┘
VERSION                    ──┘（版本字串進 window.KIT.version）
```

- **`.firebaserc` 是第五個輸出，而且是唯一一個「合併」而不是「整份重寫」的**：它把
  `firebase.json` 裡固定寫死的 `hosting.target: "web"` 對應到 `config/kit.json` 算出來的
  Hosting site（`firebase.hosting_site` 留空就等於 `project_id`——多數老師一個專案一個
  預設 site，這裡零設定）。已經存在的 `.firebaserc` 只改 `projects.default`（原本沒值才填）
  與 `targets.<project_id>.hosting.web` 這兩處，使用者自己加的其他 alias、其他 targets 都留著；
  內容沒變就不重寫。只有像同一個專案掛了不只一個 site 的進階安裝才需要填 `hosting_site`。

兩份選單 library（業務組、記錄類型）進的是**網頁上「＋ 選擇類型」「＋ 新增業務組」要顯示的選單**；
格式庫進的是網頁「產生期末素材 ▾」要列哪幾個格式（`window.KIT.reportFormats`）；
老師實際勾了什麼一律看 `config/tabs.json`（含 `vertical` 與 `reportFormat` 兩個標記）。

- **輸出全部 gitignored，而且永遠由腳本產生。** AI 代理不准手寫——
  手寫規則檔一旦把信箱打錯，資料庫就變成誰都讀不到，或更糟：誰都讀得到。
- **`storage.rules` 每次都產**（來源是 `storage.rules.tmpl`）：沒開無頭交辦的時候它是整份拒絕，
  開了才把 `headless-inbox/**` 那一段填進去。這樣老師日後自己在 Console 開了 Storage，
  也不會拿到一個誰都寫得進去的 bucket。**本機模式只產 `site/js/kit-config.js` 一個檔**（見 §11）。
- **規則裡的信箱是插進字串的，所以要跳脫。** `owner_email` 一律去空白轉小寫，
  再經跳脫才插進規則模板——寬鬆的信箱格式加上原樣字串替換，等於讓一個
  `x'||true||'someone@a.bc` 這種值把 `isOwner()` 變成恆真。
- **範本值不放行。** `owner_email` 還是 `you@example.com`、專案 id 還是範本值的時候，
  `build_config.py` 直接 exit 1。以前它照樣產檔、印「下一步：部署安全規則」然後 exit 0，
  老師與 AI 都會以為裝好了。`setup.py` 內部呼叫、測試與 CI 用 `--allow-placeholders` 降級成提醒。
- **部署一律帶 `--only`。** 無參數的 `firebase deploy` 會連 hosting、firestore、storage、functions
  一起送，其中一項沒設好就整批失敗，錯誤訊息還指不到真正的原因。
- 設定用 **JSON 不用 YAML**（v2 那個自寫的 YAML 解析器已經拆掉了）。
  JSON 不能寫註解，所以說明放在 `_註解_欄位名` 這種鍵裡，程式忽略所有底線開頭的鍵。
- 安裝是**確定性的**：`setup.py` 同樣的答案跑幾次結果都一樣。
  AI 只負責解釋題目、幫老師找答案、讀錯誤訊息。
- 範本：`config/kit.example.json`、`config/tabs.example.json`、
  `templates/answers.example.json`、`setup/progress.example.json`、`site/js/kit-config.example.js`。

---

## 9. 網站

`site/dashboard.html`——單檔、無框架、無建置步驟。

- 設定用傳統 `<script src>` 載入（`window.KIT`、`window.FIREBASE_CONFIG`、`window.OWNER_EMAIL`），
  **不是 ES module**（v2 是，照 v2 抄會壞）。
- Firebase SDK 用動態 `import()` 載，**只有非示範模式才載**。
- **示範模式**：`KIT.demo === true` 或網址加 `?demo=1`。完全不連 Firebase，
  資料是假的、只存在那個瀏覽器（localStorage），頂端有黃色橫幅講清楚。
- `scripts/build_preview.py` 把 dashboard 加設定內聯成**單一可離線開啟的 HTML**
  → `preview/teacher-records-kit-預覽.html`。零外部相依，`file://` 點兩下就開。
- **學生分頁頂端一排「記錄類型」切換**，只顯示設定裡勾的那幾種（加上網頁上臨時加、
  還沒寫進 `config/tabs.json` 的；同 id 以設定檔為準）。全班一覽、本月已記／未記、
  明細與新增表單都**依當前類型**過濾與帶欄位；一位學生的明細頁可以切看他在各類型的紀錄，
  只列他真的在裡面的類型。`scope: case` 的類型多兩顆按鈕：「＋ 列入學生」與每張卡上的「移出」
  （移出只改名冊，不刪任何紀錄）。
- 分頁狀態在網址的 `#` 後面（`#students` `#courses` `#business` `#class` `#s/<代號>` …），
  所以手機的返回鍵是通的。
- 頁尾顯示版本，來源是 `window.KIT.version`（見 §13）。
- 規則過舊會被即時偵測：新增或刪除被舊規則擋下來時，畫面直接顯示
  「你的安全規則還是舊版，請重新部署」。

不做：影音上傳到網頁、搜尋引擎、多租戶。

---

## 10. 匯出：Word 與 PDF

同一件事兩條路，內容一樣、場合不同：網頁端隨手按，腳本端出正式檔。

### 網頁端（零相依、離線可用）

- 明細頁右上角一顆「**匯出 ▾**」，學生／班級整體觀察／課程／業務組共用，
  選單內容由 `renderExportUI()` 依當前明細的種類生出來；
  學生分頁一覽另有「**匯出所有學生 ▾**」小面板（勾記錄類型、日期範圍、要不要含班級整體觀察），
  輸出一份文件、每位學生一節。
- **版面只有一份**：`buildExport()` 組出 HTML，Word 與 PDF 只差外殼。
- **Word ＝ `.doc`**：瀏覽器把那份 HTML 包成 Word 相容格式（`application/msword`）直接下載，
  **不載任何外部函式庫**，離線也按得動。
- **PDF ＝ 列印**：開一個只有標題、記錄與欄位表的列印版面（帶 `@media print` 樣式）再 `window.print()`，
  老師在列印對話框選「儲存為 PDF」，手機同樣可行。
  彈出視窗被瀏覽器擋掉時改成在同一頁蓋一層列印覆蓋層，不會卡死。

### 腳本端（`scripts/export_docs.py`）

- **`.docx` 是真的 OOXML**：用標準庫 `zipfile` 直接寫最小的 OOXML 封包，**零第三方套件**。
- **`.pdf` 借本機的 Chrome**：`--headless=new --print-to-pdf`。
  Chrome 不在預設路徑時用環境變數 **`TRK_CHROME`** 指定執行檔（測試也是靠它換掉 Chrome）。
  **Windows 沒裝 Chrome 就自動改用 Microsoft Edge**（`msedge.exe` 也在候選名單裡）。
- **找不到 Chrome 就退回 HTML**：不當成失敗，改成留下排版好的 `.html`，
  並印一行「用瀏覽器開這個檔 → 列印 → 儲存為 PDF」。
- 輸出目錄預設 `exports/`（`.gitignore` 擋著），檔名 `<種類>-<對象>[-<類型>]-<日期>`。
- 資料來源與 `export_records.py` 共用（`--local` 只讀本機 markdown、絕不連網）。

**匯出檔一律是「去識別化正文＋名冊姓名」**——因為它是老師自己要看、要交出去的文件。
所以兩端都在文件開頭印一行提醒：這份檔含姓名，只留在自己的機器上。

---

## 10.5 期末產出：素材包與草稿分工

期末要寫的東西（質性評語、IEP 追蹤報告、個案摘要）是這套系統最後一哩，
但它**刻意切成兩半**：確定性的那一半給腳本，寫字的那一半給 AI 與老師。

### 腳本只分組，不寫評語

`scripts/report_pack.py --format <格式> --target <代號>|--all` 做四件事，全部是確定性的：

1. 依格式的 `for` 撈該生那幾種記錄類型的紀錄（`--stream` 可以指定，`--from`／`--to` 可以框日期）；
2. 依 `groupBy` 分組——質性＝報告維度 → 面向 → 課程；IEP＝每目標一表、日期序的達成情形；
   SOAP＝依會談次數的 S／O／A／P 與風險趨勢；
3. 附統計與**缺漏提示**（`dimensions` 裡沒有紀錄的分組、零紀錄的目標、缺號的會談都會照實列出來）；
4. 把格式的 `sections`／`rules`／`audit` 原樣寫成一份草稿指令。

輸出兩個檔到 `exports/`（gitignored）：`<代號>-<格式>-素材包.md` 與 `<代號>-<格式>-prompt.md`；
`--all`（或 `--target all`）另出一份 `_index.md` 全班總表。
**它不呼叫任何 LLM、不生成任何一句評語**，所以同一批資料跑幾次結果都一樣。

### AI 寫本文，老師定稿

草稿指令最下面那段固定指令要求：材料只有素材包、每一句都要指得出是哪一則（哪一天）、
素材包裡沒有的事一個字都不補、缺的段落照實寫「本期未蒐集到紀錄」。
寫完 AI 要拿 `audit` 清單**逐條自檢並把沒過的列出來**，不准偷偷改掉。
`waldorf-homeroom` 的「整體感受」那一段更直接寫在規則裡：**由老師自己寫，AI 不代筆。**

網頁端的「產生期末素材 ▾」（明細頁）與「產生全班期末素材 ▾」（一覽頁）做同一件事，
下載的 .md 就是素材包＋檔尾的 prompt。

### 為什麼這樣分

- **維護成本**：格式一改（學校換表格、法規改段落），只要動 `config/report-formats.library.json`
  或老師自己的 `config/report-format.custom.json`，腳本一行都不用改；
  要是把評語生成寫進腳本，每換一種格式就得改程式，而且輸出不可重現。
- **不代管、不介入的定位**：這套 kit 從不持有老師的金鑰，也不該持有他的判斷。
  評語是專業判斷與對這個孩子的責任，腳本沒有資格代寫——它只能保證「素材沒有漏、規則有附上」。
- **定稿規矩**：老師定稿之後那一版就是那一版，AI 不回頭「順手修正」；
  這跟 §14 的「不做自動評量生成」是同一條線。

---

## 11. 兩種模式：cloud 與 local

`config/kit.json` 頂層的 `mode` 決定整套系統要不要碰雲端。只有兩個值：`cloud`（預設）與 `local`。
沒有這個鍵的舊設定一律當成 `cloud`。這條是相容性的硬規定，改它就會弄壞所有既有安裝。

腳本一律經 `lib.mode(kit)` 與 `lib.is_local(kit)` 判斷，不自己看那個鍵；
唯一的例外是 `build_config.py`，它要在讀進來的當下驗值合不合法（只能是 `cloud` 或 `local`），
所以那一支直接讀原始值。

| | `cloud` | `local` |
|---|---|---|
| Firebase 專案與那六個設定值 | 要 | **不用** |
| 手機網頁、電腦⇄手機同步 | 有 | **沒有** |
| 無頭交辦（LINE） | 可以開 | **不能開** |
| 錄音轉逐字稿、Word／PDF、期末素材包、家長信、Drive 備份 | 有 | 有 |
| 帳單 | 老師自己的（免費額度內） | 沒有帳單 |

本機模式的紀錄就只有 `data/**/*.md` 一處，台帳因此只比兩處。

**各支腳本在本機模式下的行為**（照這張表實作，改行為要連這張表一起改）：

| 腳本 | 本機模式做什麼 |
|---|---|
| `build_config.py` | **只產 `site/js/kit-config.js`**，不產 `firestore.rules`、`storage.rules`、`site/js/firebase-config.js`、`.firebaserc`（本機模式沒有 Hosting，用不到 target 對應）。以前是 cloud 留下來的舊產生檔只提醒、**不刪**（刪別人的檔不是設定產生器的事）。`headless.enabled` 為真時直接報錯 |
| `sync.py` | 印一行「本機模式沒有雲端，不用同步」就 return，**退出碼 0**——排程與 `append_record --sync` 都會叫到它，非 0 會被當成故障 |
| `ledger.py` | 自動進 offline，只比對本機與備份兩處，並明說「只比對兩處」 |
| `schedule.py` | 只掛 `backup` 一支 |
| `headless.py` | 直接拒跑（退出碼 0） |
| `doctor.py` | **每一個檢查項目的 key 都保留，雲端那幾項標成 `skipped`**（不刪項目、也不報 ✗）。CI 與 AI 代理靠固定 key 清單判斷，項目消失會被誤判成健檢本身壞了。`--json` 頂層多出 `mode` 與 `headless` |

**local → cloud**：改 `config/kit.json` 的 `mode`（或重跑一次安裝精靈）→ `setup.py` 問那六個值 →
`build_config.py` → 部署規則與 hosting → 第一次 `sync.py` 把既有紀錄整批推上去。
**既有紀錄一則都不會動。** 反方向（cloud → local）刻意不刪已經產生的規則檔，只印一行提醒。

---

## 12. 無頭交辦（LINE，選用）

老師在外面用手機對 LINE 講一句話，回家的時候紀錄已經寫好了。**只有 cloud 模式能開**，
而且需要 Firebase Blaze 方案（Cloud Functions 在免費的 Spark 方案上不會跑）。

```
  手機 LINE
      │  webhook（POST，帶 x-line-signature）
      ▼
  functions/line-relay        Cloud Functions v2 / asia-east1 / Node 20
      │  · HMAC-SHA256(rawBody, channel secret) 用 timingSafeEqual 比，不合回 401
      │  · 寫 Firestore（Admin SDK，繞過安全規則）
      │  · 語音另存 Storage headless-inbox/<messageId>.m4a
      │  · 只回一句「收到了，電腦醒著時會處理」
      ▼
  Firestore  headless_events/{webhookEventId}
      │        status: pending → processing → done / failed
      │
      │  每 5 分鐘（排程）
      ▼
  scripts/headless.py --once
      │  · 前置條件 PATCH 認領（兩台電腦同時跑也不會重複處理）
      │  · 語音 → inbox/ → transcribe.py（本機 whisper）
      │  · 把 AGENTS-HEADLESS.md 整份內嵌進提示詞
      ▼
  AI 代理 CLI（非互動）
      │
      ▼
  append_record.py（唯一寫入通道）→ sync.py
      │
      ▼
  LINE 推播一則回報   ＋   data/headless-audit.jsonl 一行
```

**資料落在哪**

| 東西 | 位置 |
|---|---|
| 原始訊息 | Firestore `headless_events/{webhookEventId}` |
| 語音檔（雲端） | Cloud Storage `headless-inbox/<messageId>.m4a`，**不自動刪** |
| 配對候選 | Firestore `headless_pairing/{userId}` |
| 配對的唯一真相 | Firestore `meta/headless.ownerUserId` |
| 語音檔（本機） | `inbox/line-<messageId>.m4a`，轉完移到 `inbox/done/` |
| 逐字稿 | `inbox/transcripts/<檔名>.md`（本機 whisper，不出本機） |
| 紀錄 | `data/**/*.md`（走 `append_record.py`） |
| 稽核 | `data/headless-audit.jsonl`，一則一行 |
| 排程 log | `logs/headless.log` |

文件 id 優先用 LINE 的 `webhookEventId`（沒有就退到 `message.id`，再沒有就退到時間戳），
寫入走 `create()` 而非 `set()`——LINE 重送就撞 `ALREADY_EXISTS` 變成 no-op。
這既是去重，也保證重送不會把工作端已經改過的 `status` 蓋回 `pending`。
**去重的保證只在 `webhookEventId` 真的有值的時候成立**；退到時間戳那一層只是保證寫得進去。

**安全**

- `firestore.rules.tmpl` 新增 `headless_events` 與 `headless_pairing` 兩個 `match`，
  兩個都是 `allow read, write: if isOwner()`。檔尾的整份預設拒絕照舊。
- 新增 `storage.rules.tmpl`：預設整份拒絕，`headless-inbox/**` 那一段**只有開了無頭交辦才會被寫進去**。
  沒開的人日後自己在 Console 開了 Storage，也不會拿到一個誰都寫得進去的 bucket。
- **relay 用 Admin SDK，完全繞過安全規則。** 那兩條規則管的是打開網頁的人；
  relay 那一端擋住陌生人的是 LINE 的簽章驗證。
- **金鑰只住兩個地方**：雲端是 Functions 的 `defineSecret`（`KIT_LINE_CHANNEL_SECRET`／
  `KIT_LINE_CHANNEL_TOKEN`，走 Secret Manager），本機是環境變數。
  `config/kit.json` 只存**變數名稱**，有一條測試守著「金鑰本身永遠不進任何檔案」。
  環境變數要寫進登入時會載入的設定檔（`~/.zshrc`、Windows 的使用者環境變數）——
  臨時 `export` 的那個值，五分鐘後跑的排程看不到。
- **配對碼就是老師自己的 LINE `userId`。** 還沒配對之前，relay 對任何人都回配對碼——
  那是老師唯一拿得到自己 id 的辦法。配好之後，不合的 `userId` **靜默丟掉、不回任何話**
  （對陌生人零回饋）。所以文件把「立刻完成配對」寫成安裝的一部分，不是之後再說。

**幾個刻意的決定**

- **不自動重試。** 失敗就停在 `failed`，等老師 `--retry <事件id>`。自動重試最糟的情況是
  同一句話被寫成三則紀錄，而老師得自己找出來刪掉——那比「沒寫成功」難收拾得多。
- **代理沒有回 `<<REPORT>>…<<END>>` 就算失敗**，即使退出碼是 0。沒有那段回報，
  就無法確定它到底有沒有寫進去，不能當成功。
- **一則交辦只推播一次**（不推「開始處理了」「轉逐字稿完成了」）——LINE 免費方案每個帳號
  每月只有 200 則推播。失敗也推，因為老師唯一的回饋就是那句「收到了」，不推等於靜靜地掉。
  推不出去不算整件事失敗——紀錄已經寫好了。
- **電腦睡著或關機**：訊息排在 Firestore 裡，一則都不會掉，也一則都不會被處理。
  電腦醒來五分鐘內補完。macOS 的排程用 `StartInterval: 300` 而不是 `StartCalendarInterval`，
  正是因為後者睡醒不補跑。

---

## 13. 版本控制

- **`VERSION`** ＝ 這份程式是哪一版（語意化版本：主版本．次版本．修訂）。**唯一的版本來源**。
- **`CHANGELOG.md`** ＝ 每一版改了什麼。**動過 `firestore.rules.tmpl` 的版本，
  那一段要明寫「規則有動，升級後必須重新部署規則」**——這是升級唯一容易漏掉的一步。
- 發版：改 `VERSION` ＋ 加 `CHANGELOG.md` 一段 ＋ `git tag v<版本>`，三件一起。
- 更新：`git pull` 或重新下載，**只覆蓋程式與範本**；
  `config/`、`data/`、`setup/progress.json` 與所有產生檔絕對不覆蓋。
  更新後必跑 `python3 scripts/build_config.py`。

### `VERSION` 流到哪三個地方

| 落點 | 誰寫 | 看得到什麼 |
|---|---|---|
| `site/js/kit-config.js` 的 `window.KIT.version` | `build_config.py`（`build_preview.py` 也內聯它） | **網頁頁尾直接顯示「版本 <版本字串>」**；沒有那個鍵就顯示「版本未知」 |
| `doctor.py` 的標頭 | `doctor.py` | 健檢第一行「健檢：<資料根目錄>（kit <版本>，<平台>）」；`--json` 也帶 `version` |
| Firestore `meta/config.version` | `sync.py`（連同 `dataVersion: 3` 與 `tabs` 鏡像一起寫） | 這個資料庫**最後一次是用哪一版同步／部署的** |

### 版本比對是自動的

`doctor.py` 連得上網的時候會抓 `meta/config.version` 下來跟本機 `VERSION` 比：

- 一樣 → 「資料庫上次部署的版本與這份程式一致」過關。
- 程式比資料庫新 → 印出「資料庫 X／這份 Y」，並告訴你重新部署規則再同步一次。
- 資料庫上還沒有版本記錄 → 叫你跑一次 `sync.py` 把版本寫上去。
- 沒登入、沒網路、還沒接 Firebase、或加了 `--skip-network` → **跳過這一項，不算失敗**。

這一項是**選用項目**（黃色驚嘆號，不擋健檢通過）——它是提醒，不是閘。
真正會擋下操作的是網頁端的即時偵測：新增或刪除被舊規則擋下來時，
畫面直接顯示「你的安全規則還是舊版，請重新部署」。

`meta/config` 另外存 `dataVersion`（整數 `3`，＝資料格式版本），
那是給未來的升級腳本判斷「要不要轉資料」用的，跟程式版本是兩件事。

---

## 14. 這套不做什麼

多租戶、代管、家長端、網頁錄音、行動 App、自動評量生成、作者對老師資料的任何介入。

「不做自動評量生成」是刻意的：`report_pack.py` 只把素材分好組、附上格式骨架與規則，
**評語本文由老師的 AI 寫、由老師定稿**（見 §10.5）。這條線不會因為方便而讓步。

`export_records.py` 的存在本身就是一個承諾：**你的資料隨時可以整包帶走，不會被鎖在這個 kit 裡。**
