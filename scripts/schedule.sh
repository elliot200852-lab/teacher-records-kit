#!/usr/bin/env bash
# schedule.sh — （選用）安裝 launchd 排程：每天同步、每週備份。
#
# 用途：
#   幫 sync.py（每天）與 backup.py（每週）掛上 macOS 排程，不用老師自己記得手動跑。
#   排程可能會靜默失敗（例如電腦沒開機、launchd 權限被擋），所以本 kit 的網頁頂端
#   會顯示「上次同步／備份幾天前」，真正要驗證排程有沒有生效請看那個數字，
#   不要只看 launchctl list 顯示有掛就以為它真的跑得動。
#
# 用法：
#   bash scripts/schedule.sh              安裝兩個 launchd 排程（每天 07:00 同步、每週日 08:00 備份）
#   bash scripts/schedule.sh --dry-run    只印會做的事，不寫檔、不安裝
#   bash scripts/schedule.sh --print-cron 只印等效的 crontab 兩行，不寫任何檔案
#   bash scripts/schedule.sh --uninstall  移除排程（bootout）並刪掉 plist
#   bash scripts/schedule.sh --help       顯示這段說明
#
# 零第三方相依：只用系統既有的 launchctl／python3。
set -uo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
LAUNCH_AGENTS_DIR="$HOME/Library/LaunchAgents"
SYNC_LABEL="com.teacher-records-kit.sync"
BACKUP_LABEL="com.teacher-records-kit.backup"
SYNC_PLIST="$LAUNCH_AGENTS_DIR/$SYNC_LABEL.plist"
BACKUP_PLIST="$LAUNCH_AGENTS_DIR/$BACKUP_LABEL.plist"

MODE="install"
DRY_RUN=0

print_help() {
  cat <<'EOF'
schedule.sh — （選用）安裝 launchd 排程：每天同步、每週備份

用法：
  bash scripts/schedule.sh              安裝排程：每天 07:00 跑 sync.py、每週日 08:00 跑 backup.py
  bash scripts/schedule.sh --dry-run    只印會做的事（會寫哪些檔、跑哪些指令），不實際寫檔或安裝
  bash scripts/schedule.sh --print-cron 只印等效的 crontab 兩行，不寫任何檔案（不想用 launchd 就抄這個）
  bash scripts/schedule.sh --uninstall  移除排程（launchctl bootout）並刪掉 plist 檔
  bash scripts/schedule.sh --help       顯示這段說明

排程會靜默失敗，驗證方式：
  安裝完不要只看 launchctl list 顯示有掛就放心；隔天早上打開 kit 的網頁，
  看頂端「上次同步 X 天前」的字樣——超過 7 天會變紅字，那才是真的知道排程
  有沒有跑起來的辦法。
EOF
}

for arg in "$@"; do
  case "$arg" in
    --help|-h) print_help; exit 0 ;;
    --dry-run) DRY_RUN=1 ;;
    --print-cron) MODE="print-cron" ;;
    --uninstall) MODE="uninstall" ;;
    *)
      echo -e "\033[31m✗ 不認得的參數：$arg\033[0m"
      echo "→ 用 bash scripts/schedule.sh --help 看可用參數。"
      exit 1
      ;;
  esac
done

# ── --print-cron：只印等效 crontab 兩行，不寫檔 ──
if [ "$MODE" = "print-cron" ]; then
  echo "等效的 crontab 兩行（crontab -e 貼進去）："
  echo ""
  echo "0 7 * * * cd $REPO_DIR && /usr/bin/python3 scripts/sync.py >> logs/sync.log 2>&1"
  echo "0 8 * * 0 cd $REPO_DIR && /usr/bin/python3 scripts/backup.py >> logs/backup.log 2>&1"
  exit 0
fi

# ── --uninstall：bootout 並刪 plist ──
if [ "$MODE" = "uninstall" ]; then
  echo "移除排程……"
  for label in "$SYNC_LABEL" "$BACKUP_LABEL"; do
    if [ "$DRY_RUN" -eq 1 ]; then
      echo "  （--dry-run，不執行）將會跑：launchctl bootout gui/$(id -u)/$label"
    else
      launchctl bootout "gui/$(id -u)/$label" 2>/dev/null
      echo "  已 bootout：${label}（若原本就沒裝，這行沒反應是正常的）"
    fi
  done
  for plist in "$SYNC_PLIST" "$BACKUP_PLIST"; do
    if [ -f "$plist" ]; then
      if [ "$DRY_RUN" -eq 1 ]; then
        echo "  （--dry-run，不執行）將會刪除：$plist"
      else
        rm -f "$plist"
        echo "  已刪除：$plist"
      fi
    fi
  done
  echo "完成。"
  exit 0
fi

# ── 安裝模式：先找 python3 絕對路徑 ──
PYTHON3_BIN="$(command -v python3 || true)"
if [ -z "$PYTHON3_BIN" ]; then
  echo -e "\033[31m✗ 找不到 python3\033[0m"
  echo "→ 先跑 bash scripts/install_tools.sh 把工具裝齊（或至少手動裝 python3）再重跑本腳本。"
  exit 1
fi

if [ "$DRY_RUN" -eq 1 ]; then
  echo "（--dry-run，不寫檔、不安裝）將會："
  echo "  1. mkdir -p \"$REPO_DIR/logs\""
  echo "  2. 寫入 ${SYNC_PLIST}（每天 07:00 跑 $PYTHON3_BIN $REPO_DIR/scripts/sync.py）"
  echo "  3. 寫入 ${BACKUP_PLIST}（每週日 08:00 跑 $PYTHON3_BIN $REPO_DIR/scripts/backup.py）"
  echo "  4. launchctl bootout gui/\$(id -u)/$SYNC_LABEL 2>/dev/null；launchctl bootstrap gui/\$(id -u) $SYNC_PLIST"
  echo "  5. launchctl bootout gui/\$(id -u)/$BACKUP_LABEL 2>/dev/null；launchctl bootstrap gui/\$(id -u) $BACKUP_PLIST"
  exit 0
fi

mkdir -p "$REPO_DIR/logs"

cat > "$SYNC_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$SYNC_LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON3_BIN</string>
        <string>$REPO_DIR/scripts/sync.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$REPO_DIR</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
    <key>StandardOutPath</key>
    <string>$REPO_DIR/logs/sync.log</string>
    <key>StandardErrorPath</key>
    <string>$REPO_DIR/logs/sync.log</string>
    <key>RunAtLoad</key>
    <false/>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>7</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
</dict>
</plist>
EOF

cat > "$BACKUP_PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$BACKUP_LABEL</string>
    <key>ProgramArguments</key>
    <array>
        <string>$PYTHON3_BIN</string>
        <string>$REPO_DIR/scripts/backup.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$REPO_DIR</string>
    <key>EnvironmentVariables</key>
    <dict>
        <key>PATH</key>
        <string>/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin</string>
    </dict>
    <key>StandardOutPath</key>
    <string>$REPO_DIR/logs/backup.log</string>
    <key>StandardErrorPath</key>
    <string>$REPO_DIR/logs/backup.log</string>
    <key>RunAtLoad</key>
    <false/>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Weekday</key>
        <integer>0</integer>
        <key>Hour</key>
        <integer>8</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
</dict>
</plist>
EOF

echo "已寫入 plist："
echo "  $SYNC_PLIST"
echo "  $BACKUP_PLIST"
echo ""

FAIL=0
for entry in "$SYNC_LABEL:$SYNC_PLIST" "$BACKUP_LABEL:$BACKUP_PLIST"; do
  label="${entry%%:*}"
  plist="${entry#*:}"
  echo "安裝排程：$label"
  launchctl bootout "gui/$(id -u)/$label" 2>/dev/null
  if launchctl bootstrap "gui/$(id -u)" "$plist" 2>/tmp/schedule-sh-err.$$; then
    echo "  ✓ 已安裝"
  else
    echo -e "  \033[31m✗ 安裝失敗（launchctl bootstrap 出錯）\033[0m"
    echo "  → 到「系統設定 → 隱私權與安全性 → 完整磁碟取用權」允許你用的終端機程式，再重跑本腳本；"
    echo "    或改用 bash scripts/schedule.sh --print-cron 拿 crontab 兩行自己排。"
    cat /tmp/schedule-sh-err.$$ 2>/dev/null
    FAIL=$((FAIL+1))
  fi
  rm -f /tmp/schedule-sh-err.$$
done

echo ""
echo "排程可能會靜默失敗（電腦沒開機、權限被擋等都看不到錯誤訊息），"
echo "所以網頁頂端會顯示「上次同步 X 天前」，超過 7 天會變紅字。"
echo "要驗證排程真的會跑，請明天早上打開 kit 的網頁看那個數字，不要只看 launchctl list 顯示有掛就放心。"

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
exit 0
