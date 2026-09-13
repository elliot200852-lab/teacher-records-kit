#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_config.py — 唯一的設定產生器：兩份 JSON 進，三個檔出。

  讀：config/kit.json（帳號、Firebase、Drive、語音）
      config/tabs.json（三個分頁要記什麼）
      config/business-groups.library.json（業務組庫，給網頁的「＋新增業務組」勾選）
      firestore.rules.tmpl（安全規則樣板）

  產：site/js/kit-config.js     window.KIT = {...}（分頁、業務組庫、擁有者、示範模式）
      site/js/firebase-config.js  window.FIREBASE_CONFIG / window.OWNER_EMAIL / window.OWNER_EMAILS（不是 module）
      firestore.rules            把樣板的 {{OWNER_EMAILS}} 換成擁有者信箱清單（owner_email＋co_owner_emails）

  這三個檔都被 .gitignore 擋住，而且**永遠由這支腳本產生**——AI 代理不准手寫。
  手寫規則檔一旦把 email 打錯，資料庫就變成誰都讀不到（或更糟：誰都讀得到）。

用法：
  python3 scripts/build_config.py            # 產生三個檔
  python3 scripts/build_config.py --check    # 只檢查設定合不合法，不寫任何檔
  python3 scripts/build_config.py --root DIR # 指定資料根目錄（測試用）
  python3 scripts/build_config.py --allow-placeholders   # 範本值只提醒不當錯誤（測試用）

設定裡還留著範本值（you@example.com、your-firebase-project-id、空白的 apiKey）時，
這支**直接 exit 1**——產得出檔卻連不上資料庫、規則鎖的是別人的信箱，那不是「裝好了」。

產生規則檔之後記得部署：
  firebase deploy --only firestore:rules --project <你的專案id>
"""
import os
import re
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib
import hostos

PLACEHOLDERS = ("you@example.com", "your-firebase-project-id", "YOUR_PROJECT")
# 嚴格的信箱字元集。**不要放寬它**：這個值會被插進 firestore.rules 的字串字面值裡，
# 舊的 `[^@\s]+` 會放行帶單引號的字串（`x'||true||'someone` 加上一個網域）——
# 貼進規則之後 isOwner() 變成恆真，整個資料庫誰都寫得進去。
# 下面 _rules_literal() 是第二道防線。
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def owner_email(kit):
    """設定裡的擁有者信箱，一律去空白＋轉小寫（規則、網頁設定三處要一模一樣）。"""
    return (kit.get("owner_email") or "").strip().lower()


def co_owner_emails(kit):
    """共同擁有者（選填清單）：跟 owner_email 一樣的權限，例如代管老師紀錄的第二個帳號。
    去空白、轉小寫、去重、剔除與 owner_email 重複者；不是清單就當空的（validate 會另外報錯）。"""
    raw = kit.get("co_owner_emails") or []
    if not isinstance(raw, list):
        return []
    out, seen = [], {owner_email(kit)}
    for e in raw:
        e = (str(e) if e is not None else "").strip().lower()
        if e and e not in seen:
            seen.add(e)
            out.append(e)
    return out


def owner_emails(kit):
    """規則與網頁真正用的名單＝owner_email 在前、co_owner_emails 在後。"""
    o = owner_email(kit)
    return ([o] if o else []) + co_owner_emails(kit)


def _rules_literal(s):
    """把字串跳脫成安全的規則字面值（樣板裡它被包在單引號裡）。

    縱深防禦：EMAIL_RE 已經擋掉引號與反斜線，這裡再跳脫一次，
    萬一以後有人放寬了那個正規表示式也不會產生一份「誰都是擁有者」的規則。
    """
    return json.dumps(s, ensure_ascii=False)[1:-1].replace("'", "\\'")


def _rules_list_literal(emails):
    """把信箱清單變成規則裡 `in [...]` 用的字面值（每個都走 _rules_literal）。"""
    return ", ".join("'%s'" % _rules_literal(e) for e in emails)


def _load_or_example(name):
    """有正式設定就用正式的，沒有就退回範本（--check 在全新的 repo 上也要能跑）。"""
    real = lib.rpath("config", name + ".json")
    if os.path.exists(real):
        return real, lib._load_json(real, "config/%s.json" % name, "重跑 `python3 scripts/setup.py`。")
    ex = lib.pkg_path("config", name + ".example.json")
    return ex, lib._load_json(ex, "config/%s.example.json" % name, "重新下載一份 kit。")


def validate(kit, tabs, problems, notes, allow_placeholders=False):
    """檢查設定的形狀。真正的錯誤進 problems（會 exit 1），可以先放著的進 notes。

    範本值（you@example.com、your-firebase-project-id、空白的 apiKey…）**預設算錯誤**：
    產得出三個檔、印一行「下一步：部署安全規則」然後 exit 0，會讓老師與 AI 以為裝好了，
    實際上那份規則鎖的是別人的信箱、網頁連不上任何資料庫。
    測試與預覽（build_preview.py）拿範本當形狀用，那種情境才加 `--allow-placeholders`。
    """
    def ph(msg, fix):
        """範本值：預設進 problems（exit 1），--allow-placeholders 時降成提醒。"""
        if allow_placeholders:
            notes.append(msg)
        else:
            problems.append((msg, fix))

    m = (kit.get("mode") or "cloud").strip().lower()
    if m not in lib.MODES:
        problems.append(("config/kit.json 的 mode 只能是 cloud 或 local（現在是 %r）" % m,
                         "cloud＝自己的 Firebase 專案＋手機網頁；local＝只在這台電腦的 data/*.md，"
                         "完全不碰雲端。改完重跑 `python3 scripts/setup.py`。"))
        m = "cloud"
    local = m == "local"

    email = (kit.get("owner_email") or "").strip().lower()
    if not email:
        problems.append(("config/kit.json 沒有 owner_email", "填你要用來登入的 Google 信箱。"))
    elif not EMAIL_RE.match(email):
        problems.append(("owner_email 看起來不是信箱：%s" % email,
                         "格式要像 someone@gmail.com（只能有英數與 . _ % + -，不能有引號）。"))
    elif email in PLACEHOLDERS:
        ph("owner_email 還是範本值（%s）——正式安裝要換成你自己的信箱。" % email,
           "把 config/kit.json 的 owner_email 換成你要用來登入的 Google 信箱，再跑一次"
           "（測試或 CI 只想驗形狀的話加 --allow-placeholders）。")
    co_raw = kit.get("co_owner_emails")
    if co_raw is not None and not isinstance(co_raw, list):
        problems.append(("co_owner_emails 要是清單（陣列）", '寫成 ["a@gmail.com", "b@gmail.com"]；沒有共同擁有者就寫 []。'))
    else:
        for e in (co_raw or []):
            e = (str(e) if e is not None else "").strip().lower()
            if not e:
                continue
            if not EMAIL_RE.match(e):
                problems.append(("co_owner_emails 裡有一個看起來不是信箱：%s" % e,
                                 "格式要像 someone@gmail.com（只能有英數與 . _ % + -，不能有引號）。"))
            elif e in PLACEHOLDERS:
                ph("co_owner_emails 裡還有範本值（%s）。" % e, "刪掉它或換成真的信箱。")

    # 本機模式沒有 Firebase 這件事：那六個值一個都不檢查（老師根本沒被問過），
    # 而且**不產** firestore.rules 與 firebase-config.js——產一份鎖著誰的規則檔出來，
    # 只會讓人以為有個資料庫在那裡。
    fb = kit.get("firebase") or {}
    if local:
        notes.append("本機模式：不檢查 firebase 那六個值，也不會產生 firestore.rules／firebase-config.js。")
        # 從 cloud 改成 local 的話，上一次產生的那幾個檔還躺在原地。**不自動刪**
        # （那是老師哪天要改回雲端時的東西，而且刪檔這種事不該是產生器順手做的），
        # 但一定要說一聲——不然他會以為「改成本機了，那份鎖著我信箱的規則檔也不見了」。
        stale = [rel for rel in ("firestore.rules", "storage.rules",
                                 os.path.join("site", "js", "firebase-config.js"))
                 if os.path.exists(lib.rpath(rel))]
        if stale:
            notes.append("這幾個是上次雲端模式留下來的，本機模式用不到（要不要刪由你決定，"
                         "改回雲端會重新產生）：%s" % "、".join(stale))
    else:
        for k in ("project_id", "api_key", "auth_domain", "storage_bucket",
                  "messaging_sender_id", "app_id"):
            if k not in fb:
                problems.append(("config/kit.json 的 firebase 少了 %s" % k,
                                 "六個值都在 Firebase Console → 專案設定 → 一般 → 你的應用程式。"))
            elif k == "auth_domain" and not str(fb.get(k) or "").strip():
                continue        # 留空是合法的：下面會自動填 <專案id>.web.app
            elif not str(fb.get(k) or "").strip() or str(fb.get(k)).startswith(PLACEHOLDERS[1]):
                ph("firebase.%s 還沒填或還是範本值——網頁會連不上你的資料庫。" % k,
                   "到 Firebase Console → 專案設定 → 一般 → 你的應用程式 → SDK 設定與配置，"
                   "把那六個值填進 config/kit.json 的 firebase 區塊"
                   "（測試或 CI 只想驗形狀的話加 --allow-placeholders）。")

    # 無頭交辦（選用）
    h = lib.headless_cfg(kit)
    if h["enabled"]:
        if local:
            problems.append(("本機模式不能開無頭交辦（headless.enabled）",
                             "LINE 的訊息要有一個收得到 webhook 的地方，那就是雲端。"
                             "要用無頭交辦就把 mode 改成 cloud 重跑安裝；只想留在本機就把 "
                             "headless.enabled 改成 false。"))
        if h["tool"] not in lib.HEADLESS_TOOLS:
            problems.append(("headless.tool 目前只支援 line（現在是 %r）" % h["tool"],
                             "改成 \"line\"。這個欄位留著是為了以後接別的工具。"))
        if h["agent"] not in hostos.AGENT_ORDER:
            problems.append(("headless.agent 要是 claude、codex 或 gemini（現在是 %r）" % h["agent"],
                             "填那台電腦上裝好、而且登入過的那一支；"
                             "`python3 scripts/doctor.py` 會告訴你找得到哪幾支。"))
        if h["timeout_sec"] < 60:
            problems.append(("headless.timeout_sec 太短（%d 秒）" % h["timeout_sec"],
                             "一則語音交辦光是轉逐字稿就可能要好幾分鐘；預設 1800（30 分鐘）。"))
        if not h["line"]["owner_user_id"]:
            notes.append("headless.line.owner_user_id 還是空的——配對完成前，relay 會把配對碼回給"
                         "任何傳訊息給你的人。拿配對碼：手機傳一句話給你的官方帳號，"
                         "或在電腦上跑 `python3 scripts/headless.py --pair`。")

    drive = kit.get("drive") or {}
    mode = drive.get("mode", "desktop")
    if mode not in ("desktop", "gws"):
        problems.append(("drive.mode 只能是 desktop 或 gws（現在是 %r）" % mode,
                         "不確定就用 desktop：把備份 zip 複製進 Google 雲端硬碟桌面程式的同步夾。"))
    if mode == "gws" and not (drive.get("backup_folder_id") or "").strip():
        problems.append(("drive.mode 是 gws 但 backup_folder_id 是空的",
                         "打開那個 Drive 資料夾，網址 .../folders/XXXX 的 XXXX 就是 id。"))

    for tab in ("students", "courses", "business"):
        if tab not in tabs:
            problems.append(("config/tabs.json 少了 %s 區塊" % tab, "重跑 `python3 scripts/setup.py`。"))
            continue
        h = (tabs[tab].get("help") or {})
        for key in ("what", "prepare", "ai"):
            if not str(h.get(key) or "").strip():
                notes.append("tabs.%s.help.%s 是空的——網頁那一頁的說明框會少一行。" % (tab, key))

    # 課程 id 會變成資料夾名（data/courses/<id>/）與雲端文件 id，跟業務組同一套規矩：
    # 沒擋字元集的話 `../../oops` 這種 id 會讓記錄檔寫到 data/ 外面去。
    seen_c = set()
    for c in ((tabs.get("courses") or {}).get("list") or []):
        if not isinstance(c, dict):
            problems.append(("課程要是物件（現在是 %r）" % (c,),
                             "每一門長成 {\"id\":\"main-block\",\"title\":\"主課程\"}。"))
            continue
        cid = (c.get("id") or "").strip()
        if not cid:
            problems.append(("課程少了 id", "每一門課都要有英數 id（會變成資料夾名與雲端文件 id）。"))
        elif not re.match(r"^[A-Za-z0-9_-]+$", cid):
            problems.append(("課程 id 只能用英數與 - _（現在是 %r）" % cid,
                             "中文請寫在 title，id 另外取一個英文短名（例如 main-block）。"))
        elif cid in seen_c:
            problems.append(("課程 id 重複：%s" % cid, "兩門課不能同名，改掉其中一個。"))
        seen_c.add(cid)

    seen = set()
    for g in ((tabs.get("business") or {}).get("groups") or []):
        gid = (g.get("id") or "").strip()
        if not gid:
            problems.append(("業務組少了 id", "每一組都要有英數 id（會變成資料夾名與雲端文件 id）。"))
        elif not re.match(r"^[A-Za-z0-9_-]+$", gid):
            problems.append(("業務組 id 只能用英數與 - _（現在是 %r）" % gid,
                             "中文請寫在 label，id 另外取一個英文短名。"))
        elif gid in seen:
            problems.append(("業務組 id 重複：%s" % gid, "兩組不能同名，改掉其中一個。"))
        seen.add(gid)

    # 學生記錄類型（stream）：id 會變成本機檔名與雲端文件的 stream 欄位，錯了就分不了流。
    st = tabs.get("students") or {}
    if "streams" in st and not isinstance(st.get("streams"), list):
        problems.append(("config/tabs.json 的 students.streams 要是一個陣列",
                         "形狀是 [{\"id\":\"homeroom\",\"label\":…,\"scope\":\"class\"}]；"
                         "一種都沒勾就寫 []。"))
    else:
        seen_s = set()
        for s in (st.get("streams") or []):
            if not isinstance(s, dict):
                problems.append(("學生記錄類型要是物件（現在是 %r）" % (s,),
                                 "每一種長成 {\"id\":…,\"label\":…,\"scope\":\"class\"|\"case\"}。"))
                continue
            sid = (s.get("id") or "").strip()
            if not sid:
                problems.append(("學生記錄類型少了 id",
                                 "每一種都要有英數 id（會變成本機檔名 data/students/<代號>/<id>.md）。"))
                continue
            if not re.match(r"^[A-Za-z0-9_-]+$", sid):
                problems.append(("學生記錄類型 id 只能用英數與 - _（現在是 %r）" % sid,
                                 "中文請寫在 label，id 另外取一個英文短名。"))
            elif sid in seen_s:
                problems.append(("學生記錄類型 id 重複：%s" % sid,
                                 "兩種類型不能同名，改掉其中一個（同名會寫進同一個本機檔）。"))
            seen_s.add(sid)
            scope = s.get("scope") or "class"
            if scope not in lib.SCOPES:
                problems.append(("學生記錄類型 %s 的 scope 只能是 class 或 case（現在是 %r）"
                                 % (sid or "?", scope),
                                 "class＝名冊每一位學生都在裡面；case＝只有 data/roster.csv "
                                 "第三欄列入的學生。"))


def build_kit_js(kit, tabs, library, stream_library):
    h = lib.headless_cfg(kit)
    payload = {
        "demo": False,
        "version": lib.version(),
        # 資料庫模式。網頁只有 cloud 模式才存在，但這個值一起帶著走：
        # 離線預覽與未來的狀態列都靠它知道「這台裝的是哪一種」。
        "mode": lib.mode(kit),
        # 無頭交辦：網頁不需要金鑰，只需要知道「有沒有開」與「還沒配對」。
        "headless": {"enabled": lib.headless_on(kit), "tool": h["tool"],
                     "paired": bool(h["line"]["owner_user_id"])},
        "ownerEmail": owner_email(kit),
        "ownerEmails": owner_emails(kit),
        "idPrefix": lib.id_prefix(kit),
        "tabs": {k: tabs.get(k, {}) for k in ("students", "courses", "business")},
        # 三個垂直方案：這位老師比較像哪一種（安裝時問的），與期末的預設報告格式。
        "vertical": tabs.get("vertical", ""),
        "reportFormat": tabs.get("reportFormat", ""),
        # 期末「產生素材」按鈕的格式清單與方案清單（正本＝config/ 底下那兩個檔）。
        "reportFormats": (lib.load_report_formats().get("formats") or []),
        "verticals": (lib.load_verticals().get("verticals") or []),
        "businessLibrary": [g for g in (library.get("groups") or []) if not g.get("open")],
        # 網頁「＋ 新增記錄類型」的可選清單。open:true 的那筆是安裝時的開放選項
        # （「我的類型不在清單裡」），不是真的類型，不給網頁。
        "studentStreamLibrary": [s for s in (stream_library.get("streams") or [])
                                 if not s.get("open")],
    }
    return ("/* 由 scripts/build_config.py 產生——不要手改，改 config/kit.json 或\n"
            "   config/tabs.json 之後重跑 `python3 scripts/build_config.py`。\n"
            "   本檔含你的信箱，已被 .gitignore 擋住。傳統 <script src> 載入，不是 module。 */\n"
            "window.KIT = " + json.dumps(payload, ensure_ascii=False, indent=2) + ";\n")


def build_firebase_js(kit):
    fb = kit.get("firebase") or {}
    cfg = {
        "apiKey": fb.get("api_key", ""),
        # 預設 `<專案id>.web.app`＝這份 kit 實際部署的網址（Firebase Hosting）。
        # Console 給的 `.firebaseapp.com` 跟網頁不同源，iOS Safari 的跨網域儲存分區
        # 會讓 Google 登入一直跳回未登入（INSTALL.md 那個坑）。填了就照填的。
        "authDomain": (fb.get("auth_domain") or "").strip()
                      or ("%s.web.app" % fb.get("project_id", "")),
        "projectId": fb.get("project_id", ""),
        "storageBucket": fb.get("storage_bucket", ""),
        "messagingSenderId": str(fb.get("messaging_sender_id", "")),
        "appId": fb.get("app_id", ""),
    }
    return ("/* 由 scripts/build_config.py 產生——不要手改。含你的 Firebase 設定，已被 .gitignore 擋住。\n"
            "   不是 module：dashboard.html 用傳統 <script src> 載入它。\n"
            "   iPhone 上登不進去的話，把 kit.json 的 firebase.auth_domain 改成你實際打開網頁的網域，\n"
            "   再重跑一次這支腳本。 */\n"
            "window.FIREBASE_CONFIG = " + json.dumps(cfg, ensure_ascii=False, indent=2) + ";\n"
            "window.OWNER_EMAIL = " + json.dumps(owner_email(kit), ensure_ascii=False) + ";\n"
            "window.OWNER_EMAILS = " + json.dumps(owner_emails(kit), ensure_ascii=False) + ";\n")


def build_rules(kit):
    tmpl_path = lib.pkg_path("firestore.rules.tmpl")
    if not os.path.exists(tmpl_path):
        lib.die("找不到安全規則樣板 firestore.rules.tmpl：%s" % tmpl_path,
                "重新下載一份 kit（這個檔跟著程式碼走）。")
    with open(tmpl_path, encoding="utf-8") as f:
        tmpl = f.read()
    if "{{OWNER_EMAILS}}" not in tmpl:
        lib.die("firestore.rules.tmpl 裡找不到 {{OWNER_EMAILS}} 佔位符。",
                "樣板被改壞了，重新下載一份 kit。")
    return tmpl.replace("{{OWNER_EMAILS}}", _rules_list_literal(owner_emails(kit)))


HEADLESS_STORAGE_BLOCK = """
    // ── 無頭交辦的收件匣（docs/HEADLESS.md）──
    // relay 走 Admin SDK 寫進來（伺服器憑證不受規則管）；這條只管「人」：
    // 只有擁有者本人下載得到自己的語音訊息。
    match /headless-inbox/{file} {
      allow read, write: if isOwner();
    }
"""


def build_storage_rules(kit):
    """Cloud Storage 規則。無頭交辦沒開的話產出來的是一份「全部 deny」——
    這樣老師不小心開了 Storage 也不會有一個誰都寫得進去的 bucket。"""
    tmpl_path = lib.pkg_path("storage.rules.tmpl")
    if not os.path.exists(tmpl_path):
        lib.die("找不到 Storage 規則樣板 storage.rules.tmpl：%s" % tmpl_path,
                "重新下載一份 kit（這個檔跟著程式碼走）。")
    with open(tmpl_path, encoding="utf-8") as f:
        tmpl = f.read()
    for ph_ in ("{{OWNER_EMAILS}}", "{{HEADLESS_BLOCK}}"):
        if ph_ not in tmpl:
            lib.die("storage.rules.tmpl 裡找不到 %s 佔位符。" % ph_,
                    "樣板被改壞了，重新下載一份 kit。")
    return (tmpl.replace("{{OWNER_EMAILS}}", _rules_list_literal(owner_emails(kit)))
                .replace("{{HEADLESS_BLOCK}}", HEADLESS_STORAGE_BLOCK if lib.headless_on(kit) else ""))


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return path


def main():
    ap = argparse.ArgumentParser(
        description="從 config/kit.json ＋ config/tabs.json 產生網頁設定與安全規則",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="產生的三個檔：site/js/kit-config.js、site/js/firebase-config.js、firestore.rules")
    ap.add_argument("--check", action="store_true", help="只檢查設定合不合法，不寫任何檔")
    ap.add_argument("--allow-placeholders", action="store_true",
                    help="範本值（you@example.com、your-firebase-project-id、空白的金鑰）降成提醒，"
                         "不當成錯誤（測試與離線預覽用；正式安裝不要加）")
    ap.add_argument("--quiet", action="store_true", help="只在出錯時輸出")
    lib.add_root_arg(ap)
    a = ap.parse_args()
    lib.apply_root(a)

    kit_path, kit = _load_or_example("kit")
    tabs_path, tabs = _load_or_example("tabs")
    library = lib.load_library()
    stream_library = lib.load_stream_library()

    problems, notes = [], []
    validate(kit, tabs, problems, notes, allow_placeholders=a.allow_placeholders)

    if problems:
        for msg, fix in problems:
            lib.err(msg, fix)
        sys.exit(1)

    if a.check:
        if not a.quiet:
            lib.ok("設定檢查通過（版本 %s；%s、%s）"
                   % (lib.version(), os.path.relpath(kit_path, lib.root()),
                      os.path.relpath(tabs_path, lib.root())))
            h = lib.headless_cfg(kit)
            print("  資料庫模式：%s" % ("local（只在這台電腦，沒有雲端也沒有網頁）"
                                        if lib.is_local(kit) else
                                        "cloud（自己的 Firebase 專案＋手機網頁）"))
            print("  無頭交辦：%s" % ("開（%s → %s%s）"
                                      % (h["tool"], h["agent"] or "（還沒選代理）",
                                         "" if h["line"]["owner_user_id"] else "，還沒配對")
                                      if lib.headless_on(kit) else "關"))
            streams = (tabs.get("students") or {}).get("streams")
            groups = (tabs.get("business") or {}).get("groups") or []
            print("  分頁：學生 %s／課程 %s／業務 %s" % (
                "開" if tabs.get("students", {}).get("enabled") else "關",
                "開" if tabs.get("courses", {}).get("enabled") else "關",
                "開" if tabs.get("business", {}).get("enabled") else "關"))
            if streams is None:
                print("  學生記錄類型：（舊版設定沒有 streams，當成只有「導師班級學生紀錄」一種）")
            else:
                print("  學生記錄類型（勾了 %d 種）：%s" % (
                    len(streams),
                    "、".join("%s／%s〔%s〕" % (s.get("id"), s.get("label") or s.get("id"),
                                                s.get("scope") or "class")
                              for s in streams) or "（一種都沒勾，學生分頁不會有紀錄）"))
            print("  業務組（勾了 %d 組）：%s" % (
                len(groups),
                "、".join("%s／%s" % (g.get("id"), g.get("label") or g.get("id"))
                          for g in groups) or "（一組都沒勾）"))
            for n in notes:
                lib.warn(n)
        return

    local = lib.is_local(kit)
    outs = [write(lib.rpath("site", "js", "kit-config.js"),
                  build_kit_js(kit, tabs, library, stream_library))]
    if not local:
        outs.append(write(lib.rpath("site", "js", "firebase-config.js"), build_firebase_js(kit)))
        outs.append(write(lib.rpath("firestore.rules"), build_rules(kit)))
        outs.append(write(lib.rpath("storage.rules"), build_storage_rules(kit)))
    if not a.quiet:
        for p in outs:
            lib.ok("產生 %s" % os.path.relpath(p, lib.root()))
        for n in notes:
            lib.warn(n)
        if local:
            print("\n本機模式：沒有要部署的東西。紀錄就在 data/ 底下，"
                  "備份跑 `%s scripts/backup.py`。" % lib.PY)
            print("  哪天想改用手機網頁：把 config/kit.json 的 mode 改成 cloud，"
                  "再跑一次 `%s scripts/setup.py`（既有紀錄不會動，第一次同步會全部推上去）。" % lib.PY)
            return
        pid = (kit.get("firebase") or {}).get("project_id") or "<你的專案id>"
        print("\n下一步：部署安全規則（沒做這一步，網頁會讀不到資料）")
        print("  firebase deploy --only firestore:rules --project %s" % pid)
        if lib.headless_on(kit):
            print("\n無頭交辦開著，還要多部署兩樣（細節見 docs/HEADLESS.md）：")
            print("  firebase deploy --only storage --project %s          # Storage 規則（語音存放處）" % pid)
            print("  firebase deploy --only functions:line-relay --project %s   # LINE 收件端" % pid)
        print("\n⚠️ 一律用 `--only`，不要跑沒有參數的 `firebase deploy`——"
              "那會連 functions 與 storage 一起送，沒開那兩個產品的專案會整個失敗。")


if __name__ == "__main__":
    main()
