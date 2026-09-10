#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""sync.py — 本機 markdown ⇄ Firestore 雙向同步（四種記錄共用一套邏輯）。

四種目標：學生記錄、班級整體觀察、課程記錄、業務記錄（由 lib.targets 產生）。
學生與班級記錄還多一層「記錄類型（stream）」：雲端同一個集合 `students/<代號>/records`
靠文件裡的 `stream` 欄位分流，本機則是一種類型一個檔（homeroom 沿用 observations.md）。
每一則推上去都會帶 `stream` 與 `sourceFile`，這樣網頁與 AI 都知道它是哪一種、來自哪個檔。

規則（每一條都是為了「不要弄丟老師的字」）：
  · 正向：檔案裡有、雲端沒有（而且以前沒同步過）→ 推上去。
  · 回寫：雲端那則被網頁改過（editedOnWeb）且本機那則自上次同步後沒動 → 寫回檔案。
  · 衝突：兩邊都改 → **不覆蓋**，印出來讓老師自己決定。
  · 前置條件：每個 PATCH 都帶 currentDocument.updateTime；雲端在我們讀完之後又被改過
    就回 412，當成衝突處理、不重試覆寫（紅隊 #9：沒有這條，老師在手機上打字會被靜默蓋掉）。
  · 刪除：雲端那則被刪掉（以前同步過、現在不見了）→ 從本機檔案也刪掉，並寫進 data/audit.jsonl。
    但**整個檔案不見或變成空的時候一律不刪任何東西**——那多半是檔案出事，不是老師要刪。
  · 回寫前先備份成 `.<檔名>.prev.md`。
  · 學生卡片上的兩塊底稿（IEP 的 goals、個案概念化）也雙向同步：只有一邊改就照那一邊，
    兩邊都改就印出來讓老師自己決定——跟記錄同一條規則。
  · 去識別化：正文出現名冊真名就攔下不同步（兩個方向都攔）。

用法：
  python3 scripts/sync.py                 同步
  python3 scripts/sync.py --dry-run       只看會發生什麼，不寫任何東西
  python3 scripts/sync.py --only students/S-03     只同步某一個目標
  python3 scripts/sync.py --root DIR
需求：gcloud 以專案擁有者登入（`gcloud auth login`）。
"""
import os
import sys
import json
import shutil
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

STATE_FILE = ".sync-state.json"


def load_state():
    p = os.path.join(lib.data_dir(), STATE_FILE)
    if os.path.exists(p):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_state(state):
    os.makedirs(lib.data_dir(), exist_ok=True)
    with open(os.path.join(lib.data_dir(), STATE_FILE), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1)


def leaks(names, *texts):
    hits = []
    for t in texts:
        hits += lib.find_names(t if isinstance(t, str) else " ".join(map(str, t or [])), names)
    return sorted(set(hits))


def cloud_record(fs):
    """雲端文件 → 跟本機同形狀的一則記錄。"""
    return {"date": fs.get("date", ""), "tags": lib.norm_tags(fs.get("tags") or []),
            "fields": {k: str(v) for k, v in (fs.get("fields") or {}).items()},
            "related": lib.parse_related(fs.get("related") or []),
            "body": fs.get("body", "")}


def doc_stream(fs):
    """雲端那則屬於哪一種記錄類型。v2 留下來的（沒有 stream 欄位）一律當導師班級紀錄，
    因為它們本來就寫在 observations.md 裡。"""
    return (fs.get("stream") or "").strip() or "homeroom"


def record_body(b, keep=None, t=None):
    """本機一則 → 要寫上雲的欄位（保留雲端原有的 source／taskId）。"""
    keep = keep or {}
    out = {"date": b["date"], "tags": b["tags"], "fields": b["fields"],
           "related": b["related"], "body": b["body"],
           "contentHash": b["hash"], "editedOnWeb": False, "webEditedAt": None,
           "source": keep.get("source") or "file"}
    if keep.get("taskId"):
        out["taskId"] = keep["taskId"]
    if t and t.get("stream"):
        out["stream"] = t["stream"]                    # 規則要求 students 的紀錄必帶
    out["sourceFile"] = (t or {}).get("sourceFile") or keep.get("sourceFile") or ""
    if not out["sourceFile"]:
        out.pop("sourceFile")
    return out


def sync_target(t, base, tok, names, state, dry, notes, counters, cards):
    key = t["key"]
    known = set(state.get(key, {}).get("rids") or [])
    cloud = {rid: (fs, ut) for rid, fs, ut in lib.list_docs(base, t["records"], tok)
             if not t["stream"] or doc_stream(fs) == t["stream"]}
    lines, blocks = lib.parse_file(t["path"])
    file_exists = os.path.exists(t["path"])
    by_rid = {b["rid"]: b for b in blocks}

    pend_push, pend_write, pend_new, pend_del = [], [], [], []

    for b in blocks:
        hit = leaks(names, b["body"], b["tags"], list(b["fields"].values()))
        if hit:
            counters["pii"] += 1
            notes.append("PII %s %s：檔案裡出現名冊真名（%s）——沒有同步這一則" % (key, b["rid"], "、".join(hit)))
            continue
        pair = cloud.get(b["rid"])
        if pair is None:
            if b["rid"] in known:
                pend_del.append(b)               # 以前同步過、現在雲端沒有 → 網頁上被刪了
            else:
                pend_push.append((b, None, {}))
            continue
        fs, ut = pair
        if fs.get("editedOnWeb"):
            if fs.get("contentHash") != b["hash"]:
                counters["conflict"] += 1
                notes.append("衝突 %s %s：網頁與本機檔案都改過，兩邊都保留、都沒動" % (key, b["rid"]))
                continue
            rec = cloud_record(fs)
            hit = leaks(names, rec["body"], rec["tags"], list(rec["fields"].values()))
            if hit:
                counters["pii"] += 1
                notes.append("PII %s %s：網頁那一則出現名冊真名（%s）——沒有寫回檔案"
                             % (key, b["rid"], "、".join(hit)))
                continue
            pend_write.append((b, rec, ut))
        elif fs.get("contentHash") != b["hash"]:
            pend_push.append((b, ut, fs))

    for rid, (fs, ut) in sorted(cloud.items()):
        if rid in by_rid:
            continue
        rec = cloud_record(fs)
        hit = leaks(names, rec["body"], rec["tags"], list(rec["fields"].values()))
        if hit:
            counters["pii"] += 1
            notes.append("PII %s %s：網頁那一則出現名冊真名（%s）——沒有寫進檔案" % (key, rid, "、".join(hit)))
            continue
        if fs.get("editedOnWeb") or rid not in known:
            pend_new.append((rid, rec))
        else:
            notes.append("本機少了 %s %s（雲端還在）：要刪請在網頁上刪，這裡不動雲端資料" % (key, rid))

    # 整檔遺失／變空的保護：不做任何刪除
    if pend_del and (not file_exists or not blocks):
        notes.append("%s 的檔案不見了或變成空的——這一輪不刪任何東西（先確認檔案沒事）" % key)
        pend_del = []

    counters["push"] += len(pend_push)
    counters["write"] += len(pend_write)
    counters["new"] += len(pend_new)
    counters["delete"] += len(pend_del)
    if dry:
        for b, _, _ in pend_push:
            notes.append("（預演）上傳 %s %s" % (key, b["rid"]))
        for b, _, _ in pend_write:
            notes.append("（預演）回寫 %s %s" % (key, b["rid"]))
        for rid, _ in pend_new:
            notes.append("（預演）從網頁新增到檔案 %s %s" % (key, rid))
        for b in pend_del:
            notes.append("（預演）從檔案刪掉 %s %s（網頁上刪了）" % (key, b["rid"]))
        return set(by_rid) | set(cloud)

    # ── 改檔案（回寫、網頁新增、網頁刪除）──
    if pend_write or pend_new or pend_del:
        if file_exists:
            d, name = os.path.dirname(t["path"]), os.path.basename(t["path"])
            shutil.copy2(t["path"], os.path.join(d, "." + name.replace(".md", "") + ".prev.md"))
        else:
            os.makedirs(os.path.dirname(t["path"]), exist_ok=True)
            kind = "case" if (t["kind"] == "students" and t["scope"] == "case") else t["kind"]
            lines = lib.file_header(kind, t["id"], t["label"],
                                    t.get("streamLabel") or "").split("\n")
        edits = []
        for b, rec, _ in pend_write:
            edits.append((b["start"], b["end"],
                          lib.render_block(b["date"], b["time"], rec["tags"], rec["fields"],
                                           rec["related"], rec["body"])))
        for b in pend_del:
            edits.append((b["start"], b["end"], []))
        for s, e, new in sorted(edits, key=lambda x: -x[0]):
            lines[s:e] = new
        for rid, rec in sorted(pend_new):
            date = rec["date"] or rid[:10]
            while lines and lines[-1].strip() == "":
                lines.pop()
            lines.append("")
            lines += lib.render_block(date, lib.time_from_rid(date, rid), rec["tags"],
                                      rec["fields"], rec["related"], rec["body"])
        with open(t["path"], "w", encoding="utf-8") as f:
            f.write("\n".join(lines).rstrip("\n") + "\n")

        # 寫回去之後，把「檔案現在長的樣子」推回雲端並清掉 editedOnWeb 旗標
        _, nb = lib.parse_file(t["path"])
        now = {x["rid"]: x for x in nb}
        for rid in [b["rid"] for b, _, _ in pend_write] + [r for r, _ in pend_new]:
            x = now.get(rid)
            if not x:
                continue
            fs, ut = cloud.get(rid, ({}, None))
            try:
                lib.http("PATCH", base, "%s/%s" % (t["records"], rid), tok,
                         record_body(x, fs, t), precondition_update_time=ut, raise_errors=True)
            except lib.Precondition:
                counters["conflict"] += 1
                notes.append("衝突 %s %s：正要清旗標時網頁又改了一次——已保留兩邊，下次再同步" % (key, rid))
        for b in pend_del:
            lib.audit({"op": "delete", "kind": t["kind"], "target": t["id"], "rid": b["rid"],
                       "reason": "雲端已刪，同步刪除本機區塊"})

    # ── 推上雲 ──
    for b, ut, fs in pend_push:
        try:
            lib.http("PATCH", base, "%s/%s" % (t["records"], b["rid"]), tok,
                     record_body(b, fs, t), precondition_update_time=ut,
                     precondition_exists=None if ut else False, raise_errors=True)
        except lib.Precondition:
            counters["conflict"] += 1
            counters["push"] -= 1
            notes.append("衝突 %s %s：雲端在同步途中被改過——這一則沒上傳" % (key, b["rid"]))

    # ── 卡片摘要：同一位學生的每一種記錄類型共用一張卡，所以先累加、迴圈跑完再寫一次 ──
    _, fb = lib.parse_file(t["path"])
    if t["card"]:
        c = cards.setdefault(t["card"], {"id": t["id"], "kind": t["kind"],
                                         "label": t["label"], "dates": [], "streams": {}})
        c["dates"] += [x["date"] for x in fb]
        if t["stream"]:
            c["streams"][t["stream"]] = len(fb)
        else:
            c["label"] = t["label"]
    return ({x["rid"] for x in fb} | set(cloud)) - {b["rid"] for b in pend_del}


def sync_student_card(sid, path, base, tok, state, dry, notes):
    """學生卡片上的兩塊底稿（IEP goals／個案概念化）雙向同步。

    這兩塊跟記錄不一樣——它們會被回頭改（目標改寫、結案標準補上），所以要兩邊都能改。
    判斷方式跟名冊第三欄一樣，用上次同步的指紋當基準：
      · 只有本機改 → 推上去　· 只有網頁改 → 寫回 card.json　· 兩邊都改 → 不覆蓋，印出來
    回傳這一次之後的基準指紋（沒同步成功就沿用舊的）。
    """
    baseline = ((state.get("_cards") or {}).get(sid) or "")
    local = lib.load_card(sid)
    fields, ut = lib.get_doc(base, path, tok)
    cloud = {"id": sid,
             "goals": lib.norm_goals((fields or {}).get("goals")),
             "conceptualization": lib.norm_conceptualization((fields or {}).get("conceptualization"))}
    lh, ch = lib.card_fingerprint(local), lib.card_fingerprint(cloud)
    if lh == ch:
        return lh
    if ch == baseline:                                   # 只有本機改過 → 推上去
        if dry:
            notes.append("（預演）卡片 %s：本機的目標／個案概念化會推上去" % sid)
            return baseline
        try:
            lib.http("PATCH", base, path, tok,
                     {"goals": local["goals"], "conceptualization": local["conceptualization"]},
                     mask=["goals", "conceptualization"],
                     precondition_update_time=ut,
                     precondition_exists=None if ut else False, raise_errors=True)
        except lib.Precondition:
            notes.append("衝突 卡片 %s：網頁在同步途中改過目標／個案概念化——這次沒推上去" % sid)
            return baseline
        notes.append("卡片 %s：目標／個案概念化已推上雲端" % sid)
        return lh
    if lh == baseline:                                   # 只有網頁改過 → 寫回本機
        if dry:
            notes.append("（預演）卡片 %s：網頁上的目標／個案概念化會寫回 card.json" % sid)
            return baseline
        lib.save_card(sid, cloud)
        notes.append("卡片 %s：網頁改的目標／個案概念化已寫回 %s"
                     % (sid, os.path.relpath(lib.card_path(sid), lib.root())))
        return ch
    notes.append("衝突 卡片 %s：本機與網頁的目標／個案概念化都改過——兩邊都沒動，"
                 "打開 %s 跟網頁比對後留一邊" % (sid, os.path.relpath(lib.card_path(sid), lib.root())))
    return baseline


def write_cards(cards, base, tok, notes=None):
    """把累加好的卡片摘要寫回去（學生卡、課程卡、業務組卡）。

    兩條規則，理由都是「不要弄丟老師在網頁上打的字」：
      · **只推統計欄位**：recordCount／lastRecordDate／monthsRecorded／streamCounts（＋id）。
        課名（courses.title）與組名（business.label）**以網頁為準**，不進 updateMask——
        老師在網頁上把「主課程」改成「五年級主課程」之後，腳本不該用 config/tabs.json
        的舊名字把它改回去。唯一的例外是這張卡雲端還沒有（下面 exists=false 的建立情境），
        那時候帶一次 label 只是把空白填起來，沒有覆寫任何人的字。
      · **PATCH 一律帶前置條件**（紅隊 #9）：先 get_doc 拿 updateTime，PATCH 帶
        currentDocument.updateTime；讀完之後網頁又改過就回 412 → 記一筆衝突、不重試覆寫。
        卡片沒有「兩邊都改」的問題（統計是算出來的），但 412 代表我們手上的 updateTime
        已經過期，硬寫下去等於用舊快照蓋新文件。
    """
    for path, c in sorted(cards.items()):
        dates = [d for d in c["dates"] if d]
        summary = {"id": c["id"], "recordCount": len(c["dates"]),
                   "lastRecordDate": max(dates, default=""),
                   "monthsRecorded": sorted({d[:7] for d in dates})}
        if c["kind"] == "students":
            summary["streamCounts"] = c["streams"]     # 哪一種類型各幾則
        fields, ut = lib.get_doc(base, path, tok)
        if fields is None and c["kind"] != "students":
            summary["label"] = c["label"]              # 只有「這張卡還不存在」才補名字
        try:
            lib.http("PATCH", base, path, tok, summary, mask=list(summary.keys()),
                     precondition_update_time=ut,
                     precondition_exists=None if ut else False, raise_errors=True)
        except lib.Precondition:
            if notes is not None:
                notes.append("衝突 卡片 %s：網頁在同步途中改過這張卡——這次沒更新它的統計"
                             "（記錄本身已經同步好了），下次同步會再算一次" % path)


def sync_roster(kit, base, tok, state, dry, notes):
    """名冊：姓名以本機 roster.csv 為準；「哪些學生列入哪些個案型類型」兩邊都可以改。

    網頁可以在某個類型下「列入／移出」學生（寫 roster/main.students[].streams），
    所以第三欄要能回寫。用上次同步的樣子當基準判斷是誰改的：
      · 只有網頁改 → 回寫 roster.csv 第三欄
      · 只有本機改 → 推上去
      · 兩邊都改   → **不覆蓋**，印出來讓老師自己決定（跟記錄的衝突規則一致）
    """
    rows = lib.load_roster_rows(kit)
    baseline = (state.get("_roster") or {}).get("streams") or {}
    cloud_doc, roster_ut = lib.get_doc(base, "roster/main", tok)
    cloud_list = (cloud_doc or {}).get("students") or []
    cloud = {}
    for s in cloud_list:
        if isinstance(s, dict) and s.get("id"):
            cloud[s["id"]] = {"name": str(s.get("name") or ""),
                              "streams": [str(x) for x in (s.get("streams") or [])]}

    pull, conflict = {}, []
    for sid in sorted(set(rows) | set(cloud)):
        loc = sorted((rows.get(sid) or {}).get("streams") or [])
        cld = sorted((cloud.get(sid) or {}).get("streams") or [])
        base_ = sorted(baseline.get(sid) or [])
        if loc == cld:
            continue
        if sid not in rows:
            notes.append("名冊 %s：網頁上有這位學生但 data/roster.csv 沒有——"
                         "把他加進名冊（代號,姓名,類型）才會同步他的紀錄" % sid)
            continue
        if sid not in baseline:
            continue                                   # 沒有基準（第一次同步）→ 以本機為準推上去
        if cld != base_ and loc == base_:
            pull[sid] = cld                            # 只有網頁改
        elif loc != base_ and cld == base_:
            pass                                       # 只有本機改 → 下面整份推上去
        else:
            conflict.append(sid)
            notes.append("衝突 名冊 %s：本機第三欄（%s）與網頁（%s）都改過，兩邊都沒動"
                         % (sid, ";".join(loc) or "空", ";".join(cld) or "空"))

    if pull and not dry:
        for sid, streams in pull.items():
            rows[sid]["streams"] = streams
        lib.save_roster_rows(rows)
        notes.append("名冊：把網頁上改過的記錄類型寫回 data/roster.csv 第三欄（%s）"
                     % "、".join(sorted(pull)))
    elif pull:
        for sid in sorted(pull):
            notes.append("（預演）把網頁上的類型寫回名冊 %s：%s" % (sid, ";".join(pull[sid]) or "空"))

    # 推上去的那份：本機為主，網頁上多出來的學生原樣保留（不靜默刪掉別人加的東西）
    merged = []
    for sid in sorted(set(rows) | set(cloud)):
        if sid in rows:
            streams = pull.get(sid, (rows[sid].get("streams") or []))
            if sid in conflict:
                streams = (cloud.get(sid) or {}).get("streams") or []   # 衝突：雲端維持原樣
            merged.append({"id": sid,
                           "name": rows[sid].get("name") or (cloud.get(sid) or {}).get("name", ""),
                           "streams": list(streams)})
        else:
            merged.append(dict({"id": sid}, **cloud[sid]))
    if merged and not dry:
        # 帶 updateMask：roster/main 上還有 protectedPhrases（§2 的形狀），
        # 無 mask 的整份 PATCH 會把它靜默清掉。
        # 帶 currentDocument 前置條件（紅隊 #9）：網頁的「＋ 列入學生」寫的就是這份
        # students[].streams——我們讀完之後老師剛好在網頁上列入一位，無條件 PATCH
        # 會把他靜默蓋掉。412 就當衝突，不重試覆寫，下次同步再對。
        try:
            lib.http("PATCH", base, "roster/main", tok, {"students": merged}, mask=["students"],
                     precondition_update_time=roster_ut,
                     precondition_exists=None if roster_ut else False,
                     raise_errors=True)
        except lib.Precondition:
            notes.append("衝突 名冊：網頁在同步途中改過 roster/main——這次沒回寫，"
                         "下次同步會重新比對（本機 data/roster.csv 沒有變動）")
            return {sid: sorted((rows.get(sid) or {}).get("streams") or [])
                    for sid in rows}
    return {m["id"]: sorted(m["streams"]) for m in merged}


def check_web_additions(tabs, base, tok, notes):
    """網頁上臨時加的記錄類型／業務組：印一行提醒，**不自動改 config**。

    config/tabs.json 是本機檔與安全規則的依據，改它是有後果的事——所以這裡只報告，
    由老師跟 AI 說一聲，AI 再重跑安裝精靈把它正式加進去。
    """
    try:
        cfg, _ = lib.get_doc(base, "meta/config", tok, raise_errors=True)
    except Exception:
        return
    known_streams = {s["id"] for s in lib.student_streams(tabs)}
    for s in ((cfg or {}).get("studentStreams") or []):
        sid = s.get("id") if isinstance(s, dict) else str(s)
        label = (s.get("label") if isinstance(s, dict) else "") or sid
        if sid and sid not in known_streams:
            notes.append("網頁上有學生記錄類型「%s」（%s）但 config/tabs.json 沒有，"
                         "請跟 AI 說要加進去" % (label, sid))
    if not (tabs.get("business") or {}).get("enabled", True):
        return
    known_groups = {g.get("id") for g in ((tabs.get("business") or {}).get("groups") or [])}
    try:
        for gid, fs, _ in lib.list_docs(base, "business", tok, raise_errors=True):
            if gid not in known_groups:
                notes.append("網頁上有業務組「%s」（%s）但 config/tabs.json 沒有，"
                             "請跟 AI 說要加進去" % (fs.get("label") or gid, gid))
    except Exception:
        pass


def main():
    ap = argparse.ArgumentParser(description="本機 markdown 與 Firestore 雙向同步（衝突不覆蓋）")
    ap.add_argument("--dry-run", action="store_true", help="只看會發生什麼，不寫任何東西")
    ap.add_argument("--only", metavar="種類/代號", help="只同步一個目標，例如 students/S-03")
    ap.add_argument("--quiet", action="store_true", help="沒事就不出聲（排程用）")
    lib.add_root_arg(ap)
    a = ap.parse_args()
    lib.apply_root(a)

    kit = lib.load_kit()
    tabs = lib.load_tabs()
    base = lib.fb_base(kit)
    tok = lib.token()
    names = lib.real_names(kit)
    state = load_state()
    tg = lib.targets(kit, tabs)
    if a.only:
        tg = [t for t in tg
              if t["key"] == a.only or "%s/%s" % (t["kind"], t["id"]) == a.only]
        if not tg:
            lib.die("找不到目標 %s" % a.only,
                    "格式是 <種類>/<代號>[/<記錄類型>]，種類有 students、class、courses、business；"
                    "學生記錄可以只同步一種類型（例如 students/S-03/case），不寫類型＝那位學生全部。"
                    "跑 `python3 scripts/ledger.py --check --offline` 可以看到所有目標。")

    notes, counters = [], {"push": 0, "write": 0, "new": 0, "delete": 0, "conflict": 0, "pii": 0}
    cards = {}
    for t in tg:
        rids = sync_target(t, base, tok, names, state, a.dry_run, notes, counters, cards)
        if not a.dry_run:
            state[t["key"]] = {"rids": sorted(rids), "at": lib.now_iso()}

    # 學生卡片的兩塊底稿（IEP goals／個案概念化）雙向同步——預演也跑，只是不寫。
    card_state = dict(state.get("_cards") or {})
    for path, c in sorted(cards.items()):
        if c["kind"] != "students":
            continue
        fp = sync_student_card(c["id"], path, base, tok, state, a.dry_run, notes)
        if fp:
            card_state[c["id"]] = fp
    if not a.dry_run:
        state["_cards"] = card_state
        write_cards(cards, base, tok, notes)
    roster_streams = sync_roster(kit, base, tok, state, a.dry_run, notes)
    check_web_additions(tabs, base, tok, notes)
    if not a.dry_run:
        state["_roster"] = {"streams": roster_streams, "at": lib.now_iso()}
        save_state(state)
        # meta/config 與 meta/status 不帶前置條件：這兩份文件裡的欄位只有腳本會寫
        # （version／dataVersion／tabs 是本機 config 的唯讀鏡像，lastSyncAt 是同步時間戳），
        # 網頁只讀不改，所以沒有「蓋掉老師的字」這回事，最後寫的那次就是對的。
        lib.http("PATCH", base, "meta/config", tok,
                 {"version": lib.version(), "dataVersion": lib.DATA_VERSION,
                  "tabs": json.dumps(tabs, ensure_ascii=False)},
                 mask=["version", "dataVersion", "tabs"])
        lib.touch_status(base, tok, "lastSyncAt")

    line = ("%s同步 %d 個目標：上傳 %d、回寫 %d、從網頁新增 %d、刪除 %d、衝突 %d、真名攔截 %d"
            % ("（預演）" if a.dry_run else "", len(tg), counters["push"], counters["write"],
               counters["new"], counters["delete"], counters["conflict"], counters["pii"]))
    status = {"at": lib.now_iso(), "dryRun": a.dry_run, "targets": len(tg),
              "counters": counters, "notes": notes}
    if not a.dry_run:
        with open(lib.rpath(".sync-last-status"), "w", encoding="utf-8") as f:
            json.dump(status, f, ensure_ascii=False, indent=1)
    if not a.quiet or counters["conflict"] or counters["pii"] or notes:
        print(line)
        for n in notes:
            print("  · " + n)
    if counters["conflict"] or counters["pii"]:
        print("\n%s衝突與真名攔截都不會自動處理——上面每一則都要你自己看過。%s" % (lib.YELLOW, lib.RESET))
        print("  衝突：打開那個檔案跟網頁比對，決定留哪一邊，改完再跑一次。")
        print("  真名：把正文裡的姓名改成代號（真名只放 data/roster.csv）。")


if __name__ == "__main__":
    main()
