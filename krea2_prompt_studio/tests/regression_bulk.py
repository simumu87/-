#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bulk regression check: python tests/regression_bulk.py [seeds]

Generates 1-person and 2-person prompts for many seeds and asserts that none of
the known v10.0.2 defects come back. Run from the package folder (needs Python 3.8+).
"""
import importlib
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import krea2_prompt_studio as k  # noqa: E402

CHECKS = [
    ("char-split join", re.compile(r"\b\w; \w; \w")),
    ("ungrammatical placement", re.compile(r"\bat (in|near|along|far|slightly)\b")),
    ("unset trigger leaked", re.compile(r"(^|, )auto, ")),
    ("korean leaked", re.compile(r"[가-힣]")),
]
SOLO_BAD = re.compile(r"other person|another person|each other|two people")


def hair_checks():
    """LoRA hair: kept when no override, fully replaced when overridden."""
    problems = []
    for override in ("", "straight blunt bangs over the forehead, hair worn loose past the shoulders"):
        o = k.GenerationOptions(seed=5)
        o.person_a = k.PersonSlot(slot="PERSON_A", lora_trigger="nayoon")
        c = k.defaults()
        if override:
            k.set_constraint_value(c, "hair_A", override)
        text = k.generate_one(o, c, seed=5).combined_prompt
        has_knot = "knot high on the crown" in text
        if override and (has_knot or "blunt bangs" not in text):
            problems.append((0, 1, "hair override did not replace the LoRA hair"))
        if not override and not has_knot:
            problems.append((0, 1, "LoRA hair missing when no override"))
    return problems


def pool_checks():
    """Pool files must reload to the exact in-code defaults and cover every pool."""
    import json
    problems = []
    for name in k.POOL_LABELS_KO:
        path = k.POOLS_DIR / f"{name.lower()}.json"
        if not path.exists():
            problems.append((0, 0, f"pool file missing: {path.name}"))
            continue
        items = json.loads(path.read_text(encoding="utf-8"))["items"]
        if {ko: v["en"] for ko, v in items.items()} != getattr(k, name):
            problems.append((0, 0, f"pool file differs from loaded pool: {name}"))
        if any(re.search(r"[가-힣]", v["en"]) for v in items.values()):
            problems.append((0, 0, f"Hangul inside an English value: {name}"))
    return problems


def composer_checks():
    """v11 composer: both modes, every hair preset, every expression, both times - no problems, trigger first."""
    import krea2_composer as c
    problems = []
    for mode in c.MODES:
        for hair in [""] + list(c.load_hair_presets()) + ["free text hair: a tidy side braid over her left shoulder"]:
            for expression in c.load_expressions():
                for time_key in ("해질녘", "오후", "밤", "밤(달빛만)", "밤(달빛 역광)", "밤(달빛 측광)", "밤(달빛 측광·위치만)"):
                    counts = []
                    for lv in (0, 1, 2):
                        rr = c.compose_split("nayoon", "gold_amber_triangle_string_bikini", time_key=time_key,
                                             expression=expression, hair=hair, mode=mode, reinforce=lv)
                        counts.append(rr["words"])
                        for pr in rr["problems"]:
                            problems.append((0, 0, f"composer {(mode, hair[:12], expression, time_key, lv)}: {pr}"))
                        if "{" in rr["combined"] or "}" in rr["combined"]:
                            problems.append((0, 0, f"composer {(mode, hair[:12], expression, time_key, lv)}: unfilled placeholder"))
                    if not (counts[0] < counts[1] < counts[2]):
                        problems.append((0, 0, f"composer {(mode, hair[:12], expression, time_key)}: reinforcement does not add text {counts}"))
                    r = c.compose_split("nayoon", "gold_amber_triangle_string_bikini", time_key=time_key,
                                        expression=expression, hair=hair, mode=mode)
                    tag = (mode, hair[:12], expression, time_key)
                    for pr in r["problems"]:
                        problems.append((0, 0, f"composer {tag}: {pr}"))
                    if not r["combined"].startswith("nayoon, "):
                        problems.append((0, 0, f"composer {tag}: trigger is not first"))
                    if "the woman" in r["combined"]:
                        problems.append((0, 0, f"composer {tag}: 'the woman' leaked into the combined prompt"))
                    if "{" in r["combined"] or "}" in r["combined"]:
                        problems.append((0, 0, f"composer {tag}: unfilled placeholder"))
                    if hair in c.load_hair_presets() and "Hairstyle" in r["combined"]:
                        problems.append((0, 0, f"composer {tag}: label in prompt"))
                    if "the woman" not in r["scene"]:
                        problems.append((0, 0, f"composer {tag}: regional scene prompt should say 'the woman'"))
    return problems


def pack_checks():
    """Every scene pack x time x valid moment x frame x mode: clean prose, only what the frame can show."""
    import krea2_composer as c
    problems = []
    feet = re.compile(r"\b(feet|foot|ankles?|barefoot|toes)\b", re.I)
    for loc in c.PACK_FILES:
        pack = c.load_pack(loc)
        for tk in pack["times"]:
            for mk, mo in pack["moments"].items():
                for fr in pack["camera"]:
                    if fr not in mo.get("frames", list(pack["camera"])):
                        continue
                    for mode in c.MODES:
                        for outfit, common in (("", True), ("", False)) + ((("gold_amber_triangle_string_bikini", False),) if loc == "해변" else ()):
                            tag = (loc, tk, mk, fr, mode, bool(outfit), common)
                            r = c.compose_split("nayoon", outfit, location=loc, time_key=tk, moment=mk, framing=fr,
                                                mode=mode, seed=3, common_outfit=common)
                            for pr in r["problems"]:
                                problems.append((0, 0, f"pack {tag}: {pr}"))
                            text = r["combined"]
                            if "{" in text or "}" in text:
                                problems.append((0, 0, f"pack {tag}: unfilled placeholder"))
                            if re.search(r"\b(at|on|in) (at|on|in)\b|\bthe the\b|\ba [aeiou]\w|\ban [bcdfghjklmnpqrstvwxyz]\w", text):
                                problems.append((0, 0, f"pack {tag}: grammar slip"))
                            if loc != "해변" and re.search(r"bikini|swimsuit", text, re.I):
                                problems.append((0, 0, f"pack {tag}: swimwear outside the beach"))
                            if fr != "전신" and feet.search(r["scene"]):
                                problems.append((0, 0, f"pack {tag}: feet written but the frame cannot show them"))
    return problems


def pose2p_checks():
    """2-person pose library: both bodies agree on the contact, nothing the frame cannot show, no grammar slips."""
    import krea2_pose2p as lib
    problems = [(0, 2, f"pose library: {x}") for x in lib.validate()]
    feet = re.compile(r"\b(feet|foot|knees?)\b", re.I)
    for inter, pose in lib.load_poses().items():
        for framing in ("전신", "무릎 위", "허리 위", "가슴 위", "클로즈업"):
            for seed in range(1, 25):
                c = k.defaults()
                k.set_constraint_value(c, "people", "2")
                k.set_constraint_value(c, "interaction", inter)
                k.set_constraint_value(c, "framing", framing)
                try:
                    r = k.generate_one(k.GenerationOptions(seed=seed), c, seed=seed)
                except Exception as exc:  # noqa: BLE001
                    problems.append((seed, 2, f"pose2p {inter}/{framing}: generation failed {exc!r}"))
                    continue
                if k.build_scene(seed, c, None, None, "", False).interaction_key != inter:
                    continue                                   # the rules replaced the interaction for this activity
                a, b = r.person_a_prompt, r.person_b_prompt
                if re.search(r"\bis (stands|sits)\b", a + b):
                    problems.append((seed, 2, f"pose2p {inter}/{framing}: 'is stands/sits'"))
                if re.search(r"\b(left|right) (hand|arm|foot|leg|shoulder)\b", a + b):
                    problems.append((seed, 2, f"pose2p {inter}/{framing}: left/right limb wording"))
                if framing in pose["frames_ok"]:
                    for word in pose["contacts"]:
                        if word not in a or word not in b:
                            problems.append((seed, 2, f"pose2p {inter}/{framing}: contact '{word}' missing on one side"))
                    if framing != "전신" and feet.search(a + b) and "feet" in (a + b).lower():
                        problems.append((seed, 2, f"pose2p {inter}/{framing}: feet written but not visible"))
                    if a.count("looking") + a.count("gaze") > 1 or b.count("looking") + b.count("gaze") > 1:
                        problems.append((seed, 2, f"pose2p {inter}/{framing}: two gaze statements"))
    return problems


def pose1p_checks():
    """1-person pose library x every framing: only what the frame shows, one gaze, extent sentence present."""
    import krea2_pose1p as lib
    problems = [(0, 1, f"pose1p library: {x}") for x in lib.validate()]
    legs = re.compile(r"\b(knees?|legs?|shins?|feet|foot|heel|toes)\b", re.I)
    rules = k.scene_rules()
    for pose_key in lib.load_poses():
        for framing in k.CAMERA_FRAMING:
            depth = rules.depth_of(framing)
            c = k.defaults()
            k.set_constraint_value(c, "people", "1")
            k.set_constraint_value(c, "pose", pose_key)
            k.set_constraint_value(c, "framing", framing)
            for seed in (1, 2, 3):
                try:
                    r = k.generate_one(k.GenerationOptions(seed=seed), c, seed=seed)
                except Exception as exc:  # noqa: BLE001
                    problems.append((seed, 1, f"pose1p {pose_key}/{framing}: generation failed {exc!r}"))
                    continue
                if k.build_scene(seed, c, None, None, "", False).pose_a.get("pose_key") != pose_key:
                    continue                                    # the rules swapped the pose for this activity
                text = r.combined_prompt
                m = re.search(r"[^.]*\b(?:is|are) (?:standing|sitting|walking|kneeling|running|riding|holding|performing)\b[^.]*\.", text)
                body = m.group(0) if m else ""
                if depth < 5 and legs.search(body):
                    problems.append((seed, 1, f"pose1p {pose_key}/{framing}: leg/foot words but the frame ends above the knees"))
                if depth < 6 and re.search(r"\b(feet|foot|heel|toes)\b", body, re.I):
                    problems.append((seed, 1, f"pose1p {pose_key}/{framing}: feet written but not visible"))
                if "frame" not in text or ("taking up" not in text and "filling" not in text and "fills the frame" not in text and "frame ends" not in text):
                    problems.append((seed, 1, f"pose1p {pose_key}/{framing}: no extent sentence"))
                if re.search(r"\b(left|right) (hand|arm|foot|leg|shoulder|knee)\b", text):
                    problems.append((seed, 1, f"pose1p {pose_key}/{framing}: left/right limb wording"))
    return problems


def desc_checks():
    """Every option shown in a menu must carry a Korean description."""
    problems = []
    live = {"THEMES": k.THEMES, "RELATIONSHIPS": k.RELATIONSHIPS, "INTERACTIONS": k.INTERACTIONS,
            "ACTIVITIES": k.ACTIVITIES, "TIME_OF_DAY": k.TIME_OF_DAY, "WEATHER": k.WEATHER, "MOODS": k.MOODS,
            "REALISM": k.REALISM, "SKIN_FINISH": k.SKIN_FINISH, "CAMERA_FRAMING": k.CAMERA_FRAMING,
            "VIEWPOINTS": k.VIEWPOINTS, "COMPOSITIONS": k.COMPOSITIONS, "LIGHT_SOURCES": k.LIGHT_SOURCES,
            "STYLE_LIBRARY": k.STYLE_LIBRARY, "PALETTES": k.PALETTES, "COLORS": k.COLORS,
            "CLOTHING_STATES": k.CLOTHING_STATES, "LOCATIONS": k.LOCATIONS, "BASE_POSES": k.BASE_POSES,
            "GARMENTS": k.GARMENTS, "FABRICS": k.FABRICS, "ENV_DENSITY": k.ENV_DENSITY,
            "RANDOM_MODES": k.RANDOM_MODES}
    for group, data in live.items():
        descs = k.option_descriptions(group)
        for key in data:
            if not descs.get(key):
                problems.append((0, 0, f"no Korean description: {group}/{key}"))
        for key, text in descs.items():
            if not re.search(r"[가-힣]", text):
                problems.append((0, 0, f"description is not Korean: {group}/{key}"))
    import krea2_composer as c
    for key, v in c.load_expressions().items():
        if not v.get("desc_ko"):
            problems.append((0, 0, f"no Korean description: expression/{key}"))
    for key, v in c.load_hair_presets().items():
        if not v.get("desc_ko"):
            problems.append((0, 0, f"no Korean description: hair preset/{key}"))
    # each expression must name the emotion AND describe it anatomically ("a wide, genuine smile: cheeks rise ...")
    labels = {"환한 미소": "smile", "은은한 미소": "smile", "수줍은 미소": "smile", "장난스러운 미소": "smirk",
              "메롱": "tongue", "놀람": "surprised", "윙크": "wink", "무표정": "neutral"}
    for key, v in c.load_expressions().items():
        main = v.get("main_en", "")
        want = labels.get(key)
        if want and want not in main.lower():
            problems.append((0, 0, f"expression {key}: emotion label '{want}' missing in main_en"))
        if ":" not in main and key in labels:
            problems.append((0, 0, f"expression {key}: no 'label: anatomy' structure in main_en"))
        if re.search(r"narrow|squint|half-clos", " ".join(str(x) for x in v.values()), re.I):
            problems.append((0, 0, f"expression {key}: eye-narrowing wording"))
        if key in labels and len(main.split()) < 18:
            problems.append((0, 0, f"expression {key}: anatomy description too short"))
    pack = c.load_pack("해변")
    for sect in ("times", "moments"):
        for key, v in pack[sect].items():
            if not v.get("desc_ko"):
                problems.append((0, 0, f"no Korean description: beach {sect}/{key}"))
    return problems


def engine_prose_checks():
    """Menu modes 1-4 (generate_one) must use the v11 prose style."""
    import krea2_prose  # noqa: F401
    problems = []
    for seed in range(1, 41):
        for people in (1, 2):
            for detail in ("보통", "상세"):
                c = k.defaults()
                k.set_constraint_value(c, "people", str(people))
                o = k.GenerationOptions(seed=seed, detail=detail)
                try:
                    r = k.generate_one(o, c, seed=seed)
                except Exception as exc:  # noqa: BLE001
                    problems.append((seed, people, f"engine path failed ({detail}): {exc!r}"))
                    continue
                text = r.combined_prompt
                tag = (seed, people, detail)
                if re.search(r"\b[A-Z][a-z]+:\s", text):
                    problems.append((*tag[:2], f"label in engine prompt ({detail})"))
                if re.search(r"scale lock|Keep all|believable|proportionally sized|human-scale|front-left|front-right", text):
                    problems.append((*tag[:2], f"legacy wording in engine prompt ({detail})"))
                if re.search(r"\bThey (is|has|wears)\b|\ba [aeiou]\w|\ban [bcdfghjklmnpqrstvwxyz]\w", text):
                    problems.append((*tag[:2], f"grammar slip in engine prompt ({detail})"))
                if people == 2 and not (r.person_a_prompt and r.person_b_prompt and r.global_prompt):
                    problems.append((*tag[:2], "regional parts missing"))
    # a LoRA person: trigger first, LoRA hair kept, hair override replaces it
    o = k.GenerationOptions(seed=3)
    o.person_a = k.PersonSlot(slot="PERSON_A", lora_trigger="nayoon")
    text = k.generate_one(o, k.defaults(), seed=3).combined_prompt
    if not text.startswith("nayoon, ") or "knot high on the crown" not in text:
        problems.append((3, 1, "LoRA person: trigger/hair missing in engine prompt"))
    return problems


def consistency_checks():
    """Automatically resolved scenes must not contradict themselves (pose/interaction/light/clothing)."""
    import scene_consistency
    return [] if scene_consistency.main(120, quiet=True) == 0 else [(0, 0, "scene contradictions found (run tests/scene_consistency.py)")]


def visibility_checks():
    """Write only what the frame can show; a top always comes with a bottom (or a dress)."""
    problems = []
    import krea2_prose as pr
    rules = k.scene_rules()
    for seed in range(1, 61):
        for framing in ("전신", "허리 위", "클로즈업"):
            c = k.defaults()
            k.set_constraint_value(c, "people", "1")
            k.set_constraint_value(c, "framing", framing)
            try:
                sc = k.build_scene(seed, c, None, None, "", False)
                text = k.generate_one(k.GenerationOptions(seed=seed), c, seed=seed).combined_prompt.lower()
            except Exception as exc:  # noqa: BLE001
                problems.append((seed, 1, f"visibility run failed ({framing}): {exc!r}"))
                continue
            main_g = sc.clothing_a
            slot = rules.garment_slot(main_g.garment_key)
            if slot in ("top", "bottom") and sc.clothing_extra_a is None:
                problems.append((seed, 1, "top/bottom outfit without its companion garment"))
            foot = k.pr_plain(main_g.footwear).lower() if hasattr(k, "pr_plain") else main_g.footwear.lower()
            if framing != "전신" and foot and foot in text:
                problems.append((seed, 1, f"footwear written although the frame ({framing}) cannot show it"))
            sheer = [g for g in (main_g, sc.clothing_extra_a) if g is not None
                     and g.fabric.key in rules.data["layers"]["sheer_materials"]
                     and rules.slot_visible(rules.garment_slot(g.garment_key), rules.depth_of(framing))]
            if sheer and rules.data["layers"].get("enabled", False) and "opaque" not in text:
                problems.append((seed, 1, f"sheer garment without an opaque under-layer ({framing})"))
            if framing == "전신" and sc.clothing_extra_a is not None:
                for g in (main_g, sc.clothing_extra_a):
                    if pr.plain(g.color).lower() not in text:
                        problems.append((seed, 1, "full-body prompt misses one of the two garments"))
                        break
    return problems


def hangyeol_checks():
    """Hangyeol outfits: every listed outfit x its locations x times x frames x modes composes cleanly,
    and each outfit only names what the frame can show (shoes only on full-length, belt/skirt only from the waist down)."""
    out = []
    c = importlib.import_module("krea2_composer")
    shoe = re.compile(r"\b(?:shoes?|sandals?|sneakers?)\b", re.I)
    lower = re.compile(r"\b(?:skirt|belt|pleat\w*|tiered)\b", re.I)
    rules = k.scene_rules()
    for oid in c.outfits_for_trigger("hangyeol"):
        data = c.load_outfit(oid)
        for loc in data["applies_to"]["locations"]:
            pack = c.load_pack(loc)
            for tk in pack["times"]:
                for mk, mv in pack["moments"].items():
                    for fr in mv.get("frames", list(pack["camera"])):
                        if fr not in pack["camera"]:
                            continue
                        depth = rules.depth_of(fr)
                        for mode in ("보통", "상세"):
                            r = c.compose_split("hangyeol", oid, location=loc, time_key=tk, moment=mk, framing=fr, mode=mode, seed=3, common_outfit=False)
                            person = r["person"]
                            tag = (oid, loc, tk, mk, fr, mode)
                            if r["problems"]:
                                out.append((0, 1, f"hangyeol compose problems {tag}: {r['problems'][:2]}"))
                            wear = person.split("She wears", 1)[-1].split(".", 1)[0] if "She wears" in person else ""
                            if depth < 6 and shoe.search(wear):
                                out.append((0, 1, f"hangyeol footwear in a frame without feet {tag}"))
                            if depth <= 1 and lower.search(wear) and "swimsuit" not in oid:
                                out.append((0, 1, f"hangyeol lower garment in a chest-up frame {tag}"))
    # reference mode: no identity / skin sentence, and clearly shorter than the normal prompt
    base = dict(location="은행나무 길", time_key="오후", moment="천천히 걷기", framing="전신", mode="보통", seed=3, common_outfit=False)
    full = c.compose_split("hangyeol", "hangyeol_autumn_cream_knit_sage_pleated", **base)
    ref = c.compose_split("hangyeol", "hangyeol_autumn_cream_knit_sage_pleated", reference=True, **base)
    if re.search(r"hangyeol|oval face|vellus|gold wire-frame", ref["combined"]):
        out.append((0, 1, "reference mode still writes identity/skin text"))
    if ref["words"] >= full["words"] - 40:
        out.append((0, 1, f"reference mode is not shorter ({ref['words']} vs {full['words']})"))
    if ref["problems"]:
        out.append((0, 1, f"reference mode problems: {ref['problems'][:2]}"))
    return out


def main() -> int:
    seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    problems = hair_checks() + pool_checks() + composer_checks() + pack_checks() + pose2p_checks() + pose1p_checks() + desc_checks() + engine_prose_checks() + consistency_checks() + visibility_checks() + hangyeol_checks()
    for seed in range(1, seeds + 1):
        for people in (1, 2):
            c = k.defaults()
            k.set_constraint_value(c, "people", str(people))
            try:
                text = k.generate_one(k.GenerationOptions(seed=seed), c, seed=seed).combined_prompt
            except Exception as exc:  # generation must never fail
                problems.append((seed, people, f"generation failed: {exc!r}"))
                continue
            for name, rx in CHECKS:
                if rx.search(text):
                    problems.append((seed, people, name))
            if people == 1 and SOLO_BAD.search(text):
                problems.append((seed, people, "two-person wording in single scene"))
    for item in problems[:20]:
        print("FAIL", item)
    print(f"{seeds * 2} prompts checked, {len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
