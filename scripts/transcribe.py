#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""transcribe.py — 錄音檔 → 逐字稿（全程在你自己的電腦上跑，錄音與逐字稿都不出本機）。

流程：ffmpeg 轉成 16kHz 單聲道 wav（暫存，用完就刪）→ whisper.cpp 轉錄 →
      寫成 inbox/transcripts/<檔名>.md（每行帶 [HH:MM:SS] 時間戳）→ 原始錄音移到 inbox/done/。

模型第一次會自動下載到 ~/.cache/whisper-cpp/（約 1.6GB，會顯示進度；Windows 的 ~ 是 C:\\Users\\你）。

用法：
  python3 scripts/transcribe.py --inbox             把 inbox/ 裡的錄音全部轉一遍
  python3 scripts/transcribe.py 會議.m4a            轉指定的檔
  python3 scripts/transcribe.py --inbox --keep      轉完不要搬動原始檔
  python3 scripts/transcribe.py --lang en 某檔.mp3  換語言

轉完之後，改寫成記錄這一步**不在這支腳本裡**——把逐字稿交給你的 AI 代理，
它讀完會用 scripts/append_record.py 寫進正確的檔案（腳本結尾會把指令印出來）。
"""
import os
import re
import sys
import json
import shutil
import tempfile
import argparse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib
import hostos

AUDIO_EXT = (".m4a", ".mp3", ".wav", ".mp4", ".mov", ".aac", ".flac", ".ogg", ".m4v", ".caf")
MODEL_DIR = hostos.model_dir()
MODEL_URL = hostos.WHISPER_MODEL_URL          # 網址的正本在 hostos（CI 的 urls job 每週檢查它們還活著）
VAD_NAME = hostos.WHISPER_VAD_NAME
VAD_URL = hostos.WHISPER_VAD_URL
PRIMER = "以下是台灣的教學現場錄音，請用繁體中文（台灣用語）記錄。"

# 外部工具的逾時：轉檔與轉錄都可能很久（一小時的會議錄音），但不能「永遠」——
# 卡住的子行程會讓整條管線靜靜地停在那裡，老師只看到游標在閃。
FFMPEG_TIMEOUT = 600         # 10 分鐘：轉成 16kHz wav，再長的錄音也不該超過
FFPROBE_TIMEOUT = 120
WHISPER_TIMEOUT = 3600       # 1 小時：large-v3-turbo 在沒有 GPU 的筆電上真的會跑這麼久


def hms(sec):
    sec = int(sec)
    return "%02d:%02d:%02d" % (sec // 3600, (sec % 3600) // 60, sec % 60)


def need(cmd):
    p = hostos.exe(cmd)
    if not p:
        lib.die("找不到 %s。" % cmd, hostos.install_hint(cmd) or hostos.install_hint("ffmpeg"))
    return p


def download(url, dest):
    """下載模型，印百分比進度。中斷不會留下半個檔（先寫 .part 再改名）。"""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    print("下載模型：%s" % url)
    print("（第一次要等一下，之後就不用再下載了）")

    def hook(blocks, bs, total):
        if total > 0:
            done = min(blocks * bs, total)
            pct = done * 100.0 / total
            sys.stdout.write("\r  %5.1f%%　%.0f／%.0f MB" % (pct, done / 1e6, total / 1e6))
            sys.stdout.flush()

    try:
        urllib.request.urlretrieve(url, tmp, hook)
    except Exception as e:
        if os.path.exists(tmp):
            os.remove(tmp)
        lib.die("模型下載失敗：%s" % e,
                "檢查網路；也可以自己用瀏覽器開 %s 下載，存到 %s。" % (url, dest))
    sys.stdout.write("\n")
    os.replace(tmp, dest)
    lib.ok("模型就緒：%s" % dest)


def ensure_model(name, url):
    path = os.path.join(MODEL_DIR, name + ".bin")
    if not os.path.exists(path):
        download(url, path)
    return path


def transcribe_one(src, model, vad, lang, out_dir, done_dir, keep, tools=None):
    ffmpeg, ffprobe, whisper = tools or ("ffmpeg", "ffprobe", "whisper-cli")
    base = os.path.splitext(os.path.basename(src))[0]
    out_md = os.path.join(out_dir, base + ".md")
    if os.path.exists(out_md):
        lib.warn("已經有逐字稿了，跳過：%s" % os.path.relpath(out_md, lib.root()))
        return out_md
    # 暫存 wav 與 `-of` 前綴都放 hostos.work_dir()，不用 %TEMP%：
    # Windows 版 whisper-cli.exe 吃窄字元 argv，使用者名稱是中文時 %TEMP% 的路徑它開不了，
    # 而且錯誤訊息看起來像「這個錄音壞了」。work_dir() 保證是 ASCII 路徑。
    work = hostos.work_dir()
    warn = hostos.work_dir_warning()
    if warn:
        lib.warn(warn)
    tmp = tempfile.mkdtemp(prefix="trk-transcribe-", dir=work)
    try:
        wav = os.path.join(tmp, "audio.wav")
        print("── %s ──" % os.path.basename(src))
        print("① 轉成 16kHz 單聲道 wav…")
        # 一律走 hostos.run：它有逾時、輸出解碼不會炸、Windows 的 .cmd 特殊字元有閘。
        rc, out = hostos.run([ffmpeg, "-y", "-i", src, "-ac", "1", "-ar", "16000",
                              "-c:a", "pcm_s16le", wav], timeout=FFMPEG_TIMEOUT)
        if rc != 0 or not os.path.exists(wav):
            lib.err("ffmpeg 轉檔失敗：%s" % os.path.basename(src),
                    ("轉檔超過 %d 秒還沒好，已經中止。" % FFMPEG_TIMEOUT) if rc == 124 else
                    "這個檔可能不是音訊或已經損壞。最後幾行訊息：%s"
                    % " ".join((out or "").strip().splitlines()[-2:]))
            return None
        dur = 0.0
        rc, out = hostos.run([ffprobe, "-v", "error", "-show_entries", "format=duration",
                              "-of", "default=noprint_wrappers=1:nokey=1", wav],
                             timeout=FFPROBE_TIMEOUT)
        try:
            dur = float((out or "").strip().splitlines()[0]) if rc == 0 and out.strip() else 0.0
        except (ValueError, IndexError):
            dur = 0.0
        print("② 轉錄中（%s，長度 %s，這一步最花時間）…" % (os.path.basename(model), hms(dur)))
        prefix = os.path.join(tmp, "out")
        cmd = [whisper, "-m", model, "-l", lang, "--prompt", PRIMER,
               "-f", wav, "-oj", "-of", prefix, "-np", "-pp"]
        if vad:
            cmd += ["--vad", "--vad-model", vad]
        rc, out = hostos.run(cmd, timeout=WHISPER_TIMEOUT)
        jpath = prefix + ".json"
        if rc != 0 or not os.path.exists(jpath):
            lib.err("whisper-cli 轉錄失敗：%s" % os.path.basename(src),
                    ("轉錄超過 %d 秒還沒好，已經中止（錄音太長或機器太慢；"
                     "可以改用小一點的模型 --model ggml-medium）。" % WHISPER_TIMEOUT) if rc == 124 else
                    "訊息：%s" % " ".join((out or "").strip().splitlines()[-2:]))
            return None
        with open(jpath, encoding="utf-8", errors="replace") as f:
            data = json.load(f)
        lines = []
        for seg in data.get("transcription", []):
            text = (seg.get("text") or "").strip()
            if not text:
                continue
            t = (seg.get("offsets", {}) or {}).get("from", 0) / 1000.0
            lines.append("[%s] %s" % (hms(t), text))
        os.makedirs(out_dir, exist_ok=True)
        with open(out_md, "w", encoding="utf-8", newline="\n") as f:
            f.write("# 逐字稿：%s\n\n" % base)
            f.write("- 來源檔：%s\n" % os.path.basename(src))
            f.write("- 長度：%s\n" % hms(dur))
            f.write("- 轉錄完成：%s\n" % lib.now_iso())
            f.write("- 引擎：whisper.cpp %s（本機，錄音沒有離開這台電腦）\n" % os.path.basename(model))
            f.write("- ⚠️ 機器轉錄、沒有人工校對；沒有語者標註；多人重疊或台語段落可能失準。\n\n")
            f.write("\n".join(lines) + "\n")
        lib.ok("逐字稿：%s（%d 段）" % (os.path.relpath(out_md, lib.root()), len(lines)))
        if not keep:
            os.makedirs(done_dir, exist_ok=True)
            dest = os.path.join(done_dir, os.path.basename(src))
            if os.path.exists(dest):
                dest = os.path.join(done_dir, "%s-%s%s" % (base, lib.now_iso().replace(":", ""),
                                                           os.path.splitext(src)[1]))
            shutil.move(src, dest)
            print("  原始錄音移到 %s" % os.path.relpath(dest, lib.root()))
        return out_md
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    ap = argparse.ArgumentParser(
        description="錄音檔 → 本機逐字稿（whisper.cpp；錄音與逐字稿都不出這台電腦）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="轉完把逐字稿交給 AI 代理改寫，再用 scripts/append_record.py 寫入。")
    ap.add_argument("files", nargs="*", metavar="錄音檔", help="要轉的檔（可以給多個）")
    ap.add_argument("--inbox", action="store_true", help="轉 inbox/ 裡所有還沒轉過的錄音")
    ap.add_argument("--lang", default="", help="語言（預設看 config 的 voice.lang，通常是 zh）")
    ap.add_argument("--model", default="", help="模型名（預設 ggml-large-v3-turbo）")
    ap.add_argument("--keep", action="store_true", help="轉完不要把原始錄音搬到 inbox/done/")
    ap.add_argument("--no-vad", action="store_true", help="不用語音活動偵測（VAD 模型下載不到時）")
    lib.add_root_arg(ap)
    a = ap.parse_args()
    lib.apply_root(a)

    kit = lib.load_kit(required=False)
    voice = kit.get("voice") or {}
    lang = a.lang or voice.get("lang") or "zh"
    model_name = a.model or voice.get("model") or hostos.WHISPER_MODEL_DEFAULT

    inbox = lib.rpath("inbox")
    out_dir = os.path.join(inbox, "transcripts")
    done_dir = os.path.join(inbox, "done")

    srcs = list(a.files)
    if a.inbox:
        if not os.path.isdir(inbox):
            lib.die("找不到 inbox/ 資料夾：%s" % inbox, "跑 `python3 scripts/setup.py` 建骨架，或自己建一個。")
        srcs += sorted(os.path.join(inbox, f) for f in os.listdir(inbox)
                       if f.lower().endswith(AUDIO_EXT) and not f.startswith("."))
    if not srcs:
        if a.inbox:
            print("inbox/ 裡沒有還沒轉的錄音檔。把錄音拖進 %s 再跑一次。" % os.path.relpath(inbox, lib.root()))
            return
        lib.die("沒有指定要轉哪個檔。",
                "用 `python3 scripts/transcribe.py --inbox` 轉 inbox/ 裡的全部，或直接給檔名。")
    missing = [s for s in srcs if not os.path.exists(s)]
    if missing:
        lib.die("找不到這些檔：%s" % "、".join(missing), "確認路徑有沒有打錯（檔名有空白要加引號）。")

    ffmpeg, ffprobe, whisper = need("ffmpeg"), need("ffprobe"), need("whisper-cli")
    model = ensure_model(model_name, MODEL_URL % model_name)
    vad = None
    if not a.no_vad:
        try:
            vad = ensure_model(VAD_NAME, VAD_URL)
        except SystemExit:
            lib.warn("VAD 模型拿不到，改用無 VAD 模式繼續（品質差一點，不影響能不能用）。")
            vad = None

    made = []
    for s in srcs:
        r = transcribe_one(s, model, vad, lang, out_dir, done_dir, a.keep, (ffmpeg, ffprobe, whisper))
        if r:
            made.append(r)

    if not made:
        lib.die("一份逐字稿都沒產生出來。", "看上面每一個 ✗ 的訊息。")
    print("\n%s完成 %d 份逐字稿。%s接下來請你的 AI 代理做這件事：" % (lib.GREEN, len(made), lib.RESET))
    print("  1. 讀逐字稿：%s" % "、".join(os.path.relpath(m, lib.root()) for m in made))
    print("  2. 判斷這是哪一種記錄（學生／班級／課程／業務），把口語整理成書面、學生一律寫代號")
    print("  3. 存成草稿檔，然後用唯一寫入通道寫進去：")
    print("       python3 scripts/append_record.py --kind <students|class|courses|business> \\")
    print("           --target <代號> --tags \"#標籤\" --content-file <草稿檔> --source voice --sync")
    print("  （逐字稿留在 inbox/transcripts/，它跟錄音一樣不會進 git、不會上傳到任何地方。）")


if __name__ == "__main__":
    main()
