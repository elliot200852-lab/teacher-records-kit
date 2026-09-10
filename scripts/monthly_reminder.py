#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
monthly_reminder.py — 把「本月還沒有任何紀錄」的學生名單寄給擁有者
  全班都記過了就不寄。本機跑（cron/launchd 每月一次）。
用法：python3 scripts/monthly_reminder.py [--dry-run] [--month 2026-09]
"""
import os, sys, argparse
from datetime import date
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib


def main():
    ap = argparse.ArgumentParser(description="把「本月還沒有任何紀錄」的學生名單寄給你自己")
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--month")
    a = ap.parse_args()
    kit = lib.load_kit()
    tabs = lib.load_tabs()
    to = kit.get("owner_email", "")
    if not to or "@" not in to:
        lib.die("config/kit.json 的 owner_email 還沒填。", "重跑 `python3 scripts/setup.py`。")
    names = lib.load_roster(kit)
    if not names:
        lib.die("名冊是空的（data/roster.csv）。", "用試算表填「代號,姓名,類型」三欄再存成 CSV。")
    ym = a.month or ("%04d-%02d" % (date.today().year, date.today().month))
    # 一位學生有好幾種記錄類型（導師班級、個案、IEP…），任何一種記過就算記過。
    paths = {}
    for t in lib.targets(kit, tabs):
        if t["kind"] == "students":
            paths.setdefault(t["id"], []).append(t["path"])

    def months(sid):
        out = set()
        for p in paths.get(sid) or []:
            out |= {r["date"][:7] for r in lib.parse_file(p)[1]}
        return out

    missing = [(i, n) for i, n in sorted(names.items()) if ym not in months(i)]
    done = len(names) - len(missing)
    print("本月 %s：已記 %d／%d，未記 %d" % (ym, done, len(names), len(missing)))
    if not missing:
        print("全班都記過了，不寄。"); return

    body = ("本月（%s）評量提醒\n\n以下 %d 位還沒有任何觀察紀錄：\n\n%s\n\n（已記 %d／%d）\n"
            % (ym, len(missing), "\n".join("　・%s %s" % (i, n) for i, n in missing), done, len(names)))
    subject = "【評量提醒】%s 還有 %d 位未記" % (ym, len(missing))
    if a.dry_run:
        print("--- 將寄給 %s ---\n%s\n%s" % (lib.mask_email(to), subject, body)); return
    lib.send_email(kit, [to], subject, body)
    lib.ok("已寄本月提醒給 %s" % lib.mask_email(to))


if __name__ == "__main__":
    main()
