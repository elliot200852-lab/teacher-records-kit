#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""端到端測試：安裝精靈、設定產生器、健檢、台帳、寫入通道。全部在暫存目錄裡跑，零網路。

    python3 -m unittest discover scripts/tests

每一個 test 都用 `--root <暫存目錄>`，所以不會碰到你自己的 config/ 與 data/。
"""
import io
import os
import re
import sys
import json
import shutil
import unittest
import tempfile
import subprocess
import contextlib

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
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300, **kw)


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
        r = run("build_config.py", "--check", "--allow-placeholders")
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
        r = run("build_config.py", "--root", self.tmp, "--allow-placeholders")
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
        self.assertEqual([s_["id"] for s_ in payload["studentStreamLibrary"]][:3],
                         ["qualitative", "homeroom", "subject"])
        self.assertTrue(payload["reportFormats"], "期末報告格式庫要跟著送到網頁")
        self.assertTrue(payload["verticals"], "三個垂直方案要跟著送到網頁")
        with open(os.path.join(PKG, "VERSION"), encoding="utf-8") as f:
            self.assertEqual(payload["version"], f.read().strip(), "window.KIT.version 要來自 VERSION 檔")
        self.assertFalse(payload["idPrefix"].endswith("-"))  # 不含尾綴，網頁自己補 -
        fb = read(fbjs)
        self.assertIn("window.FIREBASE_CONFIG", fb)
        self.assertIn("window.OWNER_EMAIL", fb)
        self.assertNotIn("export ", fb, "firebase-config.js 不能是 module")
        self.assertNotIn("{{OWNER_EMAIL}}", read(rules))

    def _kit(self, **over):
        os.makedirs(os.path.join(self.tmp, "config"), exist_ok=True)
        kit = {"owner_email": "TEACHER@example.com", "id_prefix": "S",
               "firebase": {"project_id": "real-project", "api_key": "AIzaKEY",
                            "auth_domain": "", "storage_bucket": "b",
                            "messaging_sender_id": "1", "app_id": "a"}}
        kit.update(over)
        dump_json(os.path.join(self.tmp, "config", "kit.json"), kit)
        dump_json(os.path.join(self.tmp, "config", "tabs.json"),
                  {"students": {"enabled": True, "streams": []},
                   "courses": {"enabled": True, "list": []},
                   "business": {"enabled": False, "groups": []}})
        return kit

    def test_hostile_owner_email_cannot_reach_the_rules(self):
        """`x'||true||'…@…` 混進規則的單引號字串裡，isOwner() 就變成恆真＝誰都寫得進資料庫。"""
        self._kit(owner_email="x'||true||'y@example.com")
        r = run("build_config.py", "--root", self.tmp)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("owner_email", r.stderr)
        self.assertIn("→", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "firestore.rules")),
                         "擋下來的設定不該產生任何檔")
        for bad in ("a\\'b@example.com", 'a"b@example.com', "a b@example.com"):
            with self.subTest(email=bad):
                self._kit(owner_email=bad)
                self.assertEqual(run("build_config.py", "--root", self.tmp).returncode, 1)

    def test_owner_email_is_lowercased_in_all_three_outputs(self):
        self._kit()
        r = run("build_config.py", "--root", self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rules = read(os.path.join(self.tmp, "firestore.rules"))
        kitjs = read(os.path.join(self.tmp, "site", "js", "kit-config.js"))
        fbjs = read(os.path.join(self.tmp, "site", "js", "firebase-config.js"))
        self.assertIn("teacher@example.com", rules)
        self.assertNotIn("TEACHER@example.com", rules + kitjs + fbjs)
        self.assertIn('"ownerEmail": "teacher@example.com"', kitjs)
        self.assertIn('window.OWNER_EMAIL = "teacher@example.com"', fbjs)

    def test_co_owner_emails_reach_rules_and_web(self):
        """co_owner_emails：規則變 `in [...]`、網頁拿到 ownerEmails 清單；去重、小寫、範本值擋下。"""
        self._kit(co_owner_emails=["HELPER@example.com", "helper@example.com", "TEACHER@example.com"])
        r = run("build_config.py", "--root", self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rules = read(os.path.join(self.tmp, "firestore.rules"))
        storage = read(os.path.join(self.tmp, "storage.rules"))
        kitjs = read(os.path.join(self.tmp, "site", "js", "kit-config.js"))
        fbjs = read(os.path.join(self.tmp, "site", "js", "firebase-config.js"))
        self.assertIn("request.auth.token.email in ['teacher@example.com', 'helper@example.com']", rules)
        self.assertIn("request.auth.token.email in ['teacher@example.com', 'helper@example.com']", storage)
        self.assertNotIn("{{OWNER_EMAILS}}", rules + storage)
        self.assertIn('"ownerEmails": [\n    "teacher@example.com",\n    "helper@example.com"\n  ]', kitjs)
        self.assertIn('window.OWNER_EMAILS = ["teacher@example.com", "helper@example.com"];', fbjs)
        # 沒有共同擁有者＝規則只有一個人（跟以前一樣）
        self._kit(co_owner_emails=[])
        self.assertEqual(run("build_config.py", "--root", self.tmp).returncode, 0)
        self.assertIn("in ['teacher@example.com']", read(os.path.join(self.tmp, "firestore.rules")))
        # 惡意字串進 co_owner_emails 一樣擋，不能是清單也擋
        for bad in (["x'||true||'y@example.com"], "helper@example.com"):
            with self.subTest(bad=bad):
                self._kit(co_owner_emails=bad)
                r = run("build_config.py", "--root", self.tmp)
                self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                self.assertIn("co_owner_emails", r.stderr)

    def test_auth_domain_defaults_to_web_app(self):
        """Console 給的 .firebaseapp.com 跟網頁不同源，iPhone 上會一直登不進去。"""
        self._kit()
        self.assertEqual(run("build_config.py", "--root", self.tmp).returncode, 0)
        fbjs = read(os.path.join(self.tmp, "site", "js", "firebase-config.js"))
        self.assertIn('"authDomain": "real-project.web.app"', fbjs)
        kit = self._kit()
        kit["firebase"]["auth_domain"] = "records.example.org"
        dump_json(os.path.join(self.tmp, "config", "kit.json"), kit)
        self.assertEqual(run("build_config.py", "--root", self.tmp).returncode, 0)
        self.assertIn('"authDomain": "records.example.org"',
                      read(os.path.join(self.tmp, "site", "js", "firebase-config.js")),
                      "填了就要照填的（GitHub Pages／嵌入現有站）")

    def test_placeholders_are_a_hard_error(self):
        """範本值產得出檔又 exit 0 的話，老師與 AI 會以為裝好了，其實網頁連不上任何資料庫。"""
        self._kit(owner_email="you@example.com")
        r = run("build_config.py", "--root", self.tmp)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("→", r.stderr)
        self.assertNotIn("下一步", r.stdout)
        r = run("build_config.py", "--root", self.tmp, "--allow-placeholders")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("!", r.stdout, "--allow-placeholders 時要降成提醒，不是靜靜放過")

    def test_placeholder_firebase_values_are_a_hard_error(self):
        kit = self._kit()
        kit["firebase"]["project_id"] = "your-firebase-project-id"
        dump_json(os.path.join(self.tmp, "config", "kit.json"), kit)
        self.assertEqual(run("build_config.py", "--root", self.tmp).returncode, 1)
        kit["firebase"]["project_id"] = "real-project"
        kit["firebase"]["api_key"] = ""
        dump_json(os.path.join(self.tmp, "config", "kit.json"), kit)
        self.assertEqual(run("build_config.py", "--root", self.tmp).returncode, 1)

    def test_bad_course_id_is_refused(self):
        """課程 id 會變成資料夾名（data/courses/<id>/）——`../../oops` 會寫到 data/ 外面去。"""
        os.makedirs(os.path.join(self.tmp, "config"), exist_ok=True)
        dump_json(os.path.join(self.tmp, "config", "kit.json"),
                  {"owner_email": "t@example.com", "firebase": {}})
        for courses, why in [
            ([{"id": "../../oops", "title": "壞的"}], "id 有路徑符號"),
            ([{"id": "主課程", "title": "中文 id"}], "id 不是英數"),
            ([{"id": "main", "title": "一"}, {"id": "main", "title": "二"}], "id 重複"),
            ([{"id": "", "title": "沒有 id"}], "少了 id"),
        ]:
            with self.subTest(why=why):
                dump_json(os.path.join(self.tmp, "config", "tabs.json"),
                          {"students": {"enabled": False}, "business": {"enabled": False},
                           "courses": {"enabled": True, "list": courses}})
                r = run("build_config.py", "--root", self.tmp, "--check")
                self.assertEqual(r.returncode, 1, why + "：應該擋下來")
                self.assertIn("→", r.stderr)

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
        self.assertEqual(roster[0].lstrip("\ufeff"), "代號,姓名,類型")
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
        # 0–10 是原本的安裝步驟，11 是選用的「無頭交辦」（setup.STEP_TITLES 是正本）
        self.assertEqual(len(pg["steps"]), 12)
        self.assertEqual(pg["steps"][11]["title"], "無頭交辦（選用）")
        self.assertTrue(pg["steps"][11]["done"],
                        "答案檔沒開無頭交辦，第 11 步就該標成完成（備註寫沒有開）")
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
            self.assertEqual(kit["firebase"]["auth_domain"], "old-project.web.app",
                             "預設要用 Firebase Hosting 的網址，.firebaseapp.com 在 iPhone 上登不進去")
        finally:
            shutil.rmtree(tmp2, ignore_errors=True)

    def test_upgrade_carries_the_parents_section(self):
        """v2 的家長通訊錄欄位位置不搬過來的話，升級後 parent_email.py 會抓錯欄。"""
        tmp2 = tempfile.mkdtemp(prefix="trk-upgrade2-")
        try:
            write(os.path.join(tmp2, "config.yaml"),
                  'owner_email: "teacher@example.com"\n'
                  'firebase:\n'
                  '  project_id: "old-project"\n'
                  'parents:\n'
                  '  contacts_csv: "data/我的通訊錄.csv"\n'
                  '  col_id: 2\n'
                  '  col_parent1_email: 5\n'
                  '  col_parent2_email: 6\n')
            r = run("setup.py", "--upgrade", "--root", tmp2, "--skip-network", "--skip-doctor")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            parents = load_json(os.path.join(tmp2, "config", "kit.json"))["parents"]
            self.assertEqual(str(parents["col_id"]), "2")
            self.assertEqual(str(parents["col_parent1_email"]), "5")
            self.assertEqual(str(parents["col_parent2_email"]), "6")
            self.assertEqual(parents["contacts_csv"], "data/我的通訊錄.csv")
        finally:
            shutil.rmtree(tmp2, ignore_errors=True)


class TestSetupRerunKeepsHandEdits(unittest.TestCase):
    """重跑安裝＝在現有設定上疊答案。安裝精靈沒問到的區塊（email／voice／parents／drive）
    是老師手填的，用範本值蓋回去等於默默把他的寄信設定與備份夾清掉。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="trk-rerun-")
        self.answers = os.path.join(PKG, "templates", "answers.example.json")
        r = run("setup.py", "--answers", self.answers, "--root", self.tmp,
                "--skip-network", "--skip-doctor")
        assert r.returncode == 0, r.stdout + r.stderr
        kit = load_json(os.path.join(self.tmp, "config", "kit.json"))
        kit["email"] = {"method": "smtp", "smtp_user": "teacher@example.com"}
        kit["parents"] = {"contacts_csv": "data/contacts.csv", "col_id": 2,
                          "col_parent1_email": 5, "col_parent2_email": 6}
        kit["voice"] = {"model": "ggml-medium", "lang": "yue"}
        kit["drive"]["desktop_dir"] = os.path.join(self.tmp, "我的備份夾")
        dump_json(os.path.join(self.tmp, "config", "kit.json"), kit)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_rerun_keeps_hand_edited_sections(self):
        answers = load_json(self.answers)
        answers.pop("email", None)                    # 這一輪的答案沒提到寄信與備份夾
        answers.pop("drive", None)
        path = os.path.join(self.tmp, "answers2.json")
        dump_json(path, answers)
        r = run("setup.py", "--answers", path, "--root", self.tmp,
                "--skip-network", "--skip-doctor")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        kit = load_json(os.path.join(self.tmp, "config", "kit.json"))
        self.assertEqual(kit["email"]["smtp_user"], "teacher@example.com")
        self.assertEqual(kit["parents"]["col_parent1_email"], 5)
        self.assertEqual(kit["voice"]["model"], "ggml-medium")
        self.assertEqual(kit["drive"]["desktop_dir"], os.path.join(self.tmp, "我的備份夾"))

    def test_answers_still_win_over_the_old_file(self):
        answers = load_json(self.answers)
        answers["email"] = {"method": "gws", "smtp_user": ""}
        path = os.path.join(self.tmp, "answers3.json")
        dump_json(path, answers)
        r = run("setup.py", "--answers", path, "--root", self.tmp,
                "--skip-network", "--skip-doctor")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        kit = load_json(os.path.join(self.tmp, "config", "kit.json"))
        self.assertEqual(kit["email"]["method"], "gws")
        self.assertEqual(kit["parents"]["col_id"], 2, "沒回答到的區塊仍然留著")


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

    def test_course_overview_in_md_export_but_not_in_split(self):
        """整體課程紀錄要進 .md 匯出（排在逐日紀錄前面）；`--split` 那一路刻意不變——
        那些檔是台帳要掃 `## YYYY-MM-DD` 的紀錄檔，不該多一段也不該多一個檔。"""
        self.append("--kind", "courses", "--target", "main-block", "--date", "2026-09-10",
                    "--content-file", self.draft)
        dump_json(os.path.join(self.tmp, "data", "courses", "main-block", "card.json"),
                  {"overview": "這門課從觀察月亮開始。"})
        r = run("export_records.py", "--root", self.tmp, "--local", "--kind", "courses")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("整體課程紀錄", r.stdout)
        self.assertIn("這門課從觀察月亮開始。", r.stdout)
        self.assertLess(r.stdout.index("整體課程紀錄"), r.stdout.index("2026-09-10"),
                        "整體課程紀錄要排在逐日紀錄前面")
        out = os.path.join(self.tmp, "split")
        r2 = run("export_records.py", "--root", self.tmp, "--local", "--kind", "courses",
                 "--split", out)
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        d = os.path.join(out, "courses", "main-block")
        self.assertEqual(sorted(os.listdir(d)), ["records.md"], "--split 不該多產檔")
        self.assertNotIn("整體課程紀錄", read(os.path.join(d, "records.md")))

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


class TestSyncWriteCards(unittest.TestCase):
    """卡片摘要（學生卡／課程卡／業務組卡）：只推統計、PATCH 帶前置條件、412 當衝突。

    守的是同一件事——課名／組名是老師在網頁上打的字，腳本不准用 config 的舊名字蓋回去。
    """

    def setUp(self):
        self.orig = (lib.get_doc, lib.http)

    def tearDown(self):
        lib.get_doc, lib.http = self.orig

    def call(self, exists=True, precondition=False):
        import sync
        calls, notes = [], []
        lib.get_doc = lambda base, path, tok, **kw: \
            (({"label": "網頁上改過的組名"}, "t9") if exists else (None, None))

        def fake_http(m, base, path, tok, body=None, **kw):
            calls.append({"path": path, "body": body, "mask": kw.get("mask"),
                          "ut": kw.get("precondition_update_time"),
                          "exists": kw.get("precondition_exists")})
            if precondition:
                raise lib.Precondition(path)
            return {}
        lib.http = fake_http
        cards = {"business/meetings": {"id": "meetings", "kind": "business",
                                       "label": "會議紀錄", "dates": ["2026-09-01", "2026-09-04"],
                                       "streams": {}},
                 "students/S-02": {"id": "S-02", "kind": "students", "label": "S-02（個案追蹤）",
                                   "dates": ["2026-09-05"], "streams": {"case": 1}}}
        sync.write_cards(cards, "base", "tok", notes)
        return {c["path"]: c for c in calls}, notes

    def test_does_not_push_label_over_web(self):
        calls, notes = self.call(exists=True)
        card = calls["business/meetings"]
        self.assertNotIn("label", card["mask"], "組名以網頁為準，不該進 updateMask")
        self.assertNotIn("title", card["mask"] or [])
        self.assertEqual(sorted(card["mask"]),
                         ["id", "lastRecordDate", "monthsRecorded", "recordCount"])
        self.assertEqual(card["body"]["recordCount"], 2)
        self.assertEqual(card["body"]["lastRecordDate"], "2026-09-04")
        self.assertEqual(calls["students/S-02"]["body"]["streamCounts"], {"case": 1})
        self.assertEqual(notes, [])

    def test_patch_carries_precondition(self):
        calls, _ = self.call(exists=True)
        for path, c in calls.items():
            with self.subTest(path=path):
                self.assertEqual(c["ut"], "t9", "PATCH 要帶讀到的 updateTime")

    def test_new_card_is_created_with_label(self):
        """卡片還不存在時才補一次名字（填空白，不是覆寫）——並且帶 exists=false。"""
        calls, _ = self.call(exists=False)
        self.assertEqual(calls["business/meetings"]["body"]["label"], "會議紀錄")
        self.assertIs(calls["business/meetings"]["exists"], False)
        self.assertIsNone(calls["business/meetings"]["ut"])

    def test_412_is_a_note_not_an_overwrite(self):
        calls, notes = self.call(exists=True, precondition=True)
        self.assertEqual(len(notes), 2, notes)
        self.assertTrue(all("衝突 卡片" in n for n in notes), notes)


class TestSyncStateOnlyRemembersTheCloud(unittest.TestCase):
    """同步狀態（data/.sync-state.json）只能記「雲端真的有的那些紀錄 id」。

    記成「本機每一則」的話，被真名閘攔下、被前置條件擋下而沒上傳的那幾則，
    下一輪會被當成「以前同步過、現在雲端沒有」＝網頁上刪了，於是**把老師本機的區塊刪掉**。
    """

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="trk-state-")
        self.old_root = lib.root()
        lib.set_root(self.tmp)
        self.orig = (lib.list_docs, lib.http, lib.get_doc)
        self.path = os.path.join(self.tmp, "data", "students", "S-01", "observations.md")
        os.makedirs(os.path.dirname(self.path))
        write(self.path,
              "# S-01\n\n## 2026-09-01\n\n乾淨的一則。\n\n## 2026-09-02\n\n測試丙今天很專心。\n")
        self.t = {"kind": "students", "id": "S-01", "stream": "homeroom", "scope": "class",
                  "streamLabel": "導師班級學生紀錄", "label": "S-01（導師班級學生紀錄）",
                  "path": self.path, "sourceFile": "students/S-01/observations.md",
                  "records": "students/S-01/records", "card": None,
                  "key": "students/S-01/homeroom"}

    def tearDown(self):
        lib.list_docs, lib.http, lib.get_doc = self.orig
        lib.set_root(self.old_root)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call(self, http):
        import sync
        lib.list_docs = lambda base, path, tok, **kw: []      # 雲端還是空的
        lib.http = http
        notes, counters, cards = [], dict.fromkeys(
            ("push", "write", "new", "delete", "conflict", "pii"), 0), {}
        rids = sync.sync_target(self.t, "base", "tok", ["測試丙"], {}, False,
                                notes, counters, cards)
        return rids, notes, counters

    def test_dry_run_still_accumulates_the_card(self):
        """預演也要累加卡片摘要，否則 `--dry-run` 永遠印不出卡片那一段會發生什麼。"""
        import sync
        lib.list_docs = lambda base, path, tok, **kw: []
        lib.http = lambda *a, **kw: {}
        notes, counters, cards = [], dict.fromkeys(
            ("push", "write", "new", "delete", "conflict", "pii"), 0), {}
        t = dict(self.t, card="students/S-01")
        sync.sync_target(t, "base", "tok", [], {}, True, notes, counters, cards)
        self.assertIn("students/S-01", cards)
        self.assertEqual(cards["students/S-01"]["streams"], {"homeroom": 2})
        self.assertTrue(any("預演" in n for n in notes), notes)

    def test_pii_blocked_record_is_not_remembered(self):
        rids, notes, counters = self.call(lambda *a, **kw: {})
        self.assertEqual(counters["pii"], 1, notes)
        self.assertEqual(rids, {"2026-09-01"},
                         "被真名閘攔下的那一則沒上雲，不可以寫進同步狀態")

    def test_record_that_failed_its_precondition_is_not_remembered(self):
        def boom(*a, **kw):
            raise lib.Precondition("students/S-01/records")
        rids, notes, counters = self.call(boom)
        self.assertEqual(rids, set(), "沒推成功的一則不可以寫進同步狀態")
        self.assertEqual(counters["conflict"], 1)
        self.assertEqual(counters["push"], 0)

    def test_next_run_does_not_delete_the_blocked_record(self):
        """接著跑第二輪：狀態是上一輪的結果，本機那兩則都必須原封不動。"""
        import sync
        rids, _, _ = self.call(lambda *a, **kw: {})
        notes, counters, cards = [], dict.fromkeys(
            ("push", "write", "new", "delete", "conflict", "pii"), 0), {}
        # 第二輪的雲端就是第一輪推上去的那一則（PII 那一則從來沒上去過）
        _, blocks = lib.parse_file(self.path)
        clean = [b for b in blocks if b["rid"] == "2026-09-01"][0]
        lib.list_docs = lambda base, path, tok, **kw: [
            ("2026-09-01", {"date": "2026-09-01", "stream": "homeroom", "tags": [],
                            "fields": {}, "related": [], "body": clean["body"],
                            "contentHash": clean["hash"], "editedOnWeb": False}, "t1")]
        lib.http = lambda *a, **kw: {}
        sync.sync_target(self.t, "base", "tok", ["測試丙"],
                         {self.t["key"]: {"rids": sorted(rids)}}, False, notes, counters, cards)
        self.assertEqual(counters["delete"], 0, notes)
        self.assertIn("測試丙", read(self.path))
        self.assertIn("乾淨的一則", read(self.path))


class TestSyncStatusFields(unittest.TestCase):
    """meta/status 不能只寫時間戳：有衝突、有真名攔截的那一輪也會更新時間，
    網頁於是顯示綠燈，而老師其實有幾則沒上去。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="trk-status-")
        self.old_root = lib.root()
        self.orig = (lib.load_kit, lib.load_tabs, lib.token, lib.targets,
                     lib.get_doc, lib.list_docs, lib.http)

    def tearDown(self):
        (lib.load_kit, lib.load_tabs, lib.token, lib.targets,
         lib.get_doc, lib.list_docs, lib.http) = self.orig
        lib.set_root(self.old_root)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_sync_writes_counts_and_last_error(self):
        import sync
        calls = []
        lib.load_kit = lambda *a, **kw: {"owner_email": "t@example.com",
                                         "firebase": {"project_id": "p"}}
        lib.load_tabs = lambda *a, **kw: {"students": {"enabled": False},
                                          "courses": {"enabled": False},
                                          "business": {"enabled": False}}
        lib.token = lambda *a, **kw: "tok"
        lib.targets = lambda *a, **kw: []
        lib.get_doc = lambda base, path, tok, **kw: (None, None)
        lib.list_docs = lambda base, path, tok, **kw: []
        lib.http = lambda m, base, path, tok, body=None, **kw: calls.append((path, body)) or {}
        argv = sys.argv
        sys.argv = ["sync.py", "--root", self.tmp, "--quiet"]
        try:
            sync.main()
        finally:
            sys.argv = argv
        status = dict(calls)["meta/status"]
        self.assertIn("lastSyncAt", status)
        self.assertEqual(status["lastSyncConflicts"], 0)
        self.assertEqual(status["lastSyncPii"], 0)
        self.assertEqual(status["lastError"], "")


class TestBackupStatusFields(unittest.TestCase):
    """備份上不了雲端硬碟時，網頁狀態列要說得出原因——不能只更新「上次備份時間」。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="trk-bkstatus-")
        os.makedirs(os.path.join(self.tmp, "data", "students", "S-01"))
        write(os.path.join(self.tmp, "data", "students", "S-01", "observations.md"),
              "# S-01\n\n## 2026-09-01\n\n一則。\n")
        self.old_root = lib.root()
        self.orig = (lib.load_kit, lib.load_tabs, lib.token, lib.http)

    def tearDown(self):
        lib.load_kit, lib.load_tabs, lib.token, lib.http = self.orig
        lib.set_root(self.old_root)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def run_backup(self, drive_ok):
        import backup
        calls = []
        lib.load_kit = lambda *a, **kw: {"owner_email": "t@example.com",
                                         "firebase": {"project_id": "p"},
                                         "drive": {"mode": "desktop", "keep_backups": 3,
                                                   "desktop_dir": os.path.join(self.tmp, "gdrive")}}
        lib.load_tabs = lambda *a, **kw: {"students": {"enabled": True},
                                          "courses": {"enabled": False},
                                          "business": {"enabled": False}}
        lib.token = lambda *a, **kw: "tok"
        lib.http = lambda m, base, path, tok, body=None, **kw: calls.append((path, body)) or {}
        orig = (backup.collect_export, backup.to_desktop)
        backup.collect_export = lambda kit, tabs: ({"records": []}, "")
        backup.to_desktop = (lambda kit, zip_path: ({"path": "x"}, "")) if drive_ok \
            else (lambda kit, zip_path: (None, "找不到同步資料夾"))
        argv = sys.argv
        sys.argv = ["backup.py", "--root", self.tmp, "--quiet"]
        try:
            backup.main()
        finally:
            sys.argv = argv
            backup.collect_export, backup.to_desktop = orig
        return dict(calls).get("meta/status")

    def test_drive_failure_lands_in_last_error(self):
        status = self.run_backup(drive_ok=False)
        self.assertIn("lastBackupAt", status)
        self.assertIn("找不到同步資料夾", status["lastError"])

    def test_success_clears_last_error(self):
        status = self.run_backup(drive_ok=True)
        self.assertEqual(status["lastError"], "")


class TestSyncWebAdditions(unittest.TestCase):
    """網頁上臨時加的記錄類型／業務組：只提醒，不自動改 config。
    課程是例外——它不必動 config 就能成立，所以直接補本機檔（不然那門課永遠下不來）。"""

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

    def web_course(self, dry=False):
        """網頁上開了一門本機沒有的課（art），跑一次檢查；回傳 (tmp, notes)。"""
        import sync
        tmp = tempfile.mkdtemp(prefix="trk-webcourse-")
        old_root = lib.root()
        lib.set_root(tmp)
        self.addCleanup(shutil.rmtree, tmp, True)
        self.addCleanup(lib.set_root, old_root)
        lib.get_doc = lambda *a, **kw: ({}, "t0")
        lib.list_docs = lambda base, path, tok, **kw: (
            [("main-block", {"title": "主課程"}, "t"), ("art", {"title": "藝術"}, "t")]
            if path == "courses" else [])
        notes = []
        tabs = {"students": {"enabled": True, "streams": []},
                "courses": {"enabled": True, "list": [{"id": "main-block", "title": "主課程"}]},
                "business": {"enabled": False}}
        sync.check_web_additions(tabs, "base", "tok", notes, {"main-block"}, dry)
        return tmp, notes

    def test_web_added_course_gets_a_local_file(self):
        """網頁上開的新課要自動補本機檔——lib.targets 認得資料夾，下一輪它就是正式目標。"""
        tmp, notes = self.web_course()
        p = os.path.join(tmp, "data", "courses", "art", "records.md")
        self.assertTrue(os.path.exists(p), "沒建本機檔的話，網頁上那門課的紀錄永遠下不來")
        text = read(p)
        self.assertIn("藝術", text, "檔頭要用網頁上的課名")
        self.assertEqual(len(notes), 1, notes)
        self.assertIn("art", notes[0])
        self.assertFalse(os.path.exists(os.path.join(tmp, "data", "courses", "main-block")),
                         "本機已經有的課不該重建")

    def test_dry_run_only_reports_the_new_course(self):
        tmp, notes = self.web_course(dry=True)
        self.assertFalse(os.path.exists(os.path.join(tmp, "data", "courses", "art")),
                         "--dry-run 不准寫任何東西")
        self.assertEqual(len(notes), 1, notes)
        self.assertIn("預演", notes[0])

    def test_without_the_local_course_list_nothing_is_created(self):
        """沒拿到本機課程清單（course_ids=None）就無從比對——寧可不動，也不要亂建資料夾。"""
        import sync
        tmp = tempfile.mkdtemp(prefix="trk-webcourse-")
        old_root = lib.root()
        lib.set_root(tmp)
        self.addCleanup(shutil.rmtree, tmp, True)
        self.addCleanup(lib.set_root, old_root)
        lib.get_doc = lambda *a, **kw: ({}, "t0")
        lib.list_docs = lambda base, path, tok, **kw: [("art", {"title": "藝術"}, "t")]
        notes = []
        sync.check_web_additions({"students": {"enabled": True, "streams": []},
                                  "courses": {"enabled": True},
                                  "business": {"enabled": False}}, "base", "tok", notes)
        self.assertEqual(notes, [])
        self.assertFalse(os.path.exists(os.path.join(tmp, "data", "courses")))


class TestParentEmail(unittest.TestCase):
    """家長信：--draft 一定不寄；代號比對不能假設「前綴裡沒有數字」。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="trk-parent-")
        os.makedirs(os.path.join(self.tmp, "config"))
        os.makedirs(os.path.join(self.tmp, "data"))
        dump_json(os.path.join(self.tmp, "config", "kit.json"),
                  {"owner_email": "t@example.com", "id_prefix": "6B",
                   "firebase": {"project_id": "p"},
                   "email": {"method": "smtp", "smtp_user": "t@example.com"},
                   "parents": {"contacts_csv": "data/contacts.csv", "col_id": 1,
                               "col_parent1_email": 2, "col_parent2_email": 3}})
        write(os.path.join(self.tmp, "data", "contacts.csv"),
              "座號,家長1,家長2\n01,a@example.com,b@example.com\n02,c@example.com,\n")
        self.body = write(os.path.join(self.tmp, "msg.txt"), "今天他主動幫忙搬桌子。\n")
        self.env = dict(os.environ, TRK_ROOT=self.tmp)
        self.env.pop("KIT_SMTP_APP_PASSWORD", None)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call(self, *args):
        return run("parent_email.py", "--id", "6B-01", "--subject", "課堂觀察",
                   "--body-file", self.body, *args, env=self.env)

    def test_prefix_with_a_digit_still_matches_the_contact_row(self):
        """id_prefix = 6B 時，「只留數字」會把 6B-01 算成 601，通訊錄怎麼比都比不到。"""
        r = self.call("--dry-run")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("2 位家長", r.stdout)
        self.assertNotIn("a@example.com", r.stdout, "stdout 一律遮罩 email")

    def test_draft_with_smtp_never_sends(self):
        """以前這裡會掉下去真的把信寄出去——老師以為只是出稿，信已經到家長信箱了。"""
        r = self.call("--draft")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("沒有寄出", r.stdout)
        self.assertIn("今天他主動幫忙搬桌子。", r.stdout)
        drafts = [f for f in os.listdir(os.path.join(self.tmp, "exports"))]
        self.assertTrue(drafts, "草稿要落地成檔案")
        text = read(os.path.join(self.tmp, "exports", drafts[0]))
        self.assertIn("今天他主動幫忙搬桌子。", text)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, ".parent-emails-handled.tsv")),
                         "沒寄出去就不該記進已寄台帳")


class SoftDeleteBase(unittest.TestCase):
    """兩段式刪除共用的替身：雲端那則只被標成 `deleted: true`，文件還在。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="trk-softdel-")
        self.old_root = lib.root()
        lib.set_root(self.tmp)
        self.orig = (lib.list_docs, lib.http, lib.get_doc, lib.token,
                     lib.targets, lib.delete_doc)
        self.path = os.path.join(self.tmp, "data", "students", "S-01", "observations.md")
        os.makedirs(os.path.dirname(self.path))
        self.t = {"kind": "students", "id": "S-01", "stream": "homeroom", "scope": "class",
                  "streamLabel": "導師班級學生紀錄", "label": "S-01（導師班級學生紀錄）",
                  "path": self.path, "sourceFile": "students/S-01/observations.md",
                  "records": "students/S-01/records", "card": None,
                  "key": "students/S-01/homeroom"}

    def tearDown(self):
        (lib.list_docs, lib.http, lib.get_doc, lib.token,
         lib.targets, lib.delete_doc) = self.orig
        lib.set_root(self.old_root)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def block(self, rid):
        _, blocks = lib.parse_file(self.path)
        return [b for b in blocks if b["rid"] == rid][0]

    def cloud_doc(self, rid, body, hash_="", **extra):
        fs = {"date": rid[:10], "stream": "homeroom", "tags": [], "fields": {},
              "related": [], "body": body, "contentHash": hash_, "editedOnWeb": False}
        fs.update(extra)
        return (rid, fs, "t1")

    def audit_lines(self):
        p = os.path.join(self.tmp, "data", "audit.jsonl")
        if not os.path.exists(p):
            return []
        return [json.loads(x) for x in read(p).splitlines() if x.strip()]


class TestSyncSoftDelete(SoftDeleteBase):
    """網頁刪除＝軟刪：雲端文件留著（`deleted: true`），本機區塊要刪、要記一筆稽核。

    稽核那一行**不可以帶正文**——audit.jsonl 不是紀錄的第二份正本。
    """

    def sync(self, docs, dry=False, state=None):
        import sync
        lib.list_docs = lambda base, path, tok, **kw: list(docs)
        lib.http = lambda *a, **kw: {}
        notes, counters, cards = [], dict.fromkeys(
            ("push", "write", "new", "delete", "conflict", "pii"), 0), {}
        rids = sync.sync_target(self.t, "base", "tok", [], state or {}, dry,
                                notes, counters, cards)
        return rids, notes, counters

    def two_records(self):
        write(self.path, "# S-01\n\n## 2026-09-01\n\n第一則留著。\n\n"
                         "## 2026-09-02\n\n第二則在網頁上刪掉了。\n")
        keep, gone = self.block("2026-09-01"), self.block("2026-09-02")
        docs = [self.cloud_doc("2026-09-01", keep["body"], keep["hash"]),
                self.cloud_doc("2026-09-02", gone["body"], gone["hash"],
                               deleted=True, deletedAt="2026-09-13T10:00:00",
                               deletedBy="t@example.com")]
        state = {self.t["key"]: {"rids": ["2026-09-01", "2026-09-02"]}}
        return docs, state

    def test_local_block_is_removed_and_audited_without_the_body(self):
        docs, state = self.two_records()
        _, notes, counters = self.sync(docs, state=state)
        self.assertEqual(counters["delete"], 1, notes)
        text = read(self.path)
        self.assertNotIn("第二則在網頁上刪掉了。", text, "軟刪的那則要從本機檔消失")
        self.assertIn("第一則留著。", text, "沒刪的那則不准動")
        rows = self.audit_lines()
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(rows[0]["op"], "delete")
        self.assertEqual(rows[0]["rid"], "2026-09-02")
        self.assertTrue(rows[0]["hash"], "稽核要留內容指紋")
        self.assertNotIn("第二則在網頁上刪掉了", json.dumps(rows[0], ensure_ascii=False),
                         "稽核那一行不可以帶正文")

    def test_record_the_file_never_had_is_a_no_op(self):
        """網頁上新增後馬上刪掉：本機從來沒有那一則——不做事，也不可以報錯或寫回檔案。"""
        write(self.path, "# S-01\n\n## 2026-09-01\n\n只有這一則。\n")
        keep = self.block("2026-09-01")
        docs = [self.cloud_doc("2026-09-01", keep["body"], keep["hash"]),
                self.cloud_doc("2026-09-09", "網頁上打完就刪了", "h9", deleted=True,
                               deletedAt="2026-09-13T10:00:00")]
        before = read(self.path)
        rids, notes, counters = self.sync(docs)
        self.assertEqual(counters["delete"], 0, notes)
        self.assertEqual(counters["new"], 0, "軟刪的那則絕不可以被當成『雲端新增』寫回本機")
        self.assertEqual(read(self.path), before)
        self.assertNotIn("網頁上打完就刪了", read(self.path))
        self.assertEqual(self.audit_lines(), [])
        self.assertFalse([n for n in notes if "本機少了" in n], notes)
        self.assertIn("2026-09-09", rids, "文件還在雲端，狀態檔要記得它（下一輪才不會重推）")

    def test_dry_run_deletes_nothing_and_the_next_round_does_not_repeat(self):
        docs, state = self.two_records()
        before = read(self.path)
        _, notes, counters = self.sync(docs, dry=True, state=state)
        self.assertEqual(counters["delete"], 1, "預演也要算給老師看")
        self.assertEqual(read(self.path), before, "預演不准動檔案")
        self.assertEqual(self.audit_lines(), [], "預演不准寫稽核")
        self.assertTrue([n for n in notes if "預演" in n and "2026-09-02" in n], notes)

        rids, _, counters = self.sync(docs, state=state)          # 真的跑一次
        self.assertEqual(counters["delete"], 1)
        self.assertEqual(len(self.audit_lines()), 1)

        _, notes3, counters3 = self.sync(docs, state={self.t["key"]: {"rids": sorted(rids)}})
        self.assertEqual(counters3["delete"], 0, "第二輪不可以再刪一次")
        self.assertEqual(counters3["push"], 0, "也不可以把刪掉的那則重推上雲")
        self.assertEqual(len(self.audit_lines()), 1, "稽核不可以重複寫")


class TestSoftDeleteExcludedFromReads(SoftDeleteBase):
    """匯出、期末素材包、台帳都不可以看到軟刪的那則——老師在網頁上已經看不到它了。"""

    def fixture(self):
        write(self.path, "# S-01\n\n## 2026-09-01\n\n留下來的觀察。\n")
        keep = self.block("2026-09-01")
        lib.token = lambda *a, **kw: "tok"
        lib.targets = lambda *a, **kw: [self.t]
        lib.list_docs = lambda base, path, tok, **kw: [
            self.cloud_doc("2026-09-01", keep["body"], keep["hash"]),
            self.cloud_doc("2026-09-02", "刪掉的那一則正文", "h2", deleted=True,
                           deletedAt="2026-09-13T10:00:00")]
        return {"firebase": {"project_id": "p"}}, {}

    def test_export_records_skips_them(self):
        import export_records
        kit, tabs = self.fixture()
        data = export_records.collect(kit, tabs, False)
        recs = data["targets"][0]["records"]
        self.assertEqual([r["rid"] for r in recs], ["2026-09-01"])
        self.assertNotIn("刪掉的那一則正文", json.dumps(data, ensure_ascii=False))

    def test_report_pack_material_skips_them(self):
        import export_records
        import report_pack
        kit, tabs = self.fixture()
        data = export_records.collect(kit, tabs, False)
        recs = data["targets"][0]["records"]
        pack = report_pack.build_pack(report_pack.load_format("waldorf-homeroom"),
                                      "S-01", "S-01", recs, lib.load_card("S-01"),
                                      ["homeroom"], "", "")
        self.assertIn("留下來的觀察。", pack)
        self.assertNotIn("刪掉的那一則正文", pack, "期末素材包不可以出現老師已經刪掉的紀錄")

    def test_ledger_does_not_count_them_as_cloud(self):
        import ledger
        kit, tabs = self.fixture()
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = ledger.check(kit, tabs, False, True)
        out = json.loads(buf.getvalue())
        row = [r for r in out["rows"] if r["target"] == self.t["key"]][0]
        self.assertEqual(row["cloud"], 1, "軟刪的不算『網站有』，否則三處永遠對不上")
        self.assertEqual(row["onlyCloud"], [])
        self.assertEqual(rc, 0, out["problems"])


class TestPurgeDeleted(SoftDeleteBase):
    """真刪那一段：沒有 `--confirm` 一則都不准刪，刪了要記 `op: purge`。"""

    def run_purge(self, *args):
        import purge_deleted
        write(self.path, "# S-01\n\n## 2026-09-01\n\n留下來的觀察。\n")
        keep = self.block("2026-09-01")
        calls = []
        lib.token = lambda *a, **kw: "tok"
        lib.targets = lambda *a, **kw: [self.t]
        lib.list_docs = lambda base, path, tok, **kw: [
            self.cloud_doc("2026-09-01", keep["body"], keep["hash"]),
            self.cloud_doc("2026-09-02", "刪掉的那一則正文", "h2", deleted=True,
                           deletedAt="2026-09-13T10:00:00")]
        lib.delete_doc = lambda base, path, tok, **kw: calls.append(path) or {}
        old_kit, old_tabs, argv = lib.load_kit, lib.load_tabs, sys.argv
        lib.load_kit = lambda *a, **kw: {"mode": "cloud", "firebase": {"project_id": "p"}}
        lib.load_tabs = lambda *a, **kw: {}
        sys.argv = ["purge_deleted.py", "--root", self.tmp, *args]
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                purge_deleted.main()
        finally:
            lib.load_kit, lib.load_tabs, sys.argv = old_kit, old_tabs, argv
        return calls, buf.getvalue()

    def test_list_writes_nothing(self):
        calls, out = self.run_purge("--list")
        self.assertEqual(calls, [], "--list 不准刪任何東西")
        self.assertEqual(self.audit_lines(), [])
        self.assertIn("2026-09-02", out, "清單要看得到是哪一則")
        self.assertIn("正文 8 字", out, "清單要有字數")
        self.assertNotIn("刪掉的那一則正文", out, "清單不印正文")

    def test_without_confirm_nothing_is_deleted(self):
        calls, out = self.run_purge("--all")
        self.assertEqual(calls, [], "沒有 --confirm 就不准刪")
        self.assertEqual(self.audit_lines(), [])
        self.assertIn("沒有 --confirm，一則都沒刪", out)

    def test_confirm_deletes_and_audits(self):
        calls, out = self.run_purge("--all", "--confirm")
        self.assertEqual(calls, ["students/S-01/records/2026-09-02"],
                         "只准刪被標成已刪的那一則")
        rows = self.audit_lines()
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(rows[0]["op"], "purge")
        self.assertEqual(rows[0]["rid"], "2026-09-02")
        self.assertEqual(rows[0]["hash"], "h2")
        self.assertNotIn("刪掉的那一則正文", json.dumps(rows[0], ensure_ascii=False))


class TestHelpAndHygiene(unittest.TestCase):
    SCRIPTS = ["setup.py", "build_config.py", "doctor.py", "sync.py", "append_record.py",
               "transcribe.py", "backup.py", "ledger.py", "export_records.py", "export_docs.py",
               "parent_email.py", "pending.py", "monthly_reminder.py", "purge_deleted.py"]

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
