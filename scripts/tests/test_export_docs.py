#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""export_docs.py 的測試：一鍵匯出 Word／PDF。零網路，全部在暫存樹裡跑。

    python3 -m unittest discover scripts/tests

樹是用 `setup.py --answers` 建的（跟老師實際裝出來的一模一樣），再用 `append_record.py`
塞幾則記錄——測的是「老師真的會跑的那條路徑」，不是內部函式。
"""
import os
import re
import sys
import json
import shutil
import zipfile
import datetime
import unittest
import tempfile
import subprocess
import xml.dom.minidom

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PKG = os.path.dirname(SCRIPTS)
sys.path.insert(0, SCRIPTS)

ANSWERS = os.path.join(PKG, "templates", "answers.example.json")


def run(script, *args, **kw):
    cmd = [sys.executable, os.path.join(SCRIPTS, script), *args]
    return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300, **kw)


def write(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def docx_xml(path):
    """把 .docx 裡的 word/document.xml 讀回來（順便證明它是個合法的 zip）。"""
    with zipfile.ZipFile(path) as z:
        return z.read("word/document.xml").decode("utf-8")


def plain(xml_text):
    """document.xml → 純文字（把 <w:t> 裡的字串接起來），方便斷言內容。"""
    return "\n".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", xml_text, re.S))


class ExportDocsBase(unittest.TestCase):
    """一棵共用的樹：三位學生（甲乙丙）、兩種記錄類型、班級觀察、課程、業務組。"""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="trk-docs-")
        r = run("setup.py", "--answers", ANSWERS, "--root", cls.tmp,
                "--skip-network", "--skip-doctor")
        assert r.returncode == 0, r.stdout + r.stderr
        write(os.path.join(cls.tmp, "data", "roster.csv"),
              "代號,姓名,類型\n01,測試甲,\n02,測試乙,case\n03,測試丙,\n")
        draft = write(os.path.join(cls.tmp, "draft.md"),
                      "上課主動舉手兩次。\n\n第二段：小組討論時願意讓步。")
        draft2 = write(os.path.join(cls.tmp, "draft2.md"), "先做一次個別晤談。")

        def append(*args):
            rr = run("append_record.py", "--root", cls.tmp, "--content-file", draft, *args)
            assert rr.returncode == 0, rr.stdout + rr.stderr

        append("--kind", "students", "--target", "S-01", "--stream", "homeroom",
               "--date", "2026-09-03")
        append("--kind", "students", "--target", "S-02", "--stream", "homeroom",
               "--date", "2026-09-01", "--tags", "#課堂 #人際")
        rr = run("append_record.py", "--root", cls.tmp, "--content-file", draft2,
                 "--kind", "students", "--target", "S-02", "--stream", "case",
                 "--date", "2026-09-05", "--tags", "#初談",
                 "--fields-json", '{"來源":"導師轉介","主訴／議題":"上課分心"}')
        assert rr.returncode == 0, rr.stdout + rr.stderr
        append("--kind", "class", "--target", "main", "--stream", "homeroom",
               "--date", "2026-09-02", "--tags", "#班級")
        rr = run("append_record.py", "--root", cls.tmp, "--content-file", draft2,
                 "--kind", "business", "--target", "meetings", "--date", "2026-09-04",
                 "--fields-json", '{"會議名稱":"學年會議","地點":"會議室"}')
        assert rr.returncode == 0, rr.stdout + rr.stderr

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        self.out = tempfile.mkdtemp(prefix="trk-out-")

    def tearDown(self):
        shutil.rmtree(self.out, ignore_errors=True)

    def export(self, *args, **kw):
        r = run("export_docs.py", "--root", self.tmp, "--out", self.out, *args, **kw)
        return r

    def only(self, ext):
        hits = [os.path.join(self.out, f) for f in sorted(os.listdir(self.out))
                if f.endswith(ext)]
        self.assertEqual(len(hits), 1, "%s 應該剛好產生一個：%s" % (ext, os.listdir(self.out)))
        return hits[0]


class TestStudentDocx(ExportDocsBase):
    def test_one_student_docx(self):
        r = self.export("--kind", "students", "--target", "S-02", "--local", "--docx")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        xml_text = docx_xml(self.only(".docx"))
        text = plain(xml_text)
        self.assertIn("測試乙", text, "名冊姓名要出現在文件裡")
        self.assertIn("S-02", text, "代號要出現在文件裡")
        self.assertIn("導師班級學生紀錄", text, "兩種記錄類型都要在（這是第一種）")
        self.assertIn("個案追蹤", text, "兩種記錄類型都要在（這是第二種）")
        self.assertIn("上課主動舉手兩次。", text)
        self.assertIn("先做一次個別晤談。", text)
        self.assertIn("來源", text, "欄位表的鍵")
        self.assertIn("導師轉介", text, "欄位表的值")
        self.assertIn("主訴／議題", text)
        self.assertIn("<w:tbl>", xml_text, "欄位要用兩欄表格排")
        self.assertNotIn("測試甲", text, "只匯出這一位，別把別人的紀錄帶進來")

    def test_document_xml_is_well_formed(self):
        r = self.export("--kind", "students", "--target", "S-02", "--local")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with zipfile.ZipFile(self.only(".docx")) as z:
            for part in ("[Content_Types].xml", "_rels/.rels", "word/document.xml",
                         "word/styles.xml", "word/fontTable.xml",
                         "word/_rels/document.xml.rels"):
                with self.subTest(part=part):
                    xml.dom.minidom.parseString(z.read(part))     # 解析失敗＝Word 打不開
        styles = zipfile.ZipFile(self.only(".docx")).read("word/styles.xml").decode("utf-8")
        for style in ("Heading1", "Heading2", "Heading3", "TableGrid"):
            self.assertIn(style, styles)
        self.assertIn("Noto Sans TC", styles)

    def test_docx_escapes_xml(self):
        """正文裡的 & 與 < 不能把文件弄壞（沒跳脫的話 Word 會說檔案損毀）。"""
        draft = write(os.path.join(self.out, "x.md"), "數學 & 自然 <重要> 的一節")
        r = run("append_record.py", "--root", self.tmp, "--content-file", draft,
                "--kind", "students", "--target", "S-01", "--stream", "homeroom",
                "--date", "2026-09-09")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        r = self.export("--kind", "students", "--target", "S-01", "--local")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        raw = docx_xml(self.only(".docx"))
        xml.dom.minidom.parseString(raw.encode("utf-8"))
        self.assertIn("&amp;", raw)
        self.assertIn("&lt;重要&gt;", raw)

    def test_stream_filter(self):
        r = self.export("--kind", "students", "--target", "S-02", "--stream", "case", "--local")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = plain(docx_xml(self.only(".docx")))
        self.assertIn("先做一次個別晤談。", text)
        self.assertNotIn("上課主動舉手兩次。", text, "--stream case 不該帶出導師班級紀錄")

    def test_unknown_stream_is_two_line_error(self):
        r = self.export("--kind", "students", "--target", "S-02", "--stream", "nope", "--local")
        self.assertEqual(r.returncode, 1)
        self.assertIn("✗", r.stderr)
        self.assertIn("→", r.stderr)

    def test_unknown_target_is_two_line_error(self):
        r = self.export("--kind", "students", "--target", "S-99", "--local")
        self.assertEqual(r.returncode, 1)
        self.assertIn("✗", r.stderr)
        self.assertIn("→", r.stderr)


class TestAllStudents(ExportDocsBase):
    def test_all_with_class(self):
        r = self.export("--kind", "students", "--target", "all", "--with-class", "--local")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        raw = docx_xml(self.only(".docx"))
        text = plain(raw)
        heads = re.findall(r'<w:pStyle w:val="Heading2"/></w:pPr><w:r><w:t[^>]*>(.*?)</w:t>', raw)
        self.assertEqual(heads, ["班級整體觀察", "測試甲（S-01）", "測試乙（S-02）", "測試丙（S-03）"],
                         "每位學生一個 H2，班級整體觀察排最前面")
        self.assertIn("（無記錄）", text, "沒有紀錄的學生要明講「（無記錄）」")
        after_c = text.split("測試丙（S-03）", 1)[1]
        self.assertIn("（無記錄）", after_c, "測試丙沒有紀錄")

    def test_from_tomorrow_gives_all_empty(self):
        """把起日設到明天 → 每一節都是「（無記錄）」，而不是整份文件不見。"""
        tomorrow = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        r = self.export("--kind", "students", "--target", "all", "--with-class",
                        "--local", "--from", tomorrow)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        text = plain(docx_xml(self.only(".docx")))
        self.assertEqual(text.count("（無記錄）"), 4, "四節（班級＋三位學生）全部無記錄")
        self.assertNotIn("上課主動舉手兩次。", text)
        self.assertIn("0 則記錄", r.stdout)

    def test_bad_date_is_two_line_error(self):
        r = self.export("--kind", "students", "--target", "all", "--local", "--from", "2026/09/01")
        self.assertEqual(r.returncode, 1)
        self.assertIn("✗", r.stderr)
        self.assertIn("→", r.stderr)


class TestBusinessAndPdf(ExportDocsBase):
    def test_business_group_field_table(self):
        r = self.export("--kind", "business", "--target", "meetings", "--local")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        raw = docx_xml(self.only(".docx"))
        text = plain(raw)
        self.assertIn("會議紀錄", text, "H2 是組名")
        self.assertIn("會議名稱", text)
        self.assertIn("學年會議", text)
        self.assertIn("<w:tbl>", raw, "業務組的欄位也要有欄位表")
        self.assertIn("2026-09-04", text)

    def test_pdf_falls_back_to_html_without_chrome(self):
        """沒有 Chrome 的機器：不當掉、不假裝成功——留下 HTML 並告訴老師怎麼自己印。"""
        env = dict(os.environ, PATH="", TRK_CHROME="/nonexistent/chrome")
        r = self.export("--kind", "business", "--target", "meetings", "--local", "--pdf",
                        env=env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual([f for f in os.listdir(self.out) if f.endswith(".pdf")], [])
        html_path = self.only(".html")
        with open(html_path, encoding="utf-8") as f:
            page = f.read()
        self.assertIn("@media print", page)
        self.assertIn("page-break-inside: avoid", page)
        self.assertIn("size: A4", page)
        self.assertIn("學年會議", page)
        self.assertIn("列印", r.stdout + r.stderr)

    def test_course_overview_comes_before_the_records(self):
        """整體課程紀錄（課程卡上的 overview）：排在那門課的逐日紀錄前面，而且是段落不是表格。

        Word 的表格儲存格會把一整篇敘述擠成一個框、分頁時整塊跳頁——所以它走段落。
        """
        card = os.path.join(self.tmp, "data", "courses", "main-block", "card.json")
        os.makedirs(os.path.dirname(card), exist_ok=True)
        write(card, json.dumps({"overview": "這門課從觀察月亮開始。\n\n後半段走到曆法。"},
                               ensure_ascii=False))
        self.addCleanup(os.remove, card)
        r = self.export("--kind", "courses", "--target", "main-block", "--local", "--html")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        xml_text = docx_xml(self.only(".docx"))
        text = plain(xml_text)
        self.assertIn("整體課程紀錄", text)
        self.assertIn("這門課從觀察月亮開始。", text)
        self.assertIn("後半段走到曆法。", text, "空行分開的每一段都要在")
        self.assertLess(text.index("整體課程紀錄"), text.index("（無記錄）"),
                        "整體課程紀錄要排在紀錄前面")
        self.assertNotIn("<w:tbl>", xml_text, "它是段落，不是欄位表的儲存格")
        with open(self.only(".html"), encoding="utf-8") as f:
            page = f.read()
        self.assertIn("<h3>整體課程紀錄</h3>", page)
        self.assertIn('<p class="body">這門課從觀察月亮開始。</p>', page)

    def test_prints_source_and_pii_warning(self):
        r = self.export("--kind", "courses", "--target", "main-block", "--local")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("資料來源：", r.stdout)
        self.assertIn("匯出檔含真名，別放到公開的地方", r.stdout)
        self.assertIn(".docx", r.stdout, "結尾要印出每個產出檔的路徑")

    def test_auto_source_picks_local_when_md_exists(self):
        """不給 --local 也不該連網：本機有 md 就走本機（連不上網的教室也能匯出）。"""
        r = self.export("--kind", "class")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("本機 markdown", r.stdout)
        self.assertIn("班級整體觀察", plain(docx_xml(self.only(".docx"))))


if __name__ == "__main__":
    unittest.main()
