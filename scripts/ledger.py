#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""ledger.py — 台帳：讓「本機檔案／網站資料庫／Drive 備份」三處對得起來。

每一則記錄在 data/ledger.jsonl 佔一行，記它在三處各自的狀態。
資料多了以後，你要能一眼看出「有沒有東西掉了」——這支就是為了回答那個問題。

用法：
  python3 scripts/ledger.py --rebuild            重建台帳（掃本機檔＋最近一次備份）
  python3 scripts/ledger.py --check              三處對帳（要連網讀你的 Firestore）
  python3 scripts/ledger.py --check --offline    只比本機與備份，不連網
  python3 scripts/ledger.py --check --json       輸出 JSON（給 AI 代理讀）

退出碼：0＝三處對得上｜1＝有不一致（清單會印出來）
"""
import os
import sys
import json
import zipfile
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib


def latest_backup():
    """最近一次備份的紀錄（data/backups.jsonl 最後一行）。"""
    p = os.path.join(lib.data_dir(), "backups.jsonl")
    if not os.path.exists(p):
        return None
    last = None
    with open(p, encoding="utf-8") as fh:
        lines = fh.readlines()
    for line in lines:
        line = line.strip()
        if line:
            try:
                last = json.loads(line)
            except json.JSONDecodeError:
                continue
    return last


def rids_in_backup(entry):
    """打開最近一次備份的 zip，看裡面實際有哪些紀錄（不是猜的）。"""
    if not entry:
        return None, "還沒有備份過"
    zp = entry.get("zip") or ""
    path = zp if os.path.isabs(zp) else lib.rpath(zp)
    if not os.path.exists(path):
        return None, "最近一次備份的 zip 不在本機了：%s（Drive 上那份可能還在）" % zp
    found = {}
    try:
        with zipfile.ZipFile(path) as z:
            for name in z.namelist():
                if not name.endswith(".md") or not name.startswith("data/"):
                    continue
                parts = name.split("/")
                if len(parts) < 3:
                    continue
                kind = parts[1]
                ident = parts[2] if len(parts) > 3 else "main"
                if kind == "class":
                    ident = "main"
                text = z.read(name).decode("utf-8", "replace")
                key = "%s/%s" % (kind, ident)
                bucket = found.setdefault(key, set())
                for line in text.split("\n"):
                    m = lib.DATE_RE.match(line)
                    if m:
                        bucket.add(lib.rid_for(m.group(1), m.group(2)))
    except zipfile.BadZipFile:
        return None, "備份 zip 讀不開（可能沒寫完）：%s" % zp
    return found, ""


def scan_local(kit, tabs):
    """本機四種檔 → {kind/target: {rid: block}}。"""
    out = {}
    for t in lib.targets(kit, tabs):
        _, blocks = lib.parse_file(t["path"])
        out["%s/%s" % (t["kind"], t["id"])] = {b["rid"]: b for b in blocks}
    return out


def rebuild(kit, tabs, quiet=False):
    local = scan_local(kit, tabs)
    bk = latest_backup()
    in_backup, why = rids_in_backup(bk)
    rows = []
    for key, blocks in local.items():
        kind, target = key.split("/", 1)
        for rid, b in sorted(blocks.items()):
            backup = None
            if in_backup is not None and rid in (in_backup.get(key) or set()):
                backup = {"zip": bk.get("zip"), "md5": bk.get("md5"),
                          "driveFileId": ((bk.get("drive") or {}).get("fileId")
                                          or (bk.get("drive") or {}).get("path"))}
            rows.append({"kind": kind, "target": target, "rid": rid, "date": b["date"],
                         "tags": b["tags"], "hash": b["hash"],
                         "source": "file", "related": b["related"],
                         "local": True, "cloud": None, "backup": backup})
    path = os.path.join(lib.data_dir(), "ledger.jsonl")
    os.makedirs(lib.data_dir(), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    if not quiet:
        lib.ok("台帳重建完成：%d 則（%s）" % (len(rows), os.path.relpath(path, lib.root())))
        if in_backup is None and why:
            lib.warn(why)
        print("  （cloud 欄位留白是正常的——跑 `python3 scripts/ledger.py --check` 才會去比對網站。）")
    return rows


def check(kit, tabs, offline, as_json):
    local = scan_local(kit, tabs)
    bk = latest_backup()
    in_backup, why = rids_in_backup(bk)
    cloud = {}
    cloud_err = ""
    if not offline:
        tok = lib.token(quiet=True)
        if not tok:
            cloud_err = "gcloud 沒登入，這次沒比對網站（跑 `gcloud auth login`，或加 --offline）"
        else:
            base = lib.fb_base(kit)
            for t in lib.targets(kit, tabs):
                key = "%s/%s" % (t["kind"], t["id"])
                try:
                    cloud[key] = {rid: fs for rid, fs, _ in
                                  lib.list_docs(base, t["records"], tok, raise_errors=True)}
                except Exception as e:
                    cloud_err = "讀 Firestore 失敗：%s" % e
                    cloud = {}
                    break

    rows, problems = [], []
    for key in sorted(set(local) | set(cloud)):
        lb = local.get(key, {})
        cb = cloud.get(key, {})
        bb = (in_backup or {}).get(key, set())
        only_local = sorted(set(lb) - set(cb))
        only_cloud = sorted(set(cb) - set(lb))
        diff = sorted(r for r in set(lb) & set(cb)
                      if cb[r].get("contentHash") and cb[r]["contentHash"] != lb[r]["hash"])
        miss_bk = sorted(set(lb) - bb) if in_backup is not None else []
        rows.append({"target": key, "local": len(lb),
                     "cloud": (len(cb) if (cloud or not offline) and not cloud_err else None),
                     "backup": (len(bb) if in_backup is not None else None),
                     "onlyLocal": only_local, "onlyCloud": only_cloud,
                     "hashDiff": diff, "missingFromBackup": miss_bk})
        if not cloud_err and not offline:
            for r in only_local:
                problems.append("本機有、網站沒有：%s %s（跑 `python3 scripts/sync.py` 推上去）" % (key, r))
            for r in only_cloud:
                problems.append("網站有、本機沒有：%s %s（跑 `python3 scripts/sync.py` 拉下來）" % (key, r))
            for r in diff:
                problems.append("兩邊內容不一樣：%s %s（sync 會告訴你是不是衝突）" % (key, r))
        if miss_bk:
            problems.append("最近一次備份裡沒有：%s 共 %d 則（跑 `python3 scripts/backup.py`）"
                            % (key, len(miss_bk)))

    if as_json:
        print(json.dumps({"ok": not problems, "offline": offline, "cloudError": cloud_err,
                          "backupNote": why, "rows": rows, "problems": problems},
                         ensure_ascii=False, indent=2))
        return 1 if problems else 0

    print("台帳對帳：%s\n" % lib.root())
    print("  %-28s %8s %8s %8s" % ("目標", "本機", "網站", "備份"))
    print("  " + "─" * 56)
    for r in rows:
        print("  %-28s %8s %8s %8s" % (
            r["target"], r["local"],
            "—" if r["cloud"] is None else r["cloud"],
            "—" if r["backup"] is None else r["backup"]))
    print()
    if cloud_err:
        lib.warn(cloud_err)
    if in_backup is None and why:
        lib.warn(why)
    if problems:
        print("%s不一致 %d 項：%s" % (lib.RED, len(problems), lib.RESET))
        for p in problems[:40]:
            print("  · " + p)
        if len(problems) > 40:
            print("  …還有 %d 項（用 --json 看完整清單）" % (len(problems) - 40))
        return 1
    lib.ok("三處對得上。")
    return 0


def main():
    ap = argparse.ArgumentParser(description="台帳：本機／網站／Drive 備份三處對帳")
    ap.add_argument("--rebuild", action="store_true", help="重建 data/ledger.jsonl")
    ap.add_argument("--check", action="store_true", help="三處對帳並印表")
    ap.add_argument("--offline", action="store_true", help="不連網，只比本機與備份")
    ap.add_argument("--json", action="store_true", dest="as_json", help="輸出 JSON")
    ap.add_argument("--quiet", action="store_true", help="安靜模式")
    lib.add_root_arg(ap)
    a = ap.parse_args()
    lib.apply_root(a)
    if not (a.rebuild or a.check):
        ap.print_help()
        sys.exit(2)

    kit = lib.load_kit()
    tabs = lib.load_tabs()
    rc = 0
    if a.rebuild:
        rebuild(kit, tabs, a.quiet)
    if a.check:
        rc = check(kit, tabs, a.offline, a.as_json)
    sys.exit(rc)


if __name__ == "__main__":
    main()
