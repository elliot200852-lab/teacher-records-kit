#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端到端測試：安裝精靈、設定產生器、健檢、台帳、寫入通道。全部在暫存目錄裡跑，零網路。

    python3 -m unittest discover scripts/tests

每一個 test 都用 `--root <暫存目錄>`，所以不會碰到你自己的 config/ 與 data/。
"""
import os
import re
import sys
import json
import shutil
import unittest
import tempfile
import subprocess

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.dirname(SCRIPTS)
sys.path.insert(0, SCRIPTS)
import lib  # noqa: E402


def read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def run(script, *args, **kw):
    cmd = [sys.executable, os.path.join(SCRIPTS, script), *args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=300, **kw)


class TestBuildConfig(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="trk-build-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_check_on_examples(self):
        r = run("build_config.py", "--check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_generates_three_files(self):
        r = run("build_config.py", "--root", self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        kitjs = os.path.join(self.tmp, "site", "js", "kit-config.js")
        fbjs = os.path.join(self.tmp, "site", "js", "firebase-config.js")
        rules = os.path.join(self.tmp, "firestore.rules")
        for p in (kitjs, fbjs, rules):
            self.assertTrue(os.path.exists(p), "沒產生 %s" % p)
        text = read(kitjs)
        self.assertTrue(text.startswith("/*"))
        payload = json.loads(text.split("window.KIT = ", 1)[1].rstrip().rstrip(";"))
        self.assertIs(payload["demo"], False)
        self.assertIn("students", payload["tabs"])
        self.assertIn("business", payload["tabs"])
        self.assertTrue(payload["businessLibrary"], "業務組庫是空的")
        self.assertFalse([g for g in payload["businessLibrary"] if g.get("open")],
                         "「我的業務不在清單裡」是安裝時的選項，不該出現在網頁的組庫")
        self.assertTrue(payload["idPrefix"].endswith("-"))
        fb = read(fbjs)
        self.assertIn("window.FIREBASE_CONFIG", fb)
        self.assertIn("window.OWNER_EMAIL", fb)
        self.assertNotIn("export ", fb, "firebase-config.js 不能是 module")
        self.assertNotIn("{{OWNER_EMAIL}}", read(rules))

    def test_bad_config_fails_with_reason(self):
        os.makedirs(os.path.join(self.tmp, "config"))
        dump_json(os.path.join(self.tmp, "config", "kit.json"),
                  {"owner_email": "不是信箱", "firebase": {}})
        r = run("build_config.py", "--root", self.tmp)
        self.assertEqual(r.returncode, 1)
        self.assertIn("✗", r.stderr)
        self.assertIn("→", r.stderr)


class TestSetupEndToEnd(unittest.TestCase):
    """`setup.py --answers` 跑完整流程：不連網、不問問題、產出所有檔。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="trk-setup-")
        cls.r = run("setup.py", "--answers", os.path.join(PKG, "templates", "answers.example.json"),
                    "--root", cls.tmp, "--skip-network")

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_exit_ok(self):
        self.assertEqual(self.r.returncode, 0, self.r.stdout + self.r.stderr)

    def test_writes_config(self):
        kit = load_json(os.path.join(self.tmp, "config", "kit.json"))
        tabs = load_json(os.path.join(self.tmp, "config", "tabs.json"))
        self.assertEqual(kit["owner_email"], "you@example.com")
        self.assertEqual(kit["drive"]["mode"], "desktop")
        self.assertEqual([c["id"] for c in tabs["courses"]["list"]], ["main-block", "handwork"])
        gids = [g["id"] for g in tabs["business"]["groups"]]
        self.assertEqual(gids, ["homeroom", "meetings", "club"])
        homeroom = tabs["business"]["groups"][0]
        self.assertIn("聯絡方式", [f["name"] for f in homeroom["fields"]], "自訂欄位沒被加進去")
        self.assertIn("#轉學", homeroom["tags"])
        self.assertTrue(tabs["business"]["groups"][2]["custom"], "清單外的業務要標記 custom")

    def test_builds_data_skeleton(self):
        for rel in ("data/roster.csv", "data/class/observations.md",
                    "data/students/S-01/observations.md", "data/students/S-03/observations.md",
                    "data/courses/main-block/records.md", "data/business/club/records.md"):
            self.assertTrue(os.path.exists(os.path.join(self.tmp, rel)), "缺 " + rel)
        self.assertEqual(read(os.path.join(self.tmp, "data", "roster.csv")).strip(),
                         "編號,姓名")
        head = read(os.path.join(self.tmp, "data", "students", "S-01", "observations.md"))
        self.assertIn("S-01", head)
        self.assertNotIn("{{ID}}", head)
        self.assertNotIn("範例）", head, "骨架不該把範例紀錄一起複製進去")

    def test_generated_files_and_progress(self):
        for rel in ("site/js/kit-config.js", "site/js/firebase-config.js", "firestore.rules",
                    "setup/progress.json"):
            self.assertTrue(os.path.exists(os.path.join(self.tmp, rel)), "缺 " + rel)
        pg = load_json(os.path.join(self.tmp, "setup", "progress.json"))
        self.assertEqual(len(pg["steps"]), 11)
        self.assertTrue(pg["steps"][4]["done"], "第 4 步（產生設定與規則）應該被標成完成")

    def test_rerun_does_not_clobber_records(self):
        p = os.path.join(self.tmp, "data", "students", "S-02", "observations.md")
        with open(p, "a", encoding="utf-8") as f:
            f.write("\n## 2026-09-10 #課堂\n不能被蓋掉的一則\n")
        r = run("setup.py", "--answers", os.path.join(PKG, "templates", "answers.example.json"),
                "--root", self.tmp, "--skip-network", "--skip-doctor")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("不能被蓋掉的一則", read(p))

    def test_doctor_json_is_valid(self):
        r = run("doctor.py", "--root", self.tmp, "--skip-network", "--json")
        data = json.loads(r.stdout)
        self.assertIn("items", data)
        self.assertTrue(all({"key", "label", "ok", "required"} <= set(i) for i in data["items"]))
        keys = {i["key"]: i for i in data["items"]}
        self.assertTrue(keys["cfg_kit"]["ok"])
        self.assertTrue(keys["gen_rules"]["ok"])
        self.assertTrue(keys["gcloud_auth"]["skipped"], "--skip-network 應該跳過連網項目")

    def test_upgrade_from_v2_yaml(self):
        tmp2 = tempfile.mkdtemp(prefix="trk-upgrade-")
        try:
            write(os.path.join(tmp2, "config.yaml"),
                'owner_email: "teacher@example.com"\n'
                'id_prefix: "5A"\n'
                'firebase:\n'
                '  project_id: "old-project"\n'
                '  api_key: "KEY123"\n')
            r = run("setup.py", "--upgrade", "--root", tmp2, "--skip-network", "--skip-doctor")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            kit = load_json(os.path.join(tmp2, "config", "kit.json"))
            self.assertEqual(kit["owner_email"], "teacher@example.com")
            self.assertEqual(kit["id_prefix"], "5A")
            self.assertEqual(kit["firebase"]["project_id"], "old-project")
            self.assertEqual(kit["firebase"]["auth_domain"], "old-project.firebaseapp.com")
        finally:
            shutil.rmtree(tmp2, ignore_errors=True)


class TestAppendAndLedger(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="trk-append-")
        r = run("setup.py", "--answers", os.path.join(PKG, "templates", "answers.example.json"),
                "--root", self.tmp, "--skip-network", "--skip-doctor")
        assert r.returncode == 0, r.stdout + r.stderr
        write(os.path.join(self.tmp, "data", "roster.csv"), "編號,姓名\n01,測試甲\n02,測試乙\n03,測試丙\n")
        self.draft = os.path.join(self.tmp, "draft.md")
        write(self.draft, "今天 S-03 主動舉手兩次。")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def append(self, *args):
        return run("append_record.py", "--root", self.tmp, *args)

    def test_append_students(self):
        r = self.append("--kind", "students", "--target", "S-01", "--date", "2026-09-10",
                        "--tags", "#課堂 人際", "--content-file", self.draft, "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(out["rid"], "2026-09-10")
        text = read(os.path.join(self.tmp, "data", "students", "S-01", "observations.md"))
        self.assertIn("## 2026-09-10 #課堂 #人際", text)
        self.assertIn("今天 S-03 主動舉手兩次。", text)
        audit = read(os.path.join(self.tmp, "data", "audit.jsonl")).strip()
        self.assertEqual(json.loads(audit)["op"], "append")

    def test_second_record_same_day_gets_time(self):
        self.append("--kind", "students", "--target", "S-01", "--date", "2026-09-10",
                    "--content-file", self.draft)
        r = self.append("--kind", "students", "--target", "S-01", "--date", "2026-09-10",
                        "--time", "14:35", "--content-file", self.draft, "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout.strip().splitlines()[-1])["rid"], "2026-09-10-1435")
        _, blocks = lib.parse_file(os.path.join(self.tmp, "data", "students", "S-01", "observations.md"))
        self.assertEqual([b["rid"] for b in blocks], ["2026-09-10", "2026-09-10-1435"])

    def test_existing_rids_never_change(self):
        for d in ("2026-09-01", "2026-09-02", "2026-09-03"):
            self.append("--kind", "courses", "--target", "main-block", "--date", d,
                        "--content-file", self.draft)
        path = os.path.join(self.tmp, "data", "courses", "main-block", "records.md")
        before = [b["rid"] for b in lib.parse_file(path)[1]]
        self.append("--kind", "courses", "--target", "main-block", "--date", "2026-09-04",
                    "--content-file", self.draft)
        after = [b["rid"] for b in lib.parse_file(path)[1]]
        self.assertEqual(after[:len(before)], before)
        self.assertEqual(len(after), len(before) + 1)

    def test_business_fields_and_related(self):
        r = self.append("--kind", "business", "--target", "meetings", "--date", "2026-09-10",
                        "--fields-json", json.dumps({"會議名稱": "學年會議", "決議": "下週再議"},
                                                    ensure_ascii=False),
                        "--related", "students/S-03/2026-09-10; courses/main-block/2026-09-09",
                        "--content-file", self.draft)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        _, blocks = lib.parse_file(os.path.join(self.tmp, "data", "business", "meetings", "records.md"))
        self.assertEqual(blocks[-1]["fields"], {"會議名稱": "學年會議", "決議": "下週再議"})
        self.assertEqual(blocks[-1]["related"],
                         ["students/S-03/2026-09-10", "courses/main-block/2026-09-09"])

    def test_real_name_is_blocked(self):
        bad = os.path.join(self.tmp, "bad.md")
        write(bad, "今天測試丙上課很專心。")
        r = self.append("--kind", "students", "--target", "S-03", "--content-file", bad)
        self.assertEqual(r.returncode, 5, r.stdout + r.stderr)
        self.assertIn("測試丙", r.stderr)
        self.assertIn("→", r.stderr)
        text = read(os.path.join(self.tmp, "data", "students", "S-03", "observations.md"))
        self.assertNotIn("測試丙", text)

    def test_allow_names_override_is_audited(self):
        bad = os.path.join(self.tmp, "bad.md")
        write(bad, "測試丙的家長來電。")
        r = self.append("--kind", "business", "--target", "homeroom", "--content-file", bad,
                        "--allow-names")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        entries = [json.loads(l) for l in
                   read(os.path.join(self.tmp, "data", "audit.jsonl")).splitlines() if l.strip()]
        self.assertTrue(entries[-1]["allowNames"])

    def test_unknown_target_is_refused(self):
        r = self.append("--kind", "business", "--target", "不存在的組", "--content-file", self.draft)
        self.assertEqual(r.returncode, 3)
        self.assertIn("→", r.stderr)

    def test_bad_related_is_refused(self):
        r = self.append("--kind", "students", "--target", "S-01",
                        "--related", "S-03", "--content-file", self.draft)
        self.assertEqual(r.returncode, 2)

    def test_ledger_rebuild(self):
        self.append("--kind", "students", "--target", "S-01", "--date", "2026-09-10",
                    "--content-file", self.draft)
        self.append("--kind", "business", "--target", "meetings", "--date", "2026-09-11",
                    "--content-file", self.draft)
        r = run("ledger.py", "--root", self.tmp, "--rebuild")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rows = [json.loads(l) for l in
                read(os.path.join(self.tmp, "data", "ledger.jsonl")).splitlines() if l.strip()]
        self.assertEqual(len(rows), 2)
        self.assertEqual({r_["kind"] for r_ in rows}, {"students", "business"})
        self.assertTrue(all(r_["local"] and r_["cloud"] is None for r_ in rows))

    def test_ledger_check_offline(self):
        self.append("--kind", "students", "--target", "S-01", "--content-file", self.draft)
        r = run("ledger.py", "--root", self.tmp, "--check", "--offline", "--json")
        data = json.loads(r.stdout)
        self.assertIn("rows", data)
        row = [x for x in data["rows"] if x["target"] == "students/S-01"][0]
        self.assertEqual(row["local"], 1)
        self.assertIsNone(row["cloud"])


class TestLedgerAgainstTemplates(unittest.TestCase):
    """用 templates/ 的範例檔當資料，確認台帳讀得出那些示範紀錄。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="trk-tpl-")
        os.makedirs(os.path.join(self.tmp, "config"))
        dump_json(os.path.join(self.tmp, "config", "kit.json"),
                  {"owner_email": "t@example.com", "id_prefix": "S", "firebase": {"project_id": "p"}})
        dump_json(os.path.join(self.tmp, "config", "tabs.json"),
                  {"students": {"enabled": True}, "courses": {"enabled": False},
                   "business": {"enabled": True, "groups": [{"id": "paperwork", "label": "公文"}]}})
        d = os.path.join(self.tmp, "data", "business", "paperwork")
        os.makedirs(d)
        shutil.copy(os.path.join(PKG, "templates", "business-records.example.md"),
                    os.path.join(d, "records.md"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_rebuild_reads_template_records(self):
        r = run("ledger.py", "--root", self.tmp, "--rebuild")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rows = [json.loads(l) for l in
                read(os.path.join(self.tmp, "data", "ledger.jsonl")).splitlines() if l.strip()]
        self.assertEqual([x["rid"] for x in rows], ["2026-09-10", "2026-09-12-1435"])
        self.assertEqual(rows[0]["related"], ["courses/main-block/2026-09-09-1435"])


class TestHelpAndHygiene(unittest.TestCase):
    SCRIPTS = ["setup.py", "build_config.py", "doctor.py", "sync.py", "append_record.py",
               "transcribe.py", "backup.py", "ledger.py", "export_records.py",
               "parent_email.py", "pending.py", "monthly_reminder.py"]

    def test_help_runs(self):
        for s in self.SCRIPTS:
            with self.subTest(script=s):
                r = run(s, "--help")
                self.assertEqual(r.returncode, 0, s + "：" + r.stderr)
                self.assertIn("usage", r.stdout.lower())

    def test_no_hardcoded_personal_data(self):
        """腳本與設定裡不准出現任何真實信箱或某一個班級的專屬邏輯。"""
        pat = re.compile(r"[A-Za-z0-9._%+-]+@(?!example\.com|gmail\.com\b)"
                         r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
        for folder in ("scripts", "config", "templates"):
            for root_, _dirs, files in os.walk(os.path.join(PKG, folder)):
                if "__pycache__" in root_:
                    continue
                for f in files:
                    if not f.endswith((".py", ".sh", ".json", ".md", ".csv")):
                        continue
                    p = os.path.join(root_, f)
                    text = read(p)
                    hits = [h for h in pat.findall(text) if not h.endswith(("example.com",))]
                    self.assertFalse(hits, "%s 裡有看起來像真實信箱的字串：%s" % (p, hits))


if __name__ == "__main__":
    unittest.main()
