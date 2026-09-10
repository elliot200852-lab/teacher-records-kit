#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 site/dashboard.html 打包成一個「用瀏覽器直接點兩下就能開」的單檔預覽。

為什麼要這支：dashboard.html 平常靠兩個外部檔（js/kit-config.js、js/firebase-config.js）
才跑得起來，而 file:// 底下抓不到它們。這支把設定整段內聯進去、把所有外部 script
標籤拿掉、強制 KIT.demo = true，於是產出的檔案：

  · 零外部相依（沒有任何 <script src=>，也不會連 Firebase）
  · 資料是假的，只存在打開它的那個瀏覽器（localStorage）
  · 可以放進 Google Drive、寄給別人、離線開

輸出：preview/teacher-records-kit-預覽.html

用法：
    python3 scripts/build_preview.py
    python3 scripts/build_preview.py --config site/js/kit-config.js   # 用真的設定當形狀（仍會強制 demo）

只用 Python 3 標準庫，沒有第三方相依。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DASHBOARD = ROOT / "site" / "dashboard.html"
CONFIG_EXAMPLE = ROOT / "site" / "js" / "kit-config.example.js"
VERSION_FILE = ROOT / "VERSION"
OUT = ROOT / "preview" / "teacher-records-kit-預覽.html"

# <script src="js/kit-config.js"></script>（允許屬性順序不同、單雙引號、有無空白）
SCRIPT_SRC_RE = re.compile(
    r"""[ \t]*<script\b[^>]*\bsrc\s*=\s*(?P<q>["'])(?P<src>.*?)(?P=q)[^>]*>\s*</script>[ \t]*\n?""",
    re.IGNORECASE | re.DOTALL,
)

BANNER = """<!-- ════════════════════════════════════════════════════════════════
     這是自動產生的單檔預覽（scripts/build_preview.py），不要手改。
     · 正本＝site/dashboard.html ＋ site/js/kit-config.example.js
     · 固定示範模式：資料是假的，只存在打開它的那個瀏覽器
     · 零外部相依，file:// 直接開得起來
     ════════════════════════════════════════════════════════════════ -->
"""


def read_version() -> str:
    """VERSION 檔的內容（一行版本字串）。沒有這個檔就回空字串——
    網頁頁尾會自己顯示「版本未知」，不寫死任何版本號。"""
    try:
        return VERSION_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def inline_config(config_path: Path, version: str = "") -> str:
    """把設定檔內容包成一段 inline script，並強制進入示範模式。"""
    js = config_path.read_text(encoding="utf-8")
    # </script> 出現在 JS 字串裡會提早結束標籤——先拆開它。
    js = js.replace("</script>", "<\\/script>")
    # 版本字串走 json.dumps，引號與非 ASCII 都會被跳脫成安全的 JS 字面值。
    ver_line = (
        "/* ── 版本（取自 VERSION 檔，頁尾直接顯示它）── */\n"
        "window.KIT.version = %s;\n" % json.dumps(version, ensure_ascii=False)
    ) if version else "/* ── VERSION 檔不存在，頁尾會顯示「版本未知」── */\n"
    return (
        "<script>\n"
        "/* ── 內聯自 %s（由 build_preview.py 貼進來）── */\n"
        "%s\n"
        "%s"
        "/* ── 預覽檔固定示範模式：不連 Firebase、資料只存在這個瀏覽器 ── */\n"
        "window.KIT.demo = true;\n"
        "</script>\n" % (config_path.name, js.rstrip(), ver_line)
    )


def build(dashboard: Path, config_path: Path, out: Path) -> tuple[str, list[str]]:
    html = dashboard.read_text(encoding="utf-8")
    version = read_version()
    inlined = inline_config(config_path, version)
    dropped: list[str] = []
    used = {"config": False}

    def repl(m: re.Match) -> str:
        src = m.group("src")
        if "kit-config" in src:
            if used["config"]:
                dropped.append(src)
                return "<!-- build_preview: 重複的 %s 已移除 -->\n" % src
            used["config"] = True
            return inlined
        dropped.append(src)
        return "<!-- build_preview: 已移除外部相依 %s（預覽檔不連任何外部資源） -->\n" % src

    html = SCRIPT_SRC_RE.sub(repl, html)
    if not used["config"]:
        raise SystemExit("找不到 <script src=\"…kit-config.js\"> ——dashboard.html 的載入方式改過了？")

    # 標題加註「預覽」，免得跟真正的儀表板混在一起
    html = re.sub(r"<title>(.*?)</title>", lambda m: "<title>%s（預覽）</title>" % m.group(1), html, count=1)
    html = html.replace("<!doctype html>", "<!doctype html>\n" + BANNER, 1)

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    return html, dropped


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="產生單檔離線預覽")
    ap.add_argument("--dashboard", default=str(DASHBOARD))
    ap.add_argument("--config", default=str(CONFIG_EXAMPLE), help="要內聯的設定檔（預設用範本）")
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args(argv)

    dashboard, config_path, out = Path(args.dashboard), Path(args.config), Path(args.out)
    for p in (dashboard, config_path):
        if not p.exists():
            print("✗ 找不到 %s" % p, file=sys.stderr)
            return 1

    html, dropped = build(dashboard, config_path, out)

    # 自檢：產出的檔案不該再有任何外部 script
    leftovers = SCRIPT_SRC_RE.findall(html)
    if leftovers:
        print("✗ 產出的檔案還有外部 script：%s" % leftovers, file=sys.stderr)
        return 1

    size_kb = out.stat().st_size / 1024
    print("✓ 已產生 %s（%.0f KB）" % (out, size_kb))
    print("  內聯設定：%s" % config_path.name)
    ver = read_version()
    print("  版本：%s" % (ver or "（找不到 VERSION 檔，頁尾會顯示「版本未知」）"))
    for d in dropped:
        print("  移除外部相依：%s" % d)
    print("  示範模式：強制開啟（資料只存在打開它的瀏覽器）")
    print("  打開方式：在檔案上點兩下，或 open '%s'" % out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
