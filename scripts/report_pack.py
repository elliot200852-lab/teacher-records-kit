#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""report_pack.py — 期末一鍵產出「素材包」與「草稿指令」。

期末最痛的不是寫評語，是**回頭把一整年的碎片撿起來、分好組**。這支就只做這件事：
把你整年寫的紀錄依報告格式分組、附上每一則的日期與證據、算出你哪一塊還沒有紀錄，
輸出兩個檔：

  exports/<代號>-<格式>-素材包.md    分好組的原始素材（事實，一個字都不是它編的）
  exports/<代號>-<格式>-prompt.md    校方格式骨架＋書寫規則＋稽核清單＋一段固定指令

**這支不呼叫任何 AI、不生成任何評語**。評語本文由你自己的 AI 代理照 prompt.md 寫、
由你定稿——所以它產出的東西每次都一樣，也不會替你編造任何沒發生過的觀察。

用法：
  python3 scripts/report_pack.py --format waldorf-homeroom --target S-03
  python3 scripts/report_pack.py --format iep-tracking --target S-02
  python3 scripts/report_pack.py --format case-summary --target S-02 --from 2026-09-01
  python3 scripts/report_pack.py --format subject-4 --all          全班一包（另出 _index.md）
  python3 scripts/report_pack.py --format custom --target S-03     用你們學校自己的格式

格式（config/report-formats.library.json）：
  waldorf-homeroom  導師質性評量（發展樣貌／客觀描述五維度／整體感受／導師建議）
  subject-4         科任評語四項（關係／參與／可見的學習證據／下一步，320–450 字）
  iep-tracking      IEP／早療目標追蹤（每目標一表＋期末總評）
  case-summary      個案摘要／結案報告（個案概念化＋歷程＋進展＋建議）
  custom            你們學校自己的格式（把標題貼進 config/report-format.custom.json）
"""
import os
import sys
import argparse
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib
import export_records
import export_docs

MULTI_SEP = "／"
UNTAGGED = "（未標）"
NO_REC = "（這一塊還沒有紀錄）"
# S/O/A/P 四段在紀錄裡的欄位名（會談紀錄）。
SOAP_FIELDS = ["S 主觀", "O 客觀", "A 評估", "P 計畫"]
IEP_COLS = ["達成情形", "證據", "支持策略", "下一步"]
GOAL_FIELD = "目標編號"


# ── 小工具 ──────────────────────────────────────────────────────────────
def split_multi(val):
    """複選欄位的值 → 清單（`頭·思考／心·情感` → ['頭·思考','心·情感']）。"""
    return [x.strip() for x in str(val or "").split(MULTI_SEP) if x.strip()]


def cell(text):
    """表格儲存格：換行換成空白，直線跳脫，免得把 markdown 表格打斷。"""
    return str(text or "").replace("\n", " ").replace("|", "\\|").strip() or "—"


def indent_body(body, prefix="  "):
    out = []
    for line in (body or "").strip().split("\n"):
        out.append((prefix + line) if line.strip() else "")
    return out


def tidy(lines):
    """收尾：連續空行併成一行（分組是遞迴長出來的，接縫處難免多空一行）。"""
    out = []
    for line in lines:
        if not line.strip() and out and not out[-1].strip():
            continue
        out.append(line.rstrip())
    return "\n".join(out).strip("\n") + "\n"


def rec_date(r):
    return r.get("date") or (r.get("rid") or "")[:10]


def span_of(recs):
    ds = sorted(rec_date(r) for r in recs if rec_date(r))
    return ("%s ～ %s" % (ds[0], ds[-1])) if ds else "（還沒有日期）"


# ── 素材包：一則怎麼寫 ──────────────────────────────────────────────────
def render_record(r, skip_fields=()):
    """一則記錄 → markdown 行。日期永遠在最前面，證據欄位跟在後面，正文縮排在下。"""
    extra = ["%s：%s" % (k, v) for k, v in (r.get("fields") or {}).items()
             if k not in skip_fields and str(v).strip()]
    head = "- **%s**" % rec_date(r)
    if r.get("tags"):
        head += "　" + " ".join(r["tags"])
    if extra:
        head += "　（%s）" % "｜".join(extra)
    return [head] + indent_body(r.get("body"), "  ")


# ── 分組（質性評量、科任四項、custom 共用）──────────────────────────────
# 有些介面會在維度前面加編號（「①行為與自我管理」）。分組時把編號剝掉再比對，
# 免得同一個維度因為多了一個圈圈就被拆成兩堆——老師看到的是同一件事。
_LEAD = "①②③④⑤⑥⑦⑧⑨⑩0123456789.、,．：: 　"


def canon(val, fixed=()):
    """把一個分組值對回格式定義的維度名（剝掉開頭的編號再比）。對不上就原樣留著。"""
    v = str(val or "").strip()
    bare = v.lstrip(_LEAD)
    for d in (fixed or []):
        if bare == str(d).lstrip(_LEAD):
            return d
    return v


def bucket(recs, key, fixed=()):
    """依某個欄位把紀錄分堆；複選欄位一則會同時出現在好幾堆（那正是它的意思）。"""
    out = {}
    for r in recs:
        vals = split_multi((r.get("fields") or {}).get(key, "")) or [UNTAGGED]
        for v in vals:
            out.setdefault(canon(v, fixed), []).append(r)
    return out


def order_keys(buckets, fixed):
    """固定維度先照格式定的順序列（沒有紀錄的也列出來），其餘照筆畫外的自然序，未標最後。"""
    seen = list(fixed)
    rest = sorted(k for k in buckets if k not in seen and k != UNTAGGED)
    tail = [UNTAGGED] if UNTAGGED in buckets else []
    return seen + rest + tail


def render_grouped(recs, keys, fixed, level=2, skip=()):
    """依 groupBy 一層一層分組。第一層用格式定的固定維度（缺的照樣列出來標成缺漏）。"""
    if not keys:
        L = []
        for r in sorted(recs, key=lambda x: (rec_date(x), x.get("rid") or "")):
            L += render_record(r, skip)
        return L or ["_%s_" % NO_REC]
    key = keys[0]
    buckets = bucket(recs, key, fixed if level == 2 else ())
    L = []
    for k in order_keys(buckets, fixed if level == 2 else []):
        got = buckets.get(k) or []
        L.append("%s %s%s" % ("#" * level, k, "　（%d 則）" % len(got) if got else ""))
        if not got:
            L.append("> ⚠ %s——期末寫到這一段時只能照實留白，或現在回頭補紀錄。" % NO_REC)
            L.append("")
            continue
        L += render_grouped(got, keys[1:], [], level + 1, tuple(skip) + (key,))
        L.append("")
    return L


def stats_grouped(recs, fmt):
    keys = fmt.get("groupBy") or []
    fixed = fmt.get("dimensions") or []
    L = ["## 統計（給你自己看的，不必寫進報告）", "",
         "- 則數：%d（%s）" % (len(recs), span_of(recs))]
    if fixed and keys:
        got = {k for k in bucket(recs, keys[0], fixed) if k != UNTAGGED}
        miss = [d for d in fixed if d not in got]
        L.append("- 涵蓋%s：%d／%d" % (keys[0], len(fixed) - len(miss), len(fixed)))
        L.append("- 還沒有紀錄的%s：%s" % (keys[0], "、".join(miss) if miss else "（都有了）"))
        untagged = len(bucket(recs, keys[0], fixed).get(UNTAGGED) or [])
        if untagged:
            L.append("- 沒標%s的紀錄：%d 則（在上面的「%s」那一段）" % (keys[0], untagged, UNTAGGED))
    for k in keys[1:]:
        b = {x: len(v) for x, v in bucket(recs, k).items() if x != UNTAGGED}
        if b:
            L.append("- %s分佈：%s" % (k, "、".join("%s %d" % (x, n) for x, n in sorted(b.items()))))
    src = {x: len(v) for x, v in bucket(recs, "證據來源").items() if x != UNTAGGED}
    if src:
        L.append("- 證據來源：%s" % "、".join("%s %d" % (x, n) for x, n in sorted(src.items())))
    L.append("")
    return L


# ── IEP：每目標一表 ──────────────────────────────────────────────────────
def render_iep(recs, card):
    goals = card.get("goals") or []
    by_goal = {}
    for r in recs:
        gid = str((r.get("fields") or {}).get(GOAL_FIELD, "")).strip()
        by_goal.setdefault(gid, []).append(r)
    L, zero = [], []
    if not goals:
        L.append("> ⚠ 這位學生的卡片上一條目標都還沒有——IEP 報告是照目標一條一條寫的，"
                 "先把學年／學期目標填進 data/students/<代號>/card.json 的 goals"
                 "（範本 templates/card.example.json，網頁上也能建），再跑一次。")
        L.append("")
    for g in goals:
        got = sorted(by_goal.get(g["id"]) or [], key=lambda x: (rec_date(x), x.get("rid") or ""))
        L.append("## 目標 %s｜%s" % (g["id"], g.get("領域") or "（沒寫領域）"))
        L.append("")
        L.append("| 項目 | 內容 |")
        L.append("|---|---|")
        for k in ("學年目標", "學期目標", "評量方式", "評量標準", "期程"):
            L.append("| %s | %s |" % (k, cell(g.get(k))))
        L.append("")
        if not got:
            zero.append(g["id"])
            L.append("> ⚠ 本期還沒有任何紀錄掛在這一條目標下。"
                     "期末報告這一格要照實寫「本期未蒐集到紀錄」，不要推估。")
            L.append("")
            continue
        L.append("### 日期序達成情形（%d 則，%s）" % (len(got), span_of(got)))
        L.append("")
        L.append("| 日期 | %s |" % " | ".join(IEP_COLS))
        L.append("|---|%s" % ("---|" * len(IEP_COLS)))
        for r in got:
            f = r.get("fields") or {}
            L.append("| %s | %s |" % (rec_date(r), " | ".join(cell(f.get(c)) for c in IEP_COLS)))
        L.append("")
        L.append("#### 這幾則的原文（寫報告時的證據）")
        for r in got:
            L += render_record(r, (GOAL_FIELD,) + tuple(IEP_COLS))
        L.append("")
    orphan = [r for gid, rs in by_goal.items() if not any(g["id"] == gid for g in goals) for r in rs]
    if orphan:
        L.append("## 沒有掛在任何目標下的紀錄（%d 則）" % len(orphan))
        L.append("")
        L.append("> 這幾則的「%s」是空的或指到一條卡片上沒有的目標。"
                 "要算進哪一條目標，就改 data/students/<代號>/card.json 或重寫那一則。" % GOAL_FIELD)
        for r in sorted(orphan, key=lambda x: (rec_date(x), x.get("rid") or "")):
            L += render_record(r)
        L.append("")
    return L, zero, orphan


def stats_iep(recs, card, zero, orphan):
    goals = card.get("goals") or []
    L = ["## 統計（給你自己看的，不必寫進報告）", "",
         "- 目標 %d 條、紀錄 %d 則（%s）" % (len(goals), len(recs), span_of(recs)),
         "- 零紀錄的目標：%s" % ("、".join(zero) if zero
                                 else ("（這位學生的卡片上一條目標都還沒有）" if not goals
                                       else "（沒有，每一條都有紀錄）")),
         "- 沒有掛到目標的紀錄：%d 則" % len(orphan)]
    lvl = {}
    for r in recs:
        v = str((r.get("fields") or {}).get("達成情形", "")).strip()
        if v:
            lvl[v] = lvl.get(v, 0) + 1
    if lvl:
        L.append("- 達成情形分佈：%s" % "、".join("%s %d" % (k, n) for k, n in sorted(lvl.items())))
    L.append("")
    return L


# ── SOAP：依會談次數 ────────────────────────────────────────────────────
def session_no(r):
    """會談次數（沒填就回 None，排序時排在有號碼的後面、照日期）。"""
    v = str((r.get("fields") or {}).get("會談次數", "")).strip()
    digits = "".join(c for c in v if c.isdigit())
    return int(digits) if digits else None


def render_case(recs, card):
    L = []
    con = card.get("conceptualization") or {}
    L.append("## 個案概念化（卡片上的底稿）")
    L.append("")
    if con:
        L.append("| 項目 | 內容 |")
        L.append("|---|---|")
        for k in lib.CONCEPT_KEYS:
            L.append("| %s | %s |" % (k, cell(con.get(k))))
    else:
        L.append("> ⚠ 這位個案的卡片還沒有個案概念化（主訴／背景／評估假設／處遇目標／結案標準）。"
                 "填在 data/students/<代號>/card.json 的 conceptualization，"
                 "結案報告要逐條對照「結案標準」。")
    L.append("")
    ordered = sorted(recs, key=lambda r: (session_no(r) is None, session_no(r) or 0,
                                          rec_date(r), r.get("rid") or ""))
    L.append("## 歷程摘要（依會談次數）")
    L.append("")
    if not ordered:
        L.append("_%s_" % NO_REC)
        L.append("")
    missing = []
    for i, r in enumerate(ordered, 1):
        f = r.get("fields") or {}
        no = session_no(r)
        L.append("### 第 %s 次會談　%s%s"
                 % (no if no else "?（%d）" % i, rec_date(r),
                    "　%s" % f.get("會談形式") if f.get("會談形式") else ""))
        L.append("")
        gaps = []
        for k in SOAP_FIELDS:
            v = str(f.get(k, "")).strip()
            if not v:
                gaps.append(k)
            L.append("- **%s**：%s" % (k, v or "（未留下紀錄）"))
        # 一次會談只記一筆（缺哪幾段寫在括號裡）——原本是缺一段就 append 一次，
        # 同一次會談會在統計裡重複出現好幾遍。
        if gaps:
            missing.append("%s 第 %s 次（缺 %s）" % (rec_date(r), no if no else i, "／".join(gaps)))
        for k in ("風險評估", "下次時間"):
            if str(f.get(k, "")).strip():
                L.append("- %s：%s" % (k, f[k]))
        body = (r.get("body") or "").strip()
        if body:
            L.append("- 原文：")
            L += indent_body(body, "  ")
        L.append("")
    return L, ordered, missing


def stats_case(ordered, missing):
    L = ["## 統計（給你自己看的，不必寫進報告）", "",
         "- 會談 %d 次（%s）" % (len(ordered), span_of(ordered))]
    nos = [session_no(r) for r in ordered if session_no(r)]
    if nos:
        gaps = [n for n in range(1, max(nos) + 1) if n not in nos]
        L.append("- 次數：%s" % "、".join(str(n) for n in nos))
        L.append("- 缺號：%s" % ("、".join(str(n) for n in gaps) if gaps else "（連續，沒有缺號）"))
    trend = []
    for i, r in enumerate(ordered, 1):
        v = str((r.get("fields") or {}).get("風險評估", "")).strip()
        if v:
            trend.append("第%s次 %s" % (session_no(r) or i, v))
    L.append("- 風險趨勢：%s" % (" → ".join(trend) if trend else "（沒有任何一次填了風險評估）"))
    if trend:
        high = [t for t in trend if t.endswith("高")]
        if high:
            L.append("- ⚠ 風險最高的那幾次：%s——報告的「風險與安全」那一段要交代處理。"
                     % "、".join(high))
    L.append("- S／O／A／P 有缺的：%s" % ("；".join(missing) if missing else "（每一次都齊）"))
    L.append("")
    return L


# ── 兩個檔怎麼組 ────────────────────────────────────────────────────────
def build_pack(fmt, title, sid, recs, card, streams, dfrom, dto):
    head = ["# %s　%s　素材包" % (title, fmt.get("label") or fmt["id"]),
            "",
            "> 產生於 %s ・ 格式 `%s` ・ 記錄類型 %s ・ 期間 %s"
            % (lib.now_iso().replace("T", " "), fmt["id"],
               "、".join(streams) or "全部",
               "%s 至 %s" % (dfrom or "最早", dto or "最新")),
            "> 這份是**素材**：底下每一行都是你自己寫過的紀錄，腳本只做了分組，沒有改寫、"
            "沒有生成任何一個字。",
            "> 評語本文照同一批檔案裡的 `-prompt.md` 寫；含名冊姓名，別放到公開的地方。",
            ""]
    if fmt["id"] == "iep-tracking":
        body, zero, orphan = render_iep(recs, card)
        stats = stats_iep(recs, card, zero, orphan)
    elif fmt["id"] == "case-summary":
        body, ordered, missing = render_case(recs, card)
        stats = stats_case(ordered, missing)
    else:
        body = render_grouped(recs, fmt.get("groupBy") or [], fmt.get("dimensions") or [])
        stats = stats_grouped(recs, fmt)
    return tidy(head + body + stats)


def build_prompt(fmt, title, sid, pack_name, recs):
    label = fmt.get("label") or fmt["id"]
    L = ["# %s　%s　草稿指令" % (title, label), "",
         "> 給你的 AI 代理讀。做法：把 `%s` 整份貼給它，再把最下面那段「固定指令」貼上去。"
         % pack_name,
         "> 腳本不寫評語——**這一份是規則，不是內容**；本文由 AI 依素材寫、由你定稿。", "",
         "## 這一份要寫成什麼", "",
         "- 對象：%s" % title,
         "- 格式：%s（`%s`）" % (label, fmt["id"]),
         "- 手上的素材：%d 則紀錄（%s）" % (len(recs), span_of(recs))]
    if fmt.get("totalLength"):
        L.append("- 全篇字數：%s" % fmt["totalLength"])
    L += ["", "## 報告骨架（照這個順序、逐段寫）", ""]
    for i, s in enumerate(fmt.get("sections") or [], 1):
        L.append("### %d. %s%s" % (i, s.get("title", ""),
                                   "（%s）" % s["length"] if s.get("length") else ""))
        if s.get("hint"):
            L.append("> %s" % s["hint"])
        L.append("")
    L += ["## 書寫規則（每一條都要遵守）", ""]
    L += ["- %s" % r for r in (fmt.get("rules") or [])]
    L += ["", "## 定稿前的稽核清單（寫完逐條打勾）", ""]
    L += ["- [ ] %s" % r for r in (fmt.get("audit") or [])]
    L += ["", "## 固定指令（把這一段連同素材包一起貼給 AI）", "", "```",
          "請依上面的「報告骨架」逐段寫出 %s 的%s草稿。" % (title, label),
          "材料只有我貼給你的素材包：每一句都要指得出是素材包裡哪一則（哪一天）；",
          "素材包裡沒有的事一個字都不要補。某一段沒有素材就寫「本期未蒐集到紀錄」，不要推估。",
          "「書寫規則」每一條都要遵守，寫完自己照「稽核清單」逐條檢查一次，",
          "把沒過的那幾條列出來給我看，不要偷偷改掉。",
          "輸出格式：每一段一個標題，標題逐字照骨架，段落之間空一行。",
          "```", ""]
    return tidy(L)


# ── 主流程 ──────────────────────────────────────────────────────────────
def pick_streams(fmt, tabs, want):
    """這一次要撈哪幾種記錄類型：--stream 指定的優先，否則用格式吃的那幾種。"""
    configured = lib.student_streams(tabs)
    known = {}
    for s in configured:
        for i in lib.stream_ids(s):
            known[i] = s["id"]
    if want:
        bad = [w for w in want if w not in known]
        if bad:
            lib.die("設定裡沒有這種學生記錄類型：%s" % "、".join(bad),
                    "可用的類型：%s（看 config/tabs.json 的 students.streams）。"
                    % ("、".join(sorted({s['id'] for s in configured})) or "（一種都沒有）"))
        return sorted({known[w] for w in want})
    hit = sorted({known[i] for i in known if i in (fmt.get("for") or [])})
    if hit:
        return hit
    if fmt["id"] == "custom":
        return sorted({s["id"] for s in configured})
    lib.die("「%s」這個格式吃的記錄類型（%s）你一種都沒勾。"
            % (fmt.get("label") or fmt["id"], "、".join(fmt.get("for") or []) or "（沒設定）"),
            "重跑 `python3 scripts/setup.py` 勾起來，或用 `--stream <你實際在用的類型>` "
            "指定要拿哪一種紀錄來排。")


def load_format(fid):
    lib_fmts = lib.load_report_formats()
    fmt = lib.find_format(fid, lib_fmts)
    if not fmt:
        lib.die("沒有這個報告格式：%s" % fid,
                "可用的格式：%s。"
                % "、".join("%s（%s）" % (f["id"], f["label"]) for f in lib_fmts.get("formats") or []))
    if fid != "custom":
        return fmt
    custom = lib.load_custom_format()
    if not custom:
        lib.die("--format custom 要先有 config/report-format.custom.json（你們學校的格式）。",
                "複製範本改成你們學校的標題：\n"
                "     cp templates/report-format.custom.example.json config/report-format.custom.json\n"
                "  裡面填 sections（每段的 title／length／hint）與 groupBy（素材要依哪個欄位分組）。")
    merged = dict(fmt)
    for k in ("label", "sections", "groupBy", "dimensions", "for", "totalLength"):
        if custom.get(k):
            merged[k] = custom[k]
    for k in ("rules", "audit"):
        extra = [x for x in (custom.get(k) or []) if str(x).strip()
                 and not str(x).startswith("（可自行增修")]
        if extra:
            merged[k] = list(merged.get(k) or []) + extra
    if not merged.get("sections"):
        lib.die("config/report-format.custom.json 裡的 sections 是空的。",
                "至少要有一段：[{\"title\":\"學習表現\",\"length\":\"150 字以內\",\"hint\":\"…\"}]。")
    return merged


def main():
    ap = argparse.ArgumentParser(
        description="期末素材包＋草稿指令（把整年的紀錄依報告格式分好組；不寫評語、不呼叫 AI）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="產出在 exports/（含名冊姓名，已被 .gitignore 擋住，別放到公開的地方）。")
    ap.add_argument("--format", dest="fmt", required=True, metavar="格式",
                    help="報告格式 id：waldorf-homeroom、subject-4、iep-tracking、"
                         "case-summary、custom（清單在 config/report-formats.library.json）")
    ap.add_argument("--target", default="", metavar="代號",
                    help="學生代號（例如 S-03）；all ＝全班每人一包")
    ap.add_argument("--all", action="store_true", dest="do_all",
                    help="全班一包：每位學生各一份，另出一份 _index.md 總表")
    ap.add_argument("--stream", action="append", default=[], metavar="類型",
                    help="只拿某一種學生記錄類型（可重複；不給＝這個格式吃的那幾種）")
    ap.add_argument("--from", dest="dfrom", default="", metavar="YYYY-MM-DD", help="只要這天以後的紀錄")
    ap.add_argument("--to", dest="dto", default="", metavar="YYYY-MM-DD", help="只要這天以前的紀錄")
    ap.add_argument("--out", metavar="目錄", help="輸出目錄（預設 exports/）")
    ap.add_argument("--local", action="store_true", help="只讀本機 markdown，絕不連網")
    lib.add_root_arg(ap)
    a = ap.parse_args()
    lib.apply_root(a)

    dfrom = export_docs.check_date(a.dfrom, "--from")
    dto = export_docs.check_date(a.dto, "--to")
    if dfrom and dto and dfrom > dto:
        lib.die("--from（%s）比 --to（%s）還晚。" % (dfrom, dto), "把兩個日期對調就好。")
    target = a.target or ("all" if a.do_all else "")
    if not target:
        lib.die("要指定 --target（學生代號）或 --all（全班）。",
                "例如 `--format waldorf-homeroom --target S-03`，或 `--all` 全班一次跑完。")
    if a.do_all:
        target = "all"

    kit = lib.load_kit()
    tabs = lib.load_tabs()
    fmt = load_format(a.fmt)
    streams = pick_streams(fmt, tabs, a.stream)

    local, source_note = export_docs.pick_source(kit, tabs, a.local)
    lib.ok("資料來源：%s ・ 格式：%s ・ 記錄類型：%s"
           % (source_note, fmt.get("label") or fmt["id"], "、".join(streams)))
    data = export_records.collect(kit, tabs, local)
    roster = data.get("roster") or {}

    ids = sorted({t["id"] for t in data["targets"] if t["kind"] == "students"})
    if target != "all":
        if target not in ids:
            lib.die("找不到學生 %s" % target,
                    "代號要跟 data/roster.csv 一樣（例如 S-03）；全班就用 `--all`。")
        ids = [target]
    if not ids:
        lib.die("名冊上一位學生都沒有。", "先填 data/roster.csv（代號,姓名,類型），再跑一次。")

    outdir = os.path.expanduser(a.out) if a.out else lib.rpath("exports")
    os.makedirs(outdir, exist_ok=True)
    made, rows = [], []
    for sid in ids:
        recs = []
        for t in data["targets"]:
            if t["kind"] != "students" or t["id"] != sid or t.get("stream") not in streams:
                continue
            recs += [dict(r) for r in t["records"] if export_docs.in_range(r, dfrom, dto)]
        recs.sort(key=lambda r: (rec_date(r), r.get("rid") or ""))
        card = lib.load_card(sid)
        title = export_docs.student_title(sid, roster)
        stem = "%s-%s" % (export_docs.safe_name(sid), export_docs.safe_name(fmt["id"]))
        pack_name = stem + "-素材包.md"
        pack_path = os.path.join(outdir, pack_name)
        prompt_path = os.path.join(outdir, stem + "-prompt.md")
        with open(pack_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(build_pack(fmt, title, sid, recs, card, streams, dfrom, dto))
        with open(prompt_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(build_prompt(fmt, title, sid, pack_name, recs))
        made += [pack_path, prompt_path]
        rows.append({"sid": sid, "title": title, "n": len(recs), "span": span_of(recs),
                     "pack": pack_name, "prompt": os.path.basename(prompt_path),
                     "gap": gap_note(fmt, recs, card)})

    if target == "all":
        idx = os.path.join(outdir, "_index.md")
        with open(idx, "w", encoding="utf-8", newline="\n") as f:
            f.write(build_index(fmt, rows, streams, dfrom, dto))
        made.append(idx)

    lib.ok("素材包完成：%d 位學生、%d 個檔" % (len(ids), len(made)))
    for p in made:
        print("  · " + p)
    print("%s接下來：把「素材包」貼給你的 AI 代理，再貼「prompt」裡最下面那段固定指令。"
          "腳本不寫評語，本文由 AI 寫、你定稿。%s" % (lib.DIM, lib.RESET))
    print("%s檔案裡有名冊姓名，只留在你自己的機器上。%s" % (lib.YELLOW, lib.RESET))


def gap_note(fmt, recs, card):
    """給 _index.md 用的一句話：這位學生還缺什麼。"""
    if fmt["id"] == "iep-tracking":
        goals = card.get("goals") or []
        done = {str((r.get("fields") or {}).get(GOAL_FIELD, "")).strip() for r in recs}
        zero = [g["id"] for g in goals if g["id"] not in done]
        if not goals:
            return "卡片上還沒有目標"
        return "零紀錄目標：%s" % ("、".join(zero) if zero else "（無）")
    if fmt["id"] == "case-summary":
        if not recs:
            return "還沒有會談紀錄"
        miss = [k for k in SOAP_FIELDS
                if any(not str((r.get("fields") or {}).get(k, "")).strip() for r in recs)]
        return "有缺的段落：%s" % ("、".join(miss) if miss else "（無）")
    keys = fmt.get("groupBy") or []
    fixed = fmt.get("dimensions") or []
    if not (keys and fixed):
        return "—"
    got = {k for k in bucket(recs, keys[0], fixed) if k != UNTAGGED}
    miss = [d for d in fixed if d not in got]
    return "缺%s：%s" % (keys[0], "、".join(miss) if miss else "（都有了）")


def build_index(fmt, rows, streams, dfrom, dto):
    L = ["# 全班期末素材包　%s" % (fmt.get("label") or fmt["id"]), "",
         "> 產生於 %s ・ 格式 `%s` ・ 記錄類型 %s ・ 期間 %s ・ %d 位學生"
         % (lib.now_iso().replace("T", " "), fmt["id"], "、".join(streams) or "全部",
            "%s 至 %s" % (dfrom or "最早", dto or "最新"), len(rows)),
         "", "| 對象 | 則數 | 期間 | 待補 | 素材包 | 草稿指令 |", "|---|---|---|---|---|---|"]
    for r in rows:
        L.append("| %s | %d | %s | %s | `%s` | `%s` |"
                 % (cell(r["title"]), r["n"], r["span"], cell(r["gap"]), r["pack"], r["prompt"]))
    empty = [r["title"] for r in rows if r["n"] == 0]
    L += ["", "## 全班先看這幾件事", "",
          "- 一則紀錄都沒有的：%s" % ("、".join(empty) if empty else "（沒有，每一位都有紀錄）"),
          "- 總則數：%d" % sum(r["n"] for r in rows),
          "- 每一位的「待補」欄就是期末寫評語時最會卡住的地方；現在回頭補紀錄還來得及。",
          "", "## 定稿前的全班稽核", ""]
    L += ["- [ ] %s" % x for x in (fmt.get("audit") or [])]
    L += ["", "> 這些檔含名冊姓名，只留在你自己的機器上。", ""]
    return tidy(L)


if __name__ == "__main__":
    main()
