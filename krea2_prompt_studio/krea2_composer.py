#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Krea2 prompt composer (v11 prototype) - single-paragraph prose, no labels, no meta instructions.

Layers (each owns one thing, nothing is described twice):
    LoRA identity   -> face / body / hair only          (loras.json: identity)
    signature       -> accessories that always stay      (loras.json: signature_accessories)
    outfit          -> clothing                          (outfits/lora/*.json or the common pool)
    scene           -> pose, place, light, camera        (krea2_prompt_studio scene engine)

Usage:
    python krea2_composer.py --demo
    python krea2_composer.py --trigger nayoon --outfit gold_amber_triangle_string_bikini --seed 11
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import krea2_prompt_studio as k

OUTFIT_DIR = k.CONFIG_DIR / "outfits" / "lora"
LIST_DIR = k.CONFIG_DIR / "outfits" / "lists"
PRONOUNS = {"female": ("she", "her"), "male": ("he", "his")}


# ---------------------------------------------------------------------------
# loading
# ---------------------------------------------------------------------------
def load_outfit(outfit_id: str) -> Dict[str, Any]:
    path = OUTFIT_DIR / f"{outfit_id}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def outfits_for_trigger(trigger: str) -> List[str]:
    """Outfit ids listed for a LoRA trigger (lora outfits only; the common pool lives in the main program)."""
    for path in sorted(LIST_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("trigger") == trigger:
            return list(data.get("lora_outfits", []))
    return []


# ---------------------------------------------------------------------------
# text helpers
# ---------------------------------------------------------------------------
LABEL = re.compile(r"(?:(?<=[.!?])|^)\s*(?:Hairstyle|Hair|Face|Eyes|Body|Build|Skin|Appearance)\s*:\s*", re.I)


HAIR_LABEL = re.compile(r"[.!?]\s*(?:Hairstyle|Hair)\s*:\s*", re.I)


def identity_to_prose(text: str, trigger: str = "", subj: str = "she") -> str:
    """Turn a stored identity into plain prose: no 'She is', no 'Hairstyle:' labels, sentences spaced."""
    value = re.sub(r"([.!?])(?=[A-Za-z])", r"\1 ", k.clean_text(text))   # "waist.Hairstyle" -> "waist. Hairstyle"
    value = HAIR_LABEL.sub(f", and {subj} has ", value)                  # "... waist. Hairstyle: X" -> "... waist, and she has X"
    value = LABEL.sub(" ", value)
    value = re.sub(r"([.!?])\s+([a-z])", lambda m: m.group(1) + " " + m.group(2).upper(), value)
    if trigger:
        value = re.sub(r"^(?:she|he|they)\s+is\s+", "", value, flags=re.I)
    value = re.sub(r"\s{2,}", " ", value).strip()
    return value[0].lower() + value[1:] if value else value


def sentence(text: str) -> str:
    text = k.clean_text(text)
    if text and text[-1] not in ".!?":
        text += "."
    return text[:1].upper() + text[1:] if text else text


def lock_en(outfit: Dict[str, Any], lock_id: str, variant: int = 0) -> str:
    for lock in outfit.get("locks", []):
        if lock["id"] == lock_id:
            variants = lock["en"]
            return variants[variant % len(variants)]
    return ""


# ---------------------------------------------------------------------------
# outfit -> prose (normal mode)
# ---------------------------------------------------------------------------
def outfit_normal(outfit: Dict[str, Any], subj: str) -> str:
    parts, color, mat = outfit["parts"], outfit["color"], outfit["material"]
    ring = lock_en(outfit, "center_ring")
    straps = lock_en(outfit, "thin_straps")
    top = parts["top"]["en"]
    if ring:
        top += f" with {ring}"
    if straps:
        top += f" and {straps}"
    return (f"{subj.capitalize()} wears {top}, and {parts['bottom']['en']}, all in {color['primary']['en']} "
            f"{mat['en']} with {mat['finish_en']}")


# ---------------------------------------------------------------------------
# scene -> prose (normal mode)
# ---------------------------------------------------------------------------
def scene_normal(scene: "k.SceneProfile", person: "k.PersonSlot", subj: str, poss: str) -> List[str]:
    env, light, cam = scene.environment, scene.lighting, scene.camera
    out: List[str] = []
    out.append(sentence(f"{subj.capitalize()} is {person.pose_en} {env.sublocation}, with a {person.expression} "
                        f"and {person.gaze}"))
    deco = [x for x in env.decor if x][:2]
    place = f"{env.location_en}, {env.floor}"
    if deco:
        place += ", with " + " and ".join(deco)
    if env.walls:
        place += f", and {env.walls}"
    out.append(sentence(f"The setting is {place}"))
    out.append(sentence(f"It is {scene.time_en} with {scene.weather_en}, lit by {light.source} {light.direction}, "
                        f"{light.quality}, with {light.shadow}"))
    out.append(sentence(f"{cam.framing}, {cam.lens}mm, {cam.viewpoint}, {cam.composition}, {cam.depth_of_field}"))
    out.append(sentence(k._style_line(scene)))
    return out


# ---------------------------------------------------------------------------
# compose
# ---------------------------------------------------------------------------
def compose_normal(scene: "k.SceneProfile", person: "k.PersonSlot", lora: Dict[str, Any],
                   outfit: Optional[Dict[str, Any]], hair_override: str = "") -> str:
    subj, poss = PRONOUNS.get(lora.get("gender", "female"), ("they", "their"))
    identity = identity_to_prose(lora.get("identity", ""), lora.get("trigger", ""), subj)
    chunks = [f"{lora['trigger']}, {identity}".rstrip(".") + "."]      # trigger stays exactly as registered
    hair = k.clean_text(hair_override) or k.clean_text(lora.get("hair", ""))   # override replaces the LoRA hair entirely
    if hair:
        chunks.append(sentence(f"{subj} has {hair}"))
    for acc in lora.get("signature_accessories", []):
        chunks.append(sentence(f"{acc} rests around {poss} neck" if "choker" in acc else f"{acc}"))
    if outfit:
        chunks.append(sentence(outfit_normal(outfit, subj)))
    chunks.extend(scene_normal(scene, person, subj, poss))
    text = " ".join(chunks)
    text = re.sub(r"\s+([,.])", r"\1", text)
    return re.sub(r"\s{2,}", " ", text).strip()


def lint(text: str) -> List[str]:
    problems = []
    if re.search(r"[가-힣]", text):
        problems.append("Hangul in prompt")
    if re.search(r"\b(?:Hairstyle|Expression|Gaze|Walls|Floor|Lighting|Camera|Appearance)\s*:", text):
        problems.append("field label in prompt")
    if re.search(r"scale lock|Keep all|Maintain coherent", text, re.I):
        problems.append("meta instruction in prompt")
    if re.search(r"[,.;:]{2,}", text):
        problems.append("repeated punctuation")
    return problems


def build_sample(trigger: str, outfit_id: str, seed: int, location: str = "해변", activity: str = "해변 산책",
                 time_key: str = "해질녘", weather: str = "맑음", pose: str = "천천히 걷기",
                 expression: str = "gentle natural smile", light: str = "골든아워",
                 framing: str = "전신", style: str = "여행 화보") -> Dict[str, Any]:
    lora = k.lora_profile_for_trigger(trigger)
    if not lora:
        raise SystemExit(f"LoRA trigger not registered: {trigger}")
    outfit = load_outfit(outfit_id) if outfit_id else None
    c = k.defaults()
    for key, value in {"people": "1", "location": location, "activity": activity, "time": time_key,
                       "weather": weather, "pose": pose, "expression_A": expression, "light_source": light,
                       "framing": framing, "style": style}.items():
        k.set_constraint_value(c, key, value)
    scene = k.build_scene(seed, c, None, None, "", False)
    import random
    person = k.resolve_person(random.Random(seed + 17), scene, "A", k.PersonSlot(slot="PERSON_A", lora_trigger=trigger))
    text = compose_normal(scene, person, lora, outfit)
    return {"prompt": text, "problems": lint(text), "words": len(text.split()), "seed": seed}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--trigger", default="nayoon")
    ap.add_argument("--outfit", default="gold_amber_triangle_string_bikini")
    ap.add_argument("--seed", type=int, default=11)
    args = ap.parse_args()
    result = build_sample(args.trigger, args.outfit, args.seed)
    print(result["prompt"])
    print(f"\n[{result['words']} words, seed {result['seed']}, problems: {result['problems'] or 'none'}]")
    return 1 if result["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
