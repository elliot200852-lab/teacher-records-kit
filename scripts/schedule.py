#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""schedule.py — （選用）排程（macOS launchd／Windows 工作排程器／Linux cron 同一支）。

**掛哪幾個工作由 config/kit.json 決定**（`wanted_jobs()`），不是一律三個：

  sync      每天 07:00      sync.py                  只有 cloud 模式（本機模式沒有雲端可以同步）
  backup    每週日 08:00    backup.py --quiet        一律掛
  headless  **每 5 分鐘**   headless.py --once       只有開了無頭交辦（docs/HEADLESS.md）

排程可能會靜默失敗（電腦沒開機、系統擋權限），所以本 kit 的網頁頂端會顯示「上次同步／備份幾天前」，
真正要驗證排程有沒有生效請看那個數字，不要只看 --status 顯示有掛就以為它真的跑得動。

用法：
  python3 scripts/schedule.py              照設定安裝該掛的那幾個
  python3 scripts/schedule.py --dry-run    只印會做的事，不寫檔、不安裝
  python3 scripts/schedule.py --status     看排程掛了沒、上次跑的結果
  python3 scripts/schedule.py --print-cron 只印等效的 crontab，不寫任何檔案
  python3 scripts/schedule.py --uninstall  移除排程並刪掉產生的檔（三個都清，不管現在開了哪些）
  python3 scripts/schedule.py --sync-time 06:30 --backup-day 6 --backup-time 21:00
                                           改時間（backup-day：0＝週日 … 6＝週六）

各平台怎麼做：
  macOS    ~/Library/LaunchAgents/com.teacher-records-kit.{sync,backup,headless}.plist（launchctl bootstrap）
  Windows  工作排程器 \\TeacherRecordsKit\\{Sync,Backup,Headless}，定義檔寫在 setup/launchers/*.xml（schtasks /Create /XML）
           — 用的是現在這個 Python（sys.executable），電腦沒開時錯過的那次會在下次開機補跑
  Linux    crontab（在你的 crontab 裡加幾行、用註解標記包起來）
「每 5 分鐘」在三個平台各是不同的東西（launchd StartInterval／工作排程器的 Repetition PT5M／cron 的 */5），
細節與理由寫在 docs/PLATFORMS.md「排程在三個平台各是什麼」。
log 一律在 logs/<job>.log。零第三方相依。
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
    # 無頭交辦：不是「每天幾點」而是「每 5 分鐘看一次有沒有新的交辦」。
    # 5 分鐘是刻意的折衷：老師在手機上講完話，最多等五分鐘就會收到回報；
    # 再密就只是讓筆電一直醒著、電池白白掉。
    "headless": {"script": "headless.py", "args": ["--once", "--quiet"],
                 "label": "com.teacher-records-kit.headless",
                 "win_name": r"TeacherRecordsKit\Headless",
                 "desc": "每 5 分鐘看一次 LINE 有沒有新的交辦", "network": True,
                 "interval_min": 5},
}
DRY = False


def wanted_jobs(kit=None):
    """這台電腦該掛哪幾個排程——照設定決定，不是照 JOBS 全掛。

    · 本機模式沒有雲端可以同步，掛 sync 只會每天產生一行「不用同步」的 log。
    · 無頭交辦沒開就不掛（掛了它每 5 分鐘醒來一次只為了說「沒有開」）。
    """
    kit = lib.load_kit(required=False) if kit is None else kit
    jobs = [] if lib.is_local(kit) else ["sync"]
    jobs.append("backup")
    if lib.headless_on(kit):
        jobs.append("headless")
    return jobs


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
def cron_lines(sync_t, backup_day, backup_t, jobs=("sync", "backup")):
    sh_, sm = sync_t
    bh, bm = backup_t
    py = PYTHON if " " not in PYTHON else '"%s"' % PYTHON
    out = []
    if "sync" in jobs:
        out.append("%d %d * * * cd \"%s\" && %s scripts/sync.py >> logs/sync.log 2>&1"
                   % (sm, sh_, REPO, py))
    if "backup" in jobs:
        out.append("%d %d * * %d cd \"%s\" && %s scripts/backup.py --quiet >> logs/backup.log 2>&1"
                   % (bm, bh, backup_day, REPO, py))
    if "headless" in jobs:
        out.append("*/%d * * * * cd \"%s\" && %s scripts/headless.py --once --quiet "
                   ">> logs/headless.log 2>&1"
                   % (JOBS["headless"]["interval_min"], REPO, py))
    return out


# ── macOS launchd ─────────────────────────────────────────────────────────
def mac_plist_path(job):
    return os.path.join(hostos.home(), "Library", "LaunchAgents", JOBS[job]["label"] + ".plist")


def mac_plist(job, hour, minute, weekday=None):
    j = JOBS[job]
    path_env = os.pathsep.join(["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin", "/bin",
                                os.path.join(hostos.tools_dir(), "whisper"), os.path.dirname(PYTHON)])
    plist = {
        "Label": j["label"],
        "ProgramArguments": [PYTHON, os.path.join(REPO, "scripts", j["script"]), *j["args"]],
        "WorkingDirectory": REPO,
        "EnvironmentVariables": {"PATH": path_env},
        "StandardOutPath": os.path.join(LOGS, job + ".log"),
        "StandardErrorPath": os.path.join(LOGS, job + ".log"),
        "RunAtLoad": False,
    }
    if j.get("interval_min"):
        # 「每 N 分鐘一次」用 StartInterval，不是 StartCalendarInterval——
        # 後者要把 60 分鐘列成 60 筆字典，而且睡醒之後 launchd 不會補跑。
        plist["StartInterval"] = j["interval_min"] * 60
        return plist
    cal = {"Hour": hour, "Minute": minute}
    if weekday is not None:
        cal["Weekday"] = weekday
    plist["StartCalendarInterval"] = cal
    return plist


def mac_uid():
    return str(os.getuid()) if hasattr(os, "getuid") else "501"     # Windows 上用 TRK_FORCE_OS=mac 渲染 dry-run 時沒有 getuid


def job_plan(sync_t, backup_day, backup_t, jobs):
    """(job 名, 小時, 分鐘, 星期幾) 的清單，三個平台共用同一份。"""
    all_plan = [("sync", (*sync_t, None)),
                ("backup", (*backup_t, backup_day)),
                ("headless", (0, 0, None))]        # 間隔型：時間不看，看 interval_min
    return [(j, t) for j, t in all_plan if j in jobs]


def mac_install(sync_t, backup_day, backup_t, jobs=("sync", "backup")):
    fail = 0
    for job, (h, m, wd) in job_plan(sync_t, backup_day, backup_t, jobs):
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


def mac_status(jobs=("sync", "backup")):
    for job in JOBS:
        if job not in jobs:
            print("  – %s　（沒開這個功能，本來就不該掛）" % JOBS[job]["label"])
            continue
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
    rep = ""
    if j.get("interval_min"):
        # 工作排程器沒有「每 N 分鐘」的觸發器，做法是「每天一次的觸發器 ＋ 重複整整一天」。
        # StopAtDurationEnd 要 false，不然一天結束時它會把正在跑的那一次殺掉。
        start = datetime.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        rep = ("<Repetition><Interval>PT%dM</Interval><Duration>P1D</Duration>"
               "<StopAtDurationEnd>false</StopAtDurationEnd></Repetition>" % j["interval_min"])
    if weekday is None:
        sched = "<ScheduleByDay><DaysInterval>1</DaysInterval></ScheduleByDay>"
    else:
        day = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"][weekday]
        sched = "<ScheduleByWeek><WeeksInterval>1</WeeksInterval><DaysOfWeek><%s /></DaysOfWeek></ScheduleByWeek>" % day
    sched = rep + sched
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


def win_install(sync_t, backup_day, backup_t, jobs=("sync", "backup")):
    fail = 0
    for job, (h, m, wd) in job_plan(sync_t, backup_day, backup_t, jobs):
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


def win_status(jobs=("sync", "backup")):
    for job in JOBS:
        if job not in jobs:
            print("  – %s　（沒開這個功能，本來就不該掛）" % JOBS[job]["win_name"])
            continue
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


def linux_install(sync_t, backup_day, backup_t, jobs=("sync", "backup")):
    if not hostos.exe("crontab") and DRY:
        say_dry("這台電腦目前找不到 crontab；真跑時會要求先裝 cron")
    elif not hostos.exe("crontab"):
        print("  %s✗ 找不到 crontab%s" % (lib.RED, lib.RESET))
        print("  → 裝 cron（sudo apt-get install -y cron），或改用 --print-cron 自己排到別的排程器。")
        return 1
    body = linux_strip(linux_current())
    lines = cron_lines(sync_t, backup_day, backup_t, jobs)
    new = (body + "\n" if body else "") + "\n".join([CRON_MARK_BEGIN, *lines,
                                                    CRON_MARK_END]) + "\n"
    if DRY:
        say_dry("將會把這一段寫進 crontab：")
        print("\n".join("    " + l for l in new.splitlines()[-(len(lines) + 2):]))
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


def linux_status(jobs=("sync", "backup")):
    cur = linux_current()
    print("  %s crontab %s" % ("✓" if CRON_MARK_BEGIN in cur else "✗",
                               "有 teacher-records-kit 那一段" if CRON_MARK_BEGIN in cur else "沒有那一段"))
    for job in jobs:
        print("    · %s　%s" % (JOBS[job]["desc"],
                                "在裡面" if JOBS[job]["script"] in cur else "不在裡面"))


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

    kit = lib.load_kit(required=False)
    jobs = wanted_jobs(kit)

    if a.print_cron:
        print("等效的 crontab（crontab -e 貼進去；Windows 沒有 cron，請用本腳本的預設模式）：\n")
        print("\n".join(cron_lines(sync_t, a.backup_day, backup_t, jobs)))
        return

    why = hostos.unsupported_reason()
    if why:
        lib.die(why, "換到 Windows 原生終端機之後再跑一次這支。")

    impl = {"mac": (mac_install, mac_uninstall, mac_status),
            "win": (win_install, win_uninstall, win_status),
            "linux": (linux_install, linux_uninstall, linux_status)}[OS]

    if a.status:
        print("排程狀態（%s）：" % hostos.OS_LABEL)
        impl[2](jobs)
        print("\n真正的驗證是網頁頂端「上次同步 X 天前」有沒有更新——超過 7 天會變紅字。")
        return

    if a.uninstall:
        print("移除排程（%s）……" % hostos.OS_LABEL)
        impl[1]()
        print("完成。")
        return

    # 排程用的是「現在這個 Python」（sys.executable）。那如果是 Microsoft Store 的假殼，
    # 排程會掛得上去、卻永遠不會跑，而且一聲不吭——寧可現在就拒絕。
    if hostos.python_is_store_alias(PYTHON):
        lib.die("現在跑這支的 Python 是 Microsoft Store 的「應用程式執行別名」：%s" % PYTHON,
                "排程會用同一個 Python 去跑 sync.py／backup.py，而那個假殼在工作排程器底下（沒有人登入著"
                "的那種非互動環境）叫不起來——排程看起來掛上了，卻永遠不會跑、也不會報錯。"
                "請到 https://www.python.org/downloads/ 裝 python.org 版（安裝時勾「Add python.exe to PATH」），"
                "關掉這個視窗、開一個新的 PowerShell，改用 `%s scripts\\schedule.py` 再跑一次。" % hostos.PY)

    what = []
    if "sync" in jobs:
        what.append("每天 %02d:%02d 同步" % sync_t)
    what.append("每週%s %02d:%02d 備份" % ("日一二三四五六"[a.backup_day], *backup_t))
    if "headless" in jobs:
        what.append("每 %d 分鐘收一次 LINE 交辦" % JOBS["headless"]["interval_min"])
    print("安裝排程（%s）：%s" % (hostos.OS_LABEL, "、".join(what)))
    if "sync" not in jobs:
        print("  （本機模式：沒有雲端可以同步，不掛同步排程。）")
    print("  用的 Python：%s" % PYTHON)
    if not DRY:
        os.makedirs(LOGS, exist_ok=True)
    else:
        say_dry("將會建立 %s" % LOGS)
    fail = impl[0](sync_t, a.backup_day, backup_t, jobs)
    print()
    if "headless" in jobs:
        print("無頭交辦的排程跑的是 `headless.py --once`，它要讀得到 LINE 的兩個環境變數"
              "（%s、%s）。"
              % (lib.headless_cfg(kit)["line"]["channel_secret_env"],
                 lib.headless_cfg(kit)["line"]["channel_token_env"]))
        print("排程不會讀你終端機裡臨時 export 的變數——請把它們寫進登入時會載入的設定檔"
              "（見 docs/HEADLESS.md）。")
        print()
    print("排程可能會靜默失敗（電腦沒開機、權限被擋等都看不到錯誤訊息），")
    print("所以網頁頂端會顯示「上次同步 X 天前」，超過 7 天會變紅字。")
    print("要驗證排程真的會跑，請明天打開 kit 的網頁看那個數字；`%s scripts/schedule.py --status` 只能看有沒有掛上。" % hostos.PY)
    sys.exit(1 if fail else 0)


if __name__ == "__main__":
    main()
