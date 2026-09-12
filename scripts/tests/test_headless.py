#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""兩個可選功能的測試：資料庫模式（cloud／local）與無頭交辦（LINE）。全部離線。

    python3 -m unittest discover -s scripts/tests -p "test_*.py"

這裡驗的是「選了之後整套東西真的跟著變」——不是只驗設定檔寫對了：
本機模式不產生規則檔、sync 安靜地什麼都不做、排程少掛一個 job；
無頭交辦開了才有 Storage 規則的那一段、才多掛第三個 job。

**永遠不會叫到真的 AI**：agent 那一段一律走環境變數 TRK_HEADLESS_AGENT_CMD 指到的假腳本。
"""
import os
import sys
import json
import stat
import shutil
import unittest
import tempfile
import subprocess
import xml.etree.ElementTree as ET

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.dirname(SCRIPTS)
sys.path.insert(0, SCRIPTS)
import lib          # noqa: E402
import hostos       # noqa: E402
import headless     # noqa: E402
import schedule     # noqa: E402


def run(script, *args, env=None, root=None):
    cmd = [sys.executable, os.path.join(SCRIPTS, script), *args]
    if root:
        cmd += ["--root", root]
    e = dict(os.environ)
    e.update(env or {})
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=300, env=e)


def answers(mode="cloud", headless_on=False, uid="Uabc12345678", agent="claude"):
    with open(os.path.join(PKG, "templates", "answers.example.json"), encoding="utf-8") as f:
        a = lib._strip_comments(json.load(f))
    a["mode"] = mode
    a["headless"] = {"enabled": headless_on, "agent": agent, "line": {"owner_user_id": uid}}
    return a


def install(tmp, **kw):
    """在暫存目錄裡跑一次免互動安裝，回 (root, kit)。"""
    path = os.path.join(tmp, "answers.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(answers(**kw), f, ensure_ascii=False)
    r = run("setup.py", "--answers", path, "--skip-doctor", root=tmp)
    assert r.returncode == 0, (r.stdout + r.stderr)[-2000:]
    with open(os.path.join(tmp, "config", "kit.json"), encoding="utf-8") as f:
        return tmp, json.load(f)


class ModeConfig(unittest.TestCase):
    """lib 的兩個讀取器：沒寫就是舊行為（cloud、沒開），寫了就照寫的。"""

    def test_mode_defaults_to_cloud(self):
        self.assertEqual(lib.mode({}), "cloud")
        self.assertEqual(lib.mode({"mode": "LOCAL "}), "local")
        self.assertEqual(lib.mode({"mode": "亂寫"}), "cloud")
        self.assertTrue(lib.is_local({"mode": "local"}))
        self.assertFalse(lib.is_local({}))

    def test_headless_defaults_are_off(self):
        h = lib.headless_cfg({})
        self.assertFalse(h["enabled"])
        self.assertEqual(h["tool"], "line")
        self.assertEqual(h["timeout_sec"], lib.HEADLESS_TIMEOUT_DEFAULT)
        self.assertEqual(h["line"]["channel_secret_env"], "KIT_LINE_CHANNEL_SECRET")
        self.assertFalse(lib.headless_on({}))

    def test_headless_is_off_in_local_mode(self):
        """本機模式沒有雲端可以收 webhook——就算設定寫 enabled 也一律當關著。"""
        kit = {"mode": "local", "headless": {"enabled": True, "agent": "claude"}}
        self.assertTrue(lib.headless_cfg(kit)["enabled"])
        self.assertFalse(lib.headless_on(kit))

    def test_examples_carry_both_options(self):
        kit = lib._load_json(os.path.join(PKG, "config", "kit.example.json"), "kit 範本", "")
        self.assertEqual(kit["mode"], "cloud")
        self.assertFalse(kit["headless"]["enabled"], "範本一定要是關的（零預設）")
        self.assertEqual(kit["headless"]["line"]["channel_secret_env"], "KIT_LINE_CHANNEL_SECRET")
        self.assertEqual(set(kit["headless"]["line"]),
                         {"channel_secret_env", "channel_token_env", "owner_user_id"},
                         "設定檔只寫「環境變數叫什麼」，金鑰本身永遠不進任何檔案")
        ans = lib._load_json(os.path.join(PKG, "templates", "answers.example.json"), "答案檔範本", "")
        self.assertEqual(ans["mode"], "cloud")
        self.assertFalse(ans["headless"]["enabled"])

    def test_storage_bucket_falls_back_to_default(self):
        self.assertEqual(lib.storage_bucket({"firebase": {"project_id": "p", "storage_bucket": ""}}),
                         "p.firebasestorage.app")
        self.assertEqual(lib.storage_bucket({"firebase": {"project_id": "p",
                                                          "storage_bucket": "gs://b.app/"}}), "b.app")


class LocalMode(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="trk-local-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_setup_skips_firebase_and_marks_steps(self):
        root, kit = install(self.tmp, mode="local")
        self.assertEqual(kit["mode"], "local")
        with open(os.path.join(root, "setup", "progress.json"), encoding="utf-8") as f:
            steps = {s["step"]: s for s in json.load(f)["steps"]}
        for n in (2, 4, 5):
            self.assertTrue(steps[n]["done"], "第 %d 步在本機模式應該標成完成" % n)
            self.assertEqual(steps[n]["notes"], "本機模式，略過")
        self.assertTrue(steps[11]["done"], "沒開無頭交辦，第 11 步也該是完成")

    def test_build_config_writes_no_rules_and_no_firebase_js(self):
        root, _ = install(self.tmp, mode="local")
        self.assertTrue(os.path.exists(os.path.join(root, "site", "js", "kit-config.js")))
        for gone in ("firestore.rules", "storage.rules",
                     os.path.join("site", "js", "firebase-config.js")):
            self.assertFalse(os.path.exists(os.path.join(root, gone)),
                             "本機模式不該產生 %s（產出來會讓人以為有個資料庫在那裡）" % gone)
        with open(os.path.join(root, "site", "js", "kit-config.js"), encoding="utf-8") as f:
            payload = json.loads(f.read().split("window.KIT = ", 1)[1].rstrip().rstrip(";"))
        self.assertEqual(payload["mode"], "local")
        self.assertFalse(payload["headless"]["enabled"])

    def test_build_config_does_not_require_firebase_values(self):
        """本機模式下那六個空值不算錯誤（老師根本沒被問過）。"""
        root, _ = install(self.tmp, mode="local")
        kit_path = os.path.join(root, "config", "kit.json")
        with open(kit_path, encoding="utf-8") as f:
            kit = json.load(f)
        kit["owner_email"] = "teacher@example.com"
        kit["firebase"] = {k: "" for k in ("project_id", "api_key", "auth_domain",
                                           "storage_bucket", "messaging_sender_id", "app_id")}
        with open(kit_path, "w", encoding="utf-8") as f:
            json.dump(kit, f, ensure_ascii=False)
        r = run("build_config.py", "--check", root=root)     # 注意：**沒有** --allow-placeholders
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("local", r.stdout)

    def test_sync_is_a_quiet_no_op(self):
        root, _ = install(self.tmp, mode="local")
        r = run("sync.py", root=root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("本機模式沒有雲端，不用同步", r.stdout)
        self.assertNotIn("Traceback", r.stdout + r.stderr)

    def test_ledger_check_defaults_to_offline(self):
        """沒加 --offline 也不准去要 gcloud 權杖——本機模式的人根本不會有 gcloud。"""
        root, _ = install(self.tmp, mode="local")
        r = run("ledger.py", "--rebuild", root=root)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = run("ledger.py", "--check", root=root, env={"PATH": os.path.dirname(sys.executable)})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("本機模式", r.stdout)
        self.assertNotIn("gcloud", r.stdout)

    def test_doctor_keeps_every_key_but_skips_the_cloud_ones(self):
        """CI 的離線閘靠固定的 key 清單——本機模式只准把它們標成略過，不准拿掉。"""
        root, _ = install(self.tmp, mode="local")
        r = run("doctor.py", "--json", "--skip-network", root=root)
        data = json.loads(r.stdout[r.stdout.index("{"):])
        items = {i["key"]: i for i in data["items"]}
        for key in ("platform", "python", "cfg_kit", "cfg_tabs", "gen_kitjs", "gen_fbjs",
                    "gen_rules", "rules_email"):
            self.assertIn(key, items, "doctor 不可以在本機模式下少報 %s" % key)
        for key in ("gen_fbjs", "gen_rules", "rules_email", "cloud_version", "gcloud_auth",
                    "firebase", "gcloud", "node"):
            self.assertTrue(items[key]["skipped"], "%s 在本機模式應該是「略過」不是 ✗" % key)
            self.assertFalse(items[key]["required"] and not items[key]["skipped"])
        self.assertEqual(data["mode"], "local")

    def test_schedule_drops_the_sync_job(self):
        root, kit = install(self.tmp, mode="local")
        self.assertEqual(schedule.wanted_jobs(kit), ["backup"])
        r = run("schedule.py", "--print-cron", env={"TRK_ROOT": root})
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("backup.py", r.stdout)
        self.assertNotIn("sync.py", r.stdout)

    def test_headless_refuses_local_mode(self):
        root, _ = install(self.tmp, mode="local", headless_on=True)
        r = run("headless.py", "--once", root=root)
        self.assertEqual(r.returncode, 0, "沒開不算失敗（排程會叫到它）")
        self.assertIn("本機模式", r.stdout)

    def test_build_config_rejects_headless_in_local_mode(self):
        root, _ = install(self.tmp, mode="local")
        kit_path = os.path.join(root, "config", "kit.json")
        with open(kit_path, encoding="utf-8") as f:
            kit = json.load(f)
        kit["headless"] = {"enabled": True, "tool": "line", "agent": "claude",
                           "timeout_sec": 1800, "line": {"owner_user_id": "U1"}}
        with open(kit_path, "w", encoding="utf-8") as f:
            json.dump(kit, f, ensure_ascii=False)
        r = run("build_config.py", "--check", "--allow-placeholders", root=root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("本機模式不能開無頭交辦", r.stdout + r.stderr)

    def test_bad_mode_is_rejected(self):
        root, _ = install(self.tmp, mode="local")
        kit_path = os.path.join(root, "config", "kit.json")
        with open(kit_path, encoding="utf-8") as f:
            kit = json.load(f)
        kit["mode"] = "hybrid"
        with open(kit_path, "w", encoding="utf-8") as f:
            json.dump(kit, f, ensure_ascii=False)
        r = run("build_config.py", "--check", "--allow-placeholders", root=root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("只能是 cloud 或 local", r.stdout + r.stderr)


class HeadlessConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="trk-hl-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_setup_writes_the_block_without_any_secret(self):
        root, kit = install(self.tmp, headless_on=True)
        h = kit["headless"]
        self.assertTrue(h["enabled"])
        self.assertEqual(h["tool"], "line")
        self.assertEqual(h["agent"], "claude")
        self.assertEqual(h["line"]["owner_user_id"], "Uabc12345678")
        # 設定檔裡只有「環境變數叫什麼」，沒有值
        self.assertEqual(set(h["line"]), {"channel_secret_env", "channel_token_env", "owner_user_id"})
        with open(os.path.join(root, "setup", "progress.json"), encoding="utf-8") as f:
            steps = {s["step"]: s for s in json.load(f)["steps"]}
        self.assertFalse(steps[11]["done"], "開了無頭交辦，第 11 步就還沒做完（要部署 relay）")

    def test_storage_rules_only_opens_the_inbox_when_enabled(self):
        off_root, _ = install(self.tmp, headless_on=False)
        with open(os.path.join(off_root, "storage.rules"), encoding="utf-8") as f:
            off = f.read()
        self.assertNotIn("match /headless-inbox", off,
                         "沒開無頭交辦就不該有那條規則（檔頭註解提到它沒關係）")
        self.assertIn("allow read, write: if false", off)

        tmp2 = tempfile.mkdtemp(prefix="trk-hl2-")
        try:
            on_root, _ = install(tmp2, headless_on=True)
            with open(os.path.join(on_root, "storage.rules"), encoding="utf-8") as f:
                on = f.read()
            self.assertIn("match /headless-inbox/{file}", on)
            self.assertIn("isOwner()", on)
            self.assertNotIn("{{", on, "佔位符沒被換掉")
        finally:
            shutil.rmtree(tmp2, ignore_errors=True)

    def test_firestore_rules_lock_the_event_collections(self):
        root, _ = install(self.tmp, headless_on=True)
        with open(os.path.join(root, "firestore.rules"), encoding="utf-8") as f:
            rules = f.read()
        for coll in ("headless_events", "headless_pairing"):
            self.assertIn("match /%s/" % coll, rules)
        self.assertNotIn("{{OWNER_EMAIL}}", rules)

    def test_build_config_rejects_an_unknown_agent(self):
        root, _ = install(self.tmp, headless_on=True)
        kit_path = os.path.join(root, "config", "kit.json")
        with open(kit_path, encoding="utf-8") as f:
            kit = json.load(f)
        kit["headless"]["agent"] = "copilot"
        with open(kit_path, "w", encoding="utf-8") as f:
            json.dump(kit, f, ensure_ascii=False)
        r = run("build_config.py", "--check", "--allow-placeholders", root=root)
        self.assertEqual(r.returncode, 1)
        self.assertIn("headless.agent", r.stdout + r.stderr)

    def test_doctor_reports_the_five_headless_items(self):
        root, _ = install(self.tmp, headless_on=True)
        r = run("doctor.py", "--json", "--skip-network", root=root,
                env={"KIT_LINE_CHANNEL_SECRET": "", "KIT_LINE_CHANNEL_TOKEN": ""})
        data = json.loads(r.stdout[r.stdout.index("{"):])
        items = {i["key"]: i for i in data["items"]}
        self.assertTrue(data["headless"])
        self.assertIn("headless", items)
        self.assertFalse(items["headless_secrets"]["ok"], "兩個環境變數是空的就該紅")
        self.assertTrue(items["headless_paired"]["ok"])
        self.assertTrue(items["headless_cloud"]["skipped"], "--skip-network 時不准去連雲端")

    def test_doctor_is_quiet_when_headless_is_off(self):
        root, _ = install(self.tmp, headless_on=False)
        r = run("doctor.py", "--json", "--skip-network", root=root)
        data = json.loads(r.stdout[r.stdout.index("{"):])
        items = {i["key"]: i for i in data["items"]}
        self.assertTrue(items["headless"]["ok"])
        self.assertFalse(items["headless"]["required"])
        self.assertNotIn("headless_secrets", items, "沒開就不該冒出四個新項目")


class HeadlessSchedule(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="trk-hlsched-")
        self.root, self.kit = install(self.tmp, headless_on=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_wanted_jobs(self):
        self.assertEqual(schedule.wanted_jobs(self.kit), ["sync", "backup", "headless"])
        self.assertEqual(schedule.wanted_jobs({}), ["sync", "backup"])

    def test_cron_line_is_every_five_minutes(self):
        lines = schedule.cron_lines((7, 0), 0, (8, 0), ["sync", "backup", "headless"])
        self.assertEqual(len(lines), 3)
        self.assertTrue(lines[2].startswith("*/5 * * * * cd "))
        self.assertIn("headless.py --once --quiet", lines[2])
        # 舊的呼叫法（三個位置參數）要原樣回兩行，不然既有測試與 --print-cron 會變形
        self.assertEqual(len(schedule.cron_lines((7, 0), 0, (8, 0))), 2)

    def test_mac_plist_uses_start_interval(self):
        p = schedule.mac_plist("headless", 0, 0)
        self.assertEqual(p["StartInterval"], 300)
        self.assertNotIn("StartCalendarInterval", p)
        self.assertIn("--once", p["ProgramArguments"])
        # 另外兩個 job 一定還是「幾點幾分」那種
        self.assertIn("StartCalendarInterval", schedule.mac_plist("sync", 7, 0))

    def test_windows_xml_repeats_every_five_minutes(self):
        xml = schedule.win_task_xml("headless", 0, 0, None)
        root = ET.fromstring(xml.encode("utf-16"))
        ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
        rep = root.find("t:Triggers/t:CalendarTrigger/t:Repetition", ns)
        self.assertIsNotNone(rep, "工作排程器沒有「每 N 分鐘」觸發器，要靠 Repetition")
        self.assertEqual(rep.find("t:Interval", ns).text, "PT5M")
        self.assertEqual(rep.find("t:Duration", ns).text, "P1D")
        self.assertEqual(rep.find("t:StopAtDurationEnd", ns).text, "false")
        self.assertIn("headless.py", root.find("t:Actions/t:Exec/t:Arguments", ns).text)
        # 每天型的那兩個不可以長出 Repetition
        for job, wd in (("sync", None), ("backup", 0)):
            other = ET.fromstring(schedule.win_task_xml(job, 7, 5, wd).encode("utf-16"))
            self.assertIsNone(other.find("t:Triggers/t:CalendarTrigger/t:Repetition", ns))

    def test_dry_run_renders_the_third_job_on_every_platform(self):
        for o, marker in (("mac", "com.teacher-records-kit.headless"),
                          ("win", r"TeacherRecordsKit\Headless"),
                          ("linux", "*/5 * * * *")):
            r = run("schedule.py", "--dry-run", env={"TRK_FORCE_OS": o, "TRK_ROOT": self.root})
            self.assertEqual(r.returncode, 0, (o, r.stdout[-800:], r.stderr))
            self.assertIn(marker, r.stdout, o)
            self.assertIn("每 5 分鐘", r.stdout, o)


class HeadlessWorker(unittest.TestCase):
    """headless.py 的純函式與「沒開就安靜退出」；agent 永遠是假的。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="trk-hlw-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def stub(self, body):
        """寫一支假的 AI 代理（測試永遠只會叫到它）。"""
        path = os.path.join(self.tmp, "fake-agent.py")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write("#!/usr/bin/env python3\nimport sys\n" + body)
        os.chmod(path, os.stat(path).st_mode | stat.S_IEXEC | stat.S_IRWXU)
        return path

    def test_extract_report(self):
        out = "廢話廢話\n<<REPORT>>\n已記到 S-01 的班級紀錄。\n<<END>>\n收尾"
        self.assertEqual(headless.extract_report(out), "已記到 S-01 的班級紀錄。")
        self.assertEqual(headless.extract_report("什麼都沒有"), "")
        # 有好幾段就取最後一段（代理常常先示範格式再真的印一次）
        self.assertEqual(headless.extract_report("<<REPORT>>一<<END>> <<REPORT>>二<<END>>"), "二")
        # 上限：推到手機上的東西不能無限長
        long_out = "<<REPORT>>" + "字" * 999 + "<<END>>"
        self.assertEqual(len(headless.extract_report(long_out)), headless.REPORT_MAX)

    def test_agent_argv_prefers_the_stub(self):
        path = self.stub("print('x')\n")
        os.environ["TRK_HEADLESS_AGENT_CMD"] = path
        try:
            self.assertEqual(headless.agent_argv("claude", "提示詞"), [path, "提示詞"])
        finally:
            os.environ.pop("TRK_HEADLESS_AGENT_CMD")

    def test_agent_argv_rejects_an_unknown_agent(self):
        with self.assertRaises(RuntimeError):
            headless.agent_argv("copilot", "x")

    def test_hostos_headless_forms(self):
        """三家的非互動叫法：一定要是 argv（不經 shell），而且提示詞原樣佔一格。"""
        for agent in hostos.AGENT_ORDER:
            argv = hostos.agent_headless_argv(agent, '有"引號"與 $變數 與\n換行')
            self.assertTrue(argv, agent)
            self.assertEqual(argv[0], hostos.AGENT_CLIS[agent]["cmd"])
            self.assertIn('有"引號"與 $變數 與\n換行', argv)
            self.assertNotIn("{prompt}", " ".join(argv))
        self.assertEqual(hostos.agent_headless_argv("copilot", "x"), [])
        # 逐字對過 --help 的旗標，改動時要一起改註解與 docs
        self.assertIn("-p", hostos.agent_headless_argv("claude", "x"))
        self.assertIn("acceptEdits", hostos.agent_headless_argv("claude", "x"))
        self.assertEqual(hostos.agent_headless_argv("codex", "x")[1], "exec")
        self.assertIn("yolo", hostos.agent_headless_argv("gemini", "x"))

    def test_run_agent_kills_a_hung_process_tree(self):
        """逾時的代理要連子孫一起殺掉，而且回 124。"""
        path = self.stub("import time\ntime.sleep(60)\n")
        rc, _out = headless.run_agent([sys.executable, path], timeout=2)
        self.assertEqual(rc, 124)

    def test_run_agent_returns_output(self):
        path = self.stub("print('<<REPORT>>好了<<END>>')\n")
        rc, out = headless.run_agent([sys.executable, path], timeout=60)
        self.assertEqual(rc, 0)
        self.assertEqual(headless.extract_report(out), "好了")

    def test_build_prompt_inlines_the_script(self):
        kit = {"mode": "cloud"}
        p = headless.build_prompt(kit, {"receivedAt": "2026-09-12T10:00:00"}, "今天午休…", "LINE 語音訊息")
        self.assertIn("append_record.py", p, "作業指示要整段帶進提示詞（代理可能不會去讀檔）")
        self.assertIn("<<REPORT>>", p)
        self.assertIn("今天午休…", p)
        self.assertIn("sync.py", p)
        self.assertNotIn("sync.py", headless.build_prompt({"mode": "local"}, {}, "x", "y")
                         .split("以下是你要遵守的作業指示")[0])

    def test_exits_quietly_when_not_enabled(self):
        root, _ = install(self.tmp, headless_on=False)
        for args in (["--once"], ["--status"], ["--pair"]):
            r = run("headless.py", *args, root=root)
            self.assertEqual(r.returncode, 0, (args, r.stdout + r.stderr))
            self.assertIn("無頭交辦沒有開", r.stdout)

    def test_script_file_exists_and_has_the_markers(self):
        p = os.path.join(PKG, "AGENTS-HEADLESS.md")
        self.assertTrue(os.path.exists(p))
        with open(p, encoding="utf-8") as f:
            text = f.read()
        for must in ("<<REPORT>>", "<<END>>", "append_record.py", "roster.csv", "tabs.json"):
            self.assertIn(must, text)


class Relay(unittest.TestCase):
    """Cloud Function 那一半（JS）——這裡只做靜態把關，行為由模擬器與真機驗。"""

    def setUp(self):
        self.dir = os.path.join(PKG, "functions", "line-relay")

    def test_package_json_is_minimal_and_pinned_to_node_20(self):
        with open(os.path.join(self.dir, "package.json"), encoding="utf-8") as f:
            pkg = json.load(f)
        self.assertEqual(pkg["engines"]["node"], "20")
        self.assertEqual(set(pkg["dependencies"]), {"firebase-admin", "firebase-functions"},
                         "relay 只准這兩個相依：每多一個就是老師專案裡多一份要維護的東西")

    def test_index_js_has_the_load_bearing_pieces(self):
        with open(os.path.join(self.dir, "index.js"), encoding="utf-8") as f:
            js = f.read()
        for must in ("x-line-signature",      # 簽章驗證
                     "timingSafeEqual",       # 不能用 == 比簽章
                     "req.rawBody",           # 一定要用原始 body 算
                     "asia-east1",            # 區域
                     "defineSecret",          # 金鑰走 Functions secret，不進 repo
                     "headless_events",
                     "headless-inbox",
                     "配對碼：",
                     "收到了，電腦醒著時會處理"):
            self.assertIn(must, js, must)
        # 簽章一定要拿 rawBody 去算（重組 JSON 的空白與鍵序永遠對不上）。
        # 只看程式本體，檔頭註解裡提到那個反例不算。
        body = js.split("'use strict';", 1)[1]
        self.assertIn(".update(rawBody)", body)
        self.assertNotIn("JSON.stringify(req.body)", body)
        # 這兩個字串是 headless.py 與規則檔一起認的，改名要三處一起改
        self.assertIn(headless.EVENTS, js)
        self.assertIn(headless.PAIRING, js)

    def test_firebase_json_wires_the_codebase(self):
        with open(os.path.join(PKG, "firebase.json"), encoding="utf-8") as f:
            fb = json.load(f)
        fn = fb["functions"][0]
        self.assertEqual(fn["codebase"], "line-relay")
        self.assertEqual(fn["source"], "functions/line-relay")
        self.assertEqual(fn["runtime"], "nodejs20")
        self.assertEqual(fb["storage"]["rules"], "storage.rules")


if __name__ == "__main__":
    unittest.main()
