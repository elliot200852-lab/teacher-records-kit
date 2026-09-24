# Gemini CLI 入口

這份 kit 的安裝腦只有一份：**`AGENTS.md`**（`.gemini/settings.json` 已把它登記成 context 檔，會自動載入；
沒載到的話先把它**完整**讀完再開始，它很長，不要只讀開頭）。

三件補充（不重複 AGENTS.md 的內容）：
- 平台差異（Windows 上 `python3` 要換成 `py -3`、路徑、排程）只寫在 `docs/PLATFORMS.md`。
- 產生檔一律由 `scripts/setup.py`／`scripts/build_config.py` 產生，不手寫。
- 有副作用的動作（部署、寄信、刪除、commit）先講一句再做。
