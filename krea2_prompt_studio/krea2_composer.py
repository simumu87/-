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

import importlib

_main = sys.modules.get("__main__")
# started from the studio menu? reuse that module instead of loading a second copy
k = _main if hasattr(_main, "lora_profile_for_trigger") else importlib.import_module("krea2_prompt_studio")

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


# ---------------------------------------------------------------------------
# v11 split composer: person prompt + scene prompt (the user's own structure)
# ---------------------------------------------------------------------------
PACK_DIR = k.CONFIG_DIR / "scene_packs"


def _discover_packs() -> Dict[str, str]:
    """Every scene_packs/*.json is a location; the file's own location_ko is its menu name."""
    found = {}
    for path in sorted(PACK_DIR.glob("*.json")):
        try:
            found[json.loads(path.read_text(encoding="utf-8"))["location_ko"]] = path.name
        except (ValueError, KeyError, OSError):
            continue
    return found


PACK_FILES = _discover_packs()
MODES = ("보통", "상세")


def _load(path: Path) -> Dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_expressions() -> Dict[str, Any]:
    return _load(k.CONFIG_DIR / "expressions.json")["items"]


def load_hair_presets() -> Dict[str, Any]:
    return _load(k.CONFIG_DIR / "hair_presets.json")["items"]


def load_pack(location_ko: str) -> Dict[str, Any]:
    name = PACK_FILES.get(location_ko)
    if not name:
        raise SystemExit(f"장면 팩이 없는 장소예요: {location_ko} (있는 장소: {', '.join(PACK_FILES)})")
    return _load(PACK_DIR / name)


def _fill(text: str, subj: str, poss: str, obj: str = "", color: str = "", lit: str = "") -> str:
    """{s}/{S} subject, {p}/{P} possessive, {o} object (her / the woman), {color} hair color,
    {lit} the outfit part the light lands on (outfit "lit_en", or "her outfit")."""
    obj = obj or ("her" if poss == "her" else "him" if poss == "his" else "them")
    return text.format_map({"s": subj, "S": subj.capitalize(), "p": poss, "P": poss.capitalize(), "o": obj,
                            "color": color, "lit": lit or f"{poss} outfit"})


def _join(parts: List[str]) -> str:
    return parts[0] if len(parts) == 1 else ", ".join(parts[:-1]) + ", and " + parts[-1]


def compose_split(trigger: str, outfit_id: str = "", location: str = "해변", time_key: str = "해질녘",
                  moment: str = "파도 발목", framing: str = "전신", expression: str = "환한 미소",
                  hair: str = "", mode: str = "보통", reinforce: Optional[int] = None, seed: int = 0,
                  common_outfit: bool = False) -> Dict[str, Any]:
    """Build the person prompt, the scene prompt and the combined single prompt.

    hair: "" keeps the LoRA hair; a preset name or free text replaces it entirely.
    mode: how much the scene and outfit are described. 보통 (concise) / 상세 (outfit parts, more place detail).
    reinforce: how many times key facts (expression, hair override, outfit essentials) are restated in
        different words: 0 none / 1 once more / 2 twice more. None = automatic (보통 -> 0, 상세 -> 1).
    """
    import random
    if mode not in MODES:
        raise SystemExit(f"모드는 {' / '.join(MODES)} 중에서 골라주세요.")
    detailed = mode == "상세"
    level = (1 if detailed else 0) if reinforce is None else int(reinforce)
    if level not in (0, 1, 2):
        raise SystemExit("강화 횟수는 0, 1, 2 중에서 골라주세요.")
    # a LoRA person's expression is easily overridden by the LoRA's own habit: on automatic, always restate it once
    expr_level = max(level, 1) if reinforce is None else level
    rng = random.Random(seed)
    lora = k.lora_profile_for_trigger(trigger)
    if not lora:
        raise SystemExit(f"등록되지 않은 LoRA 트리거예요: {trigger}")
    subj, poss = PRONOUNS.get(lora.get("gender", "female"), ("they", "their"))
    color = lora.get("hair_color", "")
    outfit = load_outfit(outfit_id) if outfit_id else None
    pack = load_pack(location)
    tm, mo = pack["times"][time_key], pack["moments"][moment]
    if framing not in pack["camera"]:
        raise SystemExit(f"이 장소에 없는 프레이밍이에요: {framing} (있는 것: {', '.join(pack['camera'])})")
    if framing not in mo.get("frames", list(pack["camera"])):
        raise SystemExit(f"'{moment}' 순간은 이 프레이밍에서 보이지 않는 부분을 써요: {framing}")
    exp = load_expressions()[expression]
    lit = (outfit or {}).get("lit_en", "")
    f = lambda t: _fill(t, subj, poss, color=color, lit=lit)
    fs = lambda t: _fill(t, "the woman", "the woman's", "the woman", color, lit)   # scene prompt that stands alone (regional use)
    cap = lambda t: t[:1].upper() + t[1:]

    # ---------------- person prompt: identity(face/body) -> hair -> outfit -> action/expression -> skin
    person = [f"{lora['trigger']}, {identity_to_prose(lora.get('identity', ''), lora['trigger'], subj)}".rstrip(".") + "."]
    hair_echo = hair_echo2 = ""
    if hair:
        presets = load_hair_presets()
        person.append(f"Only {poss} face and body follow the {lora['trigger']} reference; {poss} hairstyle is set separately here.")
        if hair in presets:
            h = presets[hair]
            person.append(sentence(f(h["main_en"]) + "; " + f(h["closing_en"])))
            hair_echo = f(h["echo_en"])
            hair_echo2 = f(h.get("echo2_en", ""))
        else:
            person.append(sentence(k.clean_text(hair)))
    elif lora.get("hair"):
        person.append(sentence(f"{subj.capitalize()} has {k.clean_text(lora['hair'])}"))

    if not outfit and common_outfit:
        person.append(common_outfit_sentence(location, framing, subj, poss, detailed, seed))
        for acc in lora.get("signature_accessories", []):
            person.append(sentence(f"{subj.capitalize()} also wears " + (acc if "neck" in acc or "choker" not in acc else f"{acc} around {poss} neck")))
    if outfit:
        wear = [outfit["normal_en"]]
        for acc in lora.get("signature_accessories", []):
            wear.append(acc if "neck" in acc or "choker" not in acc else f"{acc} around {poss} neck")
        person.append(sentence(f"{subj.capitalize()} wears {_join(wear)}"))
        if detailed:
            person.extend(sentence(f(t)) for t in outfit.get("detail_prose_en", []))
    if pack.get("person_extra_en"):
        person.append(sentence(f(pack["person_extra_en"])))
    person.append(sentence(f"{subj.capitalize()} {f(mo['pose_en'])}"))
    person.append(sentence(f"{subj.capitalize()} is {f(exp['main_en'])}"))      # expression gets its own sentence
    person.append(sentence(cap(f(mo["moment_en"]))))
    if expr_level >= 1:
        person.append(sentence(f(exp["echo_en"])))
    if level >= 1:
        if hair_echo:
            person.append(sentence(hair_echo))
        if outfit and outfit.get("echo_en"):
            person.append(sentence(f(outfit["echo_en"][0])))
    if expr_level >= 2:
        if exp.get("echo2_en"):
            person.append(sentence(f(exp["echo2_en"])))
    if level >= 2:
        if hair_echo2:
            person.append(sentence(hair_echo2))
        if outfit and len(outfit.get("echo_en", [])) > 1:
            person.append(sentence(f(outfit["echo_en"][1])))
    person.append(sentence(f"{poss.capitalize()} skin shows fine pores and soft vellus hair, matte, with no smoothing and no retouching"))
    person_text = " ".join(person)

    # ---------------- scene prompt
    # a time of day may bring its own water / ground / far-view / style lines (e.g. night)
    waters = list(tm.get("feature_en", pack["feature_en"]))
    grounds = list(tm.get("ground_en", pack["ground_en"]))
    fars = list(tm.get("far_en", pack["far_en"]))
    style_line = tm.get("style_en", pack["style_en"])
    rng.shuffle(waters), rng.shuffle(grounds), rng.shuffle(fars)

    def build_scene_text(fx) -> str:
        out = [sentence(f"{pack['setting_en']} {tm.get('time_prep', 'at')} {tm['time_en']}".replace("  ", " ") + f", {tm['sky_en']}, with {waters[0]} and {grounds[0]}")]
        if detailed and len(waters) > 1 and len(grounds) > 1:
            out.append(sentence(f"{pack.get('more_prefix_en', 'Farther along')}, {waters[1]}, with {grounds[1]}"))
        light = cap(fx(tm["light_en"])) + (f", and {tm['accent_en']}" if tm.get("accent_en") else "")
        out.append(sentence(light))
        if detailed:
            out.append(sentence(cap(_join(pack["detail_en"][time_key]))))
        out.append(sentence(f"{cap(fx(tm['shadow_en']))}, with {_join(fars[:2] if detailed else fars[:1])}"))
        if detailed:
            out.append(sentence(fx(pack["position_en"])))
            if framing == "전신" and pack.get("ground_contact_en"):      # only what the frame can show
                out.append(sentence(fx(pack["ground_contact_en"])))
        out.append(sentence(fx(tm.get("camera", pack["camera"])[framing])))
        out.append(sentence(style_line))
        return " ".join(out)

    scene_text = build_scene_text(fs)                          # regional use: "the woman"
    combined = f"{person_text} {build_scene_text(f)}"          # one person, one prompt: "her" keeps the thread
    problems = lint(combined)
    if hair and lora.get("hair"):                               # the replaced LoRA hair must be gone entirely
        old = k.clean_text(lora["hair"]).lower()
        if old[:40] in combined.lower() or "knot high on the crown" in combined.lower() and "knot" not in hair.lower():
            problems.append("LoRA hair text survived a hair override")
    return {"person": person_text, "scene": scene_text, "combined": combined, "problems": problems,
            "words": len(combined.split()), "reinforce": level}


def common_outfit_sentence(location: str, framing: str, subj: str, poss: str, detailed: bool, seed: int) -> str:
    """An outfit from the common pool (the main program's garment tables), fitted to the place and the frame.
    Only what the frame can show is written (companion garment, footwear and accessory follow the engine rules)."""
    import random
    import krea2_prose as kp
    c = k.defaults()
    for key, value in {"people": "1", "location": location, "framing": framing}.items():
        k.set_constraint_value(c, key, value)
    scene = k.build_scene(seed, c, None, None, "", False)
    person = k.resolve_person(random.Random(seed + 17), scene, "A", k.PersonSlot(slot="PERSON_A"))
    ref = {"s": subj, "S": subj.capitalize(), "p": poss, "P": poss.capitalize(), "o": "her", "wear": "wears"}
    return kp.render_clothing(person, ref, detailed, scene)


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
    ap.add_argument("--parts", action="store_true", help="show person and scene prompts separately (for regional use)")
    ap.add_argument("--expression", default="환한 미소")
    ap.add_argument("--framing", default="전신")
    ap.add_argument("--time", default="해질녘")
    ap.add_argument("--hair", default="", help="override the LoRA hair: a preset name or free text (replaces it entirely)")
    ap.add_argument("--mode", default="보통", choices=MODES, help="description volume: 보통 / 상세")
    ap.add_argument("--reinforce", type=int, default=None, choices=(0, 1, 2),
                    help="how many extra restatements of expression/hair/outfit (default: 보통=0, 상세=1)")
    ap.add_argument("--old", action="store_true", help="the first engine-based prototype (sample A)")
    args = ap.parse_args()
    if args.old:
        result = build_sample(args.trigger, args.outfit, args.seed)
        print(result["prompt"])
        print(f"\n[{result['words']} words, seed {result['seed']}, problems: {result['problems'] or 'none'}]")
        return 1 if result["problems"] else 0
    r = compose_split(args.trigger, args.outfit, time_key=args.time, framing=args.framing,
                      expression=args.expression, hair=args.hair, mode=args.mode, reinforce=args.reinforce, seed=args.seed)
    if args.parts:
        print("[인물 프롬프트]\n" + r["person"] + "\n\n[장면 프롬프트]\n" + r["scene"])
    else:
        print(r["combined"])           # one person: a single prompt, person first so the LoRA trigger leads
    print(f"\n[{r['words']} words, problems: {r['problems'] or 'none'}]")
    return 1 if r["problems"] else 0


if __name__ == "__main__":
    sys.exit(main())
