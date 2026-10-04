#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Prose renderer for the scene engine (v11).

Turns the engine's resolved scene (SceneProfile + PersonSlot) into prompts that read like a person wrote them:
one flowing paragraph per person and one for the scene, no field labels, no model-facing instructions.

Writing rules (agreed with the user, see docs/):
  * state light sources and materials, never what the light does to a material
  * colours are stated directly, with no cause-and-effect wording
  * the LoRA trigger leads the combined prompt, the LoRA identity is used as registered
  * a hair override replaces the LoRA hair entirely
"""
from __future__ import annotations

import importlib
import re
import sys
from typing import Any, Dict, List, Optional, Tuple


def _studio():
    """The studio module: __main__ when started from the menu, otherwise the imported module."""
    main = sys.modules.get("__main__")
    if main is not None and hasattr(main, "compose_prompt"):
        return main
    return importlib.import_module("krea2_prompt_studio")


# ---------------------------------------------------------------------------
# small text helpers
# ---------------------------------------------------------------------------
_FILLER = [
    (r"\bproportionally sized\s+", ""),
    (r"\s+with a realistic human-scale stand", ""),
    (r"\brealistic human-scale\s+", ""),
    (r"\bbelievable\s+", ""),
    (r"\bcredible\s+", ""),
    (r"\bwhen supported by the architecture\b", ""),
]


def plain(text: str) -> str:
    """Drop the engine's reassurance wording ('believable', 'proportionally sized' ...)."""
    value = str(text or "")
    for pattern, repl in _FILLER:
        value = re.sub(pattern, repl, value, flags=re.I)
    value = re.sub(r"\s{2,}", " ", value)
    value = re.sub(r"\s+([,.;])", r"\1", value)
    return fix_articles(value.strip(" ,;"))


_A_KEEP = ("uni", "use", "usu", "uti", "eu", "one", "once", "ubi")
_AN_KEEP = ("hour", "honest", "heir", "honor")


def fix_articles(text: str) -> str:
    def to_a_an(m):
        nxt = m.group(2)
        low = nxt.lower()
        if m.group(1).lower() == "a" and low[0] in "aeiou" and not low.startswith(_A_KEEP):
            return ("An " if m.group(1) == "A" else "an ") + nxt
        if m.group(1).lower() == "an" and low[0] not in "aeiou" and not low.startswith(_AN_KEEP) and low[0].isalpha():
            return ("A " if m.group(1) == "An" else "a ") + nxt
        return m.group(0)
    return re.sub(r"\b(a|an|A|An)\s+([A-Za-z][A-Za-z\-]*)", to_a_an, text)


def cap(text: str) -> str:
    return text[:1].upper() + text[1:] if text else text


def sentence(text: str) -> str:
    text = re.sub(r"\s+", " ", (text or "")).strip()
    if text and text[-1] not in ".!?":
        text += "."
    return fix_articles(cap(text))


def join_list(items: List[str]) -> str:
    items = [x for x in items if x]
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " and " + items[-1]


def article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


def strip_article(text: str) -> str:
    return re.sub(r"^(an?|the)\s+", "", text.strip(), flags=re.I)


# light directions: always relative to the camera or the subject, never "front-left"
DIRECTION_TEXT = {
    "from camera left": "from the camera's left",
    "from camera right": "from the camera's right",
    "from behind the subject": "from behind {o}",
    "from front-left": "from the camera's left side",
    "from front-right": "from the camera's right side",
    "from above and slightly to the side": "from above and a little to one side",
    "wrapping softly from both sides": "wrapping softly in from both sides",
}


# ---------------------------------------------------------------------------
# who is speaking about whom
# ---------------------------------------------------------------------------
def pronouns(person, lora: Optional[Dict[str, Any]], people: int) -> Dict[str, str]:
    gender = (lora or {}).get("gender", "")
    text = f"{person.identity} {gender}".lower()
    if not gender:
        if re.search(r"\b(woman|female|girl|she)\b", text):
            gender = "female"
        elif re.search(r"\b(man|male|boy|he)\b", text):
            gender = "male"
    verbs = {"be": "is", "have": "has", "wear": "wears"}
    if gender == "female":
        s, p, o = "she", "her", "her"
    elif gender == "male":
        s, p, o = "he", "his", "him"
    elif people == 2:
        side = "left" if "left" in person.position else "right"
        return {"s": f"the person on the {side}", "S": f"The person on the {side}", "p": "their", "P": "Their",
                "o": "them", **verbs}
    else:
        s, p, o = "they", "their", "them"
        verbs = {"be": "are", "have": "have", "wear": "wear"}
    return {"s": s, "S": cap(s), "p": p, "P": cap(p), "o": o, **verbs}


# ---------------------------------------------------------------------------
# person
# ---------------------------------------------------------------------------
def generic_identity(person, second: bool = False) -> str:
    """A person without a LoRA: describe the generated traits in one natural sentence."""
    color = re.sub(r"\s*hair$", "", person.hair_color or "", flags=re.I)
    hair = person.hair or ""
    hair_phrase = f"{hair} in a {color} shade" if hair and color else (hair or (person.hair_color or ""))
    bits = [x for x in (hair_phrase, person.eye_color, person.distinctive_feature) if x]
    build = person.body_build
    text = "Another adult person" if second else "An adult person"
    if bits:
        text += " with " + join_list(bits)
        if build:
            text += f", and {article(build)} {build}"
    elif build:
        text += f" with {article(build)} {build}"
    return text


def framing_key(scene) -> str:
    """The Korean framing key of the scene's camera (to know how much of the body is in the frame)."""
    st = _studio()
    for key, text in st.CAMERA_FRAMING.items():
        if text == scene.camera.framing:
            return key
    return "전신"


def _garment_phrase(cl, detailed: bool) -> str:
    garment = plain(cl.garment_en)
    color = plain(cl.color)
    if re.match(r"^(an?)\s", garment, flags=re.I):
        item = f"{article(color)} {color} {strip_article(garment)}"
    else:
        item = f"{color} {garment}"
    text = f"{item}, {plain(cl.fit)}, in {plain(cl.fabric.material)}"
    texture = plain(cl.fabric.texture)
    if texture:
        text += f" with a {texture}"
    return text


def shown_garments(scene, person) -> list:
    """The garments the framing can show, upper body first."""
    cl = person.clothing
    if cl is None:
        return []
    rules = _studio().scene_rules()
    depth = rules.depth_of(framing_key(scene)) if scene is not None else 6
    garments = [g for g in (cl, getattr(person, "clothing_extra", None)) if g is not None]
    shown = [g for g in garments if rules.slot_visible(rules.garment_slot(g.garment_key), depth)] or [cl]
    order = {"top": 0, "dress": 0, "bottom": 1}
    return sorted(shown, key=lambda g: order.get(rules.garment_slot(g.garment_key), 0))


def render_clothing(person, ref: Dict[str, str], detailed: bool, scene=None) -> str:
    """The outfit, limited to what the framing can show (top, bottom, shoes, accessories)."""
    cl = person.clothing
    if cl is None:
        return ""
    st = _studio()
    rules = st.scene_rules()
    depth = rules.depth_of(framing_key(scene)) if scene is not None else 6
    shown = shown_garments(scene, person)
    phrases = [_garment_phrase(g, detailed) for g in shown]
    text = f"{ref['S']} {ref['wear']} {phrases[0]}" + (f", paired with {phrases[1]}" if len(phrases) > 1 else "")
    extras = []
    if rules.slot_visible("footwear", depth) and cl.footwear:
        extras.append(plain(cl.footwear))
    acc_key = next((k_ for k_, v_ in st.ACCESSORIES.items() if v_ == cl.accessory), "")
    if cl.accessory and (not acc_key or rules.accessory_visible(acc_key, depth)):
        extras.append(plain(cl.accessory))
    if extras:
        text += f", along with {join_list(extras)}"
    out = [sentence(text)]
    if detailed:
        for g in shown:
            fab = g.fabric
            out.append(sentence(f"The {plain(fab.material)} is {plain(fab.construction)}, with {plain(fab.density)} density and a {plain(fab.drape)}"))
            if g.details:
                out.append(sentence(f"Details include {plain(g.details)}"))
        if cl.state:
            out.append(sentence(f"The clothes look {plain(cl.state)}"))
    return " ".join(out)


def hair_preset(value: str):
    """A hair override that matches a preset name uses the preset's wording."""
    try:
        import krea2_composer as comp
        return comp.load_hair_presets().get(value)
    except Exception:  # noqa: BLE001 - presets are optional
        return None


def render_person(scene, person, lora: Optional[Dict[str, Any]], detailed: bool = False,
                  reinforce: Optional[int] = None, hair_override: str = "", second: bool = False) -> str:
    """One person as one paragraph: identity -> hair -> outfit -> action and expression -> skin."""
    st = _studio()
    import krea2_composer as comp
    level = (1 if detailed else 0) if reinforce is None else int(reinforce)
    ref = pronouns(person, lora, scene.people)
    f = lambda t: t.format_map({"s": ref["s"], "S": ref["S"], "p": ref["p"], "P": ref["P"], "o": ref["o"],
                                "color": (lora or {}).get("hair_color", "")})
    out: List[str] = []

    # identity (LoRA identity is used exactly as registered)
    if person.lora_trigger and lora:
        out.append(f"{person.lora_trigger}, {comp.identity_to_prose(person.identity, person.lora_trigger, ref['s'])}".rstrip(".") + ".")
        if hair_override:
            out.append(f"Only {ref['p']} face and body follow the {person.lora_trigger} reference; {ref['p']} hairstyle is set separately here.")
            preset = hair_preset(hair_override)
            if preset:
                out.append(sentence(f(preset["main_en"]) + "; " + f(preset["closing_en"])))
            else:
                out.append(sentence(hair_override))
        elif person.hair:
            out.append(sentence(f"{ref['S']} {ref['have']} {person.hair}"))
    else:
        identity = person.identity if person.identity and person.identity.lower() not in ("adult person", "a single adult person") \
            else generic_identity(person, second)
        out.append(sentence(plain(identity)))

    # outfit
    out.append(render_clothing(person, ref, detailed, scene))
    sig = (lora or {}).get("signature_accessories", [])
    if sig:
        out.append(sentence(f"{ref['S']} also {ref['wear']} " + join_list([a if "neck" in a or "choker" not in a else f"{a} around {ref['p']} neck" for a in sig])))

    # action and expression (expression stays its own sentence)
    pose = plain(person.pose_en)
    action = scene.activity_en if scene.people == 1 else None
    if action and action not in pose:
        out.append(sentence(f"{ref['S']} {ref['be']} {action}, {pose}"))
    else:
        out.append(sentence(f"{ref['S']} {ref['be']} {pose}"))
    expr = plain(person.expression)
    expr = expr if re.match(r"^(an?|the)\s", expr, flags=re.I) else f"{article(expr)} {expr}"
    out.append(sentence(f"{ref['S']} {ref['have']} {expr}, {plain(person.gaze)}"))
    if scene.people == 2:
        out.append(sentence(f"{ref['S']} {ref['be']} positioned on the {person.position}"))
    if person.height_cm and (scene.people == 2 or detailed):
        out.append(sentence(f"{ref['S']} {ref['be']} about {person.height_cm} cm tall"))
    if person.props:
        out.append(sentence(f"{ref['S']} {'hold' if ref['be'] == 'are' else 'holds'} {join_list([plain(x) for x in person.props])}"))

    # reinforcement of a hair override (different wording, same facts)
    if hair_override and level >= 1:
        preset = hair_preset(hair_override)
        if preset:
            out.append(sentence(f(preset["echo_en"])))
            if level >= 2 and preset.get("echo2_en"):
                out.append(sentence(f(preset["echo2_en"])))

    # skin
    skin = [plain(x) for x in (person.skin_detail,) if x]
    finish = st.SKIN_FINISH.get(st.get_value(scene.constraints, "skin_finish"), st.SKIN_FINISH["자연 피부"])
    out.append(sentence(f"{ref['P']} skin is {plain(skin[0]) if skin and detailed else plain(finish)}".replace("skin is natural skin", "skin is natural")))
    return " ".join(x for x in out if x)


# ---------------------------------------------------------------------------
# scene
# ---------------------------------------------------------------------------
def env_outdoor(scene) -> bool:
    return bool(_studio().LOCATIONS[scene.location_key].get("outdoor"))


def render_scene(scene, detailed: bool = False, regional: bool = False) -> str:
    """Setting, time, light, camera and style as prose. `regional` keeps it free of pronouns."""
    st = _studio()
    env, light, cam = scene.environment, scene.lighting, scene.camera
    who = "the subjects" if scene.people == 2 else ("the subject" if regional else "the subject")
    out: List[str] = []

    depth = st.scene_rules().depth_of(framing_key(scene))
    close = depth <= 1                      # chest-up / close-up: the background is only a soft impression
    count = (1, 1) if close else ((3, 2) if detailed else (2, 1))
    things = [plain(x) for x in (env.furniture[:count[0]] + env.decor[:count[1]]) if x][: (1 if close else 6)]
    place = f"{cap(plain(env.location_en))}, {plain(env.sublocation)}"
    if things:
        place += f", with {join_list(things)}"
    out.append(sentence(place))
    floor = plain(env.floor) if env.floor and env.floor.lower() != "realistic flooring" and depth >= 5 else ""
    walls = plain(env.walls) if env.walls and not close else ""
    if floor and walls:
        out.append(sentence(f"The floor is {floor}, and the walls are {walls}"))
    elif floor or walls:
        out.append(sentence(f"The {'floor is ' + floor if floor else 'walls are ' + walls}"))
    if scene.props and not close:
        out.append(sentence(f"Nearby are {join_list([plain(x) for x in scene.props[:3 if not detailed else 4]])}"))
    if getattr(scene, "weather_visible", True):
        weather = scene.weather_en if env_outdoor(scene) else re.sub(r"\s+outside$", "", scene.weather_en) + " outside the window"
        out.append(sentence(f"It is {scene.time_en}, with {weather}; the mood is {scene.mood_en}"))
    else:
        out.append(sentence(f"It is {scene.time_en}; the mood is {scene.mood_en}"))
    if detailed and env.palette:
        out.append(sentence(f"The colors are a {plain(env.palette)}"))

    direction = DIRECTION_TEXT.get(light.direction, light.direction).format_map({"o": "the woman" if regional else "the subject"})
    intensity = light.intensity if "contrast" in light.intensity else f"{light.intensity} intensity"
    out.append(sentence(f"Lit by {plain(light.source)} {direction}, the light is {light.quality} with {intensity}"))

    out.append(sentence(f"{cap(plain(cam.framing))}, {cam.lens}mm lens, {plain(cam.viewpoint)}, {plain(cam.composition)}, "
                        f"{plain(cam.depth_of_field)}"))
    style = st._style_line(scene)
    out.append(sentence(style))
    if detailed:
        out.append(sentence(plain(scene.realism)))
    return " ".join(out)


# ---------------------------------------------------------------------------
# whole prompt
# ---------------------------------------------------------------------------
def render(scene, person_a, person_b=None, detailed: bool = False, reinforce: Optional[int] = None) -> Dict[str, str]:
    """Returns person_a / person_b / scene (regional use) and the combined prompt."""
    st = _studio()
    c = scene.constraints

    def lora_for(person):
        return st.lora_profile_for_trigger(person.lora_trigger) if person and person.lora_trigger else None

    def override(slot: str, person) -> str:
        value = st.get_value(c, f"hair_{slot}")
        return value if value not in ("", "auto") and lora_for(person) else ""

    a = render_person(scene, person_a, lora_for(person_a), detailed, reinforce, override("A", person_a))
    b = render_person(scene, person_b, lora_for(person_b), detailed, reinforce, override("B", person_b), second=True) if person_b else ""
    regional_scene = render_scene(scene, detailed, regional=True)
    parts = [a]
    if person_b:
        parts.append(b)
        parts.append(sentence(f"The two people are {scene.relationship_en.replace('two adult ', '')}, {scene.activity_en}; "
                              f"they are {plain(scene.interaction_en)}"))
    parts.append(render_scene(scene, detailed))
    return {"person_a": a, "person_b": b, "scene": regional_scene, "combined": " ".join(parts)}
