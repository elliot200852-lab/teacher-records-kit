#!/usr/bin/env bash
# bootstrap.sh — 從一台「什麼都沒裝」的 macOS／Linux 開始，把地基鋪到 AI 代理能接手為止。
#
# 這一層做四件事，做完就交棒：
#   ① 命令列工具（macOS 的 Xcode Command Line Tools）② 套件管理程式（Homebrew／apt-get）
#   ③ git、Python 3、Node.js ④ 老師訂的那一家 AI 代理 CLI（Claude Code／Codex／Gemini）
#   ⑤ 最後回頭跑 scripts/install_tools.py 與 scripts/doctor.py，然後印出下一步。
#
# 為什麼這支是 shell 不是 Python：Python 本身可能還沒有。
# **這是整份 kit 唯一被允許重複平台事實的地方**（正本仍是 scripts/hostos.py ＋ docs/PLATFORMS.md，
# 那份文件的「bootstrap 層」有記這件事）；改了這裡的裝法，兩邊都要跟著改。
# 一個 OS 一支：macOS／Linux＝這支，Windows＝setup/bootstrap.ps1（按兩下 setup\bootstrap.cmd）。
#
# 用法：
#   bash setup/bootstrap.sh                      問你要裝哪一家 AI 代理，然後全自動
#   bash setup/bootstrap.sh --agent claude       直接指定（claude／codex／gemini／none）
#   bash setup/bootstrap.sh --dry-run            只印每一步會跑什麼，一個字都不裝
#   bash setup/bootstrap.sh --yes                不停下來問你「可以嗎」
#
# 失敗哲學跟 install_tools.py 一樣：**不自動重試、不留裝到一半的狀態**；
# 某一項裝不起來就印出官方網址繼續往下走，最後由 doctor.py 說到底缺什麼。

set -euo pipefail

DRY=0
YES=0
AGENT=""

# ── 參數 ──────────────────────────────────────────────────────────────────
while [ "$#" -gt 0 ]; do
  case "${1:-}" in
    --dry-run) DRY=1 ;;
    --yes|-y) YES=1 ;;
    --agent) shift; AGENT="${1:-}" ;;
    --agent=*) AGENT="${1#--agent=}" ;;
    --help|-h)
      sed -n '2,30p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "不認得的參數：${1}（--help 看用法）" >&2; exit 2 ;;
  esac
  shift || true
done

case "$AGENT" in
  ""|claude|codex|gemini|none) : ;;
  *) echo "--agent 只吃 claude／codex／gemini／none，收到的是：$AGENT" >&2; exit 2 ;;
esac

# ── 印東西（沒有顏色也要看得懂） ───────────────────────────────────────────────
if [ -t 1 ] && [ -z "${NO_COLOR:-}" ]; then
  C_G=$'\033[32m'; C_Y=$'\033[33m'; C_R=$'\033[31m'; C_D=$'\033[2m'; C_0=$'\033[0m'
else
  C_G=""; C_Y=""; C_R=""; C_D=""; C_0=""
fi
step() { printf '\n── %s\n' "$1"; }
ok()   { printf '  %s✓%s %s\n' "$C_G" "$C_0" "$1"; }
note() { printf '  %s%s%s\n' "$C_D" "$1" "$C_0"; }
warn() { printf '  %s! %s%s\n' "$C_Y" "$1" "$C_0"; }
bad()  { printf '  %s✗ %s%s\n' "$C_R" "$1" "$C_0"; }

FAILED=""
remember_failure() { FAILED="${FAILED}${FAILED:+、}$1"; }

# ── 跑指令（--dry-run 只印） ────────────────────────────────────────────────
run() {                       # run 指令 參數…
  if [ "$DRY" = "1" ]; then printf '  （--dry-run，不執行）將會跑：%s\n' "$*"; return 0; fi
  printf '  執行：%s\n' "$*"
  "$@"
}
run_sh() {                    # run_sh '整串含管線的指令'
  if [ "$DRY" = "1" ]; then printf '  （--dry-run，不執行）將會跑：%s\n' "$1"; return 0; fi
  printf '  執行：%s\n' "$1"
  bash -c "$1"
}
have() { command -v "$1" >/dev/null 2>&1; }

# 失敗不中斷：印出官方網址繼續走（哲學同 install_tools.py）
try() {                       # try '這一步的名字' '官方網址' 指令 參數…
  local what="$1" url="$2"; shift 2
  if run "$@"; then return 0; fi
  bad "$what 沒成功。"
  note "→ 照官方說明手動裝：$url"
  remember_failure "$what"
  return 1
}
try_sh() {                    # try_sh '這一步的名字' '官方網址' '整串含管線的指令'
  local what="$1" url="$2" cmd="$3"
  if run_sh "$cmd"; then return 0; fi
  bad "$what 沒成功。"
  note "→ 照官方說明手動裝：$url"
  remember_failure "$what"
  return 1
}

confirm() {                   # confirm '要問的話'；--yes 或非互動時直接當作答應
  [ "$YES" = "1" ] && return 0
  [ -t 0 ] || return 0
  printf '\n%s [Enter 繼續／Ctrl-C 取消] ' "$1"
  read -r _ || true
  return 0
}

# ── 這是哪一台電腦 ─────────────────────────────────────────────────────────
# WSL 直接拒跑。這段話是 scripts/hostos.py 的 unsupported_reason() 的手抄本，改要一起改。
if [ -r /proc/version ] && grep -qi microsoft /proc/version; then
  cat >&2 <<'WSLMSG'
✗ 你在 WSL（Windows 底下的 Linux）裡。
這套 kit 的備份要寫進「Google 雲端硬碟」桌面程式的同步夾、排程要掛在 Windows 的工作排程器，
這兩件事在 WSL 裡都看不到 Windows 那一邊，會靜靜地失效。
請關掉 WSL，改在 Windows 原生的 PowerShell 或 Windows Terminal 裡，
對 setup\bootstrap.cmd 按兩下重新開始。
WSLMSG
  exit 1
fi
if [ -n "${WSL_DISTRO_NAME:-}" ]; then
  echo "✗ 偵測到 WSL（\$WSL_DISTRO_NAME=${WSL_DISTRO_NAME}）。請改用 Windows 原生 PowerShell 跑 setup\\bootstrap.ps1。" >&2
  exit 1
fi

UNAME="$(uname -s 2>/dev/null || echo unknown)"
ARCH="$(uname -m 2>/dev/null || echo unknown)"
case "$UNAME" in
  Darwin) HOST_OS="mac" ;;
  Linux)  HOST_OS="linux" ;;
  *) echo "✗ 這支只支援 macOS 與 Linux（你的是 ${UNAME}）。Windows 請按兩下 setup\\bootstrap.cmd。" >&2; exit 1 ;;
esac

# repo 根目錄＝這支腳本所在的 setup/ 的上一層；之後全程在那裡跑
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO"

printf '%s\n' "教學記錄 kit：地基安裝（$( [ "$HOST_OS" = mac ] && echo macOS || echo Linux )／${ARCH}）"
printf '%s\n' "資料夾：$REPO"
[ "$DRY" = "1" ] && printf '%s\n' "（--dry-run：以下只印，不會裝任何東西，也不會改你的設定檔）"

# ── 老師要裝哪一家 AI 代理 ──────────────────────────────────────────────────
choose_agent() {
  [ -n "$AGENT" ] && return 0
  if [ "$YES" = "1" ] || [ ! -t 0 ]; then
    AGENT="none"
    note "沒指定 --agent，這一輪不裝 AI 代理（要裝就加 --agent claude／codex／gemini）。"
    return 0
  fi
  cat <<'MENU'

你訂的是哪一家的 AI？裝好之後，就是它帶你把整套系統裝起來。
  1) Claude Code（你有 Claude 訂閱）
  2) OpenAI Codex CLI（你有 ChatGPT 訂閱）
  3) Gemini CLI（你有 Google 帳號）
  4) 先不要裝，我自己來
MENU
  printf '請輸入 1－4（直接按 Enter＝1）：'
  local pick=""
  read -r pick || true
  case "${pick:-1}" in
    1|"") AGENT="claude" ;;
    2) AGENT="codex" ;;
    3) AGENT="gemini" ;;
    4) AGENT="none" ;;
    *) echo "看不懂「${pick}」，這一輪先不裝 AI 代理。"; AGENT="none" ;;
  esac
}
choose_agent

confirm "接下來會裝：命令列工具、套件管理程式、git／Python／Node.js，以及 AI 代理（${AGENT}）。中途可能要你輸入開機密碼。"

# ── 版本檢查小工具 ─────────────────────────────────────────────────────────
node_major() {
  have node || { echo 0; return 0; }
  local v; v="$(node -v 2>/dev/null || echo v0)"; v="${v#v}"
  echo "${v%%.*}"
}
python_ok() {
  have python3 || return 1
  python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' >/dev/null 2>&1
}

# ── 把一行加進 shell 設定檔（已經有就不加） ───────────────────────────────────
add_line_once() {             # add_line_once 檔案 要加的那一行 說明
  local file="$1" line="$2" what="$3"
  if [ -f "$file" ] && grep -qF "$line" "$file" 2>/dev/null; then
    note "$file 裡已經有 ${what}，不重複加。"
    return 0
  fi
  if [ "$DRY" = "1" ]; then
    printf '  （--dry-run，不執行）將會把這一行加進 %s：%s\n' "$file" "$line"
    return 0
  fi
  printf '  寫入 %s：%s\n' "$file" "$line"
  { [ -f "$file" ] && [ -s "$file" ] && printf '\n'; printf '%s\n' "$line"; } >> "$file"
}

# ══ macOS ════════════════════════════════════════════════════════════════
mac_command_line_tools() {
  step "Xcode 命令列工具（macOS 的 git、編譯器都在裡面）"
  if xcode-select -p >/dev/null 2>&1; then
    ok "已經有了（$(xcode-select -p 2>/dev/null)）"
    return 0
  fi
  warn "還沒有。接下來螢幕上會跳出一個視窗。"
  run xcode-select --install || true
  if [ "$DRY" = "1" ]; then
    note "（--dry-run：真的跑的話，這裡會停下來等你把視窗裝完。）"
    return 0
  fi
  cat <<'CLTMSG'

  請在跳出來的視窗按「安裝」，等它跑完（幾分鐘到十幾分鐘，看你的網路）。
  裝完之後，回到這個終端機視窗，把同一行指令再貼一次：

      bash setup/bootstrap.sh

  （已經在裝了就等它跑完再貼；視窗沒跳出來的話，到 https://developer.apple.com/download/all/
   下載「Command Line Tools for Xcode」自己裝。）
CLTMSG
  exit 1
}

mac_brew() {
  step "Homebrew（macOS 上裝東西的套件管理程式）"
  local brew_bin=""
  for p in /opt/homebrew/bin/brew /usr/local/bin/brew; do
    [ -x "$p" ] && brew_bin="$p" && break
  done
  if [ -z "$brew_bin" ] && have brew; then brew_bin="$(command -v brew)"; fi

  if [ -z "$brew_bin" ]; then
    warn "還沒有 Homebrew，現在裝（官方安裝程式，會問你的開機密碼）。"
    try_sh "安裝 Homebrew" "https://brew.sh" \
      'NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"' || true
    for p in /opt/homebrew/bin/brew /usr/local/bin/brew; do
      [ -x "$p" ] && brew_bin="$p" && break
    done
  else
    ok "已經有了（${brew_bin}）"
  fi

  if [ -z "$brew_bin" ]; then
    if [ "$DRY" = "1" ]; then
      # Apple Silicon 是 /opt/homebrew，Intel 是 /usr/local
      brew_bin="$( [ "$ARCH" = "arm64" ] && echo /opt/homebrew/bin/brew || echo /usr/local/bin/brew )"
      note "（--dry-run：底下就假設 Homebrew 會裝在 ${brew_bin}。）"
    else
      bad "Homebrew 還是沒有，後面的 git／Python／Node.js 沒辦法自動裝。"
      note "→ 到 https://brew.sh 複製首頁那一行指令自己跑一次，然後重跑這支腳本。"
      remember_failure "Homebrew"
      return 1
    fi
  fi

  BREW="$brew_bin"
  local prefix; prefix="$(dirname "$(dirname "$BREW")")"      # /opt/homebrew 或 /usr/local
  local shellenv="eval \"\$($BREW shellenv)\""
  step "把 Homebrew 放進你的 PATH（開新終端機也找得到）"
  add_line_once "$HOME/.zprofile" "$shellenv" "Homebrew 的 shellenv"
  add_line_once "$HOME/.bash_profile" "$shellenv" "Homebrew 的 shellenv"
  if [ "$DRY" = "0" ] && [ -x "$BREW" ]; then
    eval "$("$BREW" shellenv)"                                # 這個行程立刻生效
    ok "這個視窗已經吃得到 brew（${prefix}）"
  fi
  return 0
}

mac_base_tools() {
  step "git、Python 3、Node.js"
  local want=""
  have git || want="$want git"
  python_ok || want="$want python"
  [ "$(node_major)" -ge 20 ] 2>/dev/null || want="$want node"

  if [ -z "$want" ]; then
    ok "git $(git --version 2>/dev/null | awk '{print $3}')、Python $(python3 -V 2>/dev/null | awk '{print $2}')、Node $(node -v 2>/dev/null) 都夠新，跳過。"
    return 0
  fi
  note "要裝的是：${want}（其他的已經有了）"
  if [ -z "${BREW:-}" ]; then
    bad "沒有 Homebrew，裝不了${want}。"
    note "→ 到 https://brew.sh 裝好 Homebrew 再重跑這支腳本。"
    remember_failure "git／Python／Node.js"
    return 1
  fi
  # 一項一項裝：其中一項掛掉不要拖累其他項
  for f in $want; do
    try "安裝 $f" "https://brew.sh" "$BREW" install "$f" || true
  done
  return 0
}

# ══ Linux ════════════════════════════════════════════════════════════════
linux_base_tools() {
  step "git、Python 3、Node.js、curl（apt-get）"
  if ! have apt-get; then
    bad "這台電腦沒有 apt-get。"
    note "→ 這支腳本只會用 apt-get（Debian／Ubuntu 系）。請用你自己的套件管理程式裝 git、python3、nodejs、curl，再跑 $ python3 scripts/install_tools.py"
    remember_failure "apt-get"
    return 1
  fi
  local want=""
  have git || want="$want git"
  python_ok || want="$want python3"
  have node || want="$want nodejs"
  have npm || want="$want npm"
  have curl || want="$want curl"
  if [ -z "$want" ]; then
    ok "git、Python、Node.js、curl 都有了，跳過。"
  else
    note "要裝的是：$want"
    try "apt-get update" "https://packages.debian.org" sudo apt-get update || true
    # shellcheck disable=SC2086
    try "安裝$want" "https://nodejs.org/" sudo apt-get install -y $want || true
  fi
  if [ "$DRY" = "0" ] && [ "$(node_major)" -lt 20 ] 2>/dev/null; then
    warn "Node.js 是 v$(node_major)，Firebase CLI 要 20 以上。"
    note "→ 這支不會自己動你的套件來源。請照 NodeSource 的官方說明裝新版："
    note "   https://github.com/nodesource/distributions#installation-instructions"
    note "   （裝完重開終端機，再跑一次這支腳本。）"
  fi
  return 0
}

# ══ AI 代理 CLI ═══════════════════════════════════════════════════════════
# 這張表是 scripts/hostos.py 的 AGENT_CLIS 的手抄本（Python 還沒裝好，讀不到那張表）。
ensure_local_bin_on_path() {
  # Claude Code 的原生安裝程式會把 claude 放進 ~/.local/bin
  local line='export PATH="$HOME/.local/bin:$PATH"'
  case ":${PATH}:" in
    *":$HOME/.local/bin:"*) note "~/.local/bin 已經在 PATH 裡。" ;;
    *)
      add_line_once "$HOME/.zprofile" "$line" "~/.local/bin"
      add_line_once "$HOME/.bash_profile" "$line" "~/.local/bin"
      [ "$DRY" = "0" ] && export PATH="$HOME/.local/bin:$PATH"
      ;;
  esac
}

install_agent() {
  local agent="$1"
  [ "$agent" = "none" ] && { step "AI 代理"; note "你選了先不裝，跳過。"; return 0; }

  local cmd="$agent" label url
  case "$agent" in
    claude) label="Claude Code（要有 Claude 訂閱）"; url="https://docs.claude.com/en/docs/claude-code/setup" ;;
    codex)  label="OpenAI Codex CLI（要有 ChatGPT 訂閱）"; url="https://developers.openai.com/codex/cli/" ;;
    gemini) label="Gemini CLI（要有 Google 帳號）"; url="https://github.com/google-gemini/gemini-cli" ;;
  esac

  step "AI 代理：$label"
  ensure_local_bin_on_path
  if have "$cmd"; then
    ok "已經有了（$(command -v "$cmd")），跳過。"
    return 0
  fi

  case "$agent" in
    claude)
      if ! try_sh "安裝 Claude Code" "$url" 'curl -fsSL https://claude.ai/install.sh | bash'; then
        if [ "$HOST_OS" = "mac" ] && [ -n "${BREW:-}" ]; then
          note "改走備案：Homebrew"
          try "安裝 Claude Code（備案）" "$url" "$BREW" install --cask claude-code || true
        fi
      fi
      ;;
    codex)
      if ! try_sh "安裝 Codex CLI" "$url" 'curl -fsSL https://chatgpt.com/codex/install.sh | sh'; then
        note "改走備案：npm"
        try "安裝 Codex CLI（備案）" "$url" npm install -g @openai/codex || true
      fi
      ;;
    gemini)
      if [ "$HOST_OS" = "mac" ] && [ -n "${BREW:-}" ]; then
        if ! try "安裝 Gemini CLI" "$url" "$BREW" install gemini-cli; then
          note "改走備案：npm"
          try "安裝 Gemini CLI（備案）" "$url" npm install -g @google/gemini-cli || true
        fi
      else
        try "安裝 Gemini CLI" "$url" npm install -g @google/gemini-cli || true
      fi
      ;;
  esac

  if [ "$DRY" = "0" ]; then
    hash -r 2>/dev/null || true
    if have "$cmd"; then
      ok "裝好了（$(command -v "$cmd")）"
    else
      bad "裝完還是叫不到 ${cmd}。"
      note "→ 關掉這個終端機視窗、開一個新的，再打一次 ${cmd}；還是沒有就照官方說明裝：$url"
      remember_failure "$label"
    fi
  fi
}

# ══ 開跑 ═════════════════════════════════════════════════════════════════
if [ "$HOST_OS" = "mac" ]; then
  mac_command_line_tools
  mac_brew || true
  mac_base_tools || true
else
  linux_base_tools || true
fi

install_agent "$AGENT"

# ── 交棒給 Python 那一層 ────────────────────────────────────────────────────
step "其餘工具（Firebase CLI、gcloud、ffmpeg、語音轉逐字稿）"
PYBIN="python3"
have python3 || PYBIN=""
if [ -z "$PYBIN" ] && [ "$DRY" = "0" ]; then
  bad "還是沒有 python3，沒辦法接著跑 scripts/install_tools.py。"
  note "→ macOS：brew install python；Linux：sudo apt-get install -y python3。裝完重跑這支腳本。"
  remember_failure "Python 3"
else
  if [ "$DRY" = "1" ]; then
    note "（--dry-run）接著會跑：python3 scripts/install_tools.py --dry-run"
    python3 scripts/install_tools.py --dry-run || true
  else
    "$PYBIN" scripts/install_tools.py || note "（install_tools.py 有項目沒裝成，下面的健檢會逐項說）"
  fi
fi

step "健檢"
if have python3; then
  if [ "$DRY" = "1" ]; then
    note "（--dry-run）接著會跑：python3 scripts/doctor.py"
  else
    python3 scripts/doctor.py || true      # 設定檔還沒建，這裡本來就會有 ✗，不算失敗
    note "上面「設定檔」「產生檔」那幾項是 ✗ 很正常——那些要等 AI 代理帶你做完設定才會有。"
  fi
fi

# ── 下一步（這段是整支腳本的重點，要老師照著做） ────────────────────────────────
PROMPT='請完整讀 AGENTS.md，然後帶我從步驟 0 開始安裝'
case "$AGENT" in
  claude) LAUNCH="claude \"$PROMPT\"" ;;
  codex)  LAUNCH="codex \"$PROMPT\"" ;;
  gemini) LAUNCH="gemini -i \"$PROMPT\"" ;;
  *)      LAUNCH="" ;;
esac

printf '\n%s\n' "════════════════════════════════════════════════════════"
if [ -n "$FAILED" ]; then
  printf '%s\n' "有幾項沒裝成：$FAILED"
  printf '%s\n' "上面每一項底下都印了官方網址。裝好再跑一次這支腳本（重跑是安全的，裝好的會自動跳過）。"
  printf '\n'
fi
printf '%s\n' "地基鋪好了。接下來三個動作："
printf '%s\n' ""
printf '%s\n' "  ① 關掉這個終端機視窗，重新開一個新的（剛裝好的程式要新視窗才叫得到）。"
printf '%s\n' "  ② 在新視窗裡貼這一行，切到這個資料夾："
printf '%s\n' ""
printf '%s\n' "        cd \"$REPO\""
printf '%s\n' ""
if [ -n "$LAUNCH" ]; then
  printf '%s\n' "  ③ 再貼這一行，把 AI 叫起來（第一次會請你登入你的訂閱帳號）："
  printf '%s\n' ""
  printf '%s\n' "        $LAUNCH"
  printf '%s\n' ""
  printf '%s\n' "  之後你只要回答它的問題就好——它一次只問一題，每一題都會告訴你去哪裡拿答案。"
else
  printf '%s\n' "  ③ 把你的 AI 代理叫起來（claude／codex／gemini 都行），對它說："
  printf '%s\n' ""
  printf '%s\n' "        $PROMPT"
fi
printf '%s\n' "════════════════════════════════════════════════════════"
exit 0
