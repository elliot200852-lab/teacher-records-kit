# 變更紀錄（Changelog）

版本號照 [語意化版本](https://semver.org/lang/zh-TW/)：`主版本.次版本.修訂`。
- **主版本**（3 → 4）：資料格式或安全規則不相容，升級一定要跑 `setup.py --upgrade` 並重新部署規則。
- **次版本**（3.0 → 3.1）：新功能，舊資料照用；升級＝拉新程式＋`build_config.py`＋（若規則有動）重新部署。
- **修訂**（3.0.0 → 3.0.1）：修 bug，只換檔案。

每次發版：改 `VERSION`、在本檔加一段、`git tag v<版本>`。`VERSION` 是唯一的版本來源：
`build_config.py` 把它寫進 `window.KIT.version`（網頁顯示用）、`doctor.py` 開頭印它、
`sync.py` 把它寫進 Firestore `meta/config.version`（＝這個資料庫最後一次是哪一版同步／部署的），
`doctor.py` 連得上網時會拿兩邊比對，程式比資料庫新就提醒重新部署規則。

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
