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
import subprocess
import urllib.parse
import urllib.request
import urllib.error
from email.mime.text import MIMEText

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
RED, GREEN, YELLOW, DIM, RESET = "\033[31m", "\033[32m", "\033[33m", "\033[2m", "\033[0m"


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
        with open(path, encoding="utf-8") as f:
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


def project_id(kit):
    pid = (kit.get("firebase") or {}).get("project_id", "")
    if not pid or pid.startswith("your-"):
        die("config/kit.json 的 firebase.project_id 還沒填。",
            "到 https://console.firebase.google.com 開專案，把專案 ID 填進去；或重跑 `python3 scripts/setup.py`。")
    return pid


def fb_base(kit):
    return ("https://firestore.googleapis.com/v1/projects/%s/databases/(default)/documents"
            % project_id(kit))


def id_prefix(kit):
    """代號前綴，正規化成不帶連字號（S-01 的 S）。"""
    return (kit.get("id_prefix") or "S").rstrip("-") or "S"


def student_id(kit, n):
    """把座號／序號變成代號：3 → S-03。"""
    return "%s-%02d" % (id_prefix(kit), int(n))


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
    with open(path, encoding="utf-8") as f:
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


def file_header(kind, ident, label=""):
    """新建一個記錄檔時的檔頭（取 templates/ 的範本，砍掉範例區塊）。"""
    tpl = {"students": "observation.example.md",
           "class": "observation.example.md",
           "courses": "course-records.example.md",
           "business": "business-records.example.md"}[kind]
    path = pkg_path("templates", tpl)
    text = ""
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            text = f.read().split("<!-- 以下是範例紀錄")[0]
    if not text.strip():
        text = "---\nid: {{ID}}\nkind: %s\n---\n\n# {{LABEL}}\n" % kind
    text = text.replace("{{ID}}", ident).replace("{{LABEL}}", label or ident)
    return text.rstrip("\n") + "\n\n"


# ── 四種目標 ────────────────────────────────────────────────────────────
def targets(kit, tabs, data_root=None):
    """回傳這位老師的所有記錄目標，四種混在一起、順序固定（同步、台帳、匯出共用）。

    每一項：{kind, id, label, path（本機 md）, records（Firestore 集合）, card（卡片文件或 None）}
      · students  ← data/roster.csv 的代號（＋ data/students/ 底下已存在的資料夾）
      · class     ← 固定一個 main
      · courses   ← data/courses/*/ 的資料夾（＋ tabs.courses.list 設定的課）
      · business  ← tabs.business.groups 勾選的組
    """
    d = data_root or data_dir()
    out = []
    tabs = tabs or {}

    if (tabs.get("students") or {}).get("enabled", True):
        ids = set(load_roster(kit, d).keys())
        sdir = os.path.join(d, "students")
        if os.path.isdir(sdir):
            ids |= {x for x in os.listdir(sdir)
                    if os.path.isdir(os.path.join(sdir, x)) and re.match(r".+-\d+$", x)}
        for sid in sorted(ids):
            out.append({"kind": "students", "id": sid, "label": sid,
                        "path": os.path.join(d, "students", sid, "observations.md"),
                        "records": "students/%s/records" % sid,
                        "card": "students/%s" % sid})
        out.append({"kind": "class", "id": "main", "label": "班級整體觀察",
                    "path": os.path.join(d, "class", "observations.md"),
                    "records": "class-observations", "card": None})

    if (tabs.get("courses") or {}).get("enabled", True):
        cids = {c.get("id") for c in ((tabs.get("courses") or {}).get("list") or []) if c.get("id")}
        cdir = os.path.join(d, "courses")
        if os.path.isdir(cdir):
            cids |= {x for x in os.listdir(cdir) if os.path.isdir(os.path.join(cdir, x))}
        titles = {c.get("id"): c.get("title", "") for c in ((tabs.get("courses") or {}).get("list") or [])}
        for cid in sorted(x for x in cids if x):
            out.append({"kind": "courses", "id": cid, "label": titles.get(cid) or cid,
                        "path": os.path.join(d, "courses", cid, "records.md"),
                        "records": "courses/%s/records" % cid,
                        "card": "courses/%s" % cid})

    if (tabs.get("business") or {}).get("enabled", True):
        for g in ((tabs.get("business") or {}).get("groups") or []):
            gid = g.get("id")
            if not gid:
                continue
            out.append({"kind": "business", "id": gid, "label": g.get("label") or gid,
                        "path": os.path.join(d, "business", gid, "records.md"),
                        "records": "business/%s/records" % gid,
                        "card": "business/%s" % gid})
    return out


def find_target(kit, tabs, kind, ident, data_root=None):
    """指定 kind＋id 拿一個目標（append_record、ledger 用）。找不到回 None。"""
    if kind == "class":
        ident = ident or "main"
    for t in targets(kit, tabs, data_root):
        if t["kind"] == kind and t["id"] == ident:
            return t
    return None


# ── 名冊 ────────────────────────────────────────────────────────────────
def roster_path(data_root=None):
    return os.path.join(data_root or data_dir(), "roster.csv")


def load_roster(kit=None, data_root=None):
    """data/roster.csv（第一欄編號或代號、第二欄姓名）→ {代號: 姓名}。

    真名只住在這個檔——它是 PII gate 的鑰匙，也是網頁顯示姓名的來源。
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
            if len(row) < 2 or not row[1].strip():
                continue
            if re.match(r"^\D+-\d+$", first):
                sid = first
            else:
                num = re.sub(r"\D", "", first)
                if not num:
                    continue
                sid = "%s-%s" % (prefix, num.zfill(2))
            out[sid] = row[1].strip()
    return out


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
    """gcloud 的存取權杖。拿不到就 die（除非 quiet=True，那就回 None）。"""
    try:
        return subprocess.check_output(["gcloud", "auth", "print-access-token"],
                                       text=True, stderr=subprocess.DEVNULL, timeout=60).strip()
    except Exception:
        if quiet:
            return None
        die("取不到 gcloud 存取權杖——本機腳本要用它讀寫你自己的 Firestore。",
            "先跑 `gcloud auth login`（用你當初開 Firebase 專案的 Google 帳號）；"
            "還沒裝 gcloud 就先跑 `bash scripts/install_tools.sh`。")


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
        if e.code == 412 and (precondition_update_time or precondition_exists is not None):
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
        subprocess.run(["gws", "gmail", "+send", "--to", ",".join(to_list),
                        "--subject", subject, "--body", body], check=True, stdout=subprocess.DEVNULL)
        return
    user = e.get("smtp_user", "")
    pw = os.environ.get("KIT_SMTP_APP_PASSWORD", "")
    if not user or not pw:
        die("寄信需要 config/kit.json 的 email.smtp_user，加上環境變數 KIT_SMTP_APP_PASSWORD。",
            "應用程式密碼在 Google 帳號 → 安全性 → 兩步驟驗證 → 應用程式密碼；"
            "拿到後 `export KIT_SMTP_APP_PASSWORD='那串密碼'` 再跑一次（別寫進任何檔案）。")
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = subject, user, ", ".join(to_list)
    with smtplib.SMTP("smtp.gmail.com", 587) as s:
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
    with open(os.path.join(d, "audit.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
