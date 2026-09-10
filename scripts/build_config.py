#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_config.py — 唯一的設定產生器：兩份 JSON 進，三個檔出。

  讀：config/kit.json（帳號、Firebase、Drive、語音）
      config/tabs.json（三個分頁要記什麼）
      config/business-groups.library.json（業務組庫，給網頁的「＋新增業務組」勾選）
      firestore.rules.tmpl（安全規則樣板）

  產：site/js/kit-config.js     window.KIT = {...}（分頁、業務組庫、擁有者、示範模式）
      site/js/firebase-config.js  window.FIREBASE_CONFIG / window.OWNER_EMAIL（不是 module）
      firestore.rules            把樣板的 {{OWNER_EMAIL}} 換成你的信箱

  這三個檔都被 .gitignore 擋住，而且**永遠由這支腳本產生**——AI 代理不准手寫。
  手寫規則檔一旦把 email 打錯，資料庫就變成誰都讀不到（或更糟：誰都讀得到）。

用法：
  python3 scripts/build_config.py            # 產生三個檔
  python3 scripts/build_config.py --check    # 只檢查設定合不合法，不寫任何檔
  python3 scripts/build_config.py --root DIR # 指定資料根目錄（測試用）

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

PLACEHOLDERS = ("you@example.com", "your-firebase-project-id", "YOUR_PROJECT")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _load_or_example(name):
    """有正式設定就用正式的，沒有就退回範本（--check 在全新的 repo 上也要能跑）。"""
    real = lib.rpath("config", name + ".json")
    if os.path.exists(real):
        return real, lib._load_json(real, "config/%s.json" % name, "重跑 `python3 scripts/setup.py`。")
    ex = lib.pkg_path("config", name + ".example.json")
    return ex, lib._load_json(ex, "config/%s.example.json" % name, "重新下載一份 kit。")


def validate(kit, tabs, problems, notes):
    """檢查設定的形狀。真正的錯誤進 problems（會 exit 1），可以先放著的進 notes。"""
    email = (kit.get("owner_email") or "").strip()
    if not email:
        problems.append(("config/kit.json 沒有 owner_email", "填你要用來登入的 Google 信箱。"))
    elif not EMAIL_RE.match(email):
        problems.append(("owner_email 看起來不是信箱：%s" % email, "格式要像 someone@gmail.com。"))
    elif email in PLACEHOLDERS:
        notes.append("owner_email 還是範本值（%s）——正式安裝要換成你自己的信箱。" % email)

    fb = kit.get("firebase") or {}
    for k in ("project_id", "api_key", "auth_domain", "storage_bucket",
              "messaging_sender_id", "app_id"):
        if k not in fb:
            problems.append(("config/kit.json 的 firebase 少了 %s" % k,
                             "六個值都在 Firebase Console → 專案設定 → 一般 → 你的應用程式。"))
        elif not str(fb.get(k) or "").strip() or str(fb.get(k)).startswith(PLACEHOLDERS[1]):
            notes.append("firebase.%s 還沒填或還是範本值——網頁會連不上你的資料庫。" % k)

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


def build_kit_js(kit, tabs, library):
    payload = {
        "demo": False,
        "ownerEmail": kit.get("owner_email", ""),
        "idPrefix": lib.id_prefix(kit) + "-",
        "tabs": {k: tabs.get(k, {}) for k in ("students", "courses", "business")},
        "businessLibrary": [g for g in (library.get("groups") or []) if not g.get("open")],
    }
    return ("/* 由 scripts/build_config.py 產生——不要手改，改 config/kit.json 或\n"
            "   config/tabs.json 之後重跑 `python3 scripts/build_config.py`。\n"
            "   本檔含你的信箱，已被 .gitignore 擋住。傳統 <script src> 載入，不是 module。 */\n"
            "window.KIT = " + json.dumps(payload, ensure_ascii=False, indent=2) + ";\n")


def build_firebase_js(kit):
    fb = kit.get("firebase") or {}
    cfg = {
        "apiKey": fb.get("api_key", ""),
        "authDomain": fb.get("auth_domain") or ("%s.firebaseapp.com" % fb.get("project_id", "")),
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
            "window.OWNER_EMAIL = " + json.dumps(kit.get("owner_email", ""), ensure_ascii=False) + ";\n")


def build_rules(kit):
    tmpl_path = lib.pkg_path("firestore.rules.tmpl")
    if not os.path.exists(tmpl_path):
        lib.die("找不到安全規則樣板 firestore.rules.tmpl：%s" % tmpl_path,
                "重新下載一份 kit（這個檔跟著程式碼走）。")
    with open(tmpl_path, encoding="utf-8") as f:
        tmpl = f.read()
    if "{{OWNER_EMAIL}}" not in tmpl:
        lib.die("firestore.rules.tmpl 裡找不到 {{OWNER_EMAIL}} 佔位符。",
                "樣板被改壞了，重新下載一份 kit。")
    return tmpl.replace("{{OWNER_EMAIL}}", kit.get("owner_email", ""))


def write(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    return path


def main():
    ap = argparse.ArgumentParser(
        description="從 config/kit.json ＋ config/tabs.json 產生網頁設定與安全規則",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="產生的三個檔：site/js/kit-config.js、site/js/firebase-config.js、firestore.rules")
    ap.add_argument("--check", action="store_true", help="只檢查設定合不合法，不寫任何檔")
    ap.add_argument("--quiet", action="store_true", help="只在出錯時輸出")
    lib.add_root_arg(ap)
    a = ap.parse_args()
    lib.apply_root(a)

    kit_path, kit = _load_or_example("kit")
    tabs_path, tabs = _load_or_example("tabs")
    library = lib.load_library()

    problems, notes = [], []
    validate(kit, tabs, problems, notes)

    if problems:
        for msg, fix in problems:
            lib.err(msg, fix)
        sys.exit(1)

    if a.check:
        if not a.quiet:
            lib.ok("設定檢查通過（%s、%s）" % (os.path.relpath(kit_path, lib.root()),
                                              os.path.relpath(tabs_path, lib.root())))
            print("  分頁：學生 %s／課程 %s／業務 %s（%d 組）" % (
                "開" if tabs.get("students", {}).get("enabled") else "關",
                "開" if tabs.get("courses", {}).get("enabled") else "關",
                "開" if tabs.get("business", {}).get("enabled") else "關",
                len((tabs.get("business") or {}).get("groups") or [])))
            for n in notes:
                lib.warn(n)
        return

    outs = [
        write(lib.rpath("site", "js", "kit-config.js"), build_kit_js(kit, tabs, library)),
        write(lib.rpath("site", "js", "firebase-config.js"), build_firebase_js(kit)),
        write(lib.rpath("firestore.rules"), build_rules(kit)),
    ]
    if not a.quiet:
        for p in outs:
            lib.ok("產生 %s" % os.path.relpath(p, lib.root()))
        for n in notes:
            lib.warn(n)
        print("\n下一步：部署安全規則（沒做這一步，網頁會讀不到資料）")
        print("  firebase deploy --only firestore:rules --project %s"
              % ((kit.get("firebase") or {}).get("project_id") or "<你的專案id>"))


if __name__ == "__main__":
    main()
