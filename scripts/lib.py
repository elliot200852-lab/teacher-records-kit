#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""lib.py — 全部腳本共用的底層：設定、路徑、記錄區塊解析、Firestore REST、寄信。

零第三方相依（只用 Python 3 標準庫）。這支不單獨執行，由其他腳本 `import lib` 使用。

三個概念先分清楚：
  · PKG  ＝ 這份 kit 程式碼在哪（scripts/ 的上一層）。templates/、firestore.rules.tmpl 住這裡。
  · ROOT ＝ 這位老師的資料與設定在哪（config/、data/、backups/、site/ 的產生檔）。
           平常 ROOT == PKG；測試或多帳號時用 `--root <目錄>` 或環境變數 TRK_ROOT 指到別處。
  · 找檔一律走 pkg_path()：ROOT 有就用 ROOT 的，沒有才回頭找 PKG 的（範本用得到）。

錯誤一律兩行：紅色「✗ 原因」＋「→ 怎麼修」。老師看得懂比堆疊追蹤重要。
"""
import os
import re
import csv
import ssl
import json
import time
import hashlib
import smtplib
import urllib.parse
import urllib.request
import urllib.error
from email.mime.text import MIMEText

import hostos                      # 平台差異只寫在 hostos.py
hostos.enable_console()            # Windows：主控台改 UTF-8、開 ANSI 顏色
PY = hostos.PY                     # 這台電腦怎麼叫 Python（訊息裡用）

# ── 路徑 ────────────────────────────────────────────────────────────────
PKG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ROOT = os.path.abspath(os.path.expanduser(os.environ.get("TRK_ROOT") or PKG))


def root():
    """這位老師的資料根目錄。"""
    return _ROOT


def set_root(path):
    """把資料根目錄改到別的地方（`--root` 用）。回傳新的根目錄。"""
    global _ROOT
    _ROOT = os.path.abspath(os.path.expanduser(path))
    return _ROOT


def add_root_arg(ap):
    """給每支腳本的 argparse 加上共用的 `--root`。"""
    ap.add_argument("--root", metavar="目錄",
                    help="資料根目錄（預設＝這份 kit 所在資料夾；測試或多帳號才需要指定）")
    return ap


def apply_root(args):
    if getattr(args, "root", None):
        set_root(args.root)
    return _ROOT


def rpath(*parts):
    """ROOT 底下的路徑。"""
    return os.path.join(_ROOT, *parts)


def pkg_path(*parts):
    """先找 ROOT，找不到才用 PKG（範本、規則樣板這類「程式碼自帶」的檔案）。"""
    a = os.path.join(_ROOT, *parts)
    if os.path.exists(a):
        return a
    return os.path.join(PKG, *parts)


def data_dir():
    return rpath("data")


# ── 訊息 ────────────────────────────────────────────────────────────────
RED, GREEN, YELLOW, DIM, RESET = ("\033[31m", "\033[32m", "\033[33m", "\033[2m", "\033[0m") \
    if hostos.color_ok() else ("", "", "", "", "")


def err(msg, fix=""):
    """印錯誤（不結束）。"""
    import sys
    sys.stderr.write("%s✗ %s%s\n" % (RED, msg, RESET))
    if fix:
        sys.stderr.write("  → %s\n" % fix)


def die(msg, fix=""):
    """印錯誤並結束（exit 1）。"""
    import sys
    err(msg, fix)
    sys.exit(1)


def ok(msg):
    print("%s✓ %s%s" % (GREEN, msg, RESET))


def warn(msg):
    print("%s! %s%s" % (YELLOW, msg, RESET))


# ── 版本 ────────────────────────────────────────────────────────────────
def version():
    """這份 kit 的版本字串（讀 VERSION 檔）。網頁、doctor、meta/config 都用同一個來源。"""
    p = pkg_path("VERSION")
    try:
        with open(p, encoding="utf-8") as f:
            return f.read().strip() or "3"
    except OSError:
        return "3"


# 資料格式版本（規則與 markdown 區塊的形狀）。程式版本往上跳不代表資料要搬家，
# 所以 meta/config 同時記 version（程式版本字串）與 dataVersion（這個整數）。
DATA_VERSION = 3


# ── 設定 ────────────────────────────────────────────────────────────────
KIT_JSON = "config/kit.json"
TABS_JSON = "config/tabs.json"


def _strip_comments(obj):
    """拿掉所有「_註解_…」鍵（JSON 不能寫註解，我們用鍵名代替）。"""
    if isinstance(obj, dict):
        return {k: _strip_comments(v) for k, v in obj.items() if not k.startswith("_")}
    if isinstance(obj, list):
        return [_strip_comments(x) for x in obj]
    return obj


def _load_json(path, what, fix):
    if not os.path.exists(path):
        die("找不到 %s：%s" % (what, path), fix)
    try:
        # utf-8-sig：Windows 的記事本與 Excel 存出來的 JSON 前面會多一個 BOM，
        # 用 utf-8 讀會在第一個字元就炸掉（而老師看到的檔案內容明明是對的）。
        with open(path, encoding="utf-8-sig") as f:
            return _strip_comments(json.load(f))
    except json.JSONDecodeError as e:
        die("%s 不是合法的 JSON（第 %d 行第 %d 欄：%s）" % (what, e.lineno, e.colno, e.msg),
            "多半是少了逗號、多了一個逗號，或引號沒成對。用編輯器打開 %s 看那一行。" % path)


def load_kit(required=True):
    """讀 config/kit.json。required=False 時檔案不存在回 {}（給 setup／doctor 用）。"""
    path = rpath(KIT_JSON)
    if not required and not os.path.exists(path):
        return {}
    return _load_json(path, "主設定 config/kit.json",
                      "先跑 `python3 scripts/setup.py` 安裝精靈；它會照你的回答產生這個檔。")


def load_tabs(required=True):
    """讀 config/tabs.json；沒有的話退回範本 config/tabs.example.json。"""
    path = rpath(TABS_JSON)
    if not os.path.exists(path):
        if required:
            fallback = pkg_path("config", "tabs.example.json")
            if os.path.exists(fallback):
                return _load_json(fallback, "分頁設定範本 config/tabs.example.json", "")
        else:
            return {}
    return _load_json(path, "分頁設定 config/tabs.json",
                      "先跑 `python3 scripts/setup.py` 安裝精靈；它會照你的回答產生這個檔。")


def load_library():
    """業務組庫（勾選清單）。"""
    return _load_json(pkg_path("config", "business-groups.library.json"),
                      "業務組庫 config/business-groups.library.json",
                      "這個檔跟著程式碼走，重新下載一份 kit 就有了。")


def load_stream_library():
    """學生記錄類型庫（勾選清單）。"""
    return _load_json(pkg_path("config", "student-streams.library.json"),
                      "學生記錄類型庫 config/student-streams.library.json",
                      "這個檔跟著程式碼走，重新下載一份 kit 就有了。")


def load_report_formats():
    """期末報告格式庫（`report_pack.py --format` 的可選清單）。"""
    return _load_json(pkg_path("config", "report-formats.library.json"),
                      "報告格式庫 config/report-formats.library.json",
                      "這個檔跟著程式碼走，重新下載一份 kit 就有了。")


def find_format(fid, formats=None):
    """依 id 拿一個報告格式；找不到回 None。"""
    for f in ((formats or load_report_formats()).get("formats") or []):
        if f.get("id") == fid:
            return f
    return None


def load_verticals():
    """三個垂直方案（安裝精靈唸給老師聽的建議；只是建議，不預先勾）。"""
    return _load_json(pkg_path("config", "verticals.json"),
                      "垂直方案庫 config/verticals.json",
                      "這個檔跟著程式碼走，重新下載一份 kit 就有了。")


def find_vertical(vid, verticals=None):
    for v in ((verticals or load_verticals()).get("verticals") or []):
        if v.get("id") == vid:
            return v
    return None


def load_custom_format():
    """老師自己貼的校方格式 config/report-format.custom.json（沒有就回 None）。"""
    path = rpath("config", "report-format.custom.json")
    if not os.path.exists(path):
        return None
    return _load_json(path, "校方格式 config/report-format.custom.json",
                      "照 templates/report-format.custom.example.json 的格式寫。")


# ── 兩個可選：資料庫模式與無頭交辦 ──────────────────────────────────────
# 這兩個開關跟三個分頁一樣是「老師自己勾、零預設」，正本都在 config/kit.json。
MODES = ("cloud", "local")
HEADLESS_TOOLS = ("line",)
HEADLESS_TIMEOUT_DEFAULT = 1800      # 秒：AI 代理跑一則交辦最多多久（超過就連子孫行程一起殺）


def mode(kit):
    """資料庫模式：cloud＝自己的 Firebase 專案＋手機網頁；local＝完全不碰雲端，只有 data/*.md。

    沒寫（v3.0.0-alpha.4 之前的設定）一律當 cloud——那是原本的行為，升級不能默默改掉。
    """
    m = (kit.get("mode") or "cloud").strip().lower()
    return m if m in MODES else "cloud"


def is_local(kit):
    return mode(kit) == "local"


def headless_cfg(kit):
    """無頭交辦設定（正規化過，一定有全部的鍵）。沒設就是「沒開」。"""
    h = dict(kit.get("headless") or {})
    line = dict(h.get("line") or {})
    return {
        "enabled": bool(h.get("enabled")),
        "tool": (h.get("tool") or "line").strip().lower(),
        "agent": (h.get("agent") or "").strip().lower(),
        "timeout_sec": int(h.get("timeout_sec") or HEADLESS_TIMEOUT_DEFAULT),
        "line": {
            "channel_secret_env": (line.get("channel_secret_env") or "KIT_LINE_CHANNEL_SECRET").strip(),
            "channel_token_env": (line.get("channel_token_env") or "KIT_LINE_CHANNEL_TOKEN").strip(),
            "owner_user_id": (line.get("owner_user_id") or "").strip(),
        },
    }


def headless_on(kit):
    """無頭交辦開著嗎。本機模式沒有雲端可以收件，一律當關著。"""
    return bool(headless_cfg(kit)["enabled"]) and not is_local(kit)


# 評量維度自動補標（選用）：同步做完之後，請 AI 代理替還沒有維度標的學生紀錄補上代表標籤。
# 邏輯全在 scripts/auto_dim_tags.py；這裡只管讀設定（跟上面兩個開關一樣：老師自己勾、零預設）。
AUTO_DIM_TIMEOUT_DEFAULT = 600       # 秒：一批（最多 30 則）最多讓 AI 想多久，超過就停掉、這一批不寫
AUTO_DIM_MAX_BATCHES_DEFAULT = 2     # 一次同步最多送幾批：老師多半是叫互動式 AI 跑同步，第一次開、舊紀錄多時
                                     # 一口氣全送會跑到被那個代理的指令逾時殺掉；剩下的等下次同步


def auto_dim_tags_cfg(kit):
    """評量維度自動補標的設定（正規化過，一定有全部的鍵）。沒設就是「沒開」。

    agent 空字串＝沿用 headless.agent；兩者都空＝視同沒設定（auto_dim_tags_on 為假）。
    """
    a = dict((kit or {}).get("auto_dim_tags") or {})
    own = str(a.get("agent") or "").strip().lower()
    inherited = headless_cfg(kit or {})["agent"]
    try:
        timeout = int(a.get("timeout_sec") or AUTO_DIM_TIMEOUT_DEFAULT)
    except (TypeError, ValueError):
        timeout = AUTO_DIM_TIMEOUT_DEFAULT
    try:
        max_batches = int(a.get("max_batches") or AUTO_DIM_MAX_BATCHES_DEFAULT)
    except (TypeError, ValueError):
        max_batches = AUTO_DIM_MAX_BATCHES_DEFAULT
    return {"enabled": bool(a.get("enabled")), "agent": own or inherited, "agent_own": own,
            "agent_inherited": bool(inherited and not own), "timeout_sec": timeout,
            "max_batches": max(1, max_batches)}


def auto_dim_tags_on(kit):
    """補標會不會真的跑：開著、有代理可叫、而且不是本機模式（本機模式沒有同步可以接）。"""
    c = auto_dim_tags_cfg(kit)
    return c["enabled"] and bool(c["agent"]) and not is_local(kit or {})


def project_id(kit):
    pid = (kit.get("firebase") or {}).get("project_id", "")
    if not pid or pid.startswith("your-"):
        die("config/kit.json 的 firebase.project_id 還沒填。",
            "到 https://console.firebase.google.com 開專案，把專案 ID 填進去；或重跑 `python3 scripts/setup.py`。")
    return pid


def emulator_host():
    """Firestore 模擬器（測試與 CI 用）。設了標準環境變數 FIRESTORE_EMULATOR_HOST 就走本機模擬器；
    正式使用永遠不設它。"""
    return (os.environ.get("FIRESTORE_EMULATOR_HOST") or "").strip()


def fb_base(kit):
    host = emulator_host()
    if host:
        return "http://%s/v1/projects/%s/databases/(default)/documents" % (host, project_id(kit))
    return ("https://firestore.googleapis.com/v1/projects/%s/databases/(default)/documents"
            % project_id(kit))


def storage_bucket(kit):
    """Cloud Storage 的 bucket 名（無頭交辦的錄音放那裡）。沒填就照 Firebase 現在的預設推。"""
    fb = kit.get("firebase") or {}
    b = (fb.get("storage_bucket") or "").strip()
    if b:
        return b.replace("gs://", "").rstrip("/")
    return "%s.firebasestorage.app" % project_id(kit)


ID_WIDTH = 2                       # 代號的數字補到幾位（S-03、6B-01）


def id_prefix(kit):
    """代號前綴，正規化成不帶連字號（S-01 的 S）。"""
    return (kit.get("id_prefix") or "S").rstrip("-") or "S"


def student_id(kit, n):
    """把座號／序號變成代號：3 → S-03。"""
    return "%s-%0*d" % (id_prefix(kit), ID_WIDTH, int(n))


# ── 記錄區塊 ────────────────────────────────────────────────────────────
# `## YYYY-MM-DD [HH:MM[:SS]] #標籤…`
# 時間是「同一天第二則之後」才出現的可選欄位（第一則沿用純日期，與舊檔完全相容）。
DATE_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})(?:\s+(\d{2}:\d{2}(?::\d{2})?))?\b\s*(.*)$")
# 欄位列：`鍵：值`（全形冒號）。鍵不能含冒號、不能是空的。
FIELD_RE = re.compile(r"^([^：#\s][^：]{0,40})：\s*(.*)$")
DATE_ONLY_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RELATED_KEY = "關聯"
# 關聯語法：<kind>/<target>/<rid>
KINDS = ("students", "class", "courses", "business")


def rid_for(date, tm):
    """紀錄 id：當天第一則＝日期本身；之後帶建立時間 → `2026-09-10-1435`。

    身分由「日期＋時間」決定，所以在檔案中間插入一則不會讓其他則改名——
    用出現順序編號（-2、-3）會，那會讓下一次同步把舊副本當成新紀錄再建一次。
    """
    return date if not tm else "%s-%s" % (date, tm.replace(":", ""))


def time_from_rid(date, rid):
    """反解：`2026-09-10-1435` → `14:35`、`-143512` → `14:35:12`、純日期 → None。"""
    if not rid or rid == date or not rid.startswith(date + "-"):
        return None
    suf = rid[len(date) + 1:]
    if len(suf) == 4 and suf.isdigit():
        return suf[:2] + ":" + suf[2:]
    if len(suf) == 6 and suf.isdigit():
        return suf[:2] + ":" + suf[2:4] + ":" + suf[4:]
    return None


def norm_tags(raw):
    """把 '#課堂 學習' 或 ['課堂'] 正規化成 ['#課堂', '#學習']（去重、保序）。"""
    if isinstance(raw, str):
        toks = raw.split()
    else:
        toks = list(raw or [])
    out, seen = [], set()
    for t in toks:
        t = str(t).strip()
        if not t:
            continue
        t = "#" + t.lstrip("#").strip()
        if t == "#" or t in seen:
            continue
        seen.add(t)
        out.append(t)
    return out


def parse_related(text):
    """`關聯：` 行 → ['students/S-03/2026-09-10', ...]（分號或全形分號分隔）。"""
    if isinstance(text, (list, tuple)):
        items = [str(x) for x in text]
    else:
        items = re.split(r"[;；]", str(text or ""))
    out, seen = [], set()
    for it in items:
        it = it.strip()
        if it and it not in seen:
            seen.add(it)
            out.append(it)
    return out


def content_hash(tags, fields, related, body):
    """一則記錄的內容指紋（本機與雲端兩邊算出來必須一致）。

    形狀：sha256("標籤|欄位JSON|關聯|正文")[:16]。欄位用 sort_keys 序列化，
    所以「同樣的欄位換個順序寫」不會被當成改過。
    """
    payload = "|".join([
        " ".join(norm_tags(tags)),
        json.dumps({str(k): str(v) for k, v in (fields or {}).items()},
                   ensure_ascii=False, sort_keys=True),
        ";".join(parse_related(related)),
        (body or "").strip(),
    ])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def parse_block(lines):
    """一則記錄（含 `## …` 標題列）→ {date,time,rid,tags,fields,related,body,hash}。

    §2.2 的寬鬆規則：標題列之後、第一個空行之前，任何 `鍵：值`（全形冒號）行都收進
    fields——就算那個鍵不在該業務組設定的欄位裡也照收（欄位是表單建議、不是 schema 閘，
    改欄位名不需要搬資料）。`關聯：` 是保留鍵，分號切。遇到不像欄位列的行就當正文開始。
    """
    lines = list(lines)
    if not lines:
        return None
    m = DATE_RE.match(lines[0])
    if not m:
        return None
    date, tm = m.group(1), m.group(2)
    tags = norm_tags(re.findall(r"#\S+", m.group(3) or ""))
    fields, related, i = {}, [], 1
    while i < len(lines):
        line = lines[i]
        if line.strip() == "":
            i += 1
            break
        fm = FIELD_RE.match(line.strip())
        if not fm:
            break                      # 不是欄位列 → 從這裡開始都是正文
        key, val = fm.group(1).strip(), fm.group(2).strip()
        if key == RELATED_KEY:
            related = parse_related(val)
        else:
            fields[key] = val
        i += 1
    body = "\n".join(lines[i:]).strip()
    return {"date": date, "time": tm, "rid": rid_for(date, tm), "tags": tags,
            "fields": fields, "related": related, "body": body,
            "hash": content_hash(tags, fields, related, body)}


def render_block(date, time_=None, tags=(), fields=None, related=(), body=""):
    """反向：把一則記錄畫回 markdown 行（結尾固定留一個空行）。

    與 parse_block 互為往返：render 出來的東西 parse 回去必須一模一樣。
    """
    tags = norm_tags(tags)
    head = "## " + date + ((" " + time_) if time_ else "") + ((" " + " ".join(tags)) if tags else "")
    out = [head]
    for k, v in (fields or {}).items():
        if str(k).strip() == RELATED_KEY:
            continue
        out.append("%s：%s" % (str(k).strip(), str(v).strip()))
    rel = parse_related(related)
    if rel:
        out.append("%s：%s" % (RELATED_KEY, "; ".join(rel)))
    out.append("")
    out += (body or "").strip().split("\n")
    out.append("")
    return out


def parse_file(path):
    """整個 md 檔 → (lines, blocks)。block 多帶 start/end 行號，供原地替換。"""
    if not os.path.exists(path):
        return [], []
    with open(path, encoding="utf-8-sig") as f:        # 帶 BOM 的 md（記事本存的）也讀得到
        lines = f.read().split("\n")
    starts = [i for i, l in enumerate(lines) if DATE_RE.match(l)]
    blocks = []
    for k, si in enumerate(starts):
        ei = starts[k + 1] if k + 1 < len(starts) else len(lines)
        b = parse_block(lines[si:ei])
        if b:
            b["start"], b["end"] = si, ei
            blocks.append(b)
    return lines, blocks


def file_header(kind, ident, label="", stream_label=""):
    """新建一個記錄檔時的檔頭（取 templates/ 的範本，砍掉範例區塊）。

    學生／班級的檔頭依記錄類型的範圍換範本：`scope:case` 的類型——個案追蹤、IEP、會談紀錄（SOAP）——
    用 case-records.example.md（有欄位列說明），其餘用 observation.example.md。
    """
    tpl = {"students": "observation.example.md",
           "class": "observation.example.md",
           "case": "case-records.example.md",
           "courses": "course-records.example.md",
           "business": "business-records.example.md"}[kind]
    path = pkg_path("templates", tpl)
    text = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            text = f.read().split("<!-- 以下是範例紀錄")[0]
    if not text.strip():
        text = "---\nid: {{ID}}\nkind: %s\n---\n\n# {{LABEL}}\n" % kind
    text = (text.replace("{{ID}}", ident)
                .replace("{{LABEL}}", label or ident)
                .replace("{{STREAM}}", stream_label or ""))
    return text.rstrip("\n") + "\n\n"


# ── 學生記錄類型（stream）────────────────────────────────────────────────
# 學生分頁再分「記錄類型」：導師班級學生紀錄、任課老師學生紀錄、個案追蹤、IEP、會談紀錄（SOAP）…
# 每一種各有自己的欄位、分類詞與「哪些學生在裡面」（scope）。安裝時全部由老師勾選，沒有預設。
SCOPES = ("class", "case")
LEGACY_STREAM = {"id": "homeroom", "label": "導師班級學生紀錄", "scope": "class",
                 "fields": [], "tags": [], "custom": False}


def stream_file(stream_id):
    """本機檔名：每位學生、每種類型一檔。`homeroom` 沿用 v2 的 observations.md。"""
    return "observations.md" if stream_id == "homeroom" else "%s.md" % stream_id


def student_streams(tabs):
    """這位老師勾了哪些學生記錄類型。

    · `students.streams` 是空陣列 → 一種都沒勾（零預設，學生分頁不會有任何目標）。
    · 整個 `streams` 鍵不存在 → v2 舊設定，當成只有「導師班級學生紀錄」一種
      （它的檔名正好就是 v2 的 observations.md，所以舊資料原地可用）。
    """
    st = (tabs or {}).get("students") or {}
    if "streams" not in st:
        return [dict(LEGACY_STREAM)]
    out = []
    for s in (st.get("streams") or []):
        if isinstance(s, str):
            s = {"id": s}
        if s.get("id"):
            out.append(dict(s, scope=(s.get("scope") or "class")))
    return out


def stream_ids(s):
    """一種類型認得的所有 id：自己的 id ＋ 舊 id（aliases）。

    v3 alpha 把 counseling 併進 soap，所以 `--stream counseling` 也要打得中 soap。
    本機檔名照設定裡的 id 走（`stream_file`），資料不必搬。
    """
    return [s.get("id")] + [a for a in (s.get("aliases") or []) if a]


def find_stream(tabs, stream_id):
    for s in student_streams(tabs):
        if stream_id in stream_ids(s):
            return s
    return None


# ── 學生卡片（goals／個案概念化）──────────────────────────────────────────
# 兩塊「不是一則一則的記錄，而是一直被回頭改的底稿」：
#   goals[]           IEP／早療的學年與學期目標（每一則 iep 記錄靠 `目標編號` 掛在某一條下）
#   conceptualization 個案概念化（主訴／背景／評估假設／處遇目標／結案標準）
# 本機住 data/students/<代號>/card.json，雲端住 students/<代號>；sync.py 雙向同步、衝突不覆蓋。
CARD_FILE = "card.json"
GOAL_KEYS = ("id", "領域", "學年目標", "學期目標", "評量方式", "評量標準", "期程")
CONCEPT_KEYS = ("主訴", "背景", "評估假設", "處遇目標", "結案標準")


def card_path(sid, data_root=None):
    return os.path.join(data_root or data_dir(), "students", sid, CARD_FILE)


def norm_goals(raw):
    """goals[] 正規化：只留固定七個鍵、值一律字串、沒有 id 的自動編 G1、G2…"""
    out = []
    for i, g in enumerate(raw or [], 1):
        if not isinstance(g, dict):
            continue
        gid = str(g.get("id") or "").strip() or "G%d" % i
        item = {"id": gid}
        for k in GOAL_KEYS[1:]:
            item[k] = str(g.get(k) or "").strip()
        out.append(item)
    return out


def norm_conceptualization(raw):
    """個案概念化正規化：固定五格，缺的補空字串；全空回 {}。"""
    raw = raw or {}
    if not isinstance(raw, dict):
        return {}
    out = {k: str(raw.get(k) or "").strip() for k in CONCEPT_KEYS}
    return out if any(out.values()) else {}


def load_card(sid, data_root=None):
    """讀一位學生的卡片；沒有這個檔回 {"id": sid, "goals": [], "conceptualization": {}}。"""
    path = card_path(sid, data_root)
    data = {}
    if os.path.exists(path):
        data = _load_json(path, "學生卡片 %s" % os.path.relpath(path, root()),
                          "照 templates/card.example.json 的格式寫；"
                          "或把它刪掉重跑 `python3 scripts/setup.py`。")
    if not isinstance(data, dict):
        data = {}
    return {"id": data.get("id") or sid,
            "goals": norm_goals(data.get("goals")),
            "conceptualization": norm_conceptualization(data.get("conceptualization"))}


def save_card(sid, card, data_root=None):
    """寫回卡片（只寫 id／goals／conceptualization 三個鍵，其他鍵原樣保留）。"""
    path = card_path(sid, data_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    old = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                old = json.load(f)
        except Exception:
            old = {}
    if not isinstance(old, dict):
        old = {}
    old.update({"id": card.get("id") or sid,
                "goals": norm_goals(card.get("goals")),
                "conceptualization": norm_conceptualization(card.get("conceptualization"))})
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(old, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return path


def card_fingerprint(card):
    """卡片上這兩塊的指紋（判斷「本機改了沒／雲端改了沒」用）。"""
    payload = json.dumps({"goals": norm_goals((card or {}).get("goals")),
                          "conceptualization": norm_conceptualization(
                              (card or {}).get("conceptualization"))},
                         ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def stream_needs(streams, key):
    """這些記錄類型裡，有沒有哪一種需要卡片上的 goals／conceptualization。"""
    return [s for s in streams if ((s.get("card") or {}).get(key))]


# ── 課程卡片（整體課程紀錄）──────────────────────────────────────────────
# 課程也有一塊「不是一則一則的記錄」：overview——整門課不分天的整體紀錄
# （這門課想做什麼、走過來變成什麼樣）。雲端住 courses/<id> 這張卡的 `overview` 欄位，
# 本機住 data/courses/<id>/card.json（只有 overview 一個鍵，沒有 goals／conceptualization），
# sync.py 雙向同步、衝突不覆蓋——跟學生卡片同一條規則。
#
# 為什麼不跟學生卡片共用 load_card／save_card：那一套存檔時一定會寫 goals 與
# conceptualization 兩個鍵，拿來存課程卡等於在課程卡上長出兩塊空的學生欄位；
# 反過來拿學生卡的指紋去比 overview 也永遠比不出差別。兩種卡片各一套，互不干擾。
COURSE_CARD_FILE = "card.json"


def course_card_path(cid, data_root=None):
    return os.path.join(data_root or data_dir(), "courses", cid, COURSE_CARD_FILE)


def norm_overview(raw):
    """整體課程紀錄正規化：一律字串、前後空白去掉（兩邊的換行差異不該被當成「改過了」）。"""
    return str(raw or "").strip()


def load_course_card(path):
    """讀一門課的卡片（吃檔案路徑，不是課程 id）；沒有這個檔回 {"overview": ""}。"""
    data = {}
    if path and os.path.exists(path):
        data = _load_json(path, "課程卡片 %s" % os.path.relpath(path, root()),
                          "它只有一個 overview 欄位（整體課程紀錄的文字）；"
                          "不確定就把它刪掉，下次同步會從網頁重新寫回來。")
    if not isinstance(data, dict):
        data = {}
    return {"overview": norm_overview(data.get("overview"))}


def save_course_card(path, card):
    """寫回課程卡片（只寫 overview，其他鍵原樣保留——網頁以後在這張卡上加什麼都不會被清掉）。"""
    d = os.path.dirname(path)
    if d:
        os.makedirs(d, exist_ok=True)
    old = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                old = json.load(f)
        except Exception:
            old = {}
    if not isinstance(old, dict):
        old = {}
    old["overview"] = norm_overview((card or {}).get("overview"))
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(old, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return path


def course_card_fingerprint(card):
    """課程卡上這一塊的指紋（判斷「本機改了沒／雲端改了沒」用）——只看 overview。"""
    payload = json.dumps({"overview": norm_overview((card or {}).get("overview"))},
                         ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


# ── 記錄目標 ────────────────────────────────────────────────────────────
def targets(kit, tabs, data_root=None):
    """回傳這位老師的所有記錄目標，四種混在一起、順序固定（同步、台帳、匯出共用）。

    每一項：
      {kind, id, stream（students／class 才有）, scope, label, path（本機 md）,
       sourceFile（path 相對 data/）, records（Firestore 集合）, card（卡片文件或 None）,
       key（唯一鍵：students/S-01/case、class/main/homeroom、courses/x、business/y）,
       card_file（只有 courses 有：整體課程紀錄的本機 data/courses/<id>/card.json）}

      · students  ← 每位學生 × 他所屬的每一種記錄類型各一個目標
                    （scope:class 的類型＝名冊全部學生；scope:case 的類型＝
                     roster.csv 第三欄列入的學生，加上已經有那個檔的學生）
      · class     ← 每一種 scope:class 的類型各一個（班級整體觀察）
      · courses   ← data/courses/*/ 的資料夾（＋ tabs.courses.list 設定的課）
      · business  ← tabs.business.groups 勾選的組

    同一位學生的所有類型共用 Firestore 集合 `students/<id>/records`，靠文件裡的
    `stream` 欄位分流；本機則是一種類型一個檔。班級整體觀察也一樣——每一種 class 型
    類型共用 `class-observations`。

    **這代表文件 id（＝rid）只在單一檔案裡唯一是不夠的**：同一天在兩種類型各記一則，
    兩邊都會取到 `2026-09-10` 這個 id，推上雲端時後到的那一則撞成 ALREADY_EXISTS。
    取號的地方（`append_record.next_rid`）因此要把「同集合的兄弟檔」一起算進來——
    文件 id 維持「＝日期（＋時間）」，安全規則與網頁新增的那條路才不用跟著改。
    """
    d = data_root or data_dir()
    out = []
    tabs = tabs or {}

    def add(kind, ident, label, path, records, card, stream=None, scope="class",
            stream_label=""):
        out.append({"kind": kind, "id": ident, "stream": stream, "scope": scope,
                    "streamLabel": stream_label, "label": label, "path": path,
                    "sourceFile": os.path.relpath(path, d).replace(os.sep, "/"),   # 會推上雲端，三平台都用 /
                    "records": records, "card": card,
                    "key": "%s/%s%s" % (kind, ident, ("/" + stream) if stream else "")})

    if (tabs.get("students") or {}).get("enabled", True):
        streams = student_streams(tabs)
        rows = load_roster_rows(kit, d)
        ids = set(rows)
        sdir = os.path.join(d, "students")
        if os.path.isdir(sdir):
            ids |= {x for x in os.listdir(sdir)
                    if os.path.isdir(os.path.join(sdir, x)) and re.match(r".+-\d+$", x)}
        for s in streams:
            sname = stream_file(s["id"])
            if s.get("scope") == "case":
                # 個案型：名冊第三欄列入的，加上「檔案已經在了」的（免得改名冊時紀錄憑空消失）
                members = sorted(i for i in ids
                                 if s["id"] in (rows.get(i, {}).get("streams") or [])
                                 or os.path.exists(os.path.join(sdir, i, sname)))
            else:
                members = sorted(ids)
            for sid in members:
                add("students", sid,
                    "%s（%s）" % (sid, s.get("label") or s["id"]),
                    os.path.join(d, "students", sid, sname),
                    "students/%s/records" % sid, "students/%s" % sid,
                    stream=s["id"], scope=s.get("scope", "class"),
                    stream_label=s.get("label") or s["id"])
        for s in streams:
            if s.get("scope", "class") != "class":
                continue                      # 班級整體觀察只掛在 class 範圍的類型下
            add("class", "main",
                "班級整體觀察（%s）" % (s.get("label") or s["id"]),
                os.path.join(d, "class", stream_file(s["id"])),
                "class-observations", None, stream=s["id"], scope="class",
                stream_label=s.get("label") or s["id"])

    if (tabs.get("courses") or {}).get("enabled", True):
        cids = {c.get("id") for c in ((tabs.get("courses") or {}).get("list") or []) if c.get("id")}
        cdir = os.path.join(d, "courses")
        if os.path.isdir(cdir):
            cids |= {x for x in os.listdir(cdir) if os.path.isdir(os.path.join(cdir, x))}
        titles = {c.get("id"): c.get("title", "") for c in ((tabs.get("courses") or {}).get("list") or [])}
        for cid in sorted(x for x in cids if x):
            add("courses", cid, titles.get(cid) or cid,
                os.path.join(d, "courses", cid, "records.md"),
                "courses/%s/records" % cid, "courses/%s" % cid)
            # 課程多一個 card_file：整體課程紀錄（overview）的本機正本。
            # 只有 courses 有這個鍵——學生卡片走 card_path(sid)，班級與業務組沒有卡片檔。
            out[-1]["card_file"] = course_card_path(cid, d)

    if (tabs.get("business") or {}).get("enabled", True):
        for g in ((tabs.get("business") or {}).get("groups") or []):
            gid = g.get("id")
            if not gid:
                continue
            add("business", gid, g.get("label") or gid,
                os.path.join(d, "business", gid, "records.md"),
                "business/%s/records" % gid, "business/%s" % gid)
    return out


def find_target(kit, tabs, kind, ident, stream=None, data_root=None):
    """指定 kind＋id（＋記錄類型）拿一個目標。找不到回 None。

    students／class 沒給 stream 時：只有一種類型就用那一種，有多種就回 None
    （呼叫端要叫使用者指定 `--stream`——這正是「分不清楚」要防的事）。
    """
    if kind == "class":
        ident = ident or "main"
    hits = [t for t in targets(kit, tabs, data_root) if t["kind"] == kind and t["id"] == ident]
    if stream:
        hits = [t for t in hits if t["stream"] == stream]
    return hits[0] if len(hits) == 1 else None


# ── 名冊 ────────────────────────────────────────────────────────────────
def roster_path(data_root=None):
    return os.path.join(data_root or data_dir(), "roster.csv")


ROSTER_HEADER = "代號,姓名,類型"


def load_roster_rows(kit=None, data_root=None):
    """data/roster.csv（代號,姓名,類型,…）→ {代號: {"name", "streams", "extra"}}。

    第三欄是「這位學生列入哪些個案型記錄類型」，分號分隔（例如 `case;iep`），可以空著；
    `scope:class` 的類型（導師班級、任課老師）不必列，它們自動包含名冊全部學生。
    姓名還沒填也照樣收——名冊常常先有代號、名字慢慢補。
    第四欄之後是老師自己加的欄位（學號、性別、家長信箱…），原樣收進 extra 再原樣寫回去。

    代號一律補零到 ID_WIDTH 位：老師手打的 `S-1` 跟程式產生的 `S-01` 必須是同一個人，
    不然那一列的姓名對不上，PII 閘與網頁顯示都會靜靜地漏掉他。
    """
    path = roster_path(data_root)
    prefix = id_prefix(kit or {})
    out = {}
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8-sig", newline="") as f:
        for i, row in enumerate(csv.reader(f)):
            if not row or not row[0].strip():
                continue
            first = row[0].strip()
            if i == 0 and not re.search(r"\d", first):
                continue                                   # 標頭列
            # 完整代號＝「前綴-數字」。前綴可以含數字（6B、4A 是最常見的班級前綴），
            # 所以不能用 \D+ 抓前綴——那會把 4A-01 讀成裸數字 401、變成 4A-401。
            m = re.match(r"^(.+?)-0*(\d+)$", first)
            if m:
                sid = "%s-%s" % (m.group(1), m.group(2).zfill(ID_WIDTH))
            else:
                num = re.sub(r"\D", "", first)
                if not num:
                    continue
                sid = "%s-%s" % (prefix, num.lstrip("0").zfill(ID_WIDTH))
            name = row[1].strip() if len(row) > 1 else ""
            streams = [s.strip() for s in re.split(r"[;；,，]", row[2]) if s.strip()] \
                if len(row) > 2 else []
            if sid in out:
                # 靜默覆蓋等於少掉一位學生（兩列寫成 S-1 與 S-01 是最常見的寫法）
                err("data/roster.csv 有重複的代號 %s（第 %d 列蓋掉了前面那一列）" % (sid, i + 1),
                    "打開 data/roster.csv，把重複的那一列刪掉或改成別的代號"
                    "（`S-1` 與 `S-01` 是同一個代號）。")
            out[sid] = {"name": name, "streams": streams, "extra": list(row[3:])}
    return out


def load_roster(kit=None, data_root=None):
    """名冊裡有名字的那些 → {代號: 姓名}。

    真名只住在這個檔——它是 PII gate 的鑰匙，也是網頁顯示姓名的來源。
    """
    return {sid: r["name"] for sid, r in load_roster_rows(kit, data_root).items() if r["name"]}


def save_roster_rows(rows, data_root=None):
    """把 {代號: {name, streams, extra}} 寫回 data/roster.csv（代號排序、含表頭）。

    **只重寫前三欄**：第四欄之後是老師自己加的欄位（學號／性別／家長信箱…），
    連同表頭上多出來的欄位名一起原樣保留——同步回寫第三欄不該把它們洗掉。
    寫 utf-8-sig（BOM）：名冊是唯一老師會用 Excel 打開的檔，沒有 BOM 的話
    zh-TW 版 Excel 會把中文姓名讀成亂碼。
    """
    path = roster_path(data_root)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    header = ROSTER_HEADER.split(",")
    if os.path.exists(path):
        with open(path, encoding="utf-8-sig", newline="") as f:
            first = next(csv.reader(f), [])
        if first and not re.search(r"\d", (first[0] or "").strip()):
            header = header + list(first[3:])             # 表頭多出來的欄位名照原樣留著
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, lineterminator="\n")            # 三個平台都寫 LF（Excel 也吃）
        w.writerow(header)
        for sid in sorted(rows):
            r = rows[sid] or {}
            w.writerow([sid, r.get("name", ""), ";".join(r.get("streams") or [])]
                       + list(r.get("extra") or []))
    return path


def real_names(kit=None, data_root=None):
    """名冊裡的真名清單（PII gate 用）。只取兩個字以上的，避免單字誤攔。"""
    return [n for n in load_roster(kit, data_root).values() if n and len(n) >= 2]


def find_names(text, names):
    """文字裡出現了哪些名冊真名（回傳命中的名字）。"""
    t = text or ""
    return [n for n in names if n in t]


# ── Firestore REST ──────────────────────────────────────────────────────
class Precondition(Exception):
    """PATCH 帶了 currentDocument.updateTime 但雲端那份已經被改過（HTTP 412）。"""


class FirestoreError(Exception):
    def __init__(self, code, detail):
        super().__init__("HTTP %s %s" % (code, detail))
        self.code, self.detail = code, detail


def token(quiet=False):
    """gcloud 的存取權杖。拿不到就 die（除非 quiet=True，那就回 None）。模擬器模式回固定的 owner 權杖。"""
    if emulator_host():
        return "owner"
    rc, out, _err = hostos.run(["gcloud", "auth", "print-access-token"], timeout=60, split=True)
    tok = out.strip().splitlines()[0].strip() if rc == 0 and out.strip() else ""    # 只看 stdout：stderr 常有「有更新可用」的提醒
    if tok:
        return tok
    if quiet:
        return None
    die("取不到 gcloud 存取權杖——本機腳本要用它讀寫你自己的 Firestore。",
        ("先跑 `gcloud auth login`（用你當初開 Firebase 專案的 Google 帳號）。" if rc != 127 else
         "還沒裝 gcloud：%s" % hostos.install_hint("gcloud")))


def fs_value(v):
    if v is None:
        return {"nullValue": None}
    if isinstance(v, bool):
        return {"booleanValue": v}
    if isinstance(v, int):
        return {"integerValue": str(v)}
    if isinstance(v, float):
        return {"doubleValue": v}
    if isinstance(v, (list, tuple)):
        return {"arrayValue": {"values": [fs_value(x) for x in v]}}
    if isinstance(v, dict):
        return {"mapValue": {"fields": {str(k): fs_value(x) for k, x in v.items()}}}
    return {"stringValue": str(v)}


def fs_doc(fields):
    return {"fields": {k: fs_value(v) for k, v in fields.items()}}


def py_value(v):
    if not isinstance(v, dict):
        return v
    if "nullValue" in v:
        return None
    if "booleanValue" in v:
        return v["booleanValue"]
    if "integerValue" in v:
        return int(v["integerValue"])
    if "doubleValue" in v:
        return float(v["doubleValue"])
    if "timestampValue" in v:
        return v["timestampValue"]
    if "arrayValue" in v:
        return [py_value(x) for x in (v["arrayValue"].get("values") or [])]
    if "mapValue" in v:
        return {k: py_value(x) for k, x in (v["mapValue"].get("fields") or {}).items()}
    return v.get("stringValue", "")


def doc_fields(doc):
    return {k: py_value(v) for k, v in (doc.get("fields") or {}).items()}


def http(method, base, path, tok, body=None, mask=None,
         precondition_update_time=None, precondition_exists=None,
         params=None, raise_errors=False):
    """Firestore REST 呼叫。

      mask：只更新這幾個欄位（不給就是整份文件覆蓋——沿用 v2 行為）。
      precondition_exists：PATCH 前置條件之二（False＝「這份文件現在必須不存在」，
        用在「本機有、雲端還沒有」的新紀錄上；同一秒鐘網頁剛好也建了同一則就回 412。
      precondition_update_time：PATCH 前置條件（RFC3339，來自 GET 回來的 updateTime）。
        雲端那份在我們讀到之後又被改過 → HTTP 412 → 丟 Precondition，交給呼叫端當衝突處理。
        紅隊 #9：沒有這個條件，老師一邊在手機上打字、腳本一邊回寫，他的字會被靜默蓋掉。
    """
    q = list((params or {}).items())
    for m in (mask or []):
        q.append(("updateMask.fieldPaths", m))
    if precondition_update_time:
        q.append(("currentDocument.updateTime", precondition_update_time))
    elif precondition_exists is not None:
        q.append(("currentDocument.exists", "true" if precondition_exists else "false"))
    has_precond = bool(precondition_update_time) or precondition_exists is not None
    if method == "PATCH" and has_precond:
        # 帶前置條件的 PATCH 一律改走 documents:commit，前置條件放在 body 的 Write 裡——
        # 這是 REST 文件寫明的做法；query 參數版的 currentDocument.updateTime 在 Firestore
        # 模擬器上會被當成 0（2026-09-11 在模擬器上抓到），commit 在正式環境與模擬器都一致。
        write = {"update": {"name": base.split("/v1/", 1)[1] + "/" + path,
                            "fields": fs_doc(body)["fields"]}}
        if mask:
            write["updateMask"] = {"fieldPaths": list(mask)}
        if precondition_update_time:
            write["currentDocument"] = {"updateTime": precondition_update_time}
        else:
            write["currentDocument"] = {"exists": bool(precondition_exists)}
        url, method = base + ":commit", "POST"
        data = json.dumps({"writes": [write]}).encode()
    else:
        url = base + "/" + path + (("?" + urllib.parse.urlencode(q)) if q else "")
        data = json.dumps(fs_doc(body)).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Authorization": "Bearer " + tok,
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:300]
        if method == "GET" and e.code == 404:
            return {}
        # 前置條件不成立：Firestore 回 400 FAILED_PRECONDITION（updateTime 過期）或
        # 409 ALREADY_EXISTS（要求不存在但已存在）；412 是舊文件寫的，一起認。
        if has_precond and (e.code in (409, 412) or (e.code == 400 and "FAILED_PRECONDITION" in detail)):
            raise Precondition(path)
        if raise_errors:
            raise FirestoreError(e.code, detail)
        if e.code in (401, 403):
            die("Firestore %s %s 被拒（HTTP %s）。" % (method, path, e.code),
                "多半是 gcloud 登入的帳號不是這個 Firebase 專案的擁有者。"
                "跑 `gcloud auth login` 換成正確帳號，再 `gcloud config set project <你的專案id>`。")
        die("Firestore %s %s 失敗：HTTP %s %s" % (method, path, e.code, detail),
            "網路不通就等一下再跑；一直失敗把這行訊息貼給 AI 代理看。")
    except urllib.error.URLError as e:
        if raise_errors:
            raise FirestoreError(0, str(e.reason))
        die("連不上 Firestore：%s" % e.reason, "檢查網路連線；離線時可以先跑 `--dry-run` 或 `--offline`。")


def list_docs(base, path, tok, raise_errors=False):
    """列一個集合（自動翻頁）→ [(doc_id, fields, updateTime)]。"""
    out, page = [], ""
    while True:
        params = {"pageSize": 300}
        if page:
            params["pageToken"] = page
        res = http("GET", base, path, tok, params=params, raise_errors=raise_errors) or {}
        for d in res.get("documents", []):
            out.append((d["name"].split("/")[-1], doc_fields(d), d.get("updateTime", "")))
        page = res.get("nextPageToken")
        if not page:
            break
    return out


def get_doc(base, path, tok, raise_errors=False):
    """單一文件 → (fields, updateTime)；不存在回 (None, None)。"""
    d = http("GET", base, path, tok, raise_errors=raise_errors) or {}
    if not d:
        return None, None
    return doc_fields(d), d.get("updateTime", "")


def delete_doc(base, path, tok, raise_errors=True):
    """**真刪**一份 Firestore 文件（不可逆）。只有 `scripts/purge_deleted.py` 會叫它。

    兩段式刪除的第二段：網頁上的刪除只是軟刪（`deleted: true`，文件留在雲端），
    這一支才是把原文從 Firestore 抹掉。安全規則擋不住它——它走的是 gcloud 使用者權杖，
    在 IAM 層，規則只管前端 SDK。"""
    return http("DELETE", base, path, tok, raise_errors=raise_errors)


def is_deleted(fs):
    """雲端那一則是不是被網頁軟刪了（兩段式刪除的第一段）。

    網頁刪除寫的是 `{deleted: true, deletedAt, deletedBy}`，文件本身留在 Firestore；
    本機、匯出、台帳一律當它「已經刪掉」，只有 backup.py 的雲端快照照原樣帶走。"""
    return bool((fs or {}).get("deleted"))


def now_iso():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def touch_status(base, tok, field, quiet=True):
    """更新 meta/status 的 lastSyncAt / lastBackupAt（網頁頂端靠它顯示紅字）。"""
    try:
        http("PATCH", base, "meta/status", tok, {field: now_iso()}, mask=[field], raise_errors=True)
        return True
    except Exception as e:
        if not quiet:
            warn("meta/status 更新失敗（不影響資料）：%s" % e)
        return False


# ── 寄信（SMTP 通用 / gws 進階）────────────────────────────────────────
def mask_email(addr):
    try:
        l, d = addr.split("@", 1)
        return l[0] + "***@" + d
    except ValueError:
        return "***"


# 舊名字，v2 的腳本還在用
mask = mask_email


def send_email(kit, to_list, subject, body):
    e = kit.get("email") or {}
    if e.get("method") == "gws":
        rc, out = hostos.run(["gws", "gmail", "+send", "--to", ",".join(to_list),
                              "--subject", subject, "--body", body], timeout=120)
        if rc == 126:
            die("Windows 上走 gws 寄信會經過 cmd.exe，內文的換行與 & | < > ^ % 會被截斷或改寫。",
                "把 config/kit.json 的 email.method 改成 smtp（用 Gmail 應用程式密碼寄）；Windows 上不支援 gws 寄信。")
        if rc != 0:
            die("gws 寄信失敗（回傳 %s）：%s" % (rc, out.strip()[-200:]),
                "確認 gws 已登入（gws auth login）；或改用 email.method = smtp。" if rc != 127 else hostos.install_hint("gws"))
        return
    user = e.get("smtp_user", "")
    pw = os.environ.get("KIT_SMTP_APP_PASSWORD", "")
    if not user or not pw:
        die("寄信需要 config/kit.json 的 email.smtp_user，加上環境變數 KIT_SMTP_APP_PASSWORD。",
            "應用程式密碼在 Google 帳號 → 安全性 → 兩步驟驗證 → 應用程式密碼；拿到後設環境變數"
            "再跑一次（別寫進任何檔案）：終端機（bash／zsh）打 "
            "`export KIT_SMTP_APP_PASSWORD='那串密碼'`；PowerShell 打 "
            "`$env:KIT_SMTP_APP_PASSWORD = '那串密碼'`。")
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = subject, user, ", ".join(to_list)
    # timeout：學校網路常把 587 直接丟掉（不回 RST），沒有 timeout 的話這裡會永遠掛著，
    # 排程跑的那一支就變成一個永不結束的行程。
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as s:
        s.starttls(context=ssl.create_default_context())
        s.login(user, pw)
        s.sendmail(user, to_list, msg.as_string())


# ── 稽核 ────────────────────────────────────────────────────────────────
def audit(entry, data_root=None):
    """往 data/audit.jsonl 追加一行（唯一寫入通道與刪除都要留痕）。"""
    d = data_root or data_dir()
    os.makedirs(d, exist_ok=True)
    entry = dict(entry)
    entry.setdefault("at", now_iso())
    with open(os.path.join(d, "audit.jsonl"), "a", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
