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


def main() -> int:
    seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 300
    problems = []
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
