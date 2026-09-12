#!/usr/bin/env bash
# ══════════════════════════════════════════════════════════════════════
# build_user_guide_pdf.sh — 把 docs/USER-GUIDE.md 印成一本 A4 PDF
#
# 三步：
#   ① 跑 scripts/docs/shoot_user_guide_screens.mjs 拍畫面截圖（15 張 PNG）
#   ② pandoc gfm → html5，套 scripts/docs/manual.css
#   ③ 本機 Chrome 無頭 --print-to-pdf 印成 A4
#
# 截圖與中繼 HTML 一律落在系統暫存區，**repo 裡除了 preview/（已被 .gitignore
# 擋住）以外一個檔都不寫**。PNG 不進版本控制，這是這個 repo 的鐵則。
#
# 用法：
#   bash scripts/docs/build_user_guide_pdf.sh --out ~/Desktop/老師操作書.pdf
#
# 旗標：
#   --out <pdf>            輸出的 PDF（預設 <暫存區>/Teacher-Records-Kit-老師操作書.pdf）
#   --node-modules <dir>   有 playwright-core 的 node_modules（截圖要用）
#   --img <dir>            直接用這個目錄裡現成的 PNG，不重拍
#   --keep-work            印完不要刪中繼目錄（想看 HTML 長什麼樣時用）
#   --chrome <path>        指定 Chrome（也吃環境變數 TRK_CHROME）
#
# 需要：pandoc、Chrome／Chromium／Edge、node（要重拍截圖時）。
# ══════════════════════════════════════════════════════════════════════
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
MD="$ROOT/docs/USER-GUIDE.md"
CSS="$HERE/manual.css"
SHOOT="$HERE/shoot_user_guide_screens.mjs"

# 預設的 node_modules：開發這本手冊時用的那一個（裝了 playwright-core）。
# 換機器就自己帶 --node-modules。
DEFAULT_NODE_MODULES="/private/tmp/claude-501/-Users-Dave-MyWork/672412d6-7165-4dc9-9975-862e505b54af/scratchpad/shoot/node_modules"

OUT="${TMPDIR:-/tmp}/Teacher-Records-Kit-老師操作書.pdf"
NODE_MODULES="$DEFAULT_NODE_MODULES"
IMG_DIR=""
KEEP_WORK=0
CHROME="${TRK_CHROME:-}"

while [ $# -gt 0 ]; do
  case "$1" in
    --out) OUT="$2"; shift 2 ;;
    --node-modules) NODE_MODULES="$2"; shift 2 ;;
    --img) IMG_DIR="$2"; shift 2 ;;
    --chrome) CHROME="$2"; shift 2 ;;
    --keep-work) KEEP_WORK=1; shift ;;
    -h|--help) sed -n '2,26p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "✗ 不認得的旗標：${1}（--help 看用法）" >&2; exit 2 ;;
  esac
done

[ -f "$MD" ] || { echo "✗ 找不到 $MD" >&2; exit 1; }
[ -f "$CSS" ] || { echo "✗ 找不到 $CSS" >&2; exit 1; }
command -v pandoc >/dev/null || { echo "✗ 沒有 pandoc。macOS：brew install pandoc" >&2; exit 1; }

# ── Chrome：用 kit 自己那份候選清單（scripts/hostos.py），不要各寫一套 ──
if [ -z "$CHROME" ]; then
  CHROME="$(cd "$ROOT" && python3 -c '
import sys; sys.path.insert(0, "scripts")
import hostos
c = hostos.chrome_candidates()
print(c[0] if c else "")')"
fi
[ -n "$CHROME" ] && [ -x "$CHROME" ] || {
  echo "✗ 找不到可以印 PDF 的 Chrome／Chromium／Edge。用 --chrome 指路徑，或設環境變數 TRK_CHROME。" >&2
  exit 1
}

WORK="$(mktemp -d "${TMPDIR:-/tmp}/trk-user-guide.XXXXXX")"
cleanup() { [ "$KEEP_WORK" -eq 1 ] || rm -rf "$WORK"; }
trap cleanup EXIT

# ── ① 截圖 ────────────────────────────────────────────────────────────
if [ -n "$IMG_DIR" ]; then
  echo "── 用現成的截圖：$IMG_DIR"
  mkdir -p "$WORK/img"
  cp "$IMG_DIR"/*.png "$WORK/img/"
else
  command -v node >/dev/null || { echo "✗ 沒有 node，無法拍截圖（或改用 --img <目錄>）" >&2; exit 1; }
  [ -d "$NODE_MODULES/playwright-core" ] || {
    echo "✗ $NODE_MODULES 裡沒有 playwright-core。" >&2
    echo "  用 --node-modules <dir>/node_modules 指一個有的，或 --img <目錄> 用現成的截圖。" >&2
    exit 1
  }
  echo "── ① 拍截圖"
  NODE_PATH="$NODE_MODULES" node "$SHOOT" --out "$WORK/img"
fi
SHOT_COUNT="$(ls -1 "$WORK/img"/*.png 2>/dev/null | wc -l | tr -d ' ')"
echo "   截圖 $SHOT_COUNT 張"

# ── ② markdown → HTML ────────────────────────────────────────────────
echo "── ② pandoc gfm → html5"
cp "$MD" "$WORK/USER-GUIDE.md"
cp "$CSS" "$WORK/manual.css"
# implicit_figures：圖片單獨成段時包成 <figure>＋<figcaption>（圖說就是 alt 文字）
# pagetitle（不是 title）：只寫進 <title>，不會在內文再長出一個重複的大標題
pandoc "$WORK/USER-GUIDE.md" \
  --from=gfm+implicit_figures \
  --to=html5 \
  --standalone \
  --metadata pagetitle="Teacher Records Kit 老師操作書" \
  --css=manual.css \
  --output="$WORK/user-guide.html"

# 自檢：HTML 裡不該再出現成對的 **…** —— 出現就表示有一段粗體語法沒被解析
# （中文裡最常見的原因：粗體緊貼在「」（）⋮ 這種標點或符號旁邊，
#   pandoc 的左右側判定會讓那一對 ** 開不了或關不了。）
if grep -qE '\*\*[^*]+\*\*' "$WORK/user-guide.html"; then
  echo "！ HTML 裡還有成對的 ** ——有粗體語法沒被解析，去 docs/USER-GUIDE.md 找這幾行：" >&2
  grep -nEo '.{0,30}\*\*[^*]+\*\*.{0,20}' "$WORK/user-guide.html" | head -10 >&2
fi

# ── ③ HTML → PDF ─────────────────────────────────────────────────────
echo "── ③ Chrome --print-to-pdf"
mkdir -p "$(dirname "$OUT")"
rm -f "$OUT"
"$CHROME" \
  --headless=new \
  --disable-gpu \
  --no-sandbox \
  --no-first-run \
  --no-pdf-header-footer \
  --run-all-compositor-stages-before-draw \
  --virtual-time-budget=20000 \
  --user-data-dir="$WORK/chrome-profile" \
  --print-to-pdf="$OUT" \
  "file://$WORK/user-guide.html" >"$WORK/chrome.log" 2>&1 &
CHROME_PID=$!

# Chrome（--headless=new）常常「PDF 印完了，程序不肯結束」——直接 wait 會卡在這裡。
# 所以自己看門：檔案出現、而且大小連續兩秒沒變就當印完，然後把它收掉。
printed=0; last=-1; stable=0
for _ in $(seq 1 180); do
  if ! kill -0 "$CHROME_PID" 2>/dev/null; then          # 它自己結束了
    printed=1; break
  fi
  if [ -s "$OUT" ]; then
    cur="$(wc -c <"$OUT" | tr -d ' ')"
    if [ "$cur" = "$last" ]; then stable=$((stable + 1)); else stable=0; fi
    last="$cur"
    if [ "$stable" -ge 2 ]; then
      kill "$CHROME_PID" 2>/dev/null || true
      printed=1; break
    fi
  fi
  sleep 1
done
wait "$CHROME_PID" 2>/dev/null || true

if [ "$printed" -ne 1 ]; then
  kill -9 "$CHROME_PID" 2>/dev/null || true
  echo "✗ Chrome 印 PDF 沒印出東西（等了三分鐘），log：" >&2
  cat "$WORK/chrome.log" >&2
  exit 1
fi

[ -s "$OUT" ] || { echo "✗ 印出來是空檔：$OUT" >&2; exit 1; }
SIZE="$(du -h "$OUT" | cut -f1 | tr -d ' ')"
echo
# 變數一定要加大括號：後面緊接全形「（」的話，bash 會把那幾個位元組也當成變數名，
# 在 set -u 之下直接死在「未綁定的變數」。
echo "✓ 完成：${OUT}（${SIZE}）"
[ "$KEEP_WORK" -eq 1 ] && echo "  中繼檔留在：$WORK"
exit 0
