#!/usr/bin/env python3
"""依 script.json 產生語音 (edge-tts)、manifest.js 與完整旁白音軌 narration.wav。

用法：python3 tools/build_tts.py [--force]
需求：pip install edge-tts；系統需有 ffmpeg。
"""
import asyncio, hashlib, json, os, ssl, subprocess, sys, wave
from pathlib import Path

import edge_tts
import edge_tts.communicate as _comm

ROOT = Path(__file__).resolve().parent.parent
AUDIO = ROOT / "audio"
WORK = ROOT / "tools" / ".work"
RATE = 24000
LEAD, GAP, TAIL = 0.8, 0.45, 1.4   # 每頁開頭留白、句間停頓、每頁結尾留白（秒）

# 經由公司代理/自簽 CA 時使用指定的 CA bundle
_ca = os.environ.get("SSL_CERT_FILE") or ("/root/.ccr/ca-bundle.crt" if os.path.exists("/root/.ccr/ca-bundle.crt") else None)
if _ca:
    _comm._SSL_CTX = ssl.create_default_context(cafile=_ca)
PROXY = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")


async def tts(text, v, out):
    for attempt in range(4):
        try:
            await edge_tts.Communicate(text, v["voice"], rate=v["rate"], pitch=v["pitch"], proxy=PROXY).save(str(out))
            return
        except Exception as e:  # 網路偶發錯誤重試
            print("  retry", attempt + 1, e)
            await asyncio.sleep(2 ** attempt)
    raise RuntimeError(f"TTS failed: {text}")


def to_wav(mp3, wav):
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(mp3), "-ac", "1", "-ar", str(RATE), "-sample_fmt", "s16", str(wav)], check=True)
    with wave.open(str(wav)) as w:
        return w.readframes(w.getnframes())


async def main(force=False):
    data = json.loads((ROOT / "script.json").read_text("utf-8"))
    AUDIO.mkdir(exist_ok=True); WORK.mkdir(parents=True, exist_ok=True)
    voices = data["voices"]
    jobs = []
    for s in data["slides"]:
        for i, (spk, text) in enumerate(s["lines"]):
            v = voices[spk]
            key = hashlib.md5(json.dumps([text, v], ensure_ascii=False).encode()).hexdigest()[:8]
            mp3 = AUDIO / f"{s['id']}_{i:02d}.mp3"
            stamp = WORK / f"{mp3.stem}.key"
            if force or not mp3.exists() or not stamp.exists() or stamp.read_text() != key:
                jobs.append((text, v, mp3, stamp, key))
    print(f"TTS jobs: {len(jobs)}")
    sem = asyncio.Semaphore(6)
    async def run(job):
        text, v, mp3, stamp, key = job
        async with sem:
            await tts(text, v, mp3)
            stamp.write_text(key)
            print("  ok", mp3.name)
    await asyncio.gather(*(run(j) for j in jobs))

    # 量測長度、組合完整音軌
    track = bytearray()
    def silence(sec):
        track.extend(b"\x00\x00" * int(round(sec * RATE)))
    manifest = {"title": data["title"], "lead": LEAD, "gap": GAP, "tail": TAIL,
                "speakers": {k: v["name"] for k, v in voices.items()}, "slides": []}
    for s in data["slides"]:
        ms = {"id": s["id"], "lines": []}
        silence(LEAD)
        for i, (spk, text) in enumerate(s["lines"]):
            mp3 = AUDIO / f"{s['id']}_{i:02d}.mp3"
            pcm = to_wav(mp3, WORK / f"{mp3.stem}.wav")
            dur = len(pcm) / 2 / RATE
            track.extend(pcm)
            if i < len(s["lines"]) - 1:
                silence(GAP)
            ms["lines"].append({"s": spk, "t": text, "f": f"audio/{mp3.name}", "d": round(dur, 3)})
        silence(TAIL)
        manifest["slides"].append(ms)
    with wave.open(str(WORK / "narration.wav"), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(RATE); w.writeframes(bytes(track))
    total = len(track) / 2 / RATE
    manifest["total"] = round(total, 3)
    (ROOT / "manifest.js").write_text("window.MANIFEST = " + json.dumps(manifest, ensure_ascii=False, indent=1) + ";\n", "utf-8")
    print(f"total {total/60:.1f} min -> manifest.js, tools/.work/narration.wav")


if __name__ == "__main__":
    asyncio.run(main("--force" in sys.argv))
