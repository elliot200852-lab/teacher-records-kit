#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hostos.py — 平台差異只寫在這一個檔（macOS／Windows／Linux）。

其他腳本不准自己判斷 `sys.platform`、不准自己拼 Homebrew 或 winget 指令、不准自己猜
Google 雲端硬碟或 Chrome 裝在哪——一律問這支：

  OS                      "mac" / "win" / "linux"（WSL 算 "wsl"：不支援，見 unsupported_reason()）
  PY                      這台電腦上該怎麼叫 Python（"python3"、"py -3" 或 "python"），文件與訊息用
  exe(name)               找外部工具的絕對路徑（PATH ＋ 各平台的已知安裝位置 ＋ kit 自己的工具夾）
  run(cmd, ...)           subprocess.run 的薄包裝：cmd[0] 先經 exe()、輸出解碼不會炸、.cmd 特殊字元有閘
  refresh_path()          剛裝完工具、PATH 還沒更新時，把新的路徑補進目前這個行程（Windows 讀登錄檔）
  tools_dir()             kit 自己下載的可攜工具放哪（Windows 的 ffmpeg／whisper 就住這裡）
  model_dir()             whisper 語音模型放哪
  drive_desktop_candidates()  這台電腦上「Google 雲端硬碟」桌面程式的同步夾（找得到的都列出來）
  chrome_candidates()     能拿來印 PDF 的 Chrome／Chromium／Edge
  install_hint(tool)      這個平台上怎麼裝某個工具的一句話（doctor.py 的「→ 怎麼修」用）
  TOOLS / DOWNLOADS       工具表：每個工具在每個平台怎麼裝（install_tools.py 只照這張表做事）

人讀的平台說明在 docs/PLATFORMS.md；那份文件講「為什麼」，這支管「怎麼做」。
零第三方相依。這支不 import lib（lib 會 import 它）。
"""
import os
import re
import sys
import glob
import shutil
import platform
import subprocess
import threading

# ── 這是哪一種電腦 ────────────────────────────────────────────────────────


def _detect():
    forced = os.environ.get("TRK_FORCE_OS")              # 只給測試用：在 mac 上渲染 Windows 的 dry-run
    if forced in ("mac", "win", "linux", "wsl"):
        return forced
    if sys.platform == "darwin":
        return "mac"
    if sys.platform.startswith("win") or sys.platform == "cygwin":
        return "win"
    try:
        with open("/proc/version", encoding="utf-8", errors="replace") as f:
            if "microsoft" in f.read().lower():
                return "wsl"
    except OSError:
        pass
    return "linux"


OS = _detect()
OS_LABEL = {"mac": "macOS", "win": "Windows", "linux": "Linux", "wsl": "WSL（Windows 裡的 Linux）"}[OS]
ARCH = (platform.machine() or "").lower()            # arm64 / aarch64 / x86_64 / amd64
IS_ARM = ARCH in ("arm64", "aarch64")


def unsupported_reason():
    """這個環境根本不該裝的話，回一句原因；可以裝回 ""。"""
    if OS == "wsl":
        return ("你在 WSL（Windows 底下的 Linux）裡。這套 kit 的備份要寫進「Google 雲端硬碟」桌面程式的同步夾、"
                "排程要掛在 Windows 的工作排程器，這兩件事在 WSL 裡都看不到 Windows 那一邊，會靜靜地失效。"
                "請關掉 WSL，改在 Windows 原生的 PowerShell 或 Windows Terminal 裡重新開始。")
    return ""


def _env(name, default=""):
    return os.environ.get(name) or default


def home():
    return os.path.expanduser("~")


# ── 主控台：Windows 舊版終端機不吃 ANSI 顏色、預設編碼也不是 UTF-8 ──────────────
_console_done = False


def enable_console():
    """讓 ✓✗ 與中文在 Windows 的 cmd／PowerShell 也印得出來，並開啟 ANSI 顏色。
    每支腳本 import lib 時會自動呼叫一次；重複呼叫無害。"""
    global _console_done
    if not sys.platform.startswith("win") or _console_done:      # 看真實平台，不看 TRK_FORCE_OS
        return
    _console_done = True
    try:
        import ctypes
        k = ctypes.windll.kernel32
        k.GetStdHandle.restype = ctypes.c_void_p
        k.GetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint32)]
        k.SetConsoleMode.argtypes = [ctypes.c_void_p, ctypes.c_uint32]
        k.SetConsoleOutputCP(65001)                          # 主控台改吃 UTF-8，舊 conhost 才不會印成問號
        k.SetConsoleCP(65001)
        for handle_id in (-11, -12):                         # STD_OUTPUT_HANDLE / STD_ERROR_HANDLE
            handle = k.GetStdHandle(handle_id)
            mode = ctypes.c_uint32()
            if handle and k.GetConsoleMode(handle, ctypes.byref(mode)):
                k.SetConsoleMode(handle, mode.value | 0x0004)   # ENABLE_VIRTUAL_TERMINAL_PROCESSING
    except Exception:
        pass
    for stream in (sys.stdout, sys.stderr):
        try:
            if hasattr(stream, "reconfigure"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def color_ok():
    """終端機不支援顏色（或輸出被導到檔案）時回 False，呼叫端就不要印 ANSI 碼。"""
    if _env("NO_COLOR"):
        return False
    try:
        return sys.stdout.isatty()
    except Exception:
        return False


# ── 該怎麼叫 Python ───────────────────────────────────────────────────────
def _real_python(name):
    """Windows 的 python／python3 可能只是「開 Microsoft Store」的假殼（App Execution Alias，住在 WindowsApps）。
    不跑子行程（每支腳本 import 時都會經過這裡，跑子行程太貴），只看它住哪。"""
    p = shutil.which(name)
    return bool(p) and "windowsapps" not in p.lower()


def python_cmd():
    """文件裡寫的是 `python3 scripts/…`。回傳這台電腦上真的叫得到 Python 3 的那個寫法。"""
    if OS != "win":
        return "python3"
    if shutil.which("py"):                      # python.org 版一定有 py 啟動器；Store 假殼不會有
        return "py -3"
    for name in ("python", "python3"):
        if _real_python(name):
            return name
    return "python"


PY = python_cmd()


# ── kit 自己的資料夾 ───────────────────────────────────────────────────────
def cache_dir():
    """kit 自己下載的東西（可攜工具）放哪。Windows 照慣例放 %LOCALAPPDATA%。"""
    if OS == "win":
        base = _env("LOCALAPPDATA") or os.path.join(home(), "AppData", "Local")
        return os.path.join(base, "teacher-records-kit")
    return os.path.join(home(), ".cache", "teacher-records-kit")


def tools_dir():
    return os.path.join(cache_dir(), "tools")


def model_dir():
    """whisper 模型。三個平台都放 ~/.cache/whisper-cpp（Windows 的 ~ 是 %USERPROFILE%），
    只有一條規則、跟 v3.0.0-alpha.1 相容。"""
    return os.path.join(home(), ".cache", "whisper-cpp")


def repo_path_warnings(repo_dir):
    """這份 kit 放的位置會不會出事（doctor.py 用）。回 [(原因, 怎麼辦)]。"""
    out = []
    if OS == "win":
        for var in ("OneDrive", "OneDriveConsumer", "OneDriveCommercial"):
            od = _env(var)
            if od and os.path.normcase(os.path.abspath(repo_dir)).startswith(os.path.normcase(os.path.abspath(od))):
                out.append(("這個資料夾在 OneDrive 同步範圍裡（%s）" % od,
                            "OneDrive 會鎖檔、還會把 data/ 裡的真名名冊同步上去。把整個資料夾搬到 OneDrive 外面"
                            "（例如 C:\\Users\\你\\teacher-records-kit）再繼續。"))
        if len(os.path.abspath(repo_dir)) > 150:
            out.append(("資料夾路徑太長（%d 字）" % len(os.path.abspath(repo_dir)),
                        "Windows 路徑總長超過 260 會出怪錯。把資料夾搬到淺一點的位置，例如 C:\\Users\\你\\trk。"))
    return out


# ── 找工具 ────────────────────────────────────────────────────────────────
EXE_EXTS = (".exe", ".cmd", ".bat", ".com") if OS == "win" else ("",)


def _known_dirs():
    """PATH 以外、各平台常見的安裝位置（剛裝完、還沒重開終端機時 PATH 往往還沒有它們）。"""
    t = tools_dir()
    dirs = [os.path.join(t, "whisper"), os.path.join(t, "ffmpeg"), os.path.join(t, "bin")]   # install_download 會把執行檔那一層攤平到 tools/<sub>/
    if OS == "win":
        pf = _env("ProgramFiles", r"C:\Program Files")
        pf86 = _env("ProgramFiles(x86)", r"C:\Program Files (x86)")
        la = _env("LOCALAPPDATA", os.path.join(home(), "AppData", "Local"))
        ra = _env("APPDATA", os.path.join(home(), "AppData", "Roaming"))
        dirs += [
            os.path.join(pf, "nodejs"),
            os.path.join(ra, "npm"),                                            # npm -g 的 .cmd 殼
            os.path.join(la, "Google", "Cloud SDK", "google-cloud-sdk", "bin"),
            os.path.join(pf86, "Google", "Cloud SDK", "google-cloud-sdk", "bin"),
            os.path.join(pf, "Google", "Cloud SDK", "google-cloud-sdk", "bin"),
            os.path.join(la, "Microsoft", "WinGet", "Links"),                   # winget 可攜套件的連結（ffmpeg）
        ]
    elif OS == "mac":
        dirs += ["/opt/homebrew/bin", "/usr/local/bin",
                 os.path.join(home(), "google-cloud-sdk", "bin")]
    else:
        dirs += [os.path.join(home(), "google-cloud-sdk", "bin"), os.path.join(home(), ".local", "bin"),
                 "/snap/bin", "/usr/local/bin"]
    return dirs


def _is_exe(path):
    return os.path.isfile(path) and os.access(path, os.X_OK)


def exe(name):
    """外部工具的絕對路徑；找不到回 None。
    Windows 上 subprocess 不會自己找 .cmd／.bat（gcloud、firebase、gws 都是 .cmd），
    所以呼叫外部工具**一律**先經過這裡。"""
    if os.path.sep in name or (os.path.altsep and os.path.altsep in name):
        return name if _is_exe(name) else None
    found = shutil.which(name)
    if found:
        return found
    for d in _known_dirs():
        for ext in EXE_EXTS:
            p = os.path.join(d, name + ext)
            if _is_exe(p):
                return p
    return None


_CMD_META = re.compile(r"[&|<>^%\r\n]")     # 引號本身安全（不能讓它後面接到 & 之類的才危險）；換行會讓 cmd.exe 截斷


def decode_output(data):
    """工具輸出 → 字串。先當 UTF-8；不是的話用主控台／系統編碼（Windows 中文版是 cp950），
    最後才 replace——錯誤訊息裡的中文要留著，那是代理自救的線索。"""
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    for enc in _fallback_encodings():
        try:
            return data.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return data.decode("utf-8", errors="replace")


def _fallback_encodings():
    encs = []
    if OS == "win":
        try:
            import ctypes
            cp = ctypes.windll.kernel32.GetConsoleOutputCP()
            if cp and cp != 65001:
                encs.append("cp%d" % cp)
        except Exception:
            pass
        encs.append("mbcs")
    import locale
    try:
        encs.append(locale.getpreferredencoding(False))
    except Exception:
        pass
    return [e for e in encs if e]


class ToolError(Exception):
    pass


CMD_GUARD_MSG = ("參數含有 cmd.exe 的特殊字元（& | < > ^ %% 或換行），經 %s 轉手會被重新解析或截斷，已拒絕執行。"
                 "Windows 上寄信請改 email.method=smtp。")


def run(cmd, timeout=None, capture=True, cwd=None, input_text=None, split=False):
    """跑一個外部指令，回 (returncode, stdout+stderr)；split=True 時回 (returncode, stdout, stderr)。
    cmd[0] 先經過 exe()；找不到回 127，逾時回 124。
    Windows 上 .cmd／.bat 會再經過 cmd.exe 解析一次，參數裡有 & | < > ^ % 或換行會被當指令或截斷——
    這種組合直接拒跑（回 126），呼叫端要改走不經 .cmd 的路（例如寄信改 smtp）。"""
    def _r(rc, out="", err=""):
        return (rc, out, err) if split else (rc, out + err)
    path = exe(cmd[0])
    if not path:
        return _r(127)
    args = [str(a) for a in cmd[1:]]
    if OS == "win" and path.lower().endswith((".cmd", ".bat")) and any(_CMD_META.search(a) for a in args):
        return _r(126, "", CMD_GUARD_MSG % os.path.basename(path))
    try:
        r = subprocess.run([path, *args], capture_output=capture, timeout=timeout, cwd=cwd,
                           input=input_text.encode("utf-8") if input_text is not None else None)
        if not capture:
            return _r(r.returncode)
        return _r(r.returncode, decode_output(r.stdout), decode_output(r.stderr))
    except subprocess.TimeoutExpired:
        return _r(124)
    except OSError as e:                      # 找不到、沒權限、不是可執行檔（Windows 的 exec format）都算跑不起來
        return _r(127, "", str(e))


def refresh_path():
    """剛用 winget／brew 裝完工具，目前這個行程的 PATH 還是舊的。把該補的補進來，之後 exe() 就找得到。
    Windows：重讀登錄檔裡的系統與使用者 PATH（安裝程式改的就是那裡）。"""
    extra = list(_known_dirs())
    if OS == "win":
        try:
            import winreg
            for hive, key in ((winreg.HKEY_LOCAL_MACHINE,
                               r"SYSTEM\CurrentControlSet\Control\Session Manager\Environment"),
                              (winreg.HKEY_CURRENT_USER, "Environment")):
                try:
                    with winreg.OpenKey(hive, key) as k:
                        val, _ = winreg.QueryValueEx(k, "Path")
                        extra += [os.path.expandvars(p) for p in str(val).split(os.pathsep) if p]
                except OSError:
                    pass
        except ImportError:
            pass
    cur = [p for p in os.environ.get("PATH", "").split(os.pathsep) if p]
    seen = {os.path.normcase(p) for p in cur}
    for p in extra:
        if os.path.isdir(p) and os.path.normcase(p) not in seen:
            cur.append(p)
            seen.add(os.path.normcase(p))
    os.environ["PATH"] = os.pathsep.join(cur)
    return os.environ["PATH"]


def version_of(name, args=("--version",)):
    """工具版本字串（第一行），拿不到回 ""。"""
    rc, out = run([name, *args], timeout=30)
    return out.strip().splitlines()[0].strip() if rc == 0 and out.strip() else ""


def node_major():
    """Node.js 主版本號（int），沒裝或讀不出來回 0。Firebase CLI 要 20 以上。"""
    m = re.match(r"v?(\d+)", version_of("node"))
    return int(m.group(1)) if m else 0


# ── Google 雲端硬碟桌面程式的同步夾 ───────────────────────────────────────────
DRIVE_ROOT_NAMES = ("My Drive", "我的雲端硬碟", "我的云端硬盘")


def _win_fixed_drives():
    """真的存在、而且是本機固定磁碟的代號（C 以外）。網路磁碟機／光碟／隨身碟不碰：
    斷線的 NAS 對應會讓 isdir 卡幾十秒。Google 雲端硬碟桌面程式掛出來的是固定磁碟。"""
    try:
        import ctypes
        k = ctypes.windll.kernel32
        old = ctypes.c_uint32()
        k.SetThreadErrorMode(0x0001 | 0x0002, ctypes.byref(old))   # SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX：不要跳「沒有磁片」對話框
        k.GetDriveTypeW.argtypes = [ctypes.c_wchar_p]
        k.GetDriveTypeW.restype = ctypes.c_uint32
        mask = k.GetLogicalDrives()
        out = []
        for i in range(26):
            letter = chr(ord("A") + i)
            if not (mask & (1 << i)) or letter == "C":
                continue
            if k.GetDriveTypeW("%s:\\" % letter) == 3:                       # DRIVE_FIXED
                out.append(letter)
        k.SetThreadErrorMode(old.value, None)
        return out
    except Exception:
        return []


def _isdir_timeout(path, seconds=2.0):
    """isdir 但最多等 seconds 秒（對付會卡住的磁碟）。"""
    box = {}

    def probe():
        try:
            box["v"] = os.path.isdir(path)
        except Exception:
            box["v"] = False
    t = threading.Thread(target=probe, daemon=True)
    t.start()
    t.join(seconds)
    return box.get("v", False)


def drive_desktop_candidates():
    """這台電腦上找得到的「Google 雲端硬碟」根資料夾（My Drive 那一層），找不到就回空清單。
    setup.py 用它給預設值、doctor.py 用它提示「你是不是想填這個」。"""
    found = []

    def add(p):
        if p and p not in found and _isdir_timeout(p):
            found.append(p)

    if OS == "mac":
        for base in sorted(glob.glob(os.path.join(home(), "Library", "CloudStorage", "GoogleDrive-*"))):
            for n in DRIVE_ROOT_NAMES:
                add(os.path.join(base, n))
    elif OS == "win":
        for letter in _win_fixed_drives():
            for n in DRIVE_ROOT_NAMES:
                add("%s:\\%s" % (letter, n))
        for n in DRIVE_ROOT_NAMES:
            add(os.path.join(home(), n))
            add(os.path.join(home(), "Google Drive", n))
        for base in sorted(glob.glob(os.path.join(home(), "Google Drive*"))):
            add(base)
    elif OS == "linux":
        for n in ("GoogleDrive", "google-drive", "Google Drive", "My Drive", "gdrive"):
            add(os.path.join(home(), n))
    return found


def drive_desktop_hint(owner_email=""):
    """desktop 模式的預設備份路徑（給 setup.py 當預設值、給文件當範例）。
    找得到真的同步夾就用真的；找不到就給該平台的典型長相，讓老師知道要去哪裡對。"""
    cands = drive_desktop_candidates()
    if cands:
        return os.path.join(cands[0], "教學紀錄備份")
    if OS == "mac":
        return "~/Library/CloudStorage/GoogleDrive-%s/My Drive/教學紀錄備份" % (owner_email or "你的信箱")
    if OS == "win":
        return r"G:\My Drive\教學紀錄備份"
    return "~/GoogleDrive/教學紀錄備份"


def drive_desktop_where():
    """「去哪裡拿」那一句：老師怎麼確認同步夾在哪。"""
    if OS == "mac":
        return "打開 Finder，側邊欄「Google Drive」→ My Drive；完整路徑在 ~/Library/CloudStorage/GoogleDrive-<信箱>/My Drive/ 底下。"
    if OS == "win":
        return "打開檔案總管，左側會多一個「Google Drive」磁碟機（通常是 G:），裡面的「My Drive」或「我的雲端硬碟」就是根目錄。"
    return "看你掛載 Google 雲端硬碟的方式（rclone／Insync 等），填它掛載到的資料夾。"


# ── Chrome／Chromium／Edge（export_docs.py 印 PDF 用） ───────────────────────────
def chrome_candidates():
    """依優先順序列出可能存在的瀏覽器執行檔（只回真的存在的）。Windows 一定有 Edge，所以 PDF 不會沒得印。"""
    cands = []
    if OS == "mac":
        for app in ("Google Chrome.app/Contents/MacOS/Google Chrome",
                    "Chromium.app/Contents/MacOS/Chromium",
                    "Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                    "Brave Browser.app/Contents/MacOS/Brave Browser"):
            cands += [os.path.join("/Applications", app), os.path.join(home(), "Applications", app)]
    elif OS == "win":
        pf = _env("ProgramFiles", r"C:\Program Files")
        pf86 = _env("ProgramFiles(x86)", r"C:\Program Files (x86)")
        la = _env("LOCALAPPDATA", os.path.join(home(), "AppData", "Local"))
        for base in (pf, pf86, la):
            cands.append(os.path.join(base, "Google", "Chrome", "Application", "chrome.exe"))
        for base in (pf86, pf):
            cands.append(os.path.join(base, "Microsoft", "Edge", "Application", "msedge.exe"))
        cands.append(os.path.join(la, "Chromium", "Application", "chrome.exe"))
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser",
                 "microsoft-edge", "brave-browser"):
        p = shutil.which(name)
        if p:
            cands.append(p)
    return [p for p in cands if _is_exe(p)]


# ── 工具表：每個工具在每個平台怎麼裝（install_tools.py 與 doctor.py 共用） ─────────────
# 欄位：
#   label     人看的名字＋為什麼需要
#   required  必要（沒有就不能用核心功能）或選用
#   mac/win/linux  安裝方式：("brew", formula) / ("brew-cask", cask) / ("winget", id) /
#                  ("apt", pkg) / ("npm", pkg) / ("download", key) / ("manual", "")
#   fallback  該平台主要方式失敗時改走的 DOWNLOADS key
#   url       官方下載頁（所有自動方式都失敗時印給老師）
#   after     裝完要老師做的一件事
# 改工具的裝法只改這張表；不要在別的檔案裡另外寫一份。
WHISPER_TAG = "b4938"                       # whisper.cpp 的 release 標籤；升級只改這一行（CI 每週會驗網址還在不在）
WHISPER_URL = "https://github.com/ggml-org/whisper.cpp/releases/download/%s/%%s" % WHISPER_TAG
FFMPEG_WIN_ZIP = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

DOWNLOADS = {
    # key: (網址, 解壓後要找的執行檔名, 放到 tools_dir() 底下哪個子夾)
    "whisper-win": (WHISPER_URL % "whisper-bin-x64.zip", "whisper-cli.exe", "whisper"),
    "whisper-linux-x64": (WHISPER_URL % "whisper-bin-ubuntu-x64.tar.gz", "whisper-cli", "whisper"),
    "whisper-linux-arm64": (WHISPER_URL % "whisper-bin-ubuntu-arm64.tar.gz", "whisper-cli", "whisper"),
    "ffmpeg-win": (FFMPEG_WIN_ZIP, "ffmpeg.exe", "ffmpeg"),
}


def download_key(base):
    """依平台與架構挑 DOWNLOADS 的 key；沒有對應的回 None（例如 ARM 版 Windows 沒有 whisper 預編譯檔）。"""
    if base == "whisper":
        if OS == "win":
            return None if IS_ARM else "whisper-win"
        if OS == "linux":
            return "whisper-linux-arm64" if IS_ARM else "whisper-linux-x64"
        return None
    if base == "ffmpeg":
        return "ffmpeg-win" if (OS == "win" and not IS_ARM) else None
    return None


TOOLS = {
    "node": {
        "label": "Node.js（Firebase CLI 要用它才能跑）", "required": True, "min_major": 20,
        "mac": ("brew", "node"), "win": ("winget", "OpenJS.NodeJS.LTS"), "linux": ("apt", "nodejs"),
        "url": "https://nodejs.org/",
    },
    "firebase": {
        "label": "Firebase CLI（部署安全規則與網站）", "required": True,
        "mac": ("npm", "firebase-tools"), "win": ("npm", "firebase-tools"), "linux": ("npm", "firebase-tools"),
        "url": "https://firebase.google.com/docs/cli",
    },
    "gcloud": {
        "label": "gcloud（本機腳本靠它拿權杖讀寫你自己的 Firestore）", "required": True,
        "mac": ("brew-cask", "google-cloud-sdk"), "win": ("winget", "Google.CloudSDK"), "linux": ("manual", ""),
        "url": "https://cloud.google.com/sdk/docs/install",
        "after": "裝完請跑一次：gcloud auth login（用你開 Firebase 專案的那個 Google 帳號）",
    },
    "vcredist": {
        "label": "Microsoft Visual C++ 執行階段（Windows 上 whisper 要它）", "required": False, "win_only": True,
        "mac": ("skip", ""), "win": ("winget", "Microsoft.VCRedist.2015+.x64"), "linux": ("skip", ""),
        "url": "https://aka.ms/vs/17/release/vc_redist.x64.exe",
    },
    "ffmpeg": {
        "label": "ffmpeg（錄音轉檔）", "required": False,
        "mac": ("brew", "ffmpeg"), "win": ("winget", "Gyan.FFmpeg"), "linux": ("apt", "ffmpeg"),
        "fallback": {"win": "ffmpeg"},
        "url": "https://ffmpeg.org/download.html",
    },
    "whisper-cli": {
        "label": "whisper.cpp（本機語音轉逐字稿，錄音不出本機）", "required": False,
        "mac": ("brew", "whisper-cpp"), "win": ("download", "whisper"), "linux": ("download", "whisper"),
        "url": "https://github.com/ggml-org/whisper.cpp/releases",
    },
    "gws": {
        "label": "Google Workspace CLI（只有備份走 gws 進階模式才需要）", "required": False, "optional_flag": "--with-gws",
        "mac": ("npm", "@googleworkspace/cli"), "win": ("npm", "@googleworkspace/cli"), "linux": ("npm", "@googleworkspace/cli"),
        "url": "https://github.com/googleworkspace/cli",
    },
}
TOOL_ORDER = ["node", "firebase", "gcloud", "vcredist", "ffmpeg", "whisper-cli", "gws"]


def install_hint(tool):
    """doctor.py 的「→ 怎麼修」：這個平台上一句話怎麼裝。"""
    spec = TOOLS.get(tool)
    if not spec:
        return ""
    method, arg = spec.get(OS if OS != "wsl" else "linux", ("manual", ""))
    flag = " " + spec["optional_flag"] if spec.get("optional_flag") else ""
    runner = "`%s scripts/install_tools.py%s`" % (PY, flag)
    if method == "brew":
        line = "brew install %s" % arg
    elif method == "brew-cask":
        line = "brew install --cask %s" % arg
    elif method == "winget":
        line = "winget install -e --id %s" % arg
    elif method == "apt":
        line = "sudo apt-get install -y %s" % arg
    elif method == "npm":
        line = "npm install -g %s" % arg
    elif method == "download":
        line = "由安裝腳本自動下載到 %s" % tools_dir()
    else:
        line = "照官方說明安裝：%s" % spec.get("url", "")
    return "%s（或一次裝齊：%s）" % (line, runner)


def summary():
    """健檢第一行用：這是哪種電腦、Python 怎麼叫、套件管理程式有沒有。"""
    pm = {"mac": "brew", "win": "winget", "linux": "apt-get", "wsl": "apt-get"}[OS]
    return {"os": OS, "os_label": OS_LABEL, "arch": ARCH, "python_cmd": PY,
            "python": sys.version.split()[0], "package_manager": pm,
            "package_manager_found": bool(shutil.which(pm)),
            "tools_dir": tools_dir(), "model_dir": model_dir(), "unsupported": unsupported_reason()}


if __name__ == "__main__":
    import json
    enable_console()
    print(json.dumps(dict(summary(), drive=drive_desktop_candidates(), chrome=chrome_candidates(),
                          tools={t: exe(t) for t in TOOL_ORDER}), ensure_ascii=False, indent=2))
