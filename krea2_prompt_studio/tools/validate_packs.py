#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""장소 팩 검수: python tools/validate_packs.py [팩이름.json ...]   (기준: docs/장소팩_작성기준.md)"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
PACK_DIR = ROOT / "krea2_prompt_configs" / "scene_packs"

PLACEHOLDERS = {"s", "S", "p", "P", "o", "color", "lit"}
RESULT_WORDS = re.compile(r"\b(highlights?|sheen|gloss\w*|rim light|rim-lit|catches? the light|deepens?|glow(?:s|ing)? on)\b", re.I)
OUTFIT_WORDS = re.compile(r"\b(bikini|swimsuit|dress|skirt|shirt|blouse|jacket|cardigan|jeans|shorts|sweater|coat|underwear|lingerie)\b", re.I)
OUTDOOR_ONLY = re.compile(r"\b(sun|sunset|moon\w*|stars?|rain\w*|snow\w*|fog\w*|horizon)\b", re.I)
FEET = re.compile(r"\b(feet|foot|ankles?|barefoot|toes|shoes|sneakers)\b", re.I)
REQUIRED = ("schema", "location_ko", "outdoor", "setting_en", "feature_en", "ground_en", "far_en", "times", "moments",
            "camera", "style_en", "detail_en", "position_en")
TIME_REQUIRED = ("time_en", "sky_en", "light_en", "shadow_en", "desc_ko")


def texts(node, path="", english=False):
    """(path, string) for every English string in the pack (*_en keys, their lists, and the camera texts)."""
    if isinstance(node, dict):
        for key, v in node.items():
            yield from texts(v, f"{path}/{key}", key.endswith("_en") or path.endswith("camera") or key == "camera")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from texts(v, f"{path}[{i}]", english)
    elif isinstance(node, str) and english:
        yield path, node


def check(path: Path):
    errs, warns = [], []
    d = json.loads(path.read_text(encoding="utf-8"))
    for key in REQUIRED:
        if key not in d:
            errs.append(f"필수 칸 없음: {key}")
    if errs:
        return errs, warns
    if d["schema"] != "krea2-scene-pack/2":
        errs.append(f"schema가 krea2-scene-pack/2가 아님: {d['schema']}")
    for key in ("feature_en", "ground_en", "far_en"):
        if len(d[key]) < 2:
            errs.append(f"{key}는 2개 이상 (상세 모드와 시간대별 교체용)")
    import krea2_prompt_studio as k
    for fr in d["camera"]:
        if fr not in k.CAMERA_FRAMING:
            errs.append(f"본체에 없는 프레이밍 이름: {fr}")
    if len(d["camera"]) < 2:
        errs.append("camera는 프레이밍 2개 이상")
    for tk, tm in d["times"].items():
        for key in TIME_REQUIRED:
            if not tm.get(key):
                errs.append(f"시간대 '{tk}': {key} 없음")
        if tk not in d["detail_en"] or len(d["detail_en"][tk]) < 3:
            errs.append(f"시간대 '{tk}': detail_en 3줄 이상 필요")
        if not d["outdoor"]:
            for key in ("sky_en", "light_en", "shadow_en"):
                if OUTDOOR_ONLY.search(tm.get(key, "")):
                    errs.append(f"실내 팩 '{tk}'/{key}: 야외 전용 단어 ({OUTDOOR_ONLY.search(tm[key]).group(0)})")
        if tm.get("light_en") and not re.search(r"\b(left|right|behind|above|front|beside|overhead)\b", tm["light_en"]):
            errs.append(f"시간대 '{tk}': light_en에 광원 위치가 없음")
        if "left" in tm.get("light_en", "") and "right" not in tm.get("shadow_en", "") and "behind" not in tm.get("shadow_en", "") and "gather" not in tm.get("shadow_en", "") and "pool" not in tm.get("shadow_en", ""):
            warns.append(f"시간대 '{tk}': 광원이 왼쪽인데 그림자 방향이 오른쪽/뒤로 안 읽힘")
    for mk, mo in d["moments"].items():
        for key in ("pose_en", "moment_en", "desc_ko"):
            if not mo.get(key):
                errs.append(f"순간 '{mk}': {key} 없음")
        frames = mo.get("frames", list(d["camera"]))
        if any(f not in d["camera"] for f in frames):
            errs.append(f"순간 '{mk}': frames에 camera에 없는 이름")
        if FEET.search(mo.get("pose_en", "") + " " + mo.get("moment_en", "")) and any(f != "전신" for f in frames):
            errs.append(f"순간 '{mk}': 발/발목을 쓰는데 전신 외 프레이밍에도 허용됨 (frames를 전신으로 제한)")
    if d.get("ground_contact_en") and "전신" not in d["camera"]:
        errs.append("ground_contact_en은 전신 프레이밍이 있을 때만 (발은 전신에서만 보임)")
    for where, text in texts(d):
        if re.search(r"[가-힣]", text):
            errs.append(f"영어 칸에 한글: {where}")
        for name in re.findall(r"\{(\w*)\}", text):
            if name not in PLACEHOLDERS:
                errs.append(f"모르는 자리표시자 {{{name}}}: {where}")
        if RESULT_WORDS.search(text):
            errs.append(f"빛의 결과 서술 단어 ({RESULT_WORDS.search(text).group(0)}): {where}")
        if OUTFIT_WORDS.search(text) and "lit_en" not in where:
            errs.append(f"장소 팩에 의상 단어 ({OUTFIT_WORDS.search(text).group(0)}): {where} → {{lit}} 사용")
        if re.search(r"\b(no|without|not)\b", text, re.I):
            warns.append(f"부정 표현 (안 먹음): {where}")
    return errs, warns


def main() -> int:
    names = sys.argv[1:] or [p.name for p in sorted(PACK_DIR.glob("*.json"))]
    bad = 0
    for name in names:
        errs, warns = check(PACK_DIR / name)
        print(f"{'FAIL' if errs else 'ok  '} {name}")
        for e in errs:
            print("   ✗", e)
        for w in warns:
            print("   △", w)
        bad += bool(errs)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
