#!/usr/bin/env python3
"""依 manifest.js 的章節，為 MP4 寫入章節標記（不重新編碼），並輸出 YouTube 章節時間碼。

用法：python3 tools/add_chapters.py [video.mp4]
"""
import json, subprocess, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
video = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "video" / "TVM_威脅與弱點管理.mp4"
src = (ROOT / "manifest.js").read_text("utf-8")
M = json.loads(src[src.index("{"):src.rindex("}") + 1])

# 與 index.html 相同的時間軸計算
t, start, dur = 0.0, {}, {}
for s in M["slides"]:
    d = M["lead"] + sum(l["d"] for l in s["lines"]) + M["gap"] * (len(s["lines"]) - 1) + M["tail"]
    start[s["id"]], dur[s["id"]] = t, d
    t += d
titles = {s["id"]: s.get("title", s["id"]) for s in M["slides"]}

meta = [";FFMETADATA1", f"title={M['title']}"]
for c in M["chapters"]:
    a, z = start[c["slides"][0]], start[c["slides"][-1]] + dur[c["slides"][-1]]
    meta += ["[CHAPTER]", "TIMEBASE=1/1000", f"START={int(a * 1000)}", f"END={int(z * 1000)}", f"title={c['title']}"]
work = ROOT / "tools" / ".work"; work.mkdir(parents=True, exist_ok=True)
(work / "chapters.txt").write_text("\n".join(meta) + "\n", "utf-8")
tmp = video.with_suffix(".tmp.mp4")
subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(video), "-i", str(work / "chapters.txt"),
                "-map", "0", "-map_metadata", "1", "-map_chapters", "1", "-c", "copy", "-movflags", "+faststart", str(tmp)], check=True)
tmp.replace(video)

fmt = lambda x: f"{int(x // 60)}:{int(x % 60):02d}"
lines = []
for c in M["chapters"]:
    lines.append(f"{fmt(start[c['slides'][0]])} {c['title']}")
    lines += [f"  {fmt(start[i])} {titles[i]}" for i in c["slides"]]
print("\n".join(lines))
