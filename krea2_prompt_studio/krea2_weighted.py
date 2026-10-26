"""Weighted-phrase view of a composed prompt, for the chain node `Krea2 text encode - attention-weighted phrases`.

compose_split() returns the prompt in named sections (identity / outfit / action / setting / camera / light / skin / style).
This module only re-wraps those sections as `(sentence:1.6).` groups. The text is never rewritten, except that a colon inside
a wrapped group becomes a comma (a colon would be read as the start of the weight) and that the long skin sentence can be
swapped for the short one the chain uses.

The default weights follow the prompts the owner uses (2026-10): outfit 1.6, action 1.5, setting 1.4, camera 2.5, light 1.7,
skin 1.3; identity and style are left unweighted. A weight of None or 1 leaves a section without brackets.
"""
from typing import Dict, Optional

ORDER = ("identity", "hair", "outfit", "accessory", "engraving", "action", "setting", "camera", "light", "skin", "style")
DEFAULT_WEIGHTS: Dict[str, Optional[float]] = {
    "identity": None, "hair": 1.7, "outfit": 1.6, "accessory": None, "engraving": 1.5, "action": 1.5, "setting": 1.4,
    "camera": 2.5, "light": 1.7, "skin": 1.3, "style": None,
}
SHORT_SKIN = "Natural matte skin texture"
FULL_BODY_FRAME = ("A full-length photograph from eye level, the frame running from a small gap of clear space above the top of her head "
                   "down to a small gap of clear ground below her feet, her whole body standing in the center of the frame so that her figure "
                   "takes up about three quarters of the frame height, her head near the upper quarter of the frame, a wide vertical frame")


def _num(w) -> str:
    return f"{float(w):g}"


def wrap(text: str, weight) -> str:
    """'(text:1.6).' for a weighted section, plain text otherwise."""
    text = " ".join((text or "").split())
    if not text:
        return ""
    if weight in (None, "", 0, 1, 1.0):
        return text if text.endswith((".", "!", "?")) else text + "."
    inner = text.rstrip(".!? ").replace(":", ",")
    return f"({inner}:{_num(weight)})."


def weighted_prompt(sections: Dict[str, str], weights: Optional[Dict[str, Optional[float]]] = None,
                    lighting_tag: bool = True, lighting_weight: float = 1.1, short_skin: bool = True,
                    extra_camera: str = "") -> str:
    w = dict(DEFAULT_WEIGHTS)
    w.update({k: v for k, v in (weights or {}).items() if k in ORDER})
    sec = dict(sections)
    if short_skin and sec.get("skin"):
        sec["skin"] = SHORT_SKIN
    if extra_camera.strip():
        rest = sec.get("camera", "").rstrip(".")
        rest = rest[:1].lower() + rest[1:] if rest else rest
        sec["camera"] = (extra_camera.strip().rstrip(".") + (", " + rest if rest else ""))
    head = f"(Lighting:{_num(lighting_weight)}). " if lighting_tag else ""
    paragraphs = []
    ident = wrap(sec.get("identity", ""), w["identity"])
    paragraphs.append(head + ident)
    for key in ORDER[1:]:
        if key in ("skin", "style"):
            continue
        piece = wrap(sec.get(key, ""), w[key])
        if piece:
            paragraphs.append(piece)
    tail = " ".join(x for x in (wrap(sec.get("skin", ""), w["skin"]), wrap(sec.get("style", ""), w["style"])) if x)
    if tail:
        paragraphs.append(tail)
    return "\n\n".join(paragraphs)
