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
  python3 scripts/install_tools.py --json       結果用 JSON 印（給 AI 代理讀）
  python3 scripts/install_tools.py --remove-portable
                                                刪掉 kit 自己下載的可攜工具（Windows／Linux 的 whisper、ffmpeg）；
                                                用套件管理程式裝的東西不動

各平台怎麼裝（正本＝hostos.TOOLS）：
  macOS    Homebrew（要先裝好 https://brew.sh ）＋ npm
  Windows  winget（Windows 10/11 內建）＋ npm；whisper.cpp 與（winget 失敗時的）ffmpeg
           直接下載官方預編譯檔到 %LOCALAPPDATA%\\teacher-records-kit\\tools，不需要管理員權限
  Linux    apt-get ＋ npm；whisper.cpp 下載官方預編譯檔；gcloud 請照官方說明裝

裝完之後：python3 scripts/doctor.py 逐項健檢。
零第三方相依：只用 Python 標準庫與系統既有指令。
"""
import os
import sys
import json
import shutil
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
def download(url, dest):
    """下載到 dest（先寫 .part 再改名，中斷不會留半個檔）。印百分比。"""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    print("  下載：%s" % url)
    req = urllib.request.Request(url, headers={"User-Agent": "teacher-records-kit/%s" % lib.version()})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp, open(tmp, "wb") as out:
            total = int(resp.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = resp.read(1 << 18)
                if not chunk:
                    break
                out.write(chunk)
                done += len(chunk)
                if total:
                    sys.stdout.write("\r  %5.1f%%　%.0f／%.0f MB" % (done * 100.0 / total, done / 1e6, total / 1e6))
                    sys.stdout.flush()
        sys.stdout.write("\n")
    except Exception as e:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise hostos.ToolError("下載失敗：%s（%s）" % (url, e))
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
    url, exe_name, sub = hostos.DOWNLOADS[key]
    dest_dir = os.path.join(hostos.tools_dir(), sub)
    if DRY:
        print("  （--dry-run，不執行）將會下載 %s 並解壓到 %s" % (url, dest_dir))
        return None
    stage = os.path.join(hostos.tools_dir(), "_stage-" + sub)
    archive = os.path.join(hostos.tools_dir(), "_dl-" + os.path.basename(url.split("?")[0]))
    try:
        download(url, archive)
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


def do_install(name, spec):
    """照 TOOLS 表的方式裝一個工具。回 (rc, note)。rc=0 成功、rc=None 手動。"""
    method, arg = spec.get(OS, ("manual", ""))
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
        if rc not in (0, None) and not DRY:
            # winget 的「已經是最新版」不算失敗
            if rc in (-1978335189, 0x8A15002B):
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
        if OS != "win":
            return True, "非 Windows 不需要"
        sysroot = os.environ.get("SystemRoot", r"C:\Windows")
        p = os.path.join(sysroot, "System32", "vcruntime140.dll")
        return os.path.exists(p), p if os.path.exists(p) else "找不到 vcruntime140.dll"
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


def main():
    global DRY
    ap = argparse.ArgumentParser(description="裝齊 teacher-records-kit 需要的外部工具（macOS／Windows／Linux）")
    ap.add_argument("--dry-run", action="store_true", help="只印會做什麼，不實際安裝")
    ap.add_argument("--with-gws", action="store_true", help="額外裝 googleworkspace-cli（備份 gws 進階模式才要）")
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

    failed = [n for n, r in results.items() if r["status"] == "failed"]
    manual = [n for n, r in results.items() if r["status"] == "manual"]
    if a.as_json:
        print(json.dumps({"os": OS, "python_cmd": hostos.PY, "results": results,
                          "failed": failed, "manual": manual}, ensure_ascii=False, indent=2))
    else:
        print()
        print("完成：就緒 %d、剛裝好 %d、要手動 %d、失敗 %d"
              % (sum(1 for r in results.values() if r["status"] == "ok"),
                 sum(1 for r in results.values() if r["status"] == "installed"), len(manual), len(failed)))
        if manual:
            print("要手動裝的：%s（每一項上面都印了官方網址；裝完重開終端機再跑健檢）" % "、".join(manual))
        print("下一步：%s scripts/doctor.py 逐項健檢" % hostos.PY)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
