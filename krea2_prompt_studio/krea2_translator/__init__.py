"""Embedded Korean -> English translator for Krea2 Prompt Studio."""
from .translator import (
    TRANSLATOR_VERSION,
    EmbeddedTranslator,
    get_translator,
    translate_text,
    add_user_translation,
    remove_user_translation,
    list_user_translations,
    translator_self_test,
)

__all__ = [
    "TRANSLATOR_VERSION",
    "EmbeddedTranslator",
    "get_translator",
    "translate_text",
    "add_user_translation",
    "remove_user_translation",
    "list_user_translations",
    "translator_self_test",
]
