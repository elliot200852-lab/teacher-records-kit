#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_sync_format.py — observations.md 區塊格式與紀錄 id 的迴歸測試。
零相依、不碰網路、不碰 Firestore。改 lib.DATE_RE / rid_for / sync.render 前後都跑一次：

    python3 scripts/test_sync_format.py

守的是什麼：紀錄 id 由「日期＋建立時間」決定，不由它在檔案裡的出現順序決定。
用出現順序編號（-2、-3）的話，在檔案中間插入一則同日紀錄會讓後面每一則都改名，
下一次 sync 就會把舊副本當成新紀錄再建一次——而規則不准刪，重複永久留著。
"""
import os, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib, sync

FAILED = []
def check(name, cond, detail=""):
    print(("✓ " if cond else "✗ ") + name + (("　" + str(detail)) if not cond else ""))
    if not cond: FAILED.append(name)

def write(p, text):
    open(p, "w", encoding="utf-8").write(text)
    return p

def main():
    tmp = tempfile.mkdtemp()
    p = os.path.join(tmp, "observations.md")

    check("rid：當天第一則＝純日期", lib.rid_for("2026-09-10", None) == "2026-09-10")
    check("rid：帶分鐘", lib.rid_for("2026-09-10", "14:35") == "2026-09-10-1435")
    check("rid：帶秒", lib.rid_for("2026-09-10", "14:35:12") == "2026-09-10-143512")
    check("反解：純日期→None", lib.time_from_rid("2026-09-10", "2026-09-10") is None)
    check("反解：分鐘", lib.time_from_rid("2026-09-10", "2026-09-10-1435") == "14:35")
    check("反解：秒", lib.time_from_rid("2026-09-10", "2026-09-10-143512") == "14:35:12")
    check("反解：舊流水號不被誤判成時間",
          lib.time_from_rid("2026-09-10", "2026-09-10-2") is None)

    doc = ("---\nid: S-01\n---\n\n# S-01 觀察\n\n"
           "## 2026-09-10 #數學\nA 的內容\n\n"
           "## 2026-09-10 14:35 #人際\nB 的內容\n\n"
           "## 2026-09-11 #語文\nC 的內容\n")
    _, blocks = sync.parse_file(write(p, doc))
    got = [(b["rid"], b["date"], b["time"], b["tags"], b["body"]) for b in blocks]
    check("解析：同一天兩則各自有 id", got == [
        ("2026-09-10", "2026-09-10", None, ["#數學"], "A 的內容"),
        ("2026-09-10-1435", "2026-09-10", "14:35", ["#人際"], "B 的內容"),
        ("2026-09-11", "2026-09-11", None, ["#語文"], "C 的內容")], got)

    # 在既有兩則之間插入同日新區塊——其他則的 id 一個都不准變
    before = {b["rid"]: b["body"] for b in blocks}
    doc2 = doc.replace("## 2026-09-10 14:35 #人際",
                       "## 2026-09-10 09:00 #情緒\n插進來的內容\n\n## 2026-09-10 14:35 #人際")
    _, blocks2 = sync.parse_file(write(p, doc2))
    after = {b["rid"]: b["body"] for b in blocks2}
    drift = [rid for rid, body in before.items() if after.get(rid) != body]
    check("中間插入：既有紀錄不改名、內容不漂移", not drift, drift)
    check("中間插入：新的那則拿到自己的 id",
          after.get("2026-09-10-0900") == "插進來的內容")

    for date, tm, tags, body in [("2026-09-10", None, ["#數學"], "只有一行"),
                                 ("2026-09-10", "14:35", [], "多行\n第二行"),
                                 ("2026-09-10", "14:35:12", ["#a", "#b"], "秒級")]:
        _, bs = sync.parse_file(write(p, "\n".join(sync.render(date, tm, tags, body))))
        ok = len(bs) == 1 and (bs[0]["date"], bs[0]["time"], bs[0]["tags"], bs[0]["body"]) \
            == (date, tm, tags, body)
        check(f"往返一致：{date} {tm or '(無時間)'}", ok, bs)

    print()
    if FAILED:
        print(f"✗ {len(FAILED)} 項失敗：" + "、".join(FAILED)); sys.exit(1)
    print("全部通過。")

if __name__ == "__main__":
    main()
