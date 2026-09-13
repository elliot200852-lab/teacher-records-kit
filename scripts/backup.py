#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""backup.py — 一週一次的備份：本機 zip ＋ 送上你自己的 Google 雲端硬碟。

zip 裡有兩樣東西：
  · data/ 全份（名冊、四種記錄的 markdown、台帳、稽核）
  · export.json（Firestore 全量快照——網頁上打的字也一起備走）

雲端兩種模式（config/kit.json 的 drive.mode）：
  · desktop（預設、零設定）：把 zip 複製進「Google 雲端硬碟」桌面程式的同步資料夾，
    剩下的交給那個程式自己上傳。不用 OAuth、Windows 也行。
  · gws（進階）：用 googleworkspace-cli 直接上傳到指定的 Drive 資料夾，上傳後比對 md5。
    找不到那個資料夾就停手——**絕不自己建一個新的**，那會讓備份靜靜地跑到別的地方去。

用法：
  python3 scripts/backup.py                 完整備份
  python3 scripts/backup.py --local-only    只做本機 zip，不碰雲端
  python3 scripts/backup.py --no-export     不抓 Firestore 快照（離線時）
  python3 scripts/backup.py --root DIR
"""
import os
import sys
import json
import time
import shutil
import hashlib
import zipfile
import argparse
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib
import hostos


def md5(path):
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def strip_keyring(txt):
    return "\n".join(l for l in (txt or "").splitlines() if not l.startswith("Using keyring"))


def gws_json(args, cwd=None, upload=None, body=None, params=None):
    cmd = ["gws", *args]
    if body is not None:
        cmd += ["--json", json.dumps(body, ensure_ascii=False)]
    if upload is not None:
        cmd += ["--upload", upload]          # 注意：--upload 的路徑要相對 cwd
    cmd += ["--format", "json"]
    if params:
        cmd += ["--params", json.dumps(params, ensure_ascii=False)]
    rc, out, err = hostos.run(cmd, cwd=cwd, timeout=600, split=True)
    if rc == 127:
        return None, "找不到 gws 指令"
    if rc != 0:
        return None, strip_keyring(err) + strip_keyring(out)
    txt = strip_keyring(out).strip()
    try:
        return (json.loads(txt) if txt else {}), ""
    except json.JSONDecodeError:
        return None, txt[:300]


def collect_export(kit, tabs):
    """Firestore 全量快照。抓不到就回 (None, 原因)——備份照做，只是少了雲端那一份。"""
    pid = (kit.get("firebase") or {}).get("project_id", "")
    if not pid or pid.startswith("your-"):
        # 還沒接 Firebase（或還在填範例值）也要能備份本機那一份，不能整支停掉。
        return None, "config/kit.json 的 firebase.project_id 還沒填（跑 `python3 scripts/setup.py` 接上之後就會連網站那份一起備）"
    tok = lib.token(quiet=True)
    if not tok:
        return None, "gcloud 沒登入（跑 `gcloud auth login` 之後就會連雲端那份一起備）"
    base = lib.fb_base(kit)
    out = {"exportedAt": lib.now_iso(), "projectId": lib.project_id(kit), "targets": {}}
    try:
        roster, _ = lib.get_doc(base, "roster/main", tok, raise_errors=True)
        out["roster"] = roster or {}
        cache, cards = {}, {}
        for t in lib.targets(kit, tabs):
            # 一位學生的各種記錄類型共用一個集合與一張卡，抓一次就好，再依 stream 分流。
            if t["records"] not in cache:
                cache[t["records"]] = lib.list_docs(base, t["records"], tok, raise_errors=True)
            if t["card"] and t["card"] not in cards:
                cards[t["card"]], _ = lib.get_doc(base, t["card"], tok, raise_errors=True)
            # 這裡**故意**不排除軟刪（deleted: true）的那些：備份就是雲端的全量快照，
            # 網頁上刪掉、還沒跑 purge_deleted.py 的那些原文要留在 export.json 裡
            # （zip 裡的本機 md 自然沒有它們——sync 已經把區塊刪掉了）。
            out["targets"][t["key"]] = {
                "card": cards.get(t["card"]), "stream": t["stream"],
                "sourceFile": t["sourceFile"],
                "records": {rid: fs for rid, fs, _ in cache[t["records"]]
                            if not t["stream"] or (fs.get("stream") or "homeroom") == t["stream"]}}
        for doc in ("meta/config", "meta/status"):
            fs, _ = lib.get_doc(base, doc, tok, raise_errors=True)
            out.setdefault("meta", {})[doc.split("/")[1]] = fs or {}
    except Exception as e:
        return None, "讀 Firestore 失敗：%s" % e
    return out, ""


def make_zip(zip_path, data_root, export):
    os.makedirs(os.path.dirname(zip_path), exist_ok=True)
    n = 0
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for root_, dirs, files in os.walk(data_root):
            dirs[:] = [d for d in dirs if d not in ("__pycache__",)]
            for f in files:
                p = os.path.join(root_, f)
                z.write(p, os.path.join("data", os.path.relpath(p, data_root)))
                n += 1
        if export is not None:
            z.writestr("export.json", json.dumps(export, ensure_ascii=False, indent=1))
            n += 1
    return n


def to_desktop(kit, zip_path):
    d = os.path.expanduser((kit.get("drive") or {}).get("desktop_dir") or "")
    if not d:
        return None, "config/kit.json 的 drive.desktop_dir 沒填"
    if not os.path.isdir(d):
        return None, ("找不到備份資料夾：%s（Google 雲端硬碟桌面程式沒開、沒登入，或路徑打錯）" % d)
    dest = os.path.join(d, os.path.basename(zip_path))
    shutil.copy2(zip_path, dest)
    if md5(dest) != md5(zip_path):
        os.remove(dest)
        return None, "複製過去之後 md5 對不起來（磁碟或同步夾有問題），已把那份刪掉"
    return {"path": dest}, ""


def to_gws(kit, zip_path):
    fid = ((kit.get("drive") or {}).get("backup_folder_id") or "").strip()
    if not fid:
        return None, "config/kit.json 的 drive.backup_folder_id 沒填"
    if not hostos.exe("gws"):
        return None, "找不到 gws 指令（%s）" % hostos.install_hint("gws")
    info, err = gws_json(["drive", "files", "get"],
                         params={"fileId": fid, "fields": "id,name,trashed"})
    if info is None or not info.get("id"):
        return None, "查不到 Drive 資料夾 %s：%s" % (fid, err or "沒有回傳 id")
    if info.get("trashed"):
        return None, "Drive 資料夾 %s 在垃圾桶裡" % fid
    cwd, name = os.path.dirname(zip_path), os.path.basename(zip_path)
    res, err = gws_json(["drive", "files", "create"], cwd=cwd, upload=name,
                        body={"name": name, "parents": [fid]},
                        params={"fields": "id,md5Checksum,name"})
    if res is None or not res.get("id"):
        return None, "上傳失敗：%s" % (err or "沒有回傳 file id")
    local = md5(zip_path)
    if res.get("md5Checksum") and res["md5Checksum"] != local:
        return None, "上傳完 md5 對不起來（本機 %s／雲端 %s）" % (local[:8], res["md5Checksum"][:8])
    return {"fileId": res["id"], "folder": info.get("name", ""), "md5": res.get("md5Checksum", "")}, ""


def prune(backup_dir, keep):
    zips = sorted(f for f in os.listdir(backup_dir)
                  if f.startswith("teacher-records-") and f.endswith(".zip"))
    removed = []
    for f in zips[:max(0, len(zips) - keep)]:
        os.remove(os.path.join(backup_dir, f))
        removed.append(f)
    return removed


def main():
    ap = argparse.ArgumentParser(description="備份：本機 zip ＋ 你自己的 Google 雲端硬碟")
    ap.add_argument("--local-only", action="store_true", help="只做本機 zip，不碰雲端")
    ap.add_argument("--no-export", action="store_true", help="不抓 Firestore 快照（離線時用）")
    ap.add_argument("--quiet", action="store_true", help="沒事就不出聲（排程用）")
    lib.add_root_arg(ap)
    a = ap.parse_args()
    lib.apply_root(a)

    kit = lib.load_kit()
    tabs = lib.load_tabs()
    data_root = lib.data_dir()
    if not os.path.isdir(data_root):
        lib.die("找不到 data/ 資料夾：%s" % data_root, "跑 `python3 scripts/setup.py` 建骨架。")

    export, why = (None, "--no-export")
    if not a.no_export:
        export, why = collect_export(kit, tabs)
    if export is None and not a.no_export:
        lib.warn("這次只備本機：%s" % why)

    stamp = time.strftime("%Y-%m-%d-%H%M%S")     # 帶秒：同一分鐘跑兩次不會蓋掉前一份
    zip_path = lib.rpath("backups", "teacher-records-%s.zip" % stamp)
    n = make_zip(zip_path, data_root, export)
    size = os.path.getsize(zip_path)
    digest = md5(zip_path)
    lib.ok("本機備份：%s（%d 個檔、%.1f MB）" % (os.path.relpath(zip_path, lib.root()), n, size / 1e6))

    entry = {"at": lib.now_iso(), "zip": os.path.relpath(zip_path, lib.root()),
             "md5": digest, "bytes": size, "files": n,
             "export": export is not None, "drive": None}
    mode = (kit.get("drive") or {}).get("mode", "desktop")
    last_error = ""
    if not a.local_only:
        info, err = (to_desktop if mode == "desktop" else to_gws)(kit, zip_path)
        if info is None:
            last_error = "雲端備份沒成功：%s" % err
            lib.err("雲端備份沒成功（本機那份是好的）：%s" % err,
                    "desktop 模式：確認「Google 雲端硬碟」桌面程式開著、登入了，"
                    "而且 drive.desktop_dir 指到同步夾裡真的存在的資料夾。"
                    "gws 模式：確認 backup_folder_id 沒貼錯、資料夾沒進垃圾桶。"
                    "跑 `python3 scripts/doctor.py` 會一次告訴你哪裡不對。")
        else:
            entry["drive"] = dict(info, mode=mode)
            if mode == "desktop":
                lib.ok("已複製到雲端硬碟同步夾：%s" % info["path"])
                print("  （檔案上傳完成與否由 Google 雲端硬碟桌面程式負責，可以在它的圖示上看進度）")
            else:
                lib.ok("已上傳到 Drive：file id %s（md5 對得上）" % info["fileId"])

    with open(os.path.join(data_root, "backups.jsonl"), "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    keep = int((kit.get("drive") or {}).get("keep_backups") or 12)
    removed = prune(lib.rpath("backups"), keep)
    if removed and not a.quiet:
        print("  本機只留最近 %d 份，刪掉 %d 份舊的（雲端那些不動）。" % (keep, len(removed)))

    if not a.local_only and export is not None:
        tok = lib.token(quiet=True)
        if tok:
            # lastError 一起寫：備份上不了雲端硬碟時，網頁狀態列要說得出原因，
            # 不能只更新「上次備份時間」讓它看起來一切正常（成功時寫空字串＝清掉上次的錯）。
            fields = {"lastBackupAt": lib.now_iso(), "lastError": last_error}
            try:
                lib.http("PATCH", lib.fb_base(kit), "meta/status", tok, fields,
                         mask=list(fields), raise_errors=True)
            except Exception:
                pass                     # 狀態列更新失敗不影響備份本身

    if not a.quiet:
        print("\n備份記錄寫進 data/backups.jsonl；要確認三處（本機／網站／Drive）對不對得上：")
        print("  python3 scripts/ledger.py --check")


if __name__ == "__main__":
    main()
