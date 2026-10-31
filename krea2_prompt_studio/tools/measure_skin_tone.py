"""Measure the skin tone of images: median colour of the skin-coloured pixels.

usage: python tools/measure_skin_tone.py image1.png image2.png ...

Skin pixels = hue 8-32 degrees, saturation 15-50 %, brightness 62-97 %, and red > green > blue.
That drops hair, glasses, bikini, the grey backdrop and blown highlights. The same rule was used for the
hangyeol training set (2026-10-23), so numbers from new images can be compared with `한결_피부톤_몸_정의_1023.md`.
Prints RGB, hex, HSV (hue deg / saturation % / brightness %) and the share of pixels counted as skin.
"""
import colorsys
import sys

import numpy as np
from PIL import Image


def skin_median(path):
    a = np.array(Image.open(path).convert("RGB")).astype(float) / 255
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    mx, mn = a.max(-1), a.min(-1)
    d = mx - mn + 1e-9
    s = d / (mx + 1e-9)
    h = np.where(mx == r, ((g - b) / d) % 6, np.where(mx == g, (b - r) / d + 2, (r - g) / d + 4)) * 60
    mask = (h > 8) & (h < 32) & (s > 0.15) & (s < 0.5) & (mx > 0.62) & (mx < 0.97) & (r > g) & (g > b)
    px = a[mask] * 255
    if len(px) == 0:
        return None
    med = np.median(px, axis=0).astype(int)
    hh, ss, vv = colorsys.rgb_to_hsv(*(med / 255))
    return tuple(int(x) for x in med), (round(hh * 360), round(ss * 100), round(vv * 100)), mask.mean()


def main(paths):
    if not paths:
        print(__doc__)
        return 1
    for p in paths:
        res = skin_median(p)
        if not res:
            print(f"{p}: no skin-coloured pixels found")
            continue
        rgb, hsv, share = res
        print(f"{p}: RGB {rgb}  #{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}  H{hsv[0]} S{hsv[1]} V{hsv[2]}  skin {share:.0%}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
