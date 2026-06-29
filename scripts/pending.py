#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pending.py — 列出「有觀察、但還沒處理寄家長」的紀錄（給 SessionStart hook 或手動用）
  「已處理」＝ .parent-emails-handled.tsv（status=sent 由 parent_email.py 記；skip 由本工具 --mark 記）
  沒待處理就無輸出（安靜）。
用法：
  pending.py                       列出待處理
  pending.py --all                 連已處理也列
  pending.py --mark S-01 2026-09-15 skip   標記（之後不再提醒）
"""
import os, re, sys
from datetime import datetime
import lib

HANDLED = os.path.join(lib.ROOT, ".parent-emails-handled.tsv")


def load_handled():
    s = set()
    if os.path.exists(HANDLED):
        for line in open(HANDLED, encoding="utf-8"):
            p = line.rstrip("\n").split("\t")
            if len(p) >= 2: s.add((p[0], p[1]))
    return s


def main():
    if len(sys.argv) >= 5 and sys.argv[1] == "--mark":
        with open(HANDLED, "a", encoding="utf-8") as f:
            f.write("%s\t%s\t%s\t%s\n" % (sys.argv[2], sys.argv[3], sys.argv[4], datetime.now().isoformat(timespec="seconds")))
        print("已標記 %s %s = %s" % (sys.argv[2], sys.argv[3], sys.argv[4])); return

    cfg = lib.load_config()
    names = lib.load_roster(cfg)
    sdir = lib.students_dir(cfg)
    handled = set() if "--all" in sys.argv else load_handled()
    pending = []
    if os.path.isdir(sdir):
        for sid in sorted(os.listdir(sdir)):
            obs = os.path.join(sdir, sid, "observations.md")
            if not os.path.isfile(obs):
                continue
            for r in lib.parse_blocks(obs):
                if (sid, r["date"]) not in handled:
                    pending.append((sid, names.get(sid, sid), r["date"], " ".join(r["tags"])))
    if not pending:
        return
    print("[提醒｜以下觀察尚未處理寄家長]")
    for sid, name, date, tags in pending:
        print(("  · %s %s：%s %s" % (sid, name, date, tags)).rstrip())
    print("（AI：主動問老師要不要寄。寄→跑 parent_email.py（先校對再寄、帶 --date）；"
          "不寄→ pending.py --mark <代號> <日期> skip。）")


if __name__ == "__main__":
    main()
