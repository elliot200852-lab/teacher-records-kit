# bootstrap.ps1 — 從一台「什麼都沒裝」的 Windows 10／11 開始，把地基鋪到 AI 代理能接手為止。
#
# 這一層做四件事，做完就交棒：
#   ① winget（Windows 內建的安裝程式）② git、Python 3、Node.js
#   ③ 老師訂的那一家 AI 代理 CLI（Claude Code／Codex／Gemini）
#   ④ 最後回頭跑 scripts\install_tools.py 與 scripts\doctor.py，然後印出下一步。
#
# 為什麼這支是 PowerShell 不是 Python：Python 本身可能還沒有。
# **這是整份 kit 唯一被允許重複平台事實的地方**（正本仍是 scripts\hostos.py ＋ docs\PLATFORMS.md，
# 那份文件的「bootstrap 層」有記這件事）；改了這裡的裝法，兩邊都要跟著改。
#
# 用法（一般老師不必自己打，按兩下 setup\bootstrap.cmd 就好）：
#   powershell -NoProfile -ExecutionPolicy Bypass -File setup\bootstrap.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File setup\bootstrap.ps1 -Agent claude -Yes
#   powershell -NoProfile -ExecutionPolicy Bypass -File setup\bootstrap.ps1 -DryRun
#
# 只吃 Windows 原生（PowerShell 5.1 以上就跑得動）。WSL、Git Bash 都不是這一條路。
# 失敗哲學跟 install_tools.py 一樣：不自動重試、不留裝到一半的狀態，失敗就印官方網址繼續往下走。
# 不需要系統管理員身分；winget 裝東西時可能跳出「使用者帳戶控制」，按「是」就好。

[CmdletBinding()]
param(
    [ValidateSet("claude", "codex", "gemini", "none")]
    [string]$Agent = "",
    [switch]$DryRun,
    [switch]$Yes
)

$ErrorActionPreference = "Continue"
try { $OutputEncoding = [System.Text.UTF8Encoding]::new() } catch { }
try { [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new() } catch { }

$script:Failed = @()
$script:Prompt = "請完整讀 AGENTS.md，然後帶我從步驟 0 開始安裝"

function Write-Step($text)  { Write-Host ""; Write-Host ("-- " + $text) }
function Write-Ok($text)    { Write-Host ("  [OK] " + $text) -ForegroundColor Green }
function Write-Note($text)  { Write-Host ("  " + $text) -ForegroundColor DarkGray }
function Write-Warn2($text) { Write-Host ("  ! " + $text) -ForegroundColor Yellow }
function Write-Bad($text)   { Write-Host ("  X " + $text) -ForegroundColor Red }
function Add-Failure($what) { $script:Failed += $what }

# ── 跑一個外部指令（-DryRun 只印） ─────────────────────────────────────────
function Invoke-Cmd {
    param([string]$File, [string[]]$Arguments = @())
    $line = ($File + " " + ($Arguments -join " ")).Trim()
    if ($DryRun) {
        Write-Host ("  (-DryRun，不執行) 將會跑：" + $line)
        return 0
    }
    Write-Host ("  執行：" + $line)
    # 外部指令的輸出直接給老師看；不能讓它混進這個函式的回傳值（PowerShell 會把兩者合起來）
    & $File @Arguments 2>&1 | Out-Host
    $rc = $LASTEXITCODE
    if ($null -eq $rc) { $rc = 0 }
    return $rc
}

# ── 這台電腦上有沒有這個指令、版本是多少 ──────────────────────────────────────
function Get-ToolVersion {
    param([string]$File, [string[]]$Arguments = @("--version"))
    $out = ""
    $global:LASTEXITCODE = $null
    try {
        $out = & $File @Arguments 2>&1 | Out-String
    } catch {
        return ""
    }
    # 退出碼 9009＝找不到指令，或 Microsoft Store 的 python 假殼；沒真的啟動時 $LASTEXITCODE 是舊值，也當沒有
    if ($null -eq $LASTEXITCODE -or $LASTEXITCODE -ne 0) { return "" }
    if ($null -eq $out) { return "" }
    return $out.Trim()
}

function Test-Tool([string]$name) {
    $c = Get-Command $name -ErrorAction SilentlyContinue
    return ($null -ne $c)
}

# ── 剛裝完，這個視窗的 PATH 還是舊的：從登錄檔重讀（HKLM ＋ HKCU） ─────────────
function Update-PathFromRegistry {
    if ($DryRun) { return }
    $parts = @()
    foreach ($scope in @("Machine", "User")) {
        $v = [Environment]::GetEnvironmentVariable("Path", $scope)
        if ($v) {
            foreach ($p in ($v -split ";")) {
                $p = [Environment]::ExpandEnvironmentVariables($p.Trim())
                if ($p -and ($parts -notcontains $p)) { $parts += $p }
            }
        }
    }
    foreach ($p in ($env:Path -split ";")) {
        $p = $p.Trim()
        if ($p -and ($parts -notcontains $p)) { $parts += $p }
    }
    # npm -g 的 .cmd 殼與 winget 的連結夾，安裝程式不一定會即時寫進登錄檔
    foreach ($extra in @((Join-Path $env:APPDATA "npm"),
                         (Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Links"),
                         (Join-Path $env:ProgramFiles "nodejs"))) {
        if ($extra -and (Test-Path $extra) -and ($parts -notcontains $extra)) { $parts += $extra }
    }
    $env:Path = ($parts -join ";")
}

# ── winget（這台電腦上裝東西的方式） ────────────────────────────────────────
function Install-WithWinget {
    param([string]$Id, [string]$What, [string]$Url)
    Write-Warn2 "可能會跳出「使用者帳戶控制」視窗問你要不要允許——按「是」。"
    $rc = Invoke-Cmd "winget" @("install", "-e", "--id", $Id, "--silent",
                                "--accept-package-agreements", "--accept-source-agreements")
    # 0x8A15002B / -1978335189＝「已經裝好了」，算成功
    if ($rc -eq 0 -or $rc -eq -1978335189 -or $rc -eq 2316632107) {
        Update-PathFromRegistry
        return $true
    }
    Write-Bad ($What + " 沒成功（winget 回傳 " + $rc + "）。")
    Write-Note ("→ 照官方安裝檔手動裝：" + $Url)
    Add-Failure $What
    return $false
}

# ══ 先確認這是 Windows ════════════════════════════════════════════════════
$onWindows = $true
if ($PSVersionTable.PSVersion.Major -ge 6) { $onWindows = $IsWindows }
if (-not $onWindows) {
    Write-Host "X 這支只在 Windows 原生的 PowerShell 上跑。macOS 與 Linux 請跑：bash setup/bootstrap.sh" -ForegroundColor Red
    exit 1
}

# repo 根目錄＝這支腳本所在的 setup\ 的上一層；之後全程在那裡跑
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Repo = Split-Path -Parent $ScriptDir
Set-Location $Repo

Write-Host "教學記錄 kit：地基安裝（Windows）"
Write-Host ("資料夾：" + $Repo)
if ($DryRun) { Write-Host "(-DryRun：以下只印，不會裝任何東西，也不會改你的設定)" }

# ══ 老師要裝哪一家 AI 代理 ════════════════════════════════════════════════
if (-not $Agent) {
    if ($Yes) {
        $Agent = "none"
        Write-Note "沒指定 -Agent，這一輪不裝 AI 代理（要裝就加 -Agent claude／codex／gemini）。"
    } else {
        Write-Host ""
        Write-Host "你訂的是哪一家的 AI？裝好之後，就是它帶你把整套系統裝起來。"
        Write-Host "  1) Claude Code（你有 Claude 訂閱）"
        Write-Host "  2) OpenAI Codex CLI（你有 ChatGPT 訂閱）"
        Write-Host "  3) Gemini CLI（你有 Google 帳號）"
        Write-Host "  4) 先不要裝，我自己來"
        $pick = Read-Host "請輸入 1-4（直接按 Enter＝1）"
        switch ($pick) {
            "2" { $Agent = "codex" }
            "3" { $Agent = "gemini" }
            "4" { $Agent = "none" }
            default { $Agent = "claude" }
        }
    }
}

if (-not $Yes -and -not $DryRun) {
    Write-Host ""
    Write-Host ("接下來會裝：git、Python、Node.js，以及 AI 代理（" + $Agent + "）。")
    Write-Host "中途可能會跳出「使用者帳戶控制」視窗，按「是」就好。"
    Read-Host "按 Enter 繼續（要取消就直接關掉這個視窗）" | Out-Null
}

# ══ winget ════════════════════════════════════════════════════════════════
Write-Step "winget（Windows 10／11 內建的安裝程式）"
if (Test-Tool "winget") {
    Write-Ok ("有了　" + (Get-ToolVersion "winget" @("--version")))
} else {
    Write-Bad "這台電腦上沒有 winget，後面的 git／Python／Node.js 沒辦法自動裝。"
    Write-Note "→ 開 Microsoft Store 搜尋「應用程式安裝程式／App Installer」更新它，"
    Write-Note "   或到 https://aka.ms/getwinget 下載安裝，裝完重開 PowerShell 再跑一次這支。"
    Write-Note "   學校電腦被鎖住的話，請資訊組幫忙開，或照 docs\PLATFORMS.md 手動裝三個工具。"
    exit 1
}

# ══ git ═══════════════════════════════════════════════════════════════════
Write-Step "git（取得與更新這份 kit；Claude Code 的指令工具也要它附的 bash）"
$gitVer = Get-ToolVersion "git" @("--version")
if ($gitVer) {
    Write-Ok $gitVer
} else {
    Install-WithWinget "Git.Git" "安裝 git" "https://git-scm.com/download/win" | Out-Null
}

# ══ Python 3 ══════════════════════════════════════════════════════════════
# Windows 的 python／python3 可能只是「開 Microsoft Store」的假殼（退出碼 9009）。
# 這裡真的跑一次才算數——同 scripts\hostos.py 的 python_cmd()。
function Get-PythonCmd {
    $v = Get-ToolVersion "py" @("-3", "--version")
    if ($v -match "Python 3\.(\d+)") { if ([int]$Matches[1] -ge 9) { return "py -3" } }
    $v = Get-ToolVersion "python" @("--version")
    if ($v -match "Python 3\.(\d+)") { if ([int]$Matches[1] -ge 9) { return "python" } }
    return ""
}

Write-Step "Python 3（這套 kit 的腳本全部是 Python）"
$pyCmd = Get-PythonCmd
if ($pyCmd) {
    $pyParts = $pyCmd.Split(" ")
    $pyVerArgs = @()
    if ($pyParts.Count -gt 1) { $pyVerArgs = @($pyParts[1]) }
    $pyVerArgs += "--version"
    Write-Ok ($pyCmd + "　" + (Get-ToolVersion $pyParts[0] $pyVerArgs))
} else {
    Write-Note "沒有真的 Python（打 python 只會跳出 Microsoft Store 的那種不算）。"
    if (Install-WithWinget "Python.Python.3.13" "安裝 Python" "https://www.python.org/downloads/windows/") {
        $pyCmd = Get-PythonCmd
        if ($pyCmd) { Write-Ok ("裝好了：" + $pyCmd) }
    }
}

# ══ Node.js ═══════════════════════════════════════════════════════════════
Write-Step "Node.js 20 以上（Firebase CLI 要用它才能跑）"
$nodeVer = Get-ToolVersion "node" @("-v")
$nodeMajor = 0
if ($nodeVer -match "v?(\d+)") { $nodeMajor = [int]$Matches[1] }
if ($nodeMajor -ge 20) {
    Write-Ok ("Node " + $nodeVer)
} else {
    if ($nodeMajor -gt 0) { Write-Note ("目前是 v" + $nodeMajor + "，太舊了。") }
    Install-WithWinget "OpenJS.NodeJS.LTS" "安裝 Node.js" "https://nodejs.org/" | Out-Null
}

# ══ AI 代理 CLI ═══════════════════════════════════════════════════════════
# 這張表是 scripts\hostos.py 的 AGENT_CLIS 的手抄本（Python 那時候還沒裝好，讀不到那張表）。
function Install-Agent([string]$which) {
    if ($which -eq "none") {
        Write-Step "AI 代理"
        Write-Note "你選了先不裝，跳過。"
        return
    }
    $label = ""; $url = ""
    switch ($which) {
        "claude" { $label = "Claude Code（要有 Claude 訂閱）"; $url = "https://docs.claude.com/en/docs/claude-code/setup" }
        "codex"  { $label = "OpenAI Codex CLI（要有 ChatGPT 訂閱）"; $url = "https://developers.openai.com/codex/cli/" }
        "gemini" { $label = "Gemini CLI（要有 Google 帳號）"; $url = "https://github.com/google-gemini/gemini-cli" }
    }
    Write-Step ("AI 代理：" + $label)
    Update-PathFromRegistry
    if ((Test-Tool $which) -and -not $DryRun) {
        Write-Ok ("已經有了（" + (Get-Command $which).Source + "），跳過。")
        return
    }

    if ($which -eq "claude") {
        $okc = Install-WithWinget "Anthropic.ClaudeCode" "安裝 Claude Code" $url
        if (-not $okc) {
            Write-Note "改走備案：官方 PowerShell 安裝程式"
            $rc = Invoke-Cmd "powershell" @("-NoProfile", "-ExecutionPolicy", "Bypass",
                                            "-Command", "irm https://claude.ai/install.ps1 | iex")
            if ($rc -ne 0) { Write-Note ("→ 備案也沒成。照官方說明裝：" + $url) }
        }
    } else {
        $pkg = "@openai/codex"
        if ($which -eq "gemini") { $pkg = "@google/gemini-cli" }
        if (-not (Test-Tool "npm") -and -not $DryRun) {
            Write-Bad "找不到 npm（它跟著 Node.js 一起裝）。"
            Write-Note "→ 先把上面的 Node.js 裝好、重開 PowerShell，再跑一次這支腳本。"
            Add-Failure $label
            return
        }
        $rc = Invoke-Cmd "npm" @("install", "-g", $pkg)
        if ($rc -ne 0) {
            Write-Bad ($label + " 沒裝成（npm 回傳 " + $rc + "）。")
            Write-Note ("→ 照官方說明裝：" + $url)
            Add-Failure $label
        }
    }

    Update-PathFromRegistry
    if (-not $DryRun) {
        if (Test-Tool $which) {
            Write-Ok ("裝好了（" + (Get-Command $which).Source + "）")
        } else {
            Write-Bad ("裝完還是叫不到 " + $which + "。")
            Write-Note ("→ 關掉這個視窗、開一個新的 PowerShell，再打一次 " + $which + "；還是沒有就照官方說明裝：" + $url)
            Add-Failure $label
        }
    }
}

Install-Agent $Agent

# ══ 交棒給 Python 那一層 ═══════════════════════════════════════════════════
Update-PathFromRegistry
$pyCmd = Get-PythonCmd
if (-not $pyCmd) { $pyCmd = "py -3" }
$pyFile = $pyCmd.Split(" ")[0]
$pyArgs = @()
if ($pyCmd.Split(" ").Count -gt 1) { $pyArgs = @($pyCmd.Split(" ")[1]) }

Write-Step "其餘工具（Firebase CLI、gcloud、ffmpeg、語音轉逐字稿）"
if ($DryRun) {
    if (Test-Tool $pyFile) {
        Write-Note ("(-DryRun) 接著會跑：" + $pyCmd + " scripts\install_tools.py")
        & $pyFile @($pyArgs + @("scripts\install_tools.py", "--dry-run"))
    } else {
        Write-Note ("(-DryRun) 這台電腦還沒有 Python；真的跑的話這裡會先裝好它，再跑 " + $pyCmd + " scripts\install_tools.py")
    }
} else {
    if (Test-Tool $pyFile) {
        & $pyFile @($pyArgs + @("scripts\install_tools.py"))
        if ($LASTEXITCODE -ne 0) { Write-Note "(install_tools.py 有項目沒裝成，下面的健檢會逐項說)" }
    } else {
        Write-Bad "還是沒有 Python，沒辦法接著跑 scripts\install_tools.py。"
        Write-Note "→ 到 https://www.python.org/downloads/windows/ 下載安裝（記得勾 Add python.exe to PATH），裝完重跑這支腳本。"
        Add-Failure "Python 3"
    }
}

Write-Step "健檢"
if ($DryRun) {
    Write-Note ("(-DryRun) 接著會跑：" + $pyCmd + " scripts\doctor.py")
} elseif (Test-Tool $pyFile) {
    & $pyFile @($pyArgs + @("scripts\doctor.py"))
    Write-Note "上面「設定檔」「產生檔」那幾項是 X 很正常——那些要等 AI 代理帶你做完設定才會有。"
}

# ══ 下一步（這段是整支腳本的重點，要老師照著做） ═══════════════════════════
$launch = ""
switch ($Agent) {
    "claude" { $launch = 'claude "' + $script:Prompt + '"' }
    "codex"  { $launch = 'codex "' + $script:Prompt + '"' }
    "gemini" { $launch = 'gemini -i "' + $script:Prompt + '"' }
}

Write-Host ""
Write-Host "========================================================"
if ($script:Failed.Count -gt 0) {
    Write-Host ("有幾項沒裝成：" + ($script:Failed -join "、"))
    Write-Host "上面每一項底下都印了官方網址。裝好再跑一次這支腳本（重跑是安全的，裝好的會自動跳過）。"
    Write-Host ""
}
Write-Host "地基鋪好了。接下來三個動作："
Write-Host ""
Write-Host "  (1) 關掉這個視窗，重新開一個新的 Windows 終端機或 PowerShell"
Write-Host "      （剛裝好的程式要新視窗才叫得到）。"
Write-Host "  (2) 在新視窗裡貼這一行，切到這個資料夾："
Write-Host ""
Write-Host ("        cd `"" + $Repo + "`"")
Write-Host ""
if ($launch) {
    Write-Host "  (3) 再貼這一行，把 AI 叫起來（第一次會請你登入你的訂閱帳號）："
    Write-Host ""
    Write-Host ("        " + $launch)
    Write-Host ""
    Write-Host "  之後你只要回答它的問題就好——它一次只問一題，每一題都會告訴你去哪裡拿答案。"
} else {
    Write-Host "  (3) 把你的 AI 代理叫起來（claude／codex／gemini 都行），對它說："
    Write-Host ""
    Write-Host ("        " + $script:Prompt)
}
Write-Host "========================================================"
exit 0
