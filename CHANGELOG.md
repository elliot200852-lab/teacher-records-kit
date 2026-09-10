# 變更紀錄（Changelog）

版本號照 [語意化版本](https://semver.org/lang/zh-TW/)：`主版本.次版本.修訂`。
- **主版本**（3 → 4）：資料格式或安全規則不相容，升級一定要跑 `setup.py --upgrade` 並重新部署規則。
- **次版本**（3.0 → 3.1）：新功能，舊資料照用；升級＝拉新程式＋`build_config.py`＋（若規則有動）重新部署。
- **修訂**（3.0.0 → 3.0.1）：修 bug，只換檔案。

每次發版：改 `VERSION`、在本檔加一段、`git tag v<版本>`。`VERSION` 是唯一的版本來源：
`build_config.py` 把它寫進 `window.KIT.version`（網頁顯示用）、`doctor.py` 開頭印它、
`sync.py` 把它寫進 Firestore `meta/config.version`（＝這個資料庫最後一次是哪一版同步／部署的），
`doctor.py` 連得上網時會拿兩邊比對，程式比資料庫新就提醒重新部署規則。

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
