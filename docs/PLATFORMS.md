# 平台支援：macOS／Windows／Linux（一條規則只寫在這裡）

> 這份是**平台事實的唯一正本**。程式端的正本是 `scripts/hostos.py`（工具在每個平台怎麼裝、路徑在哪、怎麼找）；
> `AGENTS.md`／`README.md`／`INSTALL.md`／`docs/GUIDE.md` 只放一行對照表與指向這裡的連結，不重複寫細節。
> 改平台相關的做法：先改 `hostos.py`，再改這份；兩個以外的地方不該有第三份。

## 支援等級

| 平台 | 等級 | 怎麼驗證的 |
|---|---|---|
| **macOS**（Apple Silicon 與 Intel） | 正式支援 | 作者日常使用；CI `macos-latest` |
| **Windows 10／11**（x64） | 正式支援 | CI `windows-latest` 真機：安裝腳本、排程掛上／拆掉、免互動安裝、Edge 印 PDF；**尚未有真人老師在 Windows 上完整裝過一次**——第一位 Windows 使用者就是第一次實測，遇到怪狀先當是我們的問題 |
| Windows on ARM | 部分 | 一切都能用，只有本機語音轉逐字稿（whisper.cpp）沒有官方預編譯檔 |
| Linux（Debian／Ubuntu 系） | 盡力支援 | CI `ubuntu-latest`；gcloud 要自己照官方說明裝 |
| **WSL** | **不支援** | 備份夾與工作排程器都在 Windows 那一邊，WSL 看不到。腳本會直接拒絕（`hostos.unsupported_reason()`），請改用 Windows 原生 PowerShell |

## 指令對照（AI 代理在 Windows 上要做的替換）

| 文件裡寫的 | macOS／Linux | Windows |
|---|---|---|
| `python3 scripts/x.py` | 照用 | **`py -3 scripts\x.py`**（python.org 版）或 `python scripts\x.py`；`python3` 在 Windows 常是「打開 Microsoft Store」的假殼。`doctor.py` 第一行會印這台電腦該用哪個 |
| `/tmp/answers.json` | 照用 | `$env:TEMP\answers.json`（PowerShell）；裝完一樣要刪 |
| `bash …` | 照用 | 沒有 bash。本 kit **已經沒有任何 .sh 腳本**，全部是 `.py` |
| `cat 檔案` | 照用 | `Get-Content 檔案`（或 `type 檔案`） |
| `ls` | 照用 | `Get-ChildItem`（`dir` 也行） |
| 路徑 `a/b/c` | 照用 | 腳本吃 `/` 也吃 `\`；老師貼給你的通常是 `C:\Users\...\` |
| `export KIT_SMTP_APP_PASSWORD='…'` | 照用 | `$env:KIT_SMTP_APP_PASSWORD = '…'` |
| `~` | 家目錄 | `C:\Users\<名字>`；腳本裡的 `~` 三個平台都會展開 |
| 終端機 | Terminal.app | **Windows Terminal 或 PowerShell**（不是 cmd、不是 WSL、不是 Git Bash） |

裝完任何工具都要**重開一個新的終端機視窗**，PATH 才會更新；腳本內部會自己補（`hostos.refresh_path()`），
但 AI 代理自己下的指令（`firebase`、`gcloud`）用的是代理那個 shell 的 PATH。

## 每個工具在每個平台怎麼來（正本＝`hostos.TOOLS`）

| 工具 | 為什麼需要 | macOS | Windows | Linux |
|---|---|---|---|---|
| Node.js ≥ 20 | Firebase CLI 的執行環境 | `brew install node` | `winget install -e --id OpenJS.NodeJS.LTS` | `apt-get install nodejs`（太舊時照 https://nodejs.org 裝） |
| firebase-tools | 部署安全規則與網站 | `npm i -g firebase-tools` | 同左（裝出來是 `firebase.cmd`） | 同左 |
| gcloud | 本機腳本拿權杖讀寫 Firestore | `brew install --cask google-cloud-sdk` | `winget install -e --id Google.CloudSDK` | 照官方說明 https://cloud.google.com/sdk/docs/install |
| ffmpeg | 錄音轉檔 | `brew install ffmpeg` | `winget install -e --id Gyan.FFmpeg`；失敗就自動下載 gyan.dev 的可攜版 | `apt-get install ffmpeg` |
| whisper.cpp | 本機語音轉逐字稿 | `brew install whisper-cpp` | 自動下載 GitHub release 的預編譯 zip（`whisper-bin-x64.zip`） | 自動下載 `whisper-bin-ubuntu-{x64,arm64}.tar.gz` |
| VC++ 執行階段 | Windows 上 whisper 要它 | — | `winget install -e --id Microsoft.VCRedist.2015+.x64` | — |
| gws（選用） | 備份走 gws 進階模式才要 | `npm i -g @googleworkspace/cli` | 同左 | 同左 |

三個平台都是同一支 `python3 scripts/install_tools.py`：已裝的跳過、能自動的自動、自動不了的印官方網址。
**它不會自動重試、不會留下裝到一半的狀態**；失敗就照印出來的網址手動裝，重開終端機，跑 `doctor.py`。

自動下載的可攜工具放在（要清掉跑 `install_tools.py --remove-portable`）：

| 平台 | 位置 |
|---|---|
| macOS／Linux | `~/.cache/teacher-records-kit/tools/` |
| Windows | `%LOCALAPPDATA%\teacher-records-kit\tools\` |

whisper 語音模型三個平台都放 `~/.cache/whisper-cpp/`（Windows 的 `~` 是 `C:\Users\<名字>`）。

## Windows 專屬的坑（每一條都對應 `hostos.py` 裡的一段程式）

| 坑 | 症狀 | 我們怎麼擋 |
|---|---|---|
| `python3` 是 Store 假殼 | 打 `python3` 跳出 Microsoft Store、退出碼 9009 | `hostos.python_cmd()` 真的跑一次才認；`doctor.py` 第一行印正確叫法 |
| `.cmd` 工具找不到 | `gcloud`／`firebase`／`gws` 在 PowerShell 打得到，Python 裡 `subprocess` 說找不到 | 所有外部工具一律經 `hostos.exe()`（會找 `.cmd`／`.bat`，還會翻 npm、Cloud SDK 的已知安裝夾） |
| 剛裝完 PATH 沒更新 | 裝完 winget 立刻健檢還是「找不到」 | `hostos.refresh_path()` 重讀登錄檔；文件要老師重開終端機 |
| 主控台不是 UTF-8 | ✓✗ 與中文印成問號、甚至 `UnicodeEncodeError` | `hostos.enable_console()`：`SetConsoleOutputCP(65001)` ＋ stdout 改 UTF-8 |
| 工具輸出是 cp950 | 錯誤訊息裡的中文變亂碼 | `hostos.decode_output()` 先 UTF-8，不行才用主控台編碼，最後才 replace |
| `.cmd` 轉手 cmd.exe 重新解析參數 | 主旨含 `&` 的信寄出去被截斷、甚至執行到別的東西 | `hostos.run()` 對 `.cmd`／`.bat` 的參數含 `& \| < > ^ % !` 引號、換行時直接拒跑（退出碼 126）；寄信改 `email.method=smtp` |
| 記錄檔被寫成 CRLF | 同一則記錄在 mac 與 Windows 算出的雜湊不同，同步一直報「內容不同」 | 所有文字寫入都帶 `newline="\n"`（有測試守著）；`.gitattributes` 鎖 LF |
| 工作排程器 `/TR` 261 字上限、錯過不補跑 | 路徑長一點就掛不上；電腦 07:00 沒開就永遠不同步 | 用 XML 定義檔（`setup/launchers/*.xml`）註冊：`StartWhenAvailable`、工作目錄、逾時都設得到 |
| 學校電腦鎖住 winget／工作排程器／UAC | 安裝卡在權限對話框、排程建不起來 | 安裝腳本每一項失敗都印官方安裝檔網址（不重試）；排程建不起來就不排程，改口頭「幫我同步一下」 |
| Google 雲端硬碟根目錄名稱與位置不固定 | `My Drive`／`我的雲端硬碟`，掛成 `G:` 或家目錄下的資料夾 | `hostos.drive_desktop_candidates()` 兩種名字都找、只探本機固定磁碟（不碰網路磁碟機，斷線的 NAS 會卡） |
| repo 放在 OneDrive 裡 | 檔案被鎖、真名名冊被同步上雲 | `doctor.py` 看到路徑在 `%OneDrive%` 底下會警告 |
| 路徑超過 260 字 | 莫名其妙的「找不到檔案」 | `doctor.py` 對太深的路徑警告 |
| whisper 缺 VC++ 執行階段 | `whisper-cli.exe` 在，但一跑就退出碼 0xC0000135 | `install_tools.py` 先裝 `Microsoft.VCRedist.2015+.x64`，裝完真的跑一次 `whisper-cli -h` 才算成功 |
| 沒有 Chrome | 匯出 PDF 失敗 | Windows 一定有 Edge，`hostos.chrome_candidates()` 把 `msedge.exe` 列進候選 |

## 排程在三個平台各是什麼

| 平台 | 機制 | 看得到的東西 | 移除 |
|---|---|---|---|
| macOS | launchd LaunchAgent | `~/Library/LaunchAgents/com.teacher-records-kit.{sync,backup}.plist` | `schedule.py --uninstall` |
| Windows | 工作排程器 | 工作 `\TeacherRecordsKit\Sync`、`\TeacherRecordsKit\Backup`；定義檔 `setup/launchers/*.xml`（gitignored） | 同上 |
| Linux | crontab | `crontab -l` 裡被 `# >>> teacher-records-kit` … `# <<< teacher-records-kit` 包起來的兩行 | 同上 |

三個平台都：每天 07:00 `sync.py`、每週日 08:00 `backup.py --quiet`，log 在 `logs/`，用的是**跑 `schedule.py` 當下那個 Python**（`sys.executable`）。
Windows 的排程只在該使用者登入時執行；錯過的那次會在下次開機補跑（`StartWhenAvailable`）。跑的時候會閃一下黑色視窗，正常。
**三個平台都會靜默失敗**——真正的驗證是網頁頂端「上次同步 X 天前」。

## 手機錄音怎麼進電腦

| 平台 | 做法 |
|---|---|
| macOS | AirDrop／隔空投送，拖進 `inbox/` |
| Windows | 手機連結（Phone Link）、LINE 傳給自己再下載、或 USB 線；存進 `inbox\` |
| 都行 | 錄音 App 直接「分享到 Google 雲端硬碟」，電腦端從同步夾拖進 `inbox/` |

## 維護這一層的規矩

1. 平台事實只住兩處：`scripts/hostos.py`（機器）與這份（人）。別的文件只准放對照表與連結。
2. 釘死的下載網址（`hostos.WHISPER_TAG`、`FFMPEG_WIN_ZIP`）CI 每週檢查一次還活著不活著（`.github/workflows/ci.yml` 的 `urls`）；掛了就改 `hostos.py` 那一行，跑一次 `install_tools.py --remove-portable` 再裝。
3. 改 `hostos.py` 之後：`python3 -m unittest discover scripts/tests`（本機）＋ push 讓 CI 在三個平台真的跑一遍。CI 的 `windows-smoke` 綠了才算 Windows 沒壞。
4. 測試裡用 `TRK_FORCE_OS=win|linux|mac|wsl` 在 mac 上渲染另一個平台的 dry-run；那只驗邏輯，不驗 winget／schtasks，真的驗證在 CI。
