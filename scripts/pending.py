#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pending.py — 列出「已經有觀察、但還沒決定要不要寄給家長」的紀錄。

「已處理」＝ .parent-emails-handled.tsv 裡有那一筆（寄出時由 parent_email.py 記，
決定不寄時用 `--mark … skip` 自己記）。沒有待處理就完全不出聲（給啟動 hook 用）。

用法：
  python3 scripts/pending.py                            列出待處理
  python3 scripts/pending.py --all                      連已處理的也列
  python3 scripts/pending.py --mark S-01 2026-09-15 skip   標記為不用再提醒
"""
import os
import sys
import argparse
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib


def handled_path():
    return lib.rpath(".parent-emails-handled.tsv")


def load_handled():
    s = set()
    p = handled_path()
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            for line in f:
                parts = line.rstrip("\n").split("\t")
                if len(parts) >= 2:
                    s.add((parts[0], parts[1]))
    return s


def main():
    ap = argparse.ArgumentParser(description="列出還沒決定要不要寄家長的學生觀察")
    ap.add_argument("--all", action="store_true", help="連已處理的也列出來")
    ap.add_argument("--mark", nargs=3, metavar=("代號", "日期", "狀態"),
                    help="標記某一則（狀態通常寫 skip，表示決定不寄、之後不用再提醒）")
    lib.add_root_arg(ap)
    a = ap.parse_args()
    lib.apply_root(a)

    if a.mark:
        sid, date, status = a.mark
        with open(handled_path(), "a", encoding="utf-8") as f:
            f.write("%s\t%s\t%s\t%s\n" % (sid, date, status,
                                          datetime.now().isoformat(timespec="seconds")))
        print("已標記 %s %s ＝ %s" % (sid, date, status))
        return

    kit = lib.load_kit()
    tabs = lib.load_tabs()
    names = lib.load_roster(kit)
    handled = set() if a.all else load_handled()
    pending = []
    for t in lib.targets(kit, tabs):
        if t["kind"] != "students":
            continue
        _, blocks = lib.parse_file(t["path"])
        for r in blocks:
            if (t["id"], r["date"]) not in handled:
                pending.append((t["id"], names.get(t["id"], t["id"]), r["date"], " ".join(r["tags"])))
    if not pending:
        return
    print("［提醒｜以下觀察還沒決定要不要寄家長］")
    for sid, name, date, tags in pending:
        print(("  · %s %s：%s %s" % (sid, name, date, tags)).rstrip())
    print("（AI：主動問老師要不要寄。要寄→先給他看稿，再跑 parent_email.py（記得帶 --date）；"
          "不寄→ `python3 scripts/pending.py --mark <代號> <日期> skip`。）")


if __name__ == "__main__":
    main()
