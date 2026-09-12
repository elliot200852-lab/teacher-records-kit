#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
parent_email.py — 把一則（已由 AI 改寫成家長語氣的）訊息寄給某生家長
  · 以代號在 data/contacts.csv 找家長 email（家長1/家長2）；兩位都有→兩位、只一位→一位
  · 寄送：SMTP（通用，需環境變數 KIT_SMTP_APP_PASSWORD）或 gws（進階）
  · 內容由呼叫端提供，且務必「先給老師看稿、確認才寄」
  · --draft 一定不寄：gws 存進 Gmail 草稿匣，其他寄法（smtp）落地成 exports/ 的草稿檔
  · stdout 一律遮罩 email；不把 email/真名寫進任何會 commit 的檔
用法：python3 scripts/parent_email.py --id S-01 --date 2026-09-15 --subject "主旨" --body-file msg.txt [--dry-run|--draft]
"""
import os, re, csv, sys, argparse
from datetime import datetime
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib
import hostos

HANDLED = lib.rpath(".parent-emails-handled.tsv")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def seat_no(cfg, value):
    """代號或座號 → 純座號數字。

    不能用「只留數字」：前綴本身含數字時（id_prefix = 6B，代號 6B-01）
    那個作法會算出 601，通訊錄怎麼比都比不到。先把設定裡的前綴切掉再取數字。
    """
    s = str(value or "").strip()
    prefix = lib.id_prefix(cfg)
    if s.upper().startswith(prefix.upper() + "-"):
        s = s[len(prefix) + 1:]
    return re.sub(r"\D", "", s)


def draft_path(sid):
    """--draft 但寄信方式做不出草稿時，把信落地在這裡（exports/ 已被 .gitignore 擋住）。"""
    return lib.rpath("exports", "家長信草稿-%s-%s.txt"
                     % (sid, datetime.now().strftime("%Y%m%d-%H%M%S")))


def find_emails(cfg, sid):
    p = cfg.get("parents") or {}
    path = lib.rpath(p.get("contacts_csv", "data/contacts.csv").lstrip("./"))
    ci = int(p.get("col_id", 1)) - 1
    c1, c2 = int(p.get("col_parent1_email", 2)) - 1, int(p.get("col_parent2_email", 3)) - 1
    if not os.path.exists(path):
        lib.die("找不到家長通訊錄：%s" % path,
                "照 templates/contacts.example.csv 的格式建一份放到 data/contacts.csv（那個檔不會進 git）。")
    want = seat_no(cfg, sid)
    with open(path, encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.reader(fh))
    for row in rows:
        if len(row) <= max(ci, c1, c2):
            continue
        cell = seat_no(cfg, row[ci])
        if cell and cell.lstrip("0") == want.lstrip("0"):
            return [row[c].strip() for c in (c1, c2) if EMAIL_RE.match((row[c] or "").strip())]
    lib.die("通訊錄裡找不到代號 %s" % sid, "確認 data/contacts.csv 第一欄的編號跟名冊對得上。")


def main():
    ap = argparse.ArgumentParser(description="把一則已經改寫成家長語氣的訊息寄給某位學生的家長（先看稿再寄）")
    ap.add_argument("--id", required=True); ap.add_argument("--date")
    ap.add_argument("--subject", required=True); ap.add_argument("--body-file", required=True)
    ap.add_argument("--dry-run", action="store_true"); ap.add_argument("--draft", action="store_true")
    a = ap.parse_args()
    cfg = lib.load_kit()
    if not os.path.exists(a.body_file):
        lib.die("找不到 body 檔：%s" % a.body_file, "先把要寄的內容存成一個純文字檔。")
    with open(a.body_file, encoding="utf-8") as f:
        body = f.read().strip()
    if not body: lib.die("信的內容是空的，拒絕寄出。", "確認 --body-file 指到的檔案有內容。")
    emails = find_emails(cfg, a.id)
    if not emails: lib.die("代號 %s 在通訊錄裡沒有可用的家長信箱" % a.id, "檢查 data/contacts.csv 那一列的信箱欄。")

    print("代號 %s ｜ %d 位家長：%s" % (a.id, len(emails), ", ".join(lib.mask_email(e) for e in emails)))
    print("主旨：%s" % a.subject)
    if a.dry_run:
        print("（DRY-RUN，未寄。body %d 字。）" % len(body)); return

    if a.draft:
        if (cfg.get("email") or {}).get("method") == "gws":
            rc, out = hostos.run(["gws", "gmail", "+send", "--to", ",".join(emails), "--subject", a.subject,
                                  "--body", body, "--draft"], timeout=120)
            if rc != 0:
                lib.die("gws 建草稿失敗（回傳 %s）：%s" % (rc, out.strip()[-200:]),
                        "126＝內容含 Windows 命令列特殊字元，請改 email.method=smtp；127＝沒裝 gws。")
            print("\033[32m✓ 已存草稿（gws）\033[0m"); return
        # SMTP 沒有「草稿」這種東西。以前這裡會掉下去真的把信寄出去——
        # 老師以為只是出稿，信已經到家長信箱了。改成落地成檔案＋印出來，絕不寄。
        out_path = draft_path(a.id)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        with open(out_path, "w", encoding="utf-8", newline="\n") as f:
            f.write("收件者：%s\n主旨：%s\n\n%s\n"
                    % (", ".join(lib.mask_email(e) for e in emails), a.subject, body))
        print("\n" + body + "\n")
        print("\033[32m✓ 已出草稿（沒有寄出）：%s\033[0m" % os.path.relpath(out_path, lib.root()))
        print("  email.method 是 %s，這種寄法沒有「存草稿」；要真的寄請拿掉 --draft。"
              % ((cfg.get("email") or {}).get("method") or "smtp"))
        return

    lib.send_email(cfg, emails, a.subject, body)
    if a.date:
        with open(HANDLED, "a", encoding="utf-8", newline="\n") as f:
            f.write("%s\t%s\tsent\t%s\n" % (a.id, a.date, datetime.now().isoformat(timespec="seconds")))
    print("\033[32m✓ 已寄給 %d 位家長（代號 %s）\033[0m" % (len(emails), a.id))


if __name__ == "__main__":
    main()
