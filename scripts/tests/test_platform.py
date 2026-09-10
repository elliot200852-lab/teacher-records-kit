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
            url = "file://" + zpath.replace("\\", "/") if not zpath.startswith("/") else "file://" + zpath
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
