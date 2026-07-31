# Teacher Records Kit —— 導師學生紀錄系統完整說明書

> **版本 v2 · 2026-07-31**（變更摘要見文末〈變更紀錄〉）。
> 本文描述的每一項行為都對應到 repo 現在的程式碼；若你發現說明與實際不符，那是 bug，請開 issue。
>
> 這是一份公開、去識別化的說明書。讀完你就能在**自己的 Firebase**上，
> 建一個只有你看得到的學生觀察紀錄系統，並部署成你自己的網站。
> 這個 kit 完全獨立——裝好之後，資料只在**你自己的** Firebase 專案裡，
> 不連到任何他人的資料庫、不上傳到任何第三方。

---

## 1. 這是什麼、解決什麼問題

導師每天都在觀察學生：某人今天在數學課特別專注、某人和同學起了衝突後怎麼處理、
某人這週的情緒起伏。這些**具體、及時的觀察**，是期末寫評量、跟家長溝通時最寶貴的素材——
但如果只靠記憶或散落的紙條，到學期末往往就想不起來了。

這套系統要解決的就是這件事：

1. **隨手記**：手機、電腦都能開一個網頁，點學生 → ＋新增 → 打幾句話就存好。
2. **看得出漏洞**：全班一覽會標「本月已記／未記」，一眼看出誰還沒被記錄到。
3. **期末一鍵取材**：學期末把全班歷次觀察一次匯出，直接餵給 AI 產出每位學生的評量草稿。

它刻意做得**極簡**：沒有帳號系統要維護、沒有伺服器要租、沒有 App 要上架。
就是一個靜態網頁 + Google 的資料庫，只有你（用你的 Google 帳號）看得到。

### 去識別化原則（重要）

紀錄內容一律用**代號**（如 `S-01`），不寫學生真名。
真名只存在你本機的一份名冊（`data/roster.csv`），用來在儀表板上顯示，**永不上雲、永不進 repo**。
這樣即使雲端資料外洩，外人看到的也只是「S-01 今天很專注」，對不到是誰。

---

## 2. 架構（純文字圖）

```
   ┌─────────────────────────────────────────────────────────────┐
   │  你的裝置（手機 / 電腦的瀏覽器）                              │
   │                                                             │
   │   dashboard.html  ← 一個靜態網頁，零 build、零 framework       │
   │        │  用 Google 帳號登入（Firebase Authentication）        │
   │        │  讀寫資料（Firebase JS SDK，直接打 Firestore）         │
   └────────┼────────────────────────────────────────────────────┘
            │  HTTPS
            ▼
   ┌─────────────────────────────────────────────────────────────┐
   │  你自己的 Firebase 專案（Google Cloud）                        │
   │                                                             │
   │   ┌──────────────────┐   ┌────────────────────────────────┐  │
   │   │ Authentication   │   │ Firestore（資料庫）             │  │
   │   │  Google 登入      │   │  students/{代號}/records/{日期}  │  │
   │   └──────────────────┘   │  class-observations/{日期}      │  │
   │                          │  roster/main（代號↔姓名）        │  │
   │   ┌──────────────────────┴────────────────────────────────┐  │
   │   │ Security Rules（安全規則）                              │  │
   │   │  「只有 owner_email 本人、Google 已驗證，才准讀寫」       │  │
   │   │  其餘所有人一律 deny——這才是真正的牆                    │  │
   │   └─────────────────────────────────────────────────────┘  │
   └─────────────────────────────────────────────────────────────┘

   （選用·進階）本機 Python 腳本，用你的 gcloud 帳號直接讀寫 Firestore：
     sync.py           本機 observations.md ↔ Firestore 雙向同步
     export_records.py 匯出全班紀錄成 Markdown / JSON，供期末評量取材
     parent_email.py   把某則觀察改寫成家長語氣寄出（Gmail）
```

**關鍵特性**：
- 前端就是一個 `.html` 檔——沒有 Node build、沒有 React、沒有打包步驟。丟到任何靜態主機就能跑。
- 前端**直接**跟 Firestore 對話（透過 Firebase 官方 JS SDK）；沒有你要維護的後端伺服器。
- 安全**不靠前端**——前端擋不住懂技術的人。真正的牆是 Firestore 的伺服器端規則。

---

## 3. 資料模型（單租戶 schema）

所有資料都在**你自己專案**的 Firestore 頂層，一位老師一個專案，天生單純。

### `students/{代號}` —— 每位學生一份摘要（相容欄位，儀表板不讀）
| 欄位 | 型別 | 說明 |
|---|---|---|
| `id` | string | 學生代號（如 `S-01`） |
| `recordCount` | number | 累積幾則紀錄（由進階同步腳本 `sync.py` 維護） |
| `lastRecordDate` | string | 最後一次記錄的日期（同上） |
| `monthsRecorded` | array | 有記錄過的月份 `YYYY-MM`（同上） |

> **儀表板不讀這三個欄位。** 全班一覽上的「N 則」與「本月已記／未記」是**每次開頁即時算**的：
> 每位學生一次計數查詢（`getCountFromServer`）＋一筆最新紀錄（`orderBy date desc, limit 1`）。
> 所以純網頁模式下數字一定是對的，不必跑任何腳本、不必改任何規則。
> 這三個欄位只是留給 `sync.py` 的相容欄位，你完全不用它們也沒關係。
>
> ⚠️ **2026-07-31 修正**：舊版說明書寫「只用網頁的話，儀表板會直接數 `records` 子集合」，
> 但當時的程式並沒有這麼做——它只讀摘要 doc，而摘要只有 `sync.py` 會寫。
> 結果是純網頁使用者記了一整個月，每張卡片還是「0 則 · 尚無紀錄 · 本月未記」。
> 現在程式真的照上面那樣做了，這句話才成立。

### `students/{代號}/records/{日期}` —— 每則觀察
文件 id 就是日期（`YYYY-MM-DD`），所以**一個學生一天一則**，天然防重複。
| 欄位 | 型別 | 說明 |
|---|---|---|
| `date` | string | `YYYY-MM-DD`；**必須等於文件 id**（規則強制） |
| `tags` | array | 題材標籤（如 `["#數學", "#專注意志"]`），已去重、統一單一 `#` |
| `body` | string | 觀察內容（客觀描述具體事件，用代號、勿寫真名） |
| `editedOnWeb` | bool | 是否在網頁上改過（供進階同步判斷回寫） |
| `webEditedAt` | timestamp | 網頁最後編輯時間 |

### `class-observations/{日期}` —— 全班觀察
資料模型與 `records` **完全相同**，只是對象是「整班」而非單一學生
（如某天全班的氛圍、一起經歷的事件）。同樣一天一則、date 綁文件 id。

### `roster/main` —— 代號↔姓名對照（唯一有真名的地方）
| 欄位 | 型別 | 說明 |
|---|---|---|
| `students` | array | 每筆 `{ id, name }`，供儀表板把代號顯示成真名 |

> 這份資料在你自己的專案裡、只有你讀得到。若你完全走「純網頁」模式，
> 甚至可以不放真名、只用代號記錄。

---

## 4. 安全設計（別人為什麼看不到）

這套的「保護」**不是把檔案加密**，而是**伺服器端的存取控制（登入閘）**。核心規則：

```
function isOwner() {
  return request.auth != null
    && request.auth.token.email == '{{OWNER_EMAIL}}'   // 只有你這個 email
    && request.auth.token.email_verified == true       // 且 Google 已驗證
    && request.auth.token.firebase.sign_in_provider == 'google.com';
}
```

- **owner email 白名單**：整個資料庫只認你一個 email。任何其他人——訪客、家長、同事，
  就算他拿到網址、就算他看網頁原始碼——**伺服器一律拒絕回傳資料**。
- **牆在後端、不在前端**：前端「藏起入口」只是介面方便，不是安全機制。真正的牆是上面這條規則。
- **紀錄不可刪**（`allow delete: if false`）：觀察是歷史，不從前端硬刪，避免手滑或誤刪。
  真要刪，去 Firebase Console 手動處理。
- **日期建立後不可竄改**：
  - 新增時，規則要求 `request.resource.data.date == recordId`（date 必須等於文件 id）。
  - 編輯時，規則要求 `request.resource.data.date == resource.data.date`（不准改 date）。
  - 效果：一則紀錄「哪天記的」是釘死的，只能改內容與標籤。
- **名冊 / 摘要的寫入者是你本人**：在這個單租戶模型裡，你就是唯一被信任的人，
  所以 `roster` 與 `students` 摘要的讀寫都綁 `isOwner()`——這也讓進階同步腳本
  （用你自己的 gcloud 帳號）能把名冊與摘要寫進去。

> 想更嚴：到 Firebase Console → Authentication → Settings 限制可登入的網域。

---

## 5. 從零到上線（步驟總覽）

以下是**你要自己做**的事。細節指令看 `AGENTS.md`（交給 AI 做）或 `INSTALL.md`（手動）。

1. **開一個 Firebase 專案**：到 [Firebase Console](https://console.firebase.google.com) 建立（或用現有的）。
2. **開 Google 登入**：Authentication → 啟用 **Google** 登入方式。
3. **開 Firestore 資料庫**：建立 Firestore Database（正式模式）。
4. **拿到網頁 App 設定**：專案設定 → 新增網頁 App → 複製 web config（apiKey 等），
   填進 `site/js/firebase-config.js`（從 `.example.js` 複製）。
5. **部署安全規則**：把 `firestore.rules.tmpl` 的 `{{OWNER_EMAIL}}` 換成你的 email，
   存成 `firestore.rules`，用 `firebase deploy --only firestore:rules`（或在 Console 貼上發布）。
6. **上線**：把 `site/` 丟到靜態主機——GitHub Pages、Firebase Hosting 皆可；
   或**嵌進你現有的網站**（見 `embed/EMBED-AND-SECURITY.md`）。
7. **放名單**：建 `data/roster.csv`（代號,姓名——本機、gitignored），開始記錄。

> 用 Firebase Hosting 上線時，記得把 `authDomain` 設成與 hosting 同源的網域
> （見第 7 節 Troubleshooting），iOS Safari 才不會登入失敗。

---

## 6. 推薦做法：把 repo 交給你的 AI 裝

這個 kit 就是為「交給 AI 裝」而設計的。**最省事的做法**：

1. 準備一個 AI 代理——**建議用付費版的 Claude Code**（能連續讀檔、跑指令、一步步帶你做，
   複雜安裝一次到位，比免費工具硬撐 workaround 省下大量時間）。
2. 把這個 repo 交給它，說：**「讀 `AGENTS.md`，幫我把這套裝起來。」**
3. 你只需要做兩件事：
   - 準備好 **`roster.csv`**（你的學生名單：代號,姓名）。
   - **回答 AI 的提問**（你的 Google email、Firebase 專案要新建還是用現有的、要獨立站還是嵌入…）。

AI 會一關一關問、缺什麼引導你補，最後幫你部署成可用的系統。
`AGENTS.md` 內建「每一步先問再做、先驗證再往下」的節奏，不會替你亂假設。

> 不想用 AI？`INSTALL.md` 有完整手動步驟。

---

## 7. Troubleshooting（常見問題）

### iOS Safari 登入一直失敗 / 登入後又跳回未登入
**成因**：iOS Safari 的**跨網域儲存分區（storage partitioning）**。
如果你打開頁面的網域（hosting）和 `authDomain` 不同源，Safari 會把登入用的暫存隔在不同分區，
Firebase 拿不回登入狀態，於是登入「看起來成功卻沒生效」。

**解法**：讓 `authDomain` 與 hosting **同源**。
若你用 Firebase Hosting（`<project>.web.app`），就把 `firebase-config.js` 的
`authDomain` 從預設的 `<project>.firebaseapp.com` 改成 `<project>.web.app`。
兩者同源後，iOS Safari 就能正常保存登入狀態。

### 在 LINE / FB / IG / WeChat 裡打開，Google 登入被擋
**成因**：這些 App 的**內建瀏覽器**（WebView）常擋掉 Google OAuth。
**本 kit 已內建防呆**：偵測到內建瀏覽器時會提示你改用 Safari / Chrome，
LINE 還給一個「改用外部瀏覽器開啟」的按鈕。照著把網址複製到 Safari / Chrome 開，再登入即可。

### 電腦上 popup 被瀏覽器擋掉
**已自動處理**：popup 失敗時前端會自動改用「整頁轉址」（redirect）登入，
登入完成後跳回頁面。你通常不會察覺切換。

### 部署規則時常見錯誤
- `firebase deploy` 前要先 `firebase login`、並用**對的專案**（`--project <PROJECT_ID>`）。
- 沒裝 CLI 也行：到 Console → Firestore → 規則，把 `firestore.rules` 內容貼上、按「發布」。
- 部署後驗證：用**你自己**的帳號登入看得到資料；換別的帳號 / 無痕視窗 → 顯示「無權檢視」、讀不到任何東西。若別的帳號還讀得到，代表規則沒生效——回頭確認 `{{OWNER_EMAIL}}` 有換成你的 email、且規則真的部署上去了。

### 進階腳本（sync / export / 寄家長）跑不動
這些是**選用**功能，需要 `gcloud` 以**專案擁有者**身分登入（`gcloud auth login`），
並填好 `config.yaml` 的 `firebase.project_id`。純用網頁儀表板則完全不需要這些。

---

## 8. 獨立性聲明

- 這個 kit 是**空殼模板**，公開 repo 本身**零個資**——只含範本與程式碼。
- 你裝好之後，所有資料存在**你自己建立的** Firebase 專案裡，由**你的** Google 帳號、
  **你部署的**安全規則保護。
- 它**不**連到任何他人的資料庫、**不**回報任何資料給原作者或第三方。
- 你的真實資料（紀錄、名冊、家長 email）一律放本機 `data/`（gitignored），永不進 git。

MIT 授權，自由使用、修改、分享。

---

## 9. 變更紀錄

### v2 — 2026-07-31

- **修正一個會讓核心功能失效的 bug**：全班一覽的「N 則」與「本月已記／未記」改成**開頁即時計算**。
  在此之前它們讀的是只有 `sync.py` 會寫的摘要欄位，所以純網頁使用者（README 說「多數人夠用」的那個模式）
  的徽章永遠停在「本月未記」。第 3 節有完整說明。
- 說明書同步改正：第 3 節那句「只用網頁的話，儀表板會直接數 `records` 子集合」以前是假的，現在是真的。

> 本說明書從 v2 起與程式碼**同批更新**——功能改了，這份就在同一個 commit 裡改。
> v1 的教訓是文件跑在程式前面，結果對外描述了不存在的行為。

### v1 — 2026-07-14

首個公開版本。
