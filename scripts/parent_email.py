#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parent_email.py — 把一則（已由 AI 改寫成家長語氣的）訊息寄給某生家長
  · 以代號在 contacts.csv 找家長 email（家長1/家長2）；兩位都有→兩位、只一位→一位
  · 寄送：SMTP（通用，需環境變數 KIT_SMTP_APP_PASSWORD）或 gws（進階）
  · 內容由呼叫端提供，且務必「先給老師看稿、確認才寄」
  · stdout 一律遮罩 email；不把 email/真名寫進任何會 commit 的檔
用法：parent_email.py --id S-01 --date 2026-09-15 --subject "主旨" --body-file msg.txt [--dry-run|--draft]
"""
import os, re, csv, sys, argparse
from datetime import datetime
import lib

HANDLED = os.path.join(lib.ROOT, ".parent-emails-handled.tsv")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def find_emails(cfg, sid):
    p = cfg.get("parents") or {}
    path = os.path.join(lib.ROOT, p.get("contacts_csv", "./data/contacts.csv").lstrip("./"))
    ci = int(p.get("col_id", 1)) - 1
    c1, c2 = int(p.get("col_parent1_email", 2)) - 1, int(p.get("col_parent2_email", 3)) - 1
    if not os.path.exists(path):
        lib.die("找不到家長通訊錄：%s（參考 templates/contacts.example.csv）" % path)
    want = re.sub(r"\D", "", sid)
    for row in csv.reader(open(path, encoding="utf-8-sig")):
        if len(row) <= max(ci, c1, c2):
            continue
        cell = re.sub(r"\D", "", (row[ci] or ""))
        if cell and cell.lstrip("0") == want.lstrip("0"):
            return [row[c].strip() for c in (c1, c2) if EMAIL_RE.match((row[c] or "").strip())]
    lib.die("通訊錄找不到代號 %s" % sid)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True); ap.add_argument("--date")
    ap.add_argument("--subject", required=True); ap.add_argument("--body-file", required=True)
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--draft", action="store_true")
    a = ap.parse_args()
    cfg = lib.load_config()
    body = open(a.body_file, encoding="utf-8").read().strip() if os.path.exists(a.body_file) else lib.die("找不到 body 檔")
    if not body: lib.die("body 是空的，拒寄")
    emails = find_emails(cfg, a.id)
    if not emails: lib.die("代號 %s 沒有有效家長 email" % a.id)

    print("代號 %s ｜ %d 位家長：%s" % (a.id, len(emails), ", ".join(lib.mask(e) for e in emails)))
    print("主旨：%s" % a.subject)
    if a.dry_run:
        print("（DRY-RUN，未寄。body %d 字。）" % len(body)); return

    if a.draft and (cfg.get("email") or {}).get("method") == "gws":
        import subprocess
        subprocess.run(["gws", "gmail", "+send", "--to", ",".join(emails), "--subject", a.subject,
                        "--body", body, "--draft"], check=True, stdout=subprocess.DEVNULL)
        print("\033[32m✓ 已存草稿（gws）\033[0m"); return

    lib.send_email(cfg, emails, a.subject, body)
    if a.date:
        with open(HANDLED, "a", encoding="utf-8") as f:
            f.write("%s\t%s\tsent\t%s\n" % (a.id, a.date, datetime.now().isoformat(timespec="seconds")))
    print("\033[32m✓ 已寄給 %d 位家長（代號 %s）\033[0m" % (len(emails), a.id))


if __name__ == "__main__":
    main()
