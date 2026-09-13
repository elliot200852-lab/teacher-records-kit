#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""評量維度自動補標（config/kit.json 的 auto_dim_tags）的測試。全部離線、合成資料、零真名。

    python3 -m unittest discover -s scripts/tests -p "test_*.py"

**永遠不會叫到真的 AI**：代理一律是環境變數 TRK_AUTO_TAGS_AGENT_CMD 指到的假腳本；
Firestore 一律是這裡的記憶體替身（前置條件、updateMask 的語意照真的做）。

守的是「不要弄丟、不要蓋掉老師的字」：只加不刪、前置條件不成立就跳過、AI 回壞東西零寫入、
CLI 不存在時同步照常結束，以及寫完之後緊接著再同步一次零推送、零回寫、零衝突、零 AI 呼叫。
"""
import io
import os
import sys
import copy
import json
import shutil
import unittest
import tempfile
import contextlib
import subprocess

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.dirname(SCRIPTS)
sys.path.insert(0, SCRIPTS)
import lib              # noqa: E402
import hostos           # noqa: E402
import auto_dim_tags as adt   # noqa: E402

REPS = ["#行為自我管理", "#人際", "#學習態度", "#內在特質", "#挑戰方向"]
KEY = "students/S-01/homeroom"

# 假代理：讀 stdin 的提示詞，照 FAKE_ADT_MODE 回答；每叫一次在 FAKE_ADT_LOG 記一行（含提示詞全文）。
FAKE_AGENT = r'''# -*- coding: utf-8 -*-
import os, sys, json, time
text = sys.stdin.buffer.read().decode("utf-8")
items = json.loads(text[text.index("\n[") + 1:])
log = os.environ.get("FAKE_ADT_LOG")
if log:
    with open(log, "a", encoding="utf-8") as f:
        f.write(json.dumps({"n": len(items), "ids": [i["id"] for i in items], "prompt": text},
                           ensure_ascii=False) + "\n")
mode = os.environ.get("FAKE_ADT_MODE", "map")
def say(s):
    sys.stdout.buffer.write((s + "\n").encode("utf-8"))
if mode == "sleep":
    time.sleep(60)
if mode == "fail":
    sys.stderr.write("not logged in\n")
    sys.exit(3)
if mode == "badjson":
    say("好的，以下是結果：{壞掉")
    sys.exit(0)
if mode == "unknown-rid":
    say(json.dumps({"S-99/2026-01-01": ["人際互動"]}, ensure_ascii=False))
    sys.exit(0)
if mode == "unknown-dim":
    say(json.dumps({i["id"]: ["人際"] for i in items}, ensure_ascii=False))
    sys.exit(0)
rules = json.loads(os.environ.get("FAKE_ADT_MAP") or "{}")
bad = os.environ.get("FAKE_ADT_BAD") or ""
out = {}
for i in items:
    if bad and bad in i["text"]:
        out[i["id"]] = ["不存在的維度"]
        continue
    dims = []
    for word, ds in rules.items():
        if word in i["text"]:
            dims += [d for d in ds if d not in dims]
    out[i["id"]] = dims
body = json.dumps(out, ensure_ascii=False)
say("```json\n" + body + "\n```" if mode == "fenced" else body)
'''


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return path


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class FakeFirestore(object):
    """記憶體裡的 Firestore：list／get／PATCH（updateMask、updateTime／exists 前置條件）／DELETE。"""

    def __init__(self):
        self.docs = {}
        self.n = 0
        self.writes = []
        self.fail_tag_patch = False
        self.fail_rollback = False                  # 第二次（含）以後的 tags／contentHash PATCH 前置條件不成立
        self.tag_patches = 0

    def _ut(self):
        self.n += 1
        return "2026-09-13T00:00:00.%06dZ" % self.n

    def put(self, path, fields):
        self.docs[path] = (copy.deepcopy(fields), self._ut())

    def fields(self, path):
        return self.docs[path][0]

    def list_docs(self, base, path, tok, raise_errors=False):
        depth = path.count("/") + 1
        return [(p.rsplit("/", 1)[1], copy.deepcopy(f), ut) for p, (f, ut) in sorted(self.docs.items())
                if p.startswith(path + "/") and p.count("/") == depth]

    def get_doc(self, base, path, tok, raise_errors=False):
        if path not in self.docs:
            return None, None
        f, ut = self.docs[path]
        return copy.deepcopy(f), ut

    def http(self, method, base, path, tok, body=None, mask=None, precondition_update_time=None,
             precondition_exists=None, params=None, raise_errors=False):
        if method == "GET":
            return {}
        if method == "DELETE":
            self.docs.pop(path, None)
            return {}
        cur = self.docs.get(path)
        tag_patch = list(mask or []) == ["tags", "contentHash"]
        if self.fail_tag_patch and tag_patch:
            raise lib.Precondition(path)            # 模擬「網頁在 AI 判斷的時候改過這一則」
        if self.fail_rollback and tag_patch and self.tag_patches >= 1:
            raise lib.Precondition(path)            # 模擬「要改回雲端時網頁又改了一次」
        if precondition_update_time and (cur is None or cur[1] != precondition_update_time):
            raise lib.Precondition(path)
        if precondition_exists is False and cur is not None:
            raise lib.Precondition(path)
        if mask:
            new = copy.deepcopy(cur[0]) if cur else {}
            for m in mask:
                if m in (body or {}):
                    new[m] = copy.deepcopy(body[m])
                else:
                    new.pop(m, None)
        else:
            new = copy.deepcopy(body or {})
        ut = self._ut()
        self.docs[path] = (new, ut)
        self.writes.append((path, copy.deepcopy(body), list(mask) if mask else None))
        if tag_patch:
            self.tag_patches += 1
        if precondition_update_time or precondition_exists is not None:
            return {"writeResults": [{"updateTime": ut}], "commitTime": ut}    # documents:commit 的形狀
        return {"updateTime": ut}

    def record_writes(self, since=0):
        return [w for w in self.writes[since:] if "/records/" in w[0]]


HOMEROOM = ("# S-01\n\n"
            "## 2026-09-01 #數學\n\n下課時主動幫同學撿起掉落的蠟筆，工作本也寫完了。\n\n"
            "## 2026-09-02\n\n今天比較安靜。\n\n"
            "## 2026-09-03 #人際\n\n和同學一起搬桌子。\n\n"
            "## 2026-09-04 #專注\n\n測試甲今天跟同學吵架。\n")
QUALITATIVE = "# S-01\n\n## 2026-09-05\n報告維度：人際互動\n\n和同學分組合作。\n"


class SyncBase(unittest.TestCase):
    ENV = (adt.STUB_ENV, adt.SKIP_ENV, "FAKE_ADT_MODE", "FAKE_ADT_MAP", "FAKE_ADT_LOG", "FAKE_ADT_BAD")

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="trk-adt-")
        self.old_root = lib.root()
        self.orig = (lib.list_docs, lib.get_doc, lib.http, lib.token, hostos.exe)
        self.old_env = {k: os.environ.get(k) for k in self.ENV}
        for k in self.ENV:
            os.environ.pop(k, None)
        self.fs = FakeFirestore()
        lib.list_docs, lib.get_doc, lib.http = self.fs.list_docs, self.fs.get_doc, self.fs.http
        lib.token = lambda *a, **kw: "tok"
        self.agent = write(os.path.join(self.tmp, "fake-agent.py"), FAKE_AGENT)
        self.log = os.path.join(self.tmp, "agent-calls.jsonl")
        os.environ[adt.STUB_ENV] = self.agent
        os.environ["FAKE_ADT_LOG"] = self.log
        os.environ["FAKE_ADT_MAP"] = json.dumps({"同學": ["人際互動"], "工作本": ["學習態度與能力"]},
                                                ensure_ascii=False)
        self.write_config()
        write(os.path.join(self.tmp, "data", "roster.csv"), "代號,姓名,類型\nS-01,測試甲,\nS-02,測試乙,\n")
        self.obs = write(os.path.join(self.tmp, "data", "students", "S-01", "observations.md"), HOMEROOM)
        write(os.path.join(self.tmp, "data", "students", "S-01", "qualitative.md"), QUALITATIVE)

    def tearDown(self):
        (lib.list_docs, lib.get_doc, lib.http, lib.token, hostos.exe) = self.orig
        lib.set_root(self.old_root)
        for k, v in self.old_env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write_config(self, headless_agent="", **ad):
        cfg = {"enabled": True, "agent": "claude", "timeout_sec": 120}
        cfg.update(ad)
        kit = {"version": 3, "mode": "cloud", "owner_email": "t@example.com", "id_prefix": "S",
               "firebase": {"project_id": "demo-adt"},
               "headless": {"enabled": False, "agent": headless_agent},
               "auto_dim_tags": cfg}
        tabs = {"version": 3,
                "students": {"enabled": True, "streams": [
                    {"id": "homeroom", "label": "導師班級學生紀錄", "scope": "class", "fields": [], "tags": []},
                    {"id": "qualitative", "label": "質性評量觀察", "scope": "class",
                     "fields": [{"name": "報告維度", "type": "select"}], "tags": []}]},
                "courses": {"enabled": False}, "business": {"enabled": False}}
        write(os.path.join(self.tmp, "config", "kit.json"), json.dumps(kit, ensure_ascii=False))
        write(os.path.join(self.tmp, "config", "tabs.json"), json.dumps(tabs, ensure_ascii=False))

    def sync(self, *args):
        """在同一個行程裡跑 sync.main()：丟出 SystemExit 測試就會失敗（＝退出碼被改了）。"""
        import sync
        buf = io.StringIO()
        argv = sys.argv
        sys.argv = ["sync.py", "--root", self.tmp] + list(args)
        try:
            with contextlib.redirect_stdout(buf):
                sync.main()
        finally:
            sys.argv = argv
        return buf.getvalue()

    def calls(self):
        if not os.path.exists(self.log):
            return []
        return [json.loads(x) for x in read(self.log).splitlines() if x.strip()]

    def cloud(self, rid, sid="S-01"):
        return self.fs.fields("students/%s/records/%s" % (sid, rid))

    def block(self, rid, path=None):
        _, blocks = lib.parse_file(path or self.obs)
        return [b for b in blocks if b["rid"] == rid][0]

    def judged(self):
        p = os.path.join(self.tmp, "data", adt.STATE_FILE)
        return (json.loads(read(p)).get("judged") or {}).get(KEY, {}) if os.path.exists(p) else None

    def failures(self):
        p = os.path.join(self.tmp, "data", adt.STATE_FILE)
        return (json.loads(read(p)).get("failures") or {}).get(KEY, {}) if os.path.exists(p) else {}


# ── 純函式 ──────────────────────────────────────────────────────────────
class TestPlanAndPick(unittest.TestCase):
    def setUp(self):
        self.formats = lib.load_report_formats()
        self.fmt = lib.find_format("waldorf-homeroom", self.formats)
        self.dimtags = adt.dimension_tags(self.fmt)
        self.tmp = tempfile.mkdtemp(prefix="trk-adt-pick-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_representative_tags_come_from_the_library(self):
        self.assertEqual(list(self.dimtags.keys()), self.fmt["dimensions"])
        self.assertEqual(list(self.dimtags.values()), REPS,
                         "代表標籤＝tagMap 裡各維度排第一個的標（改格式庫就要改這一行）")

    def test_plan_only_takes_streams_the_web_derives(self):
        tabs = {"students": {"streams": [
            {"id": "homeroom", "scope": "class", "fields": []},
            {"id": "qualitative", "scope": "class", "fields": [{"name": "報告維度"}]},
            {"id": "iep", "scope": "case", "fields": [{"name": "目標編號"}], "card": {"goals": True}},
            {"id": "soap", "scope": "case", "fields": [], "card": {"conceptualization": True}},
            {"id": "subject", "scope": "class", "fields": [{"name": "科目"}]}]}}
        targets = [{"kind": "students", "id": "S-01", "stream": s, "key": "students/S-01/" + s}
                   for s in ("homeroom", "qualitative", "iep", "soap", "subject")]
        targets.append({"kind": "class", "id": "main", "stream": "homeroom", "key": "class/main/homeroom"})
        got = adt.plan(tabs, targets, self.formats)
        self.assertEqual([t["key"] for t, _f, _d in got], ["students/S-01/homeroom"])
        self.assertEqual(adt.eligible_streams(tabs, self.formats), ["homeroom"])

    def blocks(self, text):
        _, blocks = lib.parse_file(write(os.path.join(self.tmp, "x.md"), text))
        return {b["rid"]: b for b in blocks}

    def test_pick_rules(self):
        bs = self.blocks("# x\n\n"
                         "## 2026-09-01 #人際\n\n有代表標籤。\n\n"
                         "## 2026-09-02 #數學\n\n只有主題標籤。\n\n"
                         "## 2026-09-03\n\n完全沒打標。\n\n"
                         "## 2026-09-04 #意志力#學習態度\n\n黏在一起的標也算有。\n\n"
                         "## 2026-09-05\n\n測試甲出現真名。\n\n"
                         "## 2026-09-06 #數學\n\n"
                         "## 2026-09-07\n\n判斷過、正文沒改。\n\n"
                         "## 2026-09-08\n\n判斷過、正文改了。\n")
        judged = {"2026-09-07": adt.body_hash(bs["2026-09-07"]["body"]), "2026-09-08": "0000"}
        got = [b["rid"] for b in adt.pick(list(bs.values()), self.dimtags, ["測試甲"], judged)]
        self.assertEqual(got, ["2026-09-02", "2026-09-03", "2026-09-08"])

    def test_pick_skips_records_the_cloud_does_not_agree_on(self):
        bs = self.blocks("# x\n\n## 2026-09-01\n\n一。\n\n## 2026-09-02\n\n二。\n\n"
                         "## 2026-09-03\n\n三。\n\n## 2026-09-04\n\n四。\n\n## 2026-09-05\n\n五。\n")
        cloud = {"2026-09-01": ({"contentHash": bs["2026-09-01"]["hash"]}, "t1"),
                 "2026-09-02": ({"contentHash": bs["2026-09-02"]["hash"], "deleted": True}, "t1"),
                 "2026-09-03": ({"contentHash": bs["2026-09-03"]["hash"], "editedOnWeb": True}, "t1"),
                 "2026-09-04": ({"contentHash": "不一樣"}, "t1")}           # 2026-09-05 雲端還沒有
        got = [b["rid"] for b in adt.pick(list(bs.values()), self.dimtags, [], {}, cloud)]
        self.assertEqual(got, ["2026-09-01"], "軟刪、網頁正在改、兩邊不一致、雲端還沒有的都不送")

    def test_add_tags_only_appends(self):
        tags = ["#數學", "#人際"]
        self.assertEqual(adt.add_tags(tags, ["#人際", "#學習態度", "#學習態度"]),
                         ["#數學", "#人際", "#學習態度"])
        self.assertEqual(tags, ["#數學", "#人際"], "原本那一份不可以被改到")
        self.assertEqual(adt.add_tags(["#意志力#學習態度"], ["#學習態度"]), ["#意志力#學習態度"])
        self.assertEqual(adt.add_tags([], []), [])

    def test_validate_only_accepts_known_ids_and_dimension_names(self):
        dims = self.fmt["dimensions"]
        ids = {"S-01/a", "S-01/b", "S-01/c", "S-01/d"}
        ok, bad, unknown = adt.validate({"S-01/a": ["人際互動", "行為與自我管理", "人際互動"],
                                         "S-01/b": ["人際"], "S-01/d": [],
                                         "S-99/x": ["人際互動"], }, ids, dims)
        self.assertEqual(ok, {"S-01/a": ["行為與自我管理", "人際互動"], "S-01/d": []})
        self.assertEqual(bad, ["S-01/b"])
        self.assertEqual(unknown, ["S-99/x"])
        ok, bad, _ = adt.validate({"S-01/a": "人際互動", "S-01/b": [3]}, ids, dims)
        self.assertEqual((ok, sorted(bad)), ({}, ["S-01/a", "S-01/b"]))

    def test_parse_answer(self):
        self.assertEqual(adt.parse_answer('```json\n{"a": []}\n```'), {"a": []})
        self.assertEqual(adt.parse_answer('結果如下 {"a": ["人際互動"]} 以上'), {"a": ["人際互動"]})
        for bad in ("{壞掉", "[]", "", "沒有 JSON"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                adt.parse_answer(bad)

    def test_prompt_carries_only_ids_and_bodies(self):
        bs = self.blocks("# x\n\n## 2026-09-02 #數學 #秘密標\n課程：秘密欄位\n\n只有這一段正文。\n")
        items = [{"id": "S-01/2026-09-02", "block": bs["2026-09-02"]}]
        p = adt.build_prompt(self.fmt, self.fmt["dimensions"], items)
        self.assertIn("S-01/2026-09-02", p)
        self.assertIn("只有這一段正文。", p)
        for leak in ("#數學", "#秘密標", "秘密欄位"):
            self.assertNotIn(leak, p, "送給 AI 的只有代號與正文")
        self.assertIn("他怎麼安排自己", p, "維度說明要取自格式的 sections hint")
        self.assertIn("單一事件也照打", p)
        self.assertIn("只依正文", p)


# ── 代理 CLI 與設定 ─────────────────────────────────────────────────────
class TestAgentAndConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="trk-adt-cli-")
        self.orig_exe = hostos.exe
        self.old_stub = os.environ.pop(adt.STUB_ENV, None)

    def tearDown(self):
        hostos.exe = self.orig_exe
        if self.old_stub is not None:
            os.environ[adt.STUB_ENV] = self.old_stub
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_hostos_oneshot_forms(self):
        """三家的叫法：不給工具、不帶提示詞（走 stdin）、不准出現無頭交辦那幾個放權旗標。"""
        for agent in hostos.AGENT_ORDER:
            argv = hostos.agent_oneshot_argv(agent, "/w/out.txt")
            self.assertEqual(argv[0], hostos.AGENT_CLIS[agent]["cmd"], agent)
            self.assertFalse([a for a in argv if "{" in a], agent)
            for loose in ("yolo", "acceptEdits", "workspace-write", "--allowedTools",
                          "--dangerously-skip-permissions", "bypassPermissions"):
                self.assertNotIn(loose, argv, "%s 的補標叫法不該放權：%s" % (agent, loose))
        claude = hostos.agent_oneshot_argv("claude", "")
        self.assertIn("-p", claude)
        self.assertEqual(claude[claude.index("--tools") + 1], "", "claude 要用 --tools \"\" 關掉全部工具")
        codex = hostos.agent_oneshot_argv("codex", "/w/out.txt")
        self.assertEqual(codex[1], "exec")
        self.assertEqual(codex[codex.index("--sandbox") + 1], "read-only")
        self.assertEqual(codex[codex.index("-o") + 1], "/w/out.txt")
        self.assertEqual(codex[-1], "-", "codex 的提示詞從 stdin 讀")
        gemini = hostos.agent_oneshot_argv("gemini", "")
        self.assertEqual(gemini[gemini.index("--approval-mode") + 1], "default")
        self.assertEqual(hostos.agent_oneshot_argv("copilot", ""), [])

    def test_agent_argv_raises_when_the_cli_is_missing(self):
        hostos.exe = lambda name: None
        with self.assertRaises(adt.AgentMissing):
            adt.agent_argv("claude", "")
        with self.assertRaises(adt.AgentMissing):
            adt.agent_argv("copilot", "")
        os.environ[adt.STUB_ENV] = os.path.join(self.tmp, "沒有這支.py")
        try:
            with self.assertRaises(adt.AgentMissing):
                adt.agent_argv("claude", "")
        finally:
            os.environ.pop(adt.STUB_ENV, None)

    def test_run_agent_feeds_stdin_and_blocks_nested_auto_tags(self):
        path = write(os.path.join(self.tmp, "echo.py"),
                     "import os, sys\n"
                     "t = sys.stdin.buffer.read().decode('utf-8')\n"
                     "sys.stdout.buffer.write(('%s|%s' % (os.environ.get('" + adt.SKIP_ENV + "'), t))"
                     ".encode('utf-8'))\n")
        rc, out, _err = adt.run_agent([sys.executable, path], "提示詞\n第二行", 60, cwd=self.tmp)
        self.assertEqual(rc, 0)
        self.assertEqual(out, "1|提示詞\n第二行", "代理要從 stdin 拿到提示詞，而且它跑的同步不准再補標")

    def test_run_agent_prefers_the_last_message_file(self):
        out_file = os.path.join(self.tmp, "last.txt")
        path = write(os.path.join(self.tmp, "codexish.py"),
                     "import sys\nsys.stdin.read()\nprint('進度訊息 {不是答案')\n"
                     "open(sys.argv[1], 'w', encoding='utf-8').write('{\"a\": []}')\n")
        rc, out, _ = adt.run_agent([sys.executable, path, out_file], "x", 60, out_file=out_file)
        self.assertEqual((rc, adt.parse_answer(out)), (0, {"a": []}))

    def test_run_agent_times_out(self):
        path = write(os.path.join(self.tmp, "hang.py"), "import time\ntime.sleep(60)\n")
        rc, _out, _err = adt.run_agent([sys.executable, path], "x", 2)
        self.assertEqual(rc, 124)

    def test_config_reader(self):
        cfg = lib.auto_dim_tags_cfg
        self.assertFalse(cfg({})["enabled"])
        self.assertEqual(cfg({})["timeout_sec"], lib.AUTO_DIM_TIMEOUT_DEFAULT)
        self.assertEqual(cfg({})["max_batches"], 2, "每次同步預設最多 2 批（60 則）")
        self.assertEqual(cfg({"auto_dim_tags": {"max_batches": 5}})["max_batches"], 5)
        self.assertEqual(cfg({"auto_dim_tags": {"max_batches": -3}})["max_batches"], 1)
        inherit = {"auto_dim_tags": {"enabled": True, "agent": ""}, "headless": {"agent": "codex"}}
        self.assertEqual(cfg(inherit)["agent"], "codex", "agent 空字串＝沿用 headless.agent")
        self.assertTrue(cfg(inherit)["agent_inherited"])
        self.assertTrue(lib.auto_dim_tags_on(inherit))
        own = {"auto_dim_tags": {"enabled": True, "agent": "Gemini "}, "headless": {"agent": "codex"}}
        self.assertEqual(cfg(own)["agent"], "gemini")
        none = {"auto_dim_tags": {"enabled": True, "agent": ""}}
        self.assertEqual(cfg(none)["agent"], "")
        self.assertFalse(lib.auto_dim_tags_on(none), "兩者都空＝視同沒設定")
        self.assertFalse(lib.auto_dim_tags_on(dict(inherit, mode="local")), "本機模式沒有同步")

    def test_examples_are_off(self):
        kit = lib._load_json(os.path.join(PKG, "config", "kit.example.json"), "kit 範本", "")
        self.assertIs(kit["auto_dim_tags"]["enabled"], False, "範本一定要是關的（零預設）")
        self.assertEqual(kit["auto_dim_tags"]["agent"], "")
        self.assertEqual(kit["auto_dim_tags"]["max_batches"], 2)
        ans = lib._load_json(os.path.join(PKG, "templates", "answers.example.json"), "答案檔範本", "")
        self.assertIs(ans["auto_dim_tags"]["enabled"], False)


class TestInstallDoctorBuild(unittest.TestCase):
    """安裝精靈寫得出這一段、健檢查得到代理、設定產生器擋得住亂填的代理。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="trk-adt-setup-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_py(self, script, *args):
        cmd = [sys.executable, os.path.join(SCRIPTS, script), *args, "--root", self.tmp]
        return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                              timeout=300)

    def install(self, auto):
        with open(os.path.join(PKG, "templates", "answers.example.json"), encoding="utf-8") as f:
            a = lib._strip_comments(json.load(f))
        a["auto_dim_tags"] = auto
        path = write(os.path.join(self.tmp, "answers.json"), json.dumps(a, ensure_ascii=False))
        r = self.run_py("setup.py", "--answers", path, "--skip-doctor")
        self.assertEqual(r.returncode, 0, (r.stdout + r.stderr)[-2000:])
        with open(os.path.join(self.tmp, "config", "kit.json"), encoding="utf-8") as f:
            return json.load(f)

    def doctor_items(self):
        r = self.run_py("doctor.py", "--json", "--skip-network")
        return {i["key"]: i for i in json.loads(r.stdout[r.stdout.index("{"):])["items"]}

    def test_setup_writes_the_block_and_doctor_checks_the_agent(self):
        kit = self.install({"enabled": True, "agent": "gemini"})
        self.assertEqual(kit["auto_dim_tags"]["enabled"], True)
        self.assertEqual(kit["auto_dim_tags"]["agent"], "gemini")
        items = self.doctor_items()
        self.assertIn("auto_dim_tags", items)
        self.assertIn("auto_dim_tags_agent", items, "開著就要檢查代理 CLI 找不找得到")
        self.assertIn("gemini", items["auto_dim_tags_agent"]["label"])

    def test_off_is_quiet(self):
        kit = self.install({"enabled": False, "agent": "gemini"})
        self.assertEqual(kit["auto_dim_tags"], dict(kit["auto_dim_tags"], enabled=False, agent=""))
        items = self.doctor_items()
        self.assertTrue(items["auto_dim_tags"]["ok"])
        self.assertFalse(items["auto_dim_tags"]["required"])
        self.assertNotIn("auto_dim_tags_agent", items)

    def test_build_config_rejects_an_unknown_agent(self):
        kit = self.install({"enabled": True, "agent": "claude"})
        kit["auto_dim_tags"]["agent"] = "copilot"
        write(os.path.join(self.tmp, "config", "kit.json"), json.dumps(kit, ensure_ascii=False))
        r = self.run_py("build_config.py", "--check", "--allow-placeholders")
        self.assertEqual(r.returncode, 1)
        self.assertIn("auto_dim_tags.agent", r.stdout + r.stderr)
        kit["auto_dim_tags"].update(agent="claude", max_batches=0)
        write(os.path.join(self.tmp, "config", "kit.json"), json.dumps(kit, ensure_ascii=False))
        r = self.run_py("build_config.py", "--check", "--allow-placeholders")
        self.assertEqual(r.returncode, 1)
        self.assertIn("auto_dim_tags.max_batches", r.stdout + r.stderr)

    def test_sync_help_lists_the_flag(self):
        r = self.run_py("sync.py", "--help")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("--no-auto-tags", r.stdout)


# ── 接在 sync.py 裡跑 ───────────────────────────────────────────────────
class TestSyncAutoTags(SyncBase):
    def test_first_sync_tags_and_the_next_sync_is_a_no_op(self):
        out = self.sync()
        calls = self.calls()
        self.assertEqual(len(calls), 1, out)
        self.assertEqual(sorted(calls[0]["ids"]), ["S-01/2026-09-01", "S-01/2026-09-02"],
                         "已有代表標籤的、有真名的、非自動推導類型的都不送；只有主題標籤的照送")
        prompt = calls[0]["prompt"]
        for leak in ("測試甲", "測試乙", "#數學", "報告維度：", "roster"):
            self.assertNotIn(leak, prompt, "送給 AI 的只有代號與正文")

        # 只加不刪、原標籤在前；雲端與本機一模一樣，contentHash 對得上、editedOnWeb 沒被碰
        b1 = self.block("2026-09-01")
        self.assertEqual(b1["tags"], ["#數學", "#人際", "#學習態度"])
        self.assertIn("## 2026-09-01 #數學 #人際 #學習態度", read(self.obs))
        c1 = self.cloud("2026-09-01")
        self.assertEqual(c1["tags"], ["#數學", "#人際", "#學習態度"])
        self.assertEqual(c1["contentHash"], b1["hash"])
        self.assertIs(c1["editedOnWeb"], False)
        self.assertEqual(c1["body"], b1["body"])
        tag_writes = [w for w in self.fs.record_writes() if w[2] == ["tags", "contentHash"]]
        self.assertEqual(len(tag_writes), 1, "判定零個維度的那一則不必寫雲端")
        self.assertEqual(self.block("2026-09-02")["tags"], [])
        self.assertEqual(self.cloud("2026-09-02")["tags"], [])
        judged = self.judged()
        self.assertEqual(set(judged), {"2026-09-01", "2026-09-02"}, "零個維度也要記，免得每次重問")
        self.assertIn("補上標籤 1 則", out)
        self.assertTrue(os.path.exists(os.path.join(os.path.dirname(self.obs), ".observations.prev.md")),
                        "寫本機之前要照 sync 的規矩先備份")
        self.assertIn("測試甲今天跟同學吵架。", read(self.obs))

        text, n_writes = read(self.obs), len(self.fs.writes)
        out2 = self.sync()
        self.assertEqual(len(self.calls()), 1, "第二次同步不可以再叫 AI：%s" % out2)
        self.assertEqual(self.fs.record_writes(n_writes), [], "第二次同步不可以再寫任何一則紀錄")
        self.assertIn("上傳 0、回寫 0、從網頁新增 0、刪除 0、衝突 0", out2)
        self.assertEqual(read(self.obs), text)
        self.assertNotIn("評量維度補標", out2)

    def test_record_added_on_the_web_is_tagged_after_it_lands_locally(self):
        self.fs.put("students/S-01/records/2026-09-06",
                    {"date": "2026-09-06", "stream": "homeroom", "tags": ["#課堂"], "fields": {},
                     "related": [], "body": "分組時邀請落單的同學加入。", "editedOnWeb": True,
                     "source": "web"})
        out = self.sync()
        self.assertIn("S-01/2026-09-06", self.calls()[0]["ids"], out)
        self.assertIn("## 2026-09-06 #課堂 #人際", read(self.obs))
        c = self.cloud("2026-09-06")
        self.assertEqual(c["tags"], ["#課堂", "#人際"])
        self.assertIs(c["editedOnWeb"], False)
        self.assertEqual(c["contentHash"], self.block("2026-09-06")["hash"])
        out2 = self.sync()
        self.assertIn("上傳 0、回寫 0、從網頁新增 0、刪除 0、衝突 0", out2)
        self.assertEqual(len(self.calls()), 1)

    def assert_nothing_written(self, out):
        self.assertEqual(read(self.obs), HOMEROOM, "本機檔一個字都不能動：%s" % out)
        self.assertEqual([w for w in self.fs.record_writes() if w[2] == ["tags", "contentHash"]], [])
        self.assertEqual(self.cloud("2026-09-01")["tags"], ["#數學"])
        self.assertFalse(self.judged(), "沒寫成的不可以記成判斷過")

    def test_bad_json_writes_nothing(self):
        os.environ["FAKE_ADT_MODE"] = "badjson"
        out = self.sync()
        self.assert_nothing_written(out)
        self.assertIn("不是可以用的 JSON", out)
        self.assertIn("上傳 4", out, "同步本身照常完成（homeroom 3 則＋質性 1 則）")

    def test_unknown_id_writes_nothing(self):
        os.environ["FAKE_ADT_MODE"] = "unknown-rid"
        out = self.sync()
        self.assert_nothing_written(out)
        self.assertIn("不認得的 id", out)

    def test_unknown_dimension_name_writes_nothing(self):
        os.environ["FAKE_ADT_MODE"] = "unknown-dim"
        out = self.sync()
        self.assert_nothing_written(out)
        self.assertIn("格式裡沒有的維度名", out)

    def test_fenced_json_is_accepted(self):
        os.environ["FAKE_ADT_MODE"] = "fenced"
        self.sync()
        self.assertEqual(self.block("2026-09-01")["tags"], ["#數學", "#人際", "#學習態度"])

    def test_agent_failure_writes_nothing(self):
        os.environ["FAKE_ADT_MODE"] = "fail"
        out = self.sync()
        self.assert_nothing_written(out)
        self.assertIn("回傳 3", out)

    def test_timeout_writes_nothing(self):
        self.write_config(timeout_sec=2)
        os.environ["FAKE_ADT_MODE"] = "sleep"
        out = self.sync()
        self.assert_nothing_written(out)
        self.assertIn("超過 2 秒", out)

    def test_missing_cli_keeps_the_exit_code_and_warns(self):
        os.environ[adt.STUB_ENV] = os.path.join(self.tmp, "no-such-agent")
        out = self.sync()                       # 沒有 SystemExit＝退出碼 0
        self.assertIn("評量維度補標沒有跑", out)
        self.assertIn("同步本身已經完成", out)
        self.assert_nothing_written(out)
        self.assertEqual(self.cloud("2026-09-01")["body"], self.block("2026-09-01")["body"])

    def test_missing_real_cli_keeps_the_exit_code_and_warns(self):
        os.environ.pop(adt.STUB_ENV, None)
        hostos.exe = lambda name: None
        out = self.sync()
        self.assertIn("這台電腦上找不到 claude", out)
        self.assert_nothing_written(out)

    def test_failed_precondition_skips_and_is_not_remembered(self):
        self.fs.fail_tag_patch = True
        out = self.sync()
        self.assertEqual(self.block("2026-09-01")["tags"], ["#數學"], out)
        self.assertEqual(self.cloud("2026-09-01")["tags"], ["#數學"])
        self.assertNotIn("2026-09-01", self.judged() or {}, "前置條件不成立＝不記為判斷過")
        self.assertIn("網頁上剛好在改這一則", out)
        self.fs.fail_tag_patch = False
        self.sync()
        self.assertEqual(len(self.calls()), 2, "下一次同步要再判斷那一則")
        self.assertEqual(self.calls()[1]["ids"], ["S-01/2026-09-01"])
        self.assertEqual(self.block("2026-09-01")["tags"], ["#數學", "#人際", "#學習態度"])

    def test_dry_run_does_not_call_ai(self):
        out = self.sync("--dry-run")
        self.assertEqual(self.calls(), [])
        self.assertIn("（預演）評量維度補標：會送 AI 代理（claude）判斷 2 則", out)
        self.assertEqual(read(self.obs), HOMEROOM)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "data", adt.STATE_FILE)))

    def test_no_auto_tags_flag(self):
        out = self.sync("--no-auto-tags")
        self.assertEqual(self.calls(), [])
        self.assertNotIn("評量維度補標", out)
        self.assertIn("上傳 4", out)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "data", adt.STATE_FILE)))

    def test_only_limits_the_targets(self):
        write(os.path.join(self.tmp, "data", "students", "S-02", "observations.md"),
              "# S-02\n\n## 2026-09-07\n\n和同學一起收拾教室。\n")
        self.sync("--only", "students/S-02")
        self.assertEqual([c["ids"] for c in self.calls()], [["S-02/2026-09-07"]])
        self.assertEqual(read(self.obs), HOMEROOM)

    def test_disabled_or_unconfigured_does_nothing(self):
        self.write_config(enabled=False)
        self.assertNotIn("評量維度補標", self.sync())
        self.write_config(agent="", headless_agent="")
        self.assertNotIn("評量維度補標", self.sync())
        self.assertEqual(self.calls(), [])

    def test_sync_started_by_an_agent_does_not_call_ai(self):
        os.environ[adt.SKIP_ENV] = "1"
        self.sync()
        self.assertEqual(self.calls(), [])
        self.assertEqual(read(self.obs), HOMEROOM)

    # ── 本機只在標題列尾端接標籤，其他行一個位元組都不動 ──
    def raw_lines(self):
        with open(self.obs, "rb") as f:
            return f.read().split(b"\n")

    def assert_only_header_changed(self, before, idx, new_header):
        after = self.raw_lines()
        self.assertEqual(len(after), len(before))
        for i, (x, y) in enumerate(zip(before, after)):
            if i == idx:
                self.assertEqual(y, new_header.encode("utf-8"))
            else:
                self.assertEqual(y, x, "第 %d 行不可以被動到" % (i + 1))

    def test_header_text_is_kept_byte_for_byte(self):
        write(self.obs, "# S-01\n\n## 2026-09-01 午休觀察 #數學\n\n下課時主動幫同學撿起掉落的蠟筆。  \n\n"
                        "## 2026-09-03 #人際\n\n和同學一起搬桌子。\n")
        before = self.raw_lines()
        out = self.sync()
        self.assert_only_header_changed(before, 2, "## 2026-09-01 午休觀察 #數學 #人際")
        b1 = self.block("2026-09-01")
        self.assertEqual(b1["tags"], ["#數學", "#人際"], out)
        self.assertEqual(self.cloud("2026-09-01")["tags"], ["#數學", "#人際"])
        self.assertEqual(self.cloud("2026-09-01")["contentHash"], b1["hash"])
        self.assertIn("上傳 0、回寫 0、從網頁新增 0、刪除 0、衝突 0", self.sync())
        self.assertEqual(len(self.calls()), 1)

    def test_duplicate_field_keys_are_kept_byte_for_byte(self):
        write(self.obs, "# S-01\n\n## 2026-09-01 #數學\n課程：主課程\n課程：數學\n\n和同學討論分數。\n")
        before = self.raw_lines()
        out = self.sync()
        self.assert_only_header_changed(before, 2, "## 2026-09-01 #數學 #人際")
        self.assertIn("課程：主課程\n課程：數學\n", read(self.obs), out)
        self.assertIn("上傳 0、回寫 0、從網頁新增 0、刪除 0、衝突 0", self.sync())

    def test_crlf_and_bom_are_kept(self):
        with open(self.obs, "wb") as f:
            f.write("\ufeff# S-01\r\n\r\n## 2026-09-02\r\n\r\n和同學一起收拾。\r\n".encode("utf-8"))
        before = self.raw_lines()
        out = self.sync()
        self.assert_only_header_changed(before, 2, "## 2026-09-02 #人際\r")
        self.assertTrue(self.raw_lines()[0].startswith(b"\xef\xbb\xbf"), out)

    def test_append_that_does_not_read_back_writes_nothing(self):
        orig = adt.header_with_tags

        def broken(line, added):                     # 叫 AI 之前的試接正常；真的要接時吃掉一個原本的標
            res = orig(line, added)
            return res.replace("#數學", "") if "#人際" in added else res
        adt.header_with_tags = broken
        try:
            out = self.sync()
        finally:
            adt.header_with_tags = orig
        self.assertEqual(read(self.obs), HOMEROOM, out)
        self.assertEqual([w for w in self.fs.record_writes() if w[2] == ["tags", "contentHash"]], [])
        self.assertEqual(self.cloud("2026-09-01")["tags"], ["#數學"])
        self.assertNotIn("2026-09-01", self.judged() or {})
        self.assertIn("讀回來對不上", out)

    # ── 本機寫不進去 ──
    def test_read_only_file_is_skipped_before_asking_ai(self):
        os.chmod(self.obs, 0o444)
        try:
            if os.access(self.obs, os.W_OK):
                self.skipTest("這個帳號對唯讀檔照樣寫得進去（root？）")
            out = self.sync()
        finally:
            os.chmod(self.obs, 0o644)
        self.assertEqual(self.calls(), [], "寫不進去就不要叫 AI：%s" % out)
        self.assertIn("寫不進去", out)
        self.assert_nothing_written(out)

    def test_local_write_failure_rolls_the_cloud_back(self):
        orig = adt.replace_file

        def boom(path, text):
            raise OSError("磁碟滿了")
        adt.replace_file = boom
        try:
            out = self.sync()
        finally:
            adt.replace_file = orig
        self.assertEqual(len(self.calls()), 1, out)
        self.assertEqual(read(self.obs), HOMEROOM)
        b1, c1 = self.block("2026-09-01"), self.cloud("2026-09-01")
        self.assertEqual(c1["tags"], ["#數學"], "本機沒寫成，雲端要改回原樣")
        self.assertEqual(c1["contentHash"], b1["hash"])
        self.assertIs(c1["editedOnWeb"], False)
        self.assertNotIn("2026-09-01", self.judged() or {})
        self.assertIn("改回原樣", out)
        self.assertEqual(self.failures()["2026-09-01"]["n"], 1, "本機沒寫成要記一次沒補成")
        out2 = self.sync("--no-auto-tags")
        self.assertIn("上傳 0、回寫 0、從網頁新增 0、刪除 0、衝突 0", out2, "改回去之後下一輪不可以有衝突或重推")
        # 一直寫不成：第二次就記成看不出維度，不會每輪都白叫 AI＋寫兩次雲端
        adt.replace_file = boom
        try:
            out3 = self.sync()
        finally:
            adt.replace_file = orig
        self.assertIn("2 次沒補成", out3)
        self.assertIn("2026-09-01", self.judged())
        n_calls, n_writes = len(self.calls()), len(self.fs.writes)
        self.sync()
        self.assertEqual(len(self.calls()), n_calls, "放棄之後不再叫 AI")
        self.assertEqual(self.fs.record_writes(n_writes), [])
        self.assertEqual(read(self.obs), HOMEROOM)

    def test_rollback_failure_is_a_clear_warning(self):
        orig = adt.replace_file

        def boom(path, text):
            raise OSError("磁碟滿了")
        adt.replace_file = boom
        self.fs.fail_rollback = True
        try:
            out = self.sync()
        finally:
            adt.replace_file = orig
        self.assertIn("回滾也失敗", out)
        self.assertEqual(read(self.obs), HOMEROOM)
        self.assertNotIn("2026-09-01", self.judged() or {})

    # ── 每次同步最多幾批 ──
    def test_max_batches_limits_each_sync(self):
        self.write_config(max_batches=1)
        orig = adt.BATCH_MAX
        adt.BATCH_MAX = 1
        try:
            out = self.sync()
            self.assertEqual(len(self.calls()), 1, out)
            self.assertIn("還有 1 則等下次同步", out)
            out2 = self.sync()
            self.assertEqual(len(self.calls()), 2, out2)
            self.assertNotIn("則等下次同步（每次同步最多送", out2)
            self.sync()
            self.assertEqual(len(self.calls()), 2, "都判斷完了就不再叫")
        finally:
            adt.BATCH_MAX = orig
        self.assertEqual(self.block("2026-09-01")["tags"], ["#數學", "#人際", "#學習態度"])

    def test_items_that_keep_failing_do_not_block_the_queue(self):
        """前面那一則 AI 一直回不合格：排到後面讓別的先補，同一份正文 2 次就不再送。"""
        self.write_config(max_batches=1)
        os.environ["FAKE_ADT_BAD"] = "蠟筆"                  # 2026-09-01 那一則永遠回不存在的維度名
        orig = adt.BATCH_MAX
        adt.BATCH_MAX = 1
        try:
            for _ in range(4):
                self.sync()
        finally:
            adt.BATCH_MAX = orig
        self.assertEqual([c["ids"] for c in self.calls()],
                         [["S-01/2026-09-01"], ["S-01/2026-09-02"], ["S-01/2026-09-01"]],
                         "失敗過的要排到後面；第二次失敗之後就不再送")
        self.assertEqual(self.block("2026-09-01")["tags"], ["#數學"])
        self.assertEqual(set(self.judged()), {"2026-09-01", "2026-09-02"})
        self.assertEqual(self.failures(), {})

    def test_append_during_local_write_is_not_lost(self):
        """讀檔之後、換檔之前 append_record.py 追加了一則：不換檔、雲端改回、那一則還在。"""
        orig = shutil.copy2
        added = "\n## 2026-09-09\n\n剛好寫進來的一則。\n"

        def copy_then_append(src, dst, *a, **kw):
            res = orig(src, dst, *a, **kw)
            if src == self.obs:
                with open(self.obs, "a", encoding="utf-8", newline="\n") as f:
                    f.write(added)
            return res
        shutil.copy2 = copy_then_append
        try:
            out = self.sync()
        finally:
            shutil.copy2 = orig
        self.assertEqual(read(self.obs), HOMEROOM + added, out)
        self.assertEqual(self.cloud("2026-09-01")["tags"], ["#數學"], "沒換檔就要把雲端改回去")
        self.assertIn("補標途中被改過", out)
        self.assertEqual(self.failures()["2026-09-01"]["n"], 1)

    def test_symlinked_file_is_skipped(self):
        real = write(os.path.join(self.tmp, "elsewhere", "observations.md"), HOMEROOM)
        os.remove(self.obs)
        try:
            os.symlink(real, self.obs)
        except (OSError, NotImplementedError):
            self.skipTest("這個平台／帳號建不了 symlink")
        out = self.sync()
        self.assertEqual(self.calls(), [], out)
        self.assertIn("捷徑", out)
        self.assertTrue(os.path.islink(self.obs), "捷徑不可以被換成一般檔")
        self.assertEqual(read(real), HOMEROOM)

    def test_fullwidth_space_before_tags_is_kept(self):
        write(self.obs, "# S-01\n\n## 2026-09-01 午休觀察\u3000\n\n和同學一起搬桌子。\n")
        before = self.raw_lines()
        self.sync()
        self.assert_only_header_changed(before, 2, "## 2026-09-01 午休觀察\u3000 #人際")

    def test_dry_run_counts_only_this_round(self):
        self.write_config(max_batches=1)
        orig = adt.BATCH_MAX
        adt.BATCH_MAX = 1
        try:
            out = self.sync("--dry-run")
        finally:
            adt.BATCH_MAX = orig
        self.assertIn("判斷 1 則（S-01 1 則）", out)
        self.assertIn("還有 1 則等下次同步", out)

    def test_lone_cr_file_warns_once(self):
        with open(self.obs, "wb") as f:
            f.write("# S-01\r\r## 2026-09-02\r\r和同學一起收拾。\r".encode("utf-8"))
        with open(self.obs, encoding="utf-8", newline="") as f:
            before = f.read()
        out = self.sync()
        self.assertIn("沒辦法只在標題列尾端接上標籤", out)
        out2 = self.sync()
        self.assertNotIn("沒辦法只在標題列尾端接上標籤", out2, "同一份內容只提醒一次")
        self.assertEqual(self.calls(), [])
        with open(self.obs, encoding="utf-8", newline="") as f:
            self.assertEqual(f.read(), before)

    def test_local_edit_after_the_ai_answered_wins(self):
        """AI 判斷的那段時間老師改了本機檔：那一則不寫雲端也不寫本機、不記判斷。"""
        orig = adt.run_agent

        def edit_then_answer(*a, **kw):
            res = orig(*a, **kw)
            write(self.obs, read(self.obs).replace("工作本也寫完了。", "工作本也寫完了，還幫忙發簿子。"))
            return res
        adt.run_agent = edit_then_answer
        try:
            out = self.sync()
        finally:
            adt.run_agent = orig
        self.assertIn("還幫忙發簿子", read(self.obs), out)
        self.assertEqual(self.block("2026-09-01")["tags"], ["#數學"])
        self.assertEqual(self.cloud("2026-09-01")["tags"], ["#數學"])
        self.assertNotIn("2026-09-01", self.judged() or {})


if __name__ == "__main__":
    unittest.main()
