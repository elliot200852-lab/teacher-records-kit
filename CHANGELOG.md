# 變更紀錄（Changelog）

版本號照 [語意化版本](https://semver.org/lang/zh-TW/)：`主版本.次版本.修訂`。
- **主版本**（3 → 4）：資料格式或安全規則不相容，升級一定要跑 `setup.py --upgrade` 並重新部署規則。
- **次版本**（3.0 → 3.1）：新功能，舊資料照用；升級＝拉新程式＋`build_config.py`＋（若規則有動）重新部署。
- **修訂**（3.0.0 → 3.0.1）：修 bug，只換檔案。

每次發版：改 `VERSION`、在本檔加一段、`git tag v<版本>`。網頁右下角與 `doctor.py` 都會顯示目前版本，
Firestore `meta/config.version` 記錄該資料庫最後一次用哪個版本部署過規則——網頁版本比它新就提醒重新部署。

## v3.0.0-alpha.1 — 2026-09-10（尚未發行；只有 David 驗收用）

- repo 轉為私有、邀請制、收費（授權條款 placeholder，見 `LICENSE`）。
- 三個分頁：學生記錄／課程記錄／業務記錄；每頁內建「這一頁需要什麼資料」說明框。
- 業務記錄＝業務組庫（11 組）＋每組自訂欄位＋清單外開放選項。
- 三處一台帳：Firestore（網站）＋本機 markdown＋Google Drive 備份（桌面同步夾預設、gws 進階），`ledger.py --check` 對帳。
- 錄音檔：`inbox/` → 本機 whisper 轉錄 → AI 改寫 → `append_record.py` 唯一寫入通道。
- 確定性安裝精靈 `setup.py`；AI 代理不再手寫任何產生檔。
- 安全規則：新增 `business/**`、`meta/**`；擁有者可刪除（配合個資法刪除請求）。
- 設定檔改 JSON（`config/kit.json`、`config/tabs.json`），移除自寫 YAML 解析器。
- 同步回寫加 `currentDocument.updateTime` 前置條件，不再靜默覆蓋網頁上剛改的字。
- 設計正本：`docs/SPEC-v3.md`（含紅隊裁決）。

## v2 — 2026-07-31、v1 — 2026-07-14

見 `docs/REPORT.md` 第 10 節（MIT 公開版）。
