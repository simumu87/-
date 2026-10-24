#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""1-person pose library: the body is written part by part (body, arms, legs, feet, head), only what the frame shows.

Legs (knees, shins) are written from the 3/4 full-body framing downward (depth >= 5), feet only in full-body framings (depth >= 6).
A pose with a "gaze" part fixes where the person looks, so the engine's own gaze sentence is dropped.
"""
import json
import re
from typing import Any, Dict, List, Optional, Tuple

import krea2_prompt_studio as k

POSE_FILE = k.CONFIG_DIR / "poses_1p.json"
FRAMING_FILE = k.CONFIG_DIR / "framings.json"
ORDER = ("body", "arms", "legs", "feet", "head")


def load_poses() -> Dict[str, Any]:
    return json.loads(POSE_FILE.read_text(encoding="utf-8"))["items"]


def load_framings() -> Dict[str, Any]:
    return json.loads(FRAMING_FILE.read_text(encoding="utf-8"))["items"]


def person_text(pose_key: str, ref: Dict[str, str], depth: int) -> Tuple[str, str]:
    """(pose sentence body, gaze text or "") for one person at a framing depth."""
    parts = load_poses()[pose_key]["parts"]
    fill = lambda t: t.format_map({"p": ref["p"], "P": ref["P"], "o": ref["o"], "s": ref["s"], "S": ref["S"]})
    visible = {"body": True, "arms": True, "legs": depth >= 5, "feet": depth >= 6, "head": True}
    chunks = [fill(parts[name]) for name in ORDER if name in parts and visible[name]]
    return ", ".join(chunks), fill(parts["gaze"]) if parts.get("gaze") else ""


def extent_text(framing_key: str, who: str) -> str:
    item = load_framings().get(framing_key)
    return item["extent_en"].format(who=who) if item else ""


def validate() -> List[str]:
    problems = []
    poses = load_poses()
    single = [x for x in k.BASE_POSES if x not in k.PAIR_ONLY_POSES]
    for key in single:
        if key not in poses:
            problems.append(f"{key}: no library entry")
    for key, pose in poses.items():
        if key not in k.BASE_POSES:
            problems.append(f"{key}: not a BASE_POSES name")
        if not pose.get("desc_ko"):
            problems.append(f"{key}: no Korean description")
        for name in ("body", "arms", "head"):
            if name not in pose["parts"]:
                problems.append(f"{key}: part '{name}' missing")
        if k.BASE_POSES.get(key) and k.BASE_POSES[key]["legs"][0] not in ("pedaling",) and "legs" not in pose["parts"]:
            problems.append(f"{key}: part 'legs' missing")
        text = " ".join(pose["parts"].values())
        if re.search(r"\b(left|right)\b", text):
            problems.append(f"{key}: left/right wording")
        if re.search(r"[가-힣]", text):
            problems.append(f"{key}: Hangul in English text")
        if re.search(r"\bsmil|laugh|grin", text, re.I):
            problems.append(f"{key}: expression wording (the engine writes the expression)")
    for key, item in load_framings().items():
        if not item.get("desc_ko"):
            problems.append(f"framing {key}: no Korean description")
        if key not in k.CAMERA_FRAMING:
            problems.append(f"framing {key}: not a CAMERA_FRAMING name")
    for key in k.CAMERA_FRAMING:
        if key not in load_framings():
            problems.append(f"framing {key}: no extent text")
    return problems


if __name__ == "__main__":
    import sys
    bad = validate()
    for line in bad:
        print("FAIL", line)
    print(f"{len(load_poses())} poses, {len(load_framings())} framings, {len(bad)} problems")
    sys.exit(1 if bad else 0)
