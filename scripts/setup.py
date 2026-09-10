#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""setup.py — 確定性安裝精靈：問完 → 寫設定 → 建資料骨架 → 產生網頁設定與規則 → 健檢。

為什麼要有這支：安裝這件事不能交給 AI 即興發揮（紅隊 #3）。AI 代理負責解釋題目、
幫老師找答案、讀錯誤訊息；**產生檔一律由這支腳本寫**，同樣的答案跑幾次結果都一樣。

用法：
  python3 scripts/setup.py                                   互動安裝（一次問一題）
  python3 scripts/setup.py --answers templates/answers.example.json
                                                             免互動：照答案檔直接裝完
  python3 scripts/setup.py --resume                          讀 setup/progress.json 續裝
  python3 scripts/setup.py --upgrade                         把 v2 的 config.yaml 轉成 v3 設定
  python3 scripts/setup.py --root /tmp/trk-test              裝到別的資料夾（測試用）
  python3 scripts/setup.py --mark-step 4 --note "已部署"     把第 N 步標成完成（AI 部署完用）

問法的原則（David 2026-09-10）：**全部勾選、沒有預設**——三個分頁都問「要不要」，
學生記錄類型與業務組都把清單列出來讓老師勾，一個都不預設打勾。學生段之前會先問一句
「你最像哪一種？」（三個垂直方案：質性評量自動化／IEP 追蹤／SOAP 個案紀錄，見
config/verticals.json），然後**唸出**那個方案建議勾的類型、業務組與期末格式——
唸歸唸，一項都不會替老師勾起來。

它會寫出：
  config/kit.json、config/tabs.json      你的設定（gitignored）
  data/…                                  空的資料骨架（名冊、每位學生每種記錄類型一檔、課程、業務組）
  data/students/<代號>/card.json          學生卡片（IEP 的 goals、個案概念化；答案檔可給初始值）
  site/js/kit-config.js、site/js/firebase-config.js、firestore.rules  （呼叫 build_config.py）
  setup/progress.json                     安裝進度，AI 代理接手前先讀它

它不會做的事：不部署、不寄信、不上傳、不碰網路（除非健檢那一步）。
"""
import os
import re
import sys
import json
import shutil
import argparse
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib

CONSOLE = "https://console.firebase.google.com"
WEBCFG_PATH = "專案設定（左上齒輪）→ 一般 → 你的應用程式 → 網頁應用程式 → SDK 設定與配置 → Config"

STEP_TITLES = [
    "判斷新裝／升級／續裝",
    "裝工具（install_tools.sh ＋ doctor.py）",
    "Google 帳號與 Firebase 專案",
    "分頁與向度（學生記錄類型／課程／業務組，全部勾選）",
    "產生設定與安全規則（build_config.py ＋ firebase deploy；部署完 --mark-step 4）",
    "上線（firebase deploy --only hosting）",
    "學生名單與既有資料匯入",
    "Google Drive 備份夾",
    "排程（選用）",
    "錄音檔試跑一次",
    "驗收清單",
]


# ── 互動小工具 ──────────────────────────────────────────────────────────
class Asker:
    """互動問答。answers 有值就完全不問（免互動安裝）。"""

    def __init__(self, answers=None):
        self.answers = answers
        self.interactive = answers is None

    def _need_tty(self, q):
        if not sys.stdin.isatty():
            lib.die("需要有人回答「%s」，但現在不是互動終端機。" % q,
                    "改用 `python3 scripts/setup.py --answers 你的答案.json`（範本："
                    "templates/answers.example.json）。")

    def say(self, *lines):
        if self.interactive:
            for l in lines:
                print(l)

    def where(self, text):
        """每一題附一行「去哪裡拿」。"""
        if self.interactive:
            print("  %s去哪裡拿：%s%s" % (lib.DIM, text, lib.RESET))

    def text(self, q, default="", where="", allow_empty=True, check=None):
        if not self.interactive:
            return default
        self._need_tty(q)
        while True:
            if where:
                self.where(where)
            tip = ("（直接按 Enter＝%s）" % default) if default else ""
            ans = input("%s%s：" % (q, tip)).strip() or default
            if not ans and not allow_empty:
                print("  這一題不能空白。")
                continue
            if check:
                bad = check(ans)
                if bad:
                    print("  %s" % bad)
                    continue
            return ans

    def yes(self, q, default=True):
        if not self.interactive:
            return default
        self._need_tty(q)
        d = "Y/n" if default else "y/N"
        while True:
            ans = input("%s（%s）：" % (q, d)).strip().lower()
            if not ans:
                return default
            if ans in ("y", "yes", "是", "要", "好"):
                return True
            if ans in ("n", "no", "否", "不", "不要"):
                return False
            print("  請回答 y 或 n。")

    def pick(self, q, options, default_idx=None):
        """從清單選一個，回傳 index。"""
        if not self.interactive:
            return default_idx or 0
        self._need_tty(q)
        for i, o in enumerate(options, 1):
            print("  %d) %s" % (i, o))
        while True:
            ans = input("%s（輸入編號%s）：" % (q, "，Enter＝%d" % (default_idx + 1) if default_idx is not None else "")).strip()
            if not ans and default_idx is not None:
                return default_idx
            if ans.isdigit() and 1 <= int(ans) <= len(options):
                return int(ans) - 1
            print("  請輸入 1 到 %d 之間的編號。" % len(options))

    def multi(self, q, options):
        """複選，回傳 index 陣列。輸入 1,3,5；全部＝a；都不要＝直接 Enter。"""
        if not self.interactive:
            return []
        self._need_tty(q)
        for i, o in enumerate(options, 1):
            print("  %2d) %s" % (i, o))
        while True:
            ans = input("%s（例如 1,3,5；全部＝a；都不要＝直接 Enter）：" % q).strip().lower()
            if not ans:
                return []
            if ans in ("a", "all", "全部"):
                return list(range(len(options)))
            try:
                idx = sorted({int(x) - 1 for x in re.split(r"[,\s、]+", ans) if x})
            except ValueError:
                print("  只能輸入編號與逗號。")
                continue
            if all(0 <= i < len(options) for i in idx):
                return idx
            print("  有編號超出範圍（1 到 %d）。" % len(options))


def slug(text, fallback):
    s = re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")
    return s or fallback


def valid_id(s):
    return bool(re.match(r"^[A-Za-z0-9_-]+$", s or ""))


def split_list(text):
    return [x.strip() for x in re.split(r"[,，、;；]", str(text or "")) if x.strip()]


# ── 兩層開放選項（業務組與學生記錄類型共用同一套問法）────────────────────
def ask_one_field(ask, indent):
    """問一個自訂欄位（名稱＋型別＋select 的選項）。名稱空白＝不再加了。"""
    name = ask.text(indent + "欄位名稱", default="")
    if not name:
        return None
    ti = ask.pick(indent + "這個欄位是", ["文字", "日期（YYYY-MM-DD）", "從幾個選項挑一個"], 0)
    f = {"name": name, "type": ["text", "date", "select"][ti]}
    if f["type"] == "select":
        f["options"] = split_list(ask.text(indent + "可選的值（用逗號分隔）", allow_empty=False))
    return f


def ask_extra_fields(ask, indent, label, fields):
    """第一層開放選項：這一組／這一種還要不要加自己的欄位。"""
    cur = "、".join(f["name"] for f in fields) or "（原本沒有固定欄位）"
    ask.say("%s［%s］目前的欄位：%s" % (indent, label, cur))
    while ask.yes(indent + "還有沒有你自己要記的欄位", False):
        f = ask_one_field(ask, indent + "  ")
        if f:
            fields.append(f)
    return fields


def ask_extra_tags(ask, indent, label, tags):
    """第一層開放選項：這一組／這一種還要不要加自己的分類詞。"""
    ask.say("%s［%s］目前的分類詞：%s" % (indent, label, "、".join(tags) or "（沒有）"))
    if ask.yes(indent + "還要加你自己的分類詞嗎", False):
        for t in split_list(ask.text(indent + "  分類詞（逗號分隔）", default="")):
            if t not in tags:
                tags.append(t)
    return tags


# ── v2 config.yaml → v3 kit.json ────────────────────────────────────────
def read_legacy_yaml(path):
    """極簡 YAML 讀取，只為了把 v2 的 config.yaml 轉成 JSON——之後不再用 YAML。"""
    cfg, section = {}, None
    with open(path, encoding="utf-8") as fh:
        raw_lines = fh.readlines()
    for raw in raw_lines:
        line = raw.rstrip("\n")
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        if not line.startswith((" ", "\t")):
            k, _, v = line.partition(":")
            v = v.split(" #")[0].strip().strip('"').strip("'")
            if v == "":
                section = k.strip()
                cfg[section] = {}
            else:
                cfg[k.strip()] = v
                section = None
        elif section is not None:
            k, _, v = line.strip().partition(":")
            cfg[section][k.strip()] = v.split(" #")[0].strip().strip('"').strip("'")
    return cfg


# ── 問答 → 設定 ─────────────────────────────────────────────────────────
def ask_vertical(ask, answers, verticals):
    """學生段之前先問一句「你最像哪一種？」，唸出那個方案的建議——**一項都不預先勾**。

    回傳 (vertical id 或 ""，這個方案的 suggest 字典)。答案檔用 `"vertical": "<id>"`；
    填 "none" 或不填＝都不是，什麼建議都不唸。
    """
    vids = [v["id"] for v in verticals]
    vid = str((answers or {}).get("vertical") or "").strip()
    if ask.interactive:
        ask.say("\n④-0 先問一件事，好讓我知道待會兒要建議你什麼（**只是建議，一項都不會幫你預先勾**）：")
        idx = ask.pick("   你最像哪一種？",
                       ["%s — %s" % (v["label"], v["pain"]) for v in verticals]
                       + ["都不是（我自己勾）"])
        vid = vids[idx] if idx < len(vids) else ""
    if vid in ("none", "無", "都不是"):
        vid = ""
    if vid and vid not in vids:
        lib.warn("config/verticals.json 裡沒有這個方案：%s（當成「都不是」）。" % vid)
        vid = ""
    v = next((x for x in verticals if x["id"] == vid), None)
    if not v:
        return "", {}
    sug = v.get("suggest") or {}
    ask.say("   ▸ 這一種老師通常會勾：記錄類型 %s；業務組 %s；期末用「%s」格式。"
            % ("、".join(sug.get("streams") or []) or "（無）",
               "、".join(sug.get("groups") or []) or "（無）",
               sug.get("format") or "（無）"))
    ask.say("   ▸ 語音改寫規則：%s" % (v.get("voiceRule") or ""))
    ask.say("   ▸ 以上只是建議——下面每一項還是你自己勾，我不會替你打勾。")
    return vid, sug


def gather(ask, answers, existing_kit):
    """回傳 (kit, tabs, student_ids, members, cards)。

    members＝{記錄類型 id: [學生代號…]}，也就是「哪些學生列入哪些個案型類型」，
    等一下由 build_data 寫進 data/roster.csv 第三欄。
    cards＝{學生代號: {goals, conceptualization}}，寫進 data/students/<代號>/card.json。
    """
    a = answers or {}
    kit_ex = lib._load_json(lib.pkg_path("config", "kit.example.json"), "kit 範本", "")
    tabs_ex = lib._load_json(lib.pkg_path("config", "tabs.example.json"), "tabs 範本", "")
    library = lib.load_library()
    lib_groups = [g for g in library.get("groups", []) if not g.get("open")]
    stream_library = lib.load_stream_library()
    lib_streams = [s for s in stream_library.get("streams", []) if not s.get("open")]

    ask.say("\n── 第 2 步：你的 Google 帳號與 Firebase 專案 ──")
    ask.say("這套系統整個裝在你自己的 Firebase 專案裡：資料是你的、帳單是你的（一般用量在免費額度內），")
    ask.say("賣你這套 kit 的人看不到你的任何資料。")
    owner = ask.text("① 你要用哪個 Google 信箱登入（只有這個帳號讀得到資料）",
                     default=a.get("owner_email") or existing_kit.get("owner_email") or "",
                     where="就是你平常登入 Google 的信箱。學校帳號若被管理員鎖住 Cloud Console，改用個人 Gmail。",
                     allow_empty=False,
                     check=lambda s: None if re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", s) else "格式要像 someone@gmail.com。")

    fb_a = a.get("firebase") or {}
    fb_old = existing_kit.get("firebase") or {}
    ask.say("\n② 接下來六個值都在同一個畫面：%s → %s" % (CONSOLE, WEBCFG_PATH))
    ask.say("   還沒有專案的話先在 %s 按「建立專案」，建好後加一個「網頁應用程式」。" % CONSOLE)
    fb = {}
    for key, label, hint in [
        ("project_id", "專案 ID（projectId）", "Console 網址列 /project/<這一段>"),
        ("api_key", "API 金鑰（apiKey）", "%s" % WEBCFG_PATH),
        ("auth_domain", "authDomain", "通常是 <專案ID>.firebaseapp.com"),
        ("storage_bucket", "storageBucket", "通常是 <專案ID>.firebasestorage.app"),
        ("messaging_sender_id", "messagingSenderId", "一串數字，同一個畫面"),
        ("app_id", "appId", "1:xxx:web:xxx，同一個畫面"),
    ]:
        fb[key] = ask.text("   %s" % label,
                           default=fb_a.get(key, fb_old.get(key, "")),
                           where=hint, allow_empty=True)
    if not fb.get("auth_domain") and fb.get("project_id"):
        fb["auth_domain"] = "%s.firebaseapp.com" % fb["project_id"]

    ask.say("\n── 第 3 步：三個分頁要記什麼 ──")
    ask.say("三個分頁、每一種記錄類型、每一組業務都由你自己勾——一個都不預設幫你打勾。")
    prefix = ask.text("③ 學生代號前綴（紀錄裡一律寫代號，真名只留在你電腦上的名冊）",
                      default=a.get("id_prefix") or existing_kit.get("id_prefix") or "S",
                      where="想用班級當前綴也可以，例如 6B → 代號長成 6B-01。")
    st_a = a.get("students") or {}
    if st_a.get("ids"):
        student_ids = list(st_a["ids"])
    else:
        n = st_a.get("count")
        if n is None:
            n = ask.text("④ 班上有幾位學生（之後可以再加）", default="0",
                         where="只要人數；姓名等一下填在 data/roster.csv。",
                         check=lambda s: None if s.isdigit() else "請輸入數字。")
        n = int(n or 0)
        student_ids = ["%s-%02d" % (prefix.rstrip('-'), i) for i in range(1, n + 1)]

    # 三個垂直方案：先問「你最像哪一種」，唸出建議（不預勾），再照原本流程逐項勾。
    vertical, suggest = ask_vertical(ask, a, (lib.load_verticals().get("verticals") or []))

    # 學生記錄：先問要不要，再勾記錄類型（質性評量／導師班級／任課／個案／IEP／SOAP…）
    students_on = st_a.get("enabled", True)
    if ask.interactive:
        ask.say("\n⑤ 學生記錄＝一位學生一個檔，一則一則累積下來的觀察。")
        students_on = ask.yes("   要不要「學生記錄」分頁", True)
    streams, members, cards = [], {}, {}
    if students_on:
        chosen_sids = list(st_a.get("streams") or [])
        if ask.interactive:
            ask.say("   學生記錄不能混在一起——導師的班級紀錄、任課老師的觀察、個案追蹤、")
            ask.say("   IEP、輔導晤談各是一種「記錄類型」，各有自己的欄位與分類詞。")
            idx = ask.multi("   勾選你要的記錄類型（可複選；一種都不勾也可以）",
                            ["%s〔%s〕%s — %s" % (s["label"],
                                                  "全班每一位" if s.get("scope") == "class" else "只有列入的學生",
                                                  "（建議）" if s["id"] in (suggest.get("streams") or []) else "",
                                                  s.get("desc", ""))
                             for s in lib_streams])
            chosen_sids = [lib_streams[i]["id"] for i in idx]
        by_sid = {s["id"]: s for s in lib_streams}
        ex_f = (st_a.get("extra_fields") or {})
        ex_t = (st_a.get("extra_tags") or {})
        ans_members = (st_a.get("members") or {})
        for sid in chosen_sids:
            s = by_sid.get(sid)
            if not s:
                lib.warn("記錄類型庫裡沒有 %s，跳過。" % sid)
                continue
            fields = [dict(f) for f in (s.get("fields") or [])]
            tags = list(s.get("tags") or [])
            fields += [dict(f) for f in (ex_f.get(sid) or [])]
            tags += [t for t in (ex_t.get(sid) or []) if t not in tags]
            if ask.interactive:
                ask_extra_fields(ask, "   ", s["label"], fields)
                ask_extra_tags(ask, "   ", s["label"], tags)
            entry = {"id": sid, "label": s["label"], "desc": s.get("desc", ""),
                     "scope": s.get("scope", "class"), "fields": fields,
                     "tags": lib.norm_tags(tags), "custom": False}
            # 舊 id（counseling → soap）與「這種類型要用到學生卡片的哪一塊」都帶著走，
            # 網頁表單與 append_record.py 的目標編號檢查都靠它。
            if s.get("aliases"):
                entry["aliases"] = list(s["aliases"])
            if s.get("card"):
                entry["card"] = dict(s["card"])
            if s.get("vertical"):
                entry["vertical"] = s["vertical"]
            streams.append(entry)
            members[sid] = list(ans_members.get(sid) or [])

        # 第二層開放選項：清單外的記錄類型（AI 問四件事）
        custom_streams = list(st_a.get("custom_streams") or [])
        if ask.interactive:
            while ask.yes("   還有清單裡沒有的學生記錄類型嗎", False):
                label = ask.text("     這個類型叫什麼", allow_empty=False)
                cid = ask.text("     英文短名（會變成檔名 data/students/<代號>/<短名>.md）",
                               default=slug(label, "stream-%d" % (len(custom_streams) + 1)),
                               check=lambda s_: None if valid_id(s_) else "只能用英數與 - _。")
                fields = []
                ask.say("     每次要記哪些固定欄位？一行一個，直接 Enter 結束。")
                while True:
                    f = ask_one_field(ask, "       ")
                    if not f:
                        break
                    fields.append(f)
                tags = ask.text("     常用的分類詞（逗號分隔，可留白）", default="")
                si = ask.pick("     這個類型涵蓋誰",
                              ["名冊上每一位學生（像導師班級紀錄）",
                               "只有我列入的學生（像個案追蹤）"], 0)
                custom_streams.append({"id": cid, "label": label,
                                       "fields": fields, "tags": split_list(tags),
                                       "scope": ["class", "case"][si]})
        for c in custom_streams:
            cid = c.get("id")
            if not cid:
                continue
            streams.append({"id": cid, "label": c.get("label") or cid,
                            "desc": c.get("desc", ""),
                            "scope": c.get("scope") or "class",
                            "fields": [dict(f) for f in (c.get("fields") or [])],
                            "tags": lib.norm_tags(c.get("tags") or []),
                            "custom": True})
            members[cid] = list(ans_members.get(cid) or [])

        # 個案型類型：哪些學生列入（寫進 data/roster.csv 第三欄，之後隨時可以改）
        for s in streams:
            if s["scope"] != "case":
                members.pop(s["id"], None)
                continue
            if ask.interactive:
                got = ask.text("   ［%s］哪些學生列入？（代號，逗號分隔；可先空著，之後改 "
                               "data/roster.csv 第三欄或在網頁上列入）" % s["label"], default="")
                if got:
                    members[s["id"]] = split_list(got)
        members = {k: v for k, v in members.items() if v}

        # 學生卡片：IEP 的 goals、SOAP 的個案概念化。答案檔可以先給初始值
        # （students.cards.<代號>.goals／.conceptualization），互動安裝就只提示去哪裡填——
        # 目標要一條一條打，在編輯器或網頁上填比在終端機問一輪快得多。
        for sid, c in (st_a.get("cards") or {}).items():
            if not isinstance(c, dict):
                continue
            entry = {}
            if c.get("goals"):
                entry["goals"] = lib.norm_goals(c["goals"])
            if c.get("conceptualization"):
                entry["conceptualization"] = lib.norm_conceptualization(c["conceptualization"])
            if entry:
                cards[str(sid)] = entry
        if ask.interactive:
            if lib.stream_needs(streams, "goals"):
                ask.say("   ▸ IEP／早療的學年與學期目標填在 data/students/<代號>/card.json 的 goals"
                        "（範本：templates/card.example.json，網頁上也能建）。"
                        "記錄時的「目標編號」就是從那裡選；填了不存在的編號會被擋下來。")
            if lib.stream_needs(streams, "conceptualization"):
                ask.say("   ▸ 個案概念化（主訴／背景／評估假設／處遇目標／結案標準）填在同一個 "
                        "card.json 的 conceptualization；結案報告會逐條對照「結案標準」。")

    # 課程
    c_a = a.get("courses") or {}
    courses = list(c_a.get("list") or [])
    courses_on = c_a.get("enabled", True)
    if ask.interactive:
        courses_on = ask.yes("⑥ 要不要「課程記錄」分頁（每堂課記進度、學生反應、下次調整）", True)
        if courses_on:
            ask.say("   先建幾門課？一行一門，直接 Enter 結束（之後在網頁上也能加）。")
            while True:
                title = ask.text("   課名", default="", where="")
                if not title:
                    break
                kind_i = ask.pick("   這門是", ["主課程", "科任", "其他"], 0)
                cid = slug(title, "course-%d" % (len(courses) + 1))
                cid = ask.text("   這門課的英文短名（會變成資料夾名）", default=cid,
                               where="只能用英數與 -，例如 main-block。",
                               check=lambda s: None if valid_id(s) else "只能用英數與 - _。")
                courses.append({"id": cid, "title": title,
                                "kind": ["主課程", "科任", "其他"][kind_i]})

    # 業務
    b_a = a.get("business") or {}
    business_on = b_a.get("enabled", True)
    groups = []
    if ask.interactive:
        ask.say("\n⑦ 業務記錄＝教學以外、但你每天在處理的事（班務、公文、會議、輔導個案…）。")
        business_on = ask.yes("   要不要「業務記錄」分頁", True)
    if business_on:
        chosen_ids = list(b_a.get("groups") or [])
        if ask.interactive:
            idx = ask.multi("   勾選你要的業務組（可複選；一組都不勾也可以）",
                            ["%s — %s" % (g["label"], g.get("desc", "")) for g in lib_groups])
            chosen_ids = [lib_groups[i]["id"] for i in idx]
        by_id = {g["id"]: g for g in lib_groups}
        extra_f = b_a.get("extra_fields") or {}
        extra_t = b_a.get("extra_tags") or {}
        for gid in chosen_ids:
            g = by_id.get(gid)
            if not g:
                lib.warn("業務組庫裡沒有 %s，跳過。" % gid)
                continue
            fields = [dict(f) for f in (g.get("fields") or [])]
            tags = list(g.get("tags") or [])
            for f in (extra_f.get(gid) or []):
                fields.append(dict(f))
            tags += [t for t in (extra_t.get(gid) or []) if t not in tags]
            if ask.interactive:
                ask_extra_fields(ask, "   ", g["label"], fields)
                ask_extra_tags(ask, "   ", g["label"], tags)
            groups.append({"id": gid, "label": g["label"], "fields": fields,
                           "tags": lib.norm_tags(tags), "custom": False})

        customs = list(b_a.get("custom_groups") or [])
        if ask.interactive:
            while ask.yes("   還有清單裡沒有的業務嗎", False):
                label = ask.text("     這項業務叫什麼", allow_empty=False)
                cid = ask.text("     英文短名（會變成資料夾名）", default=slug(label, "custom-%d" % (len(customs) + 1)),
                               check=lambda s: None if valid_id(s) else "只能用英數與 - _。")
                fields = []
                ask.say("     每次要記哪些固定欄位？一行一個，直接 Enter 結束。")
                while True:
                    f = ask_one_field(ask, "       ")
                    if not f:
                        break
                    fields.append(f)
                tags = ask.text("     常用的分類詞（逗號分隔，可留白）", default="")
                rel = ask.yes("     這項業務會不會跟某位學生或某門課有關（要不要「關聯」欄）", True)
                customs.append({"id": cid, "label": label, "fields": fields,
                                "tags": split_list(tags), "relate_students": rel})
        for c in customs:
            groups.append({"id": c["id"], "label": c.get("label") or c["id"],
                           "desc": c.get("desc", ""),
                           "fields": [dict(f) for f in (c.get("fields") or [])],
                           "tags": lib.norm_tags(c.get("tags") or []),
                           "relateStudents": bool(c.get("relate_students", True)),
                           "custom": True})

    # Drive
    ask.say("\n── 第 7 步：備份要放到你自己的 Google 雲端硬碟 ──")
    d_a = a.get("drive") or {}
    mode = d_a.get("mode") or "desktop"
    if ask.interactive:
        mi = ask.pick("⑧ 備份怎麼上雲端硬碟",
                      ["把 zip 複製進「Google 雲端硬碟」桌面程式的同步資料夾（推薦，零設定）",
                       "用 googleworkspace-cli 直接上傳（進階，要自己備 OAuth 憑證）"], 0)
        mode = ["desktop", "gws"][mi]
    default_dir = d_a.get("desktop_dir") or (
        "~/Library/CloudStorage/GoogleDrive-%s/My Drive/教學紀錄備份" % owner)
    desktop_dir = default_dir
    folder_id = d_a.get("backup_folder_id", "")
    if mode == "desktop":
        desktop_dir = ask.text("   備份資料夾路徑", default=default_dir,
                               where="先安裝並登入「Google 雲端硬碟」桌面程式 "
                                     "https://www.google.com/drive/download/ ，"
                                     "在雲端硬碟裡自己建一個資料夾，再把路徑貼過來。")
    else:
        folder_id = ask.text("   Drive 資料夾 ID", default=folder_id,
                             where="打開那個資料夾，網址 .../folders/XXXX 的 XXXX 就是 ID。",
                             allow_empty=False)

    kit = json.loads(json.dumps(lib._strip_comments(kit_ex)))  # 以範本為底，保留所有預設欄位
    kit.update({"version": 3, "owner_email": owner, "id_prefix": prefix.rstrip("-"), "firebase": fb})
    kit["drive"] = {"mode": mode, "desktop_dir": desktop_dir,
                    "backup_folder_id": folder_id,
                    "keep_backups": int(d_a.get("keep_backups", kit.get("drive", {}).get("keep_backups", 12)))}
    if a.get("email"):
        kit["email"] = dict(kit.get("email") or {}, **a["email"])
    if a.get("voice"):
        kit["voice"] = dict(kit.get("voice") or {}, **a["voice"])

    tabs = json.loads(json.dumps(lib._strip_comments(tabs_ex)))
    tabs["version"] = 3
    tabs["students"]["enabled"] = bool(students_on)
    tabs["students"]["streams"] = streams
    tabs["courses"]["enabled"] = bool(courses_on)
    tabs["courses"]["list"] = courses
    tabs["business"]["enabled"] = bool(business_on)
    tabs["business"]["groups"] = groups
    # 垂直方案只是「這位老師比較像哪一種」的標記與期末的預設格式；勾了什麼仍以上面為準。
    tabs["vertical"] = vertical
    tabs["reportFormat"] = (a.get("report_format") or suggest.get("format") or "")
    return kit, tabs, student_ids, members, cards


# ── 資料骨架 ────────────────────────────────────────────────────────────
def build_data(kit, tabs, student_ids, members=None, cards=None):
    """建 data/ 骨架。已存在的檔案一律不覆蓋（重跑安裝不會弄丟任何紀錄）。

    members＝{記錄類型 id: [學生代號…]}：個案型類型「哪些學生列入」，寫進 roster.csv
    第三欄。名冊本來就有的姓名一個字都不會動——只補代號列與第三欄。
    cards＝{學生代號: {goals, conceptualization}}：寫進 data/students/<代號>/card.json。
    卡片已經有內容的那一塊不覆蓋（重跑安裝不會把老師打好的目標蓋掉）。
    """
    made = []
    members = members or {}
    cards = cards or {}
    d = lib.data_dir()
    os.makedirs(d, exist_ok=True)

    # ── 名冊（唯一有真名的檔）：代號,姓名,類型 ──
    rows = lib.load_roster_rows(kit, d)
    before = json.dumps(rows, ensure_ascii=False, sort_keys=True)
    for sid in student_ids:
        rows.setdefault(sid, {"name": "", "streams": []})
    for stream_id, ids in members.items():
        for sid in ids:
            r = rows.setdefault(sid, {"name": "", "streams": []})
            if stream_id not in r["streams"]:
                r["streams"] = r["streams"] + [stream_id]
    roster = lib.roster_path(d)
    if rows and (json.dumps(rows, ensure_ascii=False, sort_keys=True) != before
                 or not os.path.exists(roster)):
        lib.save_roster_rows(rows, d)
        made.append(roster)
    elif not os.path.exists(roster):
        with open(roster, "w", encoding="utf-8") as f:
            f.write(lib.ROSTER_HEADER + "\n")
        made.append(roster)

    # ── 每位學生 × 每一種他所屬的記錄類型一個檔；班級整體觀察每一種 class 類型一個檔 ──
    all_ids = sorted(set(student_ids) | set(rows))
    for s in lib.student_streams(tabs) if (tabs.get("students") or {}).get("enabled", True) else []:
        name = lib.stream_file(s["id"])
        kind = "case" if s.get("scope") == "case" else "students"
        ids = (all_ids if s.get("scope") != "case"
               else sorted({sid for sid in all_ids if s["id"] in (rows.get(sid, {}).get("streams") or [])}))
        for sid in ids:
            p = os.path.join(d, "students", sid, name)
            if not os.path.exists(p):
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "w", encoding="utf-8") as f:
                    f.write(lib.file_header(kind, sid, sid, s.get("label") or s["id"]))
                made.append(p)
        if s.get("scope", "class") != "class":
            continue
        p = os.path.join(d, "class", name)
        if not os.path.exists(p):
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(lib.file_header("class", "main", "班級整體觀察", s.get("label") or s["id"]))
            made.append(p)
    # ── 學生卡片（IEP 目標／個案概念化）──
    for sid, c in sorted(cards.items()):
        old = lib.load_card(sid, d)
        new = dict(old)
        if c.get("goals") and not old.get("goals"):
            new["goals"] = c["goals"]
        if c.get("conceptualization") and not old.get("conceptualization"):
            new["conceptualization"] = c["conceptualization"]
        if new != old or not os.path.exists(lib.card_path(sid, d)):
            made.append(lib.save_card(sid, new, d))

    for c in ((tabs.get("courses") or {}).get("list") or []):
        p = os.path.join(d, "courses", c["id"], "records.md")
        if not os.path.exists(p):
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(lib.file_header("courses", c["id"], c.get("title") or c["id"]))
            made.append(p)
    for g in ((tabs.get("business") or {}).get("groups") or []):
        p = os.path.join(d, "business", g["id"], "records.md")
        if not os.path.exists(p):
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(lib.file_header("business", g["id"], g.get("label") or g["id"]))
            made.append(p)
    for sub in ("inbox", "backups"):
        os.makedirs(lib.rpath(sub), exist_ok=True)
    return made


def write_progress(done_steps, notes=None):
    path = lib.rpath("setup", "progress.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    old = {}
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                old = {s["step"]: s for s in (json.load(f).get("steps") or [])}
        except Exception:
            old = {}
    steps = []
    for i, title in enumerate(STEP_TITLES):
        prev = old.get(i, {})
        done = prev.get("done", False) or (i in done_steps)
        steps.append({"step": i, "title": title, "done": done,
                      "at": lib.now_iso() if (done and not prev.get("at")) else prev.get("at"),
                      "notes": (notes or {}).get(i, prev.get("notes", ""))})
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"version": 3, "steps": steps}, f, ensure_ascii=False, indent=2)
        f.write("\n")
    return path


def read_progress():
    path = lib.rpath("setup", "progress.json")
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def run(script, *args):
    """跑同一組腳本裡的另一支（帶同一個 --root）。先 flush，免得子行程的輸出插在前面。"""
    sys.stdout.flush()
    sys.stderr.flush()
    cmd = [sys.executable, os.path.join(lib.PKG, "scripts", script), "--root", lib.root(), *args]
    return subprocess.run(cmd).returncode


def main():
    ap = argparse.ArgumentParser(
        description="Teacher Records Kit 安裝精靈（互動或照答案檔）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="答案檔範本：templates/answers.example.json")
    ap.add_argument("--answers", metavar="檔案", help="免互動：照這個 JSON 檔的答案安裝")
    ap.add_argument("--upgrade", action="store_true", help="把 v2 的 config.yaml 轉成 v3 的 config/kit.json")
    ap.add_argument("--resume", action="store_true", help="讀 setup/progress.json，接著上次沒做完的地方")
    ap.add_argument("--mark-step", type=int, metavar="N",
                    help="把第 N 步標成完成（AI 代理做完部署、上線這類腳本管不到的事之後用），"
                         "可搭 --note 寫一行備註；只動 setup/progress.json，不碰其他任何檔案")
    ap.add_argument("--note", default="", metavar="文字", help="--mark-step 要寫的備註")
    ap.add_argument("--skip-network", action="store_true", help="健檢時跳過要連網的項目（--answers 時預設就跳過）")
    ap.add_argument("--skip-doctor", action="store_true", help="裝完不跑健檢")
    lib.add_root_arg(ap)
    a = ap.parse_args()
    lib.apply_root(a)
    os.makedirs(lib.rpath("config"), exist_ok=True)

    if a.mark_step is not None:
        if not (0 <= a.mark_step < len(STEP_TITLES)):
            lib.die("步驟編號要在 0 到 %d 之間（收到 %d）。" % (len(STEP_TITLES) - 1, a.mark_step),
                    "步驟清單見 AGENTS.md，或打開 setup/progress.json 看 title。")
        p = write_progress({a.mark_step}, notes={a.mark_step: a.note} if a.note else None)
        lib.ok("第 %d 步標成完成：%s" % (a.mark_step, STEP_TITLES[a.mark_step]))
        print("  %s" % p)
        return

    answers = None
    if a.answers:
        if not os.path.exists(a.answers):
            lib.die("找不到答案檔：%s" % a.answers,
                    "路徑打錯了；範本在 templates/answers.example.json。")
        answers = lib._load_json(a.answers, "答案檔", "照 templates/answers.example.json 的格式寫。")

    if a.resume:
        pg = read_progress()
        if pg:
            undone = [s for s in pg.get("steps", []) if not s.get("done")]
            print("上次的安裝進度：完成 %d／%d 步" % (len(pg.get("steps", [])) - len(undone), len(pg.get("steps", []))))
            if undone:
                print("接下來要做：第 %d 步 %s" % (undone[0]["step"], undone[0]["title"]))
        else:
            lib.warn("找不到 setup/progress.json，當成新安裝。")

    existing_kit = lib.load_kit(required=False)

    if a.upgrade:
        old_path = lib.rpath("config.yaml")
        if not os.path.exists(old_path):
            lib.die("找不到舊版設定 config.yaml：%s" % old_path,
                    "沒有舊設定就不需要 --upgrade，直接跑 `python3 scripts/setup.py`。")
        old = read_legacy_yaml(old_path)
        answers = {
            "owner_email": old.get("owner_email", ""),
            "id_prefix": old.get("id_prefix", "S"),
            "firebase": old.get("firebase", {}),
            "email": old.get("email", {}),
            # v2 的學生觀察檔就是 data/students/<代號>/observations.md，
            # 也就是 v3 的「導師班級學生紀錄」這一種類型——先勾它，舊資料才看得見。
            "students": {"enabled": True, "count": 0, "streams": ["homeroom"]},
            "courses": {"enabled": True, "list": []},
            "business": {"enabled": False, "groups": []},
            "drive": {"mode": "desktop"},
        }
        print("讀到 v2 設定：%s（owner_email、firebase、email 會照搬）" % old_path)
        print("學生記錄先勾「導師班級學生紀錄」一種（＝v2 的 observations.md）；")
        print("要個案追蹤、IEP、輔導晤談這些類型，之後跟 AI 說一聲重跑一次安裝就好。")
        print("業務記錄分頁預設先關著——之後跟 AI 說「我要開業務記錄」再重跑一次安裝就好。")

    ask = Asker(answers)
    if ask.interactive:
        print("\n═══ Teacher Records Kit 安裝精靈 ═══")
        print("一次問一題，不確定就先按 Enter 用預設值，之後改 config/kit.json 再跑")
        print("`python3 scripts/build_config.py` 就會生效。\n")

    kit, tabs, student_ids, members, cards = gather(ask, answers, existing_kit)

    kit_path = lib.rpath(lib.KIT_JSON)
    tabs_path = lib.rpath(lib.TABS_JSON)
    for p, data in ((kit_path, kit), (tabs_path, tabs)):
        if os.path.exists(p):
            shutil.copy2(p, p + ".bak")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.write("\n")
    lib.ok("寫好 %s" % os.path.relpath(kit_path, lib.root()))
    lib.ok("寫好 %s" % os.path.relpath(tabs_path, lib.root()))

    made = build_data(kit, tabs, student_ids, members, cards)
    lib.ok("資料骨架：新建 %d 個檔（已存在的一個都沒動）" % len(made))
    if tabs.get("vertical"):
        v = lib.find_vertical(tabs["vertical"])
        print("  方案：%s（期末預設格式 %s；只是預設，report_pack.py --format 隨時可換）"
              % ((v or {}).get("label") or tabs["vertical"], tabs.get("reportFormat") or "—"))
    if cards:
        print("  學生卡片 %d 張：%s（IEP 目標／個案概念化，之後改 "
              "data/students/<代號>/card.json 或在網頁上改）"
              % (len(cards), "、".join(sorted(cards))))
    streams = (tabs.get("students") or {}).get("streams") or []
    if streams:
        print("  學生記錄類型 %d 種：%s" % (
            len(streams),
            "、".join("%s〔%s〕" % (s["label"], "全班" if s["scope"] == "class" else
                                    "列入 %d 位" % len(members.get(s["id"]) or []))
                      for s in streams)))
    elif (tabs.get("students") or {}).get("enabled"):
        lib.warn("學生記錄一種類型都沒勾——學生分頁不會有任何紀錄。"
                 "要補就重跑一次安裝，在「勾選你要的記錄類型」那題勾起來。")
    if student_ids:
        print("  學生 %d 位（%s…）；姓名等你填進 data/roster.csv（那是唯一有真名的檔，"
              "第三欄是個案型類型列入誰）" % (len(student_ids), student_ids[0]))

    rc = run("build_config.py")
    if rc != 0:
        write_progress({0, 3})
        lib.die("產生網頁設定與規則失敗（build_config.py 回傳 %d）。" % rc,
                "照上面那一行 ✗ 的指示修 config/kit.json，再跑 `python3 scripts/build_config.py`。")

    doctor_rc = None
    if not a.skip_doctor:
        args = ["--skip-network"] if (a.skip_network or answers is not None) else []
        print("\n── 健檢 ──")
        doctor_rc = run("doctor.py", *args)

    # 第 4 步＝「產生設定與規則」，包含 firebase deploy——那一半不是這支腳本做的，
    # 所以這裡不標 done，只記一行備註。部署完由 AI 代理跑 `setup.py --mark-step 4`。
    done = {0, 2, 3}
    if student_ids:
        done.add(6)
    write_progress(done, notes={4: "設定已產生，規則尚未部署"})

    print("\n%s安裝精靈跑完了。%s接下來：" % (lib.GREEN, lib.RESET))
    pid = (kit.get("firebase") or {}).get("project_id") or "<你的專案id>"
    print("  1. 部署安全規則：firebase deploy --only firestore:rules --project %s" % pid)
    print("     部署成功後標記進度：python3 scripts/setup.py --mark-step 4")
    print("  2. 上線：firebase deploy --only hosting --project %s" % pid)
    print("  3. 填名單：data/roster.csv（代號,姓名,類型），然後 `python3 scripts/sync.py --dry-run` 看一次")
    print("  4. 備份夾對不對：`python3 scripts/doctor.py`")
    if doctor_rc:
        print("\n%s健檢有項目沒過（上面 ✗ 的部分）——照每一項的「→」修完再往下。%s" % (lib.YELLOW, lib.RESET))
    print("進度記在 setup/progress.json（AI 代理接手前先讀它）。")


if __name__ == "__main__":
    main()
