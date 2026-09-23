#!/usr/bin/env python3
# -*- coding: utf-8 -*-
""".firebaserc（多站 Hosting target）的測試：讓每個安裝指定自己的 Firebase Hosting site，
不必改 git 追蹤中的 firebase.json。全部離線、零網路。

    python3 -m unittest discover -s scripts/tests -p "test_*.py"

背景：firebase.json 的 hosting 物件固定寫 "target": "web"（Firebase 官方多站機制），
真正部署到哪一個 site 由 repo 根目錄的 .firebaserc 決定——那個檔是每個安裝各自的，
已經被 .gitignore 擋住，由 build_config.py 自動產生／合併，不進 git。
多數老師一個 Firebase 專案只有一個預設 site（跟 project_id 同名，零設定）；
只有像同一個專案掛了不只一個 Hosting site 那種進階安裝，才需要在 config/kit.json 的
firebase.hosting_site 填一個不一樣的 site 名稱。
"""
import os
import sys
import json
import shutil
import unittest
import tempfile
import subprocess

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.dirname(SCRIPTS)
sys.path.insert(0, SCRIPTS)
import lib          # noqa: E402
import build_config  # noqa: E402


def run(script, *args, root=None):
    cmd = [sys.executable, os.path.join(SCRIPTS, script), *args]
    if root:
        cmd += ["--root", root]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", timeout=300)


def load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def dump_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


def read_text(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def write_bytes(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


class FirebasercTestBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="trk-firebaserc-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _write_kit_tabs(self, root, mode="cloud", project_id="demo-proj", hosting_site=""):
        fb = {"project_id": project_id, "api_key": "AIzaKEY", "auth_domain": "",
              "storage_bucket": "b", "messaging_sender_id": "1", "app_id": "a"}
        if hosting_site:
            fb["hosting_site"] = hosting_site
        kit = {"mode": mode, "owner_email": "teacher@example.com", "id_prefix": "S", "firebase": fb}
        dump_json(os.path.join(root, "config", "kit.json"), kit)
        dump_json(os.path.join(root, "config", "tabs.json"),
                  {"students": {"enabled": True, "streams": []},
                   "courses": {"enabled": True, "list": []},
                   "business": {"enabled": False, "groups": []}})
        return kit

    def _firebaserc_path(self, root=None):
        return os.path.join(root or self.tmp, ".firebaserc")


class TestFirebaseJsonAndGitignore(FirebasercTestBase):
    """firebase.json 與 .gitignore 本身：這兩處是每個安裝都吃到的一次性設定，不必跑腳本就能驗。"""

    def test_firebase_json_declares_web_target(self):
        fb_json = load_json(os.path.join(PKG, "firebase.json"))
        self.assertEqual(fb_json["hosting"]["target"], "web",
                         "firebase.json 的 hosting 要固定用 target=web，實際 site 交給 .firebaserc 決定")
        # 其餘內容不該被動到
        self.assertEqual(fb_json["hosting"]["public"], "site")

    def test_firebaserc_is_gitignored(self):
        r = subprocess.run(["git", "check-ignore", ".firebaserc"], cwd=PKG,
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, ".firebaserc 應該被 .gitignore 擋住")


class TestHostingSiteHelper(FirebasercTestBase):
    """build_config.hosting_site()：空或沒填＝等於 project_id，填了就照填的。"""

    def test_defaults_to_project_id(self):
        self.assertEqual(build_config.hosting_site({"firebase": {"project_id": "demo-proj"}}),
                         "demo-proj")
        self.assertEqual(build_config.hosting_site(
            {"firebase": {"project_id": "demo-proj", "hosting_site": ""}}), "demo-proj")
        self.assertEqual(build_config.hosting_site(
            {"firebase": {"project_id": "demo-proj", "hosting_site": "   "}}), "demo-proj")

    def test_override_wins(self):
        self.assertEqual(build_config.hosting_site(
            {"firebase": {"project_id": "tw-history-tube", "hosting_site": "trk-4a"}}), "trk-4a")


class TestBuildFirebaserc(FirebasercTestBase):
    def test_default_site_equals_project_id(self):
        self._write_kit_tabs(self.tmp, project_id="demo-proj")
        r = run("build_config.py", "--root", self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rc = load_json(self._firebaserc_path())
        self.assertEqual(rc["projects"]["default"], "demo-proj")
        self.assertEqual(rc["targets"]["demo-proj"]["hosting"]["web"], ["demo-proj"])

    def test_hosting_site_override_is_used(self):
        self._write_kit_tabs(self.tmp, project_id="tw-history-tube", hosting_site="trk-4a")
        r = run("build_config.py", "--root", self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rc = load_json(self._firebaserc_path())
        self.assertEqual(rc["projects"]["default"], "tw-history-tube")
        self.assertEqual(rc["targets"]["tw-history-tube"]["hosting"]["web"], ["trk-4a"],
                         "多站的安裝：web target 要對到 hosting_site，不是 project_id")

    def test_merge_preserves_other_aliases_and_targets(self):
        """既有 .firebaserc 裡老師自己加的東西（另一個 alias、同專案 web 以外的 target、
        另一個 project 的 targets）一個都不能被洗掉；projects.default 已經有值也不能覆蓋。"""
        self._write_kit_tabs(self.tmp, project_id="demo-proj")
        dump_json(self._firebaserc_path(), {
            "projects": {"default": "hand-set-alias", "staging": "other-project-id"},
            "targets": {
                "demo-proj": {"hosting": {"web": ["old-site"], "admin": ["admin-site"]}},
                "other-project-id": {"hosting": {"web": ["other-site"]}},
            },
        })
        r = run("build_config.py", "--root", self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rc = load_json(self._firebaserc_path())
        self.assertEqual(rc["projects"]["default"], "hand-set-alias",
                         "projects.default 已經有值就不該被覆蓋")
        self.assertEqual(rc["projects"]["staging"], "other-project-id", "別的 alias 不該被刪")
        self.assertEqual(rc["targets"]["demo-proj"]["hosting"]["web"], ["demo-proj"],
                         "web 這個 target 還是要更新成現在算出來的 site")
        self.assertEqual(rc["targets"]["demo-proj"]["hosting"]["admin"], ["admin-site"],
                         "同一個專案底下 web 以外的 target 不該被刪")
        self.assertEqual(rc["targets"]["other-project-id"]["hosting"]["web"], ["other-site"],
                         "別的 project 的 targets 不該被動到")

    def test_local_mode_does_not_write_firebaserc(self):
        self._write_kit_tabs(self.tmp, mode="local")
        r = run("build_config.py", "--root", self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(self._firebaserc_path()),
                         "本機模式沒有 Hosting，不該產生 .firebaserc")

    def test_unchanged_content_is_not_rewritten(self):
        self._write_kit_tabs(self.tmp, project_id="demo-proj")
        r = run("build_config.py", "--root", self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        path = self._firebaserc_path()
        self.assertTrue(os.path.exists(path))
        old_time = 1700000000
        os.utime(path, (old_time, old_time))
        r2 = run("build_config.py", "--root", self.tmp)
        self.assertEqual(r2.returncode, 0, r2.stdout + r2.stderr)
        self.assertEqual(os.path.getmtime(path), old_time,
                         "內容沒變就不該重寫這個檔（mtime 應該原封不動）")
        self.assertIn(".firebaserc 內容沒變，不重寫", r2.stdout)

    def test_check_mode_does_not_write_anything(self):
        self._write_kit_tabs(self.tmp, project_id="demo-proj")
        r = run("build_config.py", "--root", self.tmp, "--check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(self._firebaserc_path()), "--check 不該寫任何檔")

    def test_deploy_command_still_uses_project_flag(self):
        """印出來的部署指令維持現有 --project 寫法，不必改成 --project <pid> --site 之類的新語法。"""
        self._write_kit_tabs(self.tmp, project_id="demo-proj")
        r = run("build_config.py", "--root", self.tmp)
        self.assertIn("firebase deploy --only firestore:rules --project demo-proj", r.stdout)


class TestDoctorFirebaserc(FirebasercTestBase):
    def _doctor_item(self, root):
        r = run("doctor.py", "--root", root, "--skip-network", "--json")
        data = json.loads(r.stdout)
        items = {i["key"]: i for i in data["items"]}
        self.assertIn("firebaserc", items, "doctor.py 應該要有 firebaserc 這一項")
        return items["firebaserc"], data

    def test_missing_file_is_a_problem(self):
        self._write_kit_tabs(self.tmp, project_id="demo-proj")
        # 沒跑 build_config.py，所以 .firebaserc 不存在
        item, data = self._doctor_item(self.tmp)
        self.assertFalse(item["ok"])
        self.assertTrue(item["required"])
        self.assertIn("build_config.py", item["fix"])
        self.assertFalse(data["ok"], "必要項目沒過，整份健檢要算失敗")

    def test_matching_site_passes(self):
        self._write_kit_tabs(self.tmp, project_id="demo-proj")
        r = run("build_config.py", "--root", self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        item, _ = self._doctor_item(self.tmp)
        self.assertTrue(item["ok"], item)

    def test_mismatched_site_is_a_problem(self):
        """hosting_site 改過但沒重跑產生器：.firebaserc 上還是舊的 site。"""
        self._write_kit_tabs(self.tmp, project_id="demo-proj")
        r = run("build_config.py", "--root", self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        # 手動把設定改成多站，但不重跑 build_config.py
        kit = load_json(os.path.join(self.tmp, "config", "kit.json"))
        kit["firebase"]["hosting_site"] = "trk-4a"
        dump_json(os.path.join(self.tmp, "config", "kit.json"), kit)
        item, data = self._doctor_item(self.tmp)
        self.assertFalse(item["ok"])
        self.assertIn("demo-proj", item["detail"])
        self.assertFalse(data["ok"])

    def test_local_mode_skips_the_check(self):
        self._write_kit_tabs(self.tmp, mode="local")
        item, data = self._doctor_item(self.tmp)
        self.assertTrue(item["skipped"])
        self.assertFalse(item["required"])

    def test_bad_json_is_a_problem(self):
        self._write_kit_tabs(self.tmp, project_id="demo-proj")
        with open(self._firebaserc_path(), "w", encoding="utf-8") as f:
            f.write("{not valid json")
        item, _ = self._doctor_item(self.tmp)
        self.assertFalse(item["ok"])
        self.assertIn("build_config.py", item["fix"])


class TestSetupPassesHostingSiteThrough(unittest.TestCase):
    """setup.py 的問答只問六個常見的 Firebase 值，不問 hosting_site（零設定是預設）；
    但答案檔或既有設定裡已經填了的話，不能被這支腳本悄悄清空——它要原封不動流進 kit.json，
    build_config.py 才讀得到、才產得出正確的 .firebaserc。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="trk-setup-hostingsite-")

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def _answers(self, hosting_site="trk-4a"):
        with open(os.path.join(PKG, "templates", "answers.example.json"), encoding="utf-8") as f:
            a = lib._strip_comments(json.load(f))
        a["firebase"]["project_id"] = "tw-history-tube"
        a["firebase"]["hosting_site"] = hosting_site
        return a

    def test_hosting_site_survives_answers_to_kit_json(self):
        path = os.path.join(self.tmp, "answers.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._answers(), f, ensure_ascii=False)
        r = run("setup.py", "--answers", path, "--skip-network", "--skip-doctor", root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        kit = load_json(os.path.join(self.tmp, "config", "kit.json"))
        self.assertEqual(kit["firebase"].get("hosting_site"), "trk-4a",
                         "答案檔填了 hosting_site，寫出來的 kit.json 不該把它丟掉")

    def test_empty_hosting_site_is_not_forced_in(self):
        path = os.path.join(self.tmp, "answers.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._answers(hosting_site=""), f, ensure_ascii=False)
        r = run("setup.py", "--answers", path, "--skip-network", "--skip-doctor", root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        kit = load_json(os.path.join(self.tmp, "config", "kit.json"))
        self.assertFalse((kit["firebase"].get("hosting_site") or "").strip(),
                         "大部分老師的答案檔不填 hosting_site，kit.json 也不該生出一個非空值")


class TestAuthDomainDefaultFollowsHostingSite(FirebasercTestBase):
    """驗收回 FAIL 的阻擋項：填了 hosting_site 之後，authDomain 沒有留空的預設值要跟著換，
    不然多站安裝的網頁跟 authDomain 不同源，iOS Safari 的 Google 登入會壞
    （AGENTS.md「先處理一個坑：iPhone 上登不進去」那一段）。"""

    def test_build_config_defaults_auth_domain_to_hosting_site(self):
        self._write_kit_tabs(self.tmp, project_id="tw-history-tube", hosting_site="trk-4a")
        r = run("build_config.py", "--root", self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        fbjs = read_text(os.path.join(self.tmp, "site", "js", "firebase-config.js"))
        self.assertIn('"authDomain": "trk-4a.web.app"', fbjs)
        self.assertNotIn("tw-history-tube.web.app", fbjs)

    def test_build_config_defaults_auth_domain_to_project_id_when_no_hosting_site(self):
        self._write_kit_tabs(self.tmp, project_id="demo-proj")
        r = run("build_config.py", "--root", self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        fbjs = read_text(os.path.join(self.tmp, "site", "js", "firebase-config.js"))
        self.assertIn('"authDomain": "demo-proj.web.app"', fbjs)

    def test_setup_py_writes_hosting_site_based_auth_domain(self):
        """完整跑一次 setup.py --answers：project_id=tw-history-tube、hosting_site=trk-4a、
        auth_domain 空——kit.json 與 site/js/firebase-config.js 兩處的 authDomain 都要是
        trk-4a.web.app（不是 tw-history-tube.web.app）。"""
        with open(os.path.join(PKG, "templates", "answers.example.json"), encoding="utf-8") as f:
            a = lib._strip_comments(json.load(f))
        a["firebase"]["project_id"] = "tw-history-tube"
        a["firebase"]["hosting_site"] = "trk-4a"
        a["firebase"]["auth_domain"] = ""
        ans_path = os.path.join(self.tmp, "answers.json")
        dump_json(ans_path, a)
        r = run("setup.py", "--answers", ans_path, "--skip-network", "--skip-doctor", root=self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        kit = load_json(os.path.join(self.tmp, "config", "kit.json"))
        self.assertEqual(kit["firebase"]["auth_domain"], "trk-4a.web.app",
                         "kit.json 的 auth_domain 沒有跟著 hosting_site 換")
        fbjs = read_text(os.path.join(self.tmp, "site", "js", "firebase-config.js"))
        self.assertIn('"authDomain": "trk-4a.web.app"', fbjs)
        self.assertNotIn("tw-history-tube.web.app", fbjs)


class TestFirebasercSkipsPlaceholderProjectId(FirebasercTestBase):
    """project_id 是空的或還是範本值時，build_firebaserc 整支不動作——不然 --allow-placeholders
    的測試／CI 流程會把 projects.default 永久卡在 your-firebase-project-id。"""

    def test_placeholder_project_id_is_not_written(self):
        self._write_kit_tabs(self.tmp, project_id="your-firebase-project-id")
        r = run("build_config.py", "--root", self.tmp, "--allow-placeholders")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(self._firebaserc_path()),
                         "project_id 還是範本值，不該產生 .firebaserc")

    def test_empty_project_id_is_not_written(self):
        self._write_kit_tabs(self.tmp, project_id="")
        r = run("build_config.py", "--root", self.tmp, "--allow-placeholders")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(self._firebaserc_path()))

    def test_real_project_id_after_placeholder_still_works(self):
        """先用範本值跑過一次（不產生 .firebaserc），換成真的 project_id 後 projects.default
        要正確填上——不能因為第一次被卡住了就永遠是空的。"""
        self._write_kit_tabs(self.tmp, project_id="your-firebase-project-id")
        run("build_config.py", "--root", self.tmp, "--allow-placeholders")
        self._write_kit_tabs(self.tmp, project_id="demo-proj")
        r = run("build_config.py", "--root", self.tmp)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        rc = load_json(self._firebaserc_path())
        self.assertEqual(rc["projects"]["default"], "demo-proj")

    def test_helper_function_matches_doctor_and_build(self):
        """hosting_pid_usable() 是 build_firebaserc() 與 doctor.check_firebaserc() 共用的
        唯一判準——這裡直接測那個函式本身，不必各別測兩支呼叫端的行為是否剛好一致。"""
        for bad in ("", "   ", "your-firebase-project-id", "your-anything"):
            with self.subTest(pid=bad):
                self.assertFalse(build_config.hosting_pid_usable(bad))
        for ok in ("demo-proj", "tw-history-tube"):
            with self.subTest(pid=ok):
                self.assertTrue(build_config.hosting_pid_usable(ok))


class TestFirebasercMalformedShapesDoNotCrash(FirebasercTestBase):
    """形狀不對的 .firebaserc（根是 list、projects/targets 是 list、hosting: null）：
    build_config.py 給清楚訊息而不是 traceback；doctor.py 不丟例外，報「格式不對」。"""

    MALFORMED = {
        "根是 list": ["not", "a", "dict"],
        "projects 是 list": {"projects": ["a", "b"], "targets": {}},
        "targets 是 list": {"projects": {}, "targets": ["a", "b"]},
        "hosting 是 null": {"projects": {}, "targets": {"demo-proj": {"hosting": None}}},
    }

    def test_build_config_dies_with_a_clear_message_not_a_traceback(self):
        for why, shape in self.MALFORMED.items():
            with self.subTest(why=why):
                self._write_kit_tabs(self.tmp, project_id="demo-proj")
                dump_json(self._firebaserc_path(), shape)
                r = run("build_config.py", "--root", self.tmp)
                if why == "hosting 是 null":
                    # 這一種形狀在 targets.<pid> 這一層本身仍是物件，build_firebaserc()
                    # 會安全地自我修復（hosting: null → 當成沒有），不用擋下來。
                    self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
                    rc = load_json(self._firebaserc_path())
                    self.assertEqual(rc["targets"]["demo-proj"]["hosting"]["web"], ["demo-proj"])
                    continue
                self.assertEqual(r.returncode, 1, why + "：應該擋下來，不是 traceback")
                self.assertNotIn("Traceback", r.stderr, why + "：不該是沒接住的例外")
                self.assertIn("格式不對", r.stderr, why)
                self.assertIn("→", r.stderr, why + "：要有怎麼修")
                self.assertIn("build_config.py", r.stderr, why)

    def test_doctor_reports_a_problem_not_an_exception(self):
        for why, shape in self.MALFORMED.items():
            with self.subTest(why=why):
                self._write_kit_tabs(self.tmp, project_id="demo-proj")
                dump_json(self._firebaserc_path(), shape)
                r = run("doctor.py", "--root", self.tmp, "--skip-network", "--json")
                self.assertNotIn("Traceback", r.stderr, why + "：doctor 不該丟例外")
                data = json.loads(r.stdout)   # 丟例外的話這裡就不是合法 JSON，subTest 會直接炸
                item = {i["key"]: i for i in data["items"]}["firebaserc"]
                if why == "hosting 是 null":
                    # 這一種 doctor 讀到的是「沒有對應」，不算格式壞掉；照常判斷對不對得上。
                    self.assertFalse(item["ok"], why)
                    self.assertNotIn("格式不對", item["detail"], why)
                else:
                    self.assertFalse(item["ok"], why)
                    self.assertIn("格式不對", item["detail"], why)
                    self.assertIn("build_config.py", item["fix"], why)


class TestFirebasercBadEncoding(FirebasercTestBase):
    """編碼不對的 .firebaserc（記事本存成「Unicode」＝UTF-16，開頭 fffe；或任何非 UTF-8
    的 bytes）：UnicodeDecodeError 是 ValueError 的子類別，舊版的 except 子句接不住，
    doctor.py 會整個當掉（沒印完的報告、非零退出碼），build_config.py 會留一份 traceback。
    兩支都要走「格式不對 → 刪掉 .firebaserc 再跑 build_config.py」那一套，不能丟例外。"""

    UTF16_CONTENT = json.dumps({"projects": {"default": "demo-proj"},
                                "targets": {"demo-proj": {"hosting": {"web": ["demo-proj"]}}}},
                               ensure_ascii=False).encode("utf-16")   # 帶 BOM，Notepad「Unicode」存出來的樣子
    RANDOM_BAD_BYTES = b"\x80\x81\x82\x83\xff\xfe\x00\x01broken"      # 保證不是合法 UTF-8

    def test_doctor_still_prints_a_complete_report(self):
        for label, content in (("UTF-16", self.UTF16_CONTENT), ("隨機非 UTF-8 bytes", self.RANDOM_BAD_BYTES)):
            with self.subTest(encoding=label):
                self._write_kit_tabs(self.tmp, project_id="demo-proj")
                write_bytes(self._firebaserc_path(), content)
                r = run("doctor.py", "--root", self.tmp, "--skip-network", "--json")
                self.assertNotIn("Traceback", r.stderr, label + "：doctor 不該丟例外")
                data = json.loads(r.stdout)   # 沒接住例外的話這裡不是合法 JSON，會直接炸開
                self.assertGreater(len(data["items"]), 10, label + "：報告應該要完整（不是印到一半就斷）")
                item = {i["key"]: i for i in data["items"]}["firebaserc"]
                self.assertFalse(item["ok"], label)
                self.assertIn("格式不對", item["detail"], label)
                self.assertIn("build_config.py", item["fix"], label)

    def test_build_config_gives_a_clear_message_not_a_traceback(self):
        for label, content in (("UTF-16", self.UTF16_CONTENT), ("隨機非 UTF-8 bytes", self.RANDOM_BAD_BYTES)):
            with self.subTest(encoding=label):
                self._write_kit_tabs(self.tmp, project_id="demo-proj")
                write_bytes(self._firebaserc_path(), content)
                r = run("build_config.py", "--root", self.tmp)
                self.assertEqual(r.returncode, 1, label + "：應該乾淨地停下來")
                self.assertNotIn("Traceback", r.stderr, label + "：不該是沒接住的例外")
                self.assertIn("格式不對", r.stderr, label)
                self.assertIn("→", r.stderr, label + "：要有怎麼修")
                self.assertIn("build_config.py", r.stderr, label)


class TestHostingSiteFormatValidation(FirebasercTestBase):
    """hosting_site 只能是純 site 名稱（小寫英數與 -），貼成網址或帶 .web.app 尾巴要擋下來。"""

    def test_bad_values_are_refused(self):
        for bad, why in [
            ("trk-4a.web.app", "帶了 .web.app 尾巴"),
            ("https://trk-4a", "貼成網址"),
            ("TRK-4A", "大寫"),
            ("trk 4a", "有空白"),
            ("trk_4a", "底線不合法"),
        ]:
            with self.subTest(why=why):
                self._write_kit_tabs(self.tmp, project_id="demo-proj", hosting_site=bad)
                r = run("build_config.py", "--root", self.tmp, "--check")
                self.assertEqual(r.returncode, 1, why + "：應該擋下來")
                self.assertIn("hosting_site", r.stderr, why)
                self.assertIn("→", r.stderr, why)

    def test_good_value_passes(self):
        self._write_kit_tabs(self.tmp, project_id="demo-proj", hosting_site="trk-4a")
        r = run("build_config.py", "--root", self.tmp, "--check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_empty_is_fine(self):
        self._write_kit_tabs(self.tmp, project_id="demo-proj", hosting_site="")
        r = run("build_config.py", "--root", self.tmp, "--check")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_helper_function_is_shared(self):
        """build_config.hosting_site_format_ok()：setup.py 用同一支，不各寫一份 regex。"""
        for bad in ("trk-4a.web.app", "https://trk-4a", "TRK-4A", "trk 4a", "trk_4a"):
            with self.subTest(bad=bad):
                self.assertFalse(build_config.hosting_site_format_ok(bad))
        for ok in ("trk-4a", "demo-proj", "a", "a-b-c-123"):
            with self.subTest(ok=ok):
                self.assertTrue(build_config.hosting_site_format_ok(ok))

    def test_setup_py_refuses_before_writing_a_doubled_web_app_suffix(self):
        """答案檔把 hosting_site 貼成 "trk-4a.web.app"：setup.py 要停在這裡，
        不能先算出 auth_domain="trk-4a.web.app.web.app" 這種廢話再寫進 kit.json。"""
        with open(os.path.join(PKG, "templates", "answers.example.json"), encoding="utf-8") as f:
            a = lib._strip_comments(json.load(f))
        a["firebase"]["project_id"] = "tw-history-tube"
        a["firebase"]["hosting_site"] = "trk-4a.web.app"
        a["firebase"]["auth_domain"] = ""
        ans_path = os.path.join(self.tmp, "answers.json")
        dump_json(ans_path, a)
        r = run("setup.py", "--answers", ans_path, "--skip-network", "--skip-doctor", root=self.tmp)
        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
        self.assertIn("hosting_site", r.stderr)
        self.assertIn("→", r.stderr)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "config", "kit.json")),
                         "格式不對就該整支停下來，不該先寫出一份帶廢話 auth_domain 的 kit.json")


class TestDoctorAuthDomain(FirebasercTestBase):
    """doctor.py 的新項目：cloud 模式下 authDomain 跟現在算出來的 Hosting site 同不同源。"""

    def _item(self, root):
        r = run("doctor.py", "--root", root, "--skip-network", "--json")
        data = json.loads(r.stdout)
        self.assertNotIn("Traceback", r.stderr)
        items = {i["key"]: i for i in data["items"]}
        self.assertIn("auth_domain", items, "doctor.py 應該要有 auth_domain 這一項")
        return items["auth_domain"]

    def _kit_with_auth_domain(self, project_id, hosting_site, auth_domain):
        fb = {"project_id": project_id, "api_key": "AIzaKEY", "auth_domain": auth_domain,
              "storage_bucket": "b", "messaging_sender_id": "1", "app_id": "a"}
        if hosting_site:
            fb["hosting_site"] = hosting_site
        kit = {"mode": "cloud", "owner_email": "teacher@example.com", "id_prefix": "S", "firebase": fb}
        dump_json(os.path.join(self.tmp, "config", "kit.json"), kit)
        dump_json(os.path.join(self.tmp, "config", "tabs.json"),
                  {"students": {"enabled": True, "streams": []},
                   "courses": {"enabled": True, "list": []},
                   "business": {"enabled": False, "groups": []}})

    def test_empty_auth_domain_is_ok(self):
        self._kit_with_auth_domain("demo-proj", "", "")
        item = self._item(self.tmp)
        self.assertTrue(item["ok"])
        self.assertFalse(item["required"])

    def test_matches_hosting_site_is_ok(self):
        self._kit_with_auth_domain("tw-history-tube", "trk-4a", "trk-4a.web.app")
        item = self._item(self.tmp)
        self.assertTrue(item["ok"], item)

    def test_stale_project_id_domain_after_hosting_site_change_warns(self):
        """填了 hosting_site=trk-4a，但 auth_domain 還留著舊的 <project_id>.web.app——
        這正是驗收回 FAIL 指出的那個壞情境。"""
        self._kit_with_auth_domain("tw-history-tube", "trk-4a", "tw-history-tube.web.app")
        item = self._item(self.tmp)
        self.assertFalse(item["ok"])
        self.assertFalse(item["required"], "選用警告，不擋安裝")
        self.assertIn("trk-4a", item["fix"])

    def test_firebaseapp_com_suffix_is_checked_too(self):
        self._kit_with_auth_domain("tw-history-tube", "trk-4a", "tw-history-tube.firebaseapp.com")
        item = self._item(self.tmp)
        self.assertFalse(item["ok"])

    def test_firebaseapp_com_never_counts_as_same_origin_even_with_matching_prefix(self):
        """.firebaseapp.com 是 AGENTS.md 一直在講的 iPhone 登入坑，前綴剛好等於現在的
        site 也一樣要警告——不是「前綴對了就沒事」的東西。"""
        self._kit_with_auth_domain("tw-history-tube", "trk-4a", "trk-4a.firebaseapp.com")
        item = self._item(self.tmp)
        self.assertFalse(item["ok"], "前綴對得上也不該算過，.firebaseapp.com 本身就不同源")
        self.assertFalse(item["required"])
        self.assertIn("trk-4a.web.app", item["fix"], "修法要建議換成 .web.app")

    def test_comparison_is_case_insensitive(self):
        """TRK-4A.web.app 不該被誤判成跟 site 對不上。"""
        self._kit_with_auth_domain("tw-history-tube", "trk-4a", "TRK-4A.web.app")
        item = self._item(self.tmp)
        self.assertTrue(item["ok"], item)

    def test_custom_domain_is_not_flagged(self):
        self._kit_with_auth_domain("demo-proj", "", "records.example.org")
        item = self._item(self.tmp)
        self.assertTrue(item["ok"], "自訂網域不該被當成 Firebase 網域來比對")

    def test_local_mode_is_skipped(self):
        self._write_kit_tabs(self.tmp, mode="local")
        item = self._item(self.tmp)
        self.assertTrue(item["skipped"])


if __name__ == "__main__":
    unittest.main()
