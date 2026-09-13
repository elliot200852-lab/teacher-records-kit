#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""headless.py — 無頭交辦的電腦端：把 LINE 收到的訊息變成一則紀錄。

老師在手機上對自己的 LINE 官方帳號講一段話（或打一行字），
雲端的 relay（functions/line-relay）把它放進 Firestore 的 headless_events；
這一支每 5 分鐘醒來一次，看到還沒處理的就：

  1. 搶件（帶 updateTime 前置條件把 status 改成 processing——兩台電腦同時跑也不會做兩次）
  2. 語音的話把音檔抓下來放 inbox/，跑 transcribe.py 轉成逐字稿（全程在這台電腦上）
  3. 照 AGENTS-HEADLESS.md 叫一次老師選的 AI 代理（非互動），由它用 append_record.py 寫紀錄
  4. 把代理回報的那段話用 LINE 推回老師的手機
  5. 標成 done，並在 data/headless-audit.jsonl 留一行

用法：
  python3 scripts/headless.py --once         處理完待辦就結束（排程跑的就是這一行）
  python3 scripts/headless.py --once --dry-run   只印會做什麼，不改雲端、不叫代理、不推播
  python3 scripts/headless.py --status       看有幾則待辦／處理中／失敗
  python3 scripts/headless.py --pair         印出配對碼（relay 看到的那個 LINE userId）
  python3 scripts/headless.py --retry <id>   把一則失敗的重新排回待辦

設計上的三件事：
  · **失敗不重試**。一則失敗就停在 failed，訊息寫在文件上。自動重試最糟的情況是
    同一段話被寫成三則紀錄——老師得自己去刪。要重跑請明確地 `--retry <id>`。
  · **錄音永遠不刪**。抓下來的音檔轉完會被 transcribe.py 搬到 inbox/done/，不會消失。
  · **金鑰只從環境變數讀**，名字寫在 config/kit.json（headless.line.*_env），值永遠不進任何檔案。

需求：cloud 模式、gcloud 以專案擁有者登入、config/kit.json 裡 headless.enabled = true。
完整說明（含 LINE 官方帳號怎麼開、Blaze 方案、隱私）：docs/HEADLESS.md
"""
import os
import re
import sys
import json
import time
import argparse
import subprocess
import urllib.parse
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib
import hostos

EVENTS = "headless_events"
PAIRING = "headless_pairing"
META = "meta/headless"
AUDIT = "headless-audit.jsonl"
SCRIPT = "AGENTS-HEADLESS.md"
REPORT_BEGIN = "<<REPORT>>"
REPORT_END = "<<END>>"
REPORT_MAX = 300                     # 字：推回手機的那段話上限（LINE 一則最多 5000，但手機上看不完）
STATUSES = ("pending", "processing", "done", "failed")
LINE_PUSH = "https://api.line.me/v2/bot/message/push"
LINE_CONTENT = "https://api-data.line.me/v2/bot/message/%s/content"
GCS_MEDIA = "https://storage.googleapis.com/storage/v1/b/%s/o/%s?alt=media"


# ── 小工具 ──────────────────────────────────────────────────────────────
def audit(entry):
    """data/headless-audit.jsonl 追加一行（data/ 整個被 .gitignore 擋住）。"""
    d = lib.data_dir()
    os.makedirs(d, exist_ok=True)
    entry = dict(entry)
    entry.setdefault("at", lib.now_iso())
    with open(os.path.join(d, AUDIT), "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def need_headless(kit):
    """沒開就把話講清楚再退出（退出碼 0：排程叫到它不該算失敗）。"""
    if lib.is_local(kit):
        print("本機模式沒有雲端可以收件，無頭交辦不適用。")
        print("  要用的話：把 config/kit.json 的 mode 改成 cloud，重跑 `%s scripts/setup.py`。" % lib.PY)
        sys.exit(0)
    h = lib.headless_cfg(kit)
    if not h["enabled"]:
        print("無頭交辦沒有開（config/kit.json 的 headless.enabled 是 false）。")
        print("  要開：重跑 `%s scripts/setup.py`，在「無頭交辦」那一題說要；說明見 docs/HEADLESS.md。" % lib.PY)
        sys.exit(0)
    return h


def env_token(h, which, required=True):
    """從環境變數拿 LINE 的金鑰。名字在設定裡，值永遠不在任何檔案裡。"""
    name = h["line"]["%s_env" % which]
    val = (os.environ.get(name) or "").strip()
    if not val and required:
        lib.die("環境變數 %s 是空的（LINE 的%s）。" % (name, "頻道密鑰" if which == "channel_secret" else "存取權杖"),
                "到 LINE Developers → 你的 Messaging API 頻道拿，再在終端機設起來"
                "（bash／zsh：`export %s='那串值'`；PowerShell：`$env:%s = '那串值'`）。"
                "排程要跑得到的話請寫進你的 shell 設定檔。細節見 docs/HEADLESS.md。" % (name, name))
    return val


def http_json(url, method="GET", token=None, body=None, timeout=60, raw=False):
    """一支簡單的 HTTP：回 (status, bytes 或 dict)。連不上丟 OSError。"""
    data = json.dumps(body).encode() if body is not None else None
    headers = {}
    if token:
        headers["Authorization"] = "Bearer " + token
    if data is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = r.read()
            if raw:
                return r.status, payload
            return r.status, json.loads(payload.decode() or "{}")
    except urllib.error.HTTPError as e:
        return e.code, e.read()[:400] if raw else e.read().decode("utf-8", "ignore")[:400]


# ── 雲端：搶件、配對、狀態 ──────────────────────────────────────────────
def list_events(base, tok):
    """headless_events 全部，最舊的排前面。"""
    rows = lib.list_docs(base, EVENTS, tok, raise_errors=True)
    return sorted(rows, key=lambda r: (r[1].get("receivedAt") or "", r[0]))


def claim(base, tok, eid, update_time, dry):
    """把一則從 pending 改成 processing。帶 updateTime 前置條件：
    另一台電腦（或上一輪還沒結束的自己）先搶到的話這裡會丟 Precondition，我們就跳過。"""
    if dry:
        return True
    try:
        lib.http("PATCH", base, "%s/%s" % (EVENTS, eid), tok,
                 {"status": "processing", "claimedAt": lib.now_iso(),
                  "claimedBy": hostos.OS + ":" + str(os.getpid())},
                 mask=["status", "claimedAt", "claimedBy"],
                 precondition_update_time=update_time, raise_errors=True)
        return True
    except lib.Precondition:
        return False


def finish(base, tok, eid, status, note="", dry=False):
    if dry:
        return
    fields = {"status": status, "finishedAt": lib.now_iso(), "note": note[:900]}
    lib.http("PATCH", base, "%s/%s" % (EVENTS, eid), tok, fields, mask=list(fields))


def ensure_pairing_doc(base, tok, h, dry, quiet=True):
    """把配對碼寫上 meta/headless——relay 只認那一份文件。

    配對碼是老師填進 config/kit.json 的，relay 在雲端讀不到本機的設定檔，
    所以由這一支負責把它送上去。每次 --once 都確認一次，改了就會自己收斂。
    """
    want = h["line"]["owner_user_id"]
    if not want or dry:
        return
    cur, _ = lib.get_doc(base, META, tok)
    if (cur or {}).get("ownerUserId") == want:
        return
    lib.http("PATCH", base, META, tok,
             {"ownerUserId": want, "enabled": True, "updatedAt": lib.now_iso()},
             mask=["ownerUserId", "enabled", "updatedAt"])
    if not quiet:
        lib.ok("配對碼已寫上雲端（meta/headless）——relay 從現在起只收這個人的訊息。")


# ── 音檔 ────────────────────────────────────────────────────────────────
def fetch_audio(kit, h, fs, tok, dest):
    """把語音訊息的音檔弄到 dest。先試 Storage（relay 存的），不行就直接跟 LINE 要。

    為什麼要有第二條路：relay 只有 1.2 秒可以用（LINE 逾時 2 秒），大一點的錄音
    來不及傳完就會被凍住。那種情況文件上會留 audioPending，這裡自己補抓。
    """
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    path = (fs.get("storagePath") or "").strip()
    errors = []
    if path:
        url = GCS_MEDIA % (urllib.parse.quote(lib.storage_bucket(kit), safe=""),
                           urllib.parse.quote(path, safe=""))
        try:
            code, payload = http_json(url, token=tok, timeout=300, raw=True)
            if code == 200 and payload:
                with open(dest, "wb") as f:
                    f.write(payload)
                return dest, "storage"
            errors.append("Storage HTTP %s" % code)
        except OSError as e:
            errors.append("Storage %s" % e)
    mid = (fs.get("messageId") or "").strip()
    ltok = env_token(h, "channel_token", required=False)
    if mid and ltok:
        try:
            code, payload = http_json(LINE_CONTENT % urllib.parse.quote(mid), token=ltok,
                                      timeout=300, raw=True)
            if code == 200 and payload:
                with open(dest, "wb") as f:
                    f.write(payload)
                return dest, "line"
            errors.append("LINE content HTTP %s" % code)
        except OSError as e:
            errors.append("LINE content %s" % e)
    elif not ltok:
        errors.append("環境變數 %s 沒設，無法直接跟 LINE 要音檔" % h["line"]["channel_token_env"])
    raise RuntimeError("音檔拿不到（%s）"
                       % ("；".join(errors) or "這一則既沒有 storagePath 也沒有 messageId"))


def transcribe(path, quiet=False):
    """跑 transcribe.py，回逐字稿檔的路徑。"""
    out = lib.rpath("inbox", "transcripts",
                    os.path.splitext(os.path.basename(path))[0] + ".md")
    cmd = [sys.executable, os.path.join(lib.PKG, "scripts", "transcribe.py"),
           path, "--root", lib.root()]
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=7200)
    if not os.path.exists(out):
        tail = "\n".join(((r.stdout or "") + (r.stderr or "")).strip().splitlines()[-4:])
        raise RuntimeError("轉逐字稿失敗（transcribe.py 回傳 %s）：%s" % (r.returncode, tail))
    if not quiet and r.returncode != 0:
        lib.warn("transcribe.py 回傳 %s，但逐字稿有產生出來，繼續。" % r.returncode)
    with open(out, encoding="utf-8", errors="replace") as f:
        return out, f.read()


# ── 叫 AI 代理 ──────────────────────────────────────────────────────────
def build_prompt(kit, fs, text, source_note):
    """照 AGENTS-HEADLESS.md 組一段提示詞。老師改了那個檔，下一則交辦就照新的做。"""
    spath = lib.pkg_path(SCRIPT)
    if not os.path.exists(spath):
        raise RuntimeError("找不到 %s（無頭交辦的作業指示）——重新下載一份 kit。" % SCRIPT)
    with open(spath, encoding="utf-8") as f:
        script = f.read()
    mode_line = ("寫完要跑 `python3 scripts/sync.py --quiet` 同步到雲端。"
                 if not lib.is_local(kit) else "這台是本機模式，不需要同步。")
    return (
        "你正在無頭（非互動）模式下替一位老師整理一則紀錄。工作目錄就是這份 kit 的根目錄。\n"
        "沒有人在電腦前面，你問任何問題都不會有人回答。%s\n\n"
        "以下是你要遵守的作業指示（正本＝%s）：\n"
        "════════════════════════════════════════\n%s\n"
        "════════════════════════════════════════\n\n"
        "這一則交辦的來源：%s（收件時間 %s）\n"
        "內容：\n"
        "────────────────────────────────────────\n%s\n"
        "────────────────────────────────────────\n\n"
        "現在請照上面的步驟做完，最後一定要印出 %s … %s 之間的回報。"
        % (mode_line, SCRIPT, script, source_note, fs.get("receivedAt") or "?",
           text.strip(), REPORT_BEGIN, REPORT_END))


def agent_argv(agent, prompt):
    """要跑的 argv。測試與演練用 TRK_HEADLESS_AGENT_CMD 換成一支假的，永遠不會叫到真的 AI。"""
    stub = (os.environ.get("TRK_HEADLESS_AGENT_CMD") or "").strip()
    if stub:
        return [stub, prompt]
    argv = hostos.agent_headless_argv(agent, prompt)
    if not argv:
        raise RuntimeError("不認得的 AI 代理：%r（只支援 %s）"
                           % (agent, "、".join(hostos.AGENT_ORDER)))
    path = hostos.exe(argv[0])
    if not path:
        raise RuntimeError("這台電腦上找不到 %s。%s"
                           % (argv[0], hostos.agent_install_hint(agent)))
    return [path] + argv[1:]


def run_agent(argv, timeout):
    """跑代理，逾時就把整棵行程樹殺掉。回 (returncode, 輸出)。

    start_new_session／CREATE_NEW_PROCESS_GROUP 是為了 kill_tree：
    代理自己會開一堆子行程（node、python、ripgrep…），只殺父行程的話
    那些孫子會抱著逐字稿繼續跑，下一輪排程醒來就有兩隻在同一個檔上打架。
    """
    kw = {}
    if hostos.OS == "win":
        kw["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kw["start_new_session"] = True
    # 子行程的主控台在 Windows 上預設是 cp1252／cp950，代理印回報裡的中文會直接 UnicodeEncodeError；
    # 逼它用 UTF-8（Python 子行程認 PYTHONIOENCODING／PYTHONUTF8，node 本來就是 UTF-8）。
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    # 代理照 AGENTS-HEADLESS.md 會自己跑一次 sync.py——那一次不准再叫另一支 AI 補評量維度標
    # （AI 叫 AI 會把這則交辦拖過逾時；補標留給排程的一般同步做）。見 scripts/auto_dim_tags.py。
    env["TRK_NO_AUTO_TAGS"] = "1"
    p = subprocess.Popen(argv, cwd=lib.PKG, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, env=env, **kw)
    try:
        out, _ = p.communicate(timeout=timeout)
        return p.returncode, (out or b"").decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        hostos.kill_tree(p)
        try:
            out, _ = p.communicate(timeout=10)
        except Exception:
            out = b""
        return 124, (out or b"").decode("utf-8", "replace")


def extract_report(text):
    """挑出 <<REPORT>> … <<END>> 之間那段（有好幾段就用最後一段）。找不到回 ""。"""
    hits = re.findall(re.escape(REPORT_BEGIN) + r"(.*?)" + re.escape(REPORT_END), text or "",
                      re.S)
    if not hits:
        return ""
    body = " ".join(hits[-1].split())
    return body[:REPORT_MAX]


# ── 推回手機 ────────────────────────────────────────────────────────────
def push(h, text, dry=False, quiet=False):
    """LINE 推播一則文字。回 (成功, 說明)。

    免費方案每個帳號每月 200 則推播，所以**一則交辦只推一次**（不推進度、不推開始了）。
    推不出去不算整件事失敗：紀錄已經寫好了，老師打開電腦就看得到。
    """
    to = h["line"]["owner_user_id"]
    tok = env_token(h, "channel_token", required=False)
    if dry:
        return True, "（預演，沒有真的推播）"
    if not to:
        return False, "還沒配對（headless.line.owner_user_id 是空的）"
    if not tok:
        return False, "環境變數 %s 沒設" % h["line"]["channel_token_env"]
    try:
        code, resp = http_json(LINE_PUSH, method="POST", token=tok,
                               body={"to": to, "messages": [{"type": "text", "text": text[:4900]}]},
                               timeout=30)
    except OSError as e:
        return False, "連不上 LINE：%s" % e
    if code == 200:
        return True, ""
    if code == 429:
        return False, "LINE 推播額度用完了（免費方案每月 200 則）"
    return False, "LINE 推播 HTTP %s %s" % (code, resp if isinstance(resp, str) else "")


# ── 一則的完整流程 ──────────────────────────────────────────────────────
def process(kit, h, base, tok, eid, fs, dry, quiet):
    """回 (成功, 報告或錯誤訊息)。到這裡為止這一則已經是 processing 了。"""
    kind = (fs.get("type") or "text").strip()
    audio_path = ""
    if kind == "audio":
        mid = (fs.get("messageId") or eid).strip()
        dest = lib.rpath("inbox", "line-%s.m4a" % re.sub(r"[^A-Za-z0-9_-]", "-", mid))
        if dry:
            text, source_note = "（預演：不抓音檔、不轉逐字稿）", "LINE 語音訊息"
        else:
            audio_path, how = fetch_audio(kit, h, fs, tok, dest)
            if not quiet:
                lib.ok("音檔：%s（來自 %s）" % (os.path.relpath(audio_path, lib.root()), how))
            tpath, text = transcribe(audio_path, quiet)
            source_note = "LINE 語音訊息（本機 whisper.cpp 逐字稿：%s）" % os.path.relpath(tpath, lib.root())
    else:
        text = (fs.get("text") or "").strip()
        source_note = "LINE 文字訊息"
        if not text:
            raise RuntimeError("這一則沒有內容（既不是語音也沒有文字）。")

    prompt = build_prompt(kit, fs, text, source_note)
    argv = agent_argv(h["agent"], prompt)
    if dry:
        print("  會叫：%s …（提示詞 %d 字）" % (os.path.basename(argv[0]), len(prompt)))
        return True, "（預演）"
    t0 = time.time()
    rc, out = run_agent(argv, h["timeout_sec"])
    took = int(time.time() - t0)
    report = extract_report(out)
    if rc == 124:
        raise RuntimeError("AI 代理跑超過 %d 秒被中止（已連同子行程一起殺掉）。"
                           "紀錄可能寫了一半，請打開電腦看一下 data/ 再決定要不要 --retry。"
                           % h["timeout_sec"])
    if rc != 0 and not report:
        tail = "\n".join((out or "").strip().splitlines()[-6:])
        raise RuntimeError("AI 代理回傳 %s，而且沒有印出回報。最後幾行：%s" % (rc, tail))
    if not report:
        raise RuntimeError("AI 代理沒有印出 %s … %s 的回報（跑了 %d 秒）——"
                           "無法確定它到底有沒有寫進去，先不當成功。" % (REPORT_BEGIN, REPORT_END, took))
    if not quiet:
        lib.ok("代理跑完（%d 秒）：%s" % (took, report))
    return True, report


def once(kit, h, dry, quiet):
    base = lib.fb_base(kit)
    tok = lib.token()
    ensure_pairing_doc(base, tok, h, dry, quiet)
    rows = [r for r in list_events(base, tok) if (r[1].get("status") or "pending") == "pending"]
    if not rows:
        if not quiet:
            print("沒有待處理的交辦。")
        return 0
    if not quiet:
        print("待處理 %d 則%s" % (len(rows), "（預演）" if dry else ""))
    fails = 0
    for eid, fs, up in rows:
        head = "%s %s" % (fs.get("receivedAt") or "?", "語音" if fs.get("type") == "audio" else "文字")
        if not quiet:
            print("\n── %s　%s ──" % (eid, head))
        if not claim(base, tok, eid, up, dry):
            if not quiet:
                lib.warn("這一則已經被別的行程接走了，跳過。")
            continue
        try:
            ok, report = process(kit, h, base, tok, eid, fs, dry, quiet)
        except Exception as e:                      # noqa: BLE001 一則壞掉不能拖垮整輪
            msg = str(e)[:900]
            fails += 1
            lib.err("這一則失敗了：%s" % msg,
                    "修好之後跑 `%s scripts/headless.py --retry %s` 重新排回待辦。" % (lib.PY, eid))
            finish(base, tok, eid, "failed", msg, dry)
            audit({"event": eid, "status": "failed", "type": fs.get("type"), "error": msg})
            # 失敗也要讓老師在手機上看得到——不然他只會覺得「我講了但什麼都沒發生」
            push(h, "這一則沒處理成功：%s\n（電腦上跑 headless.py --status 看詳情）" % msg[:200],
                 dry, quiet)
            continue
        sent, why = push(h, report, dry, quiet)
        if not sent and not quiet:
            lib.warn("紀錄寫好了，但推播沒送出去（%s）。" % why)
        finish(base, tok, eid, "done", report, dry)
        audit({"event": eid, "status": "done", "type": fs.get("type"),
               "report": report, "pushed": sent, "pushNote": why})
    return 1 if fails else 0


# ── --status／--pair／--retry ───────────────────────────────────────────
def status(kit, h, as_json):
    base = lib.fb_base(kit)
    tok = lib.token()
    rows = list_events(base, tok)
    counts = {s: 0 for s in STATUSES}
    failed = []
    for eid, fs, _ in rows:
        s = (fs.get("status") or "pending")
        counts[s] = counts.get(s, 0) + 1
        if s == "failed":
            failed.append({"id": eid, "at": fs.get("receivedAt", ""), "type": fs.get("type", ""),
                           "note": fs.get("note", "")})
    paired = bool(h["line"]["owner_user_id"])
    cloud, _ = lib.get_doc(base, META, tok)
    if as_json:
        print(json.dumps({"enabled": True, "tool": h["tool"], "agent": h["agent"],
                          "paired": paired, "cloudOwnerUserId": bool((cloud or {}).get("ownerUserId")),
                          "counts": counts, "failed": failed}, ensure_ascii=False, indent=2))
        return 1 if counts.get("failed") else 0
    print("無頭交辦（%s → %s）" % (h["tool"], h["agent"] or "（還沒選代理）"))
    print("  配對：%s；雲端 meta/headless：%s"
          % ("好了" if paired else "還沒（跑 --pair）",
             "已寫入" if (cloud or {}).get("ownerUserId") else "還沒寫（跑一次 --once）"))
    print("  待處理 %d、處理中 %d、完成 %d、失敗 %d"
          % (counts.get("pending", 0), counts.get("processing", 0),
             counts.get("done", 0), counts.get("failed", 0)))
    for f in failed[:20]:
        print("  ✗ %s　%s　%s" % (f["id"], f["at"], (f["note"] or "")[:80]))
    if failed:
        print("\n修好之後：`%s scripts/headless.py --retry <上面那個 id>`（不會自動重試，"
              "那樣同一段話可能被寫成好幾則）。" % lib.PY)
    return 1 if failed else 0


def pair(kit, h):
    """印出配對碼。relay 在還沒配對的時候會把每一個傳訊息的人記進 headless_pairing。"""
    if h["line"]["owner_user_id"]:
        print("已經配對過了：%s" % h["line"]["owner_user_id"])
        print("  要換人（換手機帳號）：改 config/kit.json 的 headless.line.owner_user_id，"
              "再跑 `%s scripts/build_config.py` 與一次 `%s scripts/headless.py --once`。"
              % (lib.PY, lib.PY))
        return 0
    base = lib.fb_base(kit)
    tok = lib.token()
    rows = lib.list_docs(base, PAIRING, tok, raise_errors=True)
    rows.sort(key=lambda r: r[1].get("seenAt") or "", reverse=True)
    if not rows:
        print("雲端還沒看到任何人傳訊息過來。")
        print("  拿配對碼的方法：用手機把你的 LINE 官方帳號加為好友，隨便傳一句「哈囉」給它。")
        print("  它會回你一行「配對碼：Uxxxxxxxx…」。那串就是配對碼。")
        print("  （回不了的話多半是 webhook 網址還沒填進 LINE Developers，見 docs/HEADLESS.md。）")
        return 1
    print("最近傳訊息過來的 LINE userId（最上面那個多半就是你）：")
    for eid, fs, _ in rows[:5]:
        print("  %s　（%s）" % (fs.get("userId") or eid, fs.get("seenAt") or "?"))
    print("\n把它填進 config/kit.json 的 headless.line.owner_user_id，或重跑 "
          "`%s scripts/setup.py` 在那一題貼上去；" % lib.PY)
    print("然後 `%s scripts/build_config.py`，再跑一次 `%s scripts/headless.py --once` "
          "把配對碼送上雲端。" % (lib.PY, lib.PY))
    return 0


def retry(kit, eid):
    base = lib.fb_base(kit)
    tok = lib.token()
    fs, _ = lib.get_doc(base, "%s/%s" % (EVENTS, eid), tok)
    if not fs:
        lib.die("雲端沒有這一則交辦：%s" % eid,
                "跑 `%s scripts/headless.py --status` 看有哪些 id。" % lib.PY)
    lib.http("PATCH", base, "%s/%s" % (EVENTS, eid), tok,
             {"status": "pending", "note": "", "retriedAt": lib.now_iso()},
             mask=["status", "note", "retriedAt"])
    audit({"event": eid, "status": "requeued"})
    lib.ok("%s 排回待辦了（原本是 %s）。下一次 `--once` 會處理它。"
           % (eid, fs.get("status") or "?"))
    return 0


def main():
    ap = argparse.ArgumentParser(
        description="無頭交辦：把 LINE 收到的語音／文字變成一則紀錄",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="完整說明：docs/HEADLESS.md")
    ap.add_argument("--once", action="store_true", help="處理完待辦就結束（排程跑的就是這個）")
    ap.add_argument("--dry-run", action="store_true", help="只印會做什麼，不改雲端、不叫代理、不推播")
    ap.add_argument("--status", action="store_true", dest="as_status", help="看待辦／失敗清單")
    ap.add_argument("--pair", action="store_true", help="印出配對碼（LINE userId）")
    ap.add_argument("--retry", metavar="事件id", default="", help="把一則失敗的重新排回待辦")
    ap.add_argument("--json", action="store_true", dest="as_json", help="--status 輸出 JSON")
    ap.add_argument("--quiet", action="store_true", help="沒事就不出聲（排程用）")
    lib.add_root_arg(ap)
    a = ap.parse_args()
    lib.apply_root(a)

    kit = lib.load_kit()
    h = need_headless(kit)

    if a.retry:
        sys.exit(retry(kit, a.retry))
    if a.pair:
        sys.exit(pair(kit, h))
    if a.as_status:
        sys.exit(status(kit, h, a.as_json))
    if not a.once:
        ap.print_help()
        sys.exit(2)
    sys.exit(once(kit, h, a.dry_run, a.quiet))


if __name__ == "__main__":
    main()
