#!/usr/bin/env bash
# install_tools.sh — 在 macOS 上裝齊 teacher-records-kit 需要的外部工具。
#
# 用途：
#   本 kit 對外只靠幾支外部工具（Node.js／firebase-tools／Google Cloud SDK／
#   ffmpeg／whisper-cpp），這支腳本負責把它們裝齊，裝好之後請跑
#   `python3 scripts/doctor.py` 逐項健檢。
#
# 用法：
#   bash scripts/install_tools.sh              # 逐項安裝，已裝好的自動跳過
#   bash scripts/install_tools.sh --dry-run    # 只印每一步「會做什麼」，不實際安裝
#   bash scripts/install_tools.sh --with-gws   # 額外裝 googleworkspace-cli（備份走 gws 進階模式才需要）
#   bash scripts/install_tools.sh --help       # 顯示這段說明
#
# 零第三方相依：本腳本只呼叫系統既有指令與 Homebrew／npm。
set -uo pipefail

DRY_RUN=0
WITH_GWS=0

print_help() {
  cat <<'EOF'
install_tools.sh — 裝齊 teacher-records-kit 需要的外部工具

用法：
  bash scripts/install_tools.sh              逐項安裝，已裝好的自動跳過
  bash scripts/install_tools.sh --dry-run    只印每一步「會做什麼」，不實際安裝或修改任何東西
  bash scripts/install_tools.sh --with-gws   額外裝 googleworkspace-cli（備份走 gws 進階模式才需要，預設跳過）
  bash scripts/install_tools.sh --help       顯示這段說明

會裝的工具：
  node              Firebase CLI 需要（brew install node）
  firebase-tools    部署安全規則與網站要用（npm i -g firebase-tools）
  google-cloud-sdk  本機腳本讀寫 Firestore 要靠 gcloud 拿權杖（brew install --cask google-cloud-sdk）
  ffmpeg            錄音轉檔要用（brew install ffmpeg）
  whisper-cpp       本機語音轉逐字稿、錄音不出本機（brew install whisper-cpp）
  googleworkspace-cli（選用，--with-gws 才裝）
                    只有備份要走 gws 進階模式才需要；預設備份模式（把 zip 複製進
                    「Google 雲端硬碟」桌面同步夾）不需要它。

裝完之後：
  python3 scripts/doctor.py   逐項健檢，確認工具與登入狀態都齊了
EOF
}

for arg in "$@"; do
  case "$arg" in
    --help|-h) print_help; exit 0 ;;
    --dry-run) DRY_RUN=1 ;;
    --with-gws) WITH_GWS=1 ;;
    *)
      echo -e "\033[31m✗ 不認得的參數：$arg\033[0m"
      echo "→ 用 bash scripts/install_tools.sh --help 看可用參數。"
      exit 1
      ;;
  esac
done

# ── 非 macOS：本腳本只處理 Homebrew，Windows／Linux 請自行安裝 ──
if [ "$(uname)" != "Darwin" ]; then
  cat <<'EOF'
這支腳本只處理 macOS（靠 Homebrew）。你目前的系統不是 macOS，請自行安裝下列工具：

  Node.js（含 npm）
    https://nodejs.org/

  firebase-tools（裝好 Node.js 後）
    npm install -g firebase-tools
    https://firebase.google.com/docs/cli

  Google Cloud SDK（gcloud，本機腳本讀寫 Firestore 要用它拿權杖）
    https://cloud.google.com/sdk/docs/install
    裝完請跑一次：gcloud auth login

  ffmpeg（錄音轉檔）
    https://ffmpeg.org/download.html

  whisper.cpp（本機語音轉逐字稿，錄音才不會離開你的電腦）
    https://github.com/ggml-org/whisper.cpp

裝好以上工具後，請跑：python3 scripts/doctor.py 逐項健檢。
EOF
  exit 0
fi

# ── 統計 ──
STEP_OK=0
STEP_FAIL=0

# 印一步的「要裝什麼、為什麼」說明
step_intro() {
  echo "── $1"
  echo "   為什麼需要：$2"
}

# 執行安裝指令（或在 --dry-run 下只印出來）；$1=描述用指令陣列（字串）
run_or_show() {
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "  （--dry-run，不執行）將會跑：$*"
    return 0
  fi
  echo "  執行：$*"
  "$@"
}

# ── 0. Homebrew 存不存在（不自動安裝）──
if ! command -v brew >/dev/null 2>&1; then
  echo -e "\033[31m✗ 找不到 Homebrew\033[0m"
  echo "→ 本腳本靠 Homebrew 裝 node／google-cloud-sdk／ffmpeg／whisper-cpp，請先手動安裝："
  echo '  /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'
  echo "  安裝完請重開一個新的終端機視窗（或依安裝程式提示把 Homebrew 加進 PATH），再重跑本腳本。"
  exit 1
fi

# ── 1. node（Firebase CLI 需要） ──
step_intro "node" "Firebase CLI（firebase-tools）需要 Node.js 才能跑。"
if command -v node >/dev/null 2>&1; then
  echo "✓ 已安裝，跳過"
  STEP_OK=$((STEP_OK+1))
else
  if run_or_show brew install node; then
    STEP_OK=$((STEP_OK+1))
  else
    echo -e "\033[31m✗ node 安裝失敗\033[0m"
    echo "→ 手動跑 brew install node 看完整錯誤訊息，或改用 https://nodejs.org/ 官方安裝檔。"
    STEP_FAIL=$((STEP_FAIL+1))
  fi
fi

# ── 2. firebase-tools（部署安全規則與網站要用） ──
step_intro "firebase-tools" "部署 Firestore 安全規則與網站（Firebase Hosting）要用這支 CLI。"
if command -v firebase >/dev/null 2>&1; then
  echo "✓ 已安裝，跳過"
  STEP_OK=$((STEP_OK+1))
else
  if run_or_show npm i -g firebase-tools; then
    STEP_OK=$((STEP_OK+1))
  else
    echo -e "\033[31m✗ firebase-tools 安裝失敗\033[0m"
    echo "→ 確認 node／npm 已裝好且有寫入權限，必要時改用 sudo npm i -g firebase-tools。"
    STEP_FAIL=$((STEP_FAIL+1))
  fi
fi

# ── 3. google-cloud-sdk（gcloud，本機腳本讀寫 Firestore 要用它拿權杖） ──
step_intro "google-cloud-sdk（gcloud）" "本機腳本（sync.py 等）要靠 gcloud auth print-access-token 拿權杖才能讀寫 Firestore。"
if command -v gcloud >/dev/null 2>&1; then
  echo "✓ 已安裝，跳過"
  STEP_OK=$((STEP_OK+1))
else
  if run_or_show brew install --cask google-cloud-sdk; then
    STEP_OK=$((STEP_OK+1))
    echo "  裝完請跑一次：gcloud auth login（用你這個 Firebase 專案的擁有者帳號登入）"
  else
    echo -e "\033[31m✗ google-cloud-sdk 安裝失敗\033[0m"
    echo "→ 改用官方安裝檔：https://cloud.google.com/sdk/docs/install ，裝完一樣要跑 gcloud auth login。"
    STEP_FAIL=$((STEP_FAIL+1))
  fi
fi

# ── 4. ffmpeg（錄音轉檔） ──
step_intro "ffmpeg" "transcribe.py 要用它把錄音檔轉成 whisper 看得懂的 16k wav。"
if command -v ffmpeg >/dev/null 2>&1; then
  echo "✓ 已安裝，跳過"
  STEP_OK=$((STEP_OK+1))
else
  if run_or_show brew install ffmpeg; then
    STEP_OK=$((STEP_OK+1))
  else
    echo -e "\033[31m✗ ffmpeg 安裝失敗\033[0m"
    echo "→ 手動跑 brew install ffmpeg 看完整錯誤訊息。"
    STEP_FAIL=$((STEP_FAIL+1))
  fi
fi

# ── 5. whisper-cpp（本機語音轉逐字稿，錄音不出本機） ──
step_intro "whisper-cpp" "transcribe.py 用它在本機把錄音轉成逐字稿，錄音檔完全不會上傳到任何地方。"
if command -v whisper-cli >/dev/null 2>&1; then
  echo "✓ 已安裝，跳過"
  STEP_OK=$((STEP_OK+1))
else
  if run_or_show brew install whisper-cpp; then
    STEP_OK=$((STEP_OK+1))
  else
    echo -e "\033[31m✗ whisper-cpp 安裝失敗\033[0m"
    echo "→ 手動跑 brew install whisper-cpp 看完整錯誤訊息。"
    STEP_FAIL=$((STEP_FAIL+1))
  fi
fi

# ── 6.（選用）googleworkspace-cli，只有 --with-gws 才裝 ──
if [ "$WITH_GWS" -eq 1 ]; then
  step_intro "googleworkspace-cli（選用）" "只有備份要走 gws 進階模式才需要；預設備份模式不需要它。"
  echo -e "\033[33m注意：Homebrew formula 名稱是 googleworkspace-cli，不是 gws；brew install gws 會裝到完全不相干的套件。\033[0m"
  if command -v gws >/dev/null 2>&1; then
    echo "✓ 已安裝，跳過"
    STEP_OK=$((STEP_OK+1))
  else
    if run_or_show brew install googleworkspace-cli; then
      STEP_OK=$((STEP_OK+1))
    else
      echo -e "\033[31m✗ googleworkspace-cli 安裝失敗\033[0m"
      echo "→ 手動跑 brew install googleworkspace-cli 看完整錯誤訊息；不裝也沒關係，預設備份模式用不到它。"
      STEP_FAIL=$((STEP_FAIL+1))
    fi
  fi
else
  echo "── googleworkspace-cli（選用，跳過）"
  echo "   只有備份要走 gws 進階模式才需要；預設備份模式（複製 zip 進 Google 雲端硬碟同步夾）不需要它。"
  echo "   要裝請加 --with-gws 參數重跑本腳本。"
fi

# ── 結尾 ──
echo ""
echo "完成：成功 $STEP_OK 步、失敗 $STEP_FAIL 步"
echo "下一步：python3 scripts/doctor.py 逐項健檢"

if [ "$STEP_FAIL" -gt 0 ]; then
  exit 1
fi
exit 0
