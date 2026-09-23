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
import argparse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib
import hostos
import auto_dim_tags  # noqa: E402
import build_config  # noqa: E402


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
    if lib.is_local(kit):
        # 本機模式沒有資料庫，所以沒有「資料庫上次部署的版本」這回事。
        # 這一項**留著但標成略過**，不是拿掉：CI 與 AI 代理都靠固定的 key 清單判斷，
        # 少一個 key 它們會以為健檢改名壞掉了。
        r.add("cloud_version", "資料庫上次部署的版本（meta/config.version）", False,
              "本機模式，沒有資料庫", required=False, skipped=True)
        return
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


def check_platform(r):
    """這是哪種電腦、放對地方沒。平台事實的正本在 hostos.py 與 docs/PLATFORMS.md。"""
    s = hostos.summary()
    why = hostos.unsupported_reason()
    r.add("platform", "平台 %s（%s）" % (s["os_label"], s["arch"]), not why, why or
          "Python 叫法：`%s`；套件管理：%s%s" % (s["python_cmd"], s["package_manager"],
                                             "" if s["package_manager_found"] else "（找不到）"),
          "換到 Windows 原生的 PowerShell／Windows Terminal 再裝。")
    for reason, fix in hostos.repo_path_warnings(lib.PKG):
        r.add("repo_path", "kit 放的位置", False, reason, fix, required=False)


def check_tools(r, kit, skip_network):
    v = sys.version_info
    r.add("python", "Python 3.9 以上", hostos.python_ok(9), "目前 %d.%d.%d（%s）" % (v[0], v[1], v[2], sys.executable),
          "macOS 內建的 python3 就夠；Windows 到 https://www.python.org/downloads/ 裝（勾 Add to PATH）；"
          "Linux 用 apt-get install python3。")

    # 本機模式用不到這三支（它們全是為了「把東西送上雲端」而存在的）。
    # 一樣是留著項目、標成略過，不是拿掉——key 清單要穩定。
    CLOUD_TOOLS = ("node", "firebase", "gcloud")
    local = lib.is_local(kit)

    for name in hostos.TOOL_ORDER:
        spec = hostos.TOOLS[name]
        if spec.get("win_only") and hostos.OS != "win":
            continue
        if local and name in CLOUD_TOOLS:
            r.add(name.replace("-cli", ""), spec["label"], bool(hostos.exe(name)),
                  "本機模式不需要", required=False, skipped=True)
            continue
        if name == "gws":
            continue                                   # 下面依 drive.mode 另外判
        if name == "vcredist":
            ok, detail = hostos.vcredist_present()     # 兩個 dll 都要驗；正本在 hostos，install_tools 問同一支
            r.add("vcredist", spec["label"], ok, detail,
                  hostos.install_hint("vcredist"), required=False)
            continue
        path = hostos.exe(name)
        detail, ok = (path or "找不到指令 %s" % name), bool(path)
        if ok and name == "node":
            major = hostos.node_major()
            if major and major < spec["min_major"]:
                ok, detail = False, "%s（v%d 太舊，Firebase CLI 要 %d 以上）" % (path, major, spec["min_major"])
            elif major:
                detail = "%s（v%d）" % (path, major)
        r.add(name.replace("-cli", ""), spec["label"], ok, detail, hostos.install_hint(name),
              required=spec["required"])

    if (kit.get("drive") or {}).get("mode") == "gws":
        path = hostos.exe("gws")
        r.add("gws", "gws（Google Workspace CLI，備份走 gws 模式才要）", bool(path),
              path or "找不到指令 gws",
              "%s 不想弄這個就把 config/kit.json 的 drive.mode 改成 desktop。" % hostos.install_hint("gws"))
    else:
        r.add("gws", "gws（只有 drive.mode=gws 才需要）", True, "目前是 desktop 模式，不需要",
              required=False)

    found = hostos.agent_clis_found()
    names = [hostos.AGENT_CLIS[n]["cmd"] for n in hostos.AGENT_ORDER if found.get(n)]
    r.add("agent_cli", "AI 代理的 CLI（claude／codex／gemini）", bool(names),
          ("找到：%s" % "、".join(names)) if names else "這台電腦上找不到 claude、codex 或 gemini",
          "只是報告用，不影響 kit 本身。要裝一支：`%s scripts/install_tools.py --agent claude`"
          "（或 codex／gemini）；什麼都還沒有的新電腦跑 setup/bootstrap.sh（Windows 按兩下 setup\\bootstrap.cmd）。"
          % hostos.PY,
          required=False)

    chrome = hostos.chrome_candidates()
    r.add("chrome", "Chrome／Edge（export_docs.py 印 PDF 用）", bool(chrome),
          chrome[0] if chrome else "找不到 Chrome、Chromium 或 Edge",
          "沒有也能用：匯出會留下排版好的 HTML，自己用瀏覽器開 → 列印 → 儲存為 PDF。", required=False)

    # 語音模型
    model = (kit.get("voice") or {}).get("model") or "ggml-large-v3-turbo"
    mpath = os.path.join(hostos.model_dir(), "%s.bin" % model)
    exists = os.path.exists(mpath)
    size = (" %.1f GB" % (os.path.getsize(mpath) / 1e9)) if exists else ""
    r.add("model", "語音模型 %s" % model, exists, (mpath + size) if exists else "還沒下載",
          "第一次跑 `%s scripts/transcribe.py --inbox` 時會自動下載（約 1.6GB），"
          "也可以手動抓 https://huggingface.co/ggerganov/whisper.cpp 放到 %s" % (lib.PY, hostos.model_dir()),
          required=False)

    if lib.is_local(kit):
        r.add("gcloud_auth", "gcloud 已登入", False, "本機模式不連雲端，不需要",
              required=False, skipped=True)
    elif skip_network:
        r.add("gcloud_auth", "gcloud 已登入", False, "--skip-network", required=True, skipped=True)
    elif lib.emulator_host():
        r.add("gcloud_auth", "gcloud 已登入", True, "模擬器模式（FIRESTORE_EMULATOR_HOST=%s），不需要" % lib.emulator_host())
    elif hostos.exe("gcloud"):
        rc, out = hostos.run(["gcloud", "auth", "print-access-token"], timeout=60)
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

    local = lib.is_local(kit)
    r.add("mode", "資料庫模式", True,
          "local——只放這台電腦，沒有 Firebase、沒有網頁" if local
          else "cloud——你自己的 Firebase 專案＋手機網頁")

    # 產生檔。本機模式只會有 kit-config.js；另外兩個**不是「還沒產生」而是「不該產生」**，
    # 所以標成略過而不是 ✗（key 一個都不能少，CI 與 AI 代理靠固定清單判斷）。
    for key, rel, cloud_only in [("kitjs", "site/js/kit-config.js", False),
                                 ("fbjs", "site/js/firebase-config.js", True),
                                 ("rules", "firestore.rules", True)]:
        p = lib.rpath(rel)
        if local and cloud_only:
            r.add("gen_" + key, "產生檔 %s" % rel, False, "本機模式不產生這個檔",
                  required=False, skipped=True)
            continue
        r.add("gen_" + key, "產生檔 %s" % rel, os.path.exists(p),
              p if os.path.exists(p) else "還沒產生",
              "跑 `python3 scripts/build_config.py`（這幾個檔一律由腳本產生，不要手寫）。")

    email = (kit.get("owner_email") or "").strip()
    r.add("owner", "owner_email 已填", bool(email) and email != "you@example.com",
          lib.mask_email(email) if email else "空的",
          "重跑 `python3 scripts/setup.py` 填你的 Google 信箱。")

    rules = lib.rpath("firestore.rules")
    if local:
        r.add("rules_email", "安全規則裡的信箱與設定一致", False, "本機模式沒有安全規則",
              required=False, skipped=True)
        r.add("rules_fresh", "安全規則比設定新", False, "本機模式沒有安全規則",
              required=False, skipped=True)
    elif os.path.exists(rules) and email:
        with open(rules, encoding="utf-8") as f:
            text = f.read()
        # 規則檔裡寫的是小寫的信箱（build_config 會 lower()），設定檔裡老師可能打成大寫——
        # 兩邊都轉小寫再比，不然明明產對了卻報「規則裡沒有你的信箱」。
        wanted = [email.strip().lower()] + [
            (str(e) if e is not None else "").strip().lower()
            for e in (kit.get("co_owner_emails") or [])
            if isinstance(kit.get("co_owner_emails"), list)]
        good = all(w in text.lower() for w in wanted if w) and "{{OWNER_EMAILS}}" not in text
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
              "：質性評量觀察、導師班級學生紀錄、任課老師學生紀錄、個案追蹤、IEP、會談紀錄（SOAP）。",
              required=False)
        roster = lib.load_roster(kit)
        r.add("roster", "名冊 data/roster.csv", bool(roster),
              "%d 位學生" % len(roster) if roster else "還是空的（只有表頭）",
              "用試算表打開 data/roster.csv，填「代號,姓名,類型」三欄再存成 CSV"
              "（第三欄＝這位學生列入哪些個案型記錄類型，分號分隔，可以空著）。真名只會留在你電腦上。",
              required=False)


def check_firebaserc(r, kit):
    """.firebaserc：firebase.json 的 hosting.target "web" 要靠它對應到真正的 Hosting site。

    多數老師一個專案一個預設 site，這個檔由 build_config.py 自動產生，平常不會出錯；
    只有像同一個專案掛了不只一個 site 那種進階安裝，才可能跟 kit.json 的
    firebase.hosting_site 兜不起來——幾種壞法都算：檔案不存在、格式不對（根／projects／
    targets 不是物件）、web target 沒有任何對應、或對應到的 site 跟現在算出來的不一樣
    （多半是 hosting_site 改過但沒重跑產生器）。**不管檔案裡塞了什麼奇怪的形狀都不丟例外**
    ——doctor.py 一項檢查壞掉不該讓後面的項目都不跑。
    """
    label = ".firebaserc（Hosting site 對應）"
    if lib.is_local(kit):
        r.add("firebaserc", label, True, "本機模式沒有 Hosting，不需要", required=False, skipped=True)
        return
    pid = (kit.get("firebase") or {}).get("project_id") or ""
    if not build_config.hosting_pid_usable(pid):
        r.add("firebaserc", label, True, "Firebase 專案 ID 還沒填，這一項先跳過",
              required=False, skipped=True)
        return
    wanted = build_config.hosting_site(kit)
    path = lib.rpath(".firebaserc")
    if not os.path.exists(path):
        r.add("firebaserc", label, False, "檔案不存在", "跑 `python3 scripts/build_config.py`。")
        return
    try:
        with open(path, encoding="utf-8-sig") as f:
            data = json.load(f)
    except (OSError, ValueError) as e:
        # ValueError 涵蓋 json.JSONDecodeError，也涵蓋 UnicodeDecodeError——記事本存成
        # 「Unicode」（UTF-16，開頭 fffe/feff）的 .firebaserc 讀到一半就是後者，
        # 舊版只接 (OSError, json.JSONDecodeError) 接不住，會讓整支 doctor.py 當掉。
        r.add("firebaserc", label, False, "格式不對：讀不出來（%s）" % e,
              "刪掉 .firebaserc 再跑 `python3 scripts/build_config.py`。")
        return
    if not build_config.firebaserc_shape_ok(data):
        r.add("firebaserc", label, False, "格式不對（根、projects、targets 都應該是物件）",
              "刪掉 .firebaserc 再跑 `python3 scripts/build_config.py`。")
        return
    targets = data.get("targets") or {}
    proj_targets = targets.get(pid)
    proj_targets = proj_targets if isinstance(proj_targets, dict) else {}
    hosting = proj_targets.get("hosting")
    hosting = hosting if isinstance(hosting, dict) else {}
    sites = hosting.get("web")
    sites = sites if isinstance(sites, list) else []
    good = sites == [wanted]
    r.add("firebaserc", label, good,
          "web → %s" % (", ".join(str(s) for s in sites) if sites else "（沒有對應）") if not good
          else "web → %s" % wanted,
          "跑 `python3 scripts/build_config.py`。")


def check_auth_domain(r, kit):
    """authDomain 要跟實際部署的 Hosting site 同源，不然 iOS Safari 上的 Google 登入會一直跳回
    未登入（AGENTS.md 步驟 2 那個坑）。多站安裝（填了 firebase.hosting_site）最容易踩到：
    kit.json 裡的 auth_domain 是舊 site 留下的值、或跟現在算出來的 site 對不上。

    `.web.app` 網域看前綴跟現在算出來的 site 一不一樣（比對前都轉小寫，`TRK-4A.web.app`
    不該被誤判成不對）；`.firebaseapp.com` 網域**不管前綴對不對都算沒過**——AGENTS.md
    從頭到尾都把它當成 iPhone 登入的坑（跟 Hosting 實際用的 `.web.app` 不同源），
    不是「前綴對了就沒事」的東西，一律建議改成 `<site>.web.app`。
    自訂網域（GitHub Pages、嵌入現有站）不受影響、不比對——這一項本來就選用
    （required=False），別讓它擋掉正常安裝。
    """
    label = "authDomain 跟 Hosting site 同源"
    if lib.is_local(kit):
        r.add("auth_domain", label, True, "本機模式沒有網址，不需要", required=False, skipped=True)
        return
    site = build_config.hosting_site(kit)
    actual = ((kit.get("firebase") or {}).get("auth_domain") or "").strip()
    if not actual:
        r.add("auth_domain", label, True,
              "留空——build_config.py 會自動填 %s.web.app" % (site or "<專案id>"), required=False)
        return
    if not site:
        r.add("auth_domain", label, True, "%s（還沒填 project_id，這一項先不比對）" % actual,
              required=False, skipped=True)
        return
    low, site_low = actual.lower(), site.lower()
    fix = ("多站安裝：把 config/kit.json 的 firebase.auth_domain 改成 %s.web.app，"
          "重跑 `python3 scripts/build_config.py`，並到 Firebase 主控台 Authentication → "
          "Settings → 已授權網域（Authorized domains）手動加上這個網域——沒對上的話 iOS Safari "
          "上的 Google 登入會一直跳回未登入。" % site)
    if low.endswith(".firebaseapp.com"):
        r.add("auth_domain", label, False,
              "%s（.firebaseapp.com 跟 Hosting 實際用的網址不同源，iOS 上會登不進去，"
              "建議改成 %s.web.app）" % (actual, site), fix, required=False)
        return
    if low.endswith(".web.app"):
        prefix = low[:-len(".web.app")]
        good = prefix == site_low
        r.add("auth_domain", label, good,
              actual if good else "%s（現在算出來的 Hosting site 是 %s）" % (actual, site),
              fix, required=False)
        return
    r.add("auth_domain", label, True, "%s（自訂網域，不比對）" % actual, required=False)


def check_headless(r, kit, skip_network):
    """無頭交辦（選用）。沒開就只留一項「關著」，不吵人。

    開了的話這五項全部是必要的——少任何一項，老師在手機上講的話就會靜靜地掉在雲端，
    而他完全不會知道（他唯一的回饋就是那句「收到了」，那句是 relay 回的，不代表有人處理）。
    """
    h = lib.headless_cfg(kit)
    if not lib.headless_on(kit):
        r.add("headless", "無頭交辦（LINE 語音／文字 → 紀錄）", True,
              "沒有開（本機模式不支援）" if lib.is_local(kit) else "沒有開",
              required=False)
        return
    r.add("headless", "無頭交辦（LINE → %s）" % (h["agent"] or "？"), True,
          "開著，逾時 %d 秒" % h["timeout_sec"])

    # ① 兩個金鑰的環境變數。排程跑的時候讀不到 ＝ 每 5 分鐘失敗一次，而且沒有人看 log。
    missing = [h["line"][k] for k in ("channel_secret_env", "channel_token_env")
               if not (os.environ.get(h["line"][k]) or "").strip()]
    r.add("headless_secrets", "LINE 金鑰的環境變數都設好了", not missing,
          "現在這個終端機讀不到：%s" % "、".join(missing) if missing else "兩個都讀得到",
          "到 LINE Developers → 你的 Messaging API 頻道拿 Channel secret 與 Channel access token，"
          "寫進**登入時會載入**的設定檔（macOS／Linux：~/.bashrc 或 ~/.zshrc；"
          "Windows：系統內容 → 環境變數）——只在終端機臨時 export 的話，排程跑起來讀不到。"
          "細節見 docs/HEADLESS.md。")

    # ② 配對碼
    r.add("headless_paired", "已經跟你的 LINE 帳號配對", bool(h["line"]["owner_user_id"]),
          h["line"]["owner_user_id"][:8] + "…" if h["line"]["owner_user_id"] else "還沒配對",
          "用手機傳一句話給你的官方帳號，它會回「配對碼：Uxxxx…」；"
          "或在電腦上跑 `%s scripts/headless.py --pair`。拿到之後填進 config/kit.json 的 "
          "headless.line.owner_user_id，再跑 `%s scripts/build_config.py`。" % (lib.PY, lib.PY))

    # ③ 代理的 CLI 真的在這台電腦上
    path = hostos.exe((hostos.AGENT_CLIS.get(h["agent"]) or {}).get("cmd") or h["agent"])
    r.add("headless_agent", "AI 代理 %s 叫得出來" % (h["agent"] or "？"), bool(path),
          path or "找不到指令 %s" % h["agent"],
          "%s 裝好之後要登入過一次（在終端機直接跑一次它、照它的指示登入），"
          "不然無頭模式會卡在登入畫面然後逾時。" % hostos.agent_install_hint(h["agent"]))

    # ④ 雲端那一半：relay 部署了沒、配對碼有沒有送上去
    if skip_network:
        r.add("headless_cloud", "雲端收件端（Cloud Function ＋ 配對碼）", False,
              "--skip-network", required=False, skipped=True)
        return
    tok = lib.token(quiet=True)
    if not tok:
        r.add("headless_cloud", "雲端收件端（Cloud Function ＋ 配對碼）", False,
              "gcloud 沒登入，這次沒檢查", required=False, skipped=True)
        return
    try:
        fs, _ = lib.get_doc(lib.fb_base(kit), "meta/headless", tok, raise_errors=True)
    except Exception as e:                          # noqa: BLE001 連不上不該讓健檢整個掛掉
        r.add("headless_cloud", "雲端收件端（Cloud Function ＋ 配對碼）", False,
              str(e)[:120], required=False, skipped=True)
        return
    cloud_uid = (fs or {}).get("ownerUserId") or ""
    same = bool(cloud_uid) and cloud_uid == h["line"]["owner_user_id"]
    r.add("headless_cloud", "配對碼已經送上雲端（meta/headless）", same,
          "雲端還沒有配對碼" if not cloud_uid else
          ("雲端記的是另一個人（%s…）" % cloud_uid[:8] if not same else "一致"),
          "跑一次 `%s scripts/headless.py --once`，它會把 config/kit.json 裡的配對碼寫上去。"
          "relay 讀的是雲端那一份——沒寫上去的話它會一直停在「回配對碼」的狀態。" % lib.PY)


def check_auto_dim_tags(r, kit, tabs):
    """評量維度自動補標（選用）。沒開只留一項「關著」；開了多檢查一項：代理 CLI 叫不叫得出來。

    代理叫不出來的時候同步照常完成、只印一行警告——排程的 log 沒有人看，
    老師最可能永遠不知道它其實一則都沒補。健檢是他唯一會看到的地方。
    """
    c = lib.auto_dim_tags_cfg(kit)
    label = "評量維度自動補標（同步時請 AI 補代表標籤）"
    if not c["enabled"]:
        r.add("auto_dim_tags", label, True, "沒有開", required=False)
        return
    if lib.is_local(kit):
        r.add("auto_dim_tags", label, True, "開著，但本機模式沒有同步，這一項不會跑", required=False)
        return
    if not c["agent"]:
        r.add("auto_dim_tags", label, False,
              "開著，但 auto_dim_tags.agent 與 headless.agent 都是空的——視同沒設定，同步時不會補標",
              "重跑 `%s scripts/setup.py` 在「評量維度自動補標」那一題選一支代理；或在 config/kit.json 的 "
              "auto_dim_tags.agent 填 claude、codex 或 gemini。" % lib.PY, required=False)
        return
    try:
        streams = auto_dim_tags.eligible_streams(tabs or {})
    except (Exception, SystemExit):     # noqa: BLE001 格式庫讀不到：健檢不該因此整個掛掉
        streams = []
    r.add("auto_dim_tags", "評量維度自動補標（%s%s）"
          % (c["agent"], "，沿用無頭交辦那一支" if c["agent_inherited"] else ""), True,
          ("開著，會補標的記錄類型：%s" % "、".join(streams)) if streams else
          "開著，但你勾的記錄類型沒有一種是網頁會自動推導維度的（例如導師班級學生紀錄），目前一則都不會補",
          required=False)
    spec = hostos.AGENT_CLIS.get(c["agent"])
    path = hostos.exe(spec["cmd"]) if spec else None
    r.add("auto_dim_tags_agent", "評量維度補標的 AI 代理 %s 叫得出來" % c["agent"], bool(path),
          path or ("找不到指令 %s" % spec["cmd"] if spec else "不認得的代理 %r" % c["agent"]),
          ("%s 裝好之後要登入過一次（在終端機直接跑一次它、照指示登入）。叫不出來的話同步照常完成，"
           "但每次都只印一行警告、一則也不會補。" % hostos.agent_install_hint(c["agent"])) if spec else
          "config/kit.json 的 auto_dim_tags.agent 只能是 claude、codex、gemini 或空字串（空＝沿用 headless.agent）。")


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
        cands = [] if ok else hostos.drive_desktop_candidates()
        hint = ("這台電腦上找得到的同步夾：%s ——在裡面建一個資料夾，把完整路徑填進去。" % "；".join(cands)) if cands else \
               "這台電腦上找不到「Google 雲端硬碟」的同步夾——多半是桌面程式沒裝或沒登入。%s" % hostos.drive_desktop_where()
        r.add("drive", "Drive 備份資料夾（desktop 模式）", ok, path,
              "先安裝並登入「Google 雲端硬碟」桌面程式 https://www.google.com/drive/download/ ，"
              "在雲端硬碟裡建一個資料夾，再把正確路徑填回 config/kit.json 的 drive.desktop_dir。" + hint)
        return

    fid = drive.get("backup_folder_id") or ""
    if not fid:
        r.add("drive", "Drive 備份資料夾（gws 模式）", False, "backup_folder_id 沒填",
              "打開那個 Drive 資料夾，網址 .../folders/XXXX 的 XXXX 就是 id。")
        return
    if skip_network or not hostos.exe("gws"):
        r.add("drive", "Drive 備份資料夾（gws 模式）", False,
              "--skip-network" if skip_network else "gws 還沒裝", skipped=True)
        return
    rc, out = hostos.run(["gws", "drive", "files", "get", "--format", "json",
                          "--params", json.dumps({"fileId": fid, "fields": "id,name,trashed"})], timeout=60)
    if rc == 126:
        r.add("drive", "Drive 備份資料夾（gws 模式）", False, "Windows 上這個查詢無法經 gws.cmd 送出",
              "把 config/kit.json 的 drive.mode 改成 desktop（把 zip 複製進 Google 雲端硬碟同步夾）。")
        return
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
    ap = argparse.ArgumentParser(description="Teacher Records Kit 健檢：逐項檢查並告訴你怎麼修"
                                              "（真刪雲端原文另有 scripts/purge_deleted.py，不在健檢範圍）")
    ap.add_argument("--json", action="store_true", dest="as_json", help="輸出 JSON（給 AI 代理讀）")
    ap.add_argument("--skip-network", action="store_true", help="跳過要連網的項目")
    lib.add_root_arg(ap)
    a = ap.parse_args()
    lib.apply_root(a)

    kit = lib.load_kit(required=False)
    tabs = lib.load_tabs(required=False) or {}
    r = Report()
    check_platform(r)
    check_version(r, kit, a.skip_network)
    check_tools(r, kit, a.skip_network)
    check_config(r, kit, tabs, a.skip_network)
    check_firebaserc(r, kit)
    check_auth_domain(r, kit)
    check_headless(r, kit, a.skip_network)
    check_auto_dim_tags(r, kit, tabs)
    check_drive(r, kit, a.skip_network)

    if a.as_json:
        print(json.dumps({"root": lib.root(), "version": lib.version(),
                          "mode": lib.mode(kit), "headless": lib.headless_on(kit),
                          "ok": not r.failed,
                          "failed": len(r.failed), "warned": len(r.warned),
                          "items": r.items}, ensure_ascii=False, indent=2))
        sys.exit(1 if r.failed else 0)

    print("健檢：%s（kit %s，%s）\n" % (lib.root(), lib.version(), hostos.OS_LABEL))
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
