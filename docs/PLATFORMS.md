# 平台支援：macOS／Windows／Linux（一條規則只寫在這裡）

> 這份是**平台事實的唯一正本**。程式端的正本是 `scripts/hostos.py`（工具在每個平台怎麼裝、路徑在哪、怎麼找）；
> 唯一的例外是下面第一節的 **bootstrap 層**（Python 還沒裝好，讀不到 `hostos.py`，只好一個 OS 一支 shell 腳本）；
> `AGENTS.md`／`README.md`／`INSTALL.md`／`docs/GUIDE.md` 只放一行對照表與指向這裡的連結，不重複寫細節。
> 改平台相關的做法：先改 `hostos.py`，再改這份；兩個以外的地方不該有第三份。

## bootstrap 層（Python 還沒有的時候）

`install_tools.py` 是 Python 寫的，所以它救不了「連 Python 都還沒有」的那台電腦。
那一段由 **bootstrap 層**負責，一個 OS 一支：

| 檔案 | 誰跑 | 它做什麼 |
|---|---|---|
| `setup/bootstrap.sh` | macOS／Linux，`bash setup/bootstrap.sh` | Xcode 命令列工具 → Homebrew（含 `~/.zprofile`／`~/.bash_profile` 的 shellenv，Apple Silicon 是 `/opt/homebrew`、Intel 是 `/usr/local`）→ git／Python／Node.js → AI 代理 CLI → 回頭跑 `install_tools.py` 與 `doctor.py` → 印出「開新視窗、`cd`、叫 AI」三行 |
| `setup/bootstrap.ps1` | Windows，PowerShell 5.1 以上 | winget 在不在 → git／Python／Node.js（跳過已經夠新的；Microsoft Store 的 python 假殼用退出碼 9009 認出來）→ 每裝完一項從登錄檔（HKLM＋HKCU）重讀 PATH → AI 代理 CLI → `py -3 scripts\install_tools.py`、`doctor.py` → 印出下一步 |
| `setup/bootstrap.cmd` | Windows，**按兩下** | 只有三行：用 `-NoProfile -ExecutionPolicy Bypass` 叫上面那支，最後 `pause` 讓視窗別關掉 |

**這是「平台事實只住兩處」的唯一例外**，而且是有理由的例外：Python 還沒有，讀不到 `hostos.py`。
所以這兩支腳本裡的裝法是 `hostos.TOOLS`／`hostos.AGENT_CLIS` 的**手抄本**——
改了表就要改腳本，改了腳本就要改表（`scripts/tests/test_platform.py` 的 `Bootstrap` 那一組會對，對不上就紅）。
兩支都吃 `--dry-run`／`-DryRun`（印出每一步會跑什麼、一個字都不裝）與 `--yes`／`-Yes`（不停下來問）；
失敗哲學與 `install_tools.py` 相同：**不重試、不留半套，印官方網址繼續往下走**，最後由 `doctor.py` 說缺什麼。
`bootstrap.sh` 在 WSL 裡會直接拒跑（訊息與 `hostos.unsupported_reason()` 同一份）。
`bootstrap.ps1` 存成 **UTF-8 with BOM**（PowerShell 5.1 沒有 BOM 會把中文讀成亂碼），`bootstrap.cmd` 只用 ASCII；
兩者都跟全 repo 一樣是 LF（`.gitattributes` 鎖的；`cmd.exe` 讀 LF 的批次檔沒問題）。

## AI 代理的 CLI 怎麼來（正本＝`hostos.AGENT_CLIS`）

| 代理 | 啟動指令 | macOS | Windows | Linux |
|---|---|---|---|---|
| Claude Code | `claude` | `curl -fsSL https://claude.ai/install.sh \| bash`（備案 `brew install --cask claude-code`） | `winget install -e --id Anthropic.ClaudeCode`（備案 `irm https://claude.ai/install.ps1 \| iex`） | 同 macOS，無備案 |
| OpenAI Codex CLI | `codex` | `curl -fsSL https://chatgpt.com/codex/install.sh \| sh`（備案 `npm i -g @openai/codex`） | `npm install -g @openai/codex` | 同 macOS |
| Gemini CLI | `gemini` | `brew install gemini-cli`（備案 npm） | `npm install -g @google/gemini-cli` | `npm install -g @google/gemini-cli` |

**無頭交辦（`docs/HEADLESS.md`）怎麼非互動地叫它們**——同一張表的 `headless` 欄位，
`scripts/headless.py` 只從那裡拿，不在別處寫死。旗標是 2026-09-12 在 macOS 上照各家 `--help` 對過的：

| 代理 | 無頭叫法 | 為什麼是這幾個旗標 |
|---|---|---|
| Claude Code | `claude -p "<提示詞>" --permission-mode acceptEdits --allowedTools "Bash Read Write Edit"` | `-p/--print` ＝非互動；`acceptEdits` 讓它不停下來問；工具收斂到讀檔、寫暫存草稿、跑 `append_record.py` |
| OpenAI Codex CLI | `codex exec --sandbox workspace-write --skip-git-repo-check "<提示詞>"` | `exec` ＝非互動子指令；`workspace-write` 才寫得了 `data/`；老師的 kit 資料夾多半不是 git repo |
| Gemini CLI | `gemini -p "<提示詞>" --approval-mode yolo` | `-p/--prompt` ＝非互動；`--approval-mode yolo` 等同 `--yolo`，但這個名字比較不會哪天被拿掉 |

**一律以 argv 交給 `subprocess`，不經 shell**：提示詞裡夾著逐字稿，引號、換行、`$`、`&`
都可能出現，經過一層 shell 解析輕則截斷、重則變成別的指令。
逾時（預設 1800 秒）要用 `hostos.kill_tree()` 把整棵行程樹殺掉——
代理自己會開一堆子行程，只殺父行程的話孫子還抓著同一個檔案繼續跑。
改這幾個旗標的時候，`scripts/tests/test_headless.py` 的 `test_hostos_headless_forms` 要一起改。

**評量維度補標（`scripts/auto_dim_tags.py`）怎麼叫它們**——同一張表的 `oneshot` 欄位。這個用途只要「讀一段文字、回一段 JSON」，
**不需要任何工具權限，能關的全關**；**提示詞一律從 stdin 餵，不放在參數裡**：一批 30 則正文會超過 Windows 命令列
32767 字元的上限，npm 裝的 codex／gemini 又是 `.cmd`（參數經 cmd.exe 再解析一次，換行會被截斷）。
2026-09-13 在 macOS 上照各家 `--help` 對過（claude 2.1.270／codex-cli 0.144.6／gemini 0.46.0）：

| 代理 | 補標叫法 | 對過 `--help` 的 | 【未驗證】 |
|---|---|---|---|
| Claude Code | `claude -p --tools "" --strict-mcp-config --disable-slash-commands --no-session-persistence --output-format text` | `--tools ""` 關掉全部內建工具；`--strict-mcp-config`（不給 `--mcp-config`）不載入任何 MCP；`--disable-slash-commands` 不載入技能；`--no-session-persistence` 只在 `-p` 有效；沒給提示詞參數時從 stdin 讀（help 沒寫，但 2026-09-13 驗收時實呼叫過：回 0、7.4 秒、JSON 解析得了） | （無） |
| OpenAI Codex CLI | `codex exec --sandbox read-only --skip-git-repo-check --ephemeral --color never -o <暫存檔> -` | `-`＝提示詞從 stdin 讀；`--sandbox read-only`；`--ephemeral` 不留 session 檔；`-o/--output-last-message` 只寫最後一則訊息（回答從這個檔讀，不怕 stdout 夾進度） | 它的 shell 工具關不掉，只能靠唯讀沙箱擋寫入 |
| Gemini CLI | `gemini -p "<一句 ASCII>" --approval-mode default --output-format text` | `-p` 的內容「接在 stdin 後面」，所以真正的提示詞走 stdin、`-p` 只放一句純 ASCII；`--approval-mode default` | 非互動下 default 模式會排除需要核准的寫檔／shell 工具（help 沒寫）；沒選 `plan`（help 寫 read-only），因為回答形狀不保證（未實測） |

代理的工作目錄是 `hostos.work_dir()`（保證 ASCII，而且不在 kit 資料夾裡，讀不到這份 kit 的 `CLAUDE.md`／`AGENTS.md` 安裝指示）。
**但 `claude -p` 仍會載入使用者層 `~/.claude` 的設定與 hooks**——上面那幾個旗標關不掉那一層（`--bare` 才會跳過，
可是它不讀訂閱登入，老師用不了）；老師自己在 `~/.claude` 掛的 hooks 每一批都會跑一次。
送出去的只有「代號/rid」與正文；**真名攔截只比對名冊上的全名**，正文只寫名、沒寫姓的攔不到、會照送。

逾時一樣用 `hostos.kill_tree()` 殺整棵行程樹。改這幾個旗標時，`scripts/tests/test_auto_dim_tags.py` 的
`test_hostos_oneshot_forms` 要一起改。

已經有 Python 的電腦不必走 bootstrap：`python3 scripts/install_tools.py --agent claude` 就是同一張表。
裝完之後 `doctor.py` 會多印一行「AI 代理的 CLI」告訴你找到哪幾支（**只是報告，不是必要項目**）。

Windows 要記得的三件事：

- **Git for Windows 不只是拿來 clone 的**：Claude Code 的指令工具要用它附的 `bash`，沒有 git 那個工具會廢掉。
- **Codex 與 Gemini 走 npm，所以要先有 Node.js 20 以上**；bootstrap 的順序已經排好（Node 在代理前面）。
- **Gemini CLI 官方列的 Windows 支援是 11 24H2 以上**；更舊的 Windows 10 上裝得起來但官方不保證。

裝完任何一支都要**開一個新的終端機視窗**才叫得到（PATH 是開視窗當下讀的）。
macOS／Linux 上 Claude Code 的原生安裝程式會把 `claude` 放進 `~/.local/bin`，
bootstrap 會把那一夾補進 `~/.zprofile` 與 `~/.bash_profile`（`hostos._known_dirs()` 也找得到它）。

## 支援等級

| 平台 | 等級 | 怎麼驗證的 |
|---|---|---|
| **macOS**（Apple Silicon 與 Intel） | 正式支援 | 作者日常使用；CI `macos-latest` |
| **Windows 10／11**（x64） | 正式支援 | CI `windows-latest` 真機：可攜工具下載、排程掛上／拆掉、免互動安裝、健檢（離線必過的項目逐項驗）、Edge 印 PDF；winget 只有 **ffmpeg** 那一條真的會走到（CI 會先把 runner 預裝的 ffmpeg 拿掉），Node.js 與 gcloud 在 runner 上已預裝，**它們的 winget 路徑只有真實使用者會走到**。**尚未有真人老師在 Windows 上完整裝過一次**——第一位 Windows 使用者就是第一次實測，遇到怪狀先當是我們的問題 |
| Windows on ARM | 部分 | 一切都能用，只有本機語音轉逐字稿（whisper.cpp）沒有官方預編譯檔 |
| Linux（Debian／Ubuntu 系） | 盡力支援 | CI `ubuntu-latest`；gcloud 要自己照官方說明裝 |
| **WSL** | **不支援** | 備份夾與工作排程器都在 Windows 那一邊，WSL 看不到。腳本會直接拒絕（`hostos.unsupported_reason()`），請改用 Windows 原生 PowerShell |

## 指令對照（AI 代理在 Windows 上要做的替換）

| 文件裡寫的 | macOS／Linux | Windows |
|---|---|---|
| `python3 scripts/x.py` | 照用 | **`py -3 scripts\x.py`**（python.org 版）或 `python scripts\x.py`；`python3` 在 Windows 常是「打開 Microsoft Store」的假殼。`doctor.py` 第一行會印這台電腦該用哪個 |
| `/tmp/<任何檔>`（`/tmp/answers.json`、`/tmp/一則.md`、`/tmp/改寫稿.md`…） | 照用 | `$env:TEMP\<檔>`（PowerShell）——文件裡每一個 `/tmp/…` 都照這條換，不是只有 answers.json；含個資的（答案檔、改寫稿）用完一樣要刪 |
| `bash …` | 照用 | 沒有 bash。本 kit 的腳本全部是 `.py`，唯一的 `.sh` 是 bootstrap 層（Windows 那一支是 `.ps1`／`.cmd`） |
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

外部工具的暫存工作夾（`hostos.work_dir()`，轉錄的中繼 wav 就在這裡，用完就刪）：
macOS／Linux `~/.cache/teacher-records-kit/work/`；Windows `%LOCALAPPDATA%\teacher-records-kit\work\`，
那條路徑含非 ASCII 字元（中文使用者名稱）時退到 `C:\ProgramData\teacher-records-kit\work\`。

whisper 語音模型三個平台都放 `~/.cache/whisper-cpp/`（Windows 的 `~` 是 `C:\Users\<名字>`）。

## Windows 專屬的坑（每一條都對應 `hostos.py` 裡的一段程式）

| 坑 | 症狀 | 我們怎麼擋 |
|---|---|---|
| `python3` 是 Store 假殼 | 打 `python3` 跳出 Microsoft Store、退出碼 9009 | `hostos.python_cmd()` 在 Windows 上**真的跑一次** `py -3 -c "import sys;print(sys.executable)"` 才認（退出碼 103＝啟動器在、但沒註冊任何 3.x，那樣也不算；結果整個行程只算一次）；`python`／`python3` 則看它是不是住在 `WindowsApps`。`doctor.py` 第一行印正確叫法 |
| 排程用到 Store 假殼 | 工作排程器裡工作明明在，卻永遠沒跑、也沒有錯誤訊息 | `schedule.py` 安裝前先問 `hostos.python_is_store_alias(sys.executable)`，是假殼就**拒絕安裝**並叫老師裝 python.org 版 |
| 使用者名稱是中文，`%TEMP%` 就是非 ASCII 路徑 | `whisper-cli.exe`（窄字元 argv）說找不到檔，看起來像「這個錄音壞了」 | 暫存 wav 與 `-of` 前綴改放 `hostos.work_dir()`：`%LOCALAPPDATA%\teacher-records-kit\work`，那條路徑也含非 ASCII 字元時退到 `C:\ProgramData\teacher-records-kit\work`，兩條都不行才警告 |
| Chrome 印完 PDF 留下一地暫存 profile | `%TEMP%` 裡愈積愈多 `trk-chrome-*` 資料夾 | renderer 是獨立行程，只殺父行程它們還抓著 profile；`export_docs.py` 改用 `hostos.kill_tree()`（Windows `taskkill /T /F`、POSIX 殺整個 process group） |
| `.cmd` 工具找不到 | `gcloud`／`firebase`／`gws` 在 PowerShell 打得到，Python 裡 `subprocess` 說找不到 | 所有外部工具一律經 `hostos.exe()`（會找 `.cmd`／`.bat`，還會翻 npm、Cloud SDK 的已知安裝夾） |
| 剛裝完 PATH 沒更新 | 裝完 winget 立刻健檢還是「找不到」 | `hostos.refresh_path()` 重讀登錄檔；文件要老師重開終端機 |
| 主控台不是 UTF-8 | ✓✗ 與中文印成問號、甚至 `UnicodeEncodeError` | `hostos.enable_console()`：`SetConsoleOutputCP(65001)` ＋ stdout 改 UTF-8 |
| 工具輸出是 cp950 | 錯誤訊息裡的中文變亂碼 | `hostos.decode_output()` 先 UTF-8，不行才用主控台編碼，最後才 replace |
| `.cmd` 轉手 cmd.exe 重新解析參數 | 主旨含 `&` 的信寄出去被截斷、甚至執行到別的東西 | `hostos.run()` 對 `.cmd`／`.bat` 的參數含 `& \| < > ^ %` 或換行時直接拒跑（退出碼 126，正本＝`hostos._CMD_META`）；**引號本身是允許的**（它單獨出現不會讓 cmd.exe 執行到別的東西），`!` 也沒擋（延遲展開預設是關的）。寄信改 `email.method=smtp` |
| 記錄檔被寫成 CRLF | 同一則記錄在 mac 與 Windows 算出的雜湊不同，同步一直報「內容不同」 | 所有文字寫入都帶 `newline="\n"`（有測試守著）；`.gitattributes` 鎖 LF |
| 工作排程器 `/TR` 261 字上限、錯過不補跑 | 路徑長一點就掛不上；電腦 07:00 沒開就永遠不同步 | 用 XML 定義檔（`setup/launchers/*.xml`）註冊：`StartWhenAvailable`、工作目錄、逾時都設得到 |
| 學校電腦鎖住 winget／工作排程器／UAC | 安裝卡在權限對話框、排程建不起來 | 安裝腳本每一項失敗都印官方安裝檔網址（不重試）；排程建不起來就不排程，改口頭「幫我同步一下」 |
| Google 雲端硬碟根目錄名稱與位置不固定 | `My Drive`／`我的雲端硬碟`，掛成 `G:` 或家目錄下的資料夾 | `hostos.drive_desktop_candidates()` 兩種名字都找、先讀桌面程式自己寫在 `HKCU\Software\Google\DriveFS` 的掛載點（讀不到就算了），再探本機固定磁碟（**不碰網路磁碟機**，斷線的 NAS 會卡幾十秒） |
| repo 放在 OneDrive 裡 | 檔案被鎖、真名名冊被同步上雲 | `doctor.py` 看到路徑在 `%OneDrive%` 底下會警告 |
| 路徑超過 260 字 | 莫名其妙的「找不到檔案」 | `doctor.py` 對太深的路徑警告 |
| whisper 缺 VC++ 執行階段 | `whisper-cli.exe` 在，但一跑就退出碼 0xC0000135 | `install_tools.py` 先裝 `Microsoft.VCRedist.2015+.x64`，裝完真的跑一次 `whisper-cli -h` 才算成功。「在不在」只問 `hostos.vcredist_present()` 一支（doctor 與 install_tools 共用），而且 `vcruntime140.dll` 與 `vcruntime140_1.dll` **兩個都要**——MSVC build 的 whisper 少了後者一樣 0xC0000135 |
| 沒有 Chrome | 匯出 PDF 失敗 | Windows 一定有 Edge，`hostos.chrome_candidates()` 把 `msedge.exe` 列進候選 |

## 排程在三個平台各是什麼

| 平台 | 機制 | 看得到的東西 | 移除 |
|---|---|---|---|
| macOS | launchd LaunchAgent | `~/Library/LaunchAgents/com.teacher-records-kit.{sync,backup,headless}.plist` | `schedule.py --uninstall` |
| Windows | 工作排程器 | 工作 `\TeacherRecordsKit\Sync`、`\Backup`、`\Headless`；定義檔 `setup/launchers/*.xml`（gitignored） | 同上 |
| Linux | crontab | `crontab -l` 裡被 `# >>> teacher-records-kit` … `# <<< teacher-records-kit` 包起來的那幾行 | 同上 |

**掛哪幾個由設定決定**（`schedule.py` 的 `wanted_jobs()`，正本＝`config/kit.json`）：

| job | 什麼時候 | 跑什麼 | 什麼情況下才掛 |
|---|---|---|---|
| `sync` | 每天 07:00 | `sync.py` | `mode` 是 `cloud`（本機模式沒有雲端可以同步） |
| `backup` | 每週日 08:00 | `backup.py --quiet` | 一律掛 |
| `headless` | **每 5 分鐘** | `headless.py --once --quiet` | `headless.enabled` 是 true（且 cloud 模式） |

`headless` 是唯一的「間隔型」工作，三個平台各自的做法不一樣：
macOS 用 `StartInterval`（不是 `StartCalendarInterval`——後者要把 60 分鐘列成 60 筆字典，而且睡醒不補跑）；
Windows 沒有「每 N 分鐘」的觸發器，做法是**每天一次的 `CalendarTrigger` ＋ `<Repetition>` 每 `PT5M` 重複 `P1D`**
（`StopAtDurationEnd` 要 `false`，不然一天結束會把正在跑的那次殺掉）；Linux 就是 `*/5 * * * *`。

`headless` 的排程還有一個平台陷阱：**它要讀得到兩個環境變數**（LINE 的 secret 與 token）。
launchd 不讀 `~/.bashrc`、Windows 工作排程器也不讀你終端機裡臨時 `export` 的東西——
變數要設在「登入時就會載入」的地方，見 `docs/HEADLESS.md` 第 ③ 步。

log 在 `logs/`，用的是**跑 `schedule.py` 當下那個 Python**（`sys.executable`）。
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
   唯一的例外是 `setup/bootstrap.sh`／`setup/bootstrap.ps1`（見第一節），它們是手抄本，改表就要改它們。
2. 下載網址與雜湊：`hostos.DOWNLOADS` 每一筆是 `(網址, 執行檔名, 子夾, sha256 或 None)`，
   `install_tools.download()` 只要 sha256 有填就一定驗，對不上直接丟掉不裝。
   **whisper 的三個檔釘死 sha256**（tag 釘死＝內容不會變）；**ffmpeg 的 `FFMPEG_WIN_ZIP` 是滾動網址**
   （`ffmpeg-release-essentials.zip` 同一個網址每次改版內容都不一樣），釘了每週都會紅，所以刻意留 `None`
   ——代價是那一包只驗得到「下載得到」，驗不到「沒被換過」；要更嚴就改成釘版本號的網址並補雜湊。
   CI 每週把 `hostos.ALL_URLS()`（可攜工具＋whisper 語音模型與 VAD 模型）逐一打一次確認還活著
   （`.github/workflows/ci.yml` 的 `urls`）；掛了就改 `hostos.py` 那幾行（換 tag 要一起換 sha256），
   跑一次 `install_tools.py --remove-portable` 再裝。
3. 改 `hostos.py` 之後：`python3 -m unittest discover scripts/tests`（本機）＋ push 讓 CI 在三個平台真的跑一遍。CI 的 `windows-smoke` 綠了才算 Windows 沒壞。
4. 測試裡用 `TRK_FORCE_OS=win|linux|mac|wsl` 在 mac 上渲染另一個平台的 dry-run；那只驗邏輯，不驗 winget／schtasks，真的驗證在 CI。
