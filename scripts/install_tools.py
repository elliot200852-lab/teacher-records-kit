#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""install_tools.py — 裝齊 teacher-records-kit 需要的外部工具（macOS／Windows／Linux 同一支）。

本 kit 對外只靠幾支外部工具：Node.js、firebase-tools、gcloud、ffmpeg、whisper.cpp（選用 gws）。
每個工具「在哪個平台怎麼裝」只寫在 scripts/hostos.py 的 TOOLS 表；這支只是照表施工：
已經裝好的跳過、能自動裝的自動裝、自動裝不了的把官方網址印出來讓 AI 代理帶老師手動裝。
**跑幾次結果都一樣**（每個工具獨立、不會留下裝到一半的狀態）；失敗不會自動重試。

用法：
  python3 scripts/install_tools.py              逐項安裝，已裝好的自動跳過
  python3 scripts/install_tools.py --dry-run    只印每一步「會做什麼」，不實際安裝或修改任何東西
  python3 scripts/install_tools.py --with-gws   額外裝 googleworkspace-cli（備份走 gws 進階模式才需要）
  python3 scripts/install_tools.py --agent claude
                                                順便裝老師訂的那一家 AI 代理 CLI（claude／codex／gemini）；
                                                這台電腦已經有 Python 的話，不必走 setup/bootstrap.* 也能裝
  python3 scripts/install_tools.py --json       結果用 JSON 印（給 AI 代理讀）
  python3 scripts/install_tools.py --remove-portable
                                                刪掉 kit 自己下載的可攜工具（Windows／Linux 的 whisper、ffmpeg）；
                                                用套件管理程式裝的東西不動

各平台怎麼裝（正本＝hostos.TOOLS）：
  macOS    Homebrew（要先裝好 https://brew.sh ）＋ npm
  Windows  winget（Windows 10/11 內建）＋ npm；whisper.cpp 與（winget 失敗時的）ffmpeg
           直接下載官方預編譯檔到 %LOCALAPPDATA%\\teacher-records-kit\\tools，不需要管理員權限
  Linux    apt-get ＋ npm；whisper.cpp 下載官方預編譯檔；gcloud 請照官方說明裝

什麼都還沒有的全新電腦（連 Python、git、AI 代理都沒有）請先跑 setup/bootstrap.sh（macOS／Linux）
或按兩下 setup\\bootstrap.cmd（Windows）——那一層裝完 Python 之後就是回頭跑這一支。

裝完之後：python3 scripts/doctor.py 逐項健檢。
零第三方相依：只用 Python 標準庫與系統既有指令。
"""
import os
import sys
import json
import shutil
import hashlib
import tarfile
import zipfile
import argparse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib          # noqa: E402  （順便把主控台調成 UTF-8）
import hostos       # noqa: E402

OS = hostos.OS
DRY = False


# ── 印東西 ────────────────────────────────────────────────────────────────
def intro(name, spec):
    print("── %s" % name)
    print("   為什麼需要：%s" % spec["label"])


def show_cmd(argv):
    return " ".join(('"%s"' % a) if " " in a else a for a in argv)


def run_visible(argv, cwd=None):
    """跑安裝指令，輸出直接給老師看（sudo／UAC 提示也要看得到）。--dry-run 只印不跑。"""
    if DRY:
        print("  （--dry-run，不執行）將會跑：%s" % show_cmd(argv))
        return 0
    print("  執行：%s" % show_cmd(argv))
    sys.stdout.flush()
    rc, _ = hostos.run(argv, capture=False, cwd=cwd)
    if rc == 127:
        print("  找不到指令 %s" % argv[0])
    return rc


# ── 下載可攜工具 ──────────────────────────────────────────────────────────
def download(url, dest, sha256=None):
    """下載到 dest（先寫 .part 再改名，中斷不會留半個檔）。印百分比。

    sha256 有給就一定要對得上——對不上是「上游換了檔案」，比下載失敗嚴重：
    連 .part 都刪掉、直接丟 ToolError，不解壓、不留任何殘骸。"""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    print("  下載：%s" % url)
    req = urllib.request.Request(url, headers={"User-Agent": "teacher-records-kit/%s" % lib.version()})
    h = hashlib.sha256()
    try:
        with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = resp.read(1 << 18)
                if not chunk:
                    break
                out.write(chunk)
                h.update(chunk)
                done += len(chunk)
                if total:
                    sys.stdout.write("\r  %5.1f%%　%.0f／%.0f MB" % (done * 100.0 / total, done / 1e6, total / 1e6))
                    sys.stdout.flush()
        sys.stdout.write("\n")
    except Exception as e:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise hostos.ToolError("下載失敗：%s（%s）" % (url, e))
    got = h.hexdigest()
    if sha256 and got.lower() != str(sha256).lower():
        os.remove(tmp)
        raise hostos.ToolError(
            "下載的檔跟預期的不一樣（sha256 對不上）：%s；預期 %s、實得 %s。"
            "這通常表示上游換掉了那個檔（或下載被動過手腳）。先別裝，把這一段回報作者。"
            % (url, sha256, got))
    os.replace(tmp, dest)
    return dest


def _safe_members(names):
    for n in names:
        p = n.replace("\\", "/")
        if p.startswith("/") or ".." in p.split("/") or (len(p) > 1 and p[1] == ":"):
            raise hostos.ToolError("壓縮檔裡有可疑路徑，拒絕解壓：%s" % n)


def extract(archive, into):
    """解壓 zip 或 tar.gz 到 into（先清空）。"""
    if os.path.isdir(into):
        shutil.rmtree(into)
    os.makedirs(into, exist_ok=True)
    if archive.lower().endswith(".zip"):
        with zipfile.ZipFile(archive) as z:
            _safe_members(z.namelist())
            z.extractall(into)
    else:
        with tarfile.open(archive, "r:*") as t:
            _safe_members([m.name for m in t.getmembers()])
            try:
                t.extractall(into, filter="data")          # 3.12+
            except TypeError:
                t.extractall(into)


def find_file(root, name):
    for d, _, files in os.walk(root):
        if name in files:
            return os.path.join(d, name)
    return None


def install_download(key):
    """把 DOWNLOADS[key] 裝進 tools_dir()/<sub>/：下載 → 解壓 → 找到執行檔那一層 → 攤平到目的夾。
    回傳執行檔絕對路徑。"""
    url, exe_name, sub, sha256 = hostos.download_entry(key)
    dest_dir = os.path.join(hostos.tools_dir(), sub)
    if DRY:
        print("  （--dry-run，不執行）將會下載 %s 並解壓到 %s" % (url, dest_dir))
        return None
    stage = os.path.join(hostos.tools_dir(), "_stage-" + sub)
    archive = os.path.join(hostos.tools_dir(), "_dl-" + os.path.basename(url.split("?")[0]))
    try:
        download(url, archive, sha256)
        extract(archive, stage)
        found = find_file(stage, exe_name)
        if not found:
            raise hostos.ToolError("解壓後找不到 %s（壓縮檔版面可能改了；請回報作者）" % exe_name)
        src_dir = os.path.dirname(found)
        if os.path.isdir(dest_dir):
            shutil.rmtree(dest_dir)
        shutil.move(src_dir, dest_dir)                      # 連同旁邊的 dll／so 一起搬
        target = os.path.join(dest_dir, exe_name)
        if OS != "win":
            for f in os.listdir(dest_dir):
                p = os.path.join(dest_dir, f)
                if os.path.isfile(p) and not f.endswith((".so", ".txt", ".md")) and "." not in f:
                    os.chmod(p, 0o755)
            os.chmod(target, 0o755)
        print("  已放到：%s" % target)
        return target
    finally:
        shutil.rmtree(stage, ignore_errors=True)
        if os.path.exists(archive):
            os.remove(archive)


# ── 各種安裝方式 ──────────────────────────────────────────────────────────
def need_pm(pm, how):
    if hostos.exe(pm):
        return True
    print("  %s✗ 找不到 %s%s" % (lib.RED, pm, lib.RESET))
    print("  → %s" % how)
    return False


PM_HELP = {
    "brew": "先裝 Homebrew：到 https://brew.sh 複製首頁那一行指令貼進終端機執行，裝完重開終端機再跑本腳本。",
    "winget": "winget 是 Windows 10/11 內建的「App Installer」。開 Microsoft Store 搜尋「App Installer」更新它，"
              "或到 https://aka.ms/getwinget 下載；裝完重開 PowerShell 再跑本腳本。學校電腦被鎖住裝不了的話，"
              "改用每一項印出來的官方安裝檔手動裝。",
    "apt-get": "這支只會用 apt-get；你的發行版不是 Debian／Ubuntu 系的話，請用你自己的套件管理程式裝同名套件。",
    "npm": "npm 跟著 Node.js 一起裝；先把上面的 Node.js 那一步裝好，重開終端機再跑一次本腳本。",
}


# winget 這幾個退出碼其實是「沒事」，不能當失敗。它們是同一個 0x8A15xxxx 家族、
# 在 Python 這邊會拿到負數（0x8A15002B 與 -1978335189 是同一個值），所以先 & 0xFFFFFFFF 正規化再比：
#   0x8A15002B UPDATE_NOT_APPLICABLE      已經是最新版，沒有可套用的更新
#   0x8A150061 PACKAGE_ALREADY_INSTALLED  已經裝過了
#   3010       ERROR_SUCCESS_REBOOT_REQUIRED  裝好了，只是要重開機（VC++ 執行階段常回這個）
WINGET_OK_CODES = (0x8A15002B, 0x8A150061)


def winget_rc_is_ok(rc):
    """winget 的這個退出碼算不算成功。"""
    try:
        rc = int(rc)
    except (TypeError, ValueError):
        return False
    return rc == 0 or rc == 3010 or (rc & 0xFFFFFFFF) in WINGET_OK_CODES


def install_via(method, arg):
    """跑「一種安裝方式」。工具（TOOLS）與 AI 代理（AGENT_CLIS）共用這一支。
    回 (rc, note)：rc=0 成功、rc=None 表示這台電腦沒有這條路（要手動）。"""
    if method == "brew" or method == "brew-cask":
        if not need_pm("brew", PM_HELP["brew"]):
            return None, "缺 Homebrew"
        argv = ["brew", "install"] + (["--cask", arg] if method == "brew-cask" else [arg])
        return run_visible(argv), ""
    if method == "winget":
        if not need_pm("winget", PM_HELP["winget"]):
            return None, "缺 winget"
        print("  %s可能會跳出「使用者帳戶控制」視窗問你要不要允許——按「是」。%s" % (lib.YELLOW, lib.RESET))
        argv = ["winget", "install", "-e", "--id", arg, "--silent",
                "--accept-package-agreements", "--accept-source-agreements"]
        rc = run_visible(argv)
        if rc not in (0, None) and not DRY and winget_rc_is_ok(rc):
            rc = 0
        return rc, ""
    if method == "apt":
        if not need_pm("apt-get", PM_HELP["apt-get"]):
            return None, "沒有 apt-get"
        return run_visible(["sudo", "apt-get", "install", "-y", arg]), ""
    if method == "npm":
        if not hostos.exe("npm"):
            print("  %s✗ 找不到 npm%s" % (lib.RED, lib.RESET))
            print("  → %s" % PM_HELP["npm"])
            return None, "缺 npm"
        return run_visible(["npm", "install", "-g", arg]), ""
    if method == "sh-installer":
        if not hostos.exe("curl") or not hostos.exe("bash"):
            print("  %s✗ 這台電腦沒有 curl 或 bash%s" % (lib.RED, lib.RESET))
            return None, "缺 curl／bash"
        return run_visible(["bash", "-c", "curl -fsSL %s | bash" % arg]), ""
    if method == "ps-installer":
        if not hostos.exe("powershell"):
            print("  %s✗ 找不到 powershell%s" % (lib.RED, lib.RESET))
            return None, "缺 powershell"
        return run_visible(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                            "-Command", "irm %s | iex" % arg]), ""
    if method == "skip":
        return 0, "這個平台不需要"
    return None, "手動"


def do_install(name, spec):
    """照 TOOLS 表的方式裝一個工具。回 (rc, note)。rc=0 成功、rc=None 手動。"""
    method, arg = spec.get(OS, ("manual", ""))
    if method in ("brew", "brew-cask", "winget", "apt", "npm", "sh-installer", "ps-installer"):
        return install_via(method, arg)
    if method == "download":
        key = hostos.download_key(arg)
        if not key:
            print("  這個平台／架構（%s %s）沒有官方預編譯檔。" % (hostos.OS_LABEL, hostos.ARCH))
            print("  → 自己編譯或改在別台電腦轉錄：%s" % spec.get("url", ""))
            return None, "沒有預編譯檔"
        try:
            install_download(key)
            return 0, ""
        except hostos.ToolError as e:
            print("  %s✗ %s%s" % (lib.RED, e, lib.RESET))
            return 1, str(e)
    if method == "skip":
        return 0, "這個平台不需要"
    print("  這個平台沒有自動安裝的路，請照官方說明裝：%s" % spec.get("url", ""))
    return None, "手動"


def present(name, spec):
    """這個工具現在有沒有（＋版本夠不夠）。回 (ok, detail)。"""
    if name == "vcredist":
        return hostos.vcredist_present()             # 兩個 dll 都要驗；正本在 hostos，doctor.py 問同一支
    path = hostos.exe(name)
    if not path:
        return False, "找不到指令 %s" % name
    if name == "node":
        major = hostos.node_major()
        if major and major < spec.get("min_major", 0):
            return False, "已裝但版本太舊（v%d；Firebase CLI 要 %d 以上）" % (major, spec["min_major"])
    if name == "whisper-cli":
        rc, out = hostos.run([name, "-h"], timeout=30)
        if OS == "win" and rc in (3221225781, -1073741515):    # 0xC0000135：缺 DLL（多半是 VC++ 執行階段）
            return False, "檔案在但跑不起來（缺 Visual C++ 執行階段）"
    return True, path


def install_agent(agent):
    """裝老師訂的那一家 AI 代理 CLI（正本＝hostos.AGENT_CLIS）。回結果 dict（給 --json 用）。
    跟工具一樣的規矩：已經有的跳過、失敗不重試、主要方式不成就走備案，再不成印官方網址。"""
    spec = hostos.AGENT_CLIS[agent]
    print("── AI 代理：%s" % agent)
    print("   為什麼需要：%s——它就是待會兒帶老師把整套裝起來的那一個。" % spec["label"])
    path = hostos.exe(spec["cmd"])
    if path:
        print("  ✓ 已就緒，跳過　%s%s%s" % (lib.DIM, path, lib.RESET))
        if not DRY:
            return {"status": "ok", "detail": path, "launch": hostos.agent_launch(agent)}

    method, arg = hostos.agent_method(agent)
    fb = hostos.agent_fallback(agent)
    line = hostos.method_line(method, arg)
    if DRY:
        print("  （--dry-run，不執行）沒裝的話會跑：%s"
              % (line or "（這個平台沒有自動安裝的路，照官方說明裝：%s）" % spec.get("url", "")))
        if fb:
            print("  （失敗時的備案：%s）" % hostos.method_line(*fb))
        print("  裝完之後這樣叫它：%s" % hostos.agent_launch(agent))
        return {"status": "ok" if path else "would-install", "detail": path or line,
                "launch": hostos.agent_launch(agent)}

    rc, note = install_via(method, arg)
    # 備案**只走一次**：rc 是 None（這台電腦沒有那條路）與 rc 非 0（跑了但失敗）都算「主要方式沒成」，
    # 合在同一個分支裡判——寫成兩個 if 的話同一支備案安裝程式會被連跑兩次。
    if rc != 0 and fb:
        print("  主要方式沒成（%s），改走備案……" % ("這台電腦沒有那條路" if rc is None else "回傳 %s" % rc))
        rc, note = install_via(*fb)

    hostos.refresh_path()
    path = hostos.exe(spec["cmd"])
    if path:
        print("  ✓ 裝好了　%s%s%s" % (lib.DIM, path, lib.RESET))
        if spec.get("note"):
            print("  %s" % spec["note"])
        return {"status": "installed", "detail": path, "launch": hostos.agent_launch(agent)}
    print("  %s✗ 沒裝成（%s）%s" % (lib.RED, note or ("安裝指令回傳 %s" % rc), lib.RESET))
    print("  → 重開一個新的終端機視窗再打一次 `%s`；還是沒有就照官方說明裝：%s"
          % (spec["cmd"], spec.get("url", "")))
    return {"status": "failed", "detail": note, "rc": rc, "url": spec.get("url", ""),
            "launch": hostos.agent_launch(agent)}


def main():
    global DRY
    ap = argparse.ArgumentParser(description="裝齊 teacher-records-kit 需要的外部工具（macOS／Windows／Linux）")
    ap.add_argument("--dry-run", action="store_true", help="只印會做什麼，不實際安裝")
    ap.add_argument("--with-gws", action="store_true", help="額外裝 googleworkspace-cli（備份 gws 進階模式才要）")
    ap.add_argument("--agent", choices=hostos.AGENT_ORDER,
                    help="順便裝這一家的 AI 代理 CLI（claude／codex／gemini）")
    ap.add_argument("--json", action="store_true", dest="as_json", help="結果用 JSON 印（給 AI 代理讀）")
    ap.add_argument("--remove-portable", action="store_true", help="刪掉 kit 自己下載的可攜工具")
    a = ap.parse_args()
    DRY = a.dry_run

    why = hostos.unsupported_reason()
    if why:
        lib.die(why, "換到 Windows 原生終端機之後再跑一次這支。")

    if a.remove_portable:
        d = hostos.tools_dir()
        if os.path.isdir(d):
            if DRY:
                print("（--dry-run）將會刪除：%s" % d)
            else:
                shutil.rmtree(d)
                lib.ok("已刪除 %s" % d)
        else:
            print("沒有可攜工具要刪（%s 不存在）。" % d)
        return

    s = hostos.summary()
    print("平台：%s（%s）　Python：%s（這台電腦請用 `%s` 叫它）　套件管理：%s%s"
          % (s["os_label"], s["arch"], s["python"], s["python_cmd"], s["package_manager"],
             "" if s["package_manager_found"] else "（找不到）"))
    if DRY:
        print("（--dry-run：以下只印，不會裝任何東西）")
    print()

    results = {}
    for name in hostos.TOOL_ORDER:
        spec = hostos.TOOLS[name]
        if spec.get("win_only") and OS != "win":
            continue
        if spec.get("optional_flag") and not a.with_gws:
            print("── %s（選用，跳過；要裝加 %s）" % (name, spec["optional_flag"]))
            results[name] = {"status": "skipped", "detail": "選用"}
            continue
        intro(name, spec)
        ok, detail = present(name, spec)
        if ok:
            print("  ✓ 已就緒，跳過　%s%s%s" % (lib.DIM, detail, lib.RESET))
            results[name] = {"status": "ok", "detail": detail}
            continue
        print("  目前：%s" % detail)
        rc, note = do_install(name, spec)
        if rc is None:
            results[name] = {"status": "manual", "detail": note, "url": spec.get("url", "")}
            continue
        if DRY:
            results[name] = {"status": "would-install", "detail": ""}
            continue
        hostos.refresh_path()
        ok2, detail2 = present(name, spec)
        fb_key = hostos.download_key(spec["fallback"][OS]) if spec.get("fallback", {}).get(OS) else None
        if rc == 0 and not ok2 and fb_key:
            print("  裝完還是找不到，改用備案下載……")
            try:
                install_download(fb_key)
            except hostos.ToolError as e:
                print("  %s✗ %s%s" % (lib.RED, e, lib.RESET))
            hostos.refresh_path()
            ok2, detail2 = present(name, spec)
        if ok2:
            print("  ✓ 裝好了　%s%s%s" % (lib.DIM, detail2, lib.RESET))
            if spec.get("after"):
                print("  %s" % spec["after"])
            results[name] = {"status": "installed", "detail": detail2}
        else:
            print("  %s✗ 沒裝成（%s）%s" % (lib.RED, detail2 if rc == 0 else "安裝指令回傳 %s" % rc, lib.RESET))
            print("  → 重開一個新的終端機視窗再跑 `%s scripts/doctor.py`；還是沒有就照官方安裝檔手動裝：%s"
                  % (hostos.PY, spec.get("url", "")))
            results[name] = {"status": "failed", "detail": detail2, "rc": rc, "url": spec.get("url", "")}

    agent = None
    if a.agent:
        print()
        agent = install_agent(a.agent)

    failed = [n for n, r in results.items() if r["status"] == "failed"]
    manual = [n for n, r in results.items() if r["status"] == "manual"]
    if agent and agent["status"] == "failed":
        failed.append("agent:" + a.agent)
    if a.as_json:
        print(json.dumps({"os": OS, "python_cmd": hostos.PY, "results": results,
                          "failed": failed, "manual": manual,
                          "agent": dict(agent, name=a.agent) if agent else None},
                         ensure_ascii=False, indent=2))
    else:
        print()
        print("完成：就緒 %d、剛裝好 %d、要手動 %d、失敗 %d"
              % (sum(1 for r in results.values() if r["status"] == "ok"),
                 sum(1 for r in results.values() if r["status"] == "installed"), len(manual), len(failed)))
        if manual:
            print("要手動裝的：%s（每一項上面都印了官方網址；裝完重開終端機再跑健檢）" % "、".join(manual))
        if agent:
            print("AI 代理 %s：%s" % (a.agent, agent["status"]))
        print("下一步：%s scripts/doctor.py 逐項健檢" % hostos.PY)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
