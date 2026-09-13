#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""auto_dim_tags.py — 同步時請 AI 代理替學生紀錄補上評量維度的「代表標籤」（選用）。

這支不單獨執行，由 `scripts/sync.py` 在正常同步做完之後叫（`--no-auto-tags` 可以跳過）。

為什麼有這支：網頁上的五維度小籤是「讀的時候」用格式庫的 tagMap＋keywords 當場推出來的，
不寫回紀錄——所以本機 markdown 與匯出檔看不到維度標，而且關鍵詞只是粗篩、會漏。
`config/kit.json` 的 `auto_dim_tags.enabled` 開著的話，同步完會把「還沒有任何代表標籤」的
紀錄正文交給老師自己選的 AI 代理判斷，照實打上代表標籤。**補上的標籤跟老師手打的一模一樣**
（不加任何「AI 補的」記號、網頁外觀不變）；維度則數仍由網頁照標籤算，AI 只負責打標。

規則（每一條都是為了「不要弄丟、不要蓋掉老師的字」）：
  · 只看學生紀錄，而且只看**網頁會自動推導維度**的記錄類型——跟 `site/dashboard.html` 的
    `deriveFormatFor()` 同一個判斷（類型沒有「報告維度」欄位、不是 IEP／SOAP 那種帶卡片的、
    格式庫裡有帶推導表的格式）。維度、說明、代表標籤一律從 `config/report-formats.library.json` 讀，
    代表標籤＝`tagMap` 裡第一個對到那個維度的標。
  · 只挑這樣的紀錄：本機與雲端一致（雲端在、沒有軟刪、沒有 editedOnWeb、contentHash 對得上）、
    正文不空、標籤裡**沒有任何一個代表標籤**、正文沒有名冊真名、而且「這一則＋這一份正文」
    還沒被判斷過。
  · **送給 AI 的只有「代號/紀錄 id」與正文**——沒有名冊、沒有欄位、沒有原本的標籤。
  · AI 的回答只收「這一批的 id」×「格式裡的維度名」。JSON 壞掉、逾時、找不到 CLI、代理回非 0
    ＝這一批一個字都不寫、印一行警告、不記為判斷過，後面的批次也不跑；**sync 照常結束、退出碼不變**。
  · 叫 AI 之前先確認本機 md、它的 .prev.md 與所在資料夾寫得進去；寫不進去整個目標不送。
    每次同步最多送 max_batches 批（預設 2 批＝60 則），剩下的等下次同步。
  · 寫入**只加不刪**：本機**只在那一則的標題列尾端接上缺的代表標籤**，其他每一行一個位元組都不動
    （標題列上的非標籤文字、重複的欄位列都留著）；接完用 lib 的解析器讀回，tags 對、欄位／正文雜湊
    不變才寫。先寫雲端（updateMask 只有 tags／contentHash，一定帶 currentDocument.updateTime
    前置條件；不成立＝網頁上剛好在改 → 跳過、不記、下次再來），再寫本機（先備份 `.<檔名>.prev.md`，
    暫存檔＋os.replace 整檔換新）。本機沒寫成就用剛才 PATCH 回來的 updateTime 當前置條件把雲端改回原樣。
    contentHash 跟著換成新的，所以緊接著再同步一次兩邊一致：零推送、零回寫、零衝突，也不會再問 AI。
    `editedOnWeb` 不碰。換檔前重讀一次、跟一開始讀到的逐位元組比，不同（例如剛好有新紀錄寫進來）就不換、
    雲端改回；md 是捷徑（symlink）的目標整個跳過（os.replace 會把捷徑換成一般檔）。
  · 同一份正文 AI 給不出能用的判斷（JSON 壞、維度名不對、沒回）或本機沒寫成，記一次失敗；失敗過的排到最後，
    滿 2 次就記成看不出維度、不再送——免得每次同步最前面那 60 則都是同一批，後面的永遠輪不到。
  · 判斷過就記在 `data/.auto-dim-tags.json`（目標 → 紀錄 id → 正文雜湊）；AI 判定零個維度也記，
    避免每次同步重問。正文改了才重判；老師自己把補上的標拿掉而正文沒改，就不會再補回去。
  · AI 代理叫起來的同步（無頭交辦、或這支叫的代理自己）不再補標：環境變數 TRK_NO_AUTO_TAGS。

零第三方相依。三家代理 CLI 的非互動叫法住在 `hostos.AGENT_CLIS[*]["oneshot"]`，這裡不寫死。
"""
import os
import sys
import json
import shutil
import hashlib
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib      # noqa: E402
import hostos   # noqa: E402

STATE_FILE = ".auto-dim-tags.json"
BATCH_MAX = 30                           # 一次呼叫最多送幾則（提示詞太長，模型會漏看後面的）
DIM_FIELD = "報告維度"                   # 有這個欄位的類型是老師自己標維度的，不推導、不補標
STUB_ENV = "TRK_AUTO_TAGS_AGENT_CMD"     # 測試與演練：換成一支假的代理，永遠不會叫到真的 AI
SKIP_ENV = "TRK_NO_AUTO_TAGS"            # AI 代理叫起來的同步不補標（不要讓 AI 再叫 AI）
REASON_MAX = 160                         # 警告裡引用代理輸出的長度上限（別把紀錄正文倒進 log）
FAIL_MAX = 2                             # 同一份正文沒補成幾次就記成看不出維度、不再送（不卡住後面的）


# ── 哪些記錄類型、用哪個格式（dashboard.html deriveFormatFor() 的 Python 版）─────
def fmt_dims(fmt):
    dims = (fmt or {}).get("dimensions")
    return [d for d in dims if d] if isinstance(dims, list) else []


def _dict(v):
    return v if isinstance(v, dict) else {}


def fmt_can_derive(fmt):
    """這個格式有沒有推導的本事：有維度，而且 tagMap／keywords 至少一張不是空的。"""
    return bool(fmt and fmt_dims(fmt) and (_dict(fmt.get("tagMap")) or _dict(fmt.get("keywords"))))


def formats_for(stream_id, formats):
    """格式庫裡 `for` 含這種類型的格式（`for` 沒給或空陣列＝每一種都適用）。"""
    out = []
    for f in ((formats or {}).get("formats") or []):
        fr = (f or {}).get("for")
        if not isinstance(fr, list) or not fr or stream_id in fr:
            out.append(f)
    return out


def derive_format_for(stream, formats):
    """這一種記錄類型用哪一個格式推導維度；不推導回 None。

    跟 dashboard.html 的 deriveFormatFor() 一字一句對齊：
      · 有「報告維度」欄位 → 不推（老師自己標了，照欄位分組才是他的意思）
      · 帶目標清單／個案概念化卡片（IEP／SOAP）→ 不推
      · 其餘 → 適用格式裡第一個帶推導表的（homeroom ＝ waldorf-homeroom）
    """
    if not stream:
        return None
    if any((f or {}).get("name") == DIM_FIELD for f in (stream.get("fields") or [])):
        return None
    card = stream.get("card") or {}
    if card.get("goals") or card.get("conceptualization"):
        return None
    for f in formats_for(stream.get("id"), formats):
        if fmt_can_derive(f):
            return f
    return None


def dimension_tags(fmt):
    """維度 → 代表標籤（tagMap 裡排第一個對到它的標）。tagMap 沒有標可以打的維度不列。"""
    tag_map = _dict((fmt or {}).get("tagMap"))
    out = {}
    for dim in fmt_dims(fmt):
        for tag, d in tag_map.items():
            norm = lib.norm_tags([tag])
            if d == dim and norm:
                out[dim] = norm[0]
                break
    return out


def split_tags(tags):
    """語音管線偶爾把幾個標黏成一個（#意志力#學習態度）——比對前先拆開（同 dashboard splitTags）。"""
    out = []
    for t in (tags or []):
        for x in str(t or "").split("#"):
            x = x.strip()
            if x:
                out.append("#" + x)
    return out


def eligible_streams(tabs, formats=None):
    """這位老師勾的類型裡，哪幾種會補標（setup.py 問不問、doctor.py 報什麼都看它）。"""
    formats = formats if formats is not None else lib.load_report_formats()
    out = []
    for s in lib.student_streams(tabs):
        fmt = derive_format_for(s, formats)
        if fmt and dimension_tags(fmt):
            out.append(s["id"])
    return out


def plan(tabs, targets, formats=None):
    """同步目標 → [(目標, 格式, 維度→代表標籤)]，只留會補標的學生目標。"""
    formats = formats if formats is not None else lib.load_report_formats()
    streams = {s["id"]: s for s in lib.student_streams(tabs)}
    out = []
    for t in targets:
        if t.get("kind") != "students" or not t.get("stream"):
            continue
        fmt = derive_format_for(streams.get(t["stream"]), formats)
        tags = dimension_tags(fmt) if fmt else {}
        if tags:
            out.append((t, fmt, tags))
    return out


# ── 挑紀錄 ──────────────────────────────────────────────────────────────
def body_hash(body):
    """「這一份正文」的指紋：只看正文——補了標籤之後 contentHash 會變，這個不會。"""
    return hashlib.sha256((body or "").strip().encode("utf-8")).hexdigest()[:16]


def fail_count(state, key, rid, bh):
    """這一則（這一份正文）之前沒補成過幾次；正文改了就從 0 算。"""
    e = (((state or {}).get("failures") or {}).get(key) or {}).get(rid)
    return int(e.get("n") or 0) if isinstance(e, dict) and e.get("hash") == bh else 0


def _tidy(state):
    """判斷檔裡清空了的目標拿掉。"""
    for k in ("judged", "failures"):
        d = state.get(k)
        if isinstance(d, dict):
            for key in [x for x, v in d.items() if isinstance(v, dict) and not v]:
                d.pop(key)


def has_rep_tag(tags, dimtags):
    reps = set(dimtags.values())
    return any(t in reps for t in split_tags(tags))


def leaks(names, b):
    text = " ".join([b.get("body") or "", " ".join(b.get("tags") or []),
                     " ".join(str(v) for v in (b.get("fields") or {}).values())])
    return lib.find_names(text, names)


def cloud_clean(pair, b):
    """雲端那一份跟本機這一則是不是同一個樣子（同步做完、沒人正在改）。"""
    if not pair:
        return False
    fs, ut = pair
    return (bool(ut) and not lib.is_deleted(fs) and not fs.get("editedOnWeb")
            and fs.get("contentHash") == b["hash"])


def pick(blocks, dimtags, names, judged, cloud=None):
    """要送 AI 判斷的那幾則。cloud=None＝預演（不看雲端，只照本機檔估）。"""
    out = []
    for b in blocks:
        if not (b.get("body") or "").strip():
            continue
        if has_rep_tag(b.get("tags"), dimtags):
            continue
        if leaks(names, b):
            continue                     # 真名攔截：sync 那一段已經印過了，這裡只是絕不送出去
        if (judged or {}).get(b["rid"]) == body_hash(b["body"]):
            continue
        if cloud is not None and not cloud_clean(cloud.get(b["rid"]), b):
            continue                     # 雲端還沒有、軟刪了、網頁正在改、兩邊不一致 → 下次再來
        out.append(b)
    return out


def add_tags(tags, extra):
    """只加不刪：原標籤順序不動，新的接在後面、去重（黏在一起的標也算有）。"""
    out = lib.norm_tags(tags)
    have = set(split_tags(out)) | set(out)
    for t in extra:
        norm = lib.norm_tags([t])
        if norm and norm[0] not in have:
            out.append(norm[0])
            have.add(norm[0])
    return out


# ── 提示詞與回答 ────────────────────────────────────────────────────────
def section_hint(fmt, dim):
    """維度的說明＝格式 sections 裡標題以那個維度結尾（找不到就含那個維度）的 hint。"""
    secs = [s for s in ((fmt or {}).get("sections") or []) if isinstance(s, dict)]
    for s in secs:
        if str(s.get("title") or "").endswith(dim):
            return str(s.get("hint") or "").strip()
    for s in secs:
        if dim in str(s.get("title") or ""):
            return str(s.get("hint") or "").strip()
    return ""


def build_prompt(fmt, dims, items):
    """一批紀錄的提示詞。items 的每一項要有 id 與 block（只取 block 的正文）。"""
    lines = ["你在替一位老師整理學生觀察紀錄的「評量維度」。這是純文字判斷：不需要、也不要使用任何工具，"
             "不要讀或寫任何檔案。",
             "",
             "評量維度（名稱：說明）："]
    for d in dims:
        lines.append("- %s：%s" % (d, section_hint(fmt, d) or "（沒有說明）"))
    lines += ["",
              "判準：",
              "1. 正文看得出這個維度就打；單一事件也照打。一則可以同時屬於好幾個維度。",
              "2. 只依正文判斷，不推測正文沒寫的事。看不出任何維度就給空陣列。",
              "3. 維度名稱一字不差照上面的寫法，不要縮寫，也不要自己加新的維度。",
              "",
              "輸出：只輸出一個 JSON 物件，不要任何說明文字，也不要用 Markdown 程式碼框包起來。",
              "每一則的 id 都要出現一次，值是維度名稱的陣列。",
              "形狀：{\"<id>\": [\"<維度名稱>\", …], \"<另一則的 id>\": []}",
              "",
              "紀錄（JSON 陣列，每一則有 id 與 text）：",
              json.dumps([{"id": it["id"], "text": (it["block"].get("body") or "").strip()}
                         for it in items], ensure_ascii=False, indent=1)]
    return "\n".join(lines) + "\n"


def parse_answer(text):
    """代理的輸出 → dict。容忍前後空白與 ``` 圍欄；找不到 JSON 物件就丟 ValueError。"""
    t = (text or "").strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        t = t.rstrip()
        if t.endswith("```"):
            t = t[:-3]
    try:
        obj = json.loads(t)
    except ValueError:
        i, j = t.find("{"), t.rfind("}")
        if i < 0 or j <= i:
            raise ValueError("輸出裡找不到 JSON 物件")
        obj = json.loads(t[i:j + 1])
    if not isinstance(obj, dict):
        raise ValueError("輸出不是 JSON 物件")
    return obj


def validate(answer, ids, dims):
    """只收「這一批的 id」×「格式裡的維度名」。回 (ok, bad, unknown)。

    ok＝{id: [維度…]}（照格式的維度順序、去重；空陣列＝判定零個維度）；
    bad＝值不是維度名陣列的 id（整則不收）；unknown＝不是這一批的 id（忽略）。
    沒出現在回答裡的 id 三個都不在——呼叫端當成「沒判斷」，下次再問。
    """
    ok, bad, unknown = {}, [], []
    dimset = set(dims)
    for k, v in answer.items():
        if k not in ids:
            unknown.append(k)
            continue
        if not isinstance(v, list) or any(not isinstance(x, str) or x.strip() not in dimset for x in v):
            bad.append(k)
            continue
        got = {x.strip() for x in v}
        ok[k] = [d for d in dims if d in got]
    return ok, bad, unknown


# ── 叫代理 ──────────────────────────────────────────────────────────────
class AgentMissing(RuntimeError):
    """代理 CLI 不認得或這台電腦上找不到。"""


def agent_argv(agent, out_file):
    """要跑的 argv（提示詞走 stdin，不在 argv 裡）。測試用 TRK_AUTO_TAGS_AGENT_CMD 換成假的。"""
    stub = (os.environ.get(STUB_ENV) or "").strip()
    if stub:
        if not os.path.exists(stub):
            raise AgentMissing("找不到假代理 %s（%s）" % (stub, STUB_ENV))
        return [sys.executable, stub] if stub.lower().endswith(".py") else [stub]
    argv = hostos.agent_oneshot_argv(agent, out_file)
    if not argv:
        raise AgentMissing("不認得的 AI 代理 %r（只支援 %s）" % (agent, "、".join(hostos.AGENT_ORDER)))
    path = hostos.exe(argv[0])
    if not path:
        raise AgentMissing("這台電腦上找不到 %s。%s" % (argv[0], hostos.agent_install_hint(agent)))
    return [path] + argv[1:]


def run_agent(argv, text, timeout, cwd=None, out_file=None):
    """跑代理：提示詞從 stdin 餵進去，逾時就連子孫行程一起殺。回 (returncode, 回答, stderr)。

    提示詞走 stdin 不走 argv：一批 30 則的正文動輒上萬字，Windows 的命令列上限是 32767 字元，
    npm 裝的 codex／gemini 又是 .cmd（經 cmd.exe 會把換行截斷）。
    回答優先讀 out_file（codex 的 `-o` 只寫最後一則訊息，不怕 stdout 夾雜進度），沒有才用 stdout。
    """
    kw = {}
    if hostos.OS == "win":
        kw["creationflags"] = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        kw["start_new_session"] = True
    env = dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONUTF8="1")
    env[SKIP_ENV] = "1"                  # 代理要是自己跑了 sync.py，那一次不准再叫 AI
    try:
        p = subprocess.Popen(argv, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, env=env, **kw)
    except OSError as e:
        return 127, "", str(e)
    try:
        out, err = p.communicate(input=text.encode("utf-8"), timeout=timeout)
    except subprocess.TimeoutExpired:
        hostos.kill_tree(p)
        try:
            out, err = p.communicate(timeout=10)
        except Exception:                # noqa: BLE001 殺掉之後讀不到就算了
            out, err = b"", b""
        return 124, hostos.decode_output(out), hostos.decode_output(err)
    answer = hostos.decode_output(out)
    if out_file and os.path.exists(out_file):
        try:
            with open(out_file, encoding="utf-8", errors="replace") as f:
                got = f.read()
            if got.strip():
                answer = got
        except OSError:
            pass
    return p.returncode, answer, hostos.decode_output(err)


# ── 判斷紀錄 ────────────────────────────────────────────────────────────
def state_path():
    return os.path.join(lib.data_dir(), STATE_FILE)


def load_state():
    p = state_path()
    try:
        with open(p, encoding="utf-8") as f:
            st = json.load(f)
        if isinstance(st, dict) and isinstance(st.get("judged"), dict):
            return st
    except (OSError, ValueError):
        pass
    return {"version": 1, "judged": {}}


def save_state(st):
    os.makedirs(lib.data_dir(), exist_ok=True)
    st["at"] = lib.now_iso()
    tmp = state_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)
    os.replace(tmp, state_path())


def _doc_stream(fs):
    return (fs.get("stream") or "").strip() or "homeroom"      # 同 sync.doc_stream


def _reason(rc, out, err):
    tail = [x.strip() for x in ((err or "") + "\n" + (out or "")).splitlines() if x.strip()]
    msg = tail[-1] if tail else ""
    return ("回傳 %d：%s" % (rc, msg[:REASON_MAX])) if msg else "回傳 %d" % rc


def prev_path(path):
    d, name = os.path.dirname(path), os.path.basename(path)
    return os.path.join(d, "." + name.replace(".md", "") + ".prev.md")


def writable(path):
    """這個 md、它的 .prev.md 備份、放暫存檔的資料夾都寫得進去嗎。叫 AI 之前先問——
    寫不進去還去判斷，就只會「雲端補上、本機寫不進、再改回去」，每次同步白叫一次 AI。"""
    d = os.path.dirname(path) or "."
    if not (os.path.exists(path) and os.access(path, os.W_OK) and os.access(d, os.W_OK)):
        return False
    prev = prev_path(path)
    return not os.path.exists(prev) or os.access(prev, os.W_OK)


def _strip_cr(line):
    return line[:-1] if line.endswith("\r") else line


def read_raw(path):
    """(raw_lines, blocks)。raw_lines 是檔案原樣切行（保留行尾 \r 與檔頭 BOM），寫回時其他行逐位元組不動；
    blocks 是 lib.parse_file 的結果（start／end 行號跟 raw_lines 對得上）。
    兩邊對不齊（例如只用 \r 換行的舊檔）或檔案不在，raw_lines 回 None——那種檔不補標。"""
    lines, blocks = lib.parse_file(path)
    if not os.path.exists(path):
        return None, blocks
    with open(path, encoding="utf-8", newline="") as f:
        raw_lines = f.read().split("\n")
    norm = [_strip_cr(x) for x in raw_lines]
    if norm and norm[0].startswith("\ufeff"):
        norm[0] = norm[0][1:]
    return (raw_lines if norm == lines else None), blocks


def header_with_tags(line, added):
    """標題列尾端接上缺的標籤（行尾原本的 \r 留著）。"""
    end = "\r" if line.endswith("\r") else ""
    return line[:len(line) - len(end)].rstrip(" \r\n") + " " + " ".join(added) + end   # 全形空白 U+3000 留著


def append_edit(raw_lines, b, new_tags):
    """只改 b 的標題列那一行：尾端接上 new_tags 比原本多出來的標，其他行一個位元組都不動。

    接完用 lib 的解析器把那一則讀回來驗：rid 一樣、tags＝new_tags、欄位／關聯／正文不變、
    雜湊＝content_hash(new_tags, …)。任何一項不符回 None（呼叫端不寫、不記、印警告）。
    （以前用 render_block 整則重畫，會吃掉標題列上的非標籤文字與重複鍵的欄位列。）
    """
    old = list(b["tags"])
    new_tags = list(new_tags)
    added = new_tags[len(old):]
    s, e = b["start"], b["end"]
    if raw_lines is None or not added or new_tags[:len(old)] != old or not (0 <= s < e <= len(raw_lines)):
        return None
    new = list(raw_lines)
    new[s] = header_with_tags(raw_lines[s], added)
    seg = [_strip_cr(x) for x in new[s:e]]
    if s == 0 and seg[0].startswith("\ufeff"):
        seg[0] = seg[0][1:]
    got = lib.parse_block(seg)
    if (not got or got["rid"] != b["rid"] or got["tags"] != new_tags
            or got["fields"] != b["fields"] or got["related"] != b["related"] or got["body"] != b["body"]
            or got["hash"] != lib.content_hash(new_tags, b["fields"], b["related"], b["body"])):
        return None
    return new


def replace_file(path, text):
    """整檔換新：先寫同一個資料夾的暫存檔再 os.replace——寫到一半失敗不會留下被截斷的原檔；權限位元照舊。"""
    tmp = os.path.join(os.path.dirname(path) or ".", "." + os.path.basename(path) + ".auto-dim-tags.tmp")
    try:
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        shutil.copymode(path, tmp)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def update_time_of(res):
    """帶前置條件的 PATCH（documents:commit）回來的 updateTime；拿不到回 ""。"""
    res = res if isinstance(res, dict) else {}
    wr = res.get("writeResults") or [{}]
    return ((wr[0] if isinstance(wr[0], dict) else {}).get("updateTime")
            or res.get("updateTime") or res.get("commitTime") or "")


class _Run(object):
    def __init__(self, kit, tabs, targets, base, tok, names, dry, since, progress, formats):
        self.cfg = lib.auto_dim_tags_cfg(kit)
        self.tabs, self.targets, self.base, self.tok = tabs, targets, base, tok
        self.names, self.dry, self.since, self.progress = names, dry, since, progress
        self.formats = formats
        self.lines, self.warnings = [], []
        self.counts = dict.fromkeys(("candidates", "asked", "tagged", "tags", "zero", "skipped", "later",
                                     "gaveup"), 0)
        self._cloud = {}

    def say(self, msg):
        if self.progress:
            self.progress(msg)

    def cloud(self, t, fresh=False):
        """雲端這個目標的紀錄 {rid: (fields, updateTime)}；同一個集合一輪只列一次（fresh 重列）。"""
        coll = t["records"]
        if fresh or coll not in self._cloud:
            self._cloud[coll] = lib.list_docs(self.base, coll, self.tok, raise_errors=True)
        return {rid: (fs, ut) for rid, fs, ut in self._cloud[coll] if _doc_stream(fs) == t["stream"]}

    def go(self):
        planned = plan(self.tabs, self.targets, self.formats)
        if not planned:
            return
        state = load_state()
        judged_all = state["judged"]
        items, changed = [], False
        for t, fmt, dimtags in planned:
            raw_lines, blocks = read_raw(t["path"])
            judged = dict(judged_all.get(t["key"]) or {})
            if blocks:
                # 本機已經沒有的那一則就不用記了。整個檔不見或變空的時候不修剪（跟 sync 的刪除保護同理）。
                present = {b["rid"] for b in blocks}
                kept = {r: h for r, h in judged.items() if r in present}
                if kept != judged:
                    judged, changed = kept, True
                    if kept:
                        judged_all[t["key"]] = kept
                    else:
                        judged_all.pop(t["key"], None)
                fails = (state.get("failures") or {}).get(t["key"]) or {}
                for r in [r for r in fails if r not in present]:
                    fails.pop(r)
                    changed = True
            local = pick(blocks, dimtags, self.names, judged)
            if local and os.path.islink(t["path"]):
                self.warnings.append("評量維度補標：本機檔 %s 是捷徑（symlink）——整檔換新會把捷徑換成一般檔，"
                                     "這個目標的 %d 則不送 AI、不動" % (t["sourceFile"], len(local)))
                continue
            if local and not writable(t["path"]):
                self.warnings.append("評量維度補標：本機檔 %s（或它的 .prev.md 備份、所在資料夾）寫不進去——"
                                     "這個目標的 %d 則這次不送 AI；拿掉唯讀之後下次同步會補"
                                     % (t["sourceFile"], len(local)))
                continue
            if local:
                probe = next(iter(dimtags.values()))
                fits = [b for b in local if append_edit(raw_lines, b, list(b["tags"]) + [probe]) is not None]
                fit_rids = {b["rid"] for b in fits}
                unfit = sorted("%s:%s" % (b["rid"], b["hash"]) for b in local if b["rid"] not in fit_rids)
                sig = hashlib.sha256("|".join(unfit).encode("utf-8")).hexdigest()[:16] if unfit else ""
                seen = state.setdefault("unfit", {})
                if unfit and seen.get(t["key"]) != sig:
                    # 同一份內容只提醒一次（記在判斷檔）；檔案沒改，下一次同步就安靜跳過
                    self.warnings.append("評量維度補標：%s 有 %d 則沒辦法只在標題列尾端接上標籤（例如只用 \\r 換行的舊檔）"
                                         "——那幾則不送 AI、不動（同一份內容只提醒這一次）"
                                         % (t["sourceFile"], len(unfit)))
                    seen[t["key"]] = sig
                    changed = True
                elif not unfit and t["key"] in seen:
                    seen.pop(t["key"])
                    changed = True
                local = fits
            if local and not self.dry:
                # 本機有候選才去讀雲端（沒事做的目標一次讀取都不多花）；雲端不一致的那幾則這一輪不送
                local = pick(local, dimtags, self.names, judged, self.cloud(t))
            for b in local:
                items.append({"t": t, "fmt": fmt, "dimtags": dimtags, "block": b,
                              "id": "%s/%s" % (t["id"], b["rid"])})
        self.counts["candidates"] = len(items)
        # 沒補成過的排到最後（穩定排序，其餘照原本順序）
        items.sort(key=lambda it: fail_count(state, it["t"]["key"], it["block"]["rid"],
                                             body_hash(it["block"]["body"])) > 0)

        # 同一個格式（維度表）的才放同一批；一批最多 BATCH_MAX 則；一次同步最多 max_batches 批
        batches, by_fmt = [], {}
        for it in items:
            by_fmt.setdefault(it["fmt"].get("id") or "", []).append(it)
        for group in by_fmt.values():
            for i in range(0, len(group), BATCH_MAX):
                batches.append(group[i:i + BATCH_MAX])
        limit = self.cfg["max_batches"]
        later = sum(len(b) for b in batches[limit:])
        batches = batches[:limit]
        self.counts["later"] = later
        later_line = ("評量維度補標：還有 %d 則等下次同步（每次同步最多送 %d 批、每批最多 %d 則；"
                      "要調就改 config/kit.json 的 auto_dim_tags.max_batches）" % (later, limit, BATCH_MAX))

        if self.dry:
            if items:
                per = {}
                for it in (x for b in batches for x in b):          # 只算這一輪會送的
                    per[it["t"]["id"]] = per.get(it["t"]["id"], 0) + 1
                self.lines.append("（預演）評量維度補標：會送 AI 代理（%s）判斷 %d 則（%s）——以本機檔現況估，"
                                  "這一輪才會從網頁帶下來的不在內"
                                  % (self.cfg["agent"], len(items) - later,
                                     "、".join("%s %d 則" % kv for kv in sorted(per.items()))))
                if later:
                    self.lines.append("（預演）" + later_line)
            else:
                self.lines.append("（預演）評量維度補標：沒有要送 AI 判斷的紀錄")
            return
        if changed:
            save_state(state)
        if not items:
            return

        workdir = hostos.work_dir()
        done = 0
        for n, batch in enumerate(batches):
            left = len(items) - done
            fmt, dimtags = batch[0]["fmt"], batch[0]["dimtags"]
            dims = [d for d in fmt_dims(fmt) if d in dimtags]
            ids = {it["id"]: it for it in batch}
            out_file = os.path.join(workdir, "auto-dim-tags-%d-%d.txt" % (os.getpid(), n))
            try:
                if os.path.exists(out_file):
                    os.remove(out_file)
                argv = agent_argv(self.cfg["agent"], out_file)
            except AgentMissing as e:
                self.warnings.append("評量維度補標沒有跑：%s——同步本身已經完成；%d 則等下次同步再判斷"
                                     % (e, left))
                return
            self.say("評量維度補標：請 %s 判斷 %d 則（第 %d／%d 批）…"
                     % (self.cfg["agent"], len(batch), n + 1, len(batches)))
            try:
                rc, out, err = run_agent(argv, build_prompt(fmt, dims, batch), self.cfg["timeout_sec"],
                                         cwd=workdir, out_file=out_file)
            finally:
                try:
                    if os.path.exists(out_file):
                        os.remove(out_file)
                except OSError:
                    pass
            if rc == 124:
                self.warnings.append("評量維度補標：AI 代理 %s 超過 %d 秒沒回答，已停掉——這一批一個字都沒寫；"
                                     "同步本身已經完成，%d 則等下次同步再判斷"
                                     % (self.cfg["agent"], self.cfg["timeout_sec"], left))
                return
            if rc != 0:
                self.warnings.append("評量維度補標：AI 代理 %s 沒有正常結束（%s）——這一批一個字都沒寫；"
                                     "同步本身已經完成，%d 則等下次同步再判斷。先在終端機直接跑一次 %s 確認有登入"
                                     % (self.cfg["agent"], _reason(rc, out, err), left, self.cfg["agent"]))
                return
            try:
                answer = parse_answer(out)
            except ValueError as e:
                self.warnings.append("評量維度補標：AI 代理 %s 回的不是可以用的 JSON（%s）——這一批一個字都沒寫；"
                                     "同步本身已經完成，%d 則等下次同步再判斷（這一批各記一次沒補成，排到後面）"
                                     % (self.cfg["agent"], e, left))
                for it in batch:
                    self.fail(state, it["t"], it["block"])
                _tidy(state)
                save_state(state)
                return
            ok, bad, unknown = validate(answer, set(ids), dims)
            failed = [i for i in ids if i not in ok]
            missing = len(failed) - len(bad)
            if bad or unknown or missing:
                self.warnings.append("評量維度補標：這一批 %d 則裡，%d 則回了格式裡沒有的維度名、%d 則沒有回、"
                                     "另有 %d 個不認得的 id——那些一個字都沒寫，排到後面、下次同步再判斷"
                                     % (len(ids), len(bad), missing, len(unknown)))
            for iid in failed:
                self.fail(state, ids[iid]["t"], ids[iid]["block"])
            self.apply(ok, ids, state)
            self.counts["asked"] += len(batch)
            done += len(batch)
            _tidy(state)
            save_state(state)
        if later:
            self.lines.append(later_line)

    def fail(self, state, t, b):
        """這一份正文沒補成一次（AI 給不出能用的判斷，或本機沒寫成）。滿 FAIL_MAX 次記成看不出維度、不再送。"""
        bh = body_hash(b["body"])
        n = fail_count(state, t["key"], b["rid"], bh) + 1
        fails = state.setdefault("failures", {}).setdefault(t["key"], {})
        if n < FAIL_MAX:
            fails[b["rid"]] = {"hash": bh, "n": n}
            return
        fails.pop(b["rid"], None)
        state.setdefault("judged", {}).setdefault(t["key"], {})[b["rid"]] = bh
        self.counts["gaveup"] += 1
        self.warnings.append("評量維度補標：%s %s 同一份正文已經 %d 次沒補成（AI 給不出能用的判斷，或本機一直寫不進去）"
                             "——記成看不出維度、不再送；要重判就改一下正文，或刪掉 data/%s"
                             % (t["key"], b["rid"], n, STATE_FILE))

    def _done(self, state, t, judged, b):
        judged[b["rid"]] = body_hash(b["body"])
        ((state.get("failures") or {}).get(t["key"]) or {}).pop(b["rid"], None)

    def apply(self, ok, ids, state):
        """把判到的維度寫回去：先雲端（前置條件）、再本機；本機沒寫成就把雲端改回去。成功（或判定零個）才記。"""
        per_target = []
        seen = {}
        for iid, dims in ok.items():
            it = ids[iid]
            key = it["t"]["key"]
            if key not in seen:
                seen[key] = len(per_target)
                per_target.append((it["t"], it["dimtags"], []))
            per_target[seen[key]][2].append((it, dims))

        for t, dimtags, pairs in per_target:
            judged = state["judged"].setdefault(t["key"], {})
            try:
                fresh = self.cloud(t, fresh=True)
            except Exception as e:          # noqa: BLE001 連不上：這個目標整批跳過，下次再來
                self.counts["skipped"] += len(pairs)
                self.warnings.append("評量維度補標：讀不到雲端的 %s（%s）——這幾則沒寫，下次同步再判斷"
                                     % (t["key"], str(e)[:REASON_MAX]))
                continue
            raw_lines, blocks = read_raw(t["path"])
            now = {b["rid"]: b for b in blocks}
            writes = []
            for it, dims in pairs:
                b0 = it["block"]
                b = now.get(b0["rid"])
                if not b or b["hash"] != b0["hash"] or not cloud_clean(fresh.get(b["rid"]), b):
                    # AI 判斷的這段時間裡，本機檔或網頁上改過這一則 → 不寫、不記，下次同步重判
                    self.counts["skipped"] += 1
                    continue
                new_tags = add_tags(b["tags"], [dimtags[d] for d in dims if d in dimtags])
                if new_tags == b["tags"]:
                    self._done(state, t, judged, b)
                    self.counts["zero"] += 1
                    continue
                if append_edit(raw_lines, b, new_tags) is None:
                    # 雲端也還沒寫：接上標籤之後讀回來對不上，兩邊都不動
                    self.counts["skipped"] += 1
                    self.fail(state, t, b)
                    self.warnings.append("評量維度補標：%s %s 在標題列尾端接上標籤之後讀回來對不上——"
                                         "雲端與本機都沒寫、不記判斷" % (t["key"], b["rid"]))
                    continue
                new_hash = lib.content_hash(new_tags, b["fields"], b["related"], b["body"])
                _fs, ut = fresh[b["rid"]]
                try:
                    res = lib.http("PATCH", self.base, "%s/%s" % (t["records"], b["rid"]), self.tok,
                                   {"tags": new_tags, "contentHash": new_hash},
                                   mask=["tags", "contentHash"], precondition_update_time=ut,
                                   raise_errors=True)
                except lib.Precondition:
                    self.counts["skipped"] += 1
                    self.lines.append("評量維度補標跳過 %s %s：網頁上剛好在改這一則——沒寫，下次同步再判斷"
                                      % (t["key"], b["rid"]))
                    continue
                except Exception as e:      # noqa: BLE001 寫不上去就算這一則沒做
                    self.counts["skipped"] += 1
                    self.warnings.append("評量維度補標：%s %s 寫不上雲端（%s）——沒寫，下次同步再判斷"
                                         % (t["key"], b["rid"], str(e)[:REASON_MAX]))
                    continue
                writes.append((b, new_tags, new_hash, update_time_of(res)))
            if not writes:
                continue
            try:
                status = self.write_local(t, writes)
            except Exception as e:          # noqa: BLE001 檔案沒換成：下面逐則把雲端改回去
                status = {}
                self.warnings.append("評量維度補標：本機檔 %s 寫不進去（%s）"
                                     % (t["sourceFile"], str(e)[:REASON_MAX]))
            for b, new_tags, _h, ut2 in writes:
                st = status.get(b["rid"], "unwritten")
                if st == "ok":
                    self._done(state, t, judged, b)
                    self.counts["tagged"] += 1
                    self.counts["tags"] += len(new_tags) - len(b["tags"])
                    continue
                self.counts["skipped"] += 1
                if st == "unwritten":
                    self.rollback(t, b, ut2)
                    self.fail(state, t, b)
                else:
                    self.warnings.append("評量維度補標：%s %s 本機檔寫進去之後讀回來跟預期不一樣（可能剛好有別的程式"
                                         "同時在寫這個檔）——雲端不動、不記判斷，下一輪同步照本機為準"
                                         % (t["key"], b["rid"]))
            if not judged:
                state["judged"].pop(t["key"], None)

    def rollback(self, t, b, ut):
        """本機沒寫成：用剛才 PATCH 回來的 updateTime 當前置條件，把雲端 tags／contentHash 改回原樣。"""
        where = "%s %s" % (t["key"], b["rid"])
        if not ut:
            self.warnings.append("評量維度補標：%s 雲端已補上標籤、本機沒寫成，而且拿不到雲端的 updateTime，沒辦法安全地"
                                 "改回——下一輪同步會照本機那一份把雲端蓋回去；網頁上若同時改過會報衝突，"
                                 "打開 %s 跟網頁比對" % (where, t["sourceFile"]))
            return
        try:
            lib.http("PATCH", self.base, "%s/%s" % (t["records"], b["rid"]), self.tok,
                     {"tags": list(b["tags"]), "contentHash": b["hash"]},
                     mask=["tags", "contentHash"], precondition_update_time=ut, raise_errors=True)
            self.warnings.append("評量維度補標：%s 本機檔沒寫成，雲端剛補上的標籤已經改回原樣——不記判斷，下次同步再來"
                                 % where)
        except lib.Precondition:
            self.warnings.append("評量維度補標：%s 本機檔沒寫成，想把雲端改回原樣時回滾也失敗：網頁上剛好又改了這一則，"
                                 "雲端維持補上標籤的樣子——下一輪同步多半會報衝突，打開 %s 跟網頁比對後留一邊"
                                 % (where, t["sourceFile"]))
        except Exception as e:              # noqa: BLE001
            self.warnings.append("評量維度補標：%s 本機檔沒寫成，想把雲端改回原樣時回滾也失敗（%s）——下一輪同步會照本機"
                                 "那一份把雲端蓋回去；網頁上若同時改過會報衝突，打開 %s 跟網頁比對"
                                 % (where, str(e)[:REASON_MAX], t["sourceFile"]))

    def write_local(self, t, writes):
        """本機檔：只在那幾則的標題列尾端接上標籤，其他行逐位元組不動；先備份 .prev.md。

        回 {rid: "ok"｜"unwritten"｜"mismatch"}。unwritten＝檔案裡那一則沒動（呼叫端把雲端改回去）；
        mismatch＝檔案換了、但讀回來的雜湊不是預期的（多半是剛好有別的程式同時在寫）。
        """
        path = t["path"]
        status = {w[0]["rid"]: "unwritten" for w in writes}
        if os.path.islink(path):
            self.lines.append("評量維度補標：本機檔 %s 是捷徑（symlink）——本機沒動" % t["sourceFile"])
            return status
        with open(path, "rb") as f:
            before = f.read()
        raw_lines, blocks = read_raw(path)
        if raw_lines is None or "\n".join(raw_lines).encode("utf-8") != before:
            self.lines.append("評量維度補標：本機檔 %s 在補標途中被改過——這次不換檔" % t["sourceFile"])
            return status
        now = {b["rid"]: b for b in blocks}
        new_raw, landed = raw_lines, []
        for b, new_tags, new_hash, _ut in writes:
            cur = now.get(b["rid"])
            nxt = append_edit(new_raw, cur, new_tags) if (cur and cur["hash"] == b["hash"]) else None
            if nxt is None:
                self.lines.append("評量維度補標：本機 %s %s 剛好被改過（或標題列接不上標籤）——本機沒動"
                                  % (t["key"], b["rid"]))
                continue
            new_raw = nxt
            landed.append((b["rid"], new_hash))
        if not landed:
            return status
        prev = prev_path(path)
        # 這一輪 sync 已經回寫過這個檔的話，.prev.md 裡是同步前的樣子——留著它，不要用補標前的樣子蓋掉。
        if self.since is None or os.path.getmtime(path) < self.since or not os.path.exists(prev):
            shutil.copy2(path, prev)
        # 換檔前重讀一次、逐位元組比：一開始讀完到現在，append_record.py 可能剛好追加了一則——
        # 直接換會讓那一則從 md（和 .prev.md）都消失。不同就不換，呼叫端把雲端改回去。
        # （剩下「重讀到 os.replace」之間的極短窗口擋不掉；sync.py 的回寫整檔重寫也有同樣的限制。）
        with open(path, "rb") as f:
            if f.read() != before:
                self.lines.append("評量維度補標：本機檔 %s 在補標途中被改過（例如剛好有新紀錄寫進來）——這次不換檔"
                                  % t["sourceFile"])
                return status
        replace_file(path, "\n".join(new_raw))
        _l, after = lib.parse_file(path)
        got = {x["rid"]: x["hash"] for x in after}
        for rid, h in landed:
            status[rid] = "ok" if got.get(rid) == h else "mismatch"
        return status

    def summary(self):
        c = self.counts
        if self.dry or not c["asked"]:
            return
        self.lines.insert(0, "評量維度補標：AI 判斷 %d 則，補上標籤 %d 則（共 %d 個標）、看不出維度 %d 則、跳過 %d 則"
                          % (c["asked"], c["tagged"], c["tags"], c["zero"], c["skipped"]))


def run(kit, tabs, targets, base, tok, names, dry=False, since=None, progress=None, formats=None):
    """sync.py 在正常同步做完之後叫這一支。沒開（或視同沒設定）回 None。

    回 {"lines": [...], "warnings": [...], "counts": {...}}。**永遠不丟例外、永遠不結束行程**——
    這一段出任何事，同步本身都已經完成了，退出碼不可以因為它改變。
    """
    cfg = lib.auto_dim_tags_cfg(kit)
    if not cfg["enabled"] or not cfg["agent"] or lib.is_local(kit):
        return None
    r = _Run(kit, tabs, targets, base, tok, names, dry, since, progress, formats)
    if os.environ.get(SKIP_ENV):
        r.lines.append("評量維度補標：這一次同步是 AI 代理叫起來的，不再叫另一支 AI——下一次一般同步會補")
        return {"lines": r.lines, "warnings": r.warnings, "counts": r.counts}
    try:
        r.go()
    except (Exception, SystemExit) as e:     # noqa: BLE001 lib 的某些錯誤會 die()：這裡一律吞成警告
        r.warnings.append("評量維度補標中途停下來（%s）——同步本身已經完成，還沒寫的下次同步再判斷"
                          % (str(e)[:REASON_MAX] or type(e).__name__))
    r.summary()
    return {"lines": r.lines, "warnings": r.warnings, "counts": r.counts}
