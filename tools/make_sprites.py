#!/usr/bin/env python3
"""從人物設定圖裁出去背的角色圖（assets/char/*.png）。

用法：python3 tools/make_sprites.py
來源：assets/ref/allan_sheet.jpg、assets/ref/arale_sheet.jpg（2000x1493）
"""
import json
from pathlib import Path
import numpy as np
from PIL import Image, ImageFilter
from scipy import ndimage

ROOT = Path(__file__).resolve().parent.parent
REF, OUT = ROOT / "assets" / "ref", ROOT / "assets" / "char"

# (名稱, (top, left, bottom, right), 內縮像素)  — 座標來自設定圖的格線
ALLAN = [
    ("allan_full", (80, 80, 1465, 772), 0),
    ("allan_smile", (790, 764, 1126, 1024), 0), ("allan_laugh", (790, 1073, 1125, 1333), 0),
    ("allan_think", (790, 1379, 1126, 1645), 0), ("allan_confused", (790, 1635, 1123, 1970), 0),
    ("allan_surprised", (1133, 764, 1470, 1024), 0), ("allan_point", (1133, 1042, 1469, 1334), 0),
    ("allan_wink", (1134, 1383, 1471, 1643), 0), ("allan_talk", (1134, 1703, 1471, 1959), 0),
]
ARALE = [("arale_full", (70, 95, 768, 420), 0)]
names = ["happy", "laugh", "think", "surprised", "confused", "oh", "present", "sad", "thumbs", "fist"]
cols = [(46, 417), (431, 803), (817, 1189), (1204, 1575), (1588, 1960)]
for r, (t, b) in enumerate([(800, 1121), (1137, 1457)]):
    for c, (l, rr) in enumerate(cols):
        ARALE.append((f"arale_{names[r * 5 + c]}", (t, l, b, rr), 9))   # 內縮去掉格框


def cutout(img, box, inset):
    t, l, b, r = box
    a = np.asarray(img.crop((l + inset, t + inset, r - inset, b - inset)).convert("RGB")).astype(int)
    # 去掉設定圖上的淺灰水平參考線
    grey = (a.min(axis=2) > 170) & (a.max(axis=2) - a.min(axis=2) < 14) & (a.min(axis=2) < 236)
    rows = np.where(grey.mean(axis=1) > 0.5)[0]
    for y in rows:
        a[max(0, y - 2):y + 3][grey[max(0, y - 2):y + 3]] = 255
    light = a.min(axis=2) > 232
    lab, _ = ndimage.label(light)
    edge = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])))
    edge.discard(0)
    bg = np.isin(lab, list(edge))
    alpha = np.where(bg, 0, 255).astype(np.uint8)
    # 只保留主體（與夠大的附屬物件，如阿拉蕾的問號），清掉相鄰格的殘渣
    olab, n = ndimage.label(alpha > 0)
    if n > 1:
        sizes = ndimage.sum(np.ones_like(olab), olab, range(1, n + 1))
        keep = [i + 1 for i, sz in enumerate(sizes) if sz >= 0.015 * sizes.max()]
        alpha[~np.isin(olab, keep)] = 0
    am = Image.fromarray(alpha).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))
    rgba = Image.fromarray(a.clip(0, 255).astype(np.uint8)).convert("RGBA")
    rgba.putalpha(am)
    return rgba.crop(rgba.getbbox())


OUT.mkdir(parents=True, exist_ok=True)
sizes = {}
for sheet, items in (("allan_sheet.jpg", ALLAN), ("arale_sheet.jpg", ARALE)):
    img = Image.open(REF / sheet)
    for name, box, inset in items:
        sp = cutout(img, box, inset)
        if "full" in name:
            sp.thumbnail((520, 900), Image.LANCZOS)
        sp.save(OUT / f"{name}.png", optimize=True)
        sizes[name] = sp.size
        print(name, sp.size)
(OUT / "sprites.js").write_text("window.SPRITES = " + json.dumps(sizes) + ";\n", "utf-8")
