#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""schedule.py — （選用）排程：每天同步、每週備份（macOS launchd／Windows 工作排程器／Linux cron 同一支）。

排程可能會靜默失敗（電腦沒開機、系統擋權限），所以本 kit 的網頁頂端會顯示「上次同步／備份幾天前」，
真正要驗證排程有沒有生效請看那個數字，不要只看 --status 顯示有掛就以為它真的跑得動。

用法：
  python3 scripts/schedule.py              安裝兩個排程（每天 07:00 同步、每週日 08:00 備份）
  python3 scripts/schedule.py --dry-run    只印會做的事，不寫檔、不安裝
  python3 scripts/schedule.py --status     看排程掛了沒、上次跑的結果
  python3 scripts/schedule.py --print-cron 只印等效的 crontab 兩行，不寫任何檔案
  python3 scripts/schedule.py --uninstall  移除排程並刪掉產生的檔
  python3 scripts/schedule.py --sync-time 06:30 --backup-day 6 --backup-time 21:00
                                           改時間（backup-day：0＝週日 … 6＝週六）

各平台怎麼做：
  macOS    ~/Library/LaunchAgents/com.teacher-records-kit.{sync,backup}.plist（launchctl bootstrap）
  Windows  工作排程器 \\TeacherRecordsKit\\{Sync,Backup}，定義檔寫在 setup/launchers/*.xml（schtasks /Create /XML）
           — 用的是現在這個 Python（sys.executable），電腦沒開時錯過的那次會在下次開機補跑
  Linux    crontab（在你的 crontab 裡加兩行、用註解標記包起來）
log 一律在 logs/sync.log 與 logs/backup.log。零第三方相依。
"""
import os
import re
import sys
import argparse
import datetime
import plistlib
from xml.sax.saxutils import escape

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib          # noqa: E402
import hostos       # noqa: E402

OS = hostos.OS
REPO = lib.PKG
LOGS = os.path.join(REPO, "logs")
LAUNCHERS = os.path.join(REPO, "setup", "launchers")
PYTHON = sys.executable
CRON_MARK_BEGIN = "# >>> teacher-records-kit（schedule.py 產生，不要手改這一段）"
CRON_MARK_END = "# <<< teacher-records-kit"

JOBS = {
    "sync": {"script": "sync.py", "args": [], "label": "com.teacher-records-kit.sync",
             "win_name": r"TeacherRecordsKit\Sync", "desc": "每天同步本機記錄與資料庫", "network": True},
    "backup": {"script": "backup.py", "args": ["--quiet"], "label": "com.teacher-records-kit.backup",
               "win_name": r"TeacherRecordsKit\Backup", "desc": "每週備份到你自己的 Google 雲端硬碟", "network": False},
}
DRY = False


def hhmm(s):
    m = re.match(r"^(\d{1,2}):(\d{2})$", s or "")
    if not m or not (0 <= int(m.group(1)) < 24 and 0 <= int(m.group(2)) < 60):
        lib.die("時間格式要是 HH:MM，例如 07:00；收到：%s" % s)
    return int(m.group(1)), int(m.group(2))


def say_dry(msg):
    print("  （--dry-run，不執行）%s" % msg)


def sh(argv, timeout=60):
    if DRY:
        say_dry("將會跑：%s" % " ".join(argv))
        return 0, ""
    return hostos.run(argv, timeout=timeout)


def write_file(path, content, mode="w", encoding="utf-8"):
    if DRY:
        say_dry("將會寫入：%s" % path)
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, mode, encoding=encoding, newline="\n") as f:
        f.write(content)
    print("  已寫入：%s" % path)


def remove_file(path):
    if os.path.exists(path):
        if DRY:
            say_dry("將會刪除：%s" % path)
        else:
            os.remove(path)
            print("  已刪除：%s" % path)


# ── crontab 兩行（三個平台都能印） ───────────────────────────────────────────
def cron_lines(sync_t, backup_day, backup_t):
    sh_, sm = sync_t
    bh, bm = backup_t
    py = PYTHON if " " not in PYTHON else '"%s"' % PYTHON
    return [
        "%d %d * * * cd \"%s\" && %s scripts/sync.py >> logs/sync.log 2>&1" % (sm, sh_, REPO, py),
        "%d %d * * %d cd \"%s\" && %s scripts/backup.py --quiet >> logs/backup.log 2>&1" % (bm, bh, backup_day, REPO, py),
    ]


# ── macOS launchd ─────────────────────────────────────────────────────────
def mac_plist_path(job):
    return os.path.join(hostos.home(), "Library", "LaunchAgents", JOBS[job]["label"] + ".plist")


def mac_plist(job, hour, minute, weekday=None):
    j = JOBS[job]
    cal = {"Hour": hour, "Minute": minute}
    if weekday is not None:
        cal["Weekday"] = weekday
    path_env = os.pathsep.join(["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin",
                                os.path.join(hostos.tools_dir(), "whisper"), os.path.dirname(PYTHON)])
    return {
        "Label": j["label"],
        "ProgramArguments": [PYTHON, os.path.join(REPO, "scripts", j["script"]), *j["args"]],
        "WorkingDirectory": REPO,
        "EnvironmentVariables": {"PATH": path_env},
        "StandardOutPath": os.path.join(LOGS, job + ".log"),
        "StandardErrorPath": os.path.join(LOGS, job + ".log"),
        "RunAtLoad": False,
        "StartCalendarInterval": cal,
    }


def mac_uid():
    return str(os.getuid())


def mac_install(sync_t, backup_day, backup_t):
    fail = 0
    for job, (h, m, wd) in (("sync", (*sync_t, None)), ("backup", (*backup_t, backup_day))):
        p = mac_plist_path(job)
        data = plistlib.dumps(mac_plist(job, h, m, wd), sort_keys=False).decode("utf-8")
        write_file(p, data)
        label = JOBS[job]["label"]
        sh(["launchctl", "bootout", "gui/%s/%s" % (mac_uid(), label)])
        rc, out = sh(["launchctl", "bootstrap", "gui/%s" % mac_uid(), p])
        if DRY:
            say_dry("會掛上：%s" % label)
        elif rc == 0:
            print("  ✓ 已掛上：%s" % label)
        else:
            print("  %s✗ 掛不上 %s（launchctl bootstrap 回傳 %s）%s" % (lib.RED, label, rc, lib.RESET))
            print("  → 到「系統設定 → 隱私權與安全性 → 完整磁碟取用權」允許你用的終端機程式再重跑；"
                  "或改用 --print-cron 拿 crontab 兩行自己排。")
            if out.strip():
                print("    " + out.strip().splitlines()[-1])
            fail += 1
    return fail


def mac_uninstall():
    for job in JOBS:
        sh(["launchctl", "bootout", "gui/%s/%s" % (mac_uid(), JOBS[job]["label"])])
        remove_file(mac_plist_path(job))


def mac_status():
    for job in JOBS:
        label = JOBS[job]["label"]
        rc, out = hostos.run(["launchctl", "print", "gui/%s/%s" % (mac_uid(), label)])
        loaded = rc == 0
        last = ""
        m = re.search(r"last exit code = ([^\n]+)", out or "")
        if m:
            last = "上次退出碼 %s" % m.group(1)
        print("  %s %s　%s" % ("✓" if loaded else "✗", label, "已掛上 " + last if loaded else "沒掛上"))


# ── Windows 工作排程器 ─────────────────────────────────────────────────────
def win_xml_path(job):
    return os.path.join(LAUNCHERS, job + ".xml")


def win_task_xml(job, hour, minute, weekday=None):
    """工作排程器的定義檔。用 XML 而不是 /TR 一行字，是因為 /TR 有 261 字上限、
    而且只有 XML 設得到「錯過就在下次開機補跑」（StartWhenAvailable）與工作目錄。"""
    j = JOBS[job]
    script = os.path.join(REPO, "scripts", j["script"])
    log = os.path.join(LOGS, job + ".log")
    args = '/c ""%s" "%s"%s >> "%s" 2>&1"' % (PYTHON, script, "".join(" " + a for a in j["args"]), log)
    start = datetime.datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
    if weekday is None:
        sched = "<ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>"
    else:
        day = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"][weekday]
        sched = "<ScheduleByWeek><WeeksInterval>1</WeeksInterval><DaysOfWeek><%s /></DaysOfWeek></ScheduleByWeek>" % day
    user = "%s\\%s" % (os.environ.get("USERDOMAIN", ""), os.environ.get("USERNAME", ""))
    return """<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.4" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <RegistrationInfo>
    <Description>teacher-records-kit：%(desc)s（由 scripts/schedule.py 產生）</Description>
  </RegistrationInfo>
  <Triggers>
    <CalendarTrigger>
      <StartBoundary>%(start)s</StartBoundary>
      <Enabled>true</Enabled>
      %(sched)s
    </CalendarTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>%(user)s</UserId>
      <LogonType>InteractiveToken</LogonType>
      <RunLevel>LeastPrivilege</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <AllowHardTerminate>true</AllowHardTerminate>
    <StartWhenAvailable>true</StartWhenAvailable>
    <RunOnlyIfNetworkAvailable>%(net)s</RunOnlyIfNetworkAvailable>
    <AllowStartOnDemand>true</AllowStartOnDemand>
    <Enabled>true</Enabled>
    <Hidden>false</Hidden>
    <ExecutionTimeLimit>PT2H</ExecutionTimeLimit>
    <Priority>7</Priority>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>cmd.exe</Command>
      <Arguments>%(args)s</Arguments>
      <WorkingDirectory>%(cwd)s</WorkingDirectory>
    </Exec>
  </Actions>
</Task>
""" % {"desc": escape(j["desc"]), "start": start.strftime("%Y-%m-%dT%H:%M:%S"), "sched": sched,
       "user": escape(user), "net": "true" if j["network"] else "false",
       "args": escape(args), "cwd": escape(REPO)}


def win_install(sync_t, backup_day, backup_t):
    fail = 0
    for job, (h, m, wd) in (("sync", (*sync_t, None)), ("backup", (*backup_t, backup_day))):
        p = win_xml_path(job)
        write_file(p, win_task_xml(job, h, m, wd), encoding="utf-16")
        name = JOBS[job]["win_name"]
        rc, out = sh(["schtasks", "/Create", "/F", "/TN", name, "/XML", p])
        if DRY:
            say_dry("會掛上：%s" % name)
        elif rc == 0:
            print("  ✓ 已掛上：%s" % name)
        else:
            print("  %s✗ 掛不上 %s（schtasks 回傳 %s）%s" % (lib.RED, name, rc, lib.RESET))
            if out.strip():
                print("    " + out.strip().splitlines()[-1])
            print("  → 學校電腦常把工作排程器鎖住。那就不排程：要同步的時候跟你的 AI 說「幫我同步一下」。")
            fail += 1
    return fail


def win_uninstall():
    for job in JOBS:
        sh(["schtasks", "/Delete", "/F", "/TN", JOBS[job]["win_name"]])
        remove_file(win_xml_path(job))


def win_status():
    for job in JOBS:
        name = JOBS[job]["win_name"]
        rc, out = hostos.run(["schtasks", "/Query", "/TN", name, "/FO", "LIST", "/V"])
        if rc != 0:
            print("  ✗ %s　沒掛上" % name)
            continue
        info = {}
        for line in out.splitlines():
            if ":" in line:
                k, v = line.split(":", 1)
                info[k.strip()] = v.strip()
        keys = [k for k in info if k.lower().startswith(("last run time", "last result", "next run time",
                                                           "上次執行時間", "上次結果", "下次執行時間"))]
        print("  ✓ %s　%s" % (name, "；".join("%s %s" % (k, info[k]) for k in keys) or "已掛上"))


# ── Linux crontab ─────────────────────────────────────────────────────────
def linux_current():
    rc, out = hostos.run(["crontab", "-l"])
    return out if rc == 0 else ""


def linux_strip(text):
    lines, skip = [], False
    for line in (text or "").splitlines():
        if line.strip() == CRON_MARK_BEGIN:
            skip = True
            continue
        if line.strip() == CRON_MARK_END:
            skip = False
            continue
        if not skip:
            lines.append(line)
    return "\n".join(lines).rstrip("\n")


def linux_install(sync_t, backup_day, backup_t):
    if not hostos.exe("crontab"):
        print("  %s✗ 找不到 crontab%s" % (lib.RED, lib.RESET))
        print("  → 裝 cron（sudo apt-get install -y cron），或改用 --print-cron 自己排到別的排程器。")
        return 1
    body = linux_strip(linux_current())
    new = (body + "\n" if body else "") + "\n".join([CRON_MARK_BEGIN, *cron_lines(sync_t, backup_day, backup_t),
                                                    CRON_MARK_END]) + "\n"
    if DRY:
        say_dry("將會把這一段寫進 crontab：")
        print("\n".join("    " + l for l in new.splitlines()[-4:]))
        return 0
    rc, out = hostos.run(["crontab", "-"], input_text=new)
    if rc == 0:
        print("  ✓ 已寫進 crontab")
        return 0
    print("  %s✗ crontab 寫入失敗：%s%s" % (lib.RED, out.strip(), lib.RESET))
    return 1


def linux_uninstall():
    if not hostos.exe("crontab"):
        return
    body = linux_strip(linux_current())
    if DRY:
        say_dry("將會把 teacher-records-kit 那一段從 crontab 拿掉")
        return
    hostos.run(["crontab", "-"], input_text=(body + "\n") if body else "")
    print("  已從 crontab 移除")


def linux_status():
    cur = linux_current()
    print("  %s crontab %s" % ("✓" if CRON_MARK_BEGIN in cur else "✗",
                               "有 teacher-records-kit 那一段" if CRON_MARK_BEGIN in cur else "沒有那一段"))


# ── 主程式 ───────────────────────────────────────────────────────────────
def main():
    global DRY
    ap = argparse.ArgumentParser(description="（選用）排程：每天同步、每週備份")
    ap.add_argument("--dry-run", action="store_true", help="只印會做的事，不寫檔、不安裝")
    ap.add_argument("--print-cron", action="store_true", help="只印等效的 crontab 兩行")
    ap.add_argument("--uninstall", action="store_true", help="移除排程並刪掉產生的檔")
    ap.add_argument("--status", action="store_true", help="看排程掛了沒")
    ap.add_argument("--sync-time", default="07:00", metavar="HH:MM", help="每天幾點同步（預設 07:00）")
    ap.add_argument("--backup-day", type=int, default=0, metavar="0-6", help="每週哪一天備份（0＝週日，預設 0）")
    ap.add_argument("--backup-time", default="08:00", metavar="HH:MM", help="備份幾點跑（預設 08:00）")
    a = ap.parse_args()
    DRY = a.dry_run
    sync_t, backup_t = hhmm(a.sync_time), hhmm(a.backup_time)
    if not 0 <= a.backup_day <= 6:
        lib.die("--backup-day 要在 0（週日）到 6（週六）之間。")

    if a.print_cron:
        print("等效的 crontab 兩行（crontab -e 貼進去；Windows 沒有 cron，請用本腳本的預設模式）：\n")
        print("\n".join(cron_lines(sync_t, a.backup_day, backup_t)))
        return

    why = hostos.unsupported_reason()
    if why:
        lib.die(why, "換到 Windows 原生終端機之後再跑一次這支。")

    impl = {"mac": (mac_install, mac_uninstall, mac_status),
            "win": (win_install, win_uninstall, win_status),
            "linux": (linux_install, linux_uninstall, linux_status)}[OS]

    if a.status:
        print("排程狀態（%s）：" % hostos.OS_LABEL)
        impl[2]()
        print("\n真正的驗證是網頁頂端「上次同步 X 天前」有沒有更新——超過 7 天會變紅字。")
        return

    if a.uninstall:
        print("移除排程（%s）……" % hostos.OS_LABEL)
        impl[1]()
        print("完成。")
        return

    print("安裝排程（%s）：每天 %02d:%02d 同步、每週%s %02d:%02d 備份"
          % (hostos.OS_LABEL, *sync_t, "日一二三四五六"[a.backup_day], *backup_t))
    print("  用的 Python：%s" % PYTHON)
    if not DRY:
        os.makedirs(LOGS, exist_ok=True)
    else:
        say_dry("將會建立 %s" % LOGS)
    fail = impl[0](sync_t, a.backup_day, backup_t)
    print()
    print("排程可能會靜默失敗（電腦沒開機、權限被擋等都看不到錯誤訊息），")
    print("所以網頁頂端會顯示「上次同步 X 天前」，超過 7 天會變紅字。")
    print("要驗證排程真的會跑，請明天打開 kit 的網頁看那個數字；`%s scripts/schedule.py --status` 只能看有沒有掛上。" % hostos.PY)
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
