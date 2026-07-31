#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""共用：讀 config.yaml、Firestore REST、名冊、觀察檔解析。零第三方相依。"""
import os, re, csv, json, ssl, smtplib, subprocess, urllib.request, urllib.error
from email.mime.text import MIMEText

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "config.yaml")
# `## YYYY-MM-DD [HH:MM[:SS]] #標籤`
# 時間是「同一天第二則之後」才會出現的可選欄位（第一則沿用純日期，與舊檔完全相容）。
DATE_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})(?:\s+(\d{2}:\d{2}(?::\d{2})?))?\b\s*(.*)$")


def rid_for(date, tm):
    """紀錄 id：當天第一則＝日期本身；之後帶建立時間 → `2026-09-10-1435`。
    身分由「日期＋時間」決定，所以在檔案中間插入一則不會讓其他則改名——
    用出現順序編號（-2、-3）會，那會讓下一次同步把舊副本當成新紀錄再建一次，
    而規則不准刪，重複就永久留著。"""
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


def die(msg):
    import sys; sys.stderr.write("\033[31m✗ %s\033[0m\n" % msg); sys.exit(1)


def load_config():
    """極簡 YAML：頂層 key 與單層縮排子 key。夠用於 config.example.yaml 的結構。"""
    if not os.path.exists(CONFIG):
        die("找不到 config.yaml —— 先 `cp config.example.yaml config.yaml` 並填好。")
    cfg, section = {}, None
    for raw in open(CONFIG, encoding="utf-8"):
        line = raw.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith((" ", "\t")):
            k, _, v = line.partition(":")
            v = v.split(" #")[0].strip().strip('"').strip("'")
            if v == "":
                section = k.strip(); cfg[section] = {}
            else:
                cfg[k.strip()] = v; section = None
        elif section:
            k, _, v = line.strip().partition(":")
            cfg[section][k.strip()] = v.split(" #")[0].strip().strip('"').strip("'")
    return cfg


def project_id(cfg):
    pid = (cfg.get("firebase") or {}).get("project_id", "")
    if not pid or pid.startswith("your-"):
        die("config.yaml 的 firebase.project_id 還沒填。")
    return pid


def fb_base(cfg):
    return "https://firestore.googleapis.com/v1/projects/%s/databases/(default)/documents" % project_id(cfg)


# ── Firestore REST（用 gcloud 擁有者 token；進階功能需 `gcloud auth login`）──
def token():
    try:
        return subprocess.check_output(["gcloud", "auth", "print-access-token"],
                                       text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        die("取不到 gcloud token —— 進階功能需以專案擁有者執行 `gcloud auth login`。")


def fs_value(v):
    if isinstance(v, bool):  return {"booleanValue": v}
    if isinstance(v, int):   return {"integerValue": str(v)}
    if isinstance(v, list):  return {"arrayValue": {"values": [fs_value(x) for x in v]}}
    if isinstance(v, dict):  return {"mapValue": {"fields": {k: fs_value(x) for k, x in v.items()}}}
    return {"stringValue": "" if v is None else str(v)}

def fs_doc(fields): return {"fields": {k: fs_value(v) for k, v in fields.items()}}

def py_value(v):
    if "booleanValue" in v: return v["booleanValue"]
    if "integerValue" in v: return int(v["integerValue"])
    if "arrayValue" in v:   return [py_value(x) for x in v["arrayValue"].get("values", [])]
    return v.get("stringValue", "")

def http(method, base, path, tok, body=None):
    data = json.dumps(fs_doc(body)).encode() if body is not None else None
    req = urllib.request.Request(base + "/" + path, data=data, method=method,
                                 headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        if method == "GET" and e.code == 404: return {}
        die("Firestore %s %s：HTTP %s %s" % (method, path, e.code, e.read().decode("utf-8", "ignore")[:200]))


# ── 名冊 / 觀察檔 ──
def load_roster(cfg):
    """data/roster.csv：第一欄編號、第二欄姓名 → {id: name}（id 帶前綴，如 S-01）。"""
    path = os.path.join(ROOT, (cfg.get("records") or {}).get("roster_csv", "./data/roster.csv").lstrip("./"))
    prefix = cfg.get("id_prefix", "S")
    out = {}
    if not os.path.exists(path):
        return out
    for i, row in enumerate(csv.reader(open(path, encoding="utf-8-sig"))):
        if not row or i == 0 and not row[0].strip().isdigit() and "姓名" in ",".join(row):
            continue  # 跳過標頭
        if len(row) >= 2 and row[0].strip():
            num = re.sub(r"\D", "", row[0]).zfill(2)
            out["%s-%s" % (prefix, num)] = row[1].strip()
    return out


def students_dir(cfg):
    return os.path.join(ROOT, (cfg.get("records") or {}).get("students_dir", "./data/students").lstrip("./"))


def parse_blocks(path):
    """回傳 [{date,tags,body}]（只收真實 YYYY-MM-DD 區塊）。"""
    recs, cur, fm_done, in_fm = [], None, False, False
    for raw in open(path, encoding="utf-8"):
        line = raw.rstrip("\n")
        if not fm_done:
            if line.strip() == "---":
                if not in_fm: in_fm = True
                else: fm_done = True
                continue
            if in_fm: continue
            fm_done = True
        m = DATE_RE.match(line)
        if m:
            if cur: recs.append(cur)
            cur = {"date": m.group(1), "time": m.group(2),
                   "tags": re.findall(r"#\S+", m.group(3) or ""), "body": []}
        elif cur is not None:
            cur["body"].append(line)
    if cur: recs.append(cur)
    for r in recs: r["body"] = "\n".join(r["body"]).strip()
    return recs


# ── 寄信（SMTP 通用 / gws 進階）──
def mask(addr):
    try:
        l, d = addr.split("@", 1); return l[0] + "***@" + d
    except ValueError:
        return "***"


def send_email(cfg, to_list, subject, body):
    e = cfg.get("email") or {}
    if e.get("method") == "gws":
        subprocess.run(["gws", "gmail", "+send", "--to", ",".join(to_list),
                        "--subject", subject, "--body", body], check=True, stdout=subprocess.DEVNULL)
        return
    user = e.get("smtp_user", "")
    pw = os.environ.get("KIT_SMTP_APP_PASSWORD", "")
    if not user or not pw:
        die("SMTP 寄信需 config 的 email.smtp_user + 環境變數 KIT_SMTP_APP_PASSWORD（Gmail 應用程式密碼）。")
    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = subject, user, ", ".join(to_list)
    with smtplib.SMTP("smtp.gmail.com", 587) as s:
        s.starttls(context=ssl.create_default_context())
        s.login(user, pw)
        s.sendmail(user, to_list, msg.as_string())
