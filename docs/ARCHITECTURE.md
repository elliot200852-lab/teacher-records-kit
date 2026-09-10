# 這套系統怎麼運作

給想弄懂內部的人讀：資料放在哪、誰寫得進去、同步怎麼判斷、備份怎麼跑、
安全靠什麼撐住。老師不必讀這份（要裝起來讀 `AGENTS.md`／`docs/GUIDE.md` 就夠）。

設計的正本是 `docs/SPEC-v3.md`（含紅隊裁決）。這份是它的人讀版。
每一版改了什麼看 `CHANGELOG.md`。

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

### 雲端（Firestore）

```
roster/main                       {students:[{id,name}], protectedPhrases:[]}
students/{代號}                    每生一張卡
students/{代號}/records/{rid}      每則觀察
class-observations/{rid}          班級整體觀察
courses/{課程id}                   {title,kind,season,weeks,teacherName,order}
courses/{課程id}/records/{rid}
business/{組id}                    {label,fields:[...],tags:[...],custom:bool}
business/{組id}/records/{rid}
meta/config                       設定鏡像（sync.py 寫）
meta/status                       {lastSyncAt,lastBackupAt}（網頁頂端讀它）
```

### 本機（`data/`，全部 gitignored）

```
data/roster.csv                   代號,姓名 —— 唯一有真名的檔
data/contacts.csv                 （選用）家長信箱
data/students/<代號>/observations.md
data/class/observations.md
data/courses/<課程id>/records.md
data/business/<組id>/records.md
data/ledger.jsonl                 台帳
data/audit.jsonl                  append_record.py 的寫入稽核＋同步刪除的稽核
data/backups.jsonl                每次備份的 zip 路徑、md5、Drive file id
data/.sync-state.json             上次同步時每個目標有哪些 rid
```

### 一則記錄長什麼樣

四種來源（網頁、文字檔、錄音、匯入）產出的形狀完全一樣：

```json
{
  "date": "2026-09-10",
  "tags": ["#人際", "#親師"],
  "body": "……（去識別化正文）",
  "fields": {"期限": "2026-09-20", "辦理情形": "辦理中"},
  "related": ["students/S-03/2026-09-10", "courses/fractions/2026-09-09-1435"],
  "source": "web" | "voice" | "file",
  "contentHash": "……",
  "editedOnWeb": false
}
```

`fields` 只有業務記錄會有。`related` 是三個分頁串起來的鍵。

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
- 欄位列（只有業務檔會用）：緊接標題，每行 `鍵：值`（全形冒號）。
  **解析器很寬鬆**——任何 `鍵：值` 行都收進 `fields`，就算那個鍵不在該組設定的欄位裡也照收。
  這是刻意的：組的 `fields` 只是表單建議，不是 schema 閘，**改欄位名不需要 migration**。
- `關聯：` 行用分號分隔。
- 空一行之後是正文。**檔案只加不刪**。

範例看 `templates/observation.example.md`、`templates/course-records.example.md`、
`templates/business-records.example.md`。

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

### 可以刪除

v3 起安全規則允許擁有者刪除記錄（`allow delete: if isOwner();`）。
理由是未成年人的紀錄必須能應家長要求刪除。配套：

- 網頁刪除要**二次確認**
- `sync.py` 把雲端的刪除傳播到本機檔，並寫一筆進 `data/audit.jsonl`
- **整個檔案不見或變成空的時候一律不刪任何東西**——那多半是檔案出事，不是老師要刪

---

## 4. 寫入為什麼只有一條通道

`scripts/append_record.py` 是唯一被允許寫入本機記錄檔的東西。**AI 代理不准直接編輯 `data/` 底下的 md。**

原因：AI 直接編輯很容易「把新的一則插進同一天的舊區塊前面」或整檔重寫。
那會讓既有記錄的 id 重新編號，下一次同步就把它們當成「舊的刪了、新的加了」——
**雲端那邊的紀錄會被誤刪**。

所以四道閘全部在動檔案之前跑完：

| 閘 | 擋什麼 | 失敗的退出碼 |
|---|---|---|
| 目標白名單 | `--kind` ＋ `--target` 必須是設定裡真的存在的目標 | 3 |
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
| 檔案裡有、雲端沒有、而且以前沒同步過 | 推上去 |
| 雲端那則被網頁改過（`editedOnWeb`）、本機那則自上次同步後沒動 | 寫回檔案（先備份成 `.<檔名>.prev.md`） |
| **兩邊都改** | **不覆蓋**，印出來讓老師自己決定 |
| 雲端那則被刪掉（以前同步過、現在不見了） | 從本機檔也刪掉，寫進 `data/audit.jsonl`。但整檔不見／變空就一律不刪 |
| 任一方向出現名冊真名 | 攔下不同步 |

### 前置條件式寫回（這條特別重要）

每一個回寫 Firestore 的 PATCH **都帶 `currentDocument.updateTime` 前置條件**。
雲端在我們讀完之後又被改過，伺服器會回 **412**，`sync.py` 就把它當衝突處理，
**不重試、不覆寫**。

沒有這一條的話：老師正在手機上打字，同時電腦上的排程跑了一次同步——他打的字會被靜靜蓋掉。

同步完會寫兩個地方：本機 `.sync-last-status`，以及 Firestore 的 `meta/status.lastSyncAt`。

### 排程失敗要看得見

排程（`schedule.sh` 掛的 launchd）會靜默死掉——電腦沒開機、權限被擋。
所以網頁頂端讀 `meta/status`，顯示「上次同步 X 天前・上次備份 Y 天前」，
**任一超過 7 天就顯示紅字**。

驗證排程有沒有生效，**看那個數字，不要看排程有沒有掛上**。

---

## 6. 備份的兩種模式

`scripts/backup.py`。zip 裡有兩樣東西：`data/` 全份，加上 `export.json`
（Firestore 全量快照——網頁上打的字也一起備走）。

| 模式 | 怎麼跑 | 適合誰 |
|---|---|---|
| **desktop**（預設、零設定） | 把 zip 複製進「Google 雲端硬碟」桌面程式的同步資料夾（`drive.desktop_dir`），剩下交給那個程式自己上傳 | 所有人。不用 OAuth，Windows 也行 |
| **gws**（進階） | 用 `googleworkspace-cli` 直接上傳到指定的 Drive 資料夾，上傳後比對 md5 | 已經在用 gws、不想裝桌面程式的人 |

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

## 8. 設定：一個產生器，三個輸出

```
config/kit.json          ──┐
config/tabs.json         ──┤
config/business-groups.  ──┼──►  build_config.py  ──►  site/js/kit-config.js
  library.json             │                          site/js/firebase-config.js
firestore.rules.tmpl     ──┘                          firestore.rules
```

- **三個輸出全部 gitignored，而且永遠由腳本產生。** AI 代理不准手寫——
  手寫規則檔一旦把信箱打錯，資料庫就變成誰都讀不到，或更糟：誰都讀得到。
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
- 分頁狀態在網址的 `#` 後面（`#students` `#courses` `#business` `#class` `#s/<代號>` …），
  所以手機的返回鍵是通的。
- 規則過舊會被即時偵測：新增或刪除被舊規則擋下來時，畫面直接顯示
  「你的安全規則還是舊版，請重新部署」。

不做：影音上傳到網頁、搜尋引擎、多租戶。

---

## 10. 版本控制

- **`VERSION`** ＝ 這份程式是哪一版（語意化版本：主版本．次版本．修訂）。
- **`CHANGELOG.md`** ＝ 每一版改了什麼。**動過 `firestore.rules.tmpl` 的版本，
  那一段要明寫「規則有動，升級後必須重新部署規則」**——這是升級唯一容易漏掉的一步。
- 發版：改 `VERSION` ＋ 加 `CHANGELOG.md` 一段 ＋ `git tag v<版本>`，三件一起。
- 更新：`git pull` 或重新下載，**只覆蓋程式與範本**；
  `config/`、`data/`、`setup/progress.json` 與所有產生檔絕對不覆蓋。
  更新後必跑 `python3 scripts/build_config.py`。
- **目前沒有自動的版本比對提醒**。Firestore 的 `meta/config.version` 存的是資料格式版本（整數 3），
  不是程式版本，網頁也不讀它。要確認規則是不是舊的：對 `CHANGELOG.md`，
  或直接重新部署一次（重複部署沒有害處）。

---

## 11. 這套不做什麼

多租戶、代管、家長端、網頁錄音、行動 App、自動評量生成、作者對老師資料的任何介入。

`export_records.py` 的存在本身就是一個承諾：**你的資料隨時可以整包帶走，不會被鎖在這個 kit 裡。**
