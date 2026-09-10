#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""append_record.py — 唯一被允許寫入記錄檔的通道。

為什麼要有這道閘：AI 代理如果直接編輯 records.md，很容易「把新的一則插進同一天的舊區塊
前面」或整檔重寫。那會讓既有紀錄的 id 重新編號，下一次同步就把它們當成「舊的刪了、
新的加了」——雲端那邊的紀錄會被誤刪。所以寫入收斂成這一支，四道閘全部在動檔案之前跑完：

  ① 目標白名單　kind＋target（＋學生記錄的 --stream）必須是 config 裡真的存在的目標
  ② 真名攔截　　正文／欄位／標籤出現名冊真名就拒寫（代號制的最後一道防線）
  ③ 只追加　　　O_APPEND 從檔尾追加，不 seek、不重寫、不插入
  ④ id 不變　　 寫前後各解析一次，斷言「舊的 id 一個都沒變、剛好多一則」，
                 違反就把檔案截回原長度並異常退出（寧可什麼都沒寫，也不留半截）

用法：
  python3 scripts/append_record.py --kind students --target S-03 --stream homeroom \\
      --tags "#課堂 #人際" --content-file 草稿.md

  學生記錄一定要指定 `--stream`（記錄類型）：導師的班級紀錄、任課老師的觀察、個案追蹤、
  IEP、輔導晤談各寫各的檔，混在一起就分不清楚。可用的類型看 config/tabs.json 的
  students.streams（漏給或給錯，這支會拒寫並把可用的列出來）。

  python3 scripts/append_record.py --kind business --target paperwork \\
      --date 2026-09-10 --fields-json '{"期限":"2026-09-20","辦理情形":"處理中"}' \\
      --related "students/S-03/2026-09-10" --content-file 草稿.md --source voice \\
      --task-id voice-2026-09-10-001 --sync

  --fields-json 的兩個方便寫法：
    · 複選欄位（面向這種 multiselect）可以直接給陣列，會用「／」串起來寫進檔案：
      `--fields-json '{"面向":["頭·思考","手·意志"],"報告維度":"學習態度與能力"}'`
    · IEP 的「目標編號」一定要是這位學生卡片（data/students/<代號>/card.json）上真的有的
      目標 id；給了不存在的編號這支會拒寫，並把可用的目標列出來。

參數：--content-file 用 `-` 代表從 stdin 讀。--date 預設今天。
退出碼：0 成功｜2 參數不合法（含目標編號不存在）｜3 目標不在設定裡｜5 正文含名冊真名｜
       6 檔案不存在｜9 id 斷言失敗
"""
import io
import os
import re
import sys
import json
import argparse
import subprocess
from datetime import date as _date, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

EXIT_ARGS, EXIT_TARGET, EXIT_PII, EXIT_MISSING, EXIT_ASSERT = 2, 3, 5, 6, 9
# 複選欄位寫進檔案時的分隔符（`面向：頭·思考／心·意志`）。
MULTI_SEP = "／"
# 「這一則掛在哪一條目標下」的欄位名（IEP／早療）。型別 goal 的欄位一律照這個檢查。
GOAL_FIELD = "目標編號"


def bail(code, msg, fix=""):
    lib.err(msg, fix)
    sys.exit(code)


def next_rid(blocks, date, now=None):
    """同一天已經有紀錄就帶時間；連時間都撞到就補到秒。"""
    used = {b["rid"] for b in blocks}
    if date not in used:
        return date, None
    now = now or datetime.now()
    tm = now.strftime("%H:%M")
    if lib.rid_for(date, tm) not in used:
        return lib.rid_for(date, tm), tm
    tm = now.strftime("%H:%M:%S")
    if lib.rid_for(date, tm) in used:
        bail(EXIT_ARGS, "同一秒已經有一則紀錄了（%s）。" % lib.rid_for(date, tm),
             "等一秒再跑一次就好。")
    return lib.rid_for(date, tm), tm


def main():
    ap = argparse.ArgumentParser(
        description="把一則記錄安全地追加到本機 markdown 檔（唯一寫入通道）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="AI 代理請一律用這支寫入，不要自己編輯 data/ 底下的 md 檔。")
    ap.add_argument("--kind", required=True, choices=list(lib.KINDS), help="記錄種類")
    ap.add_argument("--target", default="", help="對象代號（class 固定 main；students 用 S-03 這種代號）")
    ap.add_argument("--stream", default="",
                    help="學生記錄類型（--kind students 必填；--kind class 也吃，限 scope:class 的類型）")
    ap.add_argument("--date", default="", help="日期 YYYY-MM-DD（預設今天）")
    ap.add_argument("--time", default="", dest="time_", help="時間 HH:MM（不給就在同日撞號時自動帶現在時間）")
    ap.add_argument("--tags", default="", help='標籤，例如 "#課堂 #人際"')
    ap.add_argument("--content-file", required=True, metavar="檔案", help="正文檔（`-` ＝從 stdin 讀）")
    ap.add_argument("--fields-json", default="", metavar="JSON", help='欄位，例如 \'{"期限":"2026-09-20"}\'')
    ap.add_argument("--related", default="", help='關聯，分號分隔："students/S-03/2026-09-10"')
    ap.add_argument("--source", default="file", choices=["web", "voice", "file"], help="這一則哪裡來的")
    ap.add_argument("--task-id", default="", help="語音來源的任務代號（選填）")
    ap.add_argument("--allow-names", action="store_true",
                    help="放行真名檢查（極少數情況：對象根本不是本班學生）。會寫進稽核記錄。")
    ap.add_argument("--sync", action="store_true", help="寫完順手跑一次 sync.py（只同步這個目標）")
    ap.add_argument("--json", action="store_true", dest="as_json", help="結果輸出 JSON（給 AI 代理讀）")
    lib.add_root_arg(ap)
    a = ap.parse_args()
    lib.apply_root(a)

    kit = lib.load_kit()
    tabs = lib.load_tabs()

    # ── 閘①：目標白名單（含記錄類型）──
    target_id = a.target or ("main" if a.kind == "class" else "")
    if not target_id:
        bail(EXIT_ARGS, "--target 沒給。", "students 用代號（S-03）、courses／business 用設定裡的 id。")

    stream = a.stream.strip()
    if a.kind in ("students", "class"):
        want_scope = "class" if a.kind == "class" else None
        avail_streams = [s for s in lib.student_streams(tabs)
                         if want_scope is None or s.get("scope", "class") == want_scope]
        names = "、".join("%s（%s）" % (s["id"], s.get("label") or s["id"]) for s in avail_streams)
        if not avail_streams:
            bail(EXIT_TARGET, "設定裡一種學生記錄類型都沒有，沒有地方可以寫。",
                 "重跑 `python3 scripts/setup.py`，在「勾選你要的記錄類型」那題勾起來"
                 "（導師班級學生紀錄、個案追蹤、IEP、輔導晤談…）。")
        if not stream:
            if a.kind == "class" and len(avail_streams) == 1:
                stream = avail_streams[0]["id"]          # 只有一種就不必逼使用者打
            else:
                bail(EXIT_ARGS, "--kind %s 一定要指定 --stream（記錄類型）。" % a.kind,
                     "可用的類型：%s。例如 `--stream %s`。導師的班級紀錄、個案追蹤、IEP、"
                     "輔導晤談要分開寫，混在一起就分不清楚。" % (names, avail_streams[0]["id"]))
        # 舊 id 也認（counseling → soap）：找得到就換成設定裡真正的 id。
        hit = next((s for s in avail_streams if stream in lib.stream_ids(s)), None)
        if hit:
            stream = hit["id"]
        else:
            bail(EXIT_TARGET, "設定裡沒有這種學生記錄類型：%s" % stream,
                 "可用的類型：%s。%s要新增就重跑 `python3 scripts/setup.py`。"
                 % (names, "（--kind class 只能用涵蓋全班的類型。）" if a.kind == "class" else ""))
    elif stream:
        bail(EXIT_ARGS, "--stream 只有 --kind students／class 才用得上（收到 --kind %s）。" % a.kind,
             "課程與業務記錄沒有記錄類型這一層，把 --stream 拿掉。")

    t = lib.find_target(kit, tabs, a.kind, target_id, stream or None)
    if not t:
        avail = sorted({x["id"] for x in lib.targets(kit, tabs)
                        if x["kind"] == a.kind
                        and (not stream or x.get("stream") == stream)})
        bail(EXIT_TARGET, "設定裡沒有這個 %s 目標：%s%s"
             % (a.kind, target_id, ("（類型 %s）" % stream) if stream else ""),
             "目前有的是：%s。要新增就重跑 `python3 scripts/setup.py`"
             "（學生請先填 data/roster.csv；個案型類型要在第三欄列入那位學生）。"
             % ("、".join(avail) if avail else "（一個都沒有）"))
    if not os.path.exists(t["path"]):
        bail(EXIT_MISSING, "找不到記錄檔：%s" % t["path"],
             "跑 `python3 scripts/setup.py` 會把缺的骨架補起來（不會覆蓋已經有的檔）。")

    date = a.date or _date.today().isoformat()
    if not lib.DATE_ONLY_RE.match(date):
        bail(EXIT_ARGS, "--date 格式要是 YYYY-MM-DD（收到 %r）。" % date, "例如 2026-09-10。")
    if a.time_ and not re.match(r"^\d{2}:\d{2}(:\d{2})?$", a.time_):
        bail(EXIT_ARGS, "--time 格式要是 HH:MM（收到 %r）。" % a.time_, "例如 14:35。")

    if a.content_file == "-":
        body = io.TextIOWrapper(sys.stdin.buffer, encoding="utf-8").read()
    else:
        if not os.path.exists(a.content_file):
            bail(EXIT_ARGS, "找不到正文檔：%s" % a.content_file, "先把 AI 改寫好的內容存成一個 .md 檔。")
        with open(a.content_file, encoding="utf-8") as f:
            body = f.read()
    body = body.strip()
    if not body:
        bail(EXIT_ARGS, "正文是空的，拒絕寫入。", "確認 --content-file 指到的檔案有內容。")

    fields = {}
    if a.fields_json:
        try:
            fields = json.loads(a.fields_json)
        except json.JSONDecodeError as e:
            bail(EXIT_ARGS, "--fields-json 不是合法 JSON：%s" % e.msg,
                 "格式像 '{\"期限\":\"2026-09-20\"}'，鍵值都要用雙引號。")
        if not isinstance(fields, dict):
            bail(EXIT_ARGS, "--fields-json 要是一個物件（大括號）。", '例如 \'{"狀態":"進行中"}\'')
        # 複選欄位（multiselect）可以直接給陣列，寫進檔案時用「／」串起來。
        fields = {str(k): (MULTI_SEP.join(str(x).strip() for x in v if str(x).strip())
                           if isinstance(v, (list, tuple)) else str(v))
                  for k, v in fields.items()}

    # ── 閘①之二：目標編號要真的在這位學生的卡片上 ──
    # IEP 的每一則都掛在某一條學年／學期目標下。填了卡片上沒有的編號，期末產報告時
    # 那一則就會變成孤兒（哪一條目標都算不到），所以在這裡就擋下來、並把可用的列出來。
    sdef = lib.find_stream(tabs, t["stream"]) if t.get("stream") else None
    goal_fields = [f.get("name") for f in ((sdef or {}).get("fields") or [])
                   if f.get("type") == "goal" and f.get("name")]
    if GOAL_FIELD not in goal_fields:
        goal_fields.append(GOAL_FIELD)
    if a.kind == "students":
        card = lib.load_card(target_id)
        goal_ids = [g["id"] for g in card.get("goals") or []]
        for name in goal_fields:
            val = (fields.get(name) or "").strip()
            if not val or val in goal_ids:
                continue
            listing = ("；".join("%s＝%s" % (g["id"], g.get("學期目標") or g.get("學年目標") or "（沒寫目標內容）")
                                 for g in card["goals"])
                       if goal_ids else "（這位學生的卡片上一條目標都還沒有）")
            bail(EXIT_ARGS, "%s「%s」不在 %s 的目標清單裡。" % (name, val, target_id),
                 "可用的目標：%s。目標寫在 %s（範本 templates/card.example.json，"
                 "網頁上也能建）；改好再寫一次。"
                 % (listing, os.path.relpath(lib.card_path(target_id), lib.root())))
    tags = lib.norm_tags(a.tags)
    related = lib.parse_related(a.related)
    for r in related:
        if len(r.split("/")) != 3 or r.split("/")[0] not in lib.KINDS:
            bail(EXIT_ARGS, "關聯格式不對：%s" % r,
                 "要寫成 <種類>/<對象>/<紀錄id>，種類是 students、class、courses、business 其中之一。")

    # ── 閘②：真名攔截 ──
    names = lib.real_names(kit)
    hits = lib.find_names(" ".join([body, " ".join(tags), " ".join(fields.values()),
                                    " ".join(fields.keys())]), names)
    if hits and not a.allow_names:
        bail(EXIT_PII, "內容出現名冊上的真名：%s" % "、".join(hits),
             "紀錄一律用代號（真名只留在 data/roster.csv）。把那個名字換成代號再寫一次；"
             "真的不是本班學生的話加 --allow-names（會記進稽核）。")

    # ── 閘③④：只追加 ＋ id 斷言 ──
    before_size = os.path.getsize(t["path"])
    _, before = lib.parse_file(t["path"])
    before_rids = [b["rid"] for b in before]
    rid, tm = (lib.rid_for(date, a.time_), a.time_) if a.time_ else next_rid(before, date)
    if rid in before_rids:
        bail(EXIT_ARGS, "這個紀錄 id 已經存在：%s" % rid, "換一個 --time，或不要指定 --time 讓它自動編。")

    chunk = "\n".join(lib.render_block(date, tm, tags, fields, related, body)).rstrip("\n") + "\n"
    with open(t["path"], "r", encoding="utf-8") as f:
        tail = f.read()[-2:]
    prefix = "" if tail.endswith("\n\n") else ("\n" if tail.endswith("\n") else "\n\n")
    fd = os.open(t["path"], os.O_WRONLY | os.O_APPEND)
    try:
        os.write(fd, (prefix + chunk).encode("utf-8"))
    finally:
        os.close(fd)

    _, after = lib.parse_file(t["path"])
    after_rids = [b["rid"] for b in after]
    if after_rids != before_rids + [rid]:
        with open(t["path"], "r+", encoding="utf-8") as f:
            f.truncate(before_size)
        bail(EXIT_ASSERT,
             "寫入前後的紀錄 id 對不上（本來 %d 則、現在 %d 則）——已經把檔案還原，什麼都沒寫。"
             % (len(before_rids), len(after_rids)),
             "多半是那個檔案裡有格式怪怪的 `## 日期` 標題列。打開 %s 看一下最後幾行。" % t["path"])

    lib.audit({"op": "append", "kind": a.kind, "target": target_id, "stream": t["stream"],
               "rid": rid, "date": date, "tags": tags, "fields": sorted(fields.keys()),
               "related": related, "source": a.source, "taskId": a.task_id or None,
               "chars": len(body), "hash": lib.content_hash(tags, fields, related, body),
               "allowNames": bool(hits and a.allow_names)})

    result = {"ok": True, "kind": a.kind, "target": target_id, "stream": t["stream"],
              "rid": rid, "path": t["path"], "chars": len(body)}
    if a.as_json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        lib.ok("寫入 %s／%s%s　紀錄 id：%s（%d 字）"
               % (a.kind, target_id, ("／%s" % t["stream"]) if t["stream"] else "",
                  rid, len(body)))
        print("  檔案：%s" % t["path"])
        print("  稽核：%s" % os.path.join(lib.data_dir(), "audit.jsonl"))

    if a.sync:
        sys.stdout.flush()
        rc = subprocess.run([sys.executable, os.path.join(lib.PKG, "scripts", "sync.py"),
                             "--root", lib.root(), "--only", t["key"]]).returncode
        if rc != 0:
            lib.warn("同步沒跑成功——紀錄已經安全寫進本機檔案了，稍後再跑 `python3 scripts/sync.py`。")


if __name__ == "__main__":
    main()
