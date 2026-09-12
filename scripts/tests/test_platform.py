#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""跨平台層（hostos.py／install_tools.py／schedule.py）的測試。

兩種測法：
  · 純函式：直接改 hostos.OS 等模組變數模擬另一個平台（測邏輯分支）。
  · 子行程：用環境變數 TRK_FORCE_OS 讓腳本以另一個平台的身分跑 --dry-run（測整條印出來的路）。
真正在 Windows 上跑的是 CI（.github/workflows/ci.yml 的 windows-latest）；這裡的模擬只保證邏輯，不保證 winget。

跑法：python3 -m unittest discover scripts/tests
"""
import io
import os
import sys
import json
import shutil
import zipfile
import tempfile
import unittest
import subprocess
import xml.etree.ElementTree as ET

SCRIPTS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, SCRIPTS)
import hostos                       # noqa: E402
import install_tools                # noqa: E402
import schedule                     # noqa: E402


def run_script(script, *args, env=None, timeout=120):
    e = dict(os.environ)
    e.pop("TRK_FORCE_OS", None)
    e.update(env or {})
    return subprocess.run([sys.executable, os.path.join(SCRIPTS, script), *args],
                          capture_output=True, timeout=timeout, env=e)


class _Forced:
    """暫時把 hostos 當成另一個平台。"""

    def __init__(self, os_name):
        self.os_name = os_name

    def __enter__(self):
        self.saved = (hostos.OS, hostos.OS_LABEL, hostos.EXE_EXTS)
        hostos.OS = self.os_name
        hostos.OS_LABEL = {"mac": "macOS", "win": "Windows", "linux": "Linux", "wsl": "WSL"}[self.os_name]
        hostos.EXE_EXTS = (".exe", ".cmd", ".bat", ".com") if self.os_name == "win" else ("",)
        return self

    def __exit__(self, *a):
        hostos.OS, hostos.OS_LABEL, hostos.EXE_EXTS = self.saved


class DecodeAndRun(unittest.TestCase):
    def test_decode_utf8(self):
        self.assertEqual(hostos.decode_output("✓ 好".encode("utf-8")), "✓ 好")

    def test_decode_non_utf8_does_not_raise(self):
        out = hostos.decode_output("中文".encode("cp950"))
        self.assertIsInstance(out, str)
        self.assertTrue(out)

    def test_decode_none_and_str(self):
        self.assertEqual(hostos.decode_output(None), "")
        self.assertEqual(hostos.decode_output("x"), "x")

    def test_run_missing_tool_is_127(self):
        rc, out = hostos.run(["definitely-not-a-real-tool-xyz", "--version"])
        self.assertEqual(rc, 127)
        self.assertEqual(out, "")

    def test_run_real_python(self):
        rc, out = hostos.run([sys.executable, "-c", "print('hi')"])
        self.assertEqual(rc, 0)
        self.assertIn("hi", out)

    def test_cmd_metachar_guard_on_windows(self):
        d = tempfile.mkdtemp()
        try:
            fake = os.path.join(d, "gws.cmd")
            with open(fake, "w", encoding="utf-8") as f:
                f.write("@echo off\n")
            os.chmod(fake, 0o755)
            with _Forced("win"):
                rc, out = hostos.run([fake, "--subject", "A & B"])
                self.assertEqual(rc, 126)
                self.assertIn("特殊字元", out)
                rc, out = hostos.run([fake, "--body", "line1\nline2"])
                self.assertEqual(rc, 126)
                rc, out, err = hostos.run([fake, "--params", '{"fileId": "x"}'], split=True)
                self.assertNotEqual(rc, 126, "引號本身不該被擋（gws --params 的 JSON 要過）")
        finally:
            shutil.rmtree(d, ignore_errors=True)


class Exe(unittest.TestCase):
    def test_exe_finds_in_known_dirs_with_windows_ext(self):
        d = tempfile.mkdtemp()
        try:
            fake = os.path.join(d, "trk-fake-tool.cmd")
            with open(fake, "w", encoding="utf-8") as f:
                f.write("@echo off\n")
            os.chmod(fake, 0o755)
            saved = hostos._known_dirs
            hostos._known_dirs = lambda: [d]
            try:
                with _Forced("win"):
                    self.assertEqual(hostos.exe("trk-fake-tool"), fake)
                with _Forced("mac"):
                    self.assertIsNone(hostos.exe("gcloud-not-here"))
            finally:
                hostos._known_dirs = saved
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_exe_absolute_path(self):
        self.assertEqual(hostos.exe(sys.executable), sys.executable)
        self.assertIsNone(hostos.exe(os.path.join(tempfile.gettempdir(), "no-such-binary-xyz")))

    def test_refresh_path_adds_existing_known_dir(self):
        d = tempfile.mkdtemp()
        saved_known, saved_path = hostos._known_dirs, os.environ.get("PATH", "")
        hostos._known_dirs = lambda: [d, os.path.join(d, "nope")]
        try:
            hostos.refresh_path()
            self.assertIn(d, os.environ["PATH"].split(os.pathsep))
            self.assertNotIn(os.path.join(d, "nope"), os.environ["PATH"].split(os.pathsep))
        finally:
            hostos._known_dirs = saved_known
            os.environ["PATH"] = saved_path
            shutil.rmtree(d, ignore_errors=True)


class Drive(unittest.TestCase):
    def _with_home(self, fn):
        d = tempfile.mkdtemp()
        saved = os.environ.get("HOME"), os.environ.get("USERPROFILE")
        os.environ["HOME"] = d
        os.environ["USERPROFILE"] = d
        try:
            fn(d)
        finally:
            for k, v in (("HOME", saved[0]), ("USERPROFILE", saved[1])):
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            shutil.rmtree(d, ignore_errors=True)

    def test_mac_localised_root_found(self):
        def body(d):
            root = os.path.join(d, "Library", "CloudStorage", "GoogleDrive-a@b.c", "我的雲端硬碟")
            os.makedirs(root)
            with _Forced("mac"):
                self.assertEqual(hostos.drive_desktop_candidates(), [root])
                self.assertTrue(hostos.drive_desktop_hint("a@b.c").startswith(root))
        self._with_home(body)

    def test_win_userprofile_root_found_without_touching_drive_letters(self):
        def body(d):
            root = os.path.join(d, "My Drive")
            os.makedirs(root)
            saved = hostos._win_fixed_drives
            hostos._win_fixed_drives = lambda: []
            try:
                with _Forced("win"):
                    self.assertEqual(hostos.drive_desktop_candidates(), [root])
            finally:
                hostos._win_fixed_drives = saved
        self._with_home(body)

    def test_nothing_found_gives_platform_hint(self):
        def body(d):
            saved = hostos._win_fixed_drives
            hostos._win_fixed_drives = lambda: []
            try:
                with _Forced("win"):
                    self.assertEqual(hostos.drive_desktop_candidates(), [])
                    self.assertTrue(hostos.drive_desktop_hint().startswith("G:\\"))
                with _Forced("mac"):
                    self.assertIn("GoogleDrive-x@y.z", hostos.drive_desktop_hint("x@y.z"))
            finally:
                hostos._win_fixed_drives = saved
        self._with_home(body)


class ToolsTable(unittest.TestCase):
    def test_every_tool_has_every_platform(self):
        for name, spec in hostos.TOOLS.items():
            for o in ("mac", "win", "linux"):
                self.assertIn(o, spec, "%s 缺 %s" % (name, o))
                method, arg = spec[o]
                self.assertIn(method, ("brew", "brew-cask", "winget", "apt", "npm", "download", "manual", "skip"))
                if method == "download":
                    self.assertIn(arg, ("whisper", "ffmpeg"))
        for name in hostos.TOOL_ORDER:
            self.assertIn(name, hostos.TOOLS)

    def test_download_keys_resolve(self):
        saved = hostos.IS_ARM
        try:
            for o, arm, want in (("win", False, "whisper-win"), ("win", True, None),
                                 ("linux", False, "whisper-linux-x64"), ("linux", True, "whisper-linux-arm64"),
                                 ("mac", False, None)):
                hostos.IS_ARM = arm
                with _Forced(o):
                    self.assertEqual(hostos.download_key("whisper"), want, (o, arm))
                    if want:
                        self.assertIn(want, hostos.DOWNLOADS)
            hostos.IS_ARM = False
            with _Forced("win"):
                self.assertEqual(hostos.download_key("ffmpeg"), "ffmpeg-win")
            with _Forced("mac"):
                self.assertIsNone(hostos.download_key("ffmpeg"))
        finally:
            hostos.IS_ARM = saved

    def test_install_hint_mentions_installer_on_every_platform(self):
        for o in ("mac", "win", "linux"):
            with _Forced(o):
                for name in hostos.TOOL_ORDER:
                    h = hostos.install_hint(name)
                    self.assertIn("install_tools.py", h, (o, name))
        with _Forced("win"):
            self.assertIn("winget install -e --id OpenJS.NodeJS.LTS", hostos.install_hint("node"))
        with _Forced("mac"):
            self.assertIn("brew install --cask google-cloud-sdk", hostos.install_hint("gcloud"))

    def test_unsupported_only_for_wsl(self):
        for o in ("mac", "win", "linux"):
            with _Forced(o):
                self.assertEqual(hostos.unsupported_reason(), "")
        with _Forced("wsl"):
            self.assertIn("WSL", hostos.unsupported_reason())


class InstallTools(unittest.TestCase):
    def test_safe_members_rejects_traversal(self):
        with self.assertRaises(hostos.ToolError):
            install_tools._safe_members(["ok/x", "../evil"])
        with self.assertRaises(hostos.ToolError):
            install_tools._safe_members(["C:\\evil"])
        install_tools._safe_members(["Release/whisper-cli.exe", "a/b/c"])

    def test_install_download_flattens_zip_from_file_url(self):
        """完整走一遍：下載（file://）→ 解壓 → 找到執行檔 → 連同旁邊的 dll 攤平到 tools_dir/<sub>。"""
        d = tempfile.mkdtemp()
        try:
            zpath = os.path.join(d, "whisper-bin-x64.zip")
            with zipfile.ZipFile(zpath, "w") as z:
                z.writestr("Release/whisper-cli.exe", b"MZ fake")
                z.writestr("Release/ggml.dll", b"dll")
                z.writestr("Release/README.txt", b"hi")
            import pathlib
            url = pathlib.Path(zpath).as_uri()                 # Windows 是 file:///C:/…，mac 是 file:///…
            tools = os.path.join(d, "tools")
            saved_dl, saved_td, saved_dry = dict(hostos.DOWNLOADS), hostos.tools_dir, install_tools.DRY
            hostos.DOWNLOADS["test-whisper"] = (url, "whisper-cli.exe", "whisper")
            hostos.tools_dir = lambda: tools
            install_tools.DRY = False
            try:
                buf = io.StringIO()
                saved_out, sys.stdout = sys.stdout, buf
                try:
                    target = install_tools.install_download("test-whisper")
                finally:
                    sys.stdout = saved_out
                self.assertEqual(target, os.path.join(tools, "whisper", "whisper-cli.exe"))
                self.assertTrue(os.path.isfile(target))
                self.assertTrue(os.path.isfile(os.path.join(tools, "whisper", "ggml.dll")))
                self.assertFalse(os.path.exists(os.path.join(tools, "_stage-whisper")))
                self.assertFalse(any(f.startswith("_dl-") for f in os.listdir(tools)))
                # 再裝一次要能覆蓋，不能因為目的夾已存在而炸
                saved_out, sys.stdout = sys.stdout, io.StringIO()
                try:
                    install_tools.install_download("test-whisper")
                finally:
                    sys.stdout = saved_out
                self.assertTrue(os.path.isfile(target))
            finally:
                hostos.DOWNLOADS.clear()
                hostos.DOWNLOADS.update(saved_dl)
                hostos.tools_dir = saved_td
                install_tools.DRY = saved_dry
        finally:
            shutil.rmtree(d, ignore_errors=True)

    def test_dry_run_on_each_forced_platform_exits_zero(self):
        for o in ("mac", "win", "linux"):
            r = run_script("install_tools.py", "--dry-run", "--json", env={"TRK_FORCE_OS": o})
            self.assertEqual(r.returncode, 0, (o, r.stdout.decode("utf-8", "replace")[-800:], r.stderr))
            out = r.stdout.decode("utf-8", "replace")
            data = json.loads(out[out.index("{"):])
            self.assertEqual(data["os"], o)
            self.assertEqual(data["failed"], [])
            self.assertNotIn("gws", [k for k, v in data["results"].items() if v["status"] != "skipped"])
        r = run_script("install_tools.py", "--dry-run", env={"TRK_FORCE_OS": "win"})
        self.assertIn("vcredist", r.stdout.decode("utf-8", "replace"))

    def test_wsl_is_refused(self):
        r = run_script("install_tools.py", "--dry-run", env={"TRK_FORCE_OS": "wsl"})
        self.assertEqual(r.returncode, 1)
        self.assertIn("WSL", r.stderr.decode("utf-8", "replace"))


class AgentClis(unittest.TestCase):
    """AI 代理的 CLI 表（hostos.AGENT_CLIS）與 install_tools.py --agent。"""

    def test_every_agent_has_every_platform(self):
        for name, spec in hostos.AGENT_CLIS.items():
            self.assertTrue(spec.get("cmd"), name)
            self.assertIn("%s", spec.get("launch", ""), "%s 的 launch 要有放提示詞的位置" % name)
            self.assertTrue(spec.get("url", "").startswith("https://"), name)
            for o in ("mac", "win", "linux"):
                self.assertIn(o, spec, "%s 缺 %s" % (name, o))
                method, arg = spec[o]
                self.assertIn(method, ("brew", "brew-cask", "winget", "npm", "sh-installer", "ps-installer"))
                self.assertTrue(arg, (name, o))
                fb = (spec.get("fallback") or {}).get(o)
                if fb:
                    self.assertIn(fb[0], ("brew", "brew-cask", "winget", "npm", "sh-installer", "ps-installer"))
        for name in hostos.AGENT_ORDER:
            self.assertIn(name, hostos.AGENT_CLIS)

    def test_method_and_fallback_per_platform(self):
        for o in ("mac", "win", "linux"):
            with _Forced(o):
                self.assertEqual(hostos.agent_method("claude")[0],
                                 "winget" if o == "win" else "sh-installer")
                self.assertEqual(hostos.agent_method("gemini"),
                                 ("brew", "gemini-cli") if o == "mac" else ("npm", "@google/gemini-cli"))
        with _Forced("win"):
            self.assertEqual(hostos.agent_fallback("claude"), ("ps-installer", "https://claude.ai/install.ps1"))
        with _Forced("mac"):
            self.assertEqual(hostos.agent_fallback("claude"), ("brew-cask", "claude-code"))
        with _Forced("wsl"):                      # WSL 借用 linux 那一欄（實際上 install_tools 會先拒跑）
            self.assertEqual(hostos.agent_method("codex")[0], "sh-installer")

    def test_method_line_renders_every_method(self):
        self.assertEqual(hostos.method_line("npm", "x"), "npm install -g x")
        self.assertEqual(hostos.method_line("winget", "A.B"), "winget install -e --id A.B")
        self.assertEqual(hostos.method_line("sh-installer", "https://u"), "curl -fsSL https://u | bash")
        self.assertEqual(hostos.method_line("ps-installer", "https://u"), "irm https://u | iex")
        self.assertEqual(hostos.method_line("manual", ""), "")

    def test_install_hint_and_launch(self):
        for o in ("mac", "win", "linux"):
            with _Forced(o):
                for name in hostos.AGENT_ORDER:
                    h = hostos.agent_install_hint(name)
                    self.assertIn("install_tools.py --agent %s" % name, h, (o, name))
                    self.assertIn("AGENTS.md", hostos.agent_launch(name))
        self.assertTrue(hostos.agent_launch("gemini").startswith("gemini -i "))
        self.assertTrue(hostos.agent_launch("claude").startswith('claude "'))
        self.assertEqual(hostos.agent_launch("沒這個代理"), "")

    def test_agent_dry_run_renders_on_each_forced_platform(self):
        """--agent 在三個平台的 dry-run：印出來的那一行就是那個平台真的會跑的指令。"""
        want = {
            ("mac", "claude"): "curl -fsSL https://claude.ai/install.sh | bash",
            ("win", "claude"): "winget install -e --id Anthropic.ClaudeCode",
            ("linux", "claude"): "curl -fsSL https://claude.ai/install.sh | bash",
            ("mac", "codex"): "curl -fsSL https://chatgpt.com/codex/install.sh | bash",
            ("win", "codex"): "npm install -g @openai/codex",
            ("linux", "codex"): "curl -fsSL https://chatgpt.com/codex/install.sh | bash",
            ("mac", "gemini"): "brew install gemini-cli",
            ("win", "gemini"): "npm install -g @google/gemini-cli",
            ("linux", "gemini"): "npm install -g @google/gemini-cli",
        }
        for (o, agent), line in want.items():
            r = run_script("install_tools.py", "--dry-run", "--json", "--agent", agent, env={"TRK_FORCE_OS": o})
            out = r.stdout.decode("utf-8", "replace")
            self.assertEqual(r.returncode, 0, (o, agent, out[-800:], r.stderr))
            self.assertIn(line, out, (o, agent))
            data = json.loads(out[out.index("{"):])
            self.assertEqual(data["agent"]["name"], agent)
            self.assertIn(data["agent"]["status"], ("ok", "would-install"))
            self.assertIn("AGENTS.md", data["agent"]["launch"])
            self.assertEqual(data["failed"], [])

    def test_no_agent_flag_means_no_agent_in_json(self):
        r = run_script("install_tools.py", "--dry-run", "--json", env={"TRK_FORCE_OS": "mac"})
        out = r.stdout.decode("utf-8", "replace")
        self.assertIsNone(json.loads(out[out.index("{"):])["agent"])

    def test_bad_agent_name_is_rejected(self):
        r = run_script("install_tools.py", "--dry-run", "--agent", "chatgpt")
        self.assertEqual(r.returncode, 2)


class Bootstrap(unittest.TestCase):
    """Python 還沒裝好那一層（setup/bootstrap.*）：唯一准許重複平台事實的地方，所以要守著它別漂掉。"""
    REPO = os.path.dirname(SCRIPTS)
    SH = os.path.join(REPO, "setup", "bootstrap.sh")
    PS1 = os.path.join(REPO, "setup", "bootstrap.ps1")
    CMD = os.path.join(REPO, "setup", "bootstrap.cmd")

    def test_files_exist_with_right_shape(self):
        for p in (self.SH, self.PS1, self.CMD):
            self.assertTrue(os.path.isfile(p), p)
            with open(p, "rb") as f:
                raw = f.read()
            self.assertNotIn(b"\r\n", raw, "%s 不可以是 CRLF（.gitattributes 鎖 LF）" % p)
        with open(self.PS1, "rb") as f:
            self.assertTrue(f.read(3) == b"\xef\xbb\xbf", "bootstrap.ps1 要有 UTF-8 BOM，PowerShell 5.1 才讀得對中文")
        with open(self.CMD, "rb") as f:
            f.read().decode("ascii")                      # .cmd 只准 ASCII（cmd.exe 的編碼很難搞）
        self.assertTrue(os.access(self.SH, os.X_OK), "bootstrap.sh 要可執行")

    def test_shell_script_parses(self):
        r = subprocess.run(["bash", "-n", self.SH], capture_output=True, timeout=60)
        self.assertEqual(r.returncode, 0, r.stderr.decode("utf-8", "replace"))

    def test_bootstrap_matches_the_agent_table(self):
        """bootstrap 是 AGENT_CLIS 的手抄本：每一家在每個平台要裝的東西都得出現在對應的腳本裡。"""
        with open(self.SH, encoding="utf-8") as f:
            sh = f.read()
        with open(self.PS1, encoding="utf-8-sig") as f:
            ps1 = f.read()
        for name, spec in hostos.AGENT_CLIS.items():
            for o, text, where in (("mac", sh, "bootstrap.sh"), ("linux", sh, "bootstrap.sh"),
                                   ("win", ps1, "bootstrap.ps1")):
                arg = spec[o][1]
                self.assertIn(arg, text, "%s 的 %s 安裝方式（%s）沒寫進 %s" % (name, o, arg, where))
                fb = (spec.get("fallback") or {}).get(o)
                if fb:
                    self.assertIn(fb[1], text, "%s 的 %s 備案（%s）沒寫進 %s" % (name, o, fb[1], where))
        for text, where in ((sh, "bootstrap.sh"), (ps1, "bootstrap.ps1")):
            self.assertIn(hostos.AGENT_STARTER_PROMPT, text, "起手提示詞沒寫進 %s" % where)
            self.assertIn("install_tools.py", text, "%s 最後要回頭跑 install_tools.py" % where)
            self.assertIn("doctor.py", text, "%s 最後要跑健檢" % where)

    def test_dry_run_installs_nothing(self):
        """--dry-run 不准動這台電腦：不寫檔、不裝東西，而且要印出「將會跑」。"""
        if hostos.OS not in ("mac", "linux"):
            self.skipTest("bootstrap.sh 只在 macOS／Linux 上跑")
        home_files = {}
        for f in (".zprofile", ".bash_profile"):
            p = os.path.join(os.path.expanduser("~"), f)
            home_files[p] = os.path.getmtime(p) if os.path.exists(p) else None
        r = subprocess.run(["bash", self.SH, "--dry-run", "--agent", "none", "--yes"],
                           capture_output=True, timeout=300, cwd=tempfile.gettempdir())
        out = r.stdout.decode("utf-8", "replace")
        self.assertEqual(r.returncode, 0, out[-800:] + r.stderr.decode("utf-8", "replace")[-800:])
        self.assertIn("--dry-run", out)
        self.assertIn("AGENTS.md", out)
        for p, mtime in home_files.items():
            now = os.path.getmtime(p) if os.path.exists(p) else None
            self.assertEqual(mtime, now, "%s 被 --dry-run 改到了" % p)

    def test_bad_flag_is_rejected(self):
        if hostos.OS not in ("mac", "linux"):
            self.skipTest("bootstrap.sh 只在 macOS／Linux 上跑")
        r = subprocess.run(["bash", self.SH, "--agent", "copilot"], capture_output=True, timeout=60)
        self.assertEqual(r.returncode, 2)
        r = subprocess.run(["bash", self.SH, "--nope"], capture_output=True, timeout=60)
        self.assertEqual(r.returncode, 2)


class Schedule(unittest.TestCase):
    def test_hhmm(self):
        self.assertEqual(schedule.hhmm("07:00"), (7, 0))
        self.assertEqual(schedule.hhmm("6:30"), (6, 30))
        for bad in ("7", "25:00", "07:60", "", "abc"):
            with self.assertRaises(SystemExit):
                schedule.hhmm(bad)

    def test_cron_lines(self):
        a, b = schedule.cron_lines((7, 0), 0, (8, 0))
        self.assertTrue(a.startswith("0 7 * * * cd "))
        self.assertTrue(b.startswith("0 8 * * 0 cd "))
        self.assertIn("scripts/sync.py >> logs/sync.log 2>&1", a)
        self.assertIn("scripts/backup.py --quiet >> logs/backup.log 2>&1", b)

    def test_windows_task_xml_is_valid_and_complete(self):
        saved = os.environ.get("USERDOMAIN"), os.environ.get("USERNAME")
        os.environ["USERDOMAIN"], os.environ["USERNAME"] = "PC", "王 小明"
        try:
            for job, wd in (("sync", None), ("backup", 0)):
                xml = schedule.win_task_xml(job, 7, 5, wd)
                root = ET.fromstring(xml.encode("utf-16"))       # 檔案是 UTF-16 存的，這裡照樣解一次
                ns = {"t": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
                self.assertEqual(root.find("t:Settings/t:StartWhenAvailable", ns).text, "true")
                self.assertEqual(root.find("t:Principals/t:Principal/t:UserId", ns).text, "PC\\王 小明")
                args = root.find("t:Actions/t:Exec/t:Arguments", ns).text
                self.assertIn(job + ".py", args)
                self.assertIn(sys.executable, args)
                self.assertIn("logs", args)
                self.assertEqual(root.find("t:Actions/t:Exec/t:WorkingDirectory", ns).text, schedule.REPO)
                self.assertIn("T07:05:00", root.find("t:Triggers/t:CalendarTrigger/t:StartBoundary", ns).text)
                if wd is None:
                    self.assertIsNotNone(root.find("t:Triggers/t:CalendarTrigger/t:ScheduleByDay", ns))
                else:
                    self.assertIsNotNone(root.find("t:Triggers/t:CalendarTrigger/t:ScheduleByWeek/t:DaysOfWeek/t:Sunday", ns))
        finally:
            for k, v in (("USERDOMAIN", saved[0]), ("USERNAME", saved[1])):
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def test_mac_plist_shape(self):
        p = schedule.mac_plist("backup", 8, 0, 0)
        self.assertEqual(p["StartCalendarInterval"], {"Hour": 8, "Minute": 0, "Weekday": 0})
        self.assertEqual(p["ProgramArguments"][0], sys.executable)
        self.assertTrue(p["ProgramArguments"][1].endswith("backup.py"))
        self.assertIn("--quiet", p["ProgramArguments"])
        self.assertNotIn("Weekday", schedule.mac_plist("sync", 7, 0)["StartCalendarInterval"])

    def test_linux_strip_round_trip(self):
        body = "0 1 * * * echo keep\n" + schedule.CRON_MARK_BEGIN + "\nx\ny\n" + schedule.CRON_MARK_END + "\n0 2 * * * echo keep2"
        self.assertEqual(schedule.linux_strip(body), "0 1 * * * echo keep\n0 2 * * * echo keep2")
        self.assertEqual(schedule.linux_strip(""), "")

    def test_dry_run_on_each_forced_platform(self):
        for o, marker in (("mac", "launchctl bootstrap"), ("win", "schtasks /Create /F /TN"), ("linux", "crontab")):
            r = run_script("schedule.py", "--dry-run", env={"TRK_FORCE_OS": o})
            out = r.stdout.decode("utf-8", "replace")
            self.assertEqual(r.returncode, 0, (o, out[-600:], r.stderr))
            self.assertIn(marker, out, o)
        r = run_script("schedule.py", "--print-cron", env={"TRK_FORCE_OS": "win"})
        self.assertEqual(r.returncode, 0)
        self.assertIn("* * 0 cd", r.stdout.decode("utf-8", "replace"))
        r = run_script("schedule.py", "--dry-run", "--sync-time", "9:99")
        self.assertEqual(r.returncode, 1)

    def test_dry_run_writes_nothing(self):
        launchers = os.path.join(schedule.REPO, "setup", "launchers")
        before = set(os.listdir(launchers)) if os.path.isdir(launchers) else None
        r = run_script("schedule.py", "--dry-run", env={"TRK_FORCE_OS": "win"})
        self.assertEqual(r.returncode, 0)
        after = set(os.listdir(launchers)) if os.path.isdir(launchers) else None
        self.assertEqual(before, after)


class _Capture:
    """把 stdout／stderr 收起來（測試印出來的東西要用、也不要洗版）。"""

    def __enter__(self):
        self.saved = (sys.stdout, sys.stderr)
        self.out, self.err = io.StringIO(), io.StringIO()
        sys.stdout, sys.stderr = self.out, self.err
        return self

    def __exit__(self, *a):
        sys.stdout, sys.stderr = self.saved

    @property
    def text(self):
        return self.out.getvalue() + self.err.getvalue()


class _Patch:
    """暫時換掉模組屬性，離開時換回來。"""

    def __init__(self, mod, **kw):
        self.mod, self.kw = mod, kw

    def __enter__(self):
        self.saved = {k: getattr(self.mod, k) for k in self.kw}
        for k, v in self.kw.items():
            setattr(self.mod, k, v)
        return self

    def __exit__(self, *a):
        for k, v in self.saved.items():
            setattr(self.mod, k, v)


class PythonCmd(unittest.TestCase):
    """Windows 上「該怎麼叫 Python」：py 啟動器要真的跑得出 3.x 才算數。"""

    def setUp(self):
        hostos._py_launcher_ok = None

    def tearDown(self):
        hostos._py_launcher_ok = None

    def _fake_run(self, rc, out):
        class R:
            returncode = rc
            stdout = out

        def run(argv, **kw):
            self.ran.append(argv)
            return R()
        self.ran = []
        return run

    def test_py_launcher_without_any_real_python_is_not_trusted(self):
        """`py` 在，但 `py -3` 回 103（沒註冊任何 3.x）——不能印 `py -3` 給老師。"""
        with _Forced("win"):
            with _Patch(hostos,
                        shutil=type("S", (), {"which": staticmethod(
                            lambda n: r"C:\\Windows\\py.exe" if n == "py" else
                            (r"C:\\Python313\\python.exe" if n == "python" else None))}),
                        subprocess=type("P", (), {"run": staticmethod(self._fake_run(103, b"")),
                                                  "SubprocessError": subprocess.SubprocessError})):
                self.assertFalse(hostos._py_launcher_works())
                self.assertEqual(hostos.python_cmd(), "python")
        self.assertEqual(len(self.ran), 1, "py -3 應該只被跑一次（結果要快取）")

    def test_py_launcher_with_a_real_python_is_trusted(self):
        with _Forced("win"):
            with _Patch(hostos,
                        shutil=type("S", (), {"which": staticmethod(
                            lambda n: r"C:\\Windows\\py.exe" if n == "py" else None)}),
                        subprocess=type("P", (), {"run": staticmethod(
                            self._fake_run(0, br"C:\Python313\python.exe")),
                            "SubprocessError": subprocess.SubprocessError})):
                self.assertTrue(hostos._py_launcher_works())
                self.assertEqual(hostos.python_cmd(), "py -3")
                hostos.python_cmd()                      # 第二次不該再跑子行程
        self.assertEqual(len(self.ran), 1)

    def test_py_launcher_pointing_at_the_store_shim_is_not_trusted(self):
        with _Forced("win"):
            with _Patch(hostos,
                        shutil=type("S", (), {"which": staticmethod(
                            lambda n: r"C:\\Users\\x\\AppData\\Local\\Microsoft\\WindowsApps\\py.exe"
                            if n == "py" else None)}),
                        subprocess=type("P", (), {"run": staticmethod(self._fake_run(0, b"")),
                                                  "SubprocessError": subprocess.SubprocessError})):
                self.assertFalse(hostos._py_launcher_works())
        self.assertEqual(self.ran, [], "住在 WindowsApps 的 py 連跑都不用跑")

    def test_non_windows_never_spawns_anything(self):
        for o in ("mac", "linux"):
            with _Forced(o):
                self.assertEqual(hostos.python_cmd(), "python3")

    def test_store_alias_detection(self):
        alias = "C:\\Users\\王小明\\AppData\\Local\\Microsoft\\WindowsApps\\python.exe"
        self.assertTrue(hostos.python_is_store_alias(alias))
        self.assertTrue(hostos.python_is_store_alias(alias.replace("\\", "/")))
        self.assertFalse(hostos.python_is_store_alias(r"C:\Python313\python.exe"))
        self.assertFalse(hostos.python_is_store_alias("/usr/bin/python3"))


class WingetExitCodes(unittest.TestCase):
    """winget 的「其實沒事」退出碼家族（0x8A15002B 與 -1978335189 是同一個值）。"""

    def test_ok_family(self):
        for rc in (0, 3010, 0x8A15002B, -1978335189, 0x8A150061, -1978335135):
            self.assertTrue(install_tools.winget_rc_is_ok(rc), rc)
        self.assertEqual(0x8A15002B & 0xFFFFFFFF, -1978335189 & 0xFFFFFFFF)

    def test_real_failures_are_still_failures(self):
        for rc in (1, 2, -1978335216, 0x8A150011, None, "x"):
            self.assertFalse(install_tools.winget_rc_is_ok(rc), rc)


class VcRedist(unittest.TestCase):
    """VC++ 執行階段：兩個 dll 都要，而且只有 hostos 這一份判斷。"""

    def _with_sysroot(self, dlls):
        d = tempfile.mkdtemp()
        os.makedirs(os.path.join(d, "System32"))
        for name in dlls:
            open(os.path.join(d, "System32", name), "w").close()
        return d

    def test_needs_both_dlls(self):
        for have, want_ok in ((("vcruntime140.dll",), False),
                              (("vcruntime140.dll", "vcruntime140_1.dll"), True),
                              ((), False)):
            root = self._with_sysroot(have)
            try:
                saved = os.environ.get("SystemRoot")
                os.environ["SystemRoot"] = root
                with _Forced("win"):
                    ok, detail = hostos.vcredist_present()
                self.assertEqual(ok, want_ok, (have, detail))
                if not want_ok:
                    self.assertIn("vcruntime140_1.dll" if have else "vcruntime140.dll", detail)
            finally:
                if saved is None:
                    os.environ.pop("SystemRoot", None)
                else:
                    os.environ["SystemRoot"] = saved
                shutil.rmtree(root, ignore_errors=True)

    def test_not_windows_is_always_fine(self):
        for o in ("mac", "linux"):
            with _Forced(o):
                self.assertEqual(hostos.vcredist_present()[0], True)

    def test_only_one_implementation(self):
        """doctor.py 與 install_tools.py 都不准自己再驗一次 dll。"""
        for f in ("doctor.py", "install_tools.py"):
            with open(os.path.join(SCRIPTS, f), encoding="utf-8") as fh:
                src = fh.read()
            self.assertNotIn("vcruntime140", src, "%s 應該改問 hostos.vcredist_present()" % f)
            self.assertIn("vcredist_present", src, f)


class AgentFallbackRunsOnce(unittest.TestCase):
    """主要方式沒成才走備案，而且**只走一次**。"""

    def test_fallback_is_attempted_exactly_once(self):
        calls = []

        def fake_install_via(method, arg):
            calls.append((method, arg))
            return (None, "沒有那條路") if len(calls) == 1 else (1, "備案也失敗")

        with _Forced("mac"), _Patch(install_tools, DRY=False, install_via=fake_install_via), \
                _Patch(hostos, exe=lambda n: None):
            with _Capture():
                r = install_tools.install_agent("claude")
        self.assertEqual(r["status"], "failed")
        self.assertEqual(len(calls), 2, "主要 1 次 ＋ 備案 1 次；備案被跑第二次就是這個 bug")
        self.assertEqual(calls[0], hostos.agent_method("claude", "mac"))
        self.assertEqual(calls[1], hostos.agent_fallback("claude", "mac"))

    def test_no_fallback_platform_only_tries_once(self):
        calls = []

        def fake_install_via(method, arg):
            calls.append((method, arg))
            return (None, "沒有那條路")

        with _Forced("linux"), _Patch(install_tools, DRY=False, install_via=fake_install_via), \
                _Patch(hostos, exe=lambda n: None):
            with _Capture():
                install_tools.install_agent("claude")     # linux 的 fallback 是 None
        self.assertEqual(len(calls), 1)


class WorkDir(unittest.TestCase):
    """外部工具的暫存工作夾：路徑一定是 ASCII（whisper-cli.exe 吃窄字元 argv）。"""

    def test_default_is_under_cache_dir_and_exists(self):
        d = hostos.work_dir()
        self.assertTrue(os.path.isdir(d))
        self.assertEqual(hostos.work_dir_warning(), "")
        self.assertTrue(d.startswith(hostos.cache_dir()))

    def test_windows_cjk_username_falls_back_to_programdata(self):
        base = tempfile.mkdtemp()
        cjk = os.path.join(base, "使用者", "teacher-records-kit")
        pd = os.path.join(base, "ProgramData")
        saved = os.environ.get("ProgramData")
        os.environ["ProgramData"] = pd
        try:
            with _Forced("win"), _Patch(hostos, cache_dir=lambda: cjk):
                d = hostos.work_dir()
            self.assertTrue(hostos._is_ascii(d), d)
            self.assertTrue(d.startswith(pd), d)
            self.assertTrue(os.path.isdir(d))
            self.assertEqual(hostos.work_dir_warning(), "")
        finally:
            if saved is None:
                os.environ.pop("ProgramData", None)
            else:
                os.environ["ProgramData"] = saved
            shutil.rmtree(base, ignore_errors=True)

    def test_warns_when_no_ascii_path_is_writable(self):
        base = tempfile.mkdtemp()
        cjk = os.path.join(base, "使用者", "teacher-records-kit")
        saved = os.environ.get("ProgramData")
        os.environ["ProgramData"] = os.path.join(base, "不能寫的地方")     # 也不是 ASCII → 兩條都不行
        try:
            with _Forced("win"), _Patch(hostos, cache_dir=lambda: cjk):
                d = hostos.work_dir()
                warn = hostos.work_dir_warning()
            self.assertTrue(os.path.isdir(d))
            self.assertIn("ASCII", warn)
        finally:
            if saved is None:
                os.environ.pop("ProgramData", None)
            else:
                os.environ["ProgramData"] = saved
            shutil.rmtree(base, ignore_errors=True)


class Transcribe(unittest.TestCase):
    """transcribe.py 不准自己 subprocess.run（沒有逾時、沒有 .cmd 閘），暫存也不准放 %TEMP%。"""

    def setUp(self):
        with open(os.path.join(SCRIPTS, "transcribe.py"), encoding="utf-8") as f:
            self.src = f.read()

    def test_external_tools_go_through_hostos_run(self):
        self.assertNotIn("subprocess.run", self.src)
        self.assertNotIn("import subprocess", self.src)
        self.assertIn("hostos.run(", self.src)

    def test_every_external_call_has_a_timeout(self):
        import re
        calls = re.findall(r"hostos\.run\((.{0,400}?)\)\n", self.src, re.S)
        self.assertTrue(calls)
        for c in calls:
            self.assertIn("timeout=", c, c[:120])

    def test_scratch_lives_under_work_dir_not_system_temp(self):
        self.assertIn("hostos.work_dir()", self.src)
        self.assertIn("dir=work", self.src)

    def test_model_urls_come_from_hostos(self):
        import transcribe                                  # noqa: E402
        self.assertEqual(transcribe.MODEL_URL, hostos.WHISPER_MODEL_URL)
        self.assertEqual(transcribe.VAD_URL, hostos.WHISPER_VAD_URL)
        self.assertIn(("model:vad"), [n for n, _, _ in hostos.ALL_URLS()])


class KillTree(unittest.TestCase):
    def test_windows_uses_taskkill_tree_and_never_really_runs_it(self):
        seen = []

        class R:
            returncode = 0

        def fake_run(argv, **kw):
            seen.append(argv)
            return R()

        with _Forced("win"), _Patch(hostos, subprocess=type("P", (), {
                "run": staticmethod(fake_run), "SubprocessError": subprocess.SubprocessError})):
            self.assertTrue(hostos.kill_tree(4242))
        self.assertEqual(seen, [["taskkill", "/T", "/F", "/PID", "4242"]])

    def test_bad_pid_is_false_not_an_exception(self):
        self.assertFalse(hostos.kill_tree(None))
        self.assertFalse(hostos.kill_tree("not-a-pid"))

    @unittest.skipIf(os.name != "posix", "POSIX 才有 process group")
    def test_posix_kills_the_whole_group(self):
        p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                             start_new_session=True,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            self.assertTrue(hostos.kill_tree(p))
            self.assertIsNotNone(p.poll())
        finally:
            if p.poll() is None:
                p.kill()
                p.wait(timeout=10)


class ScheduleRefusesStorePython(unittest.TestCase):
    """排程用的是 sys.executable；那是 Store 假殼的話，掛上去也永遠不會跑——寧可拒絕。"""

    def _main_with(self, python_path, argv):
        saved_py, saved_argv, saved_dry = schedule.PYTHON, sys.argv, schedule.DRY
        schedule.PYTHON = python_path
        sys.argv = argv
        try:
            with _Capture() as cap:
                try:
                    schedule.main()
                    code = 0
                except SystemExit as e:
                    code = e.code
            return code, cap.text
        finally:
            schedule.PYTHON, sys.argv, schedule.DRY = saved_py, saved_argv, saved_dry

    def test_store_alias_python_is_refused(self):
        code, text = self._main_with(
            r"C:\Users\x\AppData\Local\Microsoft\WindowsApps\python.exe",
            ["schedule.py", "--dry-run"])
        self.assertEqual(code, 1)
        self.assertIn("WindowsApps", text)
        self.assertIn("python.org", text)

    def test_a_real_python_is_not_refused(self):
        code, text = self._main_with(sys.executable, ["schedule.py", "--dry-run"])
        self.assertEqual(code, 0, text[-400:])
        self.assertNotIn("WindowsApps", text)


class DownloadsAndUrls(unittest.TestCase):
    """DOWNLOADS 的 sha256 欄位與 CI 每週要打的網址清單。"""

    def test_every_entry_normalises_to_four_fields(self):
        for k in hostos.DOWNLOADS:
            url, exe_name, sub, sha = hostos.download_entry(k)
            self.assertTrue(url.startswith("http"), k)
            self.assertTrue(exe_name and sub, k)
            if sha is not None:
                self.assertRegex(sha, r"^[0-9a-f]{64}$", k)

    def test_pinned_tag_downloads_are_pinned_by_hash(self):
        """釘死 tag 的 whisper 三包內容不會變，一定要有 sha256；
        ffmpeg 是滾動網址（同一個 URL 內容會變），刻意留 None。"""
        for k in ("whisper-win", "whisper-linux-x64", "whisper-linux-arm64"):
            self.assertIsNotNone(hostos.download_entry(k)[3], k)
        self.assertIsNone(hostos.download_entry("ffmpeg-win")[3])

    def test_three_field_entries_still_work(self):
        saved = dict(hostos.DOWNLOADS)
        try:
            hostos.DOWNLOADS["legacy"] = ("https://x/y.zip", "y.exe", "y")
            self.assertEqual(hostos.download_entry("legacy")[3], None)
        finally:
            hostos.DOWNLOADS.clear()
            hostos.DOWNLOADS.update(saved)

    def test_all_urls_covers_downloads_and_the_speech_models(self):
        urls = {n: u for n, u, _ in hostos.ALL_URLS()}
        for k in hostos.DOWNLOADS:
            self.assertIn("download:" + k, urls)
        self.assertIn("model:" + hostos.WHISPER_MODEL_DEFAULT, urls)
        self.assertIn("model:vad", urls)
        for u in urls.values():
            self.assertTrue(u.startswith("https://"), u)

    def test_download_rejects_a_wrong_hash(self):
        """雜湊對不上就不寫出檔案，也不留 .part。"""
        d = tempfile.mkdtemp()
        try:
            src = os.path.join(d, "src.bin")
            with open(src, "wb") as f:
                f.write(b"hello")
            import pathlib
            url = pathlib.Path(src).as_uri()
            dest = os.path.join(d, "out.bin")
            with _Capture():
                with self.assertRaises(hostos.ToolError):
                    install_tools.download(url, dest, "0" * 64)
            self.assertFalse(os.path.exists(dest))
            self.assertFalse(os.path.exists(dest + ".part"))
            import hashlib
            with _Capture():
                install_tools.download(url, dest, hashlib.sha256(b"hello").hexdigest())
            self.assertTrue(os.path.exists(dest))
        finally:
            shutil.rmtree(d, ignore_errors=True)


class ExportDocsKillsTheTree(unittest.TestCase):
    def test_export_docs_uses_kill_tree_and_a_new_session(self):
        with open(os.path.join(SCRIPTS, "export_docs.py"), encoding="utf-8") as f:
            src = f.read()
        self.assertIn("hostos.kill_tree(", src)
        self.assertIn("start_new_session", src)
        self.assertNotIn("proc.kill()", src)


class LineEndings(unittest.TestCase):
    def test_no_text_write_without_lf_newline(self):
        """所有寫文字檔的 open(..., "w"/"a", encoding="utf-8") 都要帶 newline="\\n"，
        不然 Windows 會寫成 CRLF，記錄的內容雜湊就跟 mac 對不上。"""
        import re
        bad = []
        for f in os.listdir(SCRIPTS):
            if not f.endswith(".py"):
                continue
            with open(os.path.join(SCRIPTS, f), encoding="utf-8") as fh:
                for i, line in enumerate(fh, 1):
                    if "open(" in line and re.search(r'"[wa]",\s*encoding="utf-8"\)', line) and "newline=" not in line:
                        bad.append("%s:%d" % (f, i))
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
