#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sync.py — 本機 observations.md  <->  Firestore（雙向、衝突安全）
  正向：每位學生 <students_dir>/<id>/observations.md 的 ## YYYY-MM-DD 區塊 → Firestore
  回寫：網頁編輯/新增（doc 帶 editedOnWeb）→ 寫回對應檔案區塊（無檔則建檔）
  衝突：網頁與檔案同一則都改 → 不覆蓋、印出來
  代號制：內容禁含真名（名冊真名出現即攔下）；姓名只推 roster/main（擁有者可讀）
用法：sync.py [--dry-run]
需求：gcloud 以擁有者登入；config.yaml 填好 firebase.project_id 與 records.*
"""
import os, re, sys, hashlib, shutil
import lib

DRY = "--dry-run" in sys.argv
sha = lambda t: hashlib.sha256(t.encode()).hexdigest()[:16]


def parse_file(path):
    lines = open(path, encoding="utf-8").read().split("\n")
    starts = [i for i, l in enumerate(lines) if lib.DATE_RE.match(l)]
    blocks, seen = [], {}
    for k, si in enumerate(starts):
        ei = starts[k + 1] if k + 1 < len(starts) else len(lines)
        date = lib.DATE_RE.match(lines[si]).group(1)
        tags = re.findall(r"#\S+", lines[si])
        body = "\n".join(lines[si + 1:ei]).strip()
        seen[date] = seen.get(date, 0) + 1
        rid = date if seen[date] == 1 else "%s-%d" % (date, seen[date])
        blocks.append({"rid": rid, "date": date, "tags": tags, "body": body,
                       "hash": sha("|".join(tags) + "\n" + body), "start": si, "end": ei})
    return lines, blocks


def render(date, tags, body):
    return ["## " + date + ((" " + " ".join(tags)) if tags else ""), ""] + body.split("\n") + [""]


def get_records(base, sid, tok):
    d = lib.http("GET", base, "students/%s/records" % sid, tok)
    return {doc["name"].split("/")[-1]: {k: lib.py_value(v) for k, v in doc.get("fields", {}).items()}
            for doc in d.get("documents", [])}


def main():
    cfg = lib.load_config()
    base = lib.fb_base(cfg)
    roster = lib.load_roster(cfg)          # {id: name}
    names = [n for n in roster.values() if n]
    sdir = lib.students_dir(cfg)
    tok = lib.token()
    fwd = wb = created = conflicts = leaks = 0
    notes = []

    ids = sorted(set(list(roster.keys()) + (os.listdir(sdir) if os.path.isdir(sdir) else [])))
    for sid in ids:
        if not re.match(r".+-\d+$", sid):   # 只認 <prefix>-NN 形態的資料夾/代號
            continue
        sdir_i = os.path.join(sdir, sid)
        path = os.path.join(sdir_i, "observations.md")
        exists = os.path.exists(path)
        existing = get_records(base, sid, tok)
        lines, blocks = parse_file(path) if exists else (None, [])
        file_rids = {b["rid"] for b in blocks}
        pend_fwd, pend_wb, pend_new = [], [], []

        for b in blocks:
            if any(nm in (b["body"] + " " + " ".join(b["tags"])) for nm in names):
                leaks += 1; notes.append("PII %s %s（檔案含真名）" % (sid, b["rid"])); continue
            fs = existing.get(b["rid"])
            if fs is None:
                pend_fwd.append(b); fwd += 1
            elif fs.get("editedOnWeb"):
                if fs.get("contentHash") != b["hash"]:
                    conflicts += 1; notes.append("衝突 %s %s" % (sid, b["rid"])); continue
                wb_body, wb_tags = fs.get("body", ""), fs.get("tags", [])
                if any(nm in (wb_body + " " + " ".join(wb_tags)) for nm in names):
                    leaks += 1; notes.append("PII %s %s（網頁回寫含真名）" % (sid, b["rid"])); continue
                pend_wb.append((b, wb_body, wb_tags)); wb += 1
            elif fs.get("contentHash") != b["hash"]:
                pend_fwd.append(b); fwd += 1

        for rid, fs in existing.items():
            if rid in file_rids or not fs.get("editedOnWeb"):
                continue
            wb_body, wb_tags = fs.get("body", ""), fs.get("tags", [])
            if any(nm in (wb_body + " " + " ".join(wb_tags)) for nm in names):
                leaks += 1; notes.append("PII %s %s（網頁新增含真名）" % (sid, rid)); continue
            pend_new.append({"rid": rid, "date": fs.get("date", rid), "tags": wb_tags, "body": wb_body}); created += 1

        if DRY:
            continue

        if pend_wb or pend_new:
            if not exists:
                os.makedirs(sdir_i, exist_ok=True)
                lines = ["---", "id: %s" % sid, "note: 去識別化，禁寫姓名", "---", "", "# %s 觀察" % sid, "", "---", ""]
            else:
                shutil.copy2(path, os.path.join(sdir_i, ".observations.prev.md"))
            for b, body, tags in sorted(pend_wb, key=lambda x: -x[0]["start"]):
                lines[b["start"]:b["end"]] = render(b["date"], tags, body)
            for n in sorted(pend_new, key=lambda x: x["date"]):
                if lines and lines[-1].strip() != "": lines.append("")
                lines += render(n["date"], n["tags"], n["body"])
            open(path, "w", encoding="utf-8").write("\n".join(lines))
            _, nb = parse_file(path); byrid = {x["rid"]: x for x in nb}
            for rid in [b["rid"] for b, _, _ in pend_wb] + [n["rid"] for n in pend_new]:
                x = byrid.get(rid)
                if x:
                    lib.http("PATCH", base, "students/%s/records/%s" % (sid, rid), tok,
                             {"date": x["date"], "tags": x["tags"], "body": x["body"],
                              "contentHash": x["hash"], "editedOnWeb": False})

        for b in pend_fwd:
            lib.http("PATCH", base, "students/%s/records/%s" % (sid, b["rid"]), tok,
                     {"date": b["date"], "tags": b["tags"], "body": b["body"],
                      "contentHash": b["hash"], "editedOnWeb": False})

        fb = parse_file(path)[1] if os.path.exists(path) else []
        lib.http("PATCH", base, "students/%s" % sid, tok,
                 {"id": sid, "recordCount": len(fb),
                  "lastRecordDate": max((x["date"] for x in fb), default=""),
                  "monthsRecorded": sorted({x["date"][:7] for x in fb})})

    if not DRY and roster:
        lib.http("PATCH", base, "roster/main", tok,
                 {"students": [{"id": i, "name": n} for i, n in sorted(roster.items())]})

    print("%s同步：forward %d、回寫 %d、新增 %d、衝突 %d、PII 攔截 %d" %
          ("（DRY-RUN）" if DRY else "", fwd, wb, created, conflicts, leaks))
    for n in notes:
        print("  · " + n)


if __name__ == "__main__":
    main()
