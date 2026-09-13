#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""三個高痛點垂直方案的測試：質性評量／IEP 追蹤／SOAP 個案。零網路，全部在暫存樹裡跑。

    python3 -m unittest discover scripts/tests

樹一樣是用 `setup.py --answers` 建的、記錄一樣用 `append_record.py` 寫進去——測的是
老師真的會跑的那條路徑（含 --answers 給的學生卡片），不是內部函式。
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
import lib

FIELD_TYPES = {"text", "date", "select", "multiselect", "goal"}
SELECTY = {"select", "multiselect"}
# David 指定的兩條紅線：AI 對比句與定型語言，每一個格式的 rules 都要擋。
BANNED_PHRASES = ["不是A而是B", "不只是", "真正的關鍵是"]
BANNED_LABELS = ["懶惰", "能力差", "不用心", "問題學生"]


def run(script, *args):
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, script), *args],
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


# ══ 設定檔本身合法嗎 ════════════════════════════════════════════════════
class TestStreamLibrary(unittest.TestCase):
    """記錄時要有引導欄位——所以每個欄位都要有一行 hint，選項型要有 options。"""

    @classmethod
    def setUpClass(cls):
        cls.streams = lib.load_stream_library()["streams"]

    def test_every_field_has_type_hint_and_options(self):
        for s in self.streams:
            for f in (s.get("fields") or []):
                with self.subTest(stream=s["id"], field=f.get("name")):
                    self.assertTrue(f.get("name"), "欄位沒有名字")
                    self.assertIn(f.get("type"), FIELD_TYPES, "型別要在 %s 之內" % FIELD_TYPES)
                    self.assertTrue((f.get("hint") or "").strip(),
                                    "每個欄位都要有一行引導（hint）——這是「記錄時有引導」的整個重點")
                    if f["type"] in SELECTY:
                        self.assertTrue(f.get("options"), "select／multiselect 一定要有 options")

    def test_three_verticals_have_their_streams(self):
        by_id = {s["id"]: s for s in self.streams}
        for sid in ("qualitative", "iep", "soap"):
            self.assertIn(sid, by_id)
        self.assertEqual(by_id["soap"].get("aliases"), ["counseling"],
                         "counseling 併進 soap，舊 id 要留在 aliases 才讀得到舊設定")
        self.assertTrue((by_id["iep"].get("card") or {}).get("goals"),
                        "IEP 要靠學生卡片上的 goals")
        self.assertTrue((by_id["soap"].get("card") or {}).get("conceptualization"),
                        "SOAP 要靠學生卡片上的個案概念化")

    def test_qualitative_option_sets(self):
        f = {x["name"]: x for x in
             [s for s in self.streams if s["id"] == "qualitative"][0]["fields"]}
        self.assertEqual(f["面向"]["type"], "multiselect")
        self.assertEqual(f["面向"]["options"],
                         ["頭·思考", "心·情感", "手·意志", "社群·人際"])
        self.assertEqual(f["報告維度"]["type"], "select")
        self.assertEqual(len(f["報告維度"]["options"]), 5, "客觀描述五維度")
        self.assertIn("行為與自我管理", f["報告維度"]["options"])
        self.assertIn("挑戰與方向", f["報告維度"]["options"])
        self.assertTrue(f["證據來源"]["options"])
        self.assertEqual(f["指標"]["type"], "text", "指標是文字，情意類不打等級")

    def test_iep_and_soap_option_sets(self):
        by_id = {s["id"]: s for s in self.streams}
        iep = {x["name"]: x for x in by_id["iep"]["fields"]}
        self.assertEqual(iep["目標編號"]["type"], "goal")
        self.assertEqual(iep["達成情形"]["options"],
                         ["未開始", "初步", "部分達成", "達成", "類化"])
        soap = {x["name"]: x for x in by_id["soap"]["fields"]}
        self.assertEqual(soap["風險評估"]["options"], ["無", "低", "中", "高"])
        for k in ("S 主觀", "O 客觀", "A 評估", "P 計畫"):
            self.assertIn(k, soap, "SOAP 四段各自一個欄位")


class TestReportFormats(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.formats = lib.load_report_formats()["formats"]
        cls.stream_ids = {s["id"] for s in lib.load_stream_library()["streams"]}

    def test_five_formats(self):
        self.assertEqual([f["id"] for f in self.formats],
                         ["waldorf-homeroom", "subject-4", "iep-tracking",
                          "case-summary", "custom"])

    def test_shape_and_rules(self):
        for f in self.formats:
            with self.subTest(fmt=f["id"]):
                self.assertTrue(f.get("label"))
                self.assertIsInstance(f.get("for"), list)
                self.assertTrue(all(s in self.stream_ids for s in f["for"]),
                                "for 裡的記錄類型要真的在類型庫裡")
                self.assertIsInstance(f.get("sections"), list)
                for sec in f["sections"]:
                    self.assertTrue(sec.get("title"))
                    self.assertTrue((sec.get("hint") or "").strip(), "每一段都要有寫作提示")
                self.assertTrue(f.get("rules"), "沒有書寫規則的格式等於沒有規則")
                self.assertTrue(f.get("audit"), "定稿前要有稽核清單")
                joined = " ".join(f["rules"])
                for p in BANNED_PHRASES:
                    self.assertIn(p, joined, "規則要點名禁用的對比句：%s" % p)
                for p in BANNED_LABELS:
                    self.assertIn(p, joined, "規則要點名禁用的定型語言：%s" % p)
                self.assertIn("他", joined, "人稱一律「他」")
                self.assertIn("下一步", joined, "每則只給一個主要下一步")

    def test_waldorf_has_five_dimensions(self):
        f = lib.find_format("waldorf-homeroom")
        self.assertEqual(len(f["dimensions"]), 5)
        titles = " ".join(s["title"] for s in f["sections"])
        for k in ("發展樣貌", "客觀描述", "整體感受", "導師建議"):
            self.assertIn(k, titles)

    def test_custom_points_at_teacher_file(self):
        f = lib.find_format("custom")
        self.assertEqual(f["customFile"], "config/report-format.custom.json")

    def test_waldorf_carries_the_derivation_tables(self):
        """沒有「報告維度」欄位的類型（homeroom）靠這三個鍵自動推導維度——
        網頁不硬編任何一張表，掉了就整條覆蓋提醒與素材包分組都失效。"""
        f = lib.find_format("waldorf-homeroom")
        dims = f["dimensions"]
        self.assertIsInstance(f.get("thinMax"), int)
        self.assertGreaterEqual(f["thinMax"], 1)
        tag_map = f["tagMap"]
        self.assertTrue(tag_map)
        for tag, dim in tag_map.items():
            self.assertTrue(tag.startswith("#"), "tagMap 的鍵要是 #標籤：%r" % tag)
            self.assertIn(dim, dims, "tagMap 指到的維度要在 dimensions 裡：%r" % dim)
        # 每個維度都要有一個「代表標籤」（快速鍵與「補一則」預填的就是它）
        for d in dims:
            self.assertTrue(any(v == d for v in tag_map.values()),
                            "維度沒有任何標可以直接標：%s" % d)
        kw = f["keywords"]
        self.assertEqual(sorted(kw), sorted(dims), "keywords 要五個維度都有")
        for d, words in kw.items():
            self.assertTrue(words, "維度沒有關鍵詞：%s" % d)
            for w in words:
                self.assertGreaterEqual(len(w), 2, "只收兩字以上的詞（單字太鬆）：%r" % w)

    def test_build_config_carries_derivation_tables_into_window_kit(self):
        """build_config.py 原樣把格式庫帶進 window.KIT.reportFormats——
        網頁的維度推導讀的就是這裡，少一個鍵就變成「沒有維度」。"""
        import build_config
        kit_js = build_config.build_kit_js(
            {"owner_email": "t@example.com"},
            {"students": {"enabled": True, "streams": []}},
            {"groups": []}, {"streams": []})
        payload = json.loads(kit_js[kit_js.index("{"):kit_js.rindex("}") + 1])
        f = [x for x in payload["reportFormats"] if x["id"] == "waldorf-homeroom"][0]
        for k in ("tagMap", "keywords", "thinMax", "dimensions"):
            self.assertIn(k, f, "window.KIT 少了 %s" % k)
        self.assertEqual(f["tagMap"], lib.find_format("waldorf-homeroom")["tagMap"])

    def test_preview_config_mirrors_the_library(self):
        """離線預覽（build_preview.py）吃的是 site/js/kit-config.example.js——
        那一份的推導表要跟格式庫一致，不然預覽看到的維度跟真的裝起來不一樣。"""
        path = os.path.join(PKG, "site", "js", "kit-config.example.js")
        with open(path, encoding="utf-8") as fh:
            src = fh.read()
        f = lib.find_format("waldorf-homeroom")
        self.assertIn("thinMax: %d," % f["thinMax"], src)
        for tag, dim in list(f["tagMap"].items())[:5]:
            self.assertIn('"%s": "%s"' % (tag, dim), src)
        for d in f["keywords"]:
            self.assertIn('"%s": [' % d, src)


class TestVerticals(unittest.TestCase):
    def test_three_verticals_are_consistent(self):
        vs = lib.load_verticals()["verticals"]
        self.assertEqual(len(vs), 3, "三個高痛點方案")
        stream_ids = {s["id"] for s in lib.load_stream_library()["streams"]}
        group_ids = {g["id"] for g in lib.load_library()["groups"]}
        fmt_ids = {f["id"] for f in lib.load_report_formats()["formats"]}
        for v in vs:
            with self.subTest(vertical=v["id"]):
                self.assertTrue(v.get("label"))
                self.assertTrue(v.get("pain"), "要有一句話痛點（精靈要唸給老師聽）")
                self.assertTrue(v.get("voiceRule"), "要有語音改寫規則")
                sug = v["suggest"]
                self.assertTrue(set(sug["streams"]) <= stream_ids)
                self.assertTrue(set(sug["groups"]) <= group_ids)
                self.assertIn(sug["format"], fmt_ids)
                self.assertTrue(lib.find_vertical(v["id"]))


# ══ 真的裝一棵樹跑一遍 ══════════════════════════════════════════════════
ANSWERS = {
    "owner_email": "teacher@example.com",
    "id_prefix": "S",
    "vertical": "iep-tracking",
    "firebase": {"project_id": "demo-project", "api_key": "AIzaEXAMPLE",
                 "auth_domain": "demo-project.firebaseapp.com",
                 "storage_bucket": "demo-project.firebasestorage.app",
                 "messaging_sender_id": "000000000000", "app_id": "1:0:web:0"},
    "students": {
        "enabled": True, "count": 3,
        "streams": ["qualitative", "iep", "soap"],
        "members": {"iep": ["S-02"], "soap": ["S-02"]},
        "cards": {"S-02": {
            "goals": [
                {"id": "G1", "領域": "溝通", "學年目標": "能以口語表達需求。",
                 "學期目標": "能在一次提示下說出完整請求句。", "評量方式": "課堂觀察",
                 "評量標準": "三次有兩次做到。", "期程": "2026-09 至 2027-01"},
                {"id": "G2", "領域": "生活自理", "學年目標": "能獨立完成上學準備。",
                 "學期目標": "能依圖卡完成整理書包五步驟。", "評量方式": "檢核表",
                 "評量標準": "五天有四天獨立完成。", "期程": "2026-09 至 2027-01"},
            ],
            "conceptualization": {"主訴": "上課容易分心", "背景": "去年轉學",
                                  "評估假設": "可能與環境轉換有關",
                                  "處遇目標": "建立可預測的課堂節奏",
                                  "結案標準": "連續四週能自行完成課堂轉換"},
        }},
    },
    "courses": {"enabled": True, "list": [{"id": "main-block", "title": "主課程", "kind": "主課程"}]},
    "business": {"enabled": False, "groups": []},
    "drive": {"mode": "desktop", "desktop_dir": "/tmp/trk-not-used"},
    "email": {"method": "smtp", "smtp_user": ""},
}


class VerticalTreeBase(unittest.TestCase):
    """一棵裝好的樹：三位學生、質性評量＋IEP＋SOAP 三種類型、S-02 有卡片。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="trk-vert-")
        cls.answers = write(os.path.join(cls.tmp, "answers.json"),
                            json.dumps(ANSWERS, ensure_ascii=False))
        r = run("setup.py", "--answers", cls.answers, "--root", cls.tmp,
                "--skip-network", "--skip-doctor")
        assert r.returncode == 0, r.stdout + r.stderr
        write(os.path.join(cls.tmp, "data", "roster.csv"),
              "代號,姓名,類型\n01,測試甲,\n02,測試乙,iep;soap\n03,測試丙,\n")
        d1 = write(os.path.join(cls.tmp, "d1.md"), "排故事的路時他把氾濫放在耕種前面。")
        d2 = write(os.path.join(cls.tmp, "d2.md"), "小組討論時他讓出位置。")
        d3 = write(os.path.join(cls.tmp, "d3.md"), "刻陶板那天他從頭到尾自己完成。")

        def add(target, stream, date, fields, body=d1, tags=""):
            args = ["--root", cls.tmp, "--kind", "students", "--target", target,
                    "--stream", stream, "--date", date, "--content-file", body,
                    "--fields-json", json.dumps(fields, ensure_ascii=False)]
            if tags:
                args += ["--tags", tags]
            rr = run("append_record.py", *args)
            assert rr.returncode == 0, rr.stdout + rr.stderr

        add("S-01", "qualitative", "2026-09-03",
            {"面向": ["頭·思考"], "報告維度": "學習態度與能力",
             "課程": "main-block", "證據來源": "課堂觀察"}, tags="#課堂")
        add("S-01", "qualitative", "2026-09-05",
            {"面向": ["心·情感", "社群·人際"], "報告維度": "人際互動",
             "課程": "main-block", "證據來源": "課堂觀察"}, body=d2)
        add("S-01", "qualitative", "2026-09-09",
            {"面向": ["手·意志"], "報告維度": "行為與自我管理", "課程": "main-block",
             "證據來源": "作品", "指標": "第3條 可獨立完成"}, body=d3)
        add("S-02", "iep", "2026-09-04",
            {"目標編號": "G1", "達成情形": "初步", "證據": "觀察",
             "支持策略": "給圖卡提示", "下一步": "減少一次提示"})
        add("S-02", "iep", "2026-09-18",
            {"目標編號": "G1", "達成情形": "部分達成", "證據": "觀察",
             "支持策略": "同儕示範", "下一步": "換到午餐情境"}, body=d2)
        add("S-02", "soap", "2026-09-06",
            {"會談次數": "1", "會談形式": "個別", "S 主觀": "他說「上課很吵」",
             "O 客觀": "全程坐在位子上", "A 評估": "可能與環境轉換有關",
             "P 計畫": "下週安排固定座位", "風險評估": "低", "下次時間": "2026-09-13"})
        add("S-02", "soap", "2026-09-13",
            {"會談次數": "2", "會談形式": "個別", "S 主觀": "他說「好一點了」",
             "O 客觀": "主動說出兩件事", "A 評估": "適應中", "P 計畫": "維持",
             "風險評估": "中"}, body=d2)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.out = tempfile.mkdtemp(prefix="trk-pack-")

    def tearDown(self):
        shutil.rmtree(self.out, ignore_errors=True)

    def pack(self, *args):
        return run("report_pack.py", "--root", self.tmp, "--out", self.out, "--local", *args)


class TestSetupWritesCard(VerticalTreeBase):
    def test_answers_goals_land_in_card_json(self):
        card = json.loads(read(os.path.join(self.tmp, "data", "students", "S-02", "card.json")))
        self.assertEqual([g["id"] for g in card["goals"]], ["G1", "G2"])
        self.assertEqual(card["goals"][0]["評量標準"], "三次有兩次做到。")
        self.assertEqual(card["conceptualization"]["結案標準"], "連續四週能自行完成課堂轉換")

    def test_vertical_is_recorded_in_tabs(self):
        tabs = json.loads(read(os.path.join(self.tmp, "config", "tabs.json")))
        self.assertEqual(tabs["vertical"], "iep-tracking")
        self.assertEqual(tabs["reportFormat"], "iep-tracking",
                         "方案的建議格式當期末預設（仍可用 --format 換）")
        self.assertEqual([s["id"] for s in tabs["students"]["streams"]],
                         ["qualitative", "iep", "soap"], "勾了什麼就是什麼，沒有幫他預先勾")

    def test_rerun_does_not_clobber_card(self):
        p = os.path.join(self.tmp, "data", "students", "S-02", "card.json")
        card = json.loads(read(p))
        card["goals"][0]["學期目標"] = "老師自己改過的目標"
        write(p, json.dumps(card, ensure_ascii=False))
        r = run("setup.py", "--answers", self.answers, "--root", self.tmp,
                "--skip-network", "--skip-doctor")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(json.loads(read(p))["goals"][0]["學期目標"], "老師自己改過的目標")


class TestGoalGate(VerticalTreeBase):
    def test_unknown_goal_id_is_refused_with_listing(self):
        draft = write(os.path.join(self.out, "x.md"), "今天的觀察。")
        r = run("append_record.py", "--root", self.tmp, "--kind", "students",
                "--target", "S-02", "--stream", "iep", "--date", "2026-09-20",
                "--content-file", draft, "--fields-json", '{"目標編號":"G9"}')
        self.assertNotEqual(r.returncode, 0, "卡片上沒有 G9，不能寫進去")
        self.assertIn("G9", r.stderr)
        self.assertIn("G1", r.stderr, "要把可用的目標列出來")
        self.assertIn("G2", r.stderr)
        self.assertIn("→", r.stderr, "錯誤一律兩行：原因＋怎麼修")

    def test_known_goal_id_passes(self):
        draft = write(os.path.join(self.out, "y.md"), "午餐時他自己說出請求。")
        r = run("append_record.py", "--root", self.tmp, "--kind", "students",
                "--target", "S-02", "--stream", "iep", "--date", "2026-09-21",
                "--content-file", draft,
                "--fields-json", '{"目標編號":"G2","達成情形":"達成"}')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)

    def test_multiselect_is_joined_with_slash(self):
        text = read(os.path.join(self.tmp, "data", "students", "S-01", "qualitative.md"))
        self.assertIn("面向：心·情感／社群·人際", text, "複選值用「／」串起來寫進檔案")

    def test_old_stream_id_still_accepted(self):
        """counseling 併進 soap 之後，舊 id 還是要打得中（不然舊腳本會突然壞掉）。"""
        draft = write(os.path.join(self.out, "z.md"), "第三次會談。")
        r = run("append_record.py", "--root", self.tmp, "--kind", "students",
                "--target", "S-02", "--stream", "counseling", "--date", "2026-09-27",
                "--content-file", draft, "--fields-json", '{"會談次數":"3"}')
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("第三次會談。",
                      read(os.path.join(self.tmp, "data", "students", "S-02", "soap.md")))


class TestReportPack(VerticalTreeBase):
    def files(self):
        return sorted(os.listdir(self.out))

    def test_qualitative_pack_has_five_dimensions(self):
        r = self.pack("--format", "waldorf-homeroom", "--target", "S-01")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = read(os.path.join(self.out, "S-01-waldorf-homeroom-素材包.md"))
        for dim in ("行為與自我管理", "人際互動", "學習態度與能力",
                    "內在特質與個人發展", "挑戰與方向"):
            self.assertIn("## %s" % dim, text, "五個報告維度都要有標題（沒紀錄的也要列出來）")
        self.assertIn("### 頭·思考", text, "面向是第二層")
        self.assertIn("排故事的路時他把氾濫放在耕種前面。", text, "每一則的原文要在")
        self.assertIn("2026-09-03", text, "每一則要附日期")
        self.assertIn("證據來源：課堂觀察", text, "每一則要附證據")
        self.assertIn("涵蓋報告維度：3／5", text)
        self.assertIn("還沒有紀錄的報告維度：內在特質與個人發展、挑戰與方向", text)

    def test_qualitative_prompt_has_skeleton_rules_audit(self):
        self.pack("--format", "waldorf-homeroom", "--target", "S-01")
        text = read(os.path.join(self.out, "S-01-waldorf-homeroom-prompt.md"))
        for k in ("發展樣貌", "客觀描述", "整體感受", "導師建議"):
            self.assertIn(k, text, "校方格式骨架")
        self.assertIn("書寫規則", text)
        self.assertIn("不是A而是B", text, "禁對比句要寫進 prompt")
        self.assertIn("問題學生", text, "禁定型語言要寫進 prompt")
        self.assertIn("- [ ]", text, "稽核清單是可打勾的")
        self.assertIn("固定指令", text)
        self.assertIn("素材包", text)

    def test_iep_pack_has_one_table_per_goal_and_flags_zero(self):
        r = self.pack("--format", "iep-tracking", "--target", "S-02")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = read(os.path.join(self.out, "S-02-iep-tracking-素材包.md"))
        self.assertIn("## 目標 G1｜溝通", text)
        self.assertIn("## 目標 G2｜生活自理", text)
        self.assertIn("| 評量標準 | 三次有兩次做到。 |", text, "每目標一表：評量標準要在表裡")
        self.assertIn("| 日期 | 達成情形 | 證據 | 支持策略 | 下一步 |", text)
        self.assertIn("| 2026-09-18 | 部分達成 |", text, "日期序達成情形")
        self.assertIn("本期還沒有任何紀錄掛在這一條目標下", text, "零紀錄的目標要提示")
        self.assertIn("零紀錄的目標：G2", text)

    def test_soap_pack_has_session_order_and_risk_trend(self):
        r = self.pack("--format", "case-summary", "--target", "S-02")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = read(os.path.join(self.out, "S-02-case-summary-素材包.md"))
        self.assertIn("## 個案概念化", text)
        self.assertIn("| 結案標準 | 連續四週能自行完成課堂轉換 |", text)
        self.assertIn("### 第 1 次會談", text)
        self.assertIn("### 第 2 次會談", text)
        self.assertLess(text.index("### 第 1 次會談"), text.index("### 第 2 次會談"),
                        "依會談次數排序")
        for k in ("S 主觀", "O 客觀", "A 評估", "P 計畫"):
            self.assertIn("**%s**" % k, text)
        self.assertIn("風險趨勢：第1次 低 → 第2次 中", text)

    def test_all_writes_index(self):
        r = self.pack("--format", "waldorf-homeroom", "--all")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("_index.md", self.files())
        idx = read(os.path.join(self.out, "_index.md"))
        for sid in ("S-01", "S-02", "S-03"):
            self.assertIn(sid, idx, "全班每一位都要在總表上")
        self.assertIn("一則紀錄都沒有的：", idx)
        self.assertIn("- [ ]", idx, "全班稽核清單")
        self.assertEqual(len([f for f in self.files() if f.endswith("素材包.md")]), 3)

    def test_numbered_dimension_lands_in_the_same_bucket(self):
        """網頁若把維度存成「①行為與自我管理」，要和「行為與自我管理」算同一堆。

        兩邊的選項字串萬一長得不完全一樣，老師看到的不該是被拆成兩半的素材包。
        """
        sys.path.insert(0, SCRIPTS)
        import report_pack
        recs = [{"date": "2026-09-01", "rid": "a", "tags": [], "body": "甲",
                 "fields": {"報告維度": "①行為與自我管理"}},
                {"date": "2026-09-02", "rid": "b", "tags": [], "body": "乙",
                 "fields": {"報告維度": "行為與自我管理"}}]
        b = report_pack.bucket(recs, "報告維度", ["行為與自我管理", "人際互動"])
        self.assertEqual(sorted(b), ["行為與自我管理"])
        self.assertEqual(len(b["行為與自我管理"]), 2)

    def test_date_range_filters(self):
        self.pack("--format", "waldorf-homeroom", "--target", "S-01",
                  "--from", "2026-09-05", "--to", "2026-09-06")
        text = read(os.path.join(self.out, "S-01-waldorf-homeroom-素材包.md"))
        self.assertIn("小組討論時他讓出位置。", text)
        self.assertNotIn("刻陶板那天", text, "範圍外的紀錄不該進來")

    def test_unknown_format_is_two_line_error(self):
        r = self.pack("--format", "nope", "--target", "S-01")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("waldorf-homeroom", r.stderr, "要把可用的格式列出來")
        self.assertIn("→", r.stderr)

    def test_custom_without_file_tells_teacher_what_to_do(self):
        r = self.pack("--format", "custom", "--target", "S-01")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("config/report-format.custom.json", r.stderr)
        self.assertIn("→", r.stderr)

    def test_custom_with_file_uses_school_titles(self):
        write(os.path.join(self.tmp, "config", "report-format.custom.json"),
              json.dumps({"label": "某某國小學期評量表", "groupBy": ["報告維度"],
                          "dimensions": ["學習表現", "生活常規"],
                          "sections": [{"title": "學習表現", "length": "150 字以內",
                                        "hint": "校方要求：課堂參與與學習成果。"}]},
                         ensure_ascii=False))
        try:
            r = self.pack("--format", "custom", "--target", "S-01", "--stream", "qualitative")
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            prompt = read(os.path.join(self.out, "S-01-custom-prompt.md"))
            self.assertIn("某某國小學期評量表", prompt)
            self.assertIn("學習表現", prompt)
            self.assertIn("不是A而是B", prompt, "校方格式也要套同一批書寫規則")
        finally:
            os.remove(os.path.join(self.tmp, "config", "report-format.custom.json"))

    def test_pack_never_invents_content(self):
        """腳本只分組、不生成：素材包裡的正文一定逐字出現在本機 md 檔裡。"""
        self.pack("--format", "iep-tracking", "--target", "S-02")
        text = read(os.path.join(self.out, "S-02-iep-tracking-素材包.md"))
        src = read(os.path.join(self.tmp, "data", "students", "S-02", "iep.md"))
        for line in ("排故事的路時他把氾濫放在耕種前面。", "小組討論時他讓出位置。"):
            self.assertIn(line, text)
            self.assertIn(line, src)


class TestExportDocsCard(VerticalTreeBase):
    def test_docx_lists_goals_and_conceptualization(self):
        import re
        import zipfile
        r = run("export_docs.py", "--root", self.tmp, "--out", self.out,
                "--kind", "students", "--target", "S-02", "--local")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        docx = [f for f in os.listdir(self.out) if f.endswith(".docx")][0]
        with zipfile.ZipFile(os.path.join(self.out, docx)) as z:
            xml_text = z.read("word/document.xml").decode("utf-8")
        text = "\n".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", xml_text, re.S))
        self.assertIn("目標 G1｜溝通", text, "IEP 目標要排在紀錄前面")
        self.assertIn("能在一次提示下說出完整請求句。", text)
        self.assertIn("個案概念化", text)
        self.assertIn("連續四週能自行完成課堂轉換", text)


class TestSyncStudentCard(unittest.TestCase):
    """學生卡片（IEP 目標／個案概念化）雙向同步：只有一邊改就照那一邊，兩邊都改不覆蓋。

    這兩塊跟記錄不一樣——它們會被回頭改，所以老師在網頁上補了一條目標、
    同時在電腦上改了評量標準時，腳本絕對不能挑一邊蓋掉另一邊。
    """

    G_LOCAL = [{"id": "G1", "領域": "溝通", "學年目標": "本機版", "學期目標": "",
                "評量方式": "", "評量標準": "", "期程": ""}]
    G_CLOUD = [{"id": "G1", "領域": "溝通", "學年目標": "網頁版", "學期目標": "",
                "評量方式": "", "評量標準": "", "期程": ""}]

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="trk-card-")
        self.orig_root = lib.root()
        lib.set_root(self.tmp)
        self.orig = (lib.get_doc, lib.http)

    def tearDown(self):
        lib.get_doc, lib.http = self.orig
        lib.set_root(self.orig_root)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call(self, local, cloud, baseline_of, dry=False):
        import sync
        lib.save_card("S-02", {"goals": local})
        lib.get_doc = lambda base, path, tok, **kw: ({"goals": cloud}, "t9")
        calls, notes = [], []

        def fake_http(m, base, path, tok, body=None, **kw):
            calls.append({"path": path, "body": body, "mask": kw.get("mask")})
            return {}
        lib.http = fake_http
        if baseline_of is None:                      # 還沒有基準＝這位學生的第一次同步
            state = {}
        else:
            state = {"_cards": {"S-02": lib.card_fingerprint({"goals": baseline_of})}}
        fp = sync.sync_student_card("S-02", "students/S-02", "base", "tok",
                                    state, dry, notes)
        return calls, notes, fp, lib.load_card("S-02")

    def test_local_only_change_is_pushed(self):
        calls, notes, fp, card = self.call(self.G_LOCAL, self.G_CLOUD, self.G_CLOUD)
        self.assertEqual(len(calls), 1, notes)
        self.assertEqual(sorted(calls[0]["mask"]), ["conceptualization", "goals"])
        self.assertEqual(calls[0]["body"]["goals"][0]["學年目標"], "本機版")
        self.assertEqual(card["goals"][0]["學年目標"], "本機版", "本機檔不動")

    def test_web_only_change_is_written_back(self):
        calls, notes, fp, card = self.call(self.G_LOCAL, self.G_CLOUD, self.G_LOCAL)
        self.assertEqual(calls, [], "網頁比較新的時候不該推上去")
        self.assertEqual(card["goals"][0]["學年目標"], "網頁版", "要寫回 card.json")
        self.assertTrue(any("寫回" in n for n in notes), notes)

    def test_both_changed_is_a_conflict_and_nothing_is_overwritten(self):
        both = [{"id": "G1", "領域": "溝通", "學年目標": "上次同步的樣子", "學期目標": "",
                 "評量方式": "", "評量標準": "", "期程": ""}]
        calls, notes, fp, card = self.call(self.G_LOCAL, self.G_CLOUD, both)
        self.assertEqual(calls, [], "兩邊都改過就不准推")
        self.assertEqual(card["goals"][0]["學年目標"], "本機版", "也不准回寫")
        self.assertTrue(any("衝突 卡片" in n for n in notes), notes)

    def test_dry_run_writes_nothing(self):
        calls, notes, fp, card = self.call(self.G_LOCAL, self.G_CLOUD, self.G_CLOUD, dry=True)
        self.assertEqual(calls, [])
        self.assertEqual(card["goals"][0]["學年目標"], "本機版")
        self.assertTrue(any("預演" in n for n in notes), notes)

    def test_first_sync_pushes_local_when_the_cloud_card_is_empty(self):
        """第一次同步沒有基準，雲端那張卡是空的——這不是衝突，是「還沒推上去」。

        沒有這條，安裝時寫進 card.json 的 IEP 目標與個案概念化每次都被報成衝突，
        一輩子上不了網頁。
        """
        calls, notes, fp, card = self.call(self.G_LOCAL, [], None)
        self.assertEqual(len(calls), 1, notes)
        self.assertEqual(calls[0]["body"]["goals"][0]["學年目標"], "本機版")
        self.assertFalse([n for n in notes if "衝突" in n], notes)
        self.assertEqual(fp, lib.card_fingerprint({"goals": self.G_LOCAL}))

    def test_first_sync_pulls_when_local_is_empty(self):
        """反過來：本機還沒有卡片、網頁上已經建了目標 → 寫回來，不要用空的蓋掉他。"""
        calls, notes, fp, card = self.call([], self.G_CLOUD, None)
        self.assertEqual(calls, [])
        self.assertEqual(card["goals"][0]["學年目標"], "網頁版")

    def test_first_sync_with_content_on_both_sides_is_still_a_conflict(self):
        calls, notes, fp, card = self.call(self.G_LOCAL, self.G_CLOUD, None)
        self.assertEqual(calls, [])
        self.assertEqual(card["goals"][0]["學年目標"], "本機版")
        self.assertTrue(any("衝突 卡片" in n for n in notes), notes)

    def test_same_on_both_sides_is_a_no_op(self):
        calls, notes, fp, card = self.call(self.G_LOCAL, self.G_LOCAL, [])
        self.assertEqual(calls, [])
        self.assertEqual(notes, [])
        self.assertEqual(fp, lib.card_fingerprint({"goals": self.G_LOCAL}))


class TestSyncCourseCard(unittest.TestCase):
    """課程卡上的「整體課程紀錄」（overview）雙向同步：規則跟學生卡片一模一樣。

    老師在網頁上寫「這門課的整體紀錄」、又在電腦上補了一句——兩邊都改的時候，
    腳本一樣不准挑一邊蓋掉另一邊。另外守兩件事：推上去的 mask 只有 overview
    （課名與統計是別人的欄位），基準指紋的鍵是 `courses/<id>`（不跟學生代號撞）。
    """

    LOCAL = "本機版：這門課從觀察月亮開始。"
    CLOUD = "網頁版：這門課從觀察月亮開始，後半段走到曆法。"
    CID = "main-block"
    DOC = "courses/main-block"

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="trk-course-card-")
        self.orig_root = lib.root()
        lib.set_root(self.tmp)
        self.orig = (lib.get_doc, lib.http)

    def tearDown(self):
        lib.get_doc, lib.http = self.orig
        lib.set_root(self.orig_root)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def call(self, local, cloud, baseline_of, dry=False, state=None):
        import sync
        path = lib.course_card_path(self.CID)
        lib.save_course_card(path, {"overview": local})
        # 雲端那張卡上還有課名與統計——不能被這一支碰到。
        lib.get_doc = lambda base, p, tok, **kw: (
            {"overview": cloud, "title": "主課程", "recordCount": 3}, "t9")
        calls, notes = [], []

        def fake_http(m, base, p, tok, body=None, **kw):
            calls.append({"path": p, "body": body, "mask": kw.get("mask"),
                          "ut": kw.get("precondition_update_time")})
            return {}
        lib.http = fake_http
        if state is None:
            state = {} if baseline_of is None else {
                "_cards": {sync.course_card_key(self.CID):
                           lib.course_card_fingerprint({"overview": baseline_of})}}
        fp = sync.sync_course_card(self.CID, self.DOC, "base", "tok", state, dry, notes)
        return calls, notes, fp, lib.load_course_card(path)

    def test_local_only_change_is_pushed_with_mask_overview(self):
        calls, notes, fp, card = self.call(self.LOCAL, self.CLOUD, self.CLOUD)
        self.assertEqual(len(calls), 1, notes)
        self.assertEqual(calls[0]["path"], self.DOC)
        self.assertEqual(calls[0]["mask"], ["overview"],
                         "mask 只能有 overview——課名、kind、統計都是網頁那邊的欄位")
        self.assertEqual(list(calls[0]["body"]), ["overview"])
        self.assertEqual(calls[0]["body"]["overview"], self.LOCAL)
        self.assertEqual(calls[0]["ut"], "t9", "PATCH 要帶讀到的 updateTime")
        self.assertEqual(card["overview"], self.LOCAL, "本機檔不動")
        self.assertEqual(fp, lib.course_card_fingerprint({"overview": self.LOCAL}))

    def test_web_only_change_is_written_back(self):
        calls, notes, fp, card = self.call(self.LOCAL, self.CLOUD, self.LOCAL)
        self.assertEqual(calls, [], "網頁比較新的時候不該推上去")
        self.assertEqual(card["overview"], self.CLOUD, "要寫回 card.json")
        self.assertTrue(any("寫回" in n for n in notes), notes)

    def test_both_changed_is_a_conflict_and_nothing_is_overwritten(self):
        calls, notes, fp, card = self.call(self.LOCAL, self.CLOUD, "上次同步的樣子")
        self.assertEqual(calls, [], "兩邊都改過就不准推")
        self.assertEqual(card["overview"], self.LOCAL, "也不准回寫")
        self.assertTrue(any("衝突 課程卡" in n for n in notes), notes)

    def test_dry_run_writes_nothing(self):
        calls, notes, fp, card = self.call(self.LOCAL, self.CLOUD, self.CLOUD, dry=True)
        self.assertEqual(calls, [])
        self.assertEqual(card["overview"], self.LOCAL)
        self.assertTrue(any("預演" in n for n in notes), notes)

    def test_state_key_is_namespaced_under_courses(self):
        """基準指紋的鍵是 `courses/<id>`：裸 id 是學生卡片的格子，不該被當成課程的基準。

        沒有這個前綴，代號同名的課與學生會共用同一格、互相蓋掉對方的基準。
        """
        import sync
        self.assertEqual(sync.course_card_key(self.CID), "courses/main-block")
        bare = {"_cards": {self.CID: lib.course_card_fingerprint({"overview": self.CLOUD})}}
        calls, notes, fp, card = self.call(self.LOCAL, self.CLOUD, None, state=bare)
        self.assertEqual(calls, [], "裸 id 被誤認成基準的話這裡會推上去")
        self.assertEqual(card["overview"], self.LOCAL)
        self.assertTrue(any("衝突 課程卡" in n for n in notes), notes)

    def test_first_sync_pushes_local_when_the_cloud_card_is_empty(self):
        calls, notes, fp, card = self.call(self.LOCAL, "", None)
        self.assertEqual(len(calls), 1, notes)
        self.assertEqual(calls[0]["body"]["overview"], self.LOCAL)
        self.assertFalse([n for n in notes if "衝突" in n], notes)

    def test_first_sync_pulls_when_local_is_empty(self):
        calls, notes, fp, card = self.call("", self.CLOUD, None)
        self.assertEqual(calls, [])
        self.assertEqual(card["overview"], self.CLOUD)

    def test_same_on_both_sides_is_a_no_op(self):
        calls, notes, fp, card = self.call(self.LOCAL, self.LOCAL, "")
        self.assertEqual(calls, [])
        self.assertEqual(notes, [])
        self.assertEqual(fp, lib.course_card_fingerprint({"overview": self.LOCAL}))

    def test_save_keeps_unknown_keys_and_never_grows_student_blocks(self):
        """課程卡是課程卡：存回去不能長出 goals／conceptualization，也不能吃掉別人的鍵。"""
        path = lib.course_card_path(self.CID)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        write(path, json.dumps({"overview": "舊的", "網頁以後加的鍵": "別動我"},
                               ensure_ascii=False))
        lib.save_course_card(path, {"overview": "新的"})
        raw = json.loads(read(path))
        self.assertEqual(raw["overview"], "新的")
        self.assertEqual(raw["網頁以後加的鍵"], "別動我")
        self.assertNotIn("goals", raw)
        self.assertNotIn("conceptualization", raw)


if __name__ == "__main__":
    unittest.main()
