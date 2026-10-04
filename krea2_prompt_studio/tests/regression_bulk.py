#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Bulk regression check: python tests/regression_bulk.py [seeds]

Generates 1-person and 2-person prompts for many seeds and asserts that none of
the known v10.0.2 defects come back. Run from the package folder (needs Python 3.8+).
"""
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
                for time_key in ("해질녘", "오후", "밤", "밤(달빛만)"):
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


def main() -> int:
    seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    problems = hair_checks() + pool_checks() + composer_checks()
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
