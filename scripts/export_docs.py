#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""export_docs.py — 一鍵把記錄匯出成 Word（.docx）與 PDF：期末大量匯出、離線列印用。

每一位學生、每一門課程、每一個業務組、班級整體觀察，以及「所有學生」都能一鍵出文件。
零第三方套件：`.docx` 用標準庫 `zipfile` 直接寫最小 OOXML；`.pdf` 借你機器上的 Chrome
（`--headless --print-to-pdf`）印，沒有 Chrome 就把排版好的 HTML 留下來，你自己開瀏覽器
按列印→儲存為 PDF（手機也行）。

資料從哪裡來：預設先看本機 `data/` 有沒有 markdown，有就讀本機（不連網、最快）；
一個 md 都沒有才連你的 Firestore。`--local` ＝不管怎樣都只讀本機。每次都會印出用了哪一種。

用法：
  python3 scripts/export_docs.py --kind students --target S-03
      一位學生（他所有記錄類型）→ exports/students-S-03-<日期>.docx
  python3 scripts/export_docs.py --kind students --target S-03 --stream case --pdf
      只匯出他的個案追蹤，順便印一份 PDF
  python3 scripts/export_docs.py --kind students --target all --with-class --pdf
      全班一份文件（每位學生一節，含名冊姓名），班級整體觀察排在最前面
  python3 scripts/export_docs.py --kind courses --target main-block
  python3 scripts/export_docs.py --kind business --target meetings --from 2026-08-01 --to 2026-12-31
  python3 scripts/export_docs.py --kind class --pdf --html
      班級整體觀察，PDF 與 HTML 都留下來

匯出檔含名冊真名（因為是老師自己看的），一律留在你自己的機器上——別放到任何公開的地方。
"""
import os
import re
import sys
import html
import time
import shutil
import zipfile
import datetime
import argparse
import subprocess
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib
import hostos
import export_records

KIND_LABEL = export_records.KIND_LABEL
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
NO_RECORD = "（無記錄）"
OVERVIEW_HEADING = export_records.OVERVIEW_HEADING
PII_WARNING = "匯出檔含真名，別放到公開的地方"


# ── XML／文字工具 ────────────────────────────────────────────────────────
_ILLEGAL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def xe(text):
    """XML 跳脫（含屬性用的引號），順手拿掉 XML 1.0 不合法的控制字元。

    老師的正文裡什麼都可能有（貼上來的 &、<、智慧引號…），沒跳脫的話 Word 會直接
    說「檔案損毀」——這是自己寫 OOXML 最容易踩的一個洞。
    """
    return html.escape(_ILLEGAL.sub("", str("" if text is None else text)), quote=True)


def safe_name(text):
    """檔名用：只換掉檔案系統不吃的字元（保留中文，與網頁端 safeFileName 一致）。"""
    return re.sub(r'[\\/:*?"<>|\x00-\x1f\s]+', "-", str(text or "")).strip("-.") or "export"


# ── 取資料（沿用 export_records 的載入函式，不另寫一套）──────────────────
def pick_source(kit, tabs, force_local):
    """決定讀本機還是讀 Firestore，回傳 (local_only, 說明文字)。"""
    if force_local:
        return True, "本機 markdown（--local）"
    has_md = any(os.path.exists(t["path"]) for t in lib.targets(kit, tabs))
    if has_md:
        return True, "本機 markdown（data/，不連網）"
    return False, "Firestore（本機找不到任何 md 檔）"


def in_range(rec, dfrom, dto):
    d = rec.get("date") or ""
    if dfrom and (not d or d < dfrom):
        return False
    if dto and (not d or d > dto):
        return False
    return True


def student_title(sid, roster):
    """學生那一節的標題：姓名（代號）；名冊還沒填姓名就只有代號。"""
    name = roster.get(sid)
    return "%s（%s）" % (name, sid) if name else sid


def gather(data, kind, target, streams, dfrom, dto, with_class):
    """把 collect() 的結果整理成一份文件要的「節」清單。

    一節＝一個對象（一位學生／一門課／一個業務組／班級整體觀察）。同一位學生的各種
    記錄類型會合併成一節、依日期排序，每一則的標題再標出它是哪一種類型。
    """
    roster = data.get("roster") or {}
    tg = data["targets"]

    def recs_of(items):
        out = []
        for t in items:
            if streams and t.get("stream") and t["stream"] not in streams:
                continue
            for r in t["records"]:
                if not in_range(r, dfrom, dto):
                    continue
                out.append(dict(r, streamLabel=t.get("streamLabel") or ""))
        out.sort(key=lambda r: (r.get("date") or "", r.get("rid") or ""))
        return out

    sections, title = [], ""
    if kind == "students":
        ids = sorted({t["id"] for t in tg if t["kind"] == "students"})
        if target != "all":
            if target not in ids:
                lib.die("找不到學生 %s" % target,
                        "代號要跟 data/roster.csv 一樣（例如 S-03）；"
                        "想匯出全部就用 `--target all`。")
            ids = [target]
        if with_class and target == "all":
            sections.append({"title": "班級整體觀察",
                             "records": recs_of([t for t in tg if t["kind"] == "class"])})
        for sid in ids:
            # 學生卡片上的底稿（IEP 目標／個案概念化）排在那一位的紀錄前面——
            # 評鑑與個案報告一定要先看得到目標與概念化，才讀得懂後面每一則在追什麼。
            card = lib.load_card(sid)
            sections.append({"title": student_title(sid, roster),
                             "card": card,
                             "records": recs_of([t for t in tg
                                                 if t["kind"] == "students" and t["id"] == sid])})
        title = "學生記錄　%s" % ("全部學生" if target == "all" else student_title(ids[0], roster))
    elif kind == "class":
        sections.append({"title": "班級整體觀察",
                         "records": recs_of([t for t in tg if t["kind"] == "class"])})
        title = "班級整體觀察"
    else:
        items = [t for t in tg if t["kind"] == kind]
        ids = [t["id"] for t in items]
        if target != "all":
            if target not in ids:
                lib.die("找不到%s %s" % (KIND_LABEL[kind], target),
                        "id 要跟 config/tabs.json 裡的一樣；跑 "
                        "`python3 scripts/export_records.py --local --kind %s` 可以看到有哪些。" % kind)
            items = [t for t in items if t["id"] == target]
        for t in items:
            sec = {"title": t["label"], "records": recs_of([t])}
            if kind == "courses":
                # 整體課程紀錄排在那一門課的逐日紀錄前面——先看得到這門課整體在做什麼，
                # 後面每一天的紀錄才讀得懂（跟學生的 IEP 目標擺在同一個位置、同一個理由）。
                sec["card"] = lib.load_course_card(lib.course_card_path(t["id"]))
            sections.append(sec)
        title = "%s　%s" % (KIND_LABEL[kind],
                            "全部" if target == "all" else items[0]["label"])
    return sections, title


def card_blocks(card):
    """學生卡片 → [(小節標題, [(鍵, 值)…])…]；卡片上這兩塊都空的就回空清單。

    IEP 的每一條目標一個小節（目標編號當標題），個案概念化一個小節（固定五格）。
    """
    out = []
    for g in ((card or {}).get("goals") or []):
        rows = [(k, g.get(k, "")) for k in lib.GOAL_KEYS[1:] if str(g.get(k, "")).strip()]
        if rows:
            out.append(("目標 %s｜%s" % (g.get("id", ""), g.get("領域") or "（沒寫領域）"), rows))
    con = (card or {}).get("conceptualization") or {}
    rows = [(k, con.get(k, "")) for k in lib.CONCEPT_KEYS if str(con.get(k, "")).strip()]
    if rows:
        out.append(("個案概念化", rows))
    return out


def overview_paras(card):
    """課程卡上的「整體課程紀錄」→ 一段一段的文字（空的就回空清單）。

    它跟 IEP 目標那種「欄位表」不一樣——是一整段敘述，所以走段落不走 _table：
    塞進表格的儲存格裡，Word 會把整篇文章擠成一個框、分頁時整塊跳到下一頁。
    """
    text = str((card or {}).get("overview") or "").strip()
    if not text:
        return []
    return [p.strip("\n") for p in re.split(r"\n\s*\n", text) if p.strip()]


def rec_heading(rec):
    """一則的標題列：`日期 · 類型 · #標籤`（沒有的就不佔位）。"""
    date = rec.get("date") or (rec.get("rid") or "")[:10]
    tm = lib.time_from_rid(date, rec.get("rid") or "")
    parts = [date + ((" " + tm) if tm else "")]
    if rec.get("streamLabel"):
        parts.append(rec["streamLabel"])
    if rec.get("tags"):
        parts.append(" ".join(rec["tags"]))
    return " · ".join([p for p in parts if p])


def subtitle(source_note, dfrom, dto, streams):
    span = "全部日期"
    if dfrom or dto:
        span = "%s 至 %s" % (dfrom or "最早", dto or "最新")
    return "匯出於 %s ・ %s ・ 記錄類型：%s ・ 資料來源：%s\n%s。" % (
        lib.now_iso().replace("T", " "), span,
        "、".join(streams) if streams else "全部", source_note, PII_WARNING)


# ── .docx（最小 OOXML，標準庫 zipfile）──────────────────────────────────
def _p(text="", style=None, bold=False):
    """一個段落。文字裡的換行用 <w:br/> 保留（老師的分行是有意義的）。"""
    ppr = ('<w:pPr><w:pStyle w:val="%s"/></w:pPr>' % xe(style)) if style else ""
    segs = str("" if text is None else text).split("\n")
    runs = []
    for i, seg in enumerate(segs):
        rpr = "<w:rPr><w:b/></w:rPr>" if bold else ""
        br = "<w:br/>" if i else ""
        runs.append('<w:r>%s%s<w:t xml:space="preserve">%s</w:t></w:r>' % (rpr, br, xe(seg)))
    return "<w:p>%s%s</w:p>" % (ppr, "".join(runs))


def _table(rows):
    """兩欄欄位表（左欄鍵、右欄值）。表格後面一定要再接一個段落，否則 Word 會抱怨。"""
    out = ['<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/>'
           '<w:tblW w:w="0" w:type="auto"/></w:tblPr>'
           '<w:tblGrid><w:gridCol w:w="2400"/><w:gridCol w:w="6600"/></w:tblGrid>']
    for k, v in rows:
        cells = []
        for width, txt, bold in ((2400, k, True), (6600, v, False)):
            cells.append('<w:tc><w:tcPr><w:tcW w:w="%d" w:type="dxa"/></w:tcPr>%s</w:tc>'
                         % (width, _p(txt, bold=bold)))
        out.append("<w:tr>%s</w:tr>" % "".join(cells))
    out.append("</w:tbl>")
    out.append("<w:p/>")
    return "".join(out)


def _heading_style(sid, name, size, before):
    return ('<w:style w:type="paragraph" w:styleId="%s"><w:name w:val="%s"/>'
            '<w:basedOn w:val="Normal"/><w:qFormat/>'
            '<w:pPr><w:keepNext/><w:outlineLvl w:val="%d"/>'
            '<w:spacing w:before="%d" w:after="120"/></w:pPr>'
            '<w:rPr><w:b/><w:sz w:val="%d"/><w:szCs w:val="%d"/></w:rPr></w:style>'
            % (sid, name, int(sid[-1]) - 1, before, size, size))


def styles_xml():
    """字型與標題樣式。中文字型走 Noto Sans TC，機器上沒有的話由 fontTable 的
    altName 退到微軟正黑體（Windows）／PingFang TC（macOS）。"""
    borders = "".join('<w:%s w:val="single" w:sz="4" w:space="0" w:color="BFBFBF"/>' % s
                      for s in ("top", "left", "bottom", "right", "insideH", "insideV"))
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<w:styles xmlns:w="%s">'
            '<w:docDefaults><w:rPrDefault><w:rPr>'
            '<w:rFonts w:ascii="Noto Sans TC" w:hAnsi="Noto Sans TC" '
            'w:eastAsia="Noto Sans TC" w:cs="Noto Sans TC"/>'
            '<w:sz w:val="22"/><w:szCs w:val="22"/>'
            '<w:lang w:val="zh-TW" w:eastAsia="zh-TW"/>'
            '</w:rPr></w:rPrDefault><w:pPrDefault><w:pPr>'
            '<w:spacing w:after="120" w:line="300" w:lineRule="auto"/>'
            '</w:pPr></w:pPrDefault></w:docDefaults>'
            '<w:style w:type="paragraph" w:default="1" w:styleId="Normal">'
            '<w:name w:val="Normal"/><w:qFormat/></w:style>'
            '%s%s%s'
            '<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/>'
            '<w:tblPr><w:tblBorders>%s</w:tblBorders>'
            '<w:tblCellMar><w:top w:w="60" w:type="dxa"/><w:left w:w="100" w:type="dxa"/>'
            '<w:bottom w:w="60" w:type="dxa"/><w:right w:w="100" w:type="dxa"/></w:tblCellMar>'
            '</w:tblPr></w:style>'
            '</w:styles>'
            % (W_NS,
               _heading_style("Heading1", "heading 1", 36, 0),
               _heading_style("Heading2", "heading 2", 28, 320),
               _heading_style("Heading3", "heading 3", 24, 240),
               borders))


FONT_TABLE = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
              '<w:fonts xmlns:w="%s">'
              '<w:font w:name="Noto Sans TC"><w:altName w:val="微軟正黑體"/>'
              '<w:family w:val="swiss"/><w:pitch w:val="variable"/></w:font>'
              '<w:font w:name="微軟正黑體"><w:altName w:val="PingFang TC"/>'
              '<w:family w:val="swiss"/><w:pitch w:val="variable"/></w:font>'
              '</w:fonts>' % W_NS)

CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" '
    'ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-'
    'officedocument.wordprocessingml.document.main+xml"/>'
    '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-'
    'officedocument.wordprocessingml.styles+xml"/>'
    '<Override PartName="/word/fontTable.xml" ContentType="application/vnd.openxmlformats-'
    'officedocument.wordprocessingml.fontTable+xml"/>'
    '</Types>')

ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
    'relationships/officeDocument" Target="word/document.xml"/></Relationships>')

DOC_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
    'relationships/styles" Target="styles.xml"/>'
    '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
    'relationships/fontTable" Target="fontTable.xml"/></Relationships>')

# A4 直式（單位 twip）：21cm × 29.7cm，四邊留 2cm 上下、1.8cm 左右。
SECT_PR = ('<w:sectPr><w:pgSz w:w="11906" w:h="16838"/>'
           '<w:pgMar w:top="1134" w:right="1021" w:bottom="1134" w:left="1021" '
           'w:header="709" w:footer="709" w:gutter="0"/></w:sectPr>')


def document_xml(title, sub, sections):
    body = [_p(title, "Heading1"), _p(sub)]
    for sec in sections:
        body.append(_p(sec["title"], "Heading2"))
        paras = overview_paras(sec.get("card"))
        if paras:
            body.append(_p(OVERVIEW_HEADING, "Heading3"))
            for para in paras:
                body.append(_p(para))
        for sub, rows in card_blocks(sec.get("card")):
            body.append(_p(sub, "Heading3"))
            body.append(_table(rows))
        if not sec["records"]:
            body.append(_p(NO_RECORD))
            continue
        for r in sec["records"]:
            body.append(_p(rec_heading(r), "Heading3"))
            fields = [(k, v) for k, v in (r.get("fields") or {}).items()]
            if fields:
                body.append(_table(fields))
            if r.get("related"):
                body.append(_p("關聯：" + "; ".join(r["related"])))
            for para in re.split(r"\n\s*\n", (r.get("body") or "").strip()):
                if para.strip():
                    body.append(_p(para.strip("\n")))
    body.append(SECT_PR)
    return ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n'
            '<w:document xmlns:w="%s"><w:body>%s</w:body></w:document>'
            % (W_NS, "".join(body)))


def write_docx(path, title, sub, sections):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", CONTENT_TYPES)
        z.writestr("_rels/.rels", ROOT_RELS)
        z.writestr("word/_rels/document.xml.rels", DOC_RELS)
        z.writestr("word/document.xml", document_xml(title, sub, sections))
        z.writestr("word/styles.xml", styles_xml())
        z.writestr("word/fontTable.xml", FONT_TABLE)
    return path


# ── HTML（PDF 的來源，也可以自己留著列印）────────────────────────────────
CSS = """
@page { size: A4; margin: 18mm 16mm; }
* { box-sizing: border-box; }
body { font-family: "Noto Sans TC", "微軟正黑體", "PingFang TC", "Heiti TC", sans-serif;
       color: #1b1b1b; line-height: 1.7; max-width: 800px; margin: 0 auto; padding: 24px; }
h1 { font-size: 24px; margin: 0 0 4px; }
h2 { font-size: 19px; margin: 28px 0 8px; padding-bottom: 4px; border-bottom: 2px solid #ddd; }
h3 { font-size: 15px; margin: 16px 0 6px; color: #333; }
.sub { color: #666; font-size: 12px; white-space: pre-line; margin-bottom: 8px; }
.record { page-break-inside: avoid; break-inside: avoid; margin-bottom: 14px; }
.none { color: #888; }
.related { color: #555; font-size: 13px; }
p.body { margin: 6px 0; white-space: pre-wrap; }
table { border-collapse: collapse; width: 100%; margin: 6px 0; font-size: 13px; }
th, td { border: 1px solid #bfbfbf; padding: 4px 8px; text-align: left; vertical-align: top; }
th { width: 26%; background: #f6f6f6; font-weight: 600; }
@media print {
  body { padding: 0; max-width: none; }
  h2 { page-break-after: avoid; }
  .no-print { display: none; }
}
"""


def render_html(title, sub, sections):
    L = ["<!DOCTYPE html>", '<html lang="zh-Hant"><head><meta charset="utf-8">',
         "<title>%s</title>" % xe(title), "<style>%s</style></head><body>" % CSS,
         "<h1>%s</h1>" % xe(title), '<div class="sub">%s</div>' % xe(sub)]
    for sec in sections:
        L.append("<h2>%s</h2>" % xe(sec["title"]))
        paras = overview_paras(sec.get("card"))
        if paras:
            L.append("<h3>%s</h3>" % xe(OVERVIEW_HEADING))
            for para in paras:
                L.append('<p class="body">%s</p>' % xe(para))
        for sub, rows in card_blocks(sec.get("card")):
            L.append("<h3>%s</h3>" % xe(sub))
            L.append("<table>")
            for k, v in rows:
                L.append("<tr><th>%s</th><td>%s</td></tr>" % (xe(k), xe(v)))
            L.append("</table>")
        if not sec["records"]:
            L.append('<p class="none">%s</p>' % NO_RECORD)
            continue
        for r in sec["records"]:
            L.append('<div class="record">')
            L.append("<h3>%s</h3>" % xe(rec_heading(r)))
            fields = [(k, v) for k, v in (r.get("fields") or {}).items()]
            if fields:
                L.append("<table>")
                for k, v in fields:
                    L.append("<tr><th>%s</th><td>%s</td></tr>" % (xe(k), xe(v)))
                L.append("</table>")
            if r.get("related"):
                L.append('<p class="related">關聯：%s</p>' % xe("; ".join(r["related"])))
            for para in re.split(r"\n\s*\n", (r.get("body") or "").strip()):
                if para.strip():
                    L.append('<p class="body">%s</p>' % xe(para.strip("\n")))
            L.append("</div>")
    L.append("</body></html>")
    return "\n".join(L) + "\n"


# ── PDF（借 Chrome 印）───────────────────────────────────────────────────
def find_chrome():
    """找一個能用的 Chrome／Chromium／Edge（各平台的候選路徑在 hostos.chrome_candidates()）。
    環境變數 TRK_CHROME 可以指定路徑（也給測試用：指到不存在的路徑就等於「這台機器沒有 Chrome」）。"""
    envp = os.environ.get("TRK_CHROME")
    if envp is not None:
        return envp if (envp and os.path.isfile(envp) and os.access(envp, os.X_OK)) else None
    cands = hostos.chrome_candidates()
    return cands[0] if cands else None


def file_url(path):
    """本機路徑 → file:// URL（中文檔名、空白都會正確編碼）。

    Python 3.14 起 pathname2url 會回傳帶空 authority 的 `///path`，直接接在 "file://"
    後面會變成 `file://///path`；用 urljoin 兩種版本都會得到正確的 `file:///path`。
    """
    return urllib.parse.urljoin("file:", urllib.request.pathname2url(os.path.abspath(path)))


def _wait_for_pdf(proc, pdf_path, timeout=180):
    """等 Chrome 把 PDF 寫完。

    `--headless=new --print-to-pdf` 有時候印完不肯自己退場（檔案早就寫好了，行程還掛著），
    所以這裡盯的是檔案而不是行程：大小連續幾次沒變就當印完，然後把 Chrome 收掉。
    """
    last, stable, t0 = -1, 0, time.time()
    while time.time() - t0 < timeout:
        if proc.poll() is not None:
            break
        size = os.path.getsize(pdf_path) if os.path.exists(pdf_path) else -1
        stable = (stable + 1) if (size > 0 and size == last) else 0
        last = size
        if stable >= 3:
            break
        time.sleep(0.4)
    if proc.poll() is None:
        # 一定要連子孫一起殺：Chrome／Edge 的 renderer 是獨立行程，只殺父行程的話它們還抓著
        # --user-data-dir 那個暫存 profile，Windows 上 rmtree 會靜靜地失敗、留下一地 trk-chrome-*。
        hostos.kill_tree(proc)


def html_to_pdf(html_path, pdf_path):
    """Chrome headless 印 PDF。回傳 True／False（False＝沒有 Chrome 或它印不出來）。"""
    chrome = find_chrome()
    if not chrome:
        return False
    import tempfile
    profile = tempfile.mkdtemp(prefix="trk-chrome-")
    cmd = [chrome, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
           "--user-data-dir=" + profile, "--no-pdf-header-footer",
           "--print-to-pdf=" + os.path.abspath(pdf_path), file_url(html_path)]
    kw = {}
    if os.name == "posix":
        kw["start_new_session"] = True             # 自成一個 process group，kill_tree 才殺得掉整群
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
    except Exception:
        return False
    try:
        _wait_for_pdf(proc, os.path.abspath(pdf_path))
    finally:
        hostos.kill_tree(proc)                     # 保險：子孫沒死光的話下面那行刪不掉 profile
        shutil.rmtree(profile, ignore_errors=True)
    if not os.path.exists(pdf_path) or os.path.getsize(pdf_path) < 5:
        return False
    with open(pdf_path, "rb") as f:
        return f.read(4) == b"%PDF"                    # 沒印成功時它可能留下一個空殼


# ── 主流程 ──────────────────────────────────────────────────────────────
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def check_date(val, what):
    if val and not DATE_RE.match(val):
        lib.die("%s 的日期格式不對：%s" % (what, val), "格式是 YYYY-MM-DD，例如 2026-09-01。")
    return val or ""


def main():
    ap = argparse.ArgumentParser(
        description="一鍵匯出 Word（.docx）與 PDF：學生、班級、課程、業務組都可以",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="匯出檔含名冊真名，只留在你自己的機器上，別放到任何公開的地方。")
    ap.add_argument("--kind", required=True, choices=list(lib.KINDS),
                    help="要匯出哪一種記錄：students（學生）、class（班級整體觀察）、"
                         "courses（課程）、business（業務組）")
    ap.add_argument("--target", default="all",
                    help="對象代號或 id；all ＝全部（學生的 all ＝所有學生，一份文件每人一節）")
    ap.add_argument("--stream", action="append", default=[], metavar="類型",
                    help="只匯出某一種學生記錄類型（可重複；不給＝那位學生的全部類型）")
    ap.add_argument("--from", dest="dfrom", default="", metavar="YYYY-MM-DD", help="只要這天以後的記錄")
    ap.add_argument("--to", dest="dto", default="", metavar="YYYY-MM-DD", help="只要這天以前的記錄")
    ap.add_argument("--with-class", action="store_true",
                    help="匯出所有學生時，把班級整體觀察放在最前面一節")
    ap.add_argument("--docx", action="store_true", help="產生 Word 檔（預設就會產生）")
    ap.add_argument("--no-docx", action="store_true", help="不要 Word 檔（只要 PDF／HTML 時用）")
    ap.add_argument("--pdf", action="store_true", help="順便印一份 PDF（要機器上有 Chrome）")
    ap.add_argument("--html", action="store_true", help="連 HTML 一起留下來（自己用瀏覽器列印）")
    ap.add_argument("--out", metavar="目錄", help="輸出目錄（預設 exports/，已經在 .gitignore 裡）")
    ap.add_argument("--local", action="store_true", help="只讀本機 markdown，絕不連網")
    lib.add_root_arg(ap)
    a = ap.parse_args()
    lib.apply_root(a)

    dfrom = check_date(a.dfrom, "--from")
    dto = check_date(a.dto, "--to")
    if dfrom and dto and dfrom > dto:
        lib.die("--from（%s）比 --to（%s）還晚。" % (dfrom, dto), "把兩個日期對調就好。")

    kit = lib.load_kit()
    tabs = lib.load_tabs()
    if a.stream:
        known = {s["id"] for s in lib.student_streams(tabs)}
        bad = [s for s in a.stream if s not in known]
        if bad:
            lib.die("沒有這種學生記錄類型：%s" % "、".join(bad),
                    "可用的類型：%s（看 config/tabs.json 的 students.streams）。"
                    % ("、".join(sorted(known)) if known else "（一種都沒有）"))

    local, source_note = pick_source(kit, tabs, a.local)
    lib.ok("資料來源：%s" % source_note)
    # 連網模式：網頁上刪掉的那些（軟刪 deleted: true）在 collect() 就排掉了，不會進 Word／PDF。
    data = export_records.collect(kit, tabs, local)
    sections, title = gather(data, a.kind, a.target, a.stream, dfrom, dto, a.with_class)
    sub = subtitle(source_note, dfrom, dto, a.stream)

    outdir = os.path.expanduser(a.out) if a.out else lib.rpath("exports")
    os.makedirs(outdir, exist_ok=True)
    stem = "-".join([safe_name(a.kind), safe_name(a.target)]
                    + ([safe_name("-".join(a.stream))] if a.stream else [])
                    + [datetime.date.today().strftime("%Y%m%d")])
    made, hints = [], []

    if not a.no_docx:
        made.append(write_docx(os.path.join(outdir, stem + ".docx"), title, sub, sections))

    html_path = os.path.join(outdir, stem + ".html")
    if a.pdf or a.html:
        with open(html_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(render_html(title, sub, sections))
    if a.pdf:
        pdf_path = os.path.join(outdir, stem + ".pdf")
        if html_to_pdf(html_path, pdf_path):
            made.append(pdf_path)
            if a.html:
                made.append(html_path)
            else:
                os.remove(html_path)
        else:
            made.append(html_path)
            hints.append("找不到 Chrome（或它印不出來），所以沒有 PDF。"
                         "用瀏覽器開這個檔 → 列印 → 儲存為 PDF：%s" % html_path)
    elif a.html:
        made.append(html_path)

    total = sum(len(s["records"]) for s in sections)
    lib.ok("匯出完成：%d 節、%d 則記錄" % (len(sections), total))
    for p in made:
        print("  · " + p)
    for h in hints:
        lib.warn(h)
    print("%s%s（檔案裡是名冊姓名，這是給你自己看的）。%s" % (lib.YELLOW, PII_WARNING, lib.RESET))


if __name__ == "__main__":
    main()
