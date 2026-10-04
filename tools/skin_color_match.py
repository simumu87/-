#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""피부톤 맞추기 — 기준 사진의 피부색에 다른 사진의 피부색만 맞춘다 (배경·머리·수영복은 안 건드림).

사용:  python tools/skin_color_match.py --ref 기준.webp --src 맞출사진.webp --out 결과.png [--strength 0.9]
폴더:  python tools/skin_color_match.py --ref 기준.webp --src-dir 사진폴더 --out-dir 결과폴더
필요:  pip install pillow numpy
방식:  피부 픽셀(YCbCr 범위)만 골라 LAB 색공간에서 평균(밝기 L, 색 a·b)을 기준 사진에 맞춘다. 마스크 가장자리는 부드럽게 섞는다.
"""
import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter


def srgb_to_lab(rgb):
    c = rgb / 255.0
    c = np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)
    m = np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]])
    xyz = c @ m.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    return np.stack([116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])], -1)


def lab_to_srgb(lab):
    fy = (lab[..., 0] + 16) / 116
    fx, fz = fy + lab[..., 1] / 500, fy - lab[..., 2] / 200
    f = np.stack([fx, fy, fz], -1)
    xyz = np.where(f ** 3 > 0.008856, f ** 3, (f - 16 / 116) / 7.787) * np.array([0.95047, 1.0, 1.08883])
    m_inv = np.linalg.inv(np.array([[0.4124564, 0.3575761, 0.1804375], [0.2126729, 0.7151522, 0.0721750], [0.0193339, 0.1191920, 0.9503041]]))
    c = np.clip(xyz @ m_inv.T, 0, 1)
    c = np.where(c <= 0.0031308, 12.92 * c, 1.055 * np.power(c, 1 / 2.4) - 0.055)
    return np.clip(c * 255, 0, 255)


def skin_mask(img):
    """YCbCr 피부 범위 + 너무 어둡거나 밝은 곳 제외. 부드러운 0~1 마스크."""
    ycc = np.asarray(img.convert("YCbCr"), dtype=np.float32)
    y, cb, cr = ycc[..., 0], ycc[..., 1], ycc[..., 2]
    m = (cb > 77) & (cb < 127) & (cr > 133) & (cr < 173) & (y > 60) & (y < 245)
    mask = Image.fromarray((m * 255).astype(np.uint8)).filter(ImageFilter.MedianFilter(5))
    mask = mask.filter(ImageFilter.GaussianBlur(6))
    return np.asarray(mask, dtype=np.float32) / 255.0


def match(ref_path, src_path, strength=1.0):
    ref, src = Image.open(ref_path).convert("RGB"), Image.open(src_path).convert("RGB")
    rm, sm = skin_mask(ref), skin_mask(src)
    if (rm > 0.5).sum() < 500 or (sm > 0.5).sum() < 500:
        raise SystemExit("피부 영역을 못 찾았어요 (사진이 너무 어둡거나 피부가 거의 안 보임)")
    rl, sl = srgb_to_lab(np.asarray(ref, dtype=np.float32)), srgb_to_lab(np.asarray(src, dtype=np.float32))
    rmean, smean = rl[rm > 0.5].mean(0), sl[sm > 0.5].mean(0)
    shift = (rmean - smean) * strength
    out = sl + shift * sm[..., None]
    result = Image.fromarray(lab_to_srgb(out).astype(np.uint8))
    return result, rmean, smean, rmean - smean


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ref", required=True)
    ap.add_argument("--src")
    ap.add_argument("--out")
    ap.add_argument("--src-dir")
    ap.add_argument("--out-dir")
    ap.add_argument("--strength", type=float, default=1.0, help="0~1 (1=기준 평균에 완전히 맞춤)")
    a = ap.parse_args()
    jobs = []
    if a.src_dir:
        out_dir = Path(a.out_dir or "skin_matched")
        out_dir.mkdir(parents=True, exist_ok=True)
        jobs = [(p, out_dir / (p.stem + "_skin.png")) for p in sorted(Path(a.src_dir).iterdir()) if p.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}]
    elif a.src and a.out:
        jobs = [(Path(a.src), Path(a.out))]
    else:
        raise SystemExit("--src 와 --out, 또는 --src-dir 가 필요해요")
    for src, out in jobs:
        img, rmean, smean, delta = match(a.ref, src, a.strength)
        img.save(out)
        print(f"{src.name}: 피부 LAB 평균 {np.round(smean, 1)} → 기준 {np.round(rmean, 1)} (보정 ΔL={delta[0]:+.1f}, Δa={delta[1]:+.1f}, Δb={delta[2]:+.1f}) → {out}")


if __name__ == "__main__":
    main()
