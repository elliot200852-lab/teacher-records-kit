#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
monthly_reminder.py — 把「本月還沒有任何紀錄」的學生名單寄給擁有者
  全班都記過了就不寄。本機跑（cron/launchd 每月一次）。
用法：monthly_reminder.py [--dry-run] [--month 2026-09]
"""
import os, sys, argparse
from datetime import date
import lib


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--month")
    a = ap.parse_args()
    cfg = lib.load_config()
    to = cfg.get("owner_email", "")
    if not to or "@" not in to:
        lib.die("config.yaml 的 owner_email 還沒填")
    names = lib.load_roster(cfg)
    sdir = lib.students_dir(cfg)
    if not names:
        lib.die("名冊是空的（data/roster.csv）")
    ym = a.month or ("%04d-%02d" % (date.today().year, date.today().month))

    def months(sid):
        obs = os.path.join(sdir, sid, "observations.md")
        return {r["date"][:7] for r in lib.parse_blocks(obs)} if os.path.isfile(obs) else set()

    missing = [(i, n) for i, n in sorted(names.items()) if ym not in months(i)]
    done = len(names) - len(missing)
    print("本月 %s：已記 %d／%d，未記 %d" % (ym, done, len(names), len(missing)))
    if not missing:
        print("全班都記過了，不寄。"); return

    body = ("本月（%s）評量提醒\n\n以下 %d 位還沒有任何觀察紀錄：\n\n%s\n\n（已記 %d／%d）\n"
            % (ym, len(missing), "\n".join("　・%s %s" % (i, n) for i, n in missing), done, len(names)))
    subject = "【評量提醒】%s 還有 %d 位未記" % (ym, len(missing))
    if a.dry_run:
        print("--- 將寄給 %s ---\n%s\n%s" % (lib.mask(to), subject, body)); return
    lib.send_email(cfg, [to], subject, body)
    print("\033[32m✓ 已寄本月提醒給 %s\033[0m" % lib.mask(to))


if __name__ == "__main__":
    main()
