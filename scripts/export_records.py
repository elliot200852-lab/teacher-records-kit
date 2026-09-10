#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""export_records.py — 把記錄整包匯出：期末取材、換系統、或只是想留一份看得懂的檔案。

四種記錄都吃（學生／班級整體／課程／業務）。預設從你的 Firestore 抓（網頁上打的字也會一起
帶出來）；加 --local 就只讀本機 markdown，不連網。

這支的存在本身是一種保證：你的資料隨時可以整包帶走，不會被鎖在這個 kit 裡。

用法：
  python3 scripts/export_records.py                          Markdown 印到畫面
  python3 scripts/export_records.py --out ~/記錄.md          寫成一個 Markdown 檔
  python3 scripts/export_records.py --kind students          只匯出學生記錄
  python3 scripts/export_records.py --stream case            只匯出某一種學生記錄類型
  python3 scripts/export_records.py --target S-03            只匯出某一個對象（所有類型）
  python3 scripts/export_records.py --by-tag                 依標籤分組（逐題材寫評量用）
  python3 scripts/export_records.py --related                每一則後面附上它關聯到的記錄
  python3 scripts/export_records.py --json                   結構化 JSON
  python3 scripts/export_records.py --split ~/備份           每個對象一個資料夾
  python3 scripts/export_records.py --local                  不連網，只讀本機檔
"""
import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

KIND_LABEL = {"students": "學生記錄", "class": "班級整體觀察",
              "courses": "課程記錄", "business": "業務記錄"}


def rec_from_cloud(rid, fs):
    return {"rid": rid, "date": fs.get("date", "") or rid[:10],
            "tags": lib.norm_tags(fs.get("tags") or []),
            "fields": {k: str(v) for k, v in (fs.get("fields") or {}).items()},
            "related": lib.parse_related(fs.get("related") or []),
            "body": fs.get("body", "")}


def collect(kit, tabs, local_only):
    roster = lib.load_roster(kit)
    tok = None if local_only else lib.token()
    base = None if local_only else lib.fb_base(kit)
    cache = {}
    out = []
    for t in lib.targets(kit, tabs):
        if local_only:
            _, blocks = lib.parse_file(t["path"])
            recs = [{"rid": b["rid"], "date": b["date"], "tags": b["tags"],
                     "fields": b["fields"], "related": b["related"], "body": b["body"]}
                    for b in blocks]
        else:
            # 同一位學生的各種記錄類型共用一個雲端集合，抓一次就好，再依 stream 分流。
            if t["records"] not in cache:
                cache[t["records"]] = lib.list_docs(base, t["records"], tok)
            recs = [rec_from_cloud(rid, fs) for rid, fs, _ in cache[t["records"]]
                    if not t["stream"] or (fs.get("stream") or "homeroom") == t["stream"]]
        recs.sort(key=lambda r: (r.get("date") or "", r["rid"]))
        label = t["label"]
        if t["kind"] == "students" and roster.get(t["id"]):
            label = "%s　%s%s" % (t["id"], roster[t["id"]],
                                  ("（%s）" % t["streamLabel"]) if t.get("streamLabel") else "")
        out.append({"kind": t["kind"], "id": t["id"], "stream": t["stream"],
                    "streamLabel": t.get("streamLabel") or "", "label": label,
                    "records": recs})
    return {"exportedAt": lib.now_iso(), "roster": roster, "targets": out}


def index_records(data):
    """`<kind>/<target>/<rid>` → (目標, 記錄)，給 --related 用。

    關聯語法不帶記錄類型（一位學生的紀錄 id 在各類型之間本來就不會撞），
    所以同一個 key 先到先得；學生的各種類型都收得到。"""
    idx = {}
    for t in data["targets"]:
        for r in t["records"]:
            idx.setdefault("%s/%s/%s" % (t["kind"], t["id"], r["rid"]), (t, r))
    return idx


def attach_related(data, idx):
    """--json ＋ --related：每一則多一個 relatedRecords，把關聯到的那幾則整個帶出來。"""
    for t in data["targets"]:
        for r in t["records"]:
            if not r.get("related"):
                continue
            out = []
            for ref in r["related"]:
                hit = idx.get(ref)
                if hit:
                    # 淺拷貝並拿掉 relatedRecords：避免 A↔B 互相關聯時 json.dumps 撞到循環參照。
                    rec = {k: v for k, v in hit[1].items() if k != "relatedRecords"}
                    out.append({"ref": ref, "kind": hit[0]["kind"], "target": hit[0]["id"],
                                "label": hit[0]["label"], "record": rec})
                else:
                    out.append({"ref": ref, "missing": True})
            r["relatedRecords"] = out


def fmt_record(r, indent=""):
    head = "%s- **%s**%s" % (indent, r.get("date", ""), (" " + " ".join(r["tags"])) if r["tags"] else "")
    lines = [head]
    for k, v in (r.get("fields") or {}).items():
        lines.append("%s  - %s：%s" % (indent, k, v))
    body = (r.get("body") or "").strip()
    if body:
        for bl in body.split("\n"):
            lines.append("%s  %s" % (indent, bl))
    return lines


def to_md(data, with_related=False, idx=None):
    idx = (idx if idx is not None else index_records(data)) if with_related else {}
    total = sum(len(t["records"]) for t in data["targets"])
    L = ["# 記錄匯出（%s）" % data["exportedAt"],
         "> %d 個對象、%d 則記錄。學生一律以代號呈現；名冊對照在最後。" % (len(data["targets"]), total), ""]
    for kind in ("students", "class", "courses", "business"):
        ts = [t for t in data["targets"] if t["kind"] == kind]
        if not ts:
            continue
        L.append("## %s" % KIND_LABEL[kind])
        for t in ts:
            L.append("\n### %s" % t["label"])
            if not t["records"]:
                L.append("_（還沒有記錄）_")
                continue
            for r in t["records"]:
                L += fmt_record(r)
                if with_related and r.get("related"):
                    for ref in r["related"]:
                        hit = idx.get(ref)
                        if hit:
                            L.append("    ↳ 關聯 %s（%s）" % (ref, hit[0]["label"]))
                            L += fmt_record(hit[1], "    ")
                        else:
                            L.append("    ↳ 關聯 %s（找不到這一則）" % ref)
        L.append("")
    if data["roster"]:
        L += ["## 名冊對照（含真名，別把這一段貼到任何公開的地方）", ""]
        L += ["- %s　%s" % (i, n) for i, n in sorted(data["roster"].items())]
    return "\n".join(L) + "\n"


def to_md_by_tag(data):
    L = ["# 依標籤分類的記錄（%s）" % data["exportedAt"],
         "> 每個對象底下按標籤歸類；一則有多個標籤就會出現在各標籤下；沒標籤的歸「（未分類）」。", ""]
    for t in data["targets"]:
        L.append("### %s　%s" % (KIND_LABEL[t["kind"]], t["label"]))
        if not t["records"]:
            L.append("_（還沒有記錄）_\n")
            continue
        buckets = {}
        for r in t["records"]:
            for tag in (r["tags"] or ["（未分類）"]):
                buckets.setdefault(tag, []).append(r)
        for tag in sorted(buckets, key=lambda x: (x == "（未分類）", x)):
            L.append("- **%s**（%d 則）" % (tag, len(buckets[tag])))
            for r in buckets[tag]:
                L.append("    - %s：%s" % (r["date"], (r["body"] or "").strip().replace("\n", " ")))
        L.append("")
    return "\n".join(L) + "\n"


def write_split(data, base_dir):
    os.makedirs(base_dir, exist_ok=True)
    nf = nr = 0
    for t in data["targets"]:
        d = os.path.join(base_dir, t["kind"], t["id"])
        os.makedirs(d, exist_ok=True)
        fname = ("%s.md" % t["stream"]) if t.get("stream") else "records.md"
        L = ["# %s：%s" % (KIND_LABEL[t["kind"]], t["label"]), ""]
        for r in t["records"]:
            L += lib.render_block(r["date"], lib.time_from_rid(r["date"], r["rid"]),
                                  r["tags"], r["fields"], r["related"], r["body"])
            nr += 1
        with open(os.path.join(d, fname), "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(L) + "\n")
        nf += 1
    if data["roster"]:
        with open(os.path.join(base_dir, "roster.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write("# 代號↔姓名（含真名，別放進任何共享的地方）\n\n")
            for i, n in sorted(data["roster"].items()):
                f.write("- %s　%s\n" % (i, n))
    return nf, nr


def main():
    ap = argparse.ArgumentParser(description="把記錄整包匯出（四種記錄通用）")
    ap.add_argument("--kind", choices=list(lib.KINDS), help="只匯出某一種記錄")
    ap.add_argument("--target", help="只匯出某一個對象（代號或組 id）")
    ap.add_argument("--stream", help="只匯出某一種學生記錄類型（homeroom、case、iep…）")
    ap.add_argument("--id", dest="target2", help="--target 的別名（舊版習慣）")
    ap.add_argument("--by-tag", action="store_true", help="依標籤分組")
    ap.add_argument("--related", action="store_true", help="每一則後面附上它關聯到的記錄")
    ap.add_argument("--json", action="store_true", dest="as_json", help="輸出 JSON")
    ap.add_argument("--split", metavar="目錄", help="每個對象一個資料夾寫出去")
    ap.add_argument("--out", metavar="檔案", help="寫成檔案而不是印到畫面")
    ap.add_argument("--local", action="store_true", help="不連網，只讀本機 markdown")
    lib.add_root_arg(ap)
    a = ap.parse_args()
    lib.apply_root(a)

    kit = lib.load_kit()
    tabs = lib.load_tabs()
    data = collect(kit, tabs, a.local)
    # --related 要能跨對象查（篩過之後索引就查不到別的對象了），先用未篩選的全集建索引。
    rel_idx = index_records(data) if a.related else {}
    want = a.target or a.target2
    if a.kind:
        data["targets"] = [t for t in data["targets"] if t["kind"] == a.kind]
    if a.stream:
        data["targets"] = [t for t in data["targets"] if t.get("stream") == a.stream]
        if not data["targets"]:
            avail = sorted({s["id"] for s in lib.student_streams(tabs)})
            lib.die("找不到記錄類型 %s" % a.stream,
                    "可用的類型：%s（看 config/tabs.json 的 students.streams）。"
                    % ("、".join(avail) if avail else "（一種都沒有）"))
    if want:
        data["targets"] = [t for t in data["targets"] if t["id"] == want]
        if not data["targets"]:
            lib.die("找不到對象 %s" % want, "代號要跟 data/roster.csv 或設定裡的 id 一樣（例如 S-03）。")

    if a.split:
        nf, nr = write_split(data, os.path.expanduser(a.split))
        lib.ok("匯出完成 → %s（%d 個對象、%d 則記錄）" % (a.split, nf, nr))
        return
    if a.as_json:
        if a.related:
            attach_related(data, rel_idx)
        text = json.dumps(data, ensure_ascii=False, indent=2)
    elif a.by_tag:
        text = to_md_by_tag(data)
    else:
        text = to_md(data, a.related, rel_idx)
    if a.out:
        out = os.path.expanduser(a.out)
        with open(out, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        lib.ok("已寫出 %s（%d 字）" % (out, len(text)))
    else:
        print(text)


if __name__ == "__main__":
    main()
