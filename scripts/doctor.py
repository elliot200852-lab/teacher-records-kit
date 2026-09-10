#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""doctor.py — 健檢：一項一項告訴你什麼好了、什麼還沒好、沒好的怎麼修。

裝到一半卡住、或哪天突然壞掉，第一件事就是跑這支。每個 ✗ 都附「→ 怎麼修」與連結；
必要項目沒過 exit 1，選用項目沒過只印黃色驚嘆號、不算失敗。

用法：
  python3 scripts/doctor.py                  逐項檢查（人看的）
  python3 scripts/doctor.py --json           輸出 JSON（給 AI 代理讀）
  python3 scripts/doctor.py --skip-network   跳過要連網的項目（沒網路、或在測試）
  python3 scripts/doctor.py --root DIR       指定資料根目錄
"""
import os
import sys
import json
import shutil
import argparse
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

BREW = "brew install %s"
INSTALL_ALL = "一次裝齊：`bash scripts/install_tools.sh`"


def sh(cmd, timeout=60):
    """跑一個指令，回 (returncode, stdout+stderr)。找不到指令回 (127, '')。"""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except FileNotFoundError:
        return 127, ""
    except subprocess.TimeoutExpired:
        return 124, ""
    except Exception as e:                                  # pragma: no cover
        return 1, str(e)


class Report:
    def __init__(self):
        self.items = []

    def add(self, key, label, ok, detail="", fix="", required=True, skipped=False):
        self.items.append({"key": key, "label": label, "ok": bool(ok), "detail": detail,
                           "fix": fix, "required": required, "skipped": skipped})
        return ok

    @property
    def failed(self):
        return [i for i in self.items if i["required"] and not i["ok"] and not i["skipped"]]

    @property
    def warned(self):
        return [i for i in self.items if not i["required"] and not i["ok"] and not i["skipped"]]

    def render(self):
        for i in self.items:
            if i["skipped"]:
                print("%s– %s（跳過：%s）%s" % (lib.DIM, i["label"], i["detail"], lib.RESET))
            elif i["ok"]:
                print("%s✓%s %s%s" % (lib.GREEN, lib.RESET, i["label"],
                                      ("　%s%s%s" % (lib.DIM, i["detail"], lib.RESET)) if i["detail"] else ""))
            elif i["required"]:
                print("%s✗ %s%s%s" % (lib.RED, i["label"],
                                      ("　" + i["detail"]) if i["detail"] else "", lib.RESET))
                if i["fix"]:
                    print("  → %s" % i["fix"])
            else:
                print("%s! %s（選用）%s%s" % (lib.YELLOW, i["label"],
                                              ("　" + i["detail"]) if i["detail"] else "", lib.RESET))
                if i["fix"]:
                    print("  → %s" % i["fix"])


def check_version(r, kit, skip_network):
    """這份 kit 是哪一版，以及資料庫最後一次是用哪一版部署規則的。

    `meta/config.version` 由 sync.py 寫。網頁版本比它新＝規則可能過舊，要重新部署；
    連不上（沒登入、沒網路、還沒接 Firebase）就跳過，不算失敗。
    """
    ver = lib.version()
    r.add("version", "kit 版本", True, ver)
    if skip_network:
        r.add("cloud_version", "資料庫上次部署的版本（meta/config.version）", False,
              "--skip-network", required=False, skipped=True)
        return
    pid = (kit.get("firebase") or {}).get("project_id", "")
    tok = lib.token(quiet=True) if pid and not pid.startswith("your-") else None
    if not tok:
        r.add("cloud_version", "資料庫上次部署的版本（meta/config.version）", False,
              "還沒接上 Firebase 或 gcloud 沒登入", required=False, skipped=True)
        return
    try:
        fs, _ = lib.get_doc(lib.fb_base(kit), "meta/config", tok, raise_errors=True)
    except Exception as e:
        r.add("cloud_version", "資料庫上次部署的版本（meta/config.version）", False,
              str(e)[:120], required=False, skipped=True)
        return
    cloud_ver = str((fs or {}).get("version") or "")
    if not cloud_ver:
        r.add("cloud_version", "資料庫上次部署的版本（meta/config.version）", False,
              "資料庫上還沒有版本記錄",
              "跑一次 `python3 scripts/sync.py`，它會把版本寫上去。", required=False)
    else:
        same = cloud_ver == ver
        r.add("cloud_version", "資料庫上次部署的版本與這份程式一致", same,
              "資料庫 %s／這份 %s" % (cloud_ver, ver),
              "程式比資料庫新——重新部署安全規則再同步一次："
              "`python3 scripts/build_config.py` → "
              "`firebase deploy --only firestore:rules` → `python3 scripts/sync.py`。",
              required=False)


def check_tools(r, kit, skip_network):
    v = sys.version_info
    r.add("python", "Python 3.8 以上", v >= (3, 8), "目前 %d.%d.%d" % v[:3],
          "macOS 內建的 python3 就夠；`brew install python` 也可以。")

    for key, cmd, label, required, fix in [
        ("node", "node", "Node.js（Firebase CLI 要用）", True, BREW % "node"),
        ("firebase", "firebase", "Firebase CLI（部署規則與網站）", True, "npm i -g firebase-tools"),
        ("gcloud", "gcloud", "gcloud（本機腳本讀寫你的 Firestore）", True,
         "brew install --cask google-cloud-sdk，或 https://cloud.google.com/sdk/docs/install"),
        ("ffmpeg", "ffmpeg", "ffmpeg（錄音轉檔）", False, BREW % "ffmpeg"),
        ("whisper", "whisper-cli", "whisper-cli（本機語音轉逐字稿）", False, BREW % "whisper-cpp"),
    ]:
        path = shutil.which(cmd)
        r.add(key, label, bool(path), path or "找不到指令 %s" % cmd,
              "%s（%s）" % (fix, INSTALL_ALL), required=required)

    if (kit.get("drive") or {}).get("mode") == "gws":
        path = shutil.which("gws")
        r.add("gws", "gws（Google Workspace CLI，備份走 gws 模式才要）", bool(path),
              path or "找不到指令 gws",
              "brew install googleworkspace-cli ——注意 formula 叫 googleworkspace-cli，"
              "`brew install gws` 會裝到完全不相干的套件。不想弄這個就把 config/kit.json 的 "
              "drive.mode 改成 desktop。")
    else:
        r.add("gws", "gws（只有 drive.mode=gws 才需要）", True, "目前是 desktop 模式，不需要",
              required=False)

    # 語音模型
    model = (kit.get("voice") or {}).get("model") or "ggml-large-v3-turbo"
    mpath = os.path.expanduser("~/.cache/whisper-cpp/%s.bin" % model)
    exists = os.path.exists(mpath)
    size = (" %.1f GB" % (os.path.getsize(mpath) / 1e9)) if exists else ""
    r.add("model", "語音模型 %s" % model, exists, (mpath + size) if exists else "還沒下載",
          "第一次跑 `python3 scripts/transcribe.py --inbox` 時會自動下載（約 1.6GB），"
          "也可以手動抓 https://huggingface.co/ggerganov/whisper.cpp 放到 ~/.cache/whisper-cpp/",
          required=False)

    if skip_network:
        r.add("gcloud_auth", "gcloud 已登入", False, "--skip-network", required=True, skipped=True)
    elif shutil.which("gcloud"):
        rc, out = sh(["gcloud", "auth", "print-access-token"])
        r.add("gcloud_auth", "gcloud 已登入（拿得到存取權杖）", rc == 0,
              "" if rc == 0 else out.strip().splitlines()[-1][:120] if out.strip() else "拿不到權杖",
              "跑 `gcloud auth login`，用你當初開 Firebase 專案的那個 Google 帳號。")
    else:
        r.add("gcloud_auth", "gcloud 已登入", False, "gcloud 還沒裝", "先裝 gcloud（見上一項）。")


def check_config(r, kit, tabs, skip_network):
    for key, rel, required in [("kit", lib.KIT_JSON, True), ("tabs", lib.TABS_JSON, True)]:
        p = lib.rpath(rel)
        ok = os.path.exists(p)
        detail = ""
        if ok:
            try:
                with open(p, encoding="utf-8") as f:
                    json.load(f)
            except json.JSONDecodeError as e:
                ok, detail = False, "JSON 壞掉：第 %d 行 %s" % (e.lineno, e.msg)
        r.add("cfg_" + key, "設定檔 %s" % rel, ok, detail or (p if ok else "還沒產生"),
              "跑 `python3 scripts/setup.py` 安裝精靈；它會照你的回答產生這個檔。", required=required)

    for key, rel in [("kitjs", "site/js/kit-config.js"),
                     ("fbjs", "site/js/firebase-config.js"),
                     ("rules", "firestore.rules")]:
        p = lib.rpath(rel)
        r.add("gen_" + key, "產生檔 %s" % rel, os.path.exists(p),
              p if os.path.exists(p) else "還沒產生",
              "跑 `python3 scripts/build_config.py`（這三個檔一律由腳本產生，不要手寫）。")

    email = (kit.get("owner_email") or "").strip()
    r.add("owner", "owner_email 已填", bool(email) and email != "you@example.com",
          lib.mask_email(email) if email else "空的",
          "重跑 `python3 scripts/setup.py` 填你的 Google 信箱。")

    rules = lib.rpath("firestore.rules")
    if os.path.exists(rules) and email:
        with open(rules, encoding="utf-8") as f:
            text = f.read()
        good = email in text and "{{OWNER_EMAIL}}" not in text
        r.add("rules_email", "安全規則裡的信箱與設定一致", good,
              "" if good else "規則檔裡沒有你的信箱，或佔位符沒被換掉",
              "跑 `python3 scripts/build_config.py`，再 `firebase deploy --only firestore:rules`。")
        newer = os.path.getmtime(lib.rpath(lib.KIT_JSON)) > os.path.getmtime(rules) \
            if os.path.exists(lib.rpath(lib.KIT_JSON)) else False
        r.add("rules_fresh", "安全規則比設定新", not newer,
              "設定改過但規則還沒重產" if newer else "",
              "跑 `python3 scripts/build_config.py` 再部署一次。", required=False)

    # 業務組：設定與本機資料夾對得上
    d = lib.data_dir()
    if os.path.isdir(d):
        missing = [t["id"] for t in lib.targets(kit, tabs) if not os.path.exists(t["path"])]
        r.add("data_files", "本機記錄檔齊全", not missing,
              ("缺 %d 個：%s" % (len(missing), "、".join(missing[:6]))) if missing else "%d 個目標" % len(lib.targets(kit, tabs)),
              "重跑 `python3 scripts/setup.py`（不會覆蓋已經有的檔），或手動建那個資料夾與 records.md。",
              required=False)
        streams = lib.student_streams(tabs) if (tabs.get("students") or {}).get("enabled", True) else []
        r.add("streams", "學生記錄類型", bool(streams),
              "、".join("%s（%s）" % (s.get("label") or s["id"], s["id"]) for s in streams)
              if streams else "一種都沒勾——學生分頁不會有紀錄",
              "重跑 `python3 scripts/setup.py`，在「勾選你要的記錄類型」那題勾起來"
              "（導師班級學生紀錄、任課老師學生紀錄、個案追蹤、IEP、輔導晤談）。",
              required=False)
        roster = lib.load_roster(kit)
        r.add("roster", "名冊 data/roster.csv", bool(roster),
              "%d 位學生" % len(roster) if roster else "還是空的（只有表頭）",
              "用試算表打開 data/roster.csv，填「代號,姓名,類型」三欄再存成 CSV"
              "（第三欄＝這位學生列入哪些個案型記錄類型，分號分隔，可以空著）。真名只會留在你電腦上。",
              required=False)


def check_drive(r, kit, skip_network):
    drive = kit.get("drive") or {}
    mode = drive.get("mode", "desktop")
    if mode == "desktop":
        path = os.path.expanduser(drive.get("desktop_dir") or "")
        if not path:
            r.add("drive", "Drive 備份資料夾", False, "desktop_dir 沒填",
                  "在 config/kit.json 的 drive.desktop_dir 填「Google 雲端硬碟」同步夾裡的一個資料夾。")
            return
        ok = os.path.isdir(path)
        r.add("drive", "Drive 備份資料夾（desktop 模式）", ok, path,
              "先安裝並登入「Google 雲端硬碟」桌面程式 https://www.google.com/drive/download/ ，"
              "在雲端硬碟裡建一個資料夾，再把正確路徑填回 config/kit.json 的 drive.desktop_dir。"
              "（路徑裡的信箱要跟你登入桌面程式的那個一樣。）")
        return

    fid = drive.get("backup_folder_id") or ""
    if not fid:
        r.add("drive", "Drive 備份資料夾（gws 模式）", False, "backup_folder_id 沒填",
              "打開那個 Drive 資料夾，網址 .../folders/XXXX 的 XXXX 就是 id。")
        return
    if skip_network or not shutil.which("gws"):
        r.add("drive", "Drive 備份資料夾（gws 模式）", False,
              "--skip-network" if skip_network else "gws 還沒裝", skipped=True)
        return
    rc, out = sh(["gws", "drive", "files", "get", "--format", "json",
                  "--params", json.dumps({"fileId": fid, "fields": "id,name,trashed"})])
    info = {}
    if rc == 0:
        txt = "\n".join(l for l in out.splitlines() if not l.startswith("Using keyring"))
        try:
            info = json.loads(txt or "{}")
        except json.JSONDecodeError:
            info = {}
    good = rc == 0 and info.get("id") and not info.get("trashed")
    r.add("drive", "Drive 備份資料夾（gws 模式）", bool(good),
          ("%s（%s）" % (info.get("name", "?"), fid)) if good else
          ("資料夾在垃圾桶裡" if info.get("trashed") else "查不到這個資料夾 id：%s" % fid),
          "確認 id 沒貼錯、資料夾沒被丟進垃圾桶，而且 gws 登入的帳號看得到它。"
          "腳本**不會**幫你自己建一個新資料夾——那會讓備份靜靜地跑到別的地方去。")


def main():
    ap = argparse.ArgumentParser(description="Teacher Records Kit 健檢：逐項檢查並告訴你怎麼修")
    ap.add_argument("--json", action="store_true", dest="as_json", help="輸出 JSON（給 AI 代理讀）")
    ap.add_argument("--skip-network", action="store_true", help="跳過要連網的項目")
    lib.add_root_arg(ap)
    a = ap.parse_args()
    lib.apply_root(a)

    kit = lib.load_kit(required=False)
    tabs = lib.load_tabs(required=False) or {}
    r = Report()
    check_version(r, kit, a.skip_network)
    check_tools(r, kit, a.skip_network)
    check_config(r, kit, tabs, a.skip_network)
    check_drive(r, kit, a.skip_network)

    if a.as_json:
        print(json.dumps({"root": lib.root(), "version": lib.version(), "ok": not r.failed,
                          "failed": len(r.failed), "warned": len(r.warned),
                          "items": r.items}, ensure_ascii=False, indent=2))
        sys.exit(1 if r.failed else 0)

    print("健檢：%s（kit %s）\n" % (lib.root(), lib.version()))
    r.render()
    print()
    if r.failed:
        print("%s還有 %d 項必要條件沒過（上面 ✗ 的部分）。%s照每一項的「→」修完再跑一次。"
              % (lib.RED, len(r.failed), lib.RESET))
        sys.exit(1)
    if r.warned:
        print("%s必要條件都過了；%d 項選用功能還沒裝（黃色驚嘆號），不影響核心使用。%s"
              % (lib.YELLOW, len(r.warned), lib.RESET))
    else:
        lib.ok("全部通過。")


if __name__ == "__main__":
    main()
