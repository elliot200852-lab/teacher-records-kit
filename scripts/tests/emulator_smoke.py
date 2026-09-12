#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""emulator_smoke.py — 對「真的 Firestore 引擎」跑一遍連網路徑（本機模擬器；不碰任何雲端專案）。

為什麼有這支：sync／backup／ledger／doctor 的連網那一半，unittest 用假物件測不到；
這支在 Firestore 模擬器上把老師會走到的路真的走一次——推上去、網頁改了拉回來、兩邊都改要報衝突、
網頁刪了本機跟著刪並留稽核、備份 zip、三處對帳、健檢讀得到雲端版本，最後還驗安全規則本身
（擁有者讀得到、陌生人與未登入被擋、少了 stream 的紀錄建不進去）。

跑法（要有 Java 與 firebase-tools；cwd 隨便）：
  python3 scripts/tests/emulator_smoke.py
它自己會呼叫 `firebase emulators:exec`；被 emulators:exec 叫起來的那一層（環境變數 FIRESTORE_EMULATOR_HOST 已設）
才真的跑步驟。CI 的 emulator 那個 job 跑的就是這支。
"""
import io
import os
import sys
import json
import time
import base64
import shutil
import zipfile
import tempfile
import subprocess
import urllib.request
import urllib.error

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.dirname(SCRIPTS)
sys.path.insert(0, SCRIPTS)
import lib          # noqa: E402
import hostos       # noqa: E402

PROJECT = "demo-trk-smoke"          # demo- 開頭＝模擬器專用，firebase 不會去碰雲端
OWNER = "owner@example.com"
FAILS = []


def step(name, ok, detail=""):
    print("%s %s%s" % ("✓" if ok else "✗", name, ("　" + detail) if detail else ""))
    if not ok:
        FAILS.append(name)


def py(script, *args, root=None, expect=0, env=None):
    cmd = [sys.executable, os.path.join(SCRIPTS, script), *args]
    if root:
        cmd += ["--root", root]
    e = dict(os.environ)
    e.update(env or {})
    r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                       timeout=600, env=e)
    out = (r.stdout or "") + (r.stderr or "")
    if expect is not None and r.returncode != expect:
        print(out[-2000:])
    return r.returncode, out


def rest(method, kit, path, body=None, params=None, tok="owner", raise_errors=True):
    return lib.http(method, lib.fb_base(kit), path, tok, body=body, params=params, raise_errors=raise_errors)


def raw_get(kit, path, tok=None):
    """不經 lib、直接打 REST，拿 HTTP 狀態碼（驗規則用）。"""
    url = lib.fb_base(kit) + "/" + path
    headers = {"Authorization": "Bearer " + tok} if tok else {}
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def raw_post(kit, collection, doc_id, fields, tok):
    url = "%s/%s?documentId=%s" % (lib.fb_base(kit), collection, doc_id)
    data = json.dumps(lib.fs_doc(fields)).encode()
    req = urllib.request.Request(url, data=data, method="POST",
                                 headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def fake_jwt(email=None):
    """模擬器接受未簽章的 JWT（alg none），拿它來當「某個 Google 登入的人」驗規則。"""
    now = int(time.time())
    payload = {"sub": "uid-" + (email or "anon"), "user_id": "uid-" + (email or "anon"),
               "aud": PROJECT, "iss": "https://securetoken.google.com/" + PROJECT,
               "iat": now, "exp": now + 3600, "auth_time": now,
               "firebase": {"sign_in_provider": "google.com", "identities": {}}}
    if email:
        payload.update({"email": email, "email_verified": True})

    def b64(o):
        return base64.urlsafe_b64encode(json.dumps(o, separators=(",", ":")).encode()).rstrip(b"=").decode()
    return "%s.%s." % (b64({"alg": "none", "typ": "JWT"}), b64(payload))


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


FAKE_AGENT = r'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""假的 AI 代理：無頭交辦的測試絕對不會叫到真的模型。

它做的事跟真代理該做的一樣——走唯一寫入通道記一則，然後印回報——
只是判斷是寫死的。headless.py 看到的介面（argv、cwd、退出碼、<<REPORT>> 區塊）完全一樣。
"""
import os
import sys
import subprocess

prompt = sys.argv[1] if len(sys.argv) > 1 else ""
root = os.environ["TRK_ROOT"]
scripts = os.path.join(os.environ["TRK_PKG"], "scripts")

# 提示詞裡「內容：」後面夾在兩條分隔線之間的就是逐字稿／文字（真代理是讀懂之後改寫）
body = "（假代理沒讀到內容）"
if "內容：" in prompt:
    tail = prompt.split("內容：", 1)[1].splitlines()
    got = []
    for line in tail[2:]:                 # tail[0] 是空的、tail[1] 是上面那條分隔線
        if line.startswith("\u2500"):
            break
        got.append(line)
    if "".join(got).strip():
        body = "\n".join(got).strip()

draft = os.path.join(root, "fake-agent-draft.md")
with open(draft, "w", encoding="utf-8", newline="\n") as f:
    f.write(body + "\n")
r = subprocess.run([sys.executable, os.path.join(scripts, "append_record.py"),
                    "--kind", "students", "--target", "S-01", "--stream", "homeroom",
                    "--content-file", draft, "--source", "voice", "--root", root],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
if r.returncode != 0:
    print(r.stdout + r.stderr)
    print("<<REPORT>>沒有寫入：append_record 回傳 %d<<END>>" % r.returncode)
    sys.exit(1)
print("<<REPORT>>已記到 S-01 的導師班級紀錄：%s<<END>>" % body[:40])
'''


def headless_steps(root, kit, base):
    """無頭交辦的電腦端：假造一則 headless_events，讓 headless.py 真的處理一輪。

    雲端那一半（Cloud Function）不在這裡驗——模擬器只跑 Firestore。
    這裡驗的是**交給老師電腦之後**的每一件事：搶件的前置條件、叫代理、回報、標 done、稽核。
    """
    print("\n── 無頭交辦 ──")
    kit_path = os.path.join(root, "config", "kit.json")
    with open(kit_path, encoding="utf-8") as f:
        k = json.load(f)
    k["headless"] = {"enabled": True, "tool": "line", "agent": "claude", "timeout_sec": 300,
                     "line": {"channel_secret_env": "KIT_LINE_CHANNEL_SECRET",
                              "channel_token_env": "KIT_LINE_CHANNEL_TOKEN",
                              "owner_user_id": "Utest0000"}}
    write(kit_path, json.dumps(k, ensure_ascii=False, indent=1))
    rc, out = py("build_config.py", "--allow-placeholders", root=root)
    step("開了無頭交辦之後 build_config 仍然過", rc == 0, out.strip().splitlines()[-1] if rc else "")
    rules = read(os.path.join(root, "storage.rules"))
    step("storage.rules 長出收件匣那一條", "match /headless-inbox/{file}" in rules)

    agent = os.path.join(root, "fake-agent.py")
    write(agent, FAKE_AGENT)
    os.chmod(agent, 0o755)
    env = {"TRK_HEADLESS_AGENT_CMD": agent, "TRK_ROOT": root, "TRK_PKG": PKG}

    # 一則文字交辦（語音那一條路要 Storage 與 whisper，不在模擬器裡驗）
    eid = "evt-smoke-1"
    lib.http("PATCH", base, "headless_events/%s" % eid, "owner",
             {"type": "text", "text": "今天午休 S-01 主動幫忙排椅子。", "messageId": "m1",
              "userId": "Utest0000", "receivedAt": "2026-09-12T10:00:00", "status": "pending",
              "storagePath": "", "audioPending": False, "error": ""},
             precondition_exists=False)

    rc, out = py("headless.py", "--once", "--dry-run", root=root, env=env)
    step("headless --dry-run 不改任何東西", rc == 0 and "預演" in out,
         out.strip().splitlines()[-1] if out.strip() else "")
    fs, _ = lib.get_doc(base, "headless_events/%s" % eid, "owner", raise_errors=True)
    step("預演之後那一則還是 pending", fs.get("status") == "pending", str(fs.get("status")))

    rc, out = py("headless.py", "--once", root=root, env=env)
    step("headless --once 跑完", rc == 0, out.strip().splitlines()[-1] if out.strip() else "")
    fs, _ = lib.get_doc(base, "headless_events/%s" % eid, "owner", raise_errors=True)
    step("那一則標成 done 並帶回報", fs.get("status") == "done" and "S-01" in (fs.get("note") or ""),
         "%s／%s" % (fs.get("status"), (fs.get("note") or "")[:40]))
    md = read(os.path.join(root, "data", "students", "S-01", "observations.md"))
    step("紀錄真的寫進本機檔（走 append_record.py）", "主動幫忙排椅子" in md)
    meta, _ = lib.get_doc(base, "meta/headless", "owner", raise_errors=True)
    step("配對碼寫上 meta/headless（relay 讀的是這一份）",
         (meta or {}).get("ownerUserId") == "Utest0000", str((meta or {}).get("ownerUserId")))
    audit = read(os.path.join(root, "data", "headless-audit.jsonl"))
    step("稽核留了一行", eid in audit and '"status": "done"' in audit)

    rc, out = py("headless.py", "--once", root=root, env=env)
    step("第二輪沒事做（done 的不會再處理一次）", rc == 0 and "沒有待處理" in out)

    rc, out = py("headless.py", "--status", "--json", root=root, env=env, expect=None)
    data = json.loads(out[out.index("{"):])
    step("--status 數得出來", data["counts"]["done"] == 1 and data["paired"] is True,
         json.dumps(data["counts"], ensure_ascii=False))

    # 失敗的那一條路：代理不印回報 → 標 failed、不重試；--retry 才排回待辦
    write(agent, "#!/usr/bin/env python3\nprint('我什麼都沒做')\n")
    os.chmod(agent, 0o755)
    eid2 = "evt-smoke-2"
    lib.http("PATCH", base, "headless_events/%s" % eid2, "owner",
             {"type": "text", "text": "第二則", "messageId": "m2", "userId": "Utest0000",
              "receivedAt": "2026-09-12T11:00:00", "status": "pending", "storagePath": "",
              "audioPending": False, "error": ""}, precondition_exists=False)
    rc, out = py("headless.py", "--once", root=root, env=env, expect=None)
    fs2, _ = lib.get_doc(base, "headless_events/%s" % eid2, "owner", raise_errors=True)
    step("代理沒印回報 → 標 failed（不當成功）", rc == 1 and fs2.get("status") == "failed",
         "%s／%s" % (rc, fs2.get("status")))
    rc, out = py("headless.py", "--retry", eid2, root=root, env=env)
    fs2, _ = lib.get_doc(base, "headless_events/%s" % eid2, "owner", raise_errors=True)
    step("--retry 把它排回待辦", rc == 0 and fs2.get("status") == "pending", str(fs2.get("status")))

    # 規則：無頭交辦的事件與配對紀錄一樣只有擁有者讀得到
    owner_tok, stranger_tok = fake_jwt(OWNER), fake_jwt("stranger@example.com")
    step("規則：擁有者讀得到 headless_events",
         raw_get(kit, "headless_events/%s" % eid, owner_tok) == 200)
    step("規則：陌生人讀不到 headless_events（403）",
         raw_get(kit, "headless_events/%s" % eid, stranger_tok) == 403)
    step("規則：未登入讀不到 headless_events（403）",
         raw_get(kit, "headless_events/%s" % eid) == 403)


# ── 被 emulators:exec 叫起來的那一層 ───────────────────────────────────────────
def inner(root):
    lib.set_root(root)
    kit = lib.load_kit()
    base = lib.fb_base(kit)
    print("模擬器：%s\n" % base)

    # 1. 名冊填真名（唯一有真名的檔）
    lib.save_roster_rows({"S-01": {"name": "王小明", "streams": []},
                          "S-02": {"name": "李小華", "streams": ["case"]},
                          "S-03": {"name": "張小美", "streams": []}}, lib.data_dir())
    # 2. 走唯一寫入通道記三則
    draft = os.path.join(root, "draft.md")
    write(draft, "今天在主課程時主動幫同學撿起掉落的蠟筆。\n")
    rc, out = py("append_record.py", "--kind", "students", "--target", "S-01", "--stream", "homeroom",
                 "--date", "2026-09-01", "--tags", "#人際", "--content-file", draft, "--source", "file", root=root)
    step("append S-01 homeroom", rc == 0, out.strip().splitlines()[-1] if rc else "")
    write(draft, "第一次晤談，來源為導師轉介。\n")
    rc, out = py("append_record.py", "--kind", "students", "--target", "S-02", "--stream", "case",
                 "--date", "2026-09-02", "--fields-json", '{"來源":"導師轉介"}', "--content-file", draft, "--source", "file", root=root)
    step("append S-02 case", rc == 0)
    # 同一位學生、同一天、另一種記錄類型：兩種類型共用 students/S-02/records，
    # 取號沒看兄弟檔的話兩邊都會是 2026-09-02，第二則推上去就撞 ALREADY_EXISTS。
    write(draft, "同一天的班級紀錄，跟上面那則個案紀錄共用同一個雲端集合。\n")
    rc, out = py("append_record.py", "--kind", "students", "--target", "S-02", "--stream", "homeroom",
                 "--date", "2026-09-02", "--content-file", draft, "--source", "file", "--json", root=root)
    sib_rid = json.loads(out.strip().splitlines()[-1])["rid"] if rc == 0 else ""
    step("append S-02 homeroom（同日不撞紀錄 id）", rc == 0 and sib_rid.startswith("2026-09-02-"), sib_rid)
    write(draft, "公文：校外教學申請已送出。\n")
    rc, out = py("append_record.py", "--kind", "business", "--target", "homeroom",
                 "--date", "2026-09-03", "--content-file", draft, "--source", "file", root=root)
    step("append business homeroom", rc == 0)
    write(draft, "這一則提到王小明的真名，應該被擋。\n")
    rc, out = py("append_record.py", "--kind", "students", "--target", "S-03", "--stream", "homeroom",
                 "--date", "2026-09-04", "--content-file", draft, "--source", "file", root=root, expect=5)
    step("真名閘：退出碼 5", rc == 5)

    # 3. 同步：先 dry-run 再真跑
    rc, out = py("sync.py", "--dry-run", root=root)
    step("sync --dry-run", rc == 0 and "上傳" in out)
    rc, out = py("sync.py", root=root)
    step("sync 真跑", rc == 0, out.strip().splitlines()[0] if out.strip() else "")
    docs = lib.list_docs(base, "students/S-01/records", "owner", raise_errors=True)
    step("雲端有 S-01 的紀錄", len(docs) == 1 and docs[0][1].get("stream") == "homeroom"
         and docs[0][1].get("sourceFile") == "students/S-01/observations.md",
         json.dumps({k: docs[0][1].get(k) for k in ("stream", "sourceFile", "date")}, ensure_ascii=False) if docs else "空")
    s2 = lib.list_docs(base, "students/S-02/records", "owner", raise_errors=True)
    step("同一位學生兩種類型各自成一份文件（沒撞 id）",
         len(s2) == 2 and {f.get("stream") for _, f, _ in s2} == {"case", "homeroom"},
         "、".join("%s/%s" % (rid, f.get("stream")) for rid, f, _ in s2))
    card, _ = lib.get_doc(base, "students/S-02", "owner", raise_errors=True)
    step("第一次同步就把卡片的 IEP 目標推上去", len(card.get("goals") or []) == 2,
         "goals=%d" % len(card.get("goals") or []))
    cfg, _ = lib.get_doc(base, "meta/config", "owner", raise_errors=True)
    step("meta/config.version 寫上去了", cfg.get("version") == lib.version(), str(cfg.get("version")))
    st, _ = lib.get_doc(base, "meta/status", "owner", raise_errors=True)
    step("meta/status.lastSyncAt", bool(st.get("lastSyncAt")))
    step("meta/status 帶衝突／真名／錯誤三個欄位",
         st.get("lastSyncConflicts") == 0 and st.get("lastSyncPii") == 0
         and st.get("lastError") == "",
         json.dumps({k: st.get(k) for k in ("lastSyncConflicts", "lastSyncPii", "lastError")},
                    ensure_ascii=False))
    rc, out = py("sync.py", root=root)
    step("第二次 sync 沒事做", rc == 0 and "上傳 0" in out)

    # 4. 網頁改了一則 → 回寫本機
    rid = docs[0][0]
    rest("PATCH", kit, "students/S-01/records/%s" % rid,
         body={"body": "（網頁上改過）主動幫同學撿起蠟筆，之後還把蠟筆盒排好。",
               "editedOnWeb": True, "webEditedAt": lib.now_iso()},
         mask=None) if False else lib.http("PATCH", base, "students/S-01/records/%s" % rid, "owner",
                                           body={"body": "（網頁上改過）主動幫同學撿起蠟筆，之後還把蠟筆盒排好。",
                                                 "editedOnWeb": True, "webEditedAt": lib.now_iso()},
                                           mask=["body", "editedOnWeb", "webEditedAt"])
    rc, out = py("sync.py", root=root)
    md = read(os.path.join(root, "data", "students", "S-01", "observations.md"))
    step("網頁改的回寫到本機檔", rc == 0 and "（網頁上改過）" in md and "回寫 1" in out)
    fs, _ = lib.get_doc(base, "students/S-01/records/%s" % rid, "owner", raise_errors=True)
    step("回寫後雲端旗標清掉", fs.get("editedOnWeb") is False)

    # 5. 兩邊都改 → 衝突、兩邊都不動
    write(os.path.join(root, "data", "students", "S-01", "observations.md"),
          md.replace("（網頁上改過）", "（本機又改）"))
    lib.http("PATCH", base, "students/S-01/records/%s" % rid, "owner",
             body={"body": "（網頁再改一次）", "editedOnWeb": True, "webEditedAt": lib.now_iso()},
             mask=["body", "editedOnWeb", "webEditedAt"])
    rc, out = py("sync.py", root=root)
    md2 = read(os.path.join(root, "data", "students", "S-01", "observations.md"))
    fs2, _ = lib.get_doc(base, "students/S-01/records/%s" % rid, "owner", raise_errors=True)
    step("兩邊都改 → 報衝突", "衝突" in out and "衝突 1" in out)
    stc, _ = lib.get_doc(base, "meta/status", "owner", raise_errors=True)
    step("衝突那一輪 meta/status.lastSyncConflicts 記 1（網頁不能顯示綠燈）",
         stc.get("lastSyncConflicts") == 1, str(stc.get("lastSyncConflicts")))
    step("衝突時本機不動", "（本機又改）" in md2)
    step("衝突時雲端不動", fs2.get("body") == "（網頁再改一次）")
    # 老師決定留網頁版：把本機改回去讓雜湊一致 → 下一次同步就用網頁那份
    write(os.path.join(root, "data", "students", "S-01", "observations.md"), md)
    rc, out = py("sync.py", root=root)
    step("本機還原後網頁版回寫", rc == 0 and "（網頁再改一次）" in read(os.path.join(root, "data", "students", "S-01", "observations.md")))

    # 6. 網頁上新增一則 → 本機長出來
    lib.http("PATCH", base, "students/S-03/records/2026-09-05", "owner",
             body={"date": "2026-09-05", "stream": "homeroom", "tags": ["#課堂"], "fields": {}, "related": [],
                   "body": "網頁上直接新增的一則。", "editedOnWeb": True, "webEditedAt": lib.now_iso(),
                   "source": "web"}, precondition_exists=False)
    rc, out = py("sync.py", root=root)
    p3 = os.path.join(root, "data", "students", "S-03", "observations.md")
    step("網頁新增 → 本機檔長出來", rc == 0 and os.path.exists(p3) and "網頁上直接新增" in read(p3) and "從網頁新增 1" in out)

    # 7. 網頁刪了一則 → 本機跟著刪、稽核留痕
    lib.http("DELETE", base, "students/S-03/records/2026-09-05", "owner")
    rc, out = py("sync.py", root=root)
    audit = read(os.path.join(root, "data", "audit.jsonl")) if os.path.exists(os.path.join(root, "data", "audit.jsonl")) else ""
    step("網頁刪除 → 本機跟著刪", rc == 0 and "網頁上直接新增" not in read(p3) and "刪除 1" in out)
    step("刪除留在 audit.jsonl", "2026-09-05" in audit)

    # 8. 名冊第三欄雙向：網頁把 S-03 列入 case
    roster_doc, _ = lib.get_doc(base, "roster/main", "owner", raise_errors=True)
    step("名冊推上雲端（roster/main）", bool(roster_doc), str(list(roster_doc.keys())[:5]))

    # 9. 備份 → zip 在「雲端硬碟同步夾」裡、含 export.json
    rc, out = py("backup.py", root=root)
    drive_dir = os.path.expanduser(kit["drive"]["desktop_dir"])
    zips = sorted(f for f in os.listdir(drive_dir) if f.endswith(".zip")) if os.path.isdir(drive_dir) else []
    ok = rc == 0 and zips
    if ok:
        with zipfile.ZipFile(os.path.join(drive_dir, zips[-1])) as z:
            names = z.namelist()
            ok = "export.json" in names and any(n.endswith("students/S-01/observations.md") for n in names)
            export = json.loads(z.read("export.json").decode("utf-8"))
    step("backup：zip 進同步夾、含 export.json 與記錄檔", bool(ok), zips[-1] if zips else out.strip().splitlines()[-1:] and out.strip().splitlines()[-1])
    st, _ = lib.get_doc(base, "meta/status", "owner", raise_errors=True)
    step("meta/status.lastBackupAt", bool(st.get("lastBackupAt")))

    # 10. 台帳三處對帳
    rc, out = py("ledger.py", "--rebuild", root=root)
    step("ledger --rebuild", rc == 0)
    rc, out = py("ledger.py", "--check", root=root)
    step("ledger --check 三處對得上（退出碼 0）", rc == 0, out.strip().splitlines()[-1] if out.strip() else "")

    # 11. 健檢讀得到雲端版本
    rc, out = py("doctor.py", "--json", root=root, expect=None)
    try:
        rep = json.loads(out[out.index("{"):])
        items = {i["key"]: i for i in rep["items"]}
        step("doctor：資料庫版本與程式一致", items["cloud_version"]["ok"] is True, items["cloud_version"].get("detail", ""))
        step("doctor：模擬器模式不需要 gcloud", items["gcloud_auth"]["ok"] is True)
    except Exception as e:
        step("doctor --json 可解析", False, str(e))

    # 12. 匯出（連網取雲端）
    rc, out = py("export_records.py", "--out", os.path.join(root, "all.md"), root=root)
    step("export_records 連網匯出", rc == 0 and os.path.exists(os.path.join(root, "all.md")))
    rc, out = py("report_pack.py", "--format", "waldorf-homeroom", "--target", "S-01", root=root)
    step("report_pack 素材包", rc == 0)

    # 13. 安全規則本身（模擬器載入的是 setup 產生的 firestore.rules）
    owner_tok, stranger_tok = fake_jwt(OWNER), fake_jwt("stranger@example.com")
    step("規則：擁有者讀得到", raw_get(kit, "students/S-01", owner_tok) == 200)
    step("規則：陌生人被擋（403）", raw_get(kit, "students/S-01", stranger_tok) == 403)
    step("規則：未登入被擋（403）", raw_get(kit, "students/S-01") == 403)
    step("規則：擁有者可建立合法紀錄",
         raw_post(kit, "students/S-01/records", "2026-09-06",
                  {"date": "2026-09-06", "stream": "homeroom", "body": "x", "tags": [], "fields": {}}, owner_tok) == 200)
    step("規則：少了 stream 的紀錄建不進去（403）",
         raw_post(kit, "students/S-01/records", "2026-09-07",
                  {"date": "2026-09-07", "body": "x", "tags": [], "fields": {}}, owner_tok) == 403)
    step("規則：id 與 date 對不上建不進去（403）",
         raw_post(kit, "students/S-01/records", "2026-09-08",
                  {"date": "2026-09-09", "stream": "homeroom", "body": "x", "tags": [], "fields": {}}, owner_tok) == 403)
    step("規則：陌生人建不進去（403）",
         raw_post(kit, "students/S-01/records", "2026-09-10",
                  {"date": "2026-09-10", "stream": "homeroom", "body": "x", "tags": [], "fields": {}}, stranger_tok) == 403)

    # 14. 無頭交辦：假造一則事件文件，讓 headless.py 真的跑一輪（AI 代理是假的）
    headless_steps(root, kit, base)

    print()
    if FAILS:
        print("✗ %d 項沒過：%s" % (len(FAILS), "、".join(FAILS)))
        return 1
    print("✓ 連網路徑全部通過（%s）" % base)
    return 0


# ── 外層：準備 root、起模擬器、把自己再叫一次 ───────────────────────────────────
def outer():
    if not hostos.exe("firebase"):
        print("找不到 firebase CLI；npm i -g firebase-tools 之後再跑。")
        return 2
    if not (hostos.exe("java") or os.path.isdir("/opt/homebrew/opt/openjdk/bin")):
        print("Firestore 模擬器需要 Java；macOS：brew install openjdk（並把 /opt/homebrew/opt/openjdk/bin 加進 PATH）。")
        return 2
    if os.path.isdir("/opt/homebrew/opt/openjdk/bin") and not hostos.exe("java"):
        os.environ["PATH"] = "/opt/homebrew/opt/openjdk/bin" + os.pathsep + os.environ.get("PATH", "")
    root = tempfile.mkdtemp(prefix="trk-emu-")
    try:
        with open(os.path.join(PKG, "templates", "answers.example.json"), encoding="utf-8") as f:
            answers = lib._strip_comments(json.load(f))
        answers["owner_email"] = OWNER
        answers["firebase"]["project_id"] = PROJECT
        answers["firebase"]["auth_domain"] = PROJECT + ".web.app"
        answers["drive"]["desktop_dir"] = os.path.join(root, "gdrive", "教學紀錄備份")
        os.makedirs(answers["drive"]["desktop_dir"])
        ans_path = os.path.join(root, "answers.json")
        write(ans_path, json.dumps(answers, ensure_ascii=False, indent=1))
        rc, out = py("setup.py", "--answers", ans_path, "--skip-doctor", root=root)
        if rc != 0:
            print(out[-1500:])
            return 1
        # 模擬器要從有 firebase.json 的資料夾起，規則檔是 setup 剛產生的那一份。
        # **這裡故意只留 firestore 那一段**，不複製 repo 的 firebase.json：
        # 那一份還宣告了 hosting／storage／functions，functions 的來源資料夾不在這個暫存 root 裡，
        # firebase CLI 讀設定時就可能因為那一段而抱怨（而那跟這支測的東西完全無關）。
        write(os.path.join(root, "firebase.json"), json.dumps({
            "firestore": {"rules": "firestore.rules", "indexes": "firestore.indexes.json"},
        }, ensure_ascii=False, indent=2) + "\n")
        shutil.copy(os.path.join(PKG, "firestore.indexes.json"), root)
        assert os.path.exists(os.path.join(root, "firestore.rules"))
        inner_cmd = '"%s" "%s" --inner "%s"' % (sys.executable, os.path.abspath(__file__), root)
        cmd = [hostos.exe("firebase"), "emulators:exec", "--only", "firestore", "--project", PROJECT, inner_cmd]
        print("啟動 Firestore 模擬器：%s" % " ".join(cmd[1:-1]))
        r = subprocess.run(cmd, cwd=root, timeout=1200)
        return r.returncode
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    if len(sys.argv) >= 3 and sys.argv[1] == "--inner":
        if not lib.emulator_host():
            print("--inner 要在 firebase emulators:exec 底下跑（FIRESTORE_EMULATOR_HOST 沒設）")
            sys.exit(2)
        sys.exit(inner(sys.argv[2]))
    sys.exit(outer())
