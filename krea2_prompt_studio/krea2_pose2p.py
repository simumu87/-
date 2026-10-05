#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""2-person pose library: each person's body is written part by part, and both sides agree on the contact.

A stands on the left of the frame and B on the right (the regional node's split). Limbs are named by their
distance to the partner ("the arm closest to him"), never left/right, so nothing depends on whose side is meant.
"""
import json
from typing import Any, Dict, List, Optional

import krea2_prompt_studio as k

POSE_FILE = k.CONFIG_DIR / "poses_2p.json"
PARTS = ("body", "arms", "legs", "head")


def load_poses() -> Dict[str, Any]:
    return json.loads(POSE_FILE.read_text(encoding="utf-8"))["items"]


def _fill(text: str, me: Dict[str, str], partner: Dict[str, str]) -> str:
    return text.format_map({"s": me["s"], "S": me["S"], "p": me["p"], "P": me["P"], "o": me["o"],
                            "pp": partner["p"], "po": partner["o"]})


def person_text(pose: Dict[str, Any], side: str, me: Dict[str, str], partner: Dict[str, str], legs_visible: bool) -> str:
    """One person's pose as one sentence body ("stands with ..., her arm ..., her head ...")."""
    parts = pose[side]
    chunks = [_fill(parts[name], me, partner) for name in PARTS if name in parts and (name != "legs" or legs_visible)]
    return ", ".join(chunks)


def fits(interaction: str, framing: str) -> bool:
    pose = load_poses().get(interaction)
    return bool(pose) and framing in pose["frames_ok"]


def validate() -> List[str]:
    """Both sides must mention every contact; no left/right words; fields complete; Korean description present."""
    import re
    problems = []
    for key, pose in load_poses().items():
        if not pose.get("desc_ko"):
            problems.append(f"{key}: no Korean description")
        if pose.get("distance") == "contact" and pose.get("stance") not in ("standing", "sitting"):
            problems.append(f"{key}: stance missing")
        for side in ("a", "b"):
            for name in PARTS:
                if name not in pose[side]:
                    problems.append(f"{key}/{side}: part '{name}' missing")
            text = " ".join(pose[side].values())
            if re.search(r"\b(left|right)\b", text):
                problems.append(f"{key}/{side}: left/right wording (use 'closest to {{po}}')")
            if re.search(r"[가-힣]", text):
                problems.append(f"{key}/{side}: Hangul in English text")
            for word in pose.get("contacts", []):
                if word not in text:
                    problems.append(f"{key}/{side}: contact '{word}' not written on this side")
        if pose.get("distance") == "contact" and not pose.get("contacts"):
            problems.append(f"{key}: contact distance without a contact list")
        if pose.get("distance") != "contact" and pose.get("contacts"):
            problems.append(f"{key}: contacts listed for a non-contact distance")
        if not pose.get("shared_en"):
            problems.append(f"{key}: shared_en missing")
    return problems


if __name__ == "__main__":
    import sys
    bad = validate()
    for line in bad:
        print("FAIL", line)
    print(f"{len(load_poses())} poses, {len(bad)} problems")
    sys.exit(1 if bad else 0)
