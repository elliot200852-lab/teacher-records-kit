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
    就前置條件不成立（Firestore 依情境回 400 FAILED_PRECONDITION／409 ALREADY_EXISTS／412，
    lib.py 三種都認成 Precondition），當成衝突處理、不重試覆寫
    （紅隊 #9：沒有這條，老師在手機上打字會被靜默蓋掉）。
  · 刪除：雲端那則被刪掉（以前同步過、現在不見了）→ 從本機檔案也刪掉，並寫進 data/audit.jsonl。
    但**整個檔案不見或變成空的時候一律不刪任何東西**——那多半是檔案出事，不是老師要刪。
  · 軟刪（兩段式刪除的第一段）：雲端那則帶 `deleted: true`（網頁上刪的）＝視同雲端已刪——
    本機區塊照樣刪掉、照樣寫 audit（不帶正文），但雲端原文原封不動留著，等老師自己跑
    `scripts/purge_deleted.py` 才真的消失。軟刪的那則**絕不會**被當成「雲端新增」寫回本機；
    本機本來就沒有那一則（例如網頁新增後立刻刪）就什麼都不做。刪完本機區塊就沒了，
    下一輪自然不會再刪一次。
  · 回寫前先備份成 `.<檔名>.prev.md`。
  · 學生卡片上的兩塊底稿（IEP 的 goals、個案概念化）也雙向同步：只有一邊改就照那一邊，
    兩邊都改就印出來讓老師自己決定——跟記錄同一條規則。
  · 課程卡上的「整體課程紀錄」（overview，整門課不分天的那一段）同一條規則雙向同步，
    本機正本是 data/courses/<id>/card.json。
  · 網頁上開的新課：本機自動補一個空的 records.md，下一輪它就是正式目標（其餘網頁新增的
    記錄類型／業務組只提醒，不自動改 config）。
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
    with open(os.path.join(lib.data_dir(), STATE_FILE), "w", encoding="utf-8", newline="\n") as f:
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


def accumulate_card(cards, t, blocks):
    """卡片摘要：同一位學生的每一種記錄類型共用一張卡，所以先累加、迴圈跑完再寫一次。"""
    if not t["card"]:
        return
    c = cards.setdefault(t["card"], {"id": t["id"], "kind": t["kind"],
                                     "label": t["label"], "dates": [], "streams": {}})
    c["dates"] += [x["date"] for x in blocks]
    if t["stream"]:
        c["streams"][t["stream"]] = len(blocks)
    else:
        c["label"] = t["label"]


def sync_target(t, base, tok, names, state, dry, notes, counters, cards):
    """回傳「這一輪過後，這個目標在雲端有哪些 rid」——那就是下一次的 state。

    **只能放雲端真的有的 rid**（現在讀到的，加上這一輪真的推成功的）。
    把本機每一則都寫進去（含被真名閘攔下、被前置條件擋下而沒上傳的）的話，
    下一輪那些 rid 會變成「以前同步過、現在雲端沒有」＝網頁上刪了，
    於是把老師本機的區塊刪掉——紀錄就這樣不見了。
    """
    key = t["key"]
    known = set(state.get(key, {}).get("rids") or [])
    all_cloud = {rid: (fs, ut) for rid, fs, ut in lib.list_docs(base, t["records"], tok)
                 if not t["stream"] or doc_stream(fs) == t["stream"]}
    # 兩段式刪除：網頁上刪掉的那則只是被標成 deleted，文件還留在雲端。
    # 這裡把它從 cloud 拿掉＝本機視同已刪：本機有就刪本機區塊，本機沒有就什麼都不做，
    # 而且它永遠不會走到下面那個「雲端有、本機沒有 → 寫回檔案」的迴圈。
    soft = {rid for rid, (fs, _ut) in all_cloud.items() if lib.is_deleted(fs)}
    cloud = {rid: pair for rid, pair in all_cloud.items() if rid not in soft}
    lines, blocks = lib.parse_file(t["path"])
    file_exists = os.path.exists(t["path"])
    by_rid = {b["rid"]: b for b in blocks}

    pend_push, pend_write, pend_new, pend_del = [], [], [], []

    for b in blocks:
        if b["rid"] in soft:
            # 網頁軟刪了這一則：本機區塊要刪（真名閘不用管——刪掉不會外洩任何東西），
            # 而且不可以走下面的 pend_push，否則會把雲端那份軟刪的原文蓋回「沒刪」。
            pend_del.append(b)
            continue
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
            notes.append("（預演）從檔案刪掉 %s %s（%s）"
                         % (key, b["rid"],
                            "網頁上刪了，雲端原文留著" if b["rid"] in soft else "網頁上刪了"))
        accumulate_card(cards, t, blocks)      # 預演也要累加，卡片那一段才印得出預演訊息
        return set(all_cloud)

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
        with open(t["path"], "w", encoding="utf-8", newline="\n") as f:
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
            # 稽核只留「哪一則、內容指紋是什麼」，不留正文——audit.jsonl 不是紀錄的第二份正本。
            lib.audit({"op": "delete", "kind": t["kind"], "target": t["id"], "rid": b["rid"],
                       "hash": b["hash"],
                       "reason": ("雲端軟刪，同步刪除本機區塊" if b["rid"] in soft
                                  else "雲端已刪，同步刪除本機區塊")})

    # ── 推上雲 ──
    pushed = set()
    for b, ut, fs in pend_push:
        try:
            lib.http("PATCH", base, "%s/%s" % (t["records"], b["rid"]), tok,
                     record_body(b, fs, t), precondition_update_time=ut,
                     precondition_exists=None if ut else False, raise_errors=True)
            pushed.add(b["rid"])
        except lib.Precondition:
            counters["conflict"] += 1
            counters["push"] -= 1
            # 409 也可能是「同一天另一種記錄類型已經占用這個文件 id」——v3 alpha 之前
            # 取號沒看兄弟檔，舊資料裡還會有這種撞號（現在由 append_record 取號時避開）。
            notes.append("衝突 %s %s：雲端在同步途中被改過，或同一天另一種記錄類型已經用掉"
                         "這個紀錄 id——這一則沒上傳" % (key, b["rid"]))

    _, fb = lib.parse_file(t["path"])
    accumulate_card(cards, t, fb)
    # 軟刪的那些 rid 也算「雲端真的有」（文件還在，只是被標成刪除）——記進狀態檔，
    # 下一輪本機區塊已經沒了，不會再刪一次，也不會被當成沒同步過的新紀錄重推上去。
    return set(all_cloud) | pushed


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
    if not baseline:
        # 第一次同步：還沒有基準，而基準是空字串、雲端指紋是「空卡片」的雜湊——
        # 直接比會永遠不相等，於是每一次都報衝突，IEP 目標與個案概念化一輩子上不去。
        # 照名冊第三欄的同一條規則辦：沒有基準就看哪一邊是空的，空的那邊讓另一邊贏。
        empty = lib.card_fingerprint({})
        if ch == empty:
            baseline = ch                                # 雲端還沒有東西 → 本機為準，推上去
        elif lh == empty:
            baseline = lh                                # 本機還沒有東西 → 網頁為準，寫回來
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


def course_card_key(cid):
    """課程卡在 .sync-state.json 的 `_cards` 裡用哪個鍵記基準指紋。

    學生卡用裸代號（`S-02`），課程一定要加 `courses/` 前綴：兩者同放一個 dict，
    代號剛好同名的課與學生會共用同一格，互相把對方「上次同步的樣子」蓋掉，
    於是兩邊每一輪都被報成衝突（或更糟，挑錯邊覆蓋）。
    """
    return "courses/%s" % cid


def sync_course_card(cid, path, base, tok, state, dry, notes):
    """課程卡上的「整體課程紀錄」（overview）雙向同步——跟學生卡片同一條規則。

    整體課程紀錄不是一則一則的紀錄，是整門課不分天的敘述，老師會回頭改：
    今天在網頁上補一段、明天在電腦上改一句。所以：
      · 只有本機改 → 推上去（mask 只有 overview）　· 只有網頁改 → 寫回 card.json
      · 兩邊都改   → **不覆蓋**，印出來讓老師自己決定
    `path` 是雲端那張卡的文件路徑（courses/<id>）；本機正本是 lib.course_card_path(cid)。
    回傳這一次之後的基準指紋（沒同步成功就沿用舊的）。
    """
    key = course_card_key(cid)
    local_path = lib.course_card_path(cid)
    baseline = ((state.get("_cards") or {}).get(key) or "")
    local = lib.load_course_card(local_path)
    fields, ut = lib.get_doc(base, path, tok)
    cloud = {"overview": lib.norm_overview((fields or {}).get("overview"))}
    lh, ch = lib.course_card_fingerprint(local), lib.course_card_fingerprint(cloud)
    if lh == ch:
        return lh
    if not baseline:
        # 第一次同步沒有基準（跟學生卡片同一個坑）：直接比會永遠不相等、每一輪都報衝突。
        # 沒有基準就看哪一邊是空的，空的那邊讓另一邊贏。
        empty = lib.course_card_fingerprint({})
        if ch == empty:
            baseline = ch                                # 雲端還沒有東西 → 本機為準，推上去
        elif lh == empty:
            baseline = lh                                # 本機還沒有東西 → 網頁為準，寫回來
    if ch == baseline:                                   # 只有本機改過 → 推上去
        if dry:
            notes.append("（預演）課程卡 %s：本機的整體課程紀錄會推上去" % cid)
            return baseline
        try:
            # mask 只有 overview：這張卡上的 title／kind／統計欄位都是別人寫的，
            # overviewUpdatedAt 是網頁自己蓋的時間戳——一個都不要碰。
            lib.http("PATCH", base, path, tok, {"overview": local["overview"]},
                     mask=["overview"],
                     precondition_update_time=ut,
                     precondition_exists=None if ut else False, raise_errors=True)
        except lib.Precondition:
            notes.append("衝突 課程卡 %s：網頁在同步途中改過整體課程紀錄——這次沒推上去" % cid)
            return baseline
        notes.append("課程卡 %s：整體課程紀錄已推上雲端" % cid)
        return lh
    if lh == baseline:                                   # 只有網頁改過 → 寫回本機
        if dry:
            notes.append("（預演）課程卡 %s：網頁上的整體課程紀錄會寫回 card.json" % cid)
            return baseline
        lib.save_course_card(local_path, cloud)
        notes.append("課程卡 %s：網頁改的整體課程紀錄已寫回 %s"
                     % (cid, os.path.relpath(local_path, lib.root())))
        return ch
    notes.append("衝突 課程卡 %s：本機與網頁的整體課程紀錄都改過——兩邊都沒動，"
                 "打開 %s 跟網頁比對後留一邊" % (cid, os.path.relpath(local_path, lib.root())))
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
        currentDocument.updateTime；讀完之後網頁又改過就前置條件不成立
        （400 FAILED_PRECONDITION／409／412，lib.py 一律丟 Precondition）→ 記一筆衝突、不重試覆寫。
        卡片沒有「兩邊都改」的問題（統計是算出來的），但前置條件不成立代表我們手上的 updateTime
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
            # overview（整體課程紀錄）／title／kind 是網頁擁有的欄位，mask 永遠不要加進來，
            # 否則會清掉：這裡的 summary 沒有那幾個鍵，帶進 mask 等於叫 Firestore
            # 把老師在網頁上打的整篇整體課程紀錄刪成空的。
            # 整體課程紀錄走 sync_course_card 那條雙向路徑，不走這裡。
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
        # 會把他靜默蓋掉。前置條件不成立（400 FAILED_PRECONDITION／409／412）就當衝突，
        # 不重試覆寫，下次同步再對。
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


def check_web_additions(tabs, base, tok, notes, course_ids=None, dry=False):
    """網頁上臨時加的記錄類型／業務組：印一行提醒，**不自動改 config**。

    config/tabs.json 是本機檔與安全規則的依據，改它是有後果的事——所以這裡只報告，
    由老師跟 AI 說一聲，AI 再重跑安裝精靈把它正式加進去。

    課程是唯一的例外，因為它不必動 config 就能成立：`lib.targets` 認得 data/courses/ 底下
    的每一個資料夾，所以「網頁上開了一門新課」只要在本機補一個空的 records.md，
    下一輪同步它就是一個正式目標，網頁上那幾則紀錄才帶得下來（少了這一步，老師在手機上
    開的課會一直停在雲端，本機備份與 Word 匯出都看不到它）。
    `course_ids` ＝本機已經認得的課程 id（main 傳 `lib.targets` 算出來的那一份）；
    不給就不檢查課程——沒有那份清單就無從判斷「本機有沒有」，寧可不動也不要亂建資料夾。
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
    if course_ids is not None and (tabs.get("courses") or {}).get("enabled", True):
        try:
            cloud_courses = lib.list_docs(base, "courses", tok, raise_errors=True)
        except Exception:
            cloud_courses = []
        for cid, fs, _ in cloud_courses:
            if not cid or cid in course_ids:
                continue
            title = str(fs.get("title") or fs.get("label") or "").strip() or cid
            path = os.path.join(lib.data_dir(), "courses", cid, "records.md")
            rel = os.path.relpath(path, lib.root())
            if dry:
                notes.append("（預演）網頁上新增的課程「%s」（%s）會建一個本機檔 %s" % (title, cid, rel))
                continue
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if not os.path.exists(path):        # 保險：檔在、targets 卻沒認到就不要覆蓋它
                with open(path, "w", encoding="utf-8", newline="\n") as f:
                    f.write(lib.file_header("courses", cid, title))
            notes.append("從網頁新增的課程「%s」（%s）已建本機檔 %s——下一輪同步"
                         "就會把網頁上那幾則紀錄帶下來" % (title, cid, rel))
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
    # 本機模式沒有雲端可以同步。退出碼 0（不是錯誤）：排程與 append_record.py --sync
    # 都會叫到這一支，本機模式下它就該安安靜靜地什麼都不做。
    if lib.is_local(kit):
        if not a.quiet:
            print("本機模式沒有雲端，不用同步。紀錄就在 %s 底下。"
                  % os.path.relpath(lib.data_dir(), lib.root()))
            print("  想改用手機網頁：把 config/kit.json 的 mode 改成 cloud，"
                  "再跑一次 `%s scripts/setup.py`。" % lib.PY)
        return
    base = lib.fb_base(kit)
    tok = lib.token()
    names = lib.real_names(kit)
    state = load_state()
    tg = lib.targets(kit, tabs)
    # --only 會把 tg 砍掉，但「網頁上新增的課程」要跟全部本機課程比才算得準——先留一份。
    course_ids = {t["id"] for t in tg if t["kind"] == "courses"}
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

    # 卡片上那些「會被回頭改」的底稿雙向同步——預演也跑，只是不寫。
    #   學生：IEP goals／個案概念化　　課程：整體課程紀錄（overview）
    card_state = dict(state.get("_cards") or {})
    for path, c in sorted(cards.items()):
        if c["kind"] == "students":
            fp = sync_student_card(c["id"], path, base, tok, state, a.dry_run, notes)
            if fp:
                card_state[c["id"]] = fp
        elif c["kind"] == "courses":
            fp = sync_course_card(c["id"], path, base, tok, state, a.dry_run, notes)
            if fp:
                card_state[course_card_key(c["id"])] = fp
    if not a.dry_run:
        state["_cards"] = card_state
        write_cards(cards, base, tok, notes)
    roster_streams = sync_roster(kit, base, tok, state, a.dry_run, notes)
    check_web_additions(tabs, base, tok, notes, course_ids, a.dry_run)
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
        # 狀態列不能只有「上次同步時間」：有衝突、有真名攔截的那一輪也會更新時間，
        # 網頁於是顯示綠燈，而老師其實有幾則沒上去。把數字一起寫上去，網頁照這三個欄位判斷。
        status_fields = {"lastSyncAt": lib.now_iso(),
                         "lastSyncConflicts": counters["conflict"],
                         "lastSyncPii": counters["pii"],
                         "lastError": ""}
        lib.http("PATCH", base, "meta/status", tok, status_fields,
                 mask=list(status_fields))

    line = ("%s同步 %d 個目標：上傳 %d、回寫 %d、從網頁新增 %d、刪除 %d、衝突 %d、真名攔截 %d"
            % ("（預演）" if a.dry_run else "", len(tg), counters["push"], counters["write"],
               counters["new"], counters["delete"], counters["conflict"], counters["pii"]))
    status = {"at": lib.now_iso(), "dryRun": a.dry_run, "targets": len(tg),
              "counters": counters, "notes": notes}
    if not a.dry_run:
        with open(lib.rpath(".sync-last-status"), "w", encoding="utf-8", newline="\n") as f:
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
