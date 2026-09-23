# 無頭交辦：在手機上講一段話，它自己變成一則紀錄

這是 kit 的**選用**功能。裝不裝都不影響其他任何東西，而且預設是關的。

一句話：**你對自己的 LINE 官方帳號講一段話（或打一行字），電腦醒著的時候會自動把它整理成一則紀錄，
並回你一句「記好了什麼」。你從頭到尾不用打開終端機、不用開網頁、不用等在電腦前面。**

錄音（步驟 9）已經很省力了，但它還是要你「回到電腦前、把檔案拖進 inbox、跟 AI 說一聲」。
無頭交辦拿掉的是最後那三件事——放學路上、開完會走回辦公室的路上，講完就結束。

---

## 先確認你要不要（三件事講在前面）

1. **要 Firebase 的 Blaze（隨用隨付）方案。** 收訊息的那一小段程式（Cloud Function）在免費方案上不能用。
   Blaze 是「用多少算多少」，而且每個月有一份免費額度——一位老師每天傳幾則訊息的用量，
   帳單幾乎一定是 **0 元**。但 Google 規定要**綁一張信用卡**才能升級。
   不想綁卡就不要開這一項，kit 的其他功能完全不受影響。
   （不放心的話，Firebase Console 的「用量與帳單」裡可以設預算警示，例如超過 1 美元就寄信通知你。）
2. **只有雲端模式有。** 本機模式（`mode: local`）沒有雲端可以接收 LINE 的訊息，
   安裝精靈在本機模式下不會問你這一題。
3. **電腦要醒著。** 訊息會一直乖乖等在雲端，但「整理成紀錄」這件事是在**你自己的電腦上**做的
   （逐字稿與 AI 都在本機）。電腦關著就先不處理，下次開機的五分鐘內會補做完，再回報給你。

---

## 隱私：東西會經過誰

| 東西 | 經過哪裡 | 誰看得到 |
|---|---|---|
| 你錄的那段語音 | 你的手機 → LINE 的伺服器 → **你自己的 Firebase 專案**（Cloud Storage）→ 你的電腦 | 你。LINE 當然會經手（你本來就是用 LINE 傳的），但除此之外它只落在你自己的專案裡 |
| 逐字稿 | **只在你的電腦上**（whisper.cpp 本機轉錄） | 你 |
| 整理成紀錄這件事 | 你電腦上的 AI 代理 | 你訂的那一家 AI（跟你平常叫它做事一樣） |
| 最後那一則紀錄 | `data/` 底下的 md 檔 ＋ 你自己的 Firestore | 你 |

**賣你這套 kit 的人不經手任何一段。** relay 那支程式是部署在**你自己的** Firebase 專案裡，
金鑰是你自己的，帳單是你自己的。

`headless_events`（LINE 傳來的原始訊息）與 `headless-inbox/`（語音檔）都被安全規則鎖成
「只有你那個 Google 帳號讀得到」。語音檔**永遠不會被自動刪除**——要清是你自己去 Firebase Console 清。

---

## 它是怎麼運作的

```
你的手機                你自己的 Firebase 專案                     你的電腦
  │                     ┌───────────────────────┐              ┌──────────────────┐
  │ 語音／文字           │ line-relay            │              │ headless.py      │
  ├────────────────────▶│ （Cloud Function）     │              │ （每 5 分鐘醒一次）│
  │                     │  · 驗簽章              │              │                  │
  │◀────────────────────┤  · 寫 headless_events │◀─────────────┤  · 抓還沒處理的   │
  │  「收到了，電腦醒著   │  · 語音存 Storage      │              │  · 轉逐字稿       │
  │    時會處理」        │  · 回一句收到          │              │  · 叫 AI 代理     │
  │                     └───────────────────────┘              │  · append_record  │
  │                                                            │  · sync           │
  │◀───────────────────────── LINE 推播 ────────────────────────┤  · 回報給你       │
  │  「已記到 S-07 的個案追蹤：…」                                └──────────────────┘
```

兩段回覆的意思不一樣，看得懂就不會誤會：

- **「收到了，電腦醒著時會處理」** ＝ 雲端收到了。這時候還沒有任何紀錄。
- **「已記到 …」** ＝ 真的寫進去了。這一句才是完成。

---

## 安裝（大約十五分鐘，AI 代理會帶你走；這裡是給人看的版本）

### ① 升級 Firebase 到 Blaze

Firebase Console → 左下角「升級」→ 選 Blaze → 綁信用卡。
建議順手設一個預算警示（「用量與帳單 → 詳細資料與設定 → 修改預算」），設 1 美元就好。

### ② 開一個 LINE Messaging API 頻道

1. 打開 https://developers.line.biz/console/ ，用你的 LINE 帳號登入。
2. 沒有 Provider 就先「Create a new provider」（名字隨便，例如你的名字）。
3. 在那個 Provider 底下「Create a new channel」→ 選 **Messaging API**。
4. 填 channel name（例如「我的教學紀錄」）、category 隨便選、同意條款，建立。
5. 建好之後有兩個東西要拿：
   - **Channel secret**：在「Basic settings」分頁，往下找 `Channel secret`。
   - **Channel access token（long-lived）**：在「Messaging API」分頁最下面，
     `Channel access token` 按「Issue」發一個，複製起來（**只會顯示這一次**）。
6. 同一個「Messaging API」分頁裡：
   - **Auto-reply messages**：關掉（不然它會用罐頭訊息蓋掉我們的回覆）。
   - **Greeting messages**：關不關隨你。
   - **Webhook**：等一下才填（要先部署才有網址）。
7. 用手機掃那一頁的 QR code，把這個官方帳號**加為好友**。

### ③ 把兩個金鑰設成環境變數（**不寫進任何檔案**）

kit 只會在設定檔裡記「環境變數叫什麼名字」，值永遠只在你的系統裡。

**重點：要寫進「每次登入都會載入」的地方**，不能只在終端機臨時 `export`——
排程每 5 分鐘跑一次的那支程式讀不到臨時變數。

- **macOS／Linux**：把這兩行加到 `~/.bashrc`（或 `~/.zshrc`）最後面，存檔後重開終端機：
  ```bash
  export KIT_LINE_CHANNEL_SECRET='貼上 Channel secret'
  export KIT_LINE_CHANNEL_TOKEN='貼上 Channel access token'
  ```
  （macOS 上如果排程是用 launchd 跑的，launchd 不讀 `.bashrc`——
  跑 `python3 scripts/doctor.py` 時它會告訴你現在讀不讀得到。）
- **Windows**：開始 → 搜尋「編輯系統環境變數」→「環境變數」→ 在「使用者變數」按「新增」，
  名稱分別填 `KIT_LINE_CHANNEL_SECRET` 與 `KIT_LINE_CHANNEL_TOKEN`，值貼上去。
  **設完要關掉所有終端機視窗再開新的。**

### ④ 在 kit 裡打開這個功能

```bash
python3 scripts/setup.py        # 走到「無頭交辦」那一題說「要」，選你用的 AI 代理
```

或直接改 `config/kit.json` 的 `headless` 區塊（`enabled` 改 `true`、`agent` 填 `claude`／`codex`／`gemini`），
然後：

```bash
python3 scripts/build_config.py
```

### ⑤ 把兩個金鑰交給 Cloud Function，然後部署

金鑰不會進 repo，也不會進 Function 的程式碼——走 Firebase 的 secret 管理：

```bash
firebase functions:secrets:set KIT_LINE_CHANNEL_SECRET --project <你的專案id>     # 貼上，按 Enter
firebase functions:secrets:set KIT_LINE_CHANNEL_TOKEN --project <你的專案id>
firebase deploy --only storage --project <你的專案id>              # Storage 規則（語音存放處）
firebase deploy --only functions:line-relay --project <你的專案id>  # 收件端
```

> ⚠️ **一律用 `--only`。** 不要跑沒有參數的 `firebase deploy`——它會把 hosting、firestore、storage、
> functions 全部一起送，其中任何一個產品沒啟用就整批失敗，而錯誤訊息會指向錯的地方。

> Storage 那一行如果說「找不到 bucket」，是因為你的專案還沒啟用 Cloud Storage：
> Firebase Console → Build → Storage → 「開始使用」，選跟 Firestore 同一個地區，然後重跑那一行。

部署成功之後，終端機會印出一個網址，長得像：

```
https://line-relay-xxxxxxxx-de.a.run.app
```

（在 Console 的 Functions 頁面也找得到。）

### ⑥ 把網址填回 LINE，然後配對

1. 回到 LINE Developers 的「Messaging API」分頁 → **Webhook URL** 填剛剛那個網址 → Update。
2. 打開下面的 **Use webhook** 開關。
3. 按「Verify」——出現 `Success` 就對了。
   （出現 `401` 是正常的：驗證按鈕送的是空簽章，我們的程式本來就會擋。只要不是 404／500 就行。）
4. **用手機傳一句「哈囉」給這個官方帳號。** 它會回你一行：

   ```
   配對碼：Uxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```

5. 把那一串填進 `config/kit.json` 的 `headless.line.owner_user_id`
   （或重跑 `python3 scripts/setup.py`，在那一題貼上），然後：

   ```bash
   python3 scripts/build_config.py
   python3 scripts/headless.py --once     # 這一步會把配對碼送上雲端
   ```

   拿不到配對碼的話（沒收到回覆），在電腦上跑 `python3 scripts/headless.py --pair`，
   它會把 relay 看到的 userId 列出來。

> **配對完成前，任何人傳訊息給這個帳號都會拿到自己的配對碼。** 這是刻意的（你才拿得到自己的）。
> 所以請在拿到之後**馬上**完成配對——配對完就只認你一個人，別人傳什麼都會被靜靜丟掉。

### ⑦ 掛排程

```bash
python3 scripts/schedule.py
```

開了無頭交辦之後，它會多掛一個「每 5 分鐘收一次」的工作
（macOS launchd／Windows 工作排程器／Linux crontab，跟另外兩個一樣）。

### ⑧ 驗收

```bash
python3 scripts/doctor.py
```

「無頭交辦」那一區五項全綠就算裝好了。然後**實際做一次**：
用手機傳「今天午休 S-01 主動幫忙排椅子」給那個帳號，五分鐘內你應該收到一句
「已記到 S-01 的…」。

---

## 平常怎麼用

**就是傳訊息給那個帳號。** 講話或打字都可以。

講的時候請像對人講一樣把話講完整——AI 是照你講的整理，不會通靈：

- 好：「S-07 今天午休主動來找我，講了昨天跟同學衝突的事，情緒還算穩定，記在他的個案追蹤。」
- 不好：「剛剛那件事記一下。」（哪一位？哪一種紀錄？）

**講不清楚它不會亂猜。** 判斷不了的時候它會回你「聽起來像○○，但我不確定，沒有寫入」，
你再補一句就好。少一則紀錄可以補，寫錯一位學生很難發現——這是刻意的取捨。

**AI 要照著做的事寫在 `AGENTS-HEADLESS.md`**（在 kit 根目錄）。那個檔是可以改的：
你希望它寫得更簡短、或某一種紀錄一定要帶某個欄位，就改那份檔，下一則交辦就照新的做。

---

## 常用指令

```bash
python3 scripts/headless.py --status        # 待處理／處理中／完成／失敗各幾則，失敗的列出來
python3 scripts/headless.py --once          # 立刻處理一輪（不想等排程的時候）
python3 scripts/headless.py --once --dry-run   # 只看會做什麼，不改任何東西、不叫 AI
python3 scripts/headless.py --pair          # 印出配對碼
python3 scripts/headless.py --retry <事件id>  # 把一則失敗的排回待辦
```

每一則的處理結果都會在 `data/headless-audit.jsonl` 留一行（那個目錄不會進 git）。

---

## 卡住的時候

| 症狀 | 多半是 | 怎麼修 |
|---|---|---|
| 手機上傳了訊息，**完全沒有回覆** | webhook 沒設好，或 Use webhook 沒打開 | 回 LINE Developers 檢查 Webhook URL 與開關；按 Verify 看是不是 404 |
| 回的是罐頭訊息（「感謝您的訊息…」） | Auto-reply messages 沒關 | Messaging API 分頁把它關掉 |
| 一直回「配對碼：…」 | 配對碼還沒送上雲端 | 填進 `config/kit.json` → `build_config.py` → `headless.py --once` |
| 收到「收到了」但永遠等不到第二句 | 電腦沒醒、排程沒跑、或環境變數讀不到 | `python3 scripts/headless.py --status` 看有沒有堆著；`python3 scripts/doctor.py` 看金鑰那一項 |
| `--status` 裡有 failed | 那一則的原因就印在旁邊 | 常見是 AI 代理沒登入過、或它判斷不出對象。修好之後 `--retry <id>` |
| 語音一直失敗、文字沒事 | 專案沒啟用 Cloud Storage，或 whisper 沒裝 | Console 開 Storage 並部署 `--only storage`；`python3 scripts/doctor.py` 看語音那幾項 |
| 推播沒來但紀錄有寫進去 | `KIT_LINE_CHANNEL_TOKEN` 排程讀不到，或推播額度用完 | 把變數寫進登入設定檔；免費方案每月 200 則推播，一則交辦只推一次 |
| Function 部署失敗說要 Blaze | 就是還沒升級 | 見上面第 ① 步 |

看雲端那邊發生什麼事：Firebase Console → Functions → `line-relay` → 記錄檔（Logs）。

---

## 幾個刻意的設計（不是沒想到）

- **失敗不自動重試。** 重試最糟的情況是同一段話被寫成三則紀錄，而你得自己去刪。
  失敗就停在那裡，`--status` 看得到，`--retry` 才會再跑。
- **一則交辦只推播一次。** LINE 免費方案每個帳號每月 200 則推播；
  推「開始處理了」「轉逐字稿完成」只會把額度燒光。
- **語音永遠不刪。** Storage 上那一份、你電腦上 `inbox/done/` 那一份都留著。
- **relay 不叫任何 AI、不看內容。** 它只負責「收下來、存好、回一句」。
  所有判斷都在你自己的電腦上做——這樣雲端那一段就沒有任何需要你信任的東西。
- **兩台電腦同時跑也不會做兩次。** 搶件時帶著「這份文件從我讀到現在沒被改過」的條件，
  慢的那一台會直接跳過。
- **配對碼存在雲端（`meta/headless`），不是寫死在 Function 裡。** 換手機、換帳號只要改設定再跑一次
  `headless.py --once`，不用重新部署。
