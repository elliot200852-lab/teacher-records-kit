#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
export_records.py — 把「全部學生的觀察紀錄 + 全班觀察」從 Firestore 匯出，
供期末評量取材（可直接餵給 AI 逐生產出評量草稿），或做本地備份。

單租戶：資料就在你自己的 Firebase 專案頂層（students/、roster/main、class-observations）。
專案 id 預設讀 config.yaml 的 firebase.project_id，也可用 --project 覆寫。
讀取走 gcloud 現用帳號（需以專案擁有者 `gcloud auth login`）。

用法：
  python3 scripts/export_records.py                       # Markdown 印到畫面
  python3 scripts/export_records.py --out ~/records.md    # 寫成 Markdown 檔
  python3 scripts/export_records.py --json                # 結構化 JSON（給程式用）
  python3 scripts/export_records.py --by-tag              # 依題材（標籤）分組
  python3 scripts/export_records.py --id S-01             # 只抓某一位學生
  python3 scripts/export_records.py --split ~/backup      # 備份：每生一資料夾（含 roster.md）
  python3 scripts/export_records.py --project my-proj     # 覆寫 config 的專案 id
  python3 scripts/export_records.py --class-code 1A       # 顯示用班級標籤（選用）
"""
import sys, os, json, subprocess, urllib.request, urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib  # 共用：讀 config.yaml、取 token


def die(m): sys.stderr.write("ERROR: " + m + "\n"); sys.exit(1)


def resolve_project(args):
    if "--project" in args:
        return args[args.index("--project") + 1]
    cfg = lib.load_config()                 # 找不到 config.yaml 會在此提示先 cp 範本
    return lib.project_id(cfg)               # 未填 firebase.project_id 也會提示


def token():
    try:
        return subprocess.check_output(["gcloud", "auth", "print-access-token"],
                                       text=True, stderr=subprocess.DEVNULL).strip()
    except Exception as e:
        die(f"取不到 gcloud token（先以專案擁有者 `gcloud auth login`）：{e}")


def _get(url, tok):
    r = urllib.request.Request(url, headers={"Authorization": f"Bearer {tok}"})
    try:
        return json.loads(urllib.request.urlopen(r).read())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return {}
        die(f"GET {url} → {e.code}: {e.read().decode()[:200]}")


def dec(v):
    if v is None: return None
    for k, f in (("stringValue", str), ("booleanValue", bool), ("timestampValue", str), ("nullValue", lambda x: None)):
        if k in v: return f(v[k])
    if "integerValue" in v: return int(v["integerValue"])
    if "doubleValue" in v: return float(v["doubleValue"])
    if "arrayValue" in v: return [dec(x) for x in v["arrayValue"].get("values", [])]
    if "mapValue" in v: return {k: dec(x) for k, x in v["mapValue"].get("fields", {}).items()}
    return None


def fields(doc): return {k: dec(x) for k, x in (doc.get("fields") or {}).items()}


def list_docs(base, path, tok):
    out, tokp = [], ""
    while True:
        url = f"{base}/{path}?pageSize=300" + (f"&pageToken={tokp}" if tokp else "")
        res = _get(url, tok)
        for d in res.get("documents", []):
            out.append((d["name"].split("/")[-1], fields(d)))
        tokp = res.get("nextPageToken")
        if not tokp: break
    return out


def clean_tags(tags):
    # 讀取端也保險去重／去多餘 #（就算歷史資料有 ##重複也顯示乾淨）
    seen, out = set(), []
    for t in (tags or []):
        t = ("#" + str(t).lstrip("#").strip()) if str(t).strip() else ""
        if t and t != "#" and t not in seen:
            seen.add(t); out.append(t)
    return out


def collect(base, tok):
    roster = fields(_get(f"{base}/roster/main", tok))
    name_by_id = {s.get("id"): s.get("name") for s in (roster.get("students") or [])}
    ids = list(name_by_id.keys())
    if not ids:
        ids = [sid for sid, _ in list_docs(base, "students", tok)]
    students = []
    for sid in sorted(ids):
        recs = [f for _, f in list_docs(base, f"students/{sid}/records", tok)]
        recs.sort(key=lambda r: r.get("date") or "")
        students.append({"id": sid, "name": name_by_id.get(sid, ""), "records": recs})
    class_obs = [f for _, f in list_docs(base, "class-observations", tok)]
    class_obs.sort(key=lambda r: r.get("date") or "")
    return {"students": students, "class_observations": class_obs}


def label(cc, sid): return f"{cc + '-' if cc else ''}{sid}"


def to_md(data, cc=""):
    total = sum(len(s["records"]) for s in data["students"])
    L = [f"# 學生觀察紀錄匯出{('：' + cc) if cc else ''}",
         f"> {len(data['students'])} 位學生、{total} 則學生紀錄、{len(data['class_observations'])} 則全班觀察。",
         "> 此檔供撰寫期末評量取材——每位學生一段，含歷次觀察（日期＋標籤＋內容）。", ""]
    if data["class_observations"]:
        L.append("## 全班觀察")
        for r in data["class_observations"]:
            tg = " ".join(clean_tags(r.get("tags")))
            L.append(f"- **{r.get('date','')}** {tg}\n  {r.get('body','').strip()}")
        L.append("")
    L.append("## 學生逐一")
    for s in data["students"]:
        L.append(f"\n### {label(cc, s['id'])}　{s['name']}")
        if not s["records"]:
            L.append("_（尚無紀錄）_"); continue
        for r in s["records"]:
            tg = " ".join(clean_tags(r.get("tags")))
            L.append(f"- **{r.get('date','')}** {tg}\n  {r.get('body','').strip()}")
    return "\n".join(L) + "\n"


def to_md_by_tag(data, cc=""):
    """依題材（標籤）分組：每位學生底下把觀察按類別歸類，供逐題材撰寫評量。"""
    L = [f"# 依題材分類的觀察（供期末評量逐題材論述）{('：' + cc) if cc else ''}",
         "> 每位學生底下按題材（標籤）歸類；一則多標籤者會出現在各題材下；無標籤者歸「（未分類）」。", ""]
    for s in data["students"]:
        L.append(f"### {label(cc, s['id'])}　{s['name']}")
        if not s["records"]:
            L.append("_（尚無紀錄）_\n"); continue
        buckets = {}
        for r in s["records"]:
            for t in (clean_tags(r.get("tags")) or ["（未分類）"]):
                buckets.setdefault(t, []).append(r)
        for t in sorted(buckets, key=lambda x: (x == "（未分類）", x)):
            L.append(f"- **{t}**（{len(buckets[t])} 則）")
            for r in buckets[t]:
                L.append(f"    - {r.get('date','')}：{r.get('body','').strip()}")
        L.append("")
    return "\n".join(L) + "\n"


def write_split(data, base_dir, cc=""):
    """備份模式：每位學生一個資料夾 observations.md（去識別化）+ roster.md（代號↔姓名）。
    一次性從 Firestore 匯出快照，供本地備份／期末取材。回傳 (檔數, 紀錄數)。"""
    os.makedirs(base_dir, exist_ok=True)
    rl = ["# 代號↔姓名（本地備份，含真名——勿進共享 repo、勿上傳）", ""]
    for s in data["students"]:
        rl.append(f"- {label(cc, s['id'])}　{s['name']}")
    open(os.path.join(base_dir, "roster.md"), "w", encoding="utf-8").write("\n".join(rl) + "\n")
    nf = nr = 0
    for s in data["students"]:
        sd = os.path.join(base_dir, label(cc, s["id"])); os.makedirs(sd, exist_ok=True)
        L = [f"# {label(cc, s['id'])} 觀察紀錄（Firestore 備份·去識別化）", ""]
        for r in s["records"]:
            tg = " ".join(clean_tags(r.get("tags")))
            L.append(f"## {r.get('date','')} {tg}".rstrip())
            L.append((r.get("body", "") or "").strip()); L.append(""); nr += 1
        open(os.path.join(sd, "observations.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
        nf += 1
    if data["class_observations"]:
        L = ["# 全班觀察（Firestore 備份）", ""]
        for r in data["class_observations"]:
            tg = " ".join(clean_tags(r.get("tags")))
            L.append(f"## {r.get('date','')} {tg}".rstrip()); L.append((r.get("body", "") or "").strip()); L.append("")
        open(os.path.join(base_dir, "class-observations.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    return nf, nr


def main():
    args = sys.argv[1:]
    proj = resolve_project(args)
    base = f"https://firestore.googleapis.com/v1/projects/{proj}/databases/(default)/documents"
    tok = token()
    cc = args[args.index("--class-code") + 1] if "--class-code" in args else ""
    data = collect(base, tok)
    if "--id" in args:                          # 只抓某一位學生（如 --id S-01）
        want = args[args.index("--id") + 1]
        data["students"] = [s for s in data["students"] if s["id"] == want]
    if "--split" in args:                       # 備份模式：每生一資料夾寫進 DIR
        nf, nr = write_split(data, args[args.index("--split") + 1], cc)
        print(f"✓ 備份完成 → {args[args.index('--split') + 1]}（{nf} 位學生檔、{nr} 則紀錄、含 roster.md）")
        return
    if "--json" in args:
        text = json.dumps(data, ensure_ascii=False, indent=2)
    elif "--by-tag" in args:
        text = to_md_by_tag(data, cc)
    else:
        text = to_md(data, cc)
    if "--out" in args:
        out = args[args.index("--out") + 1]
        open(out, "w", encoding="utf-8").write(text); print(f"✓ 已寫出 {out}")
    else:
        print(text)


if __name__ == "__main__":
    main()
