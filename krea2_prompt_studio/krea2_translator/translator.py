#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Krea2 Prompt Studio embedded Korean -> English translation engine.

The translator is intentionally local and deterministic.  It does not call
an external service.  Vocabulary is loaded from separate JSON files so the
translator can be updated without replacing the main prompt-studio program.

Translation stages:
    1. protect explicit quoted text and LoRA-like identifiers
    2. phrase-first glossary replacement
    3. domain dictionary replacement
    4. small Korean grammar/pattern conversions
    5. Krea2 phrase normalization
    6. restore protected text

This module is a component, not the scene resolver.  It should not invent
scene facts, alter left/right semantics, or change user-fixed values.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from threading import RLock
from typing import Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

TRANSLATOR_VERSION = "1.0.0"
MODULE_DIR = Path(__file__).resolve().parent
DATA_DIR = MODULE_DIR / "data"
USER_DATA_DIR = MODULE_DIR.parent / "krea2_prompt_configs"
USER_DICTIONARY_FILE = USER_DATA_DIR / "user_dictionary.json"


def _clean(value: str) -> str:
    value = re.sub(r"\s+", " ", value or "").strip()
    value = re.sub(r"\s+([,.!?;:])", r"\1", value)
    return value


def _load_json(name: str, default):
    path = DATA_DIR / name
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data
    except (OSError, ValueError, TypeError):
        return default


def _load_user_dictionary() -> Dict[str, str]:
    try:
        data = json.loads(USER_DICTIONARY_FILE.read_text(encoding="utf-8"))
        return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}
    except (OSError, ValueError, TypeError):
        return {}


@dataclass
class TranslatorStats:
    user_terms: int = 0
    core_terms: int = 0
    domain_terms: int = 0
    pattern_rules: int = 0
    protected_items: int = 0
    replacements: int = 0


@dataclass
class EmbeddedTranslator:
    """Deterministic local translator with updateable vocabulary."""

    core: Dict[str, str] = field(default_factory=dict)
    domains: Dict[str, Dict[str, str]] = field(default_factory=dict)
    patterns: List[Tuple[str, str]] = field(default_factory=list)
    normalization: List[Tuple[str, str]] = field(default_factory=list)
    user_dictionary_path: Path = USER_DICTIONARY_FILE
    _lock: RLock = field(default_factory=RLock, init=False, repr=False)

    def __post_init__(self) -> None:
        self.reload()

    def reload(self) -> None:
        with self._lock:
            self.core = dict(_load_json("core_ko_en.json", {}))
            self.domains = {
                str(category): {str(k): str(v) for k, v in values.items()}
                for category, values in _load_json("domains_ko_en.json", {}).items()
                if isinstance(values, dict)
            }
            self.patterns = [
                (str(item["pattern"]), str(item["replacement"]))
                for item in _load_json("patterns.json", [])
                if isinstance(item, dict) and "pattern" in item and "replacement" in item
            ]
            self.normalization = [
                (str(item["pattern"]), str(item["replacement"]))
                for item in _load_json("normalization.json", [])
                if isinstance(item, dict) and "pattern" in item and "replacement" in item
            ]
            self._user = _load_user_dictionary()

    @property
    def user_dictionary(self) -> Dict[str, str]:
        with self._lock:
            return dict(self._user)

    def add(self, korean: str, english: str) -> None:
        korean = _clean(korean)
        english = _clean(english)
        if not korean or not english:
            raise ValueError("한국어 표현과 영어 표현을 모두 입력해야 합니다.")
        self.user_dictionary_path.parent.mkdir(parents=True, exist_ok=True)
        data = self.user_dictionary
        data[korean] = english
        self.user_dictionary_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        with self._lock:
            self._user = data

    def remove(self, korean: str) -> bool:
        korean = _clean(korean)
        data = self.user_dictionary
        existed = korean in data
        data.pop(korean, None)
        self.user_dictionary_path.parent.mkdir(parents=True, exist_ok=True)
        self.user_dictionary_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        with self._lock:
            self._user = data
        return existed

    def list_user(self) -> Dict[str, str]:
        return self.user_dictionary

    @staticmethod
    def _protect(text: str) -> Tuple[str, Dict[str, str]]:
        protected: Dict[str, str] = {}
        counter = 0

        def stash(value: str) -> str:
            nonlocal counter
            key = f"__KREA_PROTECTED_{counter}__"
            protected[key] = value
            counter += 1
            return key

        # Exact quotes should be preserved (especially captions and signs).
        text = re.sub(r'"[^"\n]*"|“[^”\n]*”|‘[^’\n]*’', lambda m: stash(m.group(0)), text)
        # LoRA triggers / technical identifiers should never be translated.
        text = re.sub(r"(?<![가-힣A-Za-z0-9_])(?:[A-Za-z][A-Za-z0-9_\-]{2,})(?![가-힣A-Za-z0-9_])", lambda m: stash(m.group(0)), text)
        return text, protected

    @staticmethod
    def _restore(text: str, protected: Mapping[str, str]) -> str:
        for key, value in protected.items():
            text = text.replace(key, value)
        return text

    @staticmethod
    def _replace_phrases(text: str, pairs: Iterable[Tuple[str, str]], stats: TranslatorStats) -> str:
        # Longest phrase first avoids partial replacement, e.g. "한국인 여성" before "여성".
        ordered = sorted(((str(k), str(v)) for k, v in pairs if str(k)), key=lambda x: len(x[0]), reverse=True)
        for korean, english in ordered:
            if korean in text:
                count = text.count(korean)
                text = text.replace(korean, english)
                stats.replacements += count
        return text

    def translate(self, text: str, *, include_domain: bool = True, normalize: bool = True) -> str:
        text = _clean(text)
        if not text:
            return ""

        with self._lock:
            stats = TranslatorStats(
                user_terms=len(self._user),
                core_terms=len(self.core),
                domain_terms=sum(len(v) for v in self.domains.values()),
                pattern_rules=len(self.patterns),
            )
            work, protected = self._protect(text)
            stats.protected_items = len(protected)

            # Sentence-level patterns run first so particles/endings such as
            # "연인이 ... 걷는다" can be resolved before single-word mappings.
            for pattern, replacement in self.patterns:
                new_work, count = re.subn(pattern, replacement, work, flags=re.IGNORECASE)
                if count:
                    stats.replacements += count
                work = new_work

            # User overrides have highest priority among dictionaries.
            work = self._replace_phrases(work, self._user.items(), stats)
            work = self._replace_phrases(work, self.core.items(), stats)

            if include_domain:
                all_domain_pairs: List[Tuple[str, str]] = []
                for pairs in self.domains.values():
                    all_domain_pairs.extend(pairs.items())
                work = self._replace_phrases(work, all_domain_pairs, stats)

            if normalize:
                for pattern, replacement in self.normalization:
                    work = re.sub(pattern, replacement, work, flags=re.IGNORECASE)

            work = self._restore(work, protected)
            work = _clean(work)
            return work

    def stats(self) -> TranslatorStats:
        return TranslatorStats(
            user_terms=len(self._user),
            core_terms=len(self.core),
            domain_terms=sum(len(v) for v in self.domains.values()),
            pattern_rules=len(self.patterns),
        )


_INSTANCE: Optional[EmbeddedTranslator] = None
_INSTANCE_LOCK = RLock()


def get_translator() -> EmbeddedTranslator:
    global _INSTANCE
    with _INSTANCE_LOCK:
        if _INSTANCE is None:
            _INSTANCE = EmbeddedTranslator()
        return _INSTANCE


def translate_text(text: str, **kwargs) -> str:
    return get_translator().translate(text, **kwargs)


def add_user_translation(korean: str, english: str) -> None:
    get_translator().add(korean, english)


def remove_user_translation(korean: str) -> bool:
    return get_translator().remove(korean)


def list_user_translations() -> Dict[str, str]:
    return get_translator().list_user()


def translator_self_test() -> List[Tuple[str, bool, str]]:
    t = get_translator()
    tests = [
        ("한국인 여성", "adult Korean woman"),
        ("아늑한 카페", "cozy cafe"),
        ("연인이 손을 잡고 걷는다", "the couple hold hands and walk"),
        ("하늘색 오간자 블라우스", "sky-blue organza blouse"),
        ("창문으로 들어오는 자연광", "natural light coming through the window"),
        ("정면에서 바라본 전신 구도", "full-body composition viewed from the front"),
    ]
    out: List[Tuple[str, bool, str]] = []
    for src, expected_fragment in tests:
        got = t.translate(src)
        out.append((src, expected_fragment.lower() in got.lower(), got))
    return out


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Krea2 offline Korean-English translator")
    parser.add_argument("--self-test", action="store_true", help="run built-in translation checks")
    parser.add_argument("--stats", action="store_true", help="show loaded dictionary statistics")
    parser.add_argument("text", nargs="*", help="Korean text to translate")
    args = parser.parse_args()
    translator = get_translator()
    print(f"Krea2 Embedded Translator {TRANSLATOR_VERSION}")
    if args.stats:
        print(translator.stats())
    if args.self_test or not args.text:
        for src, ok, got in translator_self_test():
            print(f"{'OK' if ok else 'FAIL'} | {src} -> {got}")
    else:
        print(translator.translate(" ".join(args.text)))
