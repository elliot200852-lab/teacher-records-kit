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
        """範本的 streams／groups 都是空陣列（零預設）——這也要算合法設定。"""
        tabs = load_json(os.path.join(PKG, "config", "tabs.example.json"))
        self.assertEqual(tabs["students"]["streams"], [], "範本不該預設勾任何記錄類型")
        self.assertEqual(tabs["business"]["groups"], [], "範本不該預設勾任何業務組")
        self.assertEqual(sorted(tabs["students"]["help"]), ["ai", "prepare", "what"])
        r = run("build_config.py", "--check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_check_lists_what_is_chosen(self):
        os.makedirs(os.path.join(self.tmp, "config"))
        dump_json(os.path.join(self.tmp, "config", "kit.json"),
                  {"owner_email": "t@example.com", "id_prefix": "S",
                   "firebase": {k: "x" for k in ("project_id", "api_key", "auth_domain",
                                                 "storage_bucket", "messaging_sender_id", "app_id")}})
        dump_json(os.path.join(self.tmp, "config", "tabs.json"),
                  {"students": {"enabled": True, "streams": [
                      {"id": "case", "label": "個案追蹤", "scope": "case"}]},
                   "courses": {"enabled": False},
                   "business": {"enabled": True, "groups": [{"id": "meetings", "label": "會議紀錄"}]}})
        r = run("build_config.py", "--root", self.tmp, "--check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("個案追蹤", r.stdout)
        self.assertIn("會議紀錄", r.stdout)

    def test_bad_stream_is_refused(self):
        os.makedirs(os.path.join(self.tmp, "config"))
        dump_json(os.path.join(self.tmp, "config", "kit.json"),
                  {"owner_email": "t@example.com", "firebase": {}})
        for streams, why in [
            ([{"id": "個案", "scope": "case"}], "id 不是英數"),
            ([{"id": "case", "scope": "someone"}], "scope 不合法"),
            ([{"id": "case", "scope": "case"}, {"id": "case", "scope": "class"}], "id 重複"),
        ]:
            with self.subTest(why=why):
                dump_json(os.path.join(self.tmp, "config", "tabs.json"),
                          {"students": {"enabled": True, "streams": streams},
                           "courses": {"enabled": False}, "business": {"enabled": False}})
                r = run("build_config.py", "--root", self.tmp, "--check")
                self.assertEqual(r.returncode, 1, why + "：應該擋下來")
                self.assertIn("→", r.stderr)

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
        self.assertTrue(payload["studentStreamLibrary"], "學生記錄類型庫是空的")
        self.assertFalse([s_ for s_ in payload["studentStreamLibrary"] if s_.get("open")],
                         "「我的類型不在清單裡」是安裝時的選項，不該出現在網頁的類型庫")
        self.assertEqual([s_["id"] for s_ in payload["studentStreamLibrary"]][:2],
                         ["homeroom", "subject"])
        with open(os.path.join(PKG, "VERSION"), encoding="utf-8") as f:
            self.assertEqual(payload["version"], f.read().strip(), "window.KIT.version 要來自 VERSION 檔")
        self.assertFalse(payload["idPrefix"].endswith("-"))  # 不含尾綴，網頁自己補 -
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
        streams = tabs["students"]["streams"]
        self.assertEqual([s["id"] for s in streams], ["homeroom", "case"],
                         "答案檔勾了哪兩種就寫哪兩種，不多不少")
        by_id = {s["id"]: s for s in streams}
        self.assertEqual(by_id["case"]["scope"], "case")
        self.assertEqual(by_id["homeroom"]["scope"], "class")
        self.assertIn("校內協同", [f["name"] for f in by_id["case"]["fields"]],
                      "那一種類型的自訂欄位沒被加進去")
        self.assertIn("#班級事務", by_id["homeroom"]["tags"])
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
        head = read(os.path.join(self.tmp, "data", "students", "S-01", "observations.md"))
        self.assertIn("S-01", head)
        self.assertNotIn("{{ID}}", head)
        self.assertNotIn("{{STREAM}}", head)
        self.assertNotIn("範例）", head, "骨架不該把範例紀錄一起複製進去")

    def test_case_stream_only_for_listed_students(self):
        """答案檔把 S-02 列入個案追蹤 → 只有他有 case.md，名冊第三欄也記著。"""
        self.assertTrue(os.path.exists(os.path.join(self.tmp, "data", "students", "S-02", "case.md")))
        for sid in ("S-01", "S-03"):
            self.assertFalse(os.path.exists(os.path.join(self.tmp, "data", "students", sid, "case.md")),
                             sid + " 沒被列入個案追蹤，不該有 case.md")
        roster = read(os.path.join(self.tmp, "data", "roster.csv")).strip().splitlines()
        self.assertEqual(roster[0], "代號,姓名,類型")
        self.assertIn("S-02,,case", roster)
        self.assertIn("S-01,,", roster)
        case_head = read(os.path.join(self.tmp, "data", "students", "S-02", "case.md"))
        self.assertIn("個案追蹤", case_head)
        self.assertNotIn("{{STREAM}}", case_head)

    def test_generated_files_and_progress(self):
        for rel in ("site/js/kit-config.js", "site/js/firebase-config.js", "firestore.rules",
                    "setup/progress.json"):
            self.assertTrue(os.path.exists(os.path.join(self.tmp, rel)), "缺 " + rel)
        pg = load_json(os.path.join(self.tmp, "setup", "progress.json"))
        self.assertEqual(len(pg["steps"]), 11)
        self.assertFalse(pg["steps"][4]["done"],
                         "第 4 步含 firebase deploy，安裝精靈不部署，所以不能標成完成")
        self.assertIn("規則尚未部署", pg["steps"][4]["notes"])
        self.assertTrue(pg["steps"][3]["done"], "第 3 步（分頁與向度）該標完成")

    def test_mark_step_marks_it_done(self):
        """部署是 AI 代理做的，做完用 --mark-step 標記——只動 progress.json。"""
        tmp2 = tempfile.mkdtemp(prefix="trk-mark-")
        try:
            r = run("setup.py", "--root", tmp2, "--mark-step", "4", "--note", "已部署規則")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            pg = load_json(os.path.join(tmp2, "setup", "progress.json"))
            self.assertTrue(pg["steps"][4]["done"])
            self.assertEqual(pg["steps"][4]["notes"], "已部署規則")
            self.assertFalse(os.path.exists(os.path.join(tmp2, "config", "kit.json")),
                             "--mark-step 只動進度檔，不該產生別的東西")
            r = run("setup.py", "--root", tmp2, "--mark-step", "99")
            self.assertEqual(r.returncode, 1, "步驟編號超出範圍要擋下來")
        finally:
            shutil.rmtree(tmp2, ignore_errors=True)

    def test_kit_config_has_stream_library_and_version(self):
        text = read(os.path.join(self.tmp, "site", "js", "kit-config.js"))
        payload = json.loads(text.split("window.KIT = ", 1)[1].rstrip().rstrip(";"))
        self.assertIn("studentStreamLibrary", payload)
        self.assertIn("version", payload)
        self.assertEqual([s["id"] for s in payload["tabs"]["students"]["streams"]],
                         ["homeroom", "case"])

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

    def test_doctor_reports_version(self):
        r = run("doctor.py", "--root", self.tmp, "--skip-network", "--json")
        data = json.loads(r.stdout)
        with open(os.path.join(PKG, "VERSION"), encoding="utf-8") as f:
            self.assertEqual(data["version"], f.read().strip())
        keys = {i["key"]: i for i in data["items"]}
        self.assertTrue(keys["version"]["ok"])
        self.assertTrue(keys["cloud_version"]["skipped"], "--skip-network 要跳過比對雲端版本")
        self.assertIn("個案追蹤", keys["streams"]["detail"])

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
            tabs = load_json(os.path.join(tmp2, "config", "tabs.json"))
            self.assertEqual([s["id"] for s in tabs["students"]["streams"]], ["homeroom"],
                             "v2 的 observations.md 就是導師班級紀錄，升級要勾起來才看得見舊資料")
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
        write(os.path.join(self.tmp, "data", "roster.csv"),
              "代號,姓名,類型\n01,測試甲,\n02,測試乙,case\n03,測試丙,\n")
        self.draft = os.path.join(self.tmp, "draft.md")
        write(self.draft, "今天 S-03 主動舉手兩次。")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def append(self, *args):
        return run("append_record.py", "--root", self.tmp, *args)

    def test_append_students(self):
        r = self.append("--kind", "students", "--target", "S-01", "--stream", "homeroom",
                        "--date", "2026-09-10",
                        "--tags", "#課堂 人際", "--content-file", self.draft, "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        out = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertEqual(out["rid"], "2026-09-10")
        self.assertEqual(out["stream"], "homeroom")
        text = read(os.path.join(self.tmp, "data", "students", "S-01", "observations.md"))
        self.assertIn("## 2026-09-10 #課堂 #人際", text)
        self.assertIn("今天 S-03 主動舉手兩次。", text)
        audit = read(os.path.join(self.tmp, "data", "audit.jsonl")).strip()
        self.assertEqual(json.loads(audit)["op"], "append")
        self.assertEqual(json.loads(audit)["stream"], "homeroom")

    def test_second_record_same_day_gets_time(self):
        self.append("--kind", "students", "--target", "S-01", "--stream", "homeroom",
                    "--date", "2026-09-10", "--content-file", self.draft)
        r = self.append("--kind", "students", "--target", "S-01", "--stream", "homeroom",
                        "--date", "2026-09-10",
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
        r = self.append("--kind", "students", "--target", "S-03", "--stream", "homeroom",
                        "--content-file", bad)
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
        r = self.append("--kind", "students", "--target", "S-01", "--stream", "homeroom",
                        "--related", "S-03", "--content-file", self.draft)
        self.assertEqual(r.returncode, 2)

    def test_ledger_rebuild(self):
        self.append("--kind", "students", "--target", "S-01", "--stream", "homeroom",
                    "--date", "2026-09-10", "--content-file", self.draft)
        self.append("--kind", "business", "--target", "meetings", "--date", "2026-09-11",
                    "--content-file", self.draft)
        r = run("ledger.py", "--root", self.tmp, "--rebuild")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rows = [json.loads(l) for l in
                read(os.path.join(self.tmp, "data", "ledger.jsonl")).splitlines() if l.strip()]
        self.assertEqual(len(rows), 2)
        self.assertEqual({r_["kind"] for r_ in rows}, {"students", "business"})
        self.assertTrue(all(r_["local"] and r_["cloud"] is None for r_ in rows))
        by_kind = {r_["kind"]: r_ for r_ in rows}
        self.assertEqual(by_kind["students"]["stream"], "homeroom", "台帳每一行要記是哪一種類型")
        self.assertIsNone(by_kind["business"]["stream"])

    def test_ledger_check_offline(self):
        self.append("--kind", "students", "--target", "S-01", "--stream", "homeroom",
                    "--content-file", self.draft)
        r = run("ledger.py", "--root", self.tmp, "--check", "--offline", "--json")
        data = json.loads(r.stdout)
        self.assertIn("rows", data)
        row = [x for x in data["rows"] if x["target"] == "students/S-01/homeroom"][0]
        self.assertEqual(row["local"], 1)
        self.assertIsNone(row["cloud"])

    # ── 記錄類型（stream）──────────────────────────────────────────────
    def test_students_without_stream_is_refused(self):
        """混在一起就分不清楚——所以學生記錄一定要指定類型，而且要把可用的列出來。"""
        r = self.append("--kind", "students", "--target", "S-01", "--content-file", self.draft)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("--stream", r.stderr)
        self.assertIn("homeroom", r.stderr)
        self.assertIn("case", r.stderr)
        self.assertIn("→", r.stderr)

    def test_unknown_stream_is_refused(self):
        r = self.append("--kind", "students", "--target", "S-01", "--stream", "iep",
                        "--content-file", self.draft)
        self.assertEqual(r.returncode, 3)
        self.assertIn("homeroom", r.stderr)

    def test_case_stream_writes_its_own_file(self):
        r = self.append("--kind", "students", "--target", "S-02", "--stream", "case",
                        "--date", "2026-09-10",
                        "--fields-json", json.dumps({"來源": "導師轉介"}, ensure_ascii=False),
                        "--content-file", self.draft, "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = read(os.path.join(self.tmp, "data", "students", "S-02", "case.md"))
        self.assertIn("來源：導師轉介", text)
        obs = read(os.path.join(self.tmp, "data", "students", "S-02", "observations.md"))
        self.assertNotIn("來源：導師轉介", obs, "個案那一則不該跑進班級紀錄檔")

    def test_case_stream_refuses_student_not_listed(self):
        """S-01 沒被列入個案追蹤（名冊第三欄是空的）→ 不能寫。"""
        r = self.append("--kind", "students", "--target", "S-01", "--stream", "case",
                        "--content-file", self.draft)
        self.assertEqual(r.returncode, 3)
        self.assertIn("→", r.stderr)

    def test_class_stream_defaults_when_unambiguous(self):
        r = self.append("--kind", "class", "--content-file", self.draft, "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(r.stdout.strip().splitlines()[-1])["stream"], "homeroom")

    def test_stream_is_rejected_for_business(self):
        r = self.append("--kind", "business", "--target", "meetings", "--stream", "case",
                        "--content-file", self.draft)
        self.assertEqual(r.returncode, 2)

    def test_export_filters_by_stream(self):
        self.append("--kind", "students", "--target", "S-01", "--stream", "homeroom",
                    "--date", "2026-09-10", "--content-file", self.draft)
        self.append("--kind", "students", "--target", "S-02", "--stream", "case",
                    "--date", "2026-09-11", "--content-file", self.draft)
        r = run("export_records.py", "--root", self.tmp, "--local", "--stream", "case", "--json")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        data = json.loads(r.stdout)
        self.assertEqual([(t["id"], t["stream"]) for t in data["targets"]], [("S-02", "case")])
        self.assertEqual(len(data["targets"][0]["records"]), 1)
        r = run("export_records.py", "--root", self.tmp, "--local", "--stream", "iep", "--json")
        self.assertEqual(r.returncode, 1, "沒有這種類型要報錯，不要靜靜地匯出空的")

    def test_export_all_streams(self):
        self.append("--kind", "students", "--target", "S-02", "--stream", "case",
                    "--date", "2026-09-11", "--content-file", self.draft)
        r = run("export_records.py", "--root", self.tmp, "--local", "--kind", "students", "--json")
        data = json.loads(r.stdout)
        keys = {(t["id"], t["stream"]) for t in data["targets"]}
        self.assertIn(("S-02", "case"), keys)
        self.assertIn(("S-02", "homeroom"), keys)


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


class TestSyncRosterStreams(unittest.TestCase):
    """名冊第三欄（哪些學生列入哪些個案型類型）的雙向規則，零網路：把 lib 的兩支
    Firestore 呼叫換掉就好。守的是「兩邊都改就不覆蓋」——跟記錄的衝突規則一致。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="trk-roster-")
        os.makedirs(os.path.join(self.tmp, "data"))
        write(os.path.join(self.tmp, "data", "roster.csv"),
              "代號,姓名,類型\nS-01,測試甲,case\nS-02,測試乙,\n")
        self.old_root = lib.root()
        lib.set_root(self.tmp)
        self.orig = (lib.get_doc, lib.http)

    def tearDown(self):
        lib.get_doc, lib.http = self.orig
        lib.set_root(self.old_root)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call(self, cloud_students, baseline):
        import sync
        pushed, notes = [], []
        lib.get_doc = lambda base, path, tok, **kw: ({"students": cloud_students}, "t0")
        lib.http = lambda m, base, path, tok, body=None, **kw: pushed.append((path, body)) or {}
        state = {"_roster": {"streams": baseline}} if baseline is not None else {}
        out = sync.sync_roster({"id_prefix": "S"}, "base", "tok", state, False, notes)
        return out, pushed, notes

    def roster_text(self):
        return read(os.path.join(self.tmp, "data", "roster.csv"))

    def test_web_added_student_to_stream_is_written_back(self):
        cloud = [{"id": "S-01", "name": "測試甲", "streams": ["case"]},
                 {"id": "S-02", "name": "測試乙", "streams": ["case"]}]      # 網頁把 S-02 列入了
        out, pushed, notes = self.call(cloud, {"S-01": ["case"], "S-02": []})
        self.assertIn("S-02,測試乙,case", self.roster_text(), "網頁上的列入沒回寫第三欄")
        self.assertEqual(out["S-02"], ["case"])
        self.assertTrue(any("寫回" in n for n in notes))

    def test_local_change_is_pushed(self):
        cloud = [{"id": "S-01", "name": "測試甲", "streams": []},
                 {"id": "S-02", "name": "測試乙", "streams": []}]
        out, pushed, notes = self.call(cloud, {"S-01": [], "S-02": []})
        self.assertIn("S-01,測試甲,case", self.roster_text(), "本機那邊不該被動到")
        students = dict((p, b) for p, b in pushed)["roster/main"]["students"]
        self.assertEqual([s for s in students if s["id"] == "S-01"][0]["streams"], ["case"])

    def test_both_changed_is_a_conflict_and_nothing_is_overwritten(self):
        cloud = [{"id": "S-01", "name": "測試甲", "streams": ["iep"]},        # 網頁改成 iep
                 {"id": "S-02", "name": "測試乙", "streams": []}]
        out, pushed, notes = self.call(cloud, {"S-01": [], "S-02": []})       # 本機改成 case
        self.assertIn("S-01,測試甲,case", self.roster_text(), "衝突時本機檔不能被改")
        students = dict((p, b) for p, b in pushed)["roster/main"]["students"]
        self.assertEqual([s for s in students if s["id"] == "S-01"][0]["streams"], ["iep"],
                         "衝突時雲端也要維持原樣")
        self.assertTrue(any("衝突" in n for n in notes), notes)

    def test_web_only_student_is_not_deleted(self):
        cloud = [{"id": "S-01", "name": "測試甲", "streams": ["case"]},
                 {"id": "S-02", "name": "測試乙", "streams": []},
                 {"id": "S-09", "name": "網頁加的", "streams": ["case"]}]
        out, pushed, notes = self.call(cloud, {"S-01": ["case"], "S-02": []})
        students = dict((p, b) for p, b in pushed)["roster/main"]["students"]
        self.assertIn("S-09", [s["id"] for s in students], "網頁上多出來的學生不能被靜默刪掉")
        self.assertTrue(any("S-09" in n for n in notes))


class TestSyncWebAdditions(unittest.TestCase):
    """網頁上臨時加的記錄類型／業務組：只提醒，不自動改 config。"""

    def setUp(self):
        self.orig = (lib.get_doc, lib.list_docs)

    def tearDown(self):
        lib.get_doc, lib.list_docs = self.orig

    def test_reports_unknown_stream_and_group(self):
        import sync
        lib.get_doc = lambda *a, **kw: ({"studentStreams": [
            {"id": "homeroom", "label": "導師班級學生紀錄"},
            {"id": "mentoring", "label": "小老師制"}]}, "t0")
        lib.list_docs = lambda base, path, tok, **kw: [("meetings", {"label": "會議紀錄"}, "t"),
                                                       ("club", {"label": "社團"}, "t")]
        notes = []
        tabs = {"students": {"enabled": True, "streams": [{"id": "homeroom", "scope": "class"}]},
                "business": {"enabled": True, "groups": [{"id": "meetings"}]}}
        sync.check_web_additions(tabs, "base", "tok", notes)
        self.assertEqual(len(notes), 2, notes)
        self.assertTrue(any("小老師制" in n and "config/tabs.json 沒有" in n for n in notes))
        self.assertTrue(any("社團" in n for n in notes))


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
