#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""記錄格式的迴歸測試：解析、還原、紀錄 id、內容指紋、四種目標。零網路、零第三方相依。

    python3 -m unittest discover scripts/tests

守的是什麼：
  · 紀錄 id 由「日期＋建立時間」決定，不由它在檔案裡的出現順序決定。
    用出現順序編號的話，在檔案中間插入一則會讓後面每一則都改名，下一次同步就把
    舊副本當成新紀錄再建一次。
  · 欄位列解析要寬鬆：設定裡沒有的欄位名照收（改欄位名不需要搬資料）。
  · content_hash 要穩定：同樣的內容換個欄位順序、多幾個空白，指紋不能變。
"""
import os
import sys
import unittest
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import lib


def write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


class TestRid(unittest.TestCase):
    def test_first_of_day_is_plain_date(self):
        self.assertEqual(lib.rid_for("2026-09-10", None), "2026-09-10")

    def test_with_minute_and_second(self):
        self.assertEqual(lib.rid_for("2026-09-10", "14:35"), "2026-09-10-1435")
        self.assertEqual(lib.rid_for("2026-09-10", "14:35:12"), "2026-09-10-143512")

    def test_round_trip(self):
        self.assertIsNone(lib.time_from_rid("2026-09-10", "2026-09-10"))
        self.assertEqual(lib.time_from_rid("2026-09-10", "2026-09-10-1435"), "14:35")
        self.assertEqual(lib.time_from_rid("2026-09-10", "2026-09-10-143512"), "14:35:12")

    def test_old_serial_is_not_mistaken_for_time(self):
        self.assertIsNone(lib.time_from_rid("2026-09-10", "2026-09-10-2"))


class TestParseBlock(unittest.TestCase):
    def test_minimal(self):
        b = lib.parse_block(["## 2026-09-10 #課堂", "", "正文一", "正文二"])
        self.assertEqual(b["date"], "2026-09-10")
        self.assertIsNone(b["time"])
        self.assertEqual(b["tags"], ["#課堂"])
        self.assertEqual(b["fields"], {})
        self.assertEqual(b["related"], [])
        self.assertEqual(b["body"], "正文一\n正文二")

    def test_fields_and_related(self):
        b = lib.parse_block([
            "## 2026-09-10 14:35 #公文 #計畫申請",
            "期限：2026-09-20",
            "辦理情形：處理中",
            "關聯：students/S-03/2026-09-10; courses/main-block/2026-09-09-1435",
            "",
            "正文",
        ])
        self.assertEqual(b["rid"], "2026-09-10-1435")
        self.assertEqual(b["fields"], {"期限": "2026-09-20", "辦理情形": "處理中"})
        self.assertEqual(b["related"],
                         ["students/S-03/2026-09-10", "courses/main-block/2026-09-09-1435"])
        self.assertEqual(b["body"], "正文")

    def test_lenient_unknown_field(self):
        """設定裡沒有的欄位名也要收——欄位是表單建議，不是 schema 閘（§2.2、紅隊 #13）。"""
        b = lib.parse_block(["## 2026-09-10", "承辦人分機：2317", "", "正文"])
        self.assertEqual(b["fields"], {"承辦人分機": "2317"})

    def test_body_starting_with_non_field_line(self):
        """標題後緊接著不像欄位列的行 → 從那裡開始就是正文，不要吃掉它。"""
        b = lib.parse_block(["## 2026-09-10 #課堂", "今天上課很順利", "第二段"])
        self.assertEqual(b["fields"], {})
        self.assertEqual(b["body"], "今天上課很順利\n第二段")

    def test_related_full_width_separator(self):
        b = lib.parse_block(["## 2026-09-10", "關聯：students/S-01/2026-09-01；class/main/2026-09-02", "", "x"])
        self.assertEqual(b["related"], ["students/S-01/2026-09-01", "class/main/2026-09-02"])

    def test_colon_inside_body_is_not_a_field(self):
        b = lib.parse_block(["## 2026-09-10", "", "他說：我先用完給你"])
        self.assertEqual(b["fields"], {})
        self.assertIn("他說：我先用完給你", b["body"])


class TestRenderRoundTrip(unittest.TestCase):
    def test_round_trip(self):
        fields = {"期限": "2026-09-20", "辦理情形": "處理中"}
        related = ["students/S-03/2026-09-10"]
        lines = lib.render_block("2026-09-10", "14:35", ["#公文"], fields, related, "第一段\n\n第二段")
        back = lib.parse_block(lines)
        self.assertEqual(back["date"], "2026-09-10")
        self.assertEqual(back["time"], "14:35")
        self.assertEqual(back["tags"], ["#公文"])
        self.assertEqual(back["fields"], fields)
        self.assertEqual(back["related"], related)
        self.assertEqual(back["body"], "第一段\n\n第二段")
        self.assertEqual(back["hash"], lib.content_hash(["#公文"], fields, related, "第一段\n\n第二段"))

    def test_round_trip_no_fields(self):
        lines = lib.render_block("2026-09-10", None, ["#課堂", "#人際"], {}, [], "正文")
        back = lib.parse_block(lines)
        self.assertEqual(back["rid"], "2026-09-10")
        self.assertEqual(back["tags"], ["#課堂", "#人際"])
        self.assertEqual(back["body"], "正文")


class TestContentHash(unittest.TestCase):
    def test_stable_across_field_order(self):
        a = lib.content_hash(["#a"], {"甲": "1", "乙": "2"}, ["x/y/z"], "正文")
        b = lib.content_hash(["#a"], {"乙": "2", "甲": "1"}, ["x/y/z"], "正文")
        self.assertEqual(a, b)

    def test_tag_normalisation(self):
        self.assertEqual(lib.content_hash(["課堂"], {}, [], "x"),
                         lib.content_hash(["#課堂"], {}, [], "x"))

    def test_trailing_whitespace_ignored(self):
        self.assertEqual(lib.content_hash([], {}, [], "正文"),
                         lib.content_hash([], {}, [], "正文\n\n"))

    def test_different_body_changes_hash(self):
        self.assertNotEqual(lib.content_hash([], {}, [], "甲"),
                            lib.content_hash([], {}, [], "乙"))

    def test_length_is_16(self):
        self.assertEqual(len(lib.content_hash(["#a"], {}, [], "x")), 16)


class TestParseFile(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="trk-test-")
        self.path = os.path.join(self.tmp, "records.md")

    def test_blocks_and_offsets(self):
        write(self.path,
              "---\nid: S-01\n---\n\n# S-01\n\n"
              "## 2026-09-01 #課堂\n甲\n\n"
              "## 2026-09-01 14:35 #人際\n乙\n")
        lines, blocks = lib.parse_file(self.path)
        self.assertEqual([b["rid"] for b in blocks], ["2026-09-01", "2026-09-01-1435"])
        self.assertEqual(lines[blocks[0]["start"]], "## 2026-09-01 #課堂")
        self.assertEqual(blocks[0]["end"], blocks[1]["start"])

    def test_missing_file(self):
        self.assertEqual(lib.parse_file(os.path.join(self.tmp, "nope.md")), ([], []))


class TestRoster(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="trk-test-")
        self.data = os.path.join(self.tmp, "data")
        os.makedirs(self.data)

    def test_header_and_prefix(self):
        write(os.path.join(self.data, "roster.csv"),
              "編號,姓名\n1,學生甲\n02,學生乙\nS-03,學生丙\n")
        r = lib.load_roster({"id_prefix": "S"}, self.data)
        self.assertEqual(r, {"S-01": "學生甲", "S-02": "學生乙", "S-03": "學生丙"})

    def test_custom_prefix(self):
        write(os.path.join(self.data, "roster.csv"), "編號,姓名\n7,某某\n")
        r = lib.load_roster({"id_prefix": "6B"}, self.data)
        self.assertEqual(list(r), ["6B-07"])

    def test_missing_roster_is_empty(self):
        self.assertEqual(lib.load_roster({}, self.data), {})

    def test_third_column_is_stream_membership(self):
        """第三欄＝這位學生列入哪些個案型記錄類型（分號分隔，可空）。"""
        write(os.path.join(self.data, "roster.csv"),
              "代號,姓名,類型\n01,學生甲,\n02,學生乙,case\n03,學生丙,case;iep\n")
        rows = lib.load_roster_rows({"id_prefix": "S"}, self.data)
        self.assertEqual(rows["S-01"]["streams"], [])
        self.assertEqual(rows["S-02"]["streams"], ["case"])
        self.assertEqual(rows["S-03"], {"name": "學生丙", "streams": ["case", "iep"]})

    def test_two_column_roster_still_reads(self):
        """v2 的兩欄名冊照樣讀得進來（第三欄當成沒列入任何個案型類型）。"""
        write(os.path.join(self.data, "roster.csv"), "編號,姓名\n01,學生甲\n")
        self.assertEqual(lib.load_roster_rows({}, self.data)["S-01"]["streams"], [])

    def test_row_without_name_keeps_streams(self):
        """名字還沒填的列也要收——名冊常常先有代號、名字慢慢補。"""
        write(os.path.join(self.data, "roster.csv"), "代號,姓名,類型\nS-05,,iep\n")
        self.assertEqual(lib.load_roster_rows({}, self.data)["S-05"]["streams"], ["iep"])
        self.assertEqual(lib.load_roster({}, self.data), {})     # 姓名對照表裡沒有他

    def test_save_round_trip(self):
        rows = {"S-02": {"name": "學生乙", "streams": ["case", "iep"]},
                "S-01": {"name": "學生甲", "streams": []}}
        lib.save_roster_rows(rows, self.data)
        with open(os.path.join(self.data, "roster.csv"), encoding="utf-8") as f:
            text = f.read()
        self.assertTrue(text.startswith("代號,姓名,類型"))
        self.assertIn("S-02,學生乙,case;iep", text)
        self.assertEqual(lib.load_roster_rows({}, self.data), rows)


class TestTargets(unittest.TestCase):
    """守的是：學生目標＝每位學生 × 他所屬的每一種記錄類型，各一個檔。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="trk-test-")
        self.data = os.path.join(self.tmp, "data")
        os.makedirs(self.data)
        write(os.path.join(self.data, "roster.csv"),
              "代號,姓名,類型\n01,學生甲,\n02,學生乙,case\n")
        self.tabs = {
            "students": {"enabled": True, "streams": [
                {"id": "homeroom", "label": "導師班級學生紀錄", "scope": "class"},
                {"id": "case", "label": "個案追蹤", "scope": "case"},
            ]},
            "courses": {"enabled": True, "list": [{"id": "main-block", "title": "主課程"}]},
            "business": {"enabled": True, "groups": [{"id": "paperwork", "label": "公文"}]},
        }

    def tg(self, tabs=None):
        return {t["key"]: t for t in lib.targets({"id_prefix": "S"}, tabs or self.tabs, self.data)}

    def test_four_kinds(self):
        tg = lib.targets({"id_prefix": "S"}, self.tabs, self.data)
        kinds = [t["kind"] for t in tg]
        self.assertEqual(kinds.count("students"), 3)     # 兩位 × 導師類型 ＋ 一位個案
        self.assertEqual(kinds.count("class"), 1)        # 只有 scope:class 的類型有班級整體觀察
        self.assertEqual(kinds.count("courses"), 1)
        self.assertEqual(kinds.count("business"), 1)

    def test_case_stream_only_covers_listed_students(self):
        tg = self.tg()
        self.assertIn("students/S-02/case", tg)
        self.assertNotIn("students/S-01/case", tg, "沒被列入第三欄的學生不該出現在個案型類型裡")

    def test_case_stream_picks_up_existing_file(self):
        """名冊第三欄被清掉、但檔案還在 → 目標還是留著（不讓紀錄憑空消失）。"""
        p = os.path.join(self.data, "students", "S-01", "case.md")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        write(p, "# S-01\n")
        self.assertIn("students/S-01/case", self.tg())

    def test_paths_and_collections(self):
        tg = self.tg()
        self.assertTrue(tg["students/S-01/homeroom"]["path"]
                        .endswith("data/students/S-01/observations.md"),
                        "導師班級紀錄要沿用 v2 的 observations.md")
        self.assertTrue(tg["students/S-02/case"]["path"].endswith("data/students/S-02/case.md"))
        self.assertEqual(tg["students/S-02/case"]["sourceFile"], "students/S-02/case.md")
        self.assertEqual(tg["students/S-01/homeroom"]["records"], "students/S-01/records")
        self.assertEqual(tg["students/S-02/case"]["records"], "students/S-02/records",
                         "同一位學生的各種類型共用一個雲端集合，靠 stream 欄位分流")
        self.assertEqual(tg["class/main/homeroom"]["records"], "class-observations")
        self.assertIsNone(tg["class/main/homeroom"]["card"])
        self.assertEqual(tg["courses/main-block"]["records"], "courses/main-block/records")
        self.assertEqual(tg["business/paperwork"]["card"], "business/paperwork")
        self.assertIsNone(tg["business/paperwork"]["stream"])

    def test_no_streams_means_no_student_targets(self):
        """零預設：一種類型都沒勾 → 學生分頁一個目標都沒有。"""
        tabs = dict(self.tabs, students={"enabled": True, "streams": []})
        tg = lib.targets({"id_prefix": "S"}, tabs, self.data)
        self.assertFalse([t for t in tg if t["kind"] in ("students", "class")])

    def test_legacy_tabs_without_streams_key(self):
        """v2 舊設定（沒有 streams 鍵）＝只有導師班級紀錄一種，舊檔原地可用。"""
        tabs = dict(self.tabs, students={"enabled": True})
        tg = self.tg(tabs)
        self.assertIn("students/S-01/homeroom", tg)
        self.assertTrue(tg["students/S-01/homeroom"]["path"].endswith("observations.md"))

    def test_disabled_tab_drops_targets(self):
        tabs = dict(self.tabs, business={"enabled": False, "groups": [{"id": "paperwork"}]})
        self.assertFalse([t for t in lib.targets({}, tabs, self.data) if t["kind"] == "business"])

    def test_find_target(self):
        t = lib.find_target({"id_prefix": "S"}, self.tabs, "class", "", "homeroom", self.data)
        self.assertEqual((t["id"], t["stream"]), ("main", "homeroom"))
        self.assertIsNone(lib.find_target({}, self.tabs, "students", "S-99", "homeroom", self.data))

    def test_find_target_needs_stream_when_ambiguous(self):
        """一位學生有兩種類型時，沒指定類型就不該猜——回 None，由呼叫端要求 --stream。"""
        self.assertIsNone(lib.find_target({"id_prefix": "S"}, self.tabs, "students", "S-02",
                                          None, self.data))
        self.assertIsNotNone(lib.find_target({"id_prefix": "S"}, self.tabs, "students", "S-01",
                                             None, self.data))


class TestStreamHelpers(unittest.TestCase):
    def test_stream_file_names(self):
        self.assertEqual(lib.stream_file("homeroom"), "observations.md")
        self.assertEqual(lib.stream_file("case"), "case.md")

    def test_student_streams_shapes(self):
        self.assertEqual([s["id"] for s in lib.student_streams({"students": {}})], ["homeroom"])
        self.assertEqual(lib.student_streams({"students": {"streams": []}}), [])
        got = lib.student_streams({"students": {"streams": [{"id": "iep"}]}})
        self.assertEqual(got[0]["scope"], "class", "沒寫 scope 就當 class")

    def test_library_has_five_plus_open_option(self):
        streams = lib.load_stream_library()["streams"]
        ids = [s["id"] for s in streams]
        self.assertEqual(ids, ["homeroom", "subject", "case", "iep", "counseling", "custom"])
        self.assertTrue(streams[-1].get("open"), "最後一筆是「不在清單裡」的開放選項")
        by_id = {s["id"]: s for s in streams}
        self.assertEqual(by_id["case"]["scope"], "case")
        self.assertEqual(by_id["subject"]["scope"], "class")
        self.assertIn("科目", [f["name"] for f in by_id["subject"]["fields"]])
        self.assertIn("#IEP", by_id["iep"]["tags"])


class TestNames(unittest.TestCase):
    def test_find_names(self):
        self.assertEqual(lib.find_names("今天陳小明很專心", ["陳小明", "林大同"]), ["陳小明"])
        self.assertEqual(lib.find_names("今天 S-03 很專心", ["陳小明"]), [])


if __name__ == "__main__":
    unittest.main()
