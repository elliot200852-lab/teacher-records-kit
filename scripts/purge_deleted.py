#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""purge_deleted.py — 把「網頁上已經刪掉、雲端還留著原文」的紀錄真的刪掉（兩段式刪除的第二段）。

兩段式刪除是這樣：
  第一段（網頁）：你在網頁上按刪除 → 那則文件被標成 `deleted: true`，**原文留在 Firestore**。
                  網頁看不到它、`sync.py` 會把本機 md 的那個區塊刪掉、匯出與台帳也都當它不存在，
                  只有 `backup.py` 的雲端快照（export.json）還留著它。
  第二段（這一支）：**只有老師本人在自己的終端機跑**，雲端那份原文才真的消失。

> **不可逆。** 刪掉的文件 Firestore 不會有回收桶，救回來的唯一路是先前的備份 zip。
> **安全規則擋不到這一支。** 規則管的是前端 SDK；這一支走 `gcloud auth print-access-token`
> 拿到的**你自己的**使用者權杖，在 IAM 層，規則裡把 `delete` 寫成一律拒也擋不住它。
> 所以它才只給人手動跑——AI 代理、無頭交辦、排程一律不准碰（見 AGENTS-HEADLESS.md 第 5 條）。

個資法的刪除請求要「完成」，最後一步就是跑這一支（先跑一次備份再刪）。

用法：
  python3 scripts/purge_deleted.py                        列出所有已刪、還留著的（不印正文）
  python3 scripts/purge_deleted.py --list                  同上
  python3 scripts/purge_deleted.py --rid 2026-09-10 --target students/S-03 --confirm
                                                           刪一則
  python3 scripts/purge_deleted.py --all --confirm         全部刪掉
  python3 scripts/purge_deleted.py --root DIR

**沒有 `--confirm` 一定不會刪任何東西**，只會把清單印出來。每刪一則寫一行
`{"op": "purge", ...}` 進 `data/audit.jsonl`（只留 rid 與內容指紋，不留正文）。
需求：gcloud 以專案擁有者登入（`gcloud auth login`）。
"""
import os
import sys
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib


def collect_deleted(kit, tabs, base, tok, only_target=""):
    """雲端所有被軟刪（`deleted: true`）的紀錄 → [{目標欄位, rid, deletedAt, chars, hash}]。

    同一位學生的各種記錄類型共用一個集合，抓一次就好，再依 stream 分流（跟 sync 同一套）。
    """
    out, cache = [], {}
    for t in lib.targets(kit, tabs):
        if only_target and only_target not in (t["key"], "%s/%s" % (t["kind"], t["id"])):
            continue
        if t["records"] not in cache:
            cache[t["records"]] = lib.list_docs(base, t["records"], tok)
        for rid, fs, _ut in cache[t["records"]]:
            if not lib.is_deleted(fs):
                continue
            if t["stream"] and (fs.get("stream") or "homeroom") != t["stream"]:
                continue
            out.append({"key": t["key"], "kind": t["kind"], "target": t["id"],
                        "stream": t["stream"] or "", "label": t["label"],
                        "path": "%s/%s" % (t["records"], rid), "rid": rid,
                        "date": fs.get("date", "") or rid[:10],
                        "deletedAt": str(fs.get("deletedAt") or ""),
                        "deletedBy": str(fs.get("deletedBy") or ""),
                        "chars": len(str(fs.get("body") or "")),
                        "hash": str(fs.get("contentHash") or "")})
    out.sort(key=lambda r: (r["key"], r["rid"]))
    return out


def print_rows(rows):
    """清單。**不印正文**——這支腳本的工作是刪，不是把刪掉的東西再攤一次。"""
    print("網頁上已刪、雲端還留著原文的紀錄：%d 則" % len(rows))
    for r in rows:
        print("  · %-28s %s　刪於 %s　正文 %d 字"
              % (r["key"], r["rid"], r["deletedAt"] or "（沒記時間）", r["chars"]))


def main():
    ap = argparse.ArgumentParser(
        description="真刪那些網頁上已刪、雲端還留著的紀錄（不可逆；沒有 --confirm 就只列出來）")
    ap.add_argument("--list", action="store_true", help="列出來（預設行為）")
    ap.add_argument("--rid", metavar="紀錄id", help="只刪這一則（要一起給 --target）")
    ap.add_argument("--target", metavar="種類/代號", help="限定一個對象，例如 students/S-03")
    ap.add_argument("--all", dest="do_all", action="store_true", help="全部刪掉")
    ap.add_argument("--confirm", action="store_true",
                    help="真的刪（不給就只列出來，一則都不刪）")
    lib.add_root_arg(ap)
    a = ap.parse_args()
    lib.apply_root(a)

    kit = lib.load_kit()
    tabs = lib.load_tabs()
    if lib.is_local(kit):
        print("本機模式沒有雲端，沒有東西要清。紀錄就在 %s 底下。"
              % os.path.relpath(lib.data_dir(), lib.root()))
        return
    if a.rid and not a.target:
        lib.die("--rid 要跟 --target 一起給。",
                "例如 `--rid 2026-09-10 --target students/S-03`；先跑一次不帶參數的"
                " `python3 scripts/purge_deleted.py` 看清單上那一則掛在誰底下。")

    base = lib.fb_base(kit)
    tok = lib.token()
    rows = collect_deleted(kit, tabs, base, tok, a.target or "")
    if a.rid:
        rows = [r for r in rows if r["rid"] == a.rid]
        if not rows:
            lib.die("在 %s 底下找不到已刪的 %s。" % (a.target, a.rid),
                    "清單上沒有就是它已經被清掉了，或它在網頁上還沒刪。"
                    "跑 `python3 scripts/purge_deleted.py` 看現在還有哪些。")

    print_rows(rows)
    if not rows:
        return
    if not (a.rid or a.do_all):
        # `--list`（預設）與只給 `--target` 的情況：只看，不刪。
        print("\n要刪的話：`--rid <紀錄id> --target <種類/代號> --confirm` 刪一則，"
              "或 `--all --confirm` 全刪。")
        print("刪掉就回不來了（Firestore 沒有回收桶）——先跑一次 "
              "`python3 scripts/backup.py` 比較安心。")
        return
    if not a.confirm:
        print("\n%s沒有 --confirm，一則都沒刪。%s" % (lib.YELLOW, lib.RESET))
        return

    done, failed = 0, []
    for r in rows:
        try:
            lib.delete_doc(base, r["path"], tok, raise_errors=True)
        except Exception as e:
            failed.append("%s %s：%s" % (r["key"], r["rid"], e))
            continue
        lib.audit({"op": "purge", "kind": r["kind"], "target": r["target"],
                   "stream": r["stream"], "rid": r["rid"], "hash": r["hash"],
                   "reason": "老師手動清除雲端原文（兩段式刪除第二段）"})
        done += 1
    lib.ok("已從雲端真的刪掉 %d 則（每一則都寫進 data/audit.jsonl）" % done)
    for f in failed:
        lib.warn("刪不掉：%s" % f)
    if failed:
        sys.exit(1)


if __name__ == "__main__":
    main()
