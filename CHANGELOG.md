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
- 同步回寫加 `currentDocument.updateTime` 前置條件，不再靜默覆蓋網頁上剛改的字。
- 設計正本：`docs/SPEC-v3.md`（含紅隊裁決）。

## v2 — 2026-07-31、v1 — 2026-07-14

見 `docs/REPORT.md` 第 10 節（MIT 公開版）。
