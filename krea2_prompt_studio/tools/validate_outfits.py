#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Validate outfit JSON files and preview how they render.

    python tools/validate_outfits.py            # validate every file in krea2_prompt_configs/outfits
    python tools/validate_outfits.py --preview  # also print the normal / detailed rendering

Rules checked (all English fields are what reaches the prompt):
  - required keys exist, schema is krea2-outfit/1
  - no Hangul inside any English field
  - no negation wording in English fields (negative prompting does not work in Krea 2 Turbo;
    state the wanted thing instead). `forbidden_ko` is never emitted, so it is exempt.
  - every lock has at least two wording variants (needed for reinforcement)
"""
import json
import re
import sys
from pathlib import Path

OUTFIT_DIR = Path(__file__).resolve().parent.parent / "krea2_prompt_configs" / "outfits"
HANGUL = re.compile(r"[가-힣]")
NEGATION = re.compile(r"\b(no|not|never|without|avoid|don't|doesn't|isn't|aren't|neither|nor|none)\b", re.I)
REQUIRED = ["schema", "id", "name_ko", "name_en", "category", "color", "material", "parts", "locks"]


def english_strings(obj, path=""):
    """Yield (path, text) for every string meant for the prompt (keys ending in en/_en or inside an en list)."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in ("forbidden_ko", "render_notes_ko", "applies_to", "source_doc"):
                continue
            sub = f"{path}.{key}" if path else key
            if key == "en" or key.endswith("_en"):
                yield from _flatten(value, sub)
            else:
                yield from english_strings(value, sub)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            yield from english_strings(item, f"{path}[{i}]")


def _flatten(value, path):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, list):
        for i, item in enumerate(value):
            yield from _flatten(item, f"{path}[{i}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            yield from _flatten(item, f"{path}.{key}")


def validate(data):
    problems = []
    for key in REQUIRED:
        if key not in data:
            problems.append(f"missing key: {key}")
    if data.get("schema") != "krea2-outfit/1":
        problems.append("schema must be krea2-outfit/1")
    for path, text in english_strings(data):
        if HANGUL.search(text):
            problems.append(f"Hangul in English field {path}: {text[:40]}")
        if NEGATION.search(text):
            problems.append(f"negation in English field {path}: {text[:60]}")
    for lock in data.get("locks", []):
        variants = lock.get("en", [])
        if not isinstance(variants, list) or len(variants) < 2:
            problems.append(f"lock {lock.get('id')} needs at least 2 English wordings")
    return problems


def render(data, detailed):
    c, m, parts = data["color"], data["material"], data["parts"]
    top, bottom = parts["top"], parts["bottom"]
    sig = ", ".join(a["en"] for a in data.get("accessories", {}).get("signature", []))
    if not detailed:
        return (f"wearing {top['en']} and {bottom['en']} in {c['primary']['en']} {m['en']} with {m['finish_en']}"
                + (f", plus {sig}" if sig else "") + ".")
    lines = [f"She wears {data['name_en']}, made of {m['en']} in {c['primary']['en']} with {m['finish_en']}."]
    lines.append(f"The top is {top['en']}: " + "; ".join(top["detail_en"]) + ".")
    lines.append(f"The bottom is {bottom['en']}: " + "; ".join(bottom["detail_en"]) + ".")
    lines.append(m["behavior_en"][0].upper() + m["behavior_en"][1:] + ". " + c["shade_en"][0].upper() + c["shade_en"][1:] + ".")
    for acc in data.get("accessories", {}).get("signature", []):
        lines.append(f"Around the neck: {acc['en']}; {acc['detail_en']}.")
    return " ".join(lines)


def main():
    preview = "--preview" in sys.argv
    files = sorted(OUTFIT_DIR.glob("*.json"))
    bad = 0
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        problems = validate(data)
        print(f"{'OK  ' if not problems else 'FAIL'} {path.name}")
        for p in problems:
            print("   -", p)
        bad += bool(problems)
        if preview and not problems:
            print("\n[보통]\n" + render(data, False) + "\n\n[상세]\n" + render(data, True) + "\n")
    print(f"{len(files)} file(s), {bad} with problems")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
