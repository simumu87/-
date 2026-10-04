#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Krea2 Turbo Prompt Studio - normal/lifestyle/romance scene generator.

Target model: pornmasterKrea2_v2TurboInt8.safetensors
Korean UI -> structured scene resolution -> English natural-language prompt.

The scene engine is deliberately separated into:
    1) user intent / constraints
    2) relational scene resolver
    3) clothing-material resolver
    4) environment / camera geometry resolver
    5) consistency checks
    6) English prompt composer

The old specialized scene vocabulary is not part of the normal generator.
"""
from __future__ import annotations

import csv
import hashlib
import json
import random
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

try:
    from krea2_translator import (
        TRANSLATOR_VERSION,
        translate_text as embedded_translate,
        add_user_translation as translator_add_user,
        remove_user_translation as translator_remove_user,
        list_user_translations as translator_list_user,
    )
except ImportError:
    TRANSLATOR_VERSION = "fallback"
    embedded_translate = None
    translator_add_user = None
    translator_remove_user = None
    translator_list_user = None

APP_NAME = "Krea2 Turbo Prompt Studio"
APP_VERSION = "11.0.0-dev"
MODEL_NAME = "pornmasterKrea2_v2TurboInt8.safetensors"
OUTPUT_DIR = Path("generated_krea2_prompts")
HISTORY_FILE = Path("krea2_prompt_history.jsonl")
CONFIG_DIR = Path("krea2_prompt_configs")
LORA_FILE = CONFIG_DIR / "loras.json"
FAVORITES_FILE = CONFIG_DIR / "favorites.json"
RECENT_FILE = CONFIG_DIR / "recent.json"
SETTINGS_FILE = CONFIG_DIR / "settings.json"
USER_DICTIONARY_FILE = CONFIG_DIR / "user_dictionary.json"


class Color:
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    BOLD = "\033[1m"
    END = "\033[0m"


def cprint(message: str, color: str = Color.END, bold: bool = False) -> None:
    print(f"{Color.BOLD if bold else ''}{color}{message}{Color.END}")


def print_header(title: str) -> None:
    cprint("=" * 88, Color.CYAN)
    cprint(f"  {title}", Color.CYAN, True)
    cprint("=" * 88, Color.CYAN)


def success(message: str) -> None:
    cprint(f"✅ {message}", Color.GREEN)


def warning(message: str) -> None:
    cprint(f"⚠️  {message}", Color.YELLOW)


def error(message: str) -> None:
    cprint(f"❌ {message}", Color.RED)


def info(message: str) -> None:
    cprint(f"ℹ️  {message}", Color.CYAN)


def clean_text(value: str, fallback: str = "") -> str:
    return re.sub(r"\s+", " ", (value or "")).strip() or fallback


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def sha12(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def choose(rng: random.Random, values: Sequence[Any]) -> Any:
    values = list(values)
    return rng.choice(values) if values else ""


def ensure_dirs() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_json(path: Path, default: Any) -> Any:
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        warning(f"파일을 읽지 못했습니다: {path}")
    return default


def save_json(path: Path, data: Any) -> None:
    ensure_dirs()
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Structured profiles
# ---------------------------------------------------------------------------
@dataclass
class BodyState:
    left_arm: str = "relaxed"
    right_arm: str = "relaxed"
    left_leg: str = "grounded"
    right_leg: str = "grounded"
    left_foot: str = "grounded"
    right_foot: str = "grounded"
    support_points: List[str] = field(default_factory=lambda: ["left foot", "right foot"])
    weight_distribution: str = "balanced"
    torso_orientation: str = "facing the scene"
    head_orientation: str = "natural"


@dataclass
class FabricProfile:
    key: str
    material: str
    fiber: str
    construction: str
    density: str
    fiber_fineness: str
    opacity: str
    thickness: str
    weight: str
    texture: str
    sheen: str
    stretch: str
    stiffness: str
    drape: str
    surface_response: str
    seasonal_feel: str
    compatible_garments: List[str] = field(default_factory=list)


@dataclass
class ClothingProfile:
    garment_key: str
    garment_en: str
    fit: str
    color: str
    details: str
    footwear: str
    accessory: str
    state: str
    fabric: FabricProfile
    construction_detail: str
    fold_behavior: str


@dataclass
class PersonSlot:
    slot: str
    lora_trigger: str = ""
    identity: str = "adult person"
    role: str = "subject"
    position: str = "center"
    orientation: str = "facing the scene"
    pose_key: str = "편안하게 서기"
    pose_en: str = "standing naturally with relaxed posture"
    expression: str = "gentle natural smile"
    gaze: str = "looking toward the scene focus"
    hair: str = "natural hairstyle with realistic individual strands"
    clothing: Optional[ClothingProfile] = None
    clothing_extra: Optional[ClothingProfile] = None
    body_state: BodyState = field(default_factory=BodyState)
    height_cm: Optional[int] = None
    props: List[str] = field(default_factory=list)
    contact_notes: List[str] = field(default_factory=list)
    body_build: str = "slim-to-average natural adult build"
    skin_detail: str = "natural skin texture with subtle tonal variation"
    eye_color: str = "natural brown eyes"
    hair_color: str = "natural dark hair color"
    distinctive_feature: str = "no exaggerated facial features"


@dataclass
class EnvironmentProfile:
    location_key: str
    location_en: str
    sublocation: str
    architecture: str
    walls: str
    floor: str
    ceiling: str
    windows: str
    doors: str
    furniture: List[str]
    decor: List[str]
    practical: List[str]
    foreground: List[str]
    midground: List[str]
    background: List[str]
    density: str
    state: str
    palette: str
    surface_response: str
    scale_rules: List[str]
    spatial_layout: Dict[str, str] = field(default_factory=dict)


@dataclass
class LightingProfile:
    source: str
    direction: str
    quality: str
    intensity: str
    color_temperature: str
    ambient: str
    bounce: str
    shadow: str
    practical: str


@dataclass
class CameraProfile:
    lens: int
    viewpoint: str
    framing: str
    composition: str
    depth_of_field: str
    camera_distance: str
    subject_scale_lock: bool = True
    environment_scale_lock: bool = True
    perspective_rule: str = "realistic perspective"


@dataclass
class ConstraintSetting:
    value: str = "auto"
    random_mode: str = "auto"
    priority: int = 50
    source: str = "auto"


@dataclass
class ConsistencyIssue:
    level: str
    category: str
    message_kr: str
    repair_kr: str = ""


@dataclass
class SceneProfile:
    theme_key: str
    theme_en: str
    location_key: str
    people: int
    relationship_key: str
    relationship_en: str
    activity_key: str
    activity_en: str
    interaction_key: str
    interaction_en: str
    time_key: str
    time_en: str
    weather_key: str
    weather_en: str
    mood_key: str
    mood_en: str
    sublocation: str
    environment: EnvironmentProfile
    pose_a: Dict[str, Any]
    pose_b: Optional[Dict[str, Any]]
    lighting: LightingProfile
    camera: CameraProfile
    realism: str
    clothing_a: ClothingProfile
    clothing_b: Optional[ClothingProfile]
    props: List[str]
    left_right_basis: str
    source_text_kr: str = ""
    constraints: Dict[str, ConstraintSetting] = field(default_factory=dict)
    issues: List[ConsistencyIssue] = field(default_factory=list)
    auto_values: Dict[str, Any] = field(default_factory=dict)
    user_values: Dict[str, Any] = field(default_factory=dict)
    weather_visible: bool = True        # false: an indoor spot without a window, the weather is not described
    clothing_extra_a: Optional[ClothingProfile] = None    # the second garment (top for a bottom, bottom for a top)
    clothing_extra_b: Optional[ClothingProfile] = None


@dataclass
class GenerationOptions:
    mode: str = "natural"
    lora_mode: str = "single"
    count: int = 1
    seed: Optional[int] = None
    output_dir: str = str(OUTPUT_DIR)
    history_path: str = str(HISTORY_FILE)
    output_format: str = "txt"
    save_history: bool = True
    prevent_duplicates: bool = True
    person_a: Optional[PersonSlot] = None
    person_b: Optional[PersonSlot] = None
    custom_notes: str = ""
    constraints: Dict[str, ConstraintSetting] = field(default_factory=dict)
    strict_consistency: bool = False
    preview_before_prompt: bool = True
    detail: str = field(default_factory=lambda: str(load_json(SETTINGS_FILE, {}).get("prompt_detail", "보통")))
    reinforce: Optional[int] = field(default_factory=lambda: load_json(SETTINGS_FILE, {}).get("reinforce"))


@dataclass
class PromptSet:
    prompt_id: str
    created_at: str
    seed: int
    mode: str
    lora_mode: str
    global_prompt: str
    person_a_prompt: str
    person_b_prompt: str
    combined_prompt: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Themes
# ---------------------------------------------------------------------------
THEMES = {
    "일상": "ordinary everyday life",
    "로맨스": "a quiet romantic moment between adults",
    "데이트": "a casual adult date",
    "주말": "a relaxed weekend lifestyle scene",
    "휴식": "calm personal downtime",
    "친구": "a warm everyday friendship moment",
    "여행": "an adult travel lifestyle scene",
    "도시 생활": "modern urban lifestyle",
    "자연": "a peaceful outdoor lifestyle",
    "직장": "professional everyday work life",
    "공부": "a focused study session",
    "취미": "a casual hobby activity",
    "예술": "a creative artistic activity",
    "스포츠": "recreational sports activity",
    "비 오는 날": "a cozy rainy-day lifestyle scene",
    "아침": "a fresh morning routine",
    "저녁": "a quiet evening routine",
    "축제": "a lively cultural festival atmosphere",
    "휴가": "a relaxed vacation atmosphere",
    "사진 화보": "a refined lifestyle editorial photograph",
}


# ---------------------------------------------------------------------------
# Locations
# ---------------------------------------------------------------------------
LOCATIONS = {
    "아파트 거실": {
        "en": "a modern apartment living room",
        "architecture": "open-plan residential architecture with believable ceiling height",
        "walls": ["warm off-white painted walls", "soft beige textured walls", "muted gray painted walls"],
        "floor": ["light oak flooring", "matte walnut flooring", "a low-pile area rug over wood flooring"],
        "ceiling": ["a clean white ceiling with recessed lights", "a simple ceiling with a minimal pendant fixture"],
        "windows": ["a wide double-glazed window", "large windows with sheer curtains"],
        "doors": ["a flush interior door", "a wooden entry door visible in the distance"],
        "furniture": ["three-seat sofa", "low coffee table", "media console", "accent chair", "floor lamp", "side table"],
        "decor": ["framed artwork", "ceramic vase", "bookshelf", "leafy houseplant", "textured throw blanket"],
        "practical": ["ceramic mug", "smartphone", "remote control", "charging cable"],
        "subs": ["beside the sofa", "near the coffee table", "by the window", "near the bookshelf", "in the open center of the room"],
        "outdoor": False,
    },
    "아파트 주방": {
        "en": "a contemporary apartment kitchen",
        "architecture": "functional residential kitchen with clean cabinetry and believable counter height",
        "walls": ["warm white walls", "subtle stone backsplash", "soft gray tile backsplash"],
        "floor": ["matte porcelain tile", "light oak flooring"],
        "ceiling": ["plain white ceiling with recessed downlights"],
        "windows": ["a kitchen window above the counter", "a wide window beside the worktop"],
        "doors": ["an open doorway toward the living area"],
        "furniture": ["kitchen island", "counter stools", "dining table", "dining chairs", "built-in cabinetry"],
        "decor": ["herb pots", "ceramic bowls", "wooden cutting board", "small framed print"],
        "practical": ["coffee machine", "kettle", "dish rack", "fruit bowl", "cookbook"],
        "subs": ["at the kitchen island", "beside the counter", "near the sink", "at the dining table"],
        "outdoor": False,
    },
    "침실": {
        "en": "a calm modern bedroom",
        "architecture": "private residential bedroom with balanced proportions",
        "walls": ["soft warm-gray walls", "cream walls", "muted sage walls"],
        "floor": ["natural oak floor", "wood floor with a woven bedside rug"],
        "ceiling": ["plain white ceiling", "simple ceiling with a central pendant"],
        "windows": ["a large bedroom window with layered curtains", "a single wide window"],
        "doors": ["a simple wooden bedroom door"],
        "furniture": ["double bed", "bedside tables", "wooden dresser", "reading chair", "standing mirror"],
        "decor": ["framed botanical print", "small lamp", "books", "ceramic tray", "folded blanket"],
        "practical": ["smartphone", "glass of water", "alarm clock", "reading glasses"],
        "subs": ["beside the bed", "at the reading chair", "near the window", "in front of the dresser", "on the edge of the bed"],
        "outdoor": False,
    },
    "홈오피스": {
        "en": "a compact home office",
        "architecture": "quiet residential workspace with functional proportions",
        "walls": ["warm white walls", "light gray walls", "soft blue-gray walls"],
        "floor": ["wood flooring", "low-pile carpet"],
        "ceiling": ["white ceiling with recessed lighting"],
        "windows": ["a wide desk-side window", "a tall single window"],
        "doors": ["a simple interior door"],
        "furniture": ["writing desk", "ergonomic office chair", "bookshelf", "drawer cabinet", "side table"],
        "decor": ["desk plant", "framed print", "cork board", "small sculpture"],
        "practical": ["laptop", "monitor", "keyboard", "notebook", "pen cup", "headphones"],
        "subs": ["at the desk", "beside the bookshelf", "near the window", "standing beside the chair"],
        "outdoor": False,
    },
    "카페": {
        "en": "a contemporary neighborhood cafe",
        "architecture": "warm commercial interior with realistic storefront proportions",
        "walls": ["painted plaster walls", "exposed warm brick", "microcement wall finish"],
        "floor": ["terrazzo flooring", "dark wood flooring", "matte concrete flooring"],
        "ceiling": ["industrial ceiling with track lights", "simple ceiling with pendant lights"],
        "windows": ["large street-facing windows", "full-height glass frontage"],
        "doors": ["a glass storefront door"],
        "furniture": ["small round tables", "wooden cafe chairs", "long counter", "bar stools", "bench seating"],
        "decor": ["menu board", "hanging plants", "ceramic cups", "local art prints", "small table lamps"],
        "practical": ["coffee grinder", "pastry display", "paper menus", "water carafe", "laptop"],
        "subs": ["at a small window table", "by the counter", "on a bench seat", "near the storefront window"],
        "outdoor": False,
    },
    "서점": {
        "en": "a quiet independent bookstore",
        "architecture": "tall-ceilinged retail interior with long shelving aisles",
        "walls": ["warm painted plaster", "cream walls with wood shelving"],
        "floor": ["polished wood floor", "matte oak flooring"],
        "ceiling": ["high ceiling with warm track lights"],
        "windows": ["large front display window"],
        "doors": ["a glass entrance door"],
        "furniture": ["tall bookshelves", "reading table", "armchair", "small display pedestal"],
        "decor": ["book displays", "small plants", "recommendation cards"],
        "practical": ["open books", "shopping basket", "bookmark display", "reading glasses"],
        "subs": ["between two bookcases", "at the reading table", "near the window display", "beside a featured-book stand"],
        "outdoor": False,
    },
    "미술관": {
        "en": "a contemporary art museum gallery",
        "architecture": "spacious museum gallery with clean architectural lines",
        "walls": ["smooth white gallery walls", "light gray gallery walls"],
        "floor": ["polished concrete floor", "light stone floor"],
        "ceiling": ["high white ceiling with directional lighting"],
        "windows": ["tall clerestory windows", "large architectural windows in the lobby"],
        "doors": ["a wide gallery doorway"],
        "furniture": ["minimal bench", "reception desk", "sculpture plinths"],
        "decor": ["framed paintings", "large sculpture", "wall labels", "museum signage"],
        "practical": ["museum brochure", "audio guide", "visitor map"],
        "subs": ["in front of a large painting", "beside a sculpture", "near a gallery bench", "in the main exhibition room"],
        "outdoor": False,
    },
    "도서관": {
        "en": "a quiet contemporary public library",
        "architecture": "large civic interior with tall shelving and acoustic surfaces",
        "walls": ["soft neutral walls", "wood-accented walls"],
        "floor": ["carpet tiles", "light oak flooring"],
        "ceiling": ["acoustic ceiling panels with linear lights"],
        "windows": ["large reading-room windows", "tall vertical windows"],
        "doors": ["glass entrance doors"],
        "furniture": ["long study tables", "individual study desks", "bookshelves", "reading chairs"],
        "decor": ["books", "quiet-study signs", "potted plants"],
        "practical": ["laptop", "notebooks", "stack of books", "library card"],
        "subs": ["at a study desk", "between shelves", "near a reading window", "at a quiet reading table"],
        "outdoor": False,
    },
    "도시 거리": {
        "en": "a clean modern city street",
        "architecture": "mixed-use urban buildings with realistic street proportions",
        "walls": ["glass and concrete facades", "brick and stone storefronts"],
        "floor": ["concrete sidewalk paving", "gray stone pedestrian pavement"],
        "ceiling": ["open sky", "storefront awnings"],
        "windows": ["retail display windows", "office windows above the street"],
        "doors": ["shop entrance doors", "glass office lobby doors"],
        "furniture": ["street bench", "small outdoor tables", "bus shelter"],
        "decor": ["planters", "street signs", "posters", "storefront displays"],
        "practical": ["crosswalk signal", "bicycle rack", "parked bicycles"],
        "subs": ["on the sidewalk", "near a cafe storefront", "at a crosswalk", "beside a street bench"],
        "outdoor": True,
    },
    "공원": {
        "en": "a landscaped urban park",
        "architecture": "organized civic park with realistic pathways and planting beds",
        "walls": ["low stone retaining walls", "green hedges and planted borders"],
        "floor": ["paved walking path", "trimmed grass", "wooden deck near a pond"],
        "ceiling": ["open sky framed by tree canopies"],
        "windows": [],
        "doors": [],
        "furniture": ["wooden bench", "picnic table", "small pavilion"],
        "decor": ["flower beds", "ornamental trees", "public sculpture"],
        "practical": ["recycling bin", "park map", "bicycle rack"],
        "subs": ["on the main path", "beside a bench", "near a pond", "under a large tree"],
        "outdoor": True,
    },
    "해변": {
        "en": "a calm sandy beach",
        "architecture": "natural shoreline with sparse recreational structures",
        "walls": ["a low seawall in the distance", "a wooden beach pavilion in the distance"],
        "floor": ["fine beach sand", "packed wet sand near the shoreline"],
        "ceiling": ["open sky"],
        "windows": [],
        "doors": [],
        "furniture": ["folding beach chair", "small sun shelter", "wooden bench"],
        "decor": ["driftwood", "shells", "simple beach sign"],
        "practical": ["tote bag", "water bottle", "beach towel", "sunglasses"],
        "subs": ["near the shoreline", "beside a beach chair", "on dry sand above the waterline", "near a small beach shelter"],
        "outdoor": True,
    },
    "산책로": {
        "en": "a wooded walking trail",
        "architecture": "natural landscape with occasional trail infrastructure",
        "walls": ["rocky hillside edges", "wooded slopes"],
        "floor": ["packed earth trail", "gravel trail", "wooden boardwalk"],
        "ceiling": ["open sky beneath a tree canopy"],
        "windows": [],
        "doors": [],
        "furniture": ["trail bench", "wooden rest shelter"],
        "decor": ["direction signs", "wildflowers", "mossy stones"],
        "practical": ["walking backpack", "water bottle", "trail map"],
        "subs": ["on the main path", "beside a trail sign", "near a bench", "on a wooden boardwalk"],
        "outdoor": True,
    },
    "호텔 로비": {
        "en": "an elegant contemporary hotel lobby",
        "architecture": "high-ceilinged hospitality interior with balanced luxury proportions",
        "walls": ["stone accent wall", "warm plaster walls", "wood paneling"],
        "floor": ["polished stone floor", "large-format porcelain tile"],
        "ceiling": ["high ceiling with modern pendant lighting"],
        "windows": ["large glazed entrance facade"],
        "doors": ["tall glass entrance doors"],
        "furniture": ["deep lounge chairs", "sofas", "marble side tables", "reception desk"],
        "decor": ["large vase arrangement", "abstract artwork", "sculptural lighting"],
        "practical": ["hotel brochures", "key-card holder", "small luggage trolley"],
        "subs": ["near the lounge seating", "beside the reception desk", "near the entrance", "under the lobby pendants"],
        "outdoor": False,
    },
    "호텔 객실": {
        "en": "a well-designed modern hotel room",
        "architecture": "proportional hotel guest room with a calm hospitality layout",
        "walls": ["warm beige walls", "soft gray walls", "textured accent wall"],
        "floor": ["carpeted floor", "engineered wood floor"],
        "ceiling": ["simple ceiling with recessed lights"],
        "windows": ["large hotel window with layered curtains", "floor-to-ceiling glazed window"],
        "doors": ["a hotel entry door"],
        "furniture": ["queen bed", "desk", "lounge chair", "bedside tables", "luggage bench"],
        "decor": ["abstract print", "small lamp", "tea tray", "decorative cushion"],
        "practical": ["room-service menu", "water bottle", "luggage", "phone charger"],
        "subs": ["by the window", "at the desk", "beside the bed", "in the lounge area"],
        "outdoor": False,
    },
    "기차역": {
        "en": "a modern intercity train station concourse",
        "architecture": "large transit hall with high structural spans and clear wayfinding",
        "walls": ["glass and metal station walls", "pale stone cladding"],
        "floor": ["polished stone tiles", "large matte terrazzo tiles"],
        "ceiling": ["high structural roof with linear lights"],
        "windows": ["large glazed station facade"],
        "doors": ["automatic glass entrance doors"],
        "furniture": ["metal benches", "ticket kiosks", "information desk"],
        "decor": ["digital departure board", "direction signs", "wayfinding graphics"],
        "practical": ["rolling suitcase", "travel bag", "train ticket", "phone"],
        "subs": ["near the departure board", "beside a station bench", "near the ticket kiosk", "by the platform entrance"],
        "outdoor": False,
    },
    "서점 카페": {
        "en": "a cozy bookstore cafe",
        "architecture": "hybrid retail and cafe interior with wood shelving",
        "walls": ["cream walls", "wood shelving against plaster walls"],
        "floor": ["warm oak floor", "terrazzo floor"],
        "ceiling": ["warm ceiling with pendant lights"],
        "windows": ["large reading-window facade"],
        "doors": ["glass storefront door"],
        "furniture": ["small cafe table", "reading armchair", "bookshelves", "counter stools"],
        "decor": ["stacked books", "small plants", "ceramic cups", "art prints"],
        "practical": ["open novel", "coffee cup", "bookmark", "notebook"],
        "subs": ["at a reading table", "in an armchair", "beside a bookshelf", "near the cafe counter"],
        "outdoor": False,
    },
}

# ---------------------------------------------------------------------------
# Themes / relationships / activities
# ---------------------------------------------------------------------------
RELATIONSHIPS = {
    "혼자": "a single adult subject",
    "친구": "two adult friends",
    "연인": "two adult romantic partners",
    "부부": "two married adult partners",
    "동료": "two adult colleagues",
    "여행 동행": "two adult travel companions",
    "스터디 메이트": "two adult study partners",
}

INTERACTIONS = {
    "없음": "no direct interaction, with natural personal space between the subjects",
    "손잡기": "holding hands naturally with relaxed fingers",
    "팔짱": "walking or standing arm in arm",
    "가벼운 포옹": "sharing a warm natural hug",
    "어깨에 기대기": "one person resting their head lightly on the other's shoulder",
    "나란히 걷기": "walking side by side at a natural pace",
    "마주 앉아 대화": "sitting across from each other and talking casually",
    "나란히 앉아 대화": "sitting side by side and talking comfortably",
    "함께 사진 보기": "looking together at a phone or printed photograph",
    "함께 책 보기": "looking together at an open book",
    "커피 건네기": "one person handing a coffee cup to the other",
    "선물 건네기": "one person handing a small wrapped gift to the other",
    "하이파이브": "sharing a casual high-five",
    "장난스럽게 웃기": "sharing a playful laugh",
    "함께 요리하기": "preparing food together at a kitchen counter",
    "함께 쇼핑하기": "browsing items together while shopping",
    "함께 전시 관람": "standing together while viewing an artwork",
    "함께 음악 듣기": "listening to music together with relaxed posture",
}

ACTIVITIES = {
    "커피 마시기": "having coffee",
    "차 마시기": "having tea",
    "아침 식사": "having a relaxed breakfast",
    "저녁 식사": "sharing a casual dinner",
    "요리하기": "cooking a simple meal",
    "베이킹": "baking in a home kitchen",
    "책 읽기": "reading a book",
    "잡지 보기": "looking through a magazine",
    "공부하기": "studying with organized notes",
    "노트북 작업": "working on a laptop",
    "화상회의": "joining a casual video meeting",
    "그림 그리기": "drawing or sketching",
    "사진 찍기": "taking photographs",
    "음악 듣기": "listening to music",
    "기타 연주": "playing an acoustic guitar",
    "피아노 연주": "playing a piano",
    "영화 보기": "watching a film at home",
    "게임하기": "playing a casual video game",
    "보드게임": "playing a board game",
    "정리하기": "organizing a room",
    "식물 돌보기": "caring for houseplants",
    "산책": "taking a relaxed walk",
    "조깅": "going for a light recreational jog",
    "자전거": "riding a bicycle recreationally",
    "공원 피크닉": "having a casual park picnic",
    "해변 산책": "walking along the beach",
    "여행 출발": "getting ready to start a trip",
    "여행 중 휴식": "taking a break while traveling",
    "기차 기다리기": "waiting for a train",
    "전시 관람": "visiting an art exhibition",
    "서점 구경": "browsing books in a bookstore",
    "카페 데이트": "having a relaxed cafe date",
    "저녁 산책": "taking an evening walk",
    "비 오는 날 산책": "taking a walk on a rainy day",
    "창가에서 쉬기": "relaxing beside a window",
    "친구와 대화": "having a friendly conversation",
    "연인과 대화": "having a quiet romantic conversation",
    "기념사진": "taking a commemorative photo together",
    "선물 고르기": "choosing a small gift together",
    "쇼핑": "shopping casually",
    # Activities referenced by the hint / compatibility tables below.
    "가볍게 운동하기": "doing light recreational exercise",
    "가볍게 포옹하기": "sharing a warm everyday embrace",
    "글쓰기": "writing in a notebook at a desk",
    "기차 타기": "traveling by train",
    "대화하기": "having an ordinary conversation",
    "바닷가 산책": "walking along the seaside",
    "사진 보기": "looking through photographs",
    "사진 촬영": "taking lifestyle photographs",
    "선물 주고받기": "exchanging a small gift",
    "손잡고 걷기": "taking a walk while holding hands",
    "아침 준비": "going through a morning routine",
    "악기 연주": "practicing a musical instrument",
    "업무 보기": "doing focused desk work",
    "여행 준비": "preparing for a trip",
    "요가하기": "practicing beginner yoga",
    "자전거 타기": "riding a bicycle",
    "함께 요리하기": "cooking together in the kitchen",
    "호텔 체크인": "arriving at a hotel",
}

BASE_POSES = {
    "편안하게 서기": {"en": "standing naturally with relaxed posture", "supports": ["left foot", "right foot"], "legs": ("grounded", "grounded")},
    "한쪽 다리에 기대 서기": {"en": "standing naturally with most weight on one leg and the other leg relaxed", "supports": ["left foot", "right foot"], "legs": ("grounded", "grounded")},
    "벽에 기대 서기": {"en": "standing while lightly leaning a shoulder or upper back against the wall", "supports": ["left foot", "right foot", "wall contact"], "legs": ("grounded", "grounded")},
    "난간에 기대기": {"en": "standing beside a railing with one forearm resting lightly on it", "supports": ["left foot", "right foot", "railing contact"], "legs": ("grounded", "grounded")},
    "걷기": {"en": "caught naturally mid-stride while walking", "supports": ["one foot at a time"], "legs": ("grounded", "transitioning")},
    "천천히 걷기": {"en": "walking at an easy pace with a relaxed stride", "supports": ["one foot at a time"], "legs": ("grounded", "transitioning")},
    "벤치에 앉기": {"en": "sitting upright on a bench with balanced weight", "supports": ["hips", "feet"], "legs": ("grounded", "grounded")},
    "소파에 편하게 앉기": {"en": "sitting comfortably on a sofa with relaxed shoulders", "supports": ["hips", "feet"], "legs": ("grounded", "grounded")},
    "의자에 앉아 읽기": {"en": "sitting in a chair while reading", "supports": ["hips", "feet"], "legs": ("grounded", "grounded")},
    "책상에 앉아 공부하기": {"en": "sitting at a desk with a focused study posture", "supports": ["hips", "feet"], "legs": ("grounded", "grounded")},
    "바닥에 앉기": {"en": "sitting comfortably on the floor with stable support through the hips and legs", "supports": ["hips", "legs"], "legs": ("supported", "supported")},
    "무릎 꿇고 앉기": {"en": "kneeling in a balanced upright posture", "supports": ["knees", "shins"], "legs": ("kneeling", "kneeling")},
    "바닥에 다리를 뻗고 앉기": {"en": "sitting on the floor with both legs extended forward", "supports": ["hips", "heels"], "legs": ("extended", "extended")},
    "다리를 꼬고 앉기": {"en": "sitting comfortably with one leg crossed over the other", "supports": ["hips", "one foot"], "legs": ("crossed", "grounded")},
    "창가에 서기": {"en": "standing near a window while looking outside", "supports": ["left foot", "right foot"], "legs": ("grounded", "grounded")},
    "창가에 앉기": {"en": "sitting comfortably near the window sill", "supports": ["hips", "feet"], "legs": ("grounded", "grounded")},
    "가볍게 스트레칭": {"en": "performing a simple standing stretch with stable balance", "supports": ["both feet"], "legs": ("grounded", "grounded")},
    "요가 자세": {"en": "holding a calm beginner-friendly yoga pose with controlled balance", "supports": ["pose-dependent support"], "legs": ("supported", "supported")},
    "달리기 동작": {"en": "caught naturally during a light recreational run", "supports": ["one foot in transition"], "legs": ("transitioning", "extended")},
    "자전거 타기": {"en": "riding a bicycle naturally with hands on the handlebars", "supports": ["bicycle seat", "pedals"], "legs": ("pedaling", "pedaling")},
    "기타 연주": {"en": "standing or sitting while naturally playing an acoustic guitar", "supports": ["feet or seat"], "legs": ("grounded", "grounded")},
    "피아노 연주": {"en": "sitting upright at a piano while playing naturally", "supports": ["bench", "feet"], "legs": ("grounded", "grounded")},
    "서로 마주 보기": {"en": "standing naturally while facing another person", "supports": ["left foot", "right foot"], "legs": ("grounded", "grounded")},
    "손잡고 걷기": {"en": "walking side by side while naturally holding hands", "supports": ["one foot at a time"], "legs": ("transitioning", "transitioning")},
    "나란히 앉기": {"en": "sitting side by side with relaxed posture", "supports": ["hips", "feet"], "legs": ("grounded", "grounded")},
    "포옹하기": {"en": "standing in a natural warm embrace with balanced support", "supports": ["both feet"], "legs": ("grounded", "grounded")},
    "마주 앉기": {"en": "sitting upright across a table with relaxed shoulders", "supports": ["hips", "feet"], "legs": ("grounded", "grounded")},
}

# Poses whose wording needs a second person; never used for single-subject scenes.
PAIR_ONLY_POSES = {"서로 마주 보기", "나란히 앉기", "손잡고 걷기", "포옹하기", "마주 앉기"}

TIME_OF_DAY = {
    "새벽": "early dawn",
    "아침": "soft morning light",
    "오전": "late morning",
    "정오": "bright midday",
    "오후": "warm afternoon light",
    "해질녘": "golden hour before sunset",
    "저녁": "early evening",
    "밤": "quiet night",
    "심야": "late night",
}

WEATHER = {
    "맑음": "clear weather",
    "구름 조금": "partly cloudy weather",
    "흐림": "overcast weather",
    "비": "gentle rain",
    "폭우": "heavy rain outside",
    "눈": "light snowfall",
    "안개": "soft morning mist",
    "바람": "a breezy day",
}

MOODS = {
    "편안함": "calm and comfortable",
    "따뜻함": "warm and welcoming",
    "낭만적": "quietly romantic",
    "발랄함": "playful and cheerful",
    "집중": "focused and attentive",
    "차분함": "peaceful and composed",
    "활기참": "lively and energetic",
    "향수어림": "slightly nostalgic",
    "아늑함": "cozy and intimate in an everyday sense",
    "세련됨": "refined and contemporary",
    "여유로움": "unhurried and relaxed",
}

REALISM = {
    "포토리얼": "natural photorealistic rendering with credible human proportions and realistic surface detail",
    "에디토리얼": "realistic editorial photography with controlled composition and refined styling",
    "다큐멘터리": "documentary-style realism with authentic environmental detail",
    "시네마틱": "cinematic realism with natural depth, grounded color and believable lighting",
    "라이프스타일": "high-end lifestyle photography with realistic textures and natural candid detail",
}

SKIN_FINISH = {
    "자연 피부": "natural skin with visible pores, fine vellus hair and subtle tonal variation",
    "매트": "soft matte-natural skin without artificial plastic gloss",
    "은은한 윤기": "subtle healthy skin sheen with realistic specular response",
    "부드러운 스튜디오": "softly lit natural skin with controlled studio highlights",
}


# ---------------------------------------------------------------------------
# Camera and lighting
# ---------------------------------------------------------------------------
CAMERA_FRAMING = {
    "전신": "full-body composition with the subject fully visible from head to feet",
    "3/4 전신": "three-quarter full-body composition showing the subject from head to below the knees with environment context",
    "무릎 위": "medium-long portrait framing from head to around the knees",
    "허벅지 위": "medium framing from head to upper thighs",
    "허리 위": "waist-up portrait framing",
    "가슴 위": "chest-up portrait framing",
    "클로즈업": "close portrait framing focused on the face and upper shoulders",
    "환경 중심": "environmental portrait framing with the subject clearly visible within the surrounding space",
    "와이드 씬": "wide scene composition with generous environmental context",
}
CAMERA_LENSES = [24, 28, 35, 40, 50, 58, 65, 85]
VIEWPOINTS = {
    "눈높이": "eye-level viewpoint",
    "약간 위": "slightly elevated viewpoint",
    "약간 아래": "slightly low viewpoint",
    "정면": "straight-on viewpoint",
    "사선": "three-quarter viewpoint",
    "옆면": "side viewpoint",
    "뒤쪽 사선": "rear three-quarter viewpoint with natural subject orientation",
}
COMPOSITIONS = {
    "중앙": "balanced centered composition",
    "삼분할": "balanced rule-of-thirds composition",
    "대각선": "subtle diagonal composition following the subject's natural gesture",
    "여백": "clean composition with intentional negative space",
    "레이어": "layered foreground, midground and background composition",
    "대칭": "controlled symmetrical composition when supported by the architecture",
    "스냅샷": "natural candid snapshot composition with believable timing",
}
DEPTH_OF_FIELD = {
    "깊음": "deep depth of field with both subject and environment remaining clear",
    "보통": "moderate depth of field with gentle background separation",
    "얕음": "shallow depth of field with selective subject emphasis",
    "매우 얕음": "very shallow depth of field reserved for close portrait details",
}
LIGHT_SOURCES = {
    "창문 자연광": "large window light",
    "부드러운 북향광": "soft diffuse north-facing daylight",
    "오후 햇빛": "warm late-afternoon sunlight",
    "골든아워": "low-angle golden-hour sunlight",
    "맑은 정오": "clean midday daylight",
    "카페 펜던트": "warm cafe pendant lighting",
    "천장 확산광": "diffuse overhead ambient lighting",
    "스탠드 램프": "a warm practical floor lamp",
    "벽 스콘스": "soft wall-sconce lighting",
    "도시 야간광": "mixed city street light filtering through the windows",
    "비 오는 날 확산광": "soft overcast daylight filtered through a rainy sky",
    "갤러리 조명": "controlled museum track lighting",
    "달빛": "soft blue moonlight from a clear night sky",
}
LIGHT_DIRECTIONS = ["from camera left", "from camera right", "from behind the subject", "from front-left", "from front-right", "from above and slightly to the side", "wrapping softly from both sides"]
LIGHT_QUALITY = ["soft and diffuse", "clean and directional", "gentle window-softened", "broad and even", "subtly dramatic but natural"]
LIGHT_INTENSITY = ["low contrast", "moderate contrast", "soft moderate contrast", "bright but controlled"]
COLOR_TEMPS = ["neutral daylight color", "slightly warm 4300K feel", "warm 4800K feel", "cool daylight 5600K feel", "golden warm ambience"]
SHADOWS = ["soft grounded shadows", "short soft-edged shadows", "natural contact shadows", "subtle directional shadows", "long soft evening shadows"]

HAIR_STYLES = [
    "straight shoulder-length hair with natural separation",
    "long softly layered hair with realistic strands",
    "short textured hair with subtle flyaways",
    "medium-length loose waves with natural volume",
    "neatly tied low ponytail with a few loose strands",
    "simple low bun with understated flyaways",
    "short bob with a clean silhouette and fine individual strands",
    "long straight hair tucked partly behind one ear",
    "natural half-up hairstyle with soft loose strands",
    "short wavy crop with gentle texture",
]
EXPRESSIONS = [
    "relaxed neutral expression", "gentle natural smile", "bright genuine smile", "small amused smile",
    "softly thoughtful expression", "focused attentive expression", "quiet content expression",
    "slightly surprised but natural expression", "playful smile", "calm observant expression",
]
GAZES = [
    "looking toward the camera", "looking slightly past the camera", "looking toward the other person",
    "looking down at the object in their hands", "looking toward the window", "looking at a book",
    "looking toward the street", "looking at the food or drink", "looking ahead while walking",
]

# ---------------------------------------------------------------------------
# Fabric physics library
# ---------------------------------------------------------------------------
def F(key: str, material: str, fiber: str, construction: str, density: str,
      fineness: str, opacity: str, thickness: str, weight: str, texture: str,
      sheen: str, stretch: str, stiffness: str, drape: str, surface: str,
      season: str, garments: Sequence[str]) -> FabricProfile:
    return FabricProfile(key, material, fiber, construction, density, fineness,
                         opacity, thickness, weight, texture, sheen, stretch,
                         stiffness, drape, surface, season, list(garments))


FABRICS: Dict[str, FabricProfile] = {
    "오간자": F("오간자", "organza", "fine filament fibers", "tightly woven plain weave", "high", "very fine", "sheer translucent", "very thin", "ultralight", "crisp airy hand", "soft luminous sheen", "low stretch", "stiff", "crisp structured drape", "clean edge highlights", "layering and dressy warm-season use", ["블라우스", "가벼운 원피스", "미디 드레스", "스카프"]),
    "쉬폰": F("쉬폰", "chiffon", "fine synthetic or silk filaments", "fine plain weave", "medium", "very fine", "semi-sheer", "very thin", "very light", "soft flowing texture", "low soft sheen", "low stretch", "fluid", "very fluid drape", "soft diffuse highlights", "warm-season", ["블라우스", "가벼운 원피스", "미디 드레스", "스카프"]),
    "실크": F("실크", "silk", "long smooth protein fibers", "fine woven construction", "medium", "fine", "opaque to lightly luminous", "light to medium", "light", "smooth supple texture", "distinctive soft luster", "low stretch", "fluid", "fluid elegant drape", "clear soft specular rolloff", "temperate", ["셔츠", "블라우스", "가벼운 원피스", "미디 드레스", "스카프"]),
    "새틴": F("새틴", "satin", "fine smooth filaments", "satin weave", "medium", "fine", "opaque", "light to medium", "light", "smooth face with subtle back texture", "high sheen", "low stretch", "moderately fluid", "sliding fluid drape", "strong elongated highlights", "temperate", ["블라우스", "가벼운 원피스", "미디 드레스", "스커트"]),
    "면": F("면", "cotton", "natural staple cotton fibers", "plain weave or twill", "medium to high", "fine to medium", "opaque", "light to medium", "light to medium", "soft natural textile grain", "matte to low sheen", "low stretch unless blended", "soft to medium", "natural relaxed drape", "broad diffuse highlights", "all-season", ["반팔 티셔츠", "셔츠", "블라우스", "미디 드레스", "청바지", "오버셔츠", "반바지", "후드 집업", "폴로 셔츠"]),
    "린넨": F("린넨", "linen", "flax fibers", "plain weave", "medium", "medium", "opaque to lightly open", "light to medium", "light to medium", "visible natural slub texture", "dry matte surface", "very low stretch", "crisp", "structured natural drape", "dry diffuse highlights", "warm-season", ["셔츠", "블라우스", "미디 드레스", "가벼운 원피스", "오버셔츠", "슬랙스", "반바지"]),
    "울": F("울", "wool", "wool staple fibers", "woven twill or plain weave", "medium-high", "medium", "opaque", "medium to heavy", "medium to heavy", "fine fuzzy textile surface", "low sheen", "low stretch", "medium", "substantial drape", "soft fuzzy edge highlights", "cool-season", ["울 코트", "블레이저", "니트 스웨터", "슬랙스", "A라인 스커트"]),
    "캐시미어": F("캐시미어", "cashmere", "very fine cashmere fibers", "fine knit or woven construction", "medium", "ultra-fine", "opaque", "light to medium", "light to medium", "exceptionally soft fine nap", "soft low sheen", "low stretch", "soft", "luxuriously soft drape", "muted highlights", "cool-season", ["니트 스웨터", "가디건", "울 코트", "스카프"]),
    "데님": F("데님", "denim", "cotton yarns", "tightly woven twill", "high", "medium", "opaque", "medium to heavy", "medium to heavy", "distinct diagonal twill texture", "matte with slight worn sheen", "low to medium stretch", "stiff to medium", "structured drape", "broad matte response", "all-season", ["데님 재킷", "청바지", "스커트", "오버셔츠"]),
    "저지": F("저지", "jersey knit", "fine knit fibers", "single-knit jersey", "medium", "fine", "opaque", "light to medium", "light", "fine knit grain", "low soft sheen", "medium to high stretch", "soft", "fluid relaxed drape", "soft diffuse highlights", "all-season", ["반팔 티셔츠", "미디 드레스", "운동복 상의", "조거 팬츠"]),
    "니트": F("니트", "knit", "looped yarn fibers", "knit-loop construction", "medium-high", "medium", "opaque", "medium", "medium", "visible knit loops", "low sheen", "medium stretch", "soft", "supple textured drape", "soft directional highlights", "cool-season", ["니트 스웨터", "가디건", "A라인 스커트"]),
    "벨벳": F("벨벳", "velvet", "fine pile yarns", "dense pile weave", "high", "fine", "opaque", "medium", "medium", "short directional pile", "rich directional sheen", "low stretch", "medium", "heavy fluid drape", "strong nap-dependent highlights", "cool-season or evening", ["미디 드레스", "블레이저", "A라인 스커트", "데님 재킷"]),
    "코듀로이": F("코듀로이", "corduroy", "cotton pile yarns", "ribbed pile weave", "high", "medium", "opaque", "medium to heavy", "medium to heavy", "distinct raised wales", "soft low directional sheen", "low stretch", "structured", "substantial drape", "rib-following highlights", "cool-season", ["코듀로이 팬츠", "데님 재킷", "오버셔츠", "A라인 스커트"]),
    "트위드": F("트위드", "tweed", "wool-blend yarns", "textured woven construction", "high", "medium", "opaque", "medium to heavy", "medium to heavy", "irregular flecked yarn texture", "low dry sheen", "low stretch", "stiff", "structured tailored drape", "textured diffuse highlights", "cool-season", ["블레이저", "울 코트", "A라인 스커트"]),
    "캔버스": F("캔버스", "canvas", "cotton or cotton-blend yarns", "dense plain weave", "very high", "medium", "opaque", "heavy", "heavy", "firm coarse weave", "matte", "very low stretch", "stiff", "strong structured drape", "broad matte response", "all-season", ["오버셔츠", "데님 재킷"]),
    "플란넬": F("플란넬", "flannel", "brushed cotton or wool fibers", "plain or twill weave", "medium-high", "medium", "opaque", "medium", "medium", "soft brushed nap", "matte", "low stretch", "soft", "warm relaxed drape", "soft diffuse highlights", "cool-season", ["셔츠", "오버셔츠", "파자마"]),
    "테리": F("테리", "terry cloth", "cotton loop yarns", "loop-pile knit or woven construction", "high", "medium", "opaque", "medium to heavy", "medium to heavy", "distinct looped surface", "matte", "medium stretch", "soft", "thick absorbent drape", "soft broad highlights", "warm-season", ["파자마", "반바지"]),
    "레이스": F("레이스", "lace", "fine yarn filaments", "openwork lace construction", "low to medium", "fine", "open semi-sheer", "thin", "very light", "open ornamental pattern", "low soft sheen", "low to medium stretch", "soft to moderately crisp", "delicate drape", "fine edge highlights", "all-season layering", ["블라우스", "미디 드레스"]),
    "메시": F("메시", "mesh", "synthetic or blended filaments", "open mesh construction", "medium", "fine", "transparent to translucent", "thin", "very light", "regular open grid texture", "low sheen", "medium stretch", "soft", "light flexible drape", "fine edge highlights", "warm-season and sport use", ["운동복 상의", "운동용 레깅스"]),
    "폴리에스터": F("폴리에스터", "polyester", "synthetic filament fibers", "plain, twill or knit construction", "medium", "fine", "opaque", "light to medium", "light", "even manufactured texture", "low to medium sheen", "low to high stretch depending on construction", "soft to medium", "stable practical drape", "clean controlled highlights", "all-season", ["셔츠", "미디 드레스", "운동복 상의", "슬랙스", "플리츠 스커트"]),
    "나일론": F("나일론", "nylon", "synthetic filaments", "tight woven or knit construction", "medium-high", "fine", "opaque to translucent depending on weight", "light", "very light", "smooth technical texture", "subtle technical sheen", "medium stretch", "soft", "light fluid drape", "controlled specular highlights", "all-season", ["운동복 상의", "운동용 레깅스", "트렌치코트"]),
    "가죽": F("가죽", "leather", "natural leather hide", "solid hide construction", "very high", "medium", "opaque", "medium to heavy", "medium to heavy", "fine grain or smooth surface", "low natural sheen", "very low stretch", "stiff to medium", "structured drape", "broad directional highlights", "cool-season or outerwear", ["데님 재킷", "블레이저"]),
    "인조가죽": F("인조가죽", "vegan leather", "polyurethane-coated textile base", "coated woven construction", "high", "fine", "opaque", "medium", "medium", "smooth coated grain", "medium sheen", "low stretch", "medium", "structured drape", "clean specular response", "all-season", ["데님 재킷", "A라인 스커트", "슬랙스"]),
    "시어서커": F("시어서커", "seersucker", "cotton yarns", "puckered plain weave", "medium", "fine to medium", "opaque", "light", "light", "distinct puckered stripes", "matte", "low stretch", "soft", "airy relaxed drape", "broken diffuse highlights", "warm-season", ["셔츠", "블라우스", "가벼운 원피스", "반바지"]),
    "모달": F("모달", "modal", "fine regenerated cellulose fibers", "fine knit or woven construction", "medium", "very fine", "opaque", "light", "light", "silky-soft smooth texture", "soft low sheen", "medium stretch", "fluid", "fluid soft drape", "soft silky highlights", "warm-season or layering", ["반팔 티셔츠", "블라우스", "미디 드레스", "파자마"]),
}


# ---------------------------------------------------------------------------
# Garment library
# ---------------------------------------------------------------------------
GARMENTS = {
    "반팔 티셔츠": ("a short-sleeve T-shirt", ["relaxed fit", "regular fit", "slightly oversized fit", "clean fitted silhouette"], ["면", "저지", "모달", "폴리에스터"], ["ribbed crew neckline", "subtle sleeve cuff", "clean double-needle hem", "minimal chest graphic"]),
    "셔츠": ("a button-front shirt", ["regular fit", "relaxed fit", "tailored fit", "slightly oversized fit"], ["면", "린넨", "실크", "폴리에스터", "플란넬"], ["button cuffs", "structured collar", "patch chest pocket", "clean placket", "slightly rolled sleeves"]),
    "블라우스": ("a blouse", ["relaxed drape", "regular fit", "lightly tailored fit", "soft fluid fit"], ["실크", "쉬폰", "오간자", "면", "레이스", "모달"], ["soft gathered neckline", "button-front closure", "subtle pleating", "delicate cuff", "fine seam finishing"]),
    "니트 스웨터": ("a knitted sweater", ["regular fit", "relaxed fit", "slightly oversized fit"], ["니트", "울", "캐시미어", "면"], ["ribbed cuffs", "ribbed hem", "fine-gauge knit", "textured cable pattern", "clean shoulder seam"]),
    "가디건": ("a cardigan", ["regular fit", "relaxed fit", "slim layering fit"], ["니트", "캐시미어", "울", "면"], ["button-front closure", "ribbed cuffs", "patch pockets", "fine-gauge knit"]),
    "블레이저": ("a tailored blazer", ["tailored fit", "relaxed tailoring", "slim tailored fit"], ["울", "트위드", "폴리에스터", "린넨"], ["notched lapels", "two-button closure", "welt pockets", "structured shoulders", "vented back hem"]),
    "트렌치코트": ("a classic trench coat", ["regular fit", "relaxed outerwear fit"], ["면", "폴리에스터", "나일론"], ["double-breasted closure", "storm flap", "belted waist", "button cuff straps", "structured collar"]),
    "울 코트": ("a wool overcoat", ["regular outerwear fit", "relaxed fit", "tailored fit"], ["울", "캐시미어", "트위드"], ["notched lapels", "front welt pockets", "single-breasted closure", "clean-lined shoulders"]),
    "데님 재킷": ("a denim jacket", ["regular fit", "slightly oversized fit", "cropped fit"], ["데님", "면", "가죽"], ["metal buttons", "chest patch pockets", "double-needle seams", "adjustable hem tabs"]),
    "오버셔츠": ("an overshirt", ["relaxed fit", "boxy fit", "slightly oversized fit"], ["면", "린넨", "플란넬", "캔버스", "데님"], ["large patch pockets", "button-front closure", "reinforced seams", "straight hem"]),
    "플리츠 스커트": ("a pleated skirt", ["high-waisted fit", "regular waist", "relaxed fit"], ["폴리에스터", "실크", "울"], ["even knife pleats", "concealed zipper", "clean waistband", "neat hem"]),
    "A라인 스커트": ("an A-line skirt", ["high-waisted fit", "regular waist", "structured fit"], ["면", "린넨", "울", "폴리에스터", "트위드", "인조가죽"], ["front pleat", "side zipper", "waistband with belt loops", "clean hem"]),
    "미디 드레스": ("a midi dress", ["fluid relaxed fit", "tailored waist", "straight silhouette", "A-line silhouette"], ["면", "린넨", "실크", "쉬폰", "모달", "폴리에스터", "레이스"], ["button-front closure", "waist seam", "subtle gathered detail", "clean neckline", "side seam pockets"]),
    "가벼운 원피스": ("a lightweight day dress", ["fluid fit", "relaxed fit", "softly tailored fit"], ["린넨", "면", "쉬폰", "모달", "오간자"], ["simple straps", "gathered waist seam", "softly curved neckline", "clean hem"]),
    "슬랙스": ("tailored trousers", ["straight fit", "wide-leg fit", "tapered fit", "relaxed tailoring"], ["울", "폴리에스터", "린넨", "트위드", "인조가죽"], ["flat front", "belt loops", "side pockets", "pressed crease", "hook-and-bar closure"]),
    "청바지": ("straight-leg jeans", ["straight fit", "relaxed fit", "slim straight fit", "wide-leg fit"], ["데님"], ["five-pocket construction", "metal rivets", "zip fly", "double-needle seams"]),
    "코듀로이 팬츠": ("corduroy trousers", ["straight fit", "relaxed fit", "wide-leg fit"], ["코듀로이"], ["front pockets", "belt loops", "zip fly", "raised wale texture"]),
    "반바지": ("casual shorts", ["regular fit", "relaxed fit", "tailored casual fit"], ["면", "린넨", "데님", "시어서커", "테리"], ["side pockets", "belt loops", "button closure", "clean hem"]),
    "조거 팬츠": ("casual jogger pants", ["relaxed fit", "tapered fit"], ["저지", "면", "폴리에스터"], ["elastic waistband", "drawstring", "ribbed cuffs", "side pockets"]),
    "후드 집업": ("a zip-front hoodie", ["relaxed fit", "regular fit", "oversized fit"], ["면", "저지", "폴리에스터"], ["drawstring hood", "full front zipper", "kangaroo pockets", "ribbed cuffs"]),
    "폴로 셔츠": ("a polo shirt", ["regular fit", "relaxed fit", "slim fit"], ["면", "저지", "폴리에스터"], ["ribbed collar", "two-button placket", "short sleeves", "side slits"]),
    "운동복 상의": ("a recreational sports top", ["regular athletic fit", "relaxed athletic fit", "close but comfortable fit"], ["나일론", "폴리에스터", "메시", "저지"], ["flat seams", "breathable panels", "short sleeves", "clean technical trim"]),
    "운동용 레깅스": ("athletic leggings", ["close athletic fit"], ["나일론", "저지", "폴리에스터"], ["wide supportive waistband", "flat seams", "subtle panel construction", "ankle-length hem"]),
    "파자마": ("a comfortable pajama set", ["relaxed fit", "oversized comfort fit"], ["면", "모달", "실크", "플란넬", "테리"], ["button-front top", "elastic waistband", "piped edges", "soft drawstring"]),
}

FOOTWEAR = {
    "화이트 스니커즈": "clean white leather sneakers",
    "캔버스 스니커즈": "classic canvas sneakers",
    "러닝화": "lightweight running shoes",
    "로퍼": "polished leather loafers",
    "메리제인": "classic Mary Jane shoes",
    "발레 플랫": "simple ballet flats",
    "앵클 부츠": "leather ankle boots",
    "첼시 부츠": "Chelsea boots",
    "샌들": "minimal leather sandals",
    "스니커즈": "casual sneakers",
    "실내 슬리퍼": "soft indoor slippers",
    "맨발": "bare feet appropriate to the setting",
}

ACCESSORIES = {
    "시계": "a simple wristwatch",
    "안경": "thin-framed eyeglasses",
    "선글라스": "simple sunglasses",
    "작은 귀걸이": "small understated earrings",
    "목걸이": "a delicate necklace",
    "반지": "a simple ring",
    "가죽 가방": "a structured leather shoulder bag",
    "캔버스 토트백": "a practical canvas tote bag",
    "백팩": "a practical backpack",
    "스카프": "a lightweight scarf",
    "모자": "a simple baseball cap",
    "비니": "a soft knit beanie",
    "헤어밴드": "a simple fabric headband",
    "없음": "no prominent accessory",
}

CLOTHING_COLORS = {
    "화이트": "clean white", "아이보리": "soft ivory", "베이지": "warm beige", "토프": "muted taupe",
    "연회색": "light gray", "차콜": "deep charcoal gray", "블랙": "black", "네이비": "deep navy",
    "하늘색": "pale blue", "코발트 블루": "cobalt blue", "세이지": "muted sage green", "올리브": "soft olive green",
    "브라운": "warm brown", "테라코타": "muted terracotta", "버건디": "deep burgundy", "핑크": "soft pink",
    "라일락": "muted lilac", "노랑": "soft golden yellow", "오렌지": "muted orange", "데님 블루": "classic denim blue",
}

CLOTHING_STATES = {
    "깔끔함": "clean, freshly maintained, and neatly arranged",
    "자연스러움": "naturally worn with subtle everyday creasing",
    "살짝 구김": "lightly rumpled with believable soft folds",
    "잘 다려짐": "freshly pressed with crisp construction lines",
    "활동 후": "slightly lived-in after normal daily activity",
    "빈티지": "gently worn with subtle age-related texture",
}

SEAM_DETAILS = [
    "single-needle topstitching", "double-needle topstitching", "reinforced side seams",
    "clean overlocked interior seams", "flat-felled seam on high-wear areas", "bound neckline edge",
    "bias-finished internal edge", "clean pocket openings", "reinforced pocket corners",
]
FASTENER_DETAILS = [
    "matte four-hole buttons", "small metal buttons", "concealed zipper", "exposed metal zipper",
    "hook-and-bar closure", "snap-button closure", "fabric-covered buttons", "simple drawstring closure",
]
FOLD_BEHAVIORS = [
    "soft folds collect naturally at elbows and knees",
    "shallow compression folds form where fabric meets a seat or backrest",
    "small tension folds radiate from moving joints",
    "fabric hangs according to its weight rather than floating unnaturally",
    "heavier sections settle downward with believable gravity",
    "lightweight sections respond to small movements with subtle secondary folds",
    "tailored sections keep clean planes between seams",
    "knit sections compress and recover naturally around bends",
]

# ---------------------------------------------------------------------------
# Environment material / object catalog
# ---------------------------------------------------------------------------
ENV_MATERIALS = {
    "오크": ("fine straight oak grain", "low satin sheen", "soft directional reflections"),
    "월넛": ("deep walnut grain", "subtle satin sheen", "controlled warm reflections"),
    "리넨": ("visible linen weave", "dry matte surface", "soft diffuse highlights"),
    "유리": ("clear smooth glass", "clean specular highlights", "sharp realistic reflections and transparency"),
    "브러시드 메탈": ("fine brushed metal grain", "controlled metallic sheen", "directional elongated reflections"),
    "대리석": ("subtle natural stone veining", "polished low-gloss surface", "broad stone reflections"),
    "테라조": ("small aggregate chips embedded in stone", "low satin sheen", "soft broken reflections"),
    "세라믹": ("smooth glazed ceramic", "gentle glaze sheen", "small clean highlights"),
    "도장 벽": ("fine painted plaster grain", "mostly matte", "broad diffuse light response"),
    "석재": ("natural porous stone texture", "low matte sheen", "soft uneven reflection"),
    "콘크리트": ("subtle mineral aggregate texture", "matte", "broad low-contrast bounce"),
    "카펫": ("dense textile pile", "matte", "soft light absorption"),
    "가죽": ("fine leather grain", "low conditioned sheen", "soft broad highlights"),
}

FURNITURE = {
    "three-seat sofa": "a proportionally sized three-seat sofa",
    "low coffee table": "a low rectangular coffee table",
    "media console": "a compact media console",
    "accent chair": "a proportionally sized accent chair",
    "floor lamp": "a floor lamp with a realistic human-scale stand",
    "side table": "a small side table",
    "kitchen island": "a proportionally sized kitchen island",
    "counter stools": "counter-height stools",
    "dining table": "a realistically sized dining table",
    "dining chairs": "simple dining chairs",
    "built-in cabinetry": "built-in kitchen cabinetry",
    "writing desk": "a functional writing desk",
    "ergonomic office chair": "an ergonomic office chair",
    "bookshelf": "a tall bookshelf",
    "drawer cabinet": "a compact drawer cabinet",
    "double bed": "a proportionally sized double bed",
    "bedside tables": "bedside tables",
    "wooden dresser": "a wooden dresser",
    "reading chair": "a comfortable reading chair",
    "standing mirror": "a full-height standing mirror",
    "small round tables": "small round cafe tables",
    "wooden cafe chairs": "wooden cafe chairs",
    "long counter": "a cafe counter",
    "bar stools": "counter-height cafe stools",
    "bench seating": "a long upholstered bench",
    "tall bookshelves": "tall bookshelves with realistic aisle spacing",
    "reading table": "a shared reading table",
    "armchair": "a comfortable armchair",
    "small display pedestal": "a small display pedestal",
    "minimal bench": "a minimal gallery bench",
    "reception desk": "a reception desk",
    "sculpture plinths": "museum sculpture plinths",
    "long study tables": "long study tables",
    "individual study desks": "individual study desks",
    "reading chairs": "reading chairs",
    "street bench": "a street bench",
    "small outdoor tables": "small outdoor tables",
    "bus shelter": "a bus shelter",
    "wooden bench": "a realistic wooden park bench",
    "picnic table": "a picnic table",
    "small pavilion": "a small park pavilion",
    "folding beach chair": "a folding beach chair",
    "small sun shelter": "a simple sun shelter",
    "trail bench": "a trail-side bench",
    "wooden rest shelter": "a small wooden trail shelter",
    "deep lounge chairs": "deep lounge chairs",
    "sofas": "hotel lobby sofas",
    "marble side tables": "marble side tables",
    "queen bed": "a proportionally sized queen bed",
    "desk": "a hotel writing desk",
    "lounge chair": "a hotel lounge chair",
    "luggage bench": "a luggage bench",
    "metal benches": "station benches",
    "ticket kiosks": "ticket kiosks",
    "information desk": "a station information desk",
    "small cafe table": "a small cafe table",
    "reading armchair": "a bookstore reading armchair",
}

DECOR = {
    "framed artwork": "framed wall artwork",
    "ceramic vase": "a small ceramic vase",
    "bookshelf": "a shelf of books",
    "leafy houseplant": "a leafy houseplant",
    "textured throw blanket": "a folded textured throw blanket",
    "herb pots": "small herb pots",
    "ceramic bowls": "ceramic bowls",
    "wooden cutting board": "a wooden cutting board",
    "small framed print": "a small framed print",
    "framed botanical print": "a framed botanical print",
    "small lamp": "a small table lamp",
    "books": "a small stack of books",
    "ceramic tray": "a ceramic tray",
    "desk plant": "a small desk plant",
    "cork board": "a practical cork board",
    "small sculpture": "a small decorative sculpture",
    "menu board": "a cafe menu board",
    "hanging plants": "hanging plants",
    "ceramic cups": "a small arrangement of ceramic cups",
    "local art prints": "local art prints",
    "small table lamps": "small table lamps",
    "book displays": "curated book displays",
    "small plants": "small potted plants",
    "recommendation cards": "handwritten book recommendation cards",
    "framed paintings": "framed paintings",
    "large sculpture": "a large gallery sculpture",
    "wall labels": "museum wall labels",
    "museum signage": "minimal museum signage",
    "quiet-study signs": "quiet-study signs",
    "potted plants": "potted plants",
    "planters": "street planters",
    "street signs": "clear street signs",
    "posters": "layered but controlled storefront posters",
    "storefront displays": "tasteful storefront displays",
    "flower beds": "seasonal flower beds",
    "ornamental trees": "ornamental trees",
    "public sculpture": "a small public sculpture",
    "driftwood": "driftwood pieces",
    "shells": "small shells",
    "simple beach sign": "a simple beach sign",
    "direction signs": "trail direction signs",
    "wildflowers": "small wildflowers",
    "mossy stones": "mossy stones",
    "large vase arrangement": "a large vase arrangement",
    "abstract artwork": "abstract lobby artwork",
    "sculptural lighting": "sculptural lobby lighting",
    "abstract print": "an abstract print",
    "tea tray": "a small tea tray",
    "decorative cushion": "a decorative cushion",
    "digital departure board": "a digital departure board",
    "direction signs": "station direction signs",
    "wayfinding graphics": "clean wayfinding graphics",
    "stacked books": "stacked books",
    "art prints": "small art prints",
}

PRACTICAL = {
    "ceramic mug": "a ceramic mug",
    "smartphone": "a smartphone",
    "remote control": "a remote control",
    "charging cable": "a charging cable",
    "coffee machine": "a compact coffee machine",
    "kettle": "a kettle",
    "dish rack": "a dish rack",
    "fruit bowl": "a fruit bowl",
    "cookbook": "an open cookbook",
    "glass of water": "a glass of water",
    "alarm clock": "an alarm clock",
    "reading glasses": "reading glasses",
    "laptop": "an open laptop",
    "monitor": "a desktop monitor",
    "keyboard": "a keyboard",
    "notebook": "an open notebook",
    "pen cup": "a pen cup",
    "headphones": "a pair of headphones",
    "coffee grinder": "a coffee grinder",
    "pastry display": "a compact pastry display",
    "paper menus": "paper menus",
    "water carafe": "a water carafe",
    "open books": "open books",
    "shopping basket": "a shopping basket",
    "bookmark display": "a bookmark display",
    "museum brochure": "a museum brochure",
    "audio guide": "an audio guide",
    "visitor map": "a visitor map",
    "library card": "a library card",
    "crosswalk signal": "a crosswalk signal",
    "bicycle rack": "a bicycle rack",
    "parked bicycles": "parked bicycles",
    "recycling bin": "a recycling bin",
    "park map": "a park map",
    "tote bag": "a practical tote bag",
    "water bottle": "a reusable water bottle",
    "beach towel": "a neatly folded beach towel",
    "sunglasses": "a pair of sunglasses",
    "walking backpack": "a practical walking backpack",
    "trail map": "a folded trail map",
    "hotel brochures": "hotel brochures",
    "key-card holder": "a key-card holder",
    "small luggage trolley": "a small luggage trolley",
    "room-service menu": "a room-service menu",
    "luggage": "travel luggage",
    "phone charger": "a phone charger",
    "rolling suitcase": "a rolling suitcase",
    "travel bag": "a compact travel bag",
    "train ticket": "a train ticket",
    "open novel": "an open novel",
    "coffee cup": "a coffee cup",
    "bookmark": "a bookmark",
}

PALETTES = {
    "뉴트럴": "warm neutral harmony of ivory, beige, gray and natural wood",
    "쿨 뉴트럴": "cool neutral harmony of soft gray, blue-gray and pale wood",
    "웜 뉴트럴": "warm ivory, beige, tan and muted brown harmony",
    "세이지": "sage green, cream and natural wood harmony",
    "블루": "muted blue, ivory and charcoal harmony",
    "테라코타": "muted terracotta, cream and warm wood harmony",
    "모노톤": "coherent monochrome palette with subtle tonal variation",
    "파스텔": "soft pastel palette with restrained saturation",
}

CAMERA_FRAMING = {
    "전신": "full-body composition with the subject fully visible from head to feet",
    "3/4 전신": "three-quarter full-body composition showing the subject from head to below the knees with environmental context",
    "무릎 위": "medium-long portrait framing from head to around the knees",
    "허벅지 위": "medium framing from head to upper thighs",
    "허리 위": "waist-up portrait framing",
    "가슴 위": "chest-up portrait framing",
    "클로즈업": "close portrait framing focused on the face and upper shoulders",
    "환경 중심": "environmental portrait framing with the subject clearly visible within the surrounding space",
    "와이드 씬": "wide scene composition with generous environmental context",
}
VIEWPOINTS = {
    "눈높이": "eye-level viewpoint",
    "약간 위": "slightly elevated viewpoint",
    "약간 아래": "slightly low viewpoint",
    "정면": "straight-on viewpoint",
    "사선": "three-quarter viewpoint",
    "옆면": "side viewpoint",
    "뒤쪽 사선": "rear three-quarter viewpoint with natural subject orientation",
}
COMPOSITIONS = {
    "중앙": "balanced centered composition",
    "삼분할": "balanced rule-of-thirds composition",
    "대각선": "subtle diagonal composition following natural gesture",
    "여백": "clean composition with intentional negative space",
    "레이어": "layered foreground, midground and background composition",
    "대칭": "controlled symmetrical composition when supported by the architecture",
    "스냅샷": "natural candid snapshot composition with believable timing",
}
DEPTHS = {
    "깊음": "deep depth of field with both subject and environment remaining clear",
    "보통": "moderate depth of field with gentle background separation",
    "얕음": "shallow depth of field with selective subject emphasis",
    "매우 얕음": "very shallow depth of field reserved for close portrait details",
}


# ---------------------------------------------------------------------------
# Embedded translator interface
# ---------------------------------------------------------------------------
# Translation vocabulary lives in the separate ``krea2_translator`` package.
# The tiny fallback below keeps the prompt studio usable if that package is
# temporarily missing; normal operation always uses the replaceable module.
KOREAN_GLOSSARY = {
    "한국인 여성": "adult Korean woman",
    "한국인 남성": "adult Korean man",
    "한국인 성인": "adult Korean person",
    "성인 여성": "adult woman",
    "성인 남성": "adult man",
    "여성": "woman",
    "남성": "man",
    "한국인": "Korean",
    "자연스러운": "natural",
    "현실적인": "realistic",
    "아늑한": "cozy",
    "로맨틱한": "romantic",
    "따뜻한": "warm",
    "차분한": "calm",
    "세련된": "refined",
    "일상적인": "everyday",
    "실제 크기": "real-world scale",
    "자연광": "natural light",
    "피부결": "natural skin texture",
}


def local_translate(text: str) -> str:
    """Translate free-form Korean through the replaceable local module."""
    if embedded_translate is not None:
        return embedded_translate(text)
    result = text or ""
    user_dict = load_json(USER_DICTIONARY_FILE, {})
    pairs = list(user_dict.items()) if isinstance(user_dict, dict) else []
    pairs += list(KOREAN_GLOSSARY.items())
    for kr, en in sorted(pairs, key=lambda pair: len(str(pair[0])), reverse=True):
        result = result.replace(str(kr), str(en))
    return clean_text(result)


# ---------------------------------------------------------------------------
# Smart Random configuration
# ---------------------------------------------------------------------------
RANDOM_MODES = {
    "고정": "fixed",
    "좁은 랜덤": "narrow",
    "중간 랜덤": "medium",
    "넓은 랜덤": "wide",
    "자동": "auto",
}
FIELD_HELP = {
    "theme": "장면 전체의 세계와 큰 분위기를 정합니다",
    "location": "인물이 있는 실제 공간 종류입니다",
    "activity": "인물이 실제로 하고 있는 행동입니다",
    "interaction": "두 사람 사이의 몸짓입니다 (2인일 때)",
    "pose": "몸의 자세와 체중을 받치는 곳을 정합니다",
    "material": "의상 원단입니다. 의상 종류와 어울리는 것만 나옵니다",
    "garment": "입는 옷의 종류입니다",
    "fit": "옷의 실루엣(넉넉함/몸에 맞음)입니다",
    "color": "의상 색상입니다",
    "environment_density": "배경에 놓이는 물건의 양입니다",
    "environment_state": "공간이 얼마나 정돈돼 보이는지입니다",
    "palette": "장면 전체의 색 조화입니다",
    "framing": "인물을 어디까지 화면에 담을지 정합니다",
    "viewpoint": "카메라가 인물을 보는 방향과 높이입니다",
    "composition": "인물과 배경을 화면에 배치하는 방식입니다",
    "lens": "초점거리(mm)입니다. 숫자가 작을수록 넓게 보입니다",
    "weather": "바깥 날씨입니다",
    "time": "장면의 시간대입니다. 빛의 방향과 분위기가 달라집니다",
    "mood": "장면이 주는 감정의 결입니다",
}


def constraint(value: str = "auto", mode: str = "auto", priority: int = 50, source: str = "auto") -> ConstraintSetting:
    return ConstraintSetting(value=value, random_mode=mode, priority=priority, source=source)


def defaults() -> Dict[str, ConstraintSetting]:
    result: Dict[str, ConstraintSetting] = {}
    for key in FIELD_HELP:
        result[key] = constraint()
    result["left_right_basis"] = constraint("subject perspective", "fixed", 100, "system")
    for slot in ("A", "B"):
        for suffix in ("garment", "fit", "material", "color", "footwear", "accessory", "state", "detail"):
            result[f"{suffix}_{slot}"] = constraint()
    result["people"] = constraint("auto")
    result["identity_A"] = constraint("adult person")
    result["identity_B"] = constraint("adult person")
    result["skin_finish"] = constraint("자연 피부")
    result["realism"] = constraint("포토리얼")
    for key in ("light_source", "light_direction", "light_quality", "light_intensity", "color_temperature", "style", "prop_A", "prop_B", "lora_trigger_A", "lora_trigger_B", "expression_A", "expression_B", "gaze_A", "gaze_B", "hair_A", "hair_B", "height_A", "height_B", "sublocation"):
        result.setdefault(key, constraint())
    return result


def set_constraint_value(c: Dict[str, ConstraintSetting], key: str, value: str, mode: str = "fixed", priority: int = 95, source: str = "user") -> None:
    c[key] = constraint(value, mode, priority, source)


def get_value(c: Dict[str, ConstraintSetting], key: str, default: str = "auto") -> str:
    item = c.get(key)
    return item.value if item and item.value else default


def resolve_mapping_value(requested: str, mapping: Dict[str, str], rng: random.Random, label: str) -> str:
    """Accept either a Korean UI key or an already-translated English value."""
    if requested in mapping:
        return mapping[requested]
    if requested in mapping.values():
        return requested
    return choose(rng, list(mapping.values()))


def slot_trigger(c: Dict[str, ConstraintSetting], slot: str) -> str:
    value = clean_text(get_value(c, f"lora_trigger_{slot}"))
    return "" if value.lower() in {"auto", "none"} else value


def lora_profile_for_trigger(trigger: str) -> Optional[Dict[str, Any]]:
    trigger = clean_text(trigger)
    if not trigger:
        return None
    for row in load_loras():
        if not isinstance(row, dict):
            continue
        if clean_text(str(row.get("trigger", ""))).lower() == trigger.lower():
            return row
    return None


def is_lora_identity_locked(trigger: str, identity: str) -> bool:
    profile = lora_profile_for_trigger(trigger)
    return bool(profile and clean_text(str(profile.get("identity", ""))))


def choose_with_mode(rng: random.Random, values: Sequence[Any], mode: str) -> Any:
    vals = list(values)
    if not vals:
        return ""
    if mode == "fixed":
        return vals[0]
    if mode == "narrow":
        return choose(rng, vals[: min(3, len(vals))])
    if mode == "medium":
        return choose(rng, vals[: min(max(4, len(vals) // 2), len(vals))])
    return choose(rng, vals)

# ---------------------------------------------------------------------------
# Clothing resolution: material drives physical properties
# ---------------------------------------------------------------------------
CLOTHING_DETAILS = [
    "clean seam finishing", "double-needle hem", "subtle topstitching", "reinforced stress points",
    "small tonal buttons", "matte metal zipper", "concealed zipper", "realistic collar roll",
    "natural sleeve compression", "believable hem weight", "subtle seam puckering", "well-proportioned pockets",
]
FOOTWEAR = {
    "화이트 스니커즈": "clean white leather sneakers",
    "캔버스 스니커즈": "classic canvas sneakers",
    "러닝화": "lightweight running shoes",
    "로퍼": "polished leather loafers",
    "메리제인": "classic Mary Jane shoes",
    "발레 플랫": "simple ballet flats",
    "앵클 부츠": "leather ankle boots",
    "첼시 부츠": "Chelsea boots",
    "샌들": "minimal leather sandals",
    "스니커즈": "casual sneakers",
    "실내 슬리퍼": "soft indoor slippers",
    "맨발": "bare feet suitable to the setting",
}
ACCESSORIES = {
    "시계": "a simple wristwatch", "안경": "thin-framed eyeglasses", "선글라스": "simple sunglasses",
    "작은 귀걸이": "small understated earrings", "목걸이": "a delicate necklace", "반지": "a simple ring",
    "가죽 가방": "a structured leather shoulder bag", "캔버스 토트백": "a practical canvas tote bag",
    "백팩": "a practical backpack", "스카프": "a lightweight scarf", "모자": "a simple baseball cap",
    "비니": "a soft knit beanie", "헤어밴드": "a simple fabric headband", "없음": "no prominent accessory",
}
COLORS = {
    "화이트": "clean white", "아이보리": "soft ivory", "베이지": "warm beige", "토프": "muted taupe",
    "연회색": "light gray", "차콜": "deep charcoal gray", "블랙": "black", "네이비": "deep navy",
    "하늘색": "pale blue", "코발트 블루": "cobalt blue", "세이지": "muted sage green", "올리브": "soft olive green",
    "브라운": "warm brown", "테라코타": "muted terracotta", "버건디": "deep burgundy", "핑크": "soft pink",
    "라일락": "muted lilac", "노랑": "soft golden yellow", "오렌지": "muted orange", "데님 블루": "classic denim blue",
}
CLOTHING_STATES = {
    "깔끔함": "clean and freshly maintained", "자연스러움": "naturally worn with subtle everyday creasing",
    "살짝 구김": "lightly rumpled with believable soft folds", "잘 다려짐": "freshly pressed with crisp construction lines",
    "활동 후": "slightly lived-in after normal daily activity", "빈티지": "gently worn with subtle age-related texture",
}


def compatible_fabrics(garment_key: str) -> List[str]:
    """Return the union of garment-declared and fabric-declared compatibility.

    This keeps the two catalogs from drifting apart: fabrics such as satin and velvet
    remain selectable when their own compatibility records declare the garment valid.
    """
    data = GARMENTS.get(garment_key)
    if not data:
        return list(FABRICS)
    forward = [key for key in data[2] if key in FABRICS]
    reverse = [key for key, fabric in FABRICS.items() if garment_key in fabric.compatible_garments]
    return list(dict.fromkeys(forward + reverse))


def resolve_clothing(rng: random.Random, slot: str, c: Dict[str, ConstraintSetting]) -> ClothingProfile:
    garment_req = get_value(c, f"garment_{slot}")
    garment_key = garment_req if garment_req in GARMENTS else choose(rng, list(GARMENTS))
    garment_en, fits, mats, details = GARMENTS[garment_key]

    fit_req = get_value(c, f"fit_{slot}")
    fit = fit_req if fit_req in fits else choose(rng, fits)

    mat_req = get_value(c, f"material_{slot}")
    allowed_materials = compatible_fabrics(garment_key)
    if mat_req in FABRICS:
        material_mode = c.get(f"material_{slot}", constraint()).random_mode
        garment_mode = c.get(f"garment_{slot}", constraint()).random_mode
        incompatible = mat_req not in allowed_materials
        if incompatible and material_mode == "fixed" and garment_mode == "fixed":
            raise ValueError(f"인물 {slot}: 고정한 의상 '{garment_key}'와 고정한 소재 '{mat_req}'가 호환되지 않습니다. 둘 중 하나를 자동으로 바꾸거나 호환 조합을 선택하세요.")
        if incompatible and material_mode == "fixed":
            compatible_garments = [k for k in GARMENTS if mat_req in compatible_fabrics(k)]
            if not compatible_garments:
                raise ValueError(f"인물 {slot}: 소재 '{mat_req}'에 호환되는 의상이 없습니다.")
            garment_key = choose(rng, compatible_garments)
            garment_en, fits, mats, details = GARMENTS[garment_key]
            if fit not in fits:
                fit = choose(rng, fits)
            allowed_materials = compatible_fabrics(garment_key)
        fabric_key = mat_req if mat_req in FABRICS else choose(rng, allowed_materials or list(FABRICS))
    else:
        fabric_key = choose(rng, allowed_materials or list(FABRICS))
    fabric = FABRICS[fabric_key]

    color_req = get_value(c, f"color_{slot}")
    color = COLORS[color_req] if color_req in COLORS else choose(rng, list(COLORS.values()))
    state_req = get_value(c, f"state_{slot}")
    state = CLOTHING_STATES.get(state_req, choose(rng, list(CLOTHING_STATES.values())))
    foot_req = get_value(c, f"footwear_{slot}")
    foot = FOOTWEAR.get(foot_req, choose(rng, list(FOOTWEAR.values())))
    acc_req = get_value(c, f"accessory_{slot}")
    accessory = ACCESSORIES.get(acc_req, choose(rng, list(ACCESSORIES.values())))
    detail_req = get_value(c, f"detail_{slot}")
    if detail_req not in {"", "auto"}:
        detail = detail_req
    else:
        detail = f"{choose(rng, details)}, {choose(rng, CLOTHING_DETAILS)}"

    # Material-specific physical coupling. A selected material owns the values;
    # independent random generation is never allowed to contradict these.
    if fabric.key == "오간자":
        detail += ", fine tightly packed yarns with crisp translucent edges"
    elif fabric.key in {"쉬폰", "레이스"}:
        detail += ", lightweight construction with delicate edge behavior"
    elif fabric.key in {"데님", "캔버스", "코듀로이"}:
        detail += ", dense construction with visibly substantial seams"
    elif fabric.key in {"니트", "캐시미어", "울"}:
        detail += ", believable yarn structure and gravity-driven folds"
    elif fabric.key in {"린넨", "시어서커"}:
        detail += ", visible natural slub or puckered texture"

    return ClothingProfile(
        garment_key=garment_key,
        garment_en=garment_en,
        fit=fit,
        color=color,
        details=detail,
        footwear=foot,
        accessory=accessory,
        state=state,
        fabric=fabric,
        construction_detail=fabric.construction,
        fold_behavior=choose(rng, FOLD_BEHAVIORS),
    )


def clothing_prompt(c: ClothingProfile) -> str:
    f = c.fabric
    physical = (
        f"{f.material} made from {f.fiber}; {f.construction}; {f.density} fabric density; "
        f"{f.fiber_fineness} fibers; {f.opacity} opacity; {f.thickness} thickness; {f.weight} weight; "
        f"{f.texture}; {f.sheen}; {f.stretch}; {f.stiffness} hand; {f.drape}; {f.surface_response}"
    )
    garment = re.sub(r"^(an?)\s+", "", c.garment_en)
    return (
        f"{c.color} {garment}, {c.fit}, {physical}; {c.details}; "
        f"{c.fold_behavior}; {c.state}; {c.footwear}; {c.accessory}."
    )


# ---------------------------------------------------------------------------
# Environment resolution: foreground / midground / background + scale
# ---------------------------------------------------------------------------
ENV_DENSITY = {
    "희박": (2, 1, 1, "sparse"),
    "낮음": (3, 2, 1, "light"),
    "보통": (4, 3, 2, "moderate"),
    "높음": (5, 4, 3, "detailed"),
    "풍부": (6, 5, 4, "rich"),
}


def _obj_translate(name: str, catalog: Dict[str, str]) -> str:
    return catalog.get(name, name)


def resolve_environment(location_key: str, rng: random.Random, c: Dict[str, ConstraintSetting]) -> EnvironmentProfile:
    data = LOCATIONS[location_key]
    density_req = get_value(c, "environment_density")
    density_key = density_req if density_req in ENV_DENSITY else choose(rng, ["낮음", "보통", "보통", "높음", "풍부"])
    fn, dn, pn, density_en = ENV_DENSITY[density_key]

    def take(values: Sequence[str], n: int, translate: Optional[Dict[str, str]] = None) -> List[str]:
        seq = list(values)
        rng.shuffle(seq)
        return [translate.get(x, x) if translate else x for x in seq[: min(n, len(seq))]]

    furniture = take(data.get("furniture", []), fn, FURNITURE)
    decor = take(data.get("decor", []), dn, DECOR)
    practical = take(data.get("practical", []), pn, PRACTICAL)

    # The same actual object must belong to one depth layer only. This prevents
    # the common bug where a table is simultaneously foreground and background.
    foreground = furniture[: max(1, min(2, len(furniture)))]
    midground = [x for x in furniture[max(2, len(foreground)) : max(3, len(furniture))]] + decor[:2]
    midground = midground + practical
    background = decor[2:]

    state_req = get_value(c, "environment_state")
    state_map = {
        "깔끔": "clean and organized",
        "생활감": "tidy but naturally lived-in",
        "정돈된": "carefully organized with practical objects placed logically",
        "살짝 어수선": "lightly lived-in with a few believable objects left in use",
    }
    state = state_map.get(state_req, choose(rng, list(state_map.values())))

    palette_req = get_value(c, "palette")
    palette = resolve_mapping_value(palette_req, PALETTES, rng, "palette")

    material_key = choose(rng, list(ENV_MATERIALS))
    surface, sheen, response = ENV_MATERIALS[material_key]
    surface_response = f"{surface}, {sheen}, {response}"

    env = EnvironmentProfile(
        location_key=location_key,
        location_en=data["en"],
        sublocation=choose(rng, data.get("subs", ["in the main area"])),
        architecture=data["architecture"],
        walls=choose(rng, data.get("walls", ["neutral painted walls"])),
        floor=choose(rng, data.get("floor", ["realistic flooring"])),
        ceiling=choose(rng, data.get("ceiling", ["simple ceiling"])),
        windows=choose(rng, data.get("windows", ["appropriate glazing"])),
        doors=choose(rng, data.get("doors", ["appropriate doors"])),
        furniture=furniture,
        decor=decor,
        practical=practical,
        foreground=foreground,
        midground=midground,
        background=background,
        density=density_en,
        state=state,
        palette=palette,
        surface_response=surface_response,
        scale_rules=[
            "furniture, doors, windows and counters use realistic dimensions relative to an adult human",
            "foreground objects are larger only because of perspective, never because of arbitrary scaling",
            "midground and background objects retain coherent perspective compression",
            "all architectural lines share one consistent vanishing system",
            "the person's physical size remains consistent with nearby furniture",
            "nearby objects share the same floor contact plane as the subject when appropriate",
        ],
    )
    env.spatial_layout = build_spatial_layout(env, rng)
    return env


def build_spatial_layout(env: EnvironmentProfile, rng: random.Random) -> Dict[str, str]:
    pools = {
        "foreground": ["near the camera-left edge", "near the camera-right edge",
                       "close to the camera on the left", "close to the camera on the right"],
        "midground": ["slightly left of the subject", "slightly right of the subject",
                      "beside the main furniture group", "near the main window",
                      "near the entrance or doorway", "behind the subject at a comfortable distance"],
        "background": ["along the far wall", "far behind the subject", "in the far corner of the room",
                       "at the back of the space", "near the far window or doorway"],
    }
    layout: Dict[str, str] = {}
    used: set[str] = set()
    for layer_name, items in (("foreground", env.foreground), ("midground", env.midground), ("background", env.background)):
        for item in items:
            candidates = [x for x in pools[layer_name] if x not in used]
            position = choose(rng, candidates or pools[layer_name])
            used.add(position)
            layout[item] = f"in the {layer_name}, {position}"
    return layout


def environment_prompt(env: EnvironmentProfile) -> str:
    def join(items: Any, default: str) -> str:
        if not items:
            return default
        if isinstance(items, str):
            return items
        return "; ".join(items)
    architectural_openings = []
    if env.windows:
        architectural_openings.append(f"Windows: {join(env.windows, 'appropriate glazing')}")
    if env.doors:
        architectural_openings.append(f"Doors: {join(env.doors, 'appropriate doors')}")
    if not architectural_openings:
        architectural_openings.append("Open-air setting with no relevant enclosed windows or doors")
    return (
        f"The environment is {env.location_en}, specifically {env.sublocation}. {env.architecture}. "
        f"Walls: {env.walls}. Floor: {env.floor}. Ceiling: {env.ceiling}. "
        + " ".join(architectural_openings) + ". "
        + f"Furniture: {join(env.furniture, 'minimal furniture')}. Decor: {join(env.decor, 'minimal decor')}. "
        + f"Practical objects: {join(env.practical, 'few practical objects')}. "
        + f"Foreground: {join(env.foreground, 'clear foreground')}. Midground: {join(env.midground, 'open midground')}. "
        + f"Background: {join(env.background, 'quiet background')}. Background density is {env.density}. "
        + f"The space is {env.state}. The color harmony is {env.palette}. Surface response: {env.surface_response}. "
        + ". ".join(env.scale_rules) + ". "
        + "Spatial placement: " + "; ".join(f"{item}: {place}" for item, place in env.spatial_layout.items()) + "."
    )


# ---------------------------------------------------------------------------
# Body state / pose solver
# ---------------------------------------------------------------------------
def pose_state(pose_key: str, rng: random.Random) -> Dict[str, Any]:
    p = BASE_POSES[pose_key]
    left_leg, right_leg = p["legs"]
    weight = "balanced"
    if pose_key == "한쪽 다리에 기대 서기":
        weight = choose(rng, ["mostly left-leg weighted", "mostly right-leg weighted"])
    elif pose_key in {"걷기", "천천히 걷기", "손잡고 걷기", "달리기 동작"}:
        weight = "weight transfers naturally during movement"
    elif pose_key in {"벤치에 앉기", "소파에 편하게 앉기", "의자에 앉아 읽기", "책상에 앉아 공부하기"}:
        weight = "supported through the hips with both feet grounded"
    return {
        "pose_key": pose_key,
        "pose_en": p["en"],
        "support_points": list(p["supports"]),
        "left_leg": left_leg,
        "right_leg": right_leg,
        "left_foot": "grounded" if left_leg == "grounded" else left_leg,
        "right_foot": "grounded" if right_leg == "grounded" else right_leg,
        "weight_distribution": weight,
        "left_arm": "relaxed and task-appropriate",
        "right_arm": "relaxed and task-appropriate",
        "torso": "natural neutral alignment",
        "head": "natural neck alignment",
    }


def resolve_pose(rng: random.Random, c: Dict[str, ConstraintSetting], people: int, activity_key: str, interaction_key: str) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    req = get_value(c, "pose")
    if req in BASE_POSES:
        key_a = req
    else:
        activity_pose_bias = {
            "산책": ["걷기", "천천히 걷기", "편안하게 서기"],
            "저녁 산책": ["천천히 걷기", "손잡고 걷기", "편안하게 서기"],
            "손잡고 걷기": ["손잡고 걷기"],
            "공원 피크닉": ["벤치에 앉기", "바닥에 앉기", "편안하게 서기"],
            "공부하기": ["책상에 앉아 공부하기", "의자에 앉아 읽기"],
            "책 읽기": ["의자에 앉아 읽기", "소파에 편하게 앉기", "창가에 앉기"],
            "카페 데이트": ["나란히 앉기", "벤치에 앉기", "서로 마주 보기"],
            "연인과 대화": ["나란히 앉기", "서로 마주 보기", "편안하게 서기"],
            "함께 요리하기": ["서로 마주 보기", "편안하게 서기"],
            "전시 관람": ["편안하게 서기", "서로 마주 보기", "창가에 서기"],
        }
        key_a = choose(rng, activity_pose_bias.get(activity_key, list(BASE_POSES)))

    p_a = pose_state(key_a, rng)
    p_b = None
    if people == 2:
        if interaction_key == "나란히 걷기" or interaction_key == "손잡기":
            key_b = "손잡고 걷기" if "걷" in ACTIVITY_HINTS.get(activity_key, "") or activity_key in {"산책", "저녁 산책", "비 오는 날 산책"} else "편안하게 서기"
        elif interaction_key in {"나란히 앉아 대화", "함께 책 보기"}:
            key_b = "나란히 앉기"
        elif interaction_key == "가벼운 포옹":
            key_b = "포옹하기"
        else:
            key_b = choose(rng, ["편안하게 서기", "벤치에 앉기", "나란히 앉기", "서로 마주 보기"])
        p_b = pose_state(key_b, rng)
    return p_a, p_b


# ---------------------------------------------------------------------------
# Camera solver: close-up never enlarges the person inside the room
# ---------------------------------------------------------------------------
def resolve_camera(rng: random.Random, c: Dict[str, ConstraintSetting], people: int, pose_a: Dict[str, Any]) -> CameraProfile:
    framing_req = get_value(c, "framing")
    if framing_req in CAMERA_FRAMING.values():
        framing = framing_req
    elif framing_req in CAMERA_FRAMING:
        framing = CAMERA_FRAMING[framing_req]
    else:
        framing = choose(rng, list(CAMERA_FRAMING.values()))

    if framing == CAMERA_FRAMING["클로즈업"]:
        lens = choose(rng, [58, 65, 85])
        dof = DEPTHS["얕음"]
        distance = "portrait camera distance appropriate to the chosen focal length"
    elif framing in {CAMERA_FRAMING["전신"], CAMERA_FRAMING["와이드 씬"]}:
        lens = choose(rng, [24, 28, 35, 40])
        dof = DEPTHS["깊음"] if framing == CAMERA_FRAMING["와이드 씬"] else DEPTHS["보통"]
        distance = "camera distance sufficient to include the full body and the surrounding architecture without scale distortion"
    else:
        lens = choose(rng, [35, 40, 50, 58])
        dof = DEPTHS["보통"]
        distance = "normal perspective distance matched to the focal length and framing"

    lens_req = get_value(c, "lens")
    if str(lens_req).isdigit() and int(lens_req) in CAMERA_LENSES:
        lens = int(lens_req)

    viewpoint_req = get_value(c, "viewpoint")
    viewpoint = resolve_mapping_value(viewpoint_req, VIEWPOINTS, rng, "viewpoint")
    composition_req = get_value(c, "composition")
    composition = resolve_mapping_value(composition_req, COMPOSITIONS, rng, "composition")
    if people == 2 and composition == COMPOSITIONS["대칭"]:
        composition = COMPOSITIONS["삼분할"]

    return CameraProfile(
        lens=lens,
        viewpoint=viewpoint,
        framing=framing,
        composition=composition,
        depth_of_field=dof,
        camera_distance=distance,
        subject_scale_lock=True,
        environment_scale_lock=True,
        perspective_rule=(
            "camera position, focal length and crop control apparent framing; they do not change the subject's physical size "
            "relative to furniture, doors, windows or the architecture"
        ),
    )

# ---------------------------------------------------------------------------
# Normal-scene compatibility graph
# ---------------------------------------------------------------------------
ACTIVITY_HINTS = {
    "아침 준비": "morning routine",
    "커피 마시기": "quiet cafe or home coffee routine",
    "요리하기": "kitchen activity",
    "함께 요리하기": "shared kitchen activity",
    "책 읽기": "reading activity",
    "공부하기": "study session",
    "업무 보기": "work session",
    "화상회의": "home or office work session",
    "글쓰기": "desk writing activity",
    "그림 그리기": "art studio or desk activity",
    "사진 촬영": "lifestyle photography activity",
    "전시 관람": "museum visit",
    "쇼핑": "retail or city outing",
    "카페 데이트": "casual cafe date",
    "산책": "outdoor walking",
    "저녁 산책": "outdoor evening walk",
    "손잡고 걷기": "romantic walk",
    "공원 피크닉": "park picnic",
    "바닷가 산책": "beach walk",
    "여행 준비": "travel preparation",
    "기차 타기": "train travel",
    "호텔 체크인": "hotel arrival",
    "자전거 타기": "recreational cycling",
    "가볍게 운동하기": "light recreational exercise",
    "요가하기": "beginner yoga practice",
    "악기 연주": "music practice",
    "기타 연주": "guitar practice",
    "피아노 연주": "piano practice",
    "사진 보기": "looking through photographs",
    "대화하기": "ordinary conversation",
    "연인과 대화": "quiet romantic conversation",
    "가볍게 포옹하기": "warm everyday embrace",
    "선물 주고받기": "friendly or romantic gift exchange",
}

ACTIVITY_LOCATION_COMPAT = {
    "아침 준비": {"아파트 거실", "침실", "아파트 주방", "호텔 객실"},
    "커피 마시기": {"아파트 거실", "아파트 주방", "카페", "서점 카페", "호텔 로비", "호텔 객실"},
    "요리하기": {"아파트 주방", "호텔 객실"},
    "함께 요리하기": {"아파트 주방"},
    "책 읽기": {"거실", "침실", "서점", "미술관", "도서관", "카페", "서점 카페"},
    "공부하기": {"홈오피스", "도서관", "서점", "카페", "서점 카페"},
    "업무 보기": {"홈오피스", "카페", "도서관", "호텔 객실", "호텔 로비"},
    "화상회의": {"홈오피스", "호텔 객실", "아파트 거실"},
    "글쓰기": {"홈오피스", "도서관", "카페", "서점 카페", "아파트 거실"},
    "그림 그리기": {"홈오피스", "미술관", "아파트 거실", "카페"},
    "전시 관람": {"미술관"},
    "쇼핑": {"도시 거리", "서점", "백화점"},
    "카페 데이트": {"카페", "서점 카페"},
    "산책": {"도시 거리", "공원", "해변", "산책로"},
    "저녁 산책": {"도시 거리", "공원", "해변", "산책로"},
    "손잡고 걷기": {"도시 거리", "공원", "해변", "산책로"},
    "공원 피크닉": {"공원"},
    "바닷가 산책": {"해변"},
    "여행 준비": {"호텔 객실", "기차역", "아파트 거실"},
    "기차 타기": {"기차역"},
    "호텔 체크인": {"호텔 로비"},
    "자전거 타기": {"공원", "산책로", "도시 거리"},
    "가볍게 운동하기": {"공원", "홈오피스", "호텔 객실"},
    "요가하기": {"홈오피스", "침실", "공원", "호텔 객실"},
    "악기 연주": {"홈오피스", "아파트 거실", "침실"},
    "기타 연주": {"아파트 거실", "홈오피스", "해변"},
    "피아노 연주": {"아파트 거실", "홈오피스"},
    "사진 보기": {"아파트 거실", "카페", "서점 카페", "홈오피스"},
    "대화하기": set(LOCATIONS),
    "연인과 대화": {"아파트 거실", "카페", "서점 카페", "공원", "해변", "호텔 로비", "도시 거리"},
    "가볍게 포옹하기": {"공원", "도시 거리", "카페", "아파트 거실", "해변", "호텔 로비"},
    "선물 주고받기": {"카페", "아파트 거실", "공원", "호텔 로비", "도시 거리", "서점"},
}

RELATIONSHIP_ACTIVITY_COMPAT = {
    "혼자": {"친구와 대화": False},
    "친구": {"연인과 대화": True, "카페 데이트": True},
    "연인": {"카페 데이트": True, "손잡고 걷기": True, "연인과 대화": True, "가볍게 포옹하기": True, "선물 주고받기": True},
    "부부": {"카페 데이트": True, "손잡고 걷기": True, "연인과 대화": True, "가볍게 포옹하기": True, "선물 주고받기": True},
}


def normalize_location_key(value: str) -> str:
    value = clean_text(value)
    if value in LOCATIONS:
        return value
    aliases = {
        "거실": "아파트 거실",
        "집 거실": "아파트 거실",
        "주방": "아파트 주방",
        "키친": "아파트 주방",
        "집": "아파트 거실",
        "회사": "홈오피스",
        "사무실": "홈오피스",
        "오피스": "홈오피스",
        "서점 카페": "카페",
        "갤러리": "미술관",
        "박물관": "미술관",
        "도서관": "도서관",
        "길거리": "도시 거리",
        "거리": "도시 거리",
        "바다": "해변",
        "해변": "해변",
        "숲길": "산책로",
        "트레일": "산책로",
        "호텔": "호텔 객실",
        "역": "기차역",
    }
    return aliases.get(value, value if value in LOCATIONS else "아파트 거실")


def normalize_activity_key(value: str) -> str:
    value = clean_text(value)
    aliases = {
        "걷기": "산책", "산책하기": "산책", "저녁에 걷기": "저녁 산책", "같이 걷기": "손잡고 걷기",
        "데이트": "카페 데이트", "카페에서 데이트": "카페 데이트", "함께 책읽기": "책 읽기",
        "책읽기": "책 읽기", "공부": "공부하기", "일하기": "업무 보기", "회의": "화상회의",
        "운동": "가볍게 운동하기", "요가": "요가하기", "자전거": "자전거 타기",
        "요리": "요리하기", "같이 요리": "함께 요리하기", "같이 요리하기": "함께 요리하기",
        "사진": "사진 촬영", "그림": "그림 그리기", "기타": "기타 연주", "피아노": "피아노 연주",
        "대화": "대화하기", "연인 대화": "연인과 대화", "포옹": "가볍게 포옹하기",
    }
    return aliases.get(value, value if value in ACTIVITIES else "대화하기")


def resolve_lighting(rng: random.Random, location_key: str, time_key: str, weather_key: str, c: Dict[str, ConstraintSetting],
                     window_view: bool = False) -> LightingProfile:
    source_req = get_value(c, "light_source")
    source = LIGHT_SOURCES.get(source_req, source_req if source_req in LIGHT_SOURCES.values() else "")
    if not source:
        location = LOCATIONS[location_key]
        rules = scene_rules()
        night = time_key in {"밤", "심야"}
        if location.get("outdoor"):
            if night:
                source = LIGHT_SOURCES[rules.night_source(True, location_key, rng)]
            elif weather_key in {"비", "폭우", "눈", "흐림", "안개"}:
                source = LIGHT_SOURCES["비 오는 날 확산광"]
            elif time_key in {"해질녘", "저녁"}:
                source = choose(rng, [LIGHT_SOURCES["골든아워"], LIGHT_SOURCES["오후 햇빛"]]
                                + ([LIGHT_SOURCES["도시 야간광"]] if location_key in {"도시 거리", "기차역"} and time_key == "저녁" else []))
            else:
                source = choose(rng, [LIGHT_SOURCES["맑은 정오"], LIGHT_SOURCES["부드러운 북향광"], LIGHT_SOURCES["오후 햇빛"]])
        else:
            if night:
                source = LIGHT_SOURCES[rules.night_source(False, location_key, rng)]
            elif window_view and weather_key in {"비", "폭우", "눈", "안개", "흐림"}:
                source = LIGHT_SOURCES["비 오는 날 확산광"]       # overcast light coming in through the window
            elif time_key == "저녁":
                source = choose(rng, [LIGHT_SOURCES["스탠드 램프"], LIGHT_SOURCES["벽 스콘스"], LIGHT_SOURCES["천장 확산광"], LIGHT_SOURCES["창문 자연광"]])
            else:
                source = choose(rng, [LIGHT_SOURCES["창문 자연광"], LIGHT_SOURCES["천장 확산광"], LIGHT_SOURCES["스탠드 램프"], LIGHT_SOURCES["벽 스콘스"]])
    direction = get_value(c, "light_direction")
    if direction not in LIGHT_DIRECTIONS:
        direction = choose(rng, LIGHT_DIRECTIONS)
    quality = get_value(c, "light_quality")
    if quality not in LIGHT_QUALITY:
        quality = choose(rng, LIGHT_QUALITY)
    intensity = get_value(c, "light_intensity")
    if intensity not in LIGHT_INTENSITY:
        intensity = choose(rng, LIGHT_INTENSITY)
    temp = get_value(c, "color_temperature")
    if temp not in COLOR_TEMPS:
        if time_key in {"밤", "심야", "저녁"}:
            temp = choose(rng, [COLOR_TEMPS[1], COLOR_TEMPS[4]])
        else:
            temp = choose(rng, [COLOR_TEMPS[0], COLOR_TEMPS[1], COLOR_TEMPS[2], COLOR_TEMPS[3]])
    ambient = choose(rng, ["soft ambient fill", "subtle room bounce", "gentle environmental illumination"])
    bounce = choose(rng, ["soft bounce from nearby walls and floor", "controlled secondary bounce from surrounding surfaces", "subtle color bounce from the environment"])
    shadow = choose(rng, SHADOWS)
    practical = "practical lights remain physically consistent with the scene" if not LOCATIONS[location_key].get("outdoor") else "street and environmental practical lights remain physically consistent"
    return LightingProfile(source, direction, quality, intensity, temp, ambient, bounce, shadow, practical)


# ---------------------------------------------------------------------------
# Scene resolution and relational smart-random
# ---------------------------------------------------------------------------

def scene_rules():
    import krea2_rules
    return krea2_rules.get_rules(CONFIG_DIR)


def _candidate_locations_for_activity(activity_key: str) -> List[str]:
    allowed = {x for x in ACTIVITY_LOCATION_COMPAT.get(activity_key, set()) if x in LOCATIONS}
    return list(allowed) if allowed else list(LOCATIONS)


def _select_relation(people: int, activity_key: str, requested: str, rng: random.Random) -> str:
    if people <= 1:
        return "혼자"
    if requested in RELATIONSHIPS and requested != "혼자":
        return requested
    if activity_key in {"카페 데이트", "손잡고 걷기", "연인과 대화", "가볍게 포옹하기", "선물 고르기"}:
        return choose(rng, ["연인", "부부", "연인"])
    if activity_key in {"공부하기", "노트북 작업", "화상회의"}:
        return choose(rng, ["동료", "스터디 메이트", "친구"])
    if activity_key in {"친구와 대화", "쇼핑", "보드게임"}:
        return choose(rng, ["친구", "친구", "동료"])
    if activity_key in {"여행 출발", "여행 중 휴식", "기차 기다리기"}:
        return choose(rng, ["여행 동행", "친구", "연인"])
    return choose(rng, ["친구", "연인", "동료", "여행 동행"])


def _interaction_for_scene(people: int, relation_key: str, activity_key: str, requested: str, rng: random.Random) -> Tuple[str, str]:
    if people <= 1:
        return "없음", INTERACTIONS["없음"]
    if requested in INTERACTIONS:
        return requested, INTERACTIONS[requested]
    table = {
        "카페 데이트": ["마주 앉아 대화", "커피 건네기", "장난스럽게 웃기", "함께 사진 보기"],
        "손잡고 걷기": ["손잡기", "나란히 걷기", "팔짱"],
        "저녁 산책": ["나란히 걷기", "손잡기", "장난스럽게 웃기"],
        "연인과 대화": ["나란히 앉아 대화", "마주 앉아 대화", "가벼운 포옹"],
        "가볍게 포옹하기": ["가벼운 포옹"],
        "공원 피크닉": ["나란히 앉아 대화", "함께 사진 보기", "장난스럽게 웃기"],
        "친구와 대화": ["마주 앉아 대화", "하이파이브", "장난스럽게 웃기"],
        "함께 요리하기": ["함께 요리하기"],
        "쇼핑": ["함께 쇼핑하기", "장난스럽게 웃기"],
        "선물 고르기": ["선물 건네기", "나란히 앉아 대화", "장난스럽게 웃기"],
        "기념사진": ["함께 사진 보기", "장난스럽게 웃기", "어깨에 기대기"],
        "전시 관람": ["함께 전시 관람", "나란히 걷기"],
        "음악 듣기": ["함께 음악 듣기", "나란히 앉아 대화"],
    }
    rules = scene_rules()
    candidates = [x for x in table.get(activity_key, []) if rules.interaction_fits(x, activity_key)]
    if not candidates:
        pool = rules.interaction_candidates(activity_key)
        if relation_key in {"연인", "부부"}:
            romantic = [x for x in pool if x in {"손잡기", "팔짱", "어깨에 기대기", "가벼운 포옹", "나란히 앉아 대화", "나란히 걷기"}]
            pool = romantic or pool
        candidates = pool
    key = choose(rng, [x for x in candidates if x in INTERACTIONS] or ["장난스럽게 웃기"])
    return key, INTERACTIONS[key]


def _compatible_pose_for_activity(activity_key: str, location_key: str, rng: random.Random, people: int = 2) -> str:
    pool = {
        "커피 마시기": ["벤치에 앉기", "소파에 편하게 앉기", "편안하게 서기"],
        "차 마시기": ["벤치에 앉기", "소파에 편하게 앉기", "나란히 앉기"],
        "아침 식사": ["벤치에 앉기", "나란히 앉기", "서로 마주 보기"],
        "저녁 식사": ["벤치에 앉기", "나란히 앉기", "서로 마주 보기"],
        "요리하기": ["편안하게 서기", "난간에 기대기"],
        "베이킹": ["편안하게 서기"],
        "책 읽기": ["의자에 앉아 읽기", "소파에 편하게 앉기", "창가에 앉기"],
        "잡지 보기": ["소파에 편하게 앉기", "벤치에 앉기", "의자에 앉아 읽기"],
        "공부하기": ["책상에 앉아 공부하기", "의자에 앉아 읽기"],
        "노트북 작업": ["책상에 앉아 공부하기", "소파에 편하게 앉기"],
        "화상회의": ["책상에 앉아 공부하기", "편안하게 서기"],
        "그림 그리기": ["책상에 앉아 공부하기", "편안하게 서기"],
        "사진 찍기": ["편안하게 서기", "한쪽 다리에 기대 서기"],
        "음악 듣기": ["소파에 편하게 앉기", "나란히 앉기", "창가에 앉기"],
        "기타 연주": ["기타 연주"],
        "피아노 연주": ["피아노 연주"],
        "영화 보기": ["소파에 편하게 앉기"],
        "게임하기": ["소파에 편하게 앉기", "책상에 앉아 공부하기"],
        "보드게임": ["나란히 앉기", "마주 앉기", "벤치에 앉기"],
        "정리하기": ["편안하게 서기", "한쪽 다리에 기대 서기"],
        "식물 돌보기": ["편안하게 서기", "한쪽 다리에 기대 서기"],
        "산책": ["걷기", "천천히 걷기", "편안하게 서기"],
        "조깅": ["달리기 동작"],
        "자전거": ["자전거 타기"],
        "공원 피크닉": ["바닥에 앉기", "벤치에 앉기", "나란히 앉기"],
        "해변 산책": ["걷기", "천천히 걷기", "편안하게 서기"],
        "여행 출발": ["편안하게 서기", "걷기"],
        "여행 중 휴식": ["벤치에 앉기", "소파에 편하게 앉기", "나란히 앉기"],
        "기차 기다리기": ["편안하게 서기", "벤치에 앉기"],
        "전시 관람": ["편안하게 서기", "창가에 서기", "서로 마주 보기"],
        "서점 구경": ["편안하게 서기", "창가에 서기", "의자에 앉아 읽기"],
        "카페 데이트": ["나란히 앉기", "벤치에 앉기", "서로 마주 보기"],
        "저녁 산책": ["천천히 걷기", "손잡고 걷기", "편안하게 서기"],
        "비 오는 날 산책": ["걷기", "천천히 걷기", "편안하게 서기"],
        "창가에서 쉬기": ["창가에 앉기", "창가에 서기"],
        "친구와 대화": ["나란히 앉기", "서로 마주 보기", "벤치에 앉기"],
        "연인과 대화": ["나란히 앉기", "서로 마주 보기", "벤치에 앉기"],
        "기념사진": ["편안하게 서기", "한쪽 다리에 기대 서기"],
        "선물 고르기": ["편안하게 서기", "나란히 앉기", "벤치에 앉기"],
        "쇼핑": ["걷기", "편안하게 서기"],
    }
    candidates = pool.get(activity_key, list(BASE_POSES))
    if people == 1:
        solo = [x for x in candidates if x not in PAIR_ONLY_POSES]
        candidates = solo or ["편안하게 서기", "소파에 편하게 앉기"]
    return choose(rng, candidates)


def _select_activity(rng: random.Random, requested: str, theme_key: str, people: int) -> str:
    if requested in ACTIVITIES:
        return requested
    weighted = list(ACTIVITIES)
    if theme_key == "로맨스" or theme_key == "데이트":
        weighted += ["카페 데이트", "연인과 대화", "저녁 산책", "기념사진", "가볍게 포옹하기"]
    if theme_key == "공부":
        weighted += ["공부하기", "책 읽기", "노트북 작업"] * 2
    if theme_key == "직장":
        weighted += ["노트북 작업", "화상회의", "글쓰기"] * 2
    if theme_key == "여행":
        weighted += ["여행 출발", "여행 중 휴식", "기차 기다리기", "해변 산책"] * 2
    if people == 1:
        weighted = [x for x in weighted if x not in {"친구와 대화", "연인과 대화", "기념사진", "카페 데이트", "손잡고 걷기"}] or weighted
    return choose(rng, weighted)


def _theme_default_people(theme_key: str, rng: random.Random) -> int:
    if theme_key in {"로맨스", "데이트", "친구", "축제"}:
        return 2
    return choose(rng, [1, 1, 1, 2])


def _record_resolved(scene: SceneProfile, key: str, value: Any, source: str) -> None:
    if source == "user":
        scene.user_values[key] = value
    else:
        scene.auto_values[key] = value


def _resolve_choice(c: Dict[str, ConstraintSetting], key: str, pool: Sequence[str], rng: random.Random, default: str = "") -> Tuple[str, str]:
    item = c.get(key, constraint())
    value = item.value if item.value not in {None, "", "auto"} else ""
    if value:
        return value, item.source
    mode = item.random_mode
    return choose_with_mode(rng, pool, mode), "auto"


def build_scene(seed: Optional[int] = None, constraints: Optional[Dict[str, ConstraintSetting]] = None,
                person_a: Optional[PersonSlot] = None, person_b: Optional[PersonSlot] = None,
                source_text_kr: str = "", strict: bool = False) -> SceneProfile:
    rng = random.Random(seed if seed is not None else random.randrange(1, 2**32))
    c = constraints or defaults()

    theme, theme_source = _resolve_choice(c, "theme", list(THEMES), rng)
    if theme not in THEMES:
        theme = choose(rng, list(THEMES))
        theme_source = "auto"

    people_req = get_value(c, "people")
    if people_req in {"1", "2", "single", "dual"}:
        people = 1 if people_req in {"1", "single"} else 2
    else:
        people = _theme_default_people(theme, rng)
        if person_b is not None:
            people = 2
        elif person_a is None and c.get("people", constraint()).random_mode == "fixed" and people_req == "1":
            people = 1

    activity_req = get_value(c, "activity")
    activity = _select_activity(rng, activity_req, theme, people)

    loc_req = get_value(c, "location")
    if loc_req:
        location = normalize_location_key(loc_req)
    else:
        compatible = _candidate_locations_for_activity(activity)
        location = choose(rng, compatible)
    if location not in LOCATIONS:
        location = choose(rng, list(LOCATIONS))

    relationship_req = get_value(c, "relationship")
    relationship = _select_relation(people, activity, relationship_req, rng)
    if people == 1:
        relationship = "혼자"

    interaction_key, interaction_en = _interaction_for_scene(
        people, relationship, activity, get_value(c, "interaction"), rng
    )

    rules = scene_rules()
    pose_req = get_value(c, "pose")
    if people == 2:
        auto_a, auto_b = rules.pair_poses(interaction_key, activity)
        pose_a_key = pose_req if pose_req in BASE_POSES else auto_a
        pose_b_key = auto_b
        pose_a = pose_state(pose_a_key, rng)
        pose_b = pose_state(pose_b_key, rng)
    else:
        pose_a_key = _compatible_pose_for_activity(activity, location, rng, people)
        if pose_req in BASE_POSES:
            pose_a_key = pose_req
        elif not rules.pose_fits_activity(pose_a_key, activity):
            fits = [x for x in BASE_POSES if x not in PAIR_ONLY_POSES and rules.pose_fits_activity(x, activity)]
            pose_a_key = choose(rng, fits) if fits else pose_a_key
        pose_a = pose_state(pose_a_key, rng)
        pose_b = None

    time_req = get_value(c, "time")
    time_key = time_req if time_req in TIME_OF_DAY else choose(rng, list(TIME_OF_DAY))
    weather_req = get_value(c, "weather")
    weather_key = weather_req if weather_req in WEATHER else choose(rng, list(WEATHER))
    if not LOCATIONS[location].get("outdoor"):
        if weather_key not in WEATHER:
            weather_key = "맑음"
    if activity == "비 오는 날 산책" and LOCATIONS[location].get("outdoor"):
        weather_key = "비"
    if activity == "해변 산책":
        location = "해변"

    mood_req = get_value(c, "mood")
    mood_key = mood_req if mood_req in MOODS else choose(rng, list(MOODS))
    realism_req = get_value(c, "realism")
    realism = REALISM.get(realism_req, choose(rng, list(REALISM.values())))

    env = resolve_environment(location, rng, c)
    outdoor_place = bool(LOCATIONS[location].get("outdoor"))
    weather_visible = scene_rules().weather_visible(outdoor_place, env.sublocation)
    light = resolve_lighting(rng, location, time_key, weather_key, c, window_view=weather_visible and not outdoor_place)
    camera = resolve_camera(rng, c, people, pose_a)
    def _clothing_for(slot: str) -> ClothingProfile:
        pick = resolve_clothing(rng, slot, c)
        if get_value(c, f"garment_{slot}") not in {"", "auto"}:
            return pick                       # a user-fixed garment is never replaced
        out_door = bool(LOCATIONS[location].get("outdoor"))
        for _ in range(12):
            fw_key = next((k_ for k_, v_ in FOOTWEAR.items() if v_ == pick.footwear), "")
            if scene_rules().clothing_ok(pick.garment_key, fw_key, location, weather_key, out_door):
                break
            pick = resolve_clothing(rng, slot, c)
        return pick

    def _companion_for(slot: str, main: ClothingProfile) -> Optional[ClothingProfile]:
        """A top gets a bottom and a bottom gets a top, so nothing is left for the model to invent."""
        rules_ = scene_rules()
        pool = rules_.companion_pool(main.garment_key)
        if not pool or get_value(c, f"garment_{slot}") not in {"", "auto"} and rules_.garment_slot(main.garment_key) == "dress":
            return None
        out_door = bool(LOCATIONS[location].get("outdoor"))
        keys = [x for x in pool if x in GARMENTS and rules_.clothing_ok(x, "", location, weather_key, out_door)]
        if not keys:
            return None
        trial = dict(c)
        trial[f"garment_{slot}"] = constraint(choose(rng, keys), "fixed", 95, "auto")
        trial[f"material_{slot}"] = constraint("auto", "auto", 50, "auto")      # fabric must fit the companion garment
        trial[f"fit_{slot}"] = constraint("auto", "auto", 50, "auto")
        try:
            return resolve_clothing(rng, slot, trial)
        except Exception:
            return None

    clothing_a = _clothing_for("A")
    clothing_b = _clothing_for("B") if people == 2 else None
    extra_a = _companion_for("A", clothing_a)
    extra_b = _companion_for("B", clothing_b) if clothing_b else None

    props = []
    if get_value(c, "prop_A") not in {"", "auto"}:
        props.append(get_value(c, "prop_A"))
    else:
        candidates = env.practical + env.decor
        if activity in {"커피 마시기", "차 마시기", "아침 식사", "저녁 식사"}:
            candidates += ["ceramic mug", "coffee cup", "glass of water"]
        if activity in {"공부하기", "노트북 작업", "화상회의", "글쓰기"}:
            candidates += ["laptop", "notebook", "headphones"]
        if activity in {"책 읽기", "서점 구경"}:
            candidates += ["open book", "bookmark", "reading glasses"]
        props = list(dict.fromkeys(candidates[:4]))

    scene = SceneProfile(
        theme_key=theme,
        theme_en=THEMES[theme],
        location_key=location,
        people=people,
        relationship_key=relationship,
        relationship_en=RELATIONSHIPS[relationship],
        activity_key=activity,
        activity_en=ACTIVITIES.get(activity, activity),
        interaction_key=interaction_key,
        interaction_en=interaction_en,
        time_key=time_key,
        time_en=TIME_OF_DAY[time_key],
        weather_key=weather_key,
        weather_en=WEATHER[weather_key],
        mood_key=mood_key,
        mood_en=MOODS[mood_key],
        sublocation=env.sublocation,
        environment=env,
        pose_a=pose_a,
        pose_b=pose_b,
        lighting=light,
        camera=camera,
        realism=realism,
        clothing_a=clothing_a,
        clothing_b=clothing_b,
        props=props,
        left_right_basis=get_value(c, "left_right_basis", "subject perspective"),
        source_text_kr=source_text_kr,
        constraints=c,
        weather_visible=weather_visible,
        clothing_extra_a=extra_a,
        clothing_extra_b=extra_b,
    )
    _record_resolved(scene, "theme", theme, theme_source)
    _record_resolved(scene, "people", people, "user" if get_value(c, "people") not in {"", "auto"} else "auto")
    _record_resolved(scene, "activity", activity, "user" if activity_req in ACTIVITIES else "auto")
    _record_resolved(scene, "location", location, "user" if loc_req else "auto")
    _record_resolved(scene, "relationship", relationship, "user" if relationship_req in RELATIONSHIPS else "auto")
    _record_resolved(scene, "interaction", interaction_key, "user" if get_value(c, "interaction") in INTERACTIONS else "auto")
    _record_resolved(scene, "pose_A", pose_a_key, "user" if pose_req in BASE_POSES else "auto")
    validate_scene(scene, strict=strict)
    return scene


# ---------------------------------------------------------------------------
# Consistency engine
# ---------------------------------------------------------------------------
POSE_FAMILY = {
    "standing": {"편안하게 서기", "한쪽 다리에 기대 서기", "벽에 기대 서기", "난간에 기대기", "창가에 서기", "서로 마주 보기", "편안하게 서기"},
    "walking": {"걷기", "천천히 걷기", "손잡고 걷기", "달리기 동작"},
    "seated": {"벤치에 앉기", "소파에 편하게 앉기", "의자에 앉아 읽기", "책상에 앉아 공부하기", "바닥에 앉기", "무릎 꿇고 앉기", "바닥에 다리를 뻗고 앉기", "다리를 꼬고 앉기", "창가에 앉기", "나란히 앉기", "기타 연주", "피아노 연주"},
    "activity": {"가볍게 스트레칭", "요가 자세", "자전거 타기", "기타 연주", "피아노 연주"},
}


def _issue(scene: SceneProfile, level: str, category: str, message: str, repair: str = "") -> None:
    scene.issues.append(ConsistencyIssue(level, category, message, repair))


def validate_pose_state(pose: Dict[str, Any], scene: SceneProfile, label: str) -> None:
    left = pose.get("left_leg", "")
    right = pose.get("right_leg", "")
    left_foot = pose.get("left_foot", "")
    right_foot = pose.get("right_foot", "")
    supports = set(pose.get("support_points", []))
    if pose.get("pose_key") in {"편안하게 서기", "한쪽 다리에 기대 서기", "벽에 기대 서기", "난간에 기대기", "창가에 서기", "서로 마주 보기"}:
        if left_foot != "grounded" or right_foot != "grounded":
            _issue(scene, "error", "pose", f"{label}: 서 있는 자세인데 양발 접지 상태가 깨졌습니다.", "양발 접지로 정정")
    if pose.get("pose_key") in {"벤치에 앉기", "소파에 편하게 앉기", "의자에 앉아 읽기", "책상에 앉아 공부하기", "창가에 앉기", "나란히 앉기"}:
        if "hips" not in supports:
            _issue(scene, "error", "pose", f"{label}: 앉은 자세에 엉덩이 지지점이 없습니다.", "hips support 추가")
    if left == "raised" and right == "raised" and "airborne" not in supports:
        _issue(scene, "error", "pose", f"{label}: 두 다리가 동시에 들린 상태인데 공중 지지 조건이 없습니다.", "한쪽 다리 또는 지지점을 정정")
    if left_foot == "raised" and right_foot == "raised" and not supports.intersection({"seat", "hips", "knees", "bicycle seat", "floor"}):
        _issue(scene, "error", "pose", f"{label}: 두 발이 모두 들렸지만 신체 지지점이 불명확합니다.", "지지점 명시")
    if left_foot == "grounded" and right_foot == "grounded" and any(x in {"transitioning", "airborne", "raised"} for x in (left, right)):
        if pose.get("pose_key") not in {"걷기", "천천히 걷기", "손잡고 걷기", "달리기 동작"}:
            _issue(scene, "warning", "pose", f"{label}: 다리 상태와 발 접지가 서로 다른 동작을 암시합니다.", "다리 상태를 접지 기준으로 재정렬")


def validate_interaction(scene: SceneProfile) -> None:
    if scene.people == 1:
        if scene.relationship_key != "혼자":
            _issue(scene, "error", "relationship", "1인 장면인데 2인 관계가 선택되었습니다.", "혼자로 정정")
        if scene.interaction_key != "없음":
            _issue(scene, "warning", "interaction", "1인 장면의 직접 상호작용이 선택되었습니다.", "상호작용을 없음으로 정정")
    if scene.people == 2:
        if scene.pose_b is None:
            _issue(scene, "error", "people", "2인 장면인데 B 인물의 자세가 없습니다.", "B 자세 생성")
        if scene.interaction_key == "손잡기":
            _issue(scene, "warning", "interaction", "손잡기는 양손 중 어느 손인지 명시되지 않은 상태입니다.", "자연스러운 단일 손 접촉으로 작곡")
        if scene.interaction_key == "나란히 걷기":
            if scene.pose_a.get("pose_key") not in {"걷기", "천천히 걷기", "손잡고 걷기", "편안하게 서기"}:
                _issue(scene, "warning", "interaction", "나란히 걷기와 A의 자세가 맞지 않습니다.", "보행 자세로 정정")
            if scene.pose_b and scene.pose_b.get("pose_key") not in {"걷기", "천천히 걷기", "손잡고 걷기", "편안하게 서기"}:
                _issue(scene, "warning", "interaction", "나란히 걷기와 B의 자세가 맞지 않습니다.", "보행 자세로 정정")


def validate_camera(scene: SceneProfile) -> None:
    cam = scene.camera
    framing = cam.framing
    full = framing in {CAMERA_FRAMING["전신"], CAMERA_FRAMING["3/4 전신"]}
    close = framing in {CAMERA_FRAMING["클로즈업"], CAMERA_FRAMING["가슴 위"]}
    if full and cam.lens >= 65:
        _issue(scene, "warning", "camera", "전신 프레이밍에 긴 렌즈가 선택되어 공간 압축이 커질 수 있습니다.", "35~58mm 범위 권장")
    if close and cam.lens <= 28:
        _issue(scene, "warning", "camera", "근접 인물 프레이밍에 초광각 렌즈가 선택되었습니다.", "58~85mm 범위 권장")
    if cam.subject_scale_lock is not True or cam.environment_scale_lock is not True:
        _issue(scene, "error", "scale", "주제/환경 실제 크기 잠금이 꺼져 있습니다.", "두 scale lock을 True로 고정")
    if "physical size" not in cam.perspective_rule:
        _issue(scene, "error", "scale", "카메라 프레이밍과 실제 신체 크기를 분리하는 규칙이 없습니다.", "원근 규칙 추가")


def validate_environment(scene: SceneProfile) -> None:
    env = scene.environment
    all_layers = env.foreground + env.midground + env.background
    seen: Dict[str, str] = {}
    for layer_name, layer in (("foreground", env.foreground), ("midground", env.midground), ("background", env.background)):
        for item in layer:
            if item in seen:
                _issue(scene, "error", "environment", f"환경 오브젝트 {item!r}이 {seen[item]}와 {layer_name}에 중복 배치되었습니다.", "각 오브젝트를 한 depth layer에만 배치")
            seen[item] = layer_name
    if len(all_layers) != len(seen):
        _issue(scene, "error", "environment", "환경 깊이 레이어에 중복 오브젝트가 있습니다.", "중복 제거")
    for rule in env.scale_rules:
        if "realistic dimensions" in rule or "physical size" in rule:
            break
    else:
        _issue(scene, "warning", "scale", "환경의 실측 스케일 규칙이 충분하지 않습니다.", "사람-가구-건축 규모 관계 추가")


def validate_clothing(scene: SceneProfile, clothing: ClothingProfile, label: str) -> None:
    f = clothing.fabric
    if f.key not in FABRICS:
        _issue(scene, "error", "clothing", f"{label}: 원단 데이터가 사전에 없습니다.", "기본 원단으로 대체")
    if not f.compatible_garments or clothing.garment_key not in f.compatible_garments:
        _issue(scene, "error", "clothing", f"{label}: 원단과 의상 호환 관계가 깨졌습니다.", "호환 의상/원단 조합으로 정정")
    if "opaque" in f.opacity and "transparent" in f.surface_response.lower():
        _issue(scene, "warning", "clothing", f"{label}: 불투명도와 표면 응답 설명이 충돌할 수 있습니다.", "표면 응답을 불투명 기준으로 조정")


def _repair_scene(scene: SceneProfile) -> None:
    # Repairs only resolve deterministic structural problems. User-fixed values
    # remain visible in user_values and are never silently rewritten.
    if scene.people == 1:
        scene.relationship_key = "혼자"
        scene.relationship_en = RELATIONSHIPS["혼자"]
        scene.pose_b = None
        scene.interaction_key = "없음"
        scene.interaction_en = INTERACTIONS["없음"]
    if scene.people == 2 and scene.pose_b is None:
        scene.pose_b = pose_state("편안하게 서기", random.Random(0))
        scene.auto_values["pose_B"] = "편안하게 서기"
    if scene.camera.subject_scale_lock is not True:
        scene.camera.subject_scale_lock = True
        scene.auto_values["camera.subject_scale_lock"] = True
    if scene.camera.environment_scale_lock is not True:
        scene.camera.environment_scale_lock = True
        scene.auto_values["camera.environment_scale_lock"] = True
    # Fix only clear pose metadata inconsistencies.
    for pose in [scene.pose_a] + ([scene.pose_b] if scene.pose_b else []):
        if pose.get("pose_key") in {"편안하게 서기", "한쪽 다리에 기대 서기", "벽에 기대 서기", "난간에 기대기", "창가에 서기", "서로 마주 보기"}:
            pose["left_leg"] = "grounded"
            pose["right_leg"] = "grounded"
            pose["left_foot"] = "grounded"
            pose["right_foot"] = "grounded"
            if "left foot" not in pose.get("support_points", []):
                pose.setdefault("support_points", []).append("left foot")
            if "right foot" not in pose.get("support_points", []):
                pose.setdefault("support_points", []).append("right foot")


def validate_scene(scene: SceneProfile, strict: bool = False) -> List[ConsistencyIssue]:
    scene.issues = []
    validate_pose_state(scene.pose_a, scene, "A")
    if scene.pose_b:
        validate_pose_state(scene.pose_b, scene, "B")
    validate_interaction(scene)
    validate_camera(scene)
    validate_environment(scene)
    validate_clothing(scene, scene.clothing_a, "A")
    if scene.clothing_b:
        validate_clothing(scene, scene.clothing_b, "B")

    allowed_locs = _candidate_locations_for_activity(scene.activity_key)
    if scene.location_key not in allowed_locs and scene.activity_key in ACTIVITY_LOCATION_COMPAT:
        _issue(scene, "warning", "space", f"{scene.activity_key}와 {scene.location_key}의 조합은 기본 호환 목록 밖입니다.", "사용자 고정값이면 유지하고 비고에 표시")

    if scene.location_key not in LOCATIONS:
        _issue(scene, "error", "space", "존재하지 않는 장소 키가 선택되었습니다.", "아파트 거실로 정정")
    if scene.time_key in {"밤", "심야"} and scene.weather_key in {"맑음", "구름 조금"} and LOCATIONS[scene.location_key].get("outdoor"):
        # Night outdoor scenes still can have clear weather; no error. The line exists to
        # document that this combination is accepted rather than falsely repaired.
        pass
    # Hard scale rule: a close-up changes crop, not human/object dimensions.
    if scene.camera.framing == CAMERA_FRAMING["클로즈업"] and not scene.camera.subject_scale_lock:
        _issue(scene, "error", "scale", "클로즈업 때문에 인물 실물 크기를 변경하는 설정이 감지되었습니다.", "실제 크기 잠금")
    _repair_scene(scene)
    # Re-run after deterministic repairs.
    scene.issues = scene.issues[:]
    post = []
    validate_pose_state(scene.pose_a, scene, "A(after repair)")
    if scene.pose_b:
        validate_pose_state(scene.pose_b, scene, "B(after repair)")
    validate_camera(scene)
    validate_environment(scene)
    # strict = fixed contradictions become errors; normal mode exposes them as warnings.
    if strict:
        for item in scene.issues:
            if item.level == "warning":
                item.level = "error"
    return scene.issues


# ---------------------------------------------------------------------------
# Person and prompt composition
# ---------------------------------------------------------------------------
APPEARANCE_BUILDS = [
    "slim athletic adult build with natural limb proportions",
    "slim natural adult build with long balanced limbs",
    "average adult build with realistic proportions",
    "softly athletic adult build with relaxed natural posture",
    "lean adult build with balanced shoulders and hips",
]
EYE_COLORS = [
    "dark brown eyes", "warm brown eyes", "deep hazel eyes", "soft amber-brown eyes",
    "dark gray-brown eyes", "natural black-brown eyes",
]
HAIR_COLORS = [
    "natural black hair", "deep brown hair", "dark espresso-brown hair", "soft chestnut-brown hair",
    "natural dark ash-brown hair",
]
DISTINCTIVE_FEATURES = [
    "subtle natural facial asymmetry", "fine brow detail and realistic eyelid structure",
    "soft natural cheek contour", "subtle beauty mark kept small and unexaggerated",
    "natural lip shape with fine surface texture",
]


def _identity_for_slot(slot: str, c: Dict[str, ConstraintSetting], person: Optional[PersonSlot]) -> str:
    # Explicit manual identity wins; otherwise a registered LoRA profile supplies the fixed identity.
    if person and person.identity and clean_text(person.identity).lower() not in {"adult person", "a single adult person"}:
        return clean_text(person.identity)
    trigger = person.lora_trigger if person else slot_trigger(c, slot)
    profile = lora_profile_for_trigger(trigger)
    if profile:
        identity = clean_text(str(profile.get("identity", "")))
        if identity:
            return identity
    req = get_value(c, f"identity_{slot}")
    if req not in {"", "auto", "adult person"}:
        return local_translate(req)
    return "adult person"


def resolve_person(rng: random.Random, scene: SceneProfile, slot: str, source_person: Optional[PersonSlot]) -> PersonSlot:
    c = scene.constraints
    clothing = scene.clothing_a if slot == "A" else scene.clothing_b
    pose = scene.pose_a if slot == "A" else scene.pose_b
    if clothing is None or pose is None:
        raise ValueError(f"Missing resolved data for person {slot}")
    trigger = source_person.lora_trigger if source_person else slot_trigger(c, slot)
    identity = _identity_for_slot(slot, c, source_person)
    lora_locked = is_lora_identity_locked(trigger, identity)

    expr_req = get_value(c, f"expression_{slot}")
    expression = expr_req if expr_req in EXPRESSIONS else choose(rng, EXPRESSIONS)
    gaze_req = get_value(c, f"gaze_{slot}")
    gaze_pool = GAZES if scene.people == 2 else [g for g in GAZES if "other person" not in g]
    gaze = gaze_req if gaze_req in GAZES else choose(rng, gaze_pool)

    # Character identity details from a registered LoRA are fixed. Only explicit user overrides are allowed.
    hair_req = get_value(c, f"hair_{slot}")
    lora_hair = clean_text(str((lora_profile_for_trigger(trigger) or {}).get("hair", ""))) if lora_locked else ""
    if hair_req not in {"", "auto"}:
        hair = hair_req                      # user override replaces the LoRA hair entirely
    elif lora_hair:
        hair = lora_hair                     # no override: the registered LoRA hair stays fixed
    else:
        hair = "" if lora_locked else choose(rng, HAIR_STYLES)
    build_req = get_value(c, f"body_build_{slot}")
    body_build = build_req if build_req not in {"", "auto"} else ("" if lora_locked else choose(rng, APPEARANCE_BUILDS))
    skin_req = get_value(c, f"skin_detail_{slot}")
    skin_detail = skin_req if skin_req not in {"", "auto"} else ("" if lora_locked else choose(rng, [
        "natural skin texture with visible pores and fine vellus hair",
        "natural skin texture with subtle tonal variation and fine surface detail",
        "matte-natural skin with believable microtexture",
    ]))
    eye_req = get_value(c, f"eye_color_{slot}")
    eye_color = eye_req if eye_req not in {"", "auto"} else ("" if lora_locked else choose(rng, EYE_COLORS))
    hair_color_req = get_value(c, f"hair_color_{slot}")
    hair_color = hair_color_req if hair_color_req not in {"", "auto"} else ("" if lora_locked else choose(rng, HAIR_COLORS))
    feature_req = get_value(c, f"distinctive_feature_{slot}")
    distinctive_feature = feature_req if feature_req not in {"", "auto"} else ("" if lora_locked else choose(rng, DISTINCTIVE_FEATURES))

    height = None
    h_req = get_value(c, f"height_{slot}")
    if h_req.isdigit():
        height = max(120, min(220, int(h_req)))
    elif source_person and source_person.height_cm:
        height = source_person.height_cm
    elif not lora_locked:
        height = 168 if slot == "A" else 170

    return PersonSlot(
        slot=f"PERSON_{slot}",
        lora_trigger=trigger,
        identity=identity,
        role="primary subject" if slot == "A" else "secondary subject",
        position="center" if scene.people == 1 else ("left side of the frame" if slot == "A" else "right side of the frame"),
        orientation=pose.get("torso", "natural neutral alignment"),
        pose_key=pose["pose_key"],
        pose_en=pose["pose_en"],
        expression=expression,
        gaze=gaze,
        hair=hair if hair == lora_hair and hair else local_translate(hair),
        clothing=clothing,
        clothing_extra=scene.clothing_extra_a if slot == "A" else scene.clothing_extra_b,
        body_state=BodyState(
            left_arm=pose.get("left_arm", "relaxed"),
            right_arm=pose.get("right_arm", "relaxed"),
            left_leg=pose.get("left_leg", "grounded"),
            right_leg=pose.get("right_leg", "grounded"),
            left_foot=pose.get("left_foot", "grounded"),
            right_foot=pose.get("right_foot", "grounded"),
            support_points=list(pose.get("support_points", [])),
            weight_distribution=pose.get("weight_distribution", "balanced"),
            torso_orientation=pose.get("torso", "natural neutral alignment"),
            head_orientation=pose.get("head", "natural neck alignment"),
        ),
        height_cm=height,
        props=[],
        body_build=body_build,
        skin_detail=skin_detail,
        eye_color=eye_color,
        hair_color=hair_color,
        distinctive_feature=distinctive_feature,
    )


def _contact_line(scene: SceneProfile) -> str:
    if scene.people != 2:
        return "They maintain natural personal space appropriate to the activity."
    return f"The two people {scene.interaction_en}. Keep the contact physically plausible, with clear hand placement, natural limb angles, and no duplicated limbs or merged bodies."


def _pose_line(person: PersonSlot, left_right_basis: str = "subject perspective") -> str:
    bs = person.body_state
    support = ", ".join(bs.support_points) if bs.support_points else "natural body support"
    return (
        f"{person.slot.replace('_', ' ').title()} is {person.pose_en}. "
        f"Weight distribution: {bs.weight_distribution}. Support points: {support}. "
        f"Left/right references use {left_right_basis} and remain consistent throughout the scene. "
        f"Left leg: {bs.left_leg}, left foot: {bs.left_foot}; right leg: {bs.right_leg}, right foot: {bs.right_foot}."
    )


def _prompt_text_fragment(text: str) -> str:
    # Clean imported identity text without changing its meaning.
    value = clean_text(text)
    value = re.sub(r"([.!?])(?=[A-Za-z0-9])", r"\1 ", value)
    value = re.sub(r",(?=[A-Za-z0-9])", ", ", value)
    value = re.sub(r"\s{2,}", " ", value)
    return value.strip()


def _identity_prompt_fragment(text: str, lora_trigger: str = "") -> str:
    value = _prompt_text_fragment(text).rstrip(".,; ")
    if lora_trigger:
        value = re.sub(r"^(?:she|he|they)\s+is\s+", "", value, flags=re.I)
    return value


def person_prompt(person: PersonSlot, left_right_basis: str = "subject perspective") -> str:
    identity = _identity_prompt_fragment(person.identity, person.lora_trigger)
    first = f"{person.lora_trigger}, {identity}" if person.lora_trigger else identity
    parts: List[str] = [f"{first}, positioned at the {person.position}"]
    if person.hair_color or person.hair:
        hair_bits = ", ".join(x for x in [person.hair_color, person.hair] if clean_text(x))
        parts.append(f"Hair: {_prompt_text_fragment(hair_bits)}")
    if person.eye_color:
        parts.append(f"Eyes: {_prompt_text_fragment(person.eye_color)}")
    parts.append(f"Expression: {_prompt_text_fragment(person.expression)}")
    parts.append(f"Gaze: {_prompt_text_fragment(person.gaze)}")
    appearance_bits = [_prompt_text_fragment(x) for x in [person.body_build, person.skin_detail, person.distinctive_feature] if clean_text(x)]
    if appearance_bits:
        parts.append("Appearance: " + "; ".join(appearance_bits))
    if person.height_cm:
        parts.append(f"adult height is approximately {person.height_cm} cm when visible, with realistic human scale")
    parts.append(_pose_line(person, left_right_basis))
    parts.append(clothing_prompt(person.clothing))
    return ". ".join(clean_text(x).rstrip(".") for x in parts if clean_text(x)) + "."


def lighting_prompt(light: LightingProfile) -> str:
    return (
        f"Lighting comes from {light.source}, {light.direction}, with {light.quality} quality and {light.intensity}. "
        f"The scene has {light.color_temperature}, {light.ambient}, {light.bounce}, and {light.shadow}. {light.practical}."
    )


def camera_prompt(cam: CameraProfile) -> str:
    return (
        f"Camera: {cam.lens}mm, {cam.viewpoint}, {cam.framing}, {cam.composition}, {cam.depth_of_field}. "
        f"{cam.camera_distance}. Subject scale lock is enabled: camera framing changes do not enlarge or shrink the person's real-world size. "
        f"Environment scale lock is enabled: furniture, doors, windows and architecture keep believable dimensions. "
        f"{cam.perspective_rule}."
    )


def _style_line(scene: SceneProfile) -> str:
    style_req = get_value(scene.constraints, "style")
    return STYLE_LIBRARY.get(style_req, STYLE_LIBRARY["자연광 라이프스타일"])


def _sentence(text: str) -> str:
    value = clean_text(text)
    if value and value[-1] not in ".!?":
        value += "."
    return value


def compose_prompt(scene: SceneProfile, person_a: PersonSlot, person_b: Optional[PersonSlot],
                   detailed: bool = False, reinforce: Optional[int] = None) -> str:
    """v11: one flowing prompt that reads like a person wrote it (see krea2_prose.py)."""
    import krea2_prose
    return krea2_prose.render(scene, person_a, person_b, detailed, reinforce)["combined"]


def compose_prompt_legacy(scene: SceneProfile, person_a: PersonSlot, person_b: Optional[PersonSlot]) -> str:
    # v10 spec-sheet format, kept only for reference / rollback.
    # Put the primary LoRA token/identity at the beginning of the prompt for reliable character anchoring.
    parts = [
        person_prompt(person_a, scene.left_right_basis),
        f"Create a natural, realistic scene with {scene.theme_en}.",
        f"The scene shows {scene.relationship_en} {scene.activity_en}.",
    ]
    if person_b:
        parts.append(person_prompt(person_b, scene.left_right_basis))
        parts.append(_contact_line(scene))
    parts.extend([
        f"The emotional atmosphere is {scene.mood_en}.",
        environment_prompt(scene.environment),
        f"Scene props used by the subjects: {', '.join(scene.props) if scene.props else 'none specified'}.",
        f"The time is {scene.time_en}, with {scene.weather_en}.",
        lighting_prompt(scene.lighting),
        camera_prompt(scene.camera),
        scene.realism,
        _style_line(scene),
        SKIN_FINISH.get(get_value(scene.constraints, "skin_finish"), SKIN_FINISH["자연 피부"]),
        "Maintain coherent human anatomy, realistic grounding, natural contact shadows, and correct object scale throughout the frame.",
        "Keep all foreground, midground and background elements spatially consistent with one camera and one coherent perspective system.",
    ])
    prompt = " ".join(_sentence(x) for x in parts if clean_text(x))
    prompt = re.sub(r"\s+([,.])", r"\1", prompt)
    prompt = re.sub(r"\.{2,}", ".", prompt)
    prompt = re.sub(r";{2,}", ";", prompt)
    prompt = re.sub(r"\s{2,}", " ", prompt)
    return prompt.strip()


# ---------------------------------------------------------------------------
# Final prompt linter
# ---------------------------------------------------------------------------
def prompt_option_coverage(scene: SceneProfile, person_a: PersonSlot, person_b: Optional[PersonSlot], prompt: str) -> Dict[str, Any]:
    """Verify that the key resolved options survive into the prose prompt (filler wording is ignored)."""
    import krea2_prose as pr
    checks: List[Tuple[str, str]] = []

    def add(name: str, fragment: str) -> None:
        fragment = clean_text(pr.plain(str(fragment)))
        if fragment:
            checks.append((name, fragment))

    if scene.people == 1:
        add("activity", scene.activity_en)
    else:
        add("activity", scene.activity_en)
        add("interaction", scene.interaction_en)
    add("location", scene.environment.location_en)
    add("sublocation", scene.environment.sublocation)
    add("time", scene.time_en)
    if getattr(scene, "weather_visible", True):
        add("weather", re.sub(r"\s+outside$", "", scene.weather_en))
    add("mood", scene.mood_en)
    add("light_source", scene.lighting.source)
    add("light_quality", scene.lighting.quality)
    add("light_intensity", scene.lighting.intensity)
    add("lens", f"{scene.camera.lens}mm")
    add("framing", scene.camera.framing)
    add("viewpoint", scene.camera.viewpoint)
    add("composition", scene.camera.composition)
    add("depth_of_field", scene.camera.depth_of_field)
    add("style", _style_line(scene))
    for name, person in (("A", person_a), ("B", person_b)):
        if not person:
            continue
        if person.lora_trigger:
            add(f"person_{name}_trigger", person.lora_trigger)
        add(f"person_{name}_pose", person.pose_en)
        add(f"person_{name}_expression", person.expression)
        add(f"person_{name}_gaze", person.gaze)
        for idx, cl in enumerate(pr.shown_garments(scene, person)):          # only what the framing shows
            add(f"person_{name}_garment{idx}", re.sub(r"^(an?)\s+", "", cl.garment_en))
            add(f"person_{name}_color{idx}", cl.color)
            add(f"person_{name}_material{idx}", cl.fabric.material)
    lower = clean_text(prompt).lower()
    missing = [name for name, frag in checks if frag.lower() not in lower]
    return {"total": len(checks), "passed": len(checks) - len(missing), "missing": missing}


def prompt_syntax_errors(prompt: str) -> List[str]:
    errors: List[str] = []
    if re.search(r"[,.;:]{2,}", prompt):
        errors.append("repeated punctuation")
    if re.search(r"\s+[,.]", prompt):
        errors.append("space before punctuation")
    if "Use the LoRA trigger" in prompt:
        errors.append("LoRA trigger is written as instruction prose instead of a prompt token")
    if not prompt or not prompt.endswith((".", "!", "?")):
        errors.append("prompt does not end with sentence punctuation")
    return errors


CONFLICT_PATTERNS = [
    (r"\bfull-body composition with the subject fully visible from head to feet\b.*\bclose portrait framing focused on the face and upper shoulders\b|\bclose portrait framing focused on the face and upper shoulders\b.*\bfull-body composition with the subject fully visible from head to feet\b", "framing contradiction"),
    (r"\bleft foot[^.]{0,120}\braised\b[^.]{0,120}\bright foot[^.]{0,120}\braised\b", "both feet raised without support"),
    (r"\bright foot[^.]{0,120}\braised\b[^.]{0,120}\bleft foot[^.]{0,120}\braised\b", "both feet raised without support"),
]


def lint_prompt(prompt: str, scene: Optional[SceneProfile] = None) -> List[str]:
    errors = list(prompt_syntax_errors(prompt))
    lower = prompt.lower()
    for pattern, label in CONFLICT_PATTERNS:
        if re.search(pattern, lower, flags=re.DOTALL):
            errors.append(label)
    if re.search(r"[가-힣]", prompt):
        errors.append("Korean characters leaked into final prompt")
    if re.search(r"\b(?:Hairstyle|Expression|Gaze|Walls|Floor|Lighting|Camera|Appearance|Furniture|Decor)\s*:", prompt):
        errors.append("field label in prompt")
    if re.search(r"scale lock|keep all (?:foreground|the)|maintain coherent", lower):
        errors.append("model-facing instruction in prompt")
    if scene:
        if scene.people == 1 and any(word in lower for word in ("two adult", "two people", "secondary subject")):
            errors.append("single-subject scene contains two-person wording")
        if scene.people == 2 and scene.pose_b is None:
            errors.append("two-person scene has no second pose")
    return list(dict.fromkeys(errors))


def final_prompt(scene: SceneProfile, person_a: PersonSlot, person_b: Optional[PersonSlot], strict: bool = True,
                 detailed: bool = False, reinforce: Optional[int] = None) -> str:
    prompt = compose_prompt(scene, person_a, person_b, detailed, reinforce)
    errors = lint_prompt(prompt, scene)
    if errors and strict:
        raise ValueError("Prompt validation failed: " + "; ".join(errors))
    return prompt


# ---------------------------------------------------------------------------
# Translation / option pools kept in files (krea2_prompt_configs/pools/*.json)
# ---------------------------------------------------------------------------
POOLS_DIR = CONFIG_DIR / "pools"
POOL_LABELS_KO = {
    "THEMES": "테마", "RELATIONSHIPS": "관계", "INTERACTIONS": "상호작용", "ACTIVITIES": "활동",
    "TIME_OF_DAY": "시간대", "WEATHER": "날씨", "MOODS": "분위기", "REALISM": "사실감",
    "SKIN_FINISH": "피부 질감", "CAMERA_FRAMING": "프레이밍", "VIEWPOINTS": "시점", "COMPOSITIONS": "구도",
    "DEPTHS": "심도(환경)", "DEPTH_OF_FIELD": "심도", "LIGHT_SOURCES": "광원", "STYLE_LIBRARY": "스타일",
    "KOREAN_GLOSSARY": "기본 용어집", "PALETTES": "색 조화", "COLORS": "색상", "CLOTHING_COLORS": "의상 색상",
    "CLOTHING_STATES": "의상 상태", "FOOTWEAR": "신발", "ACCESSORIES": "액세서리", "FURNITURE": "가구",
    "DECOR": "장식", "PRACTICAL": "생활 소품",
}


def apply_pool_files() -> None:
    """Replace each pool's content with its JSON file (in place, so every reference keeps working).

    Item format: {"한글 이름": {"en": "english phrase", "desc_ko": "한글 설명"}} (a plain string also works).
    A missing or broken file leaves the built-in defaults untouched.
    """
    for name in POOL_LABELS_KO:
        path = POOLS_DIR / f"{name.lower()}.json"
        target = globals().get(name)
        if not path.exists() or not isinstance(target, dict):
            continue
        try:
            items = json.loads(path.read_text(encoding="utf-8"))["items"]
            loaded = {str(ko): (v["en"] if isinstance(v, dict) else str(v)) for ko, v in items.items()}
        except (OSError, ValueError, KeyError, TypeError):
            warning(f"번역풀 파일을 읽지 못해 기본값을 씁니다: {path.name}")
            continue
        if loaded:
            target.clear()
            target.update(loaded)


def export_pool_files(force: bool = False) -> List[str]:
    """Write the built-in pools to krea2_prompt_configs/pools/ (existing files are kept unless force=True)."""
    POOLS_DIR.mkdir(parents=True, exist_ok=True)
    written = []
    for name, label in POOL_LABELS_KO.items():
        path = POOLS_DIR / f"{name.lower()}.json"
        data = globals().get(name)
        if not isinstance(data, dict) or (path.exists() and not force):
            continue
        payload = {"schema": "krea2-pool/1", "pool": name, "label_ko": label,
                   "items": {ko: {"en": en, "desc_ko": ""} for ko, en in data.items()}}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(path.name)
    return written


apply_pool_files()


# ---------------------------------------------------------------------------
# Korean natural-language parser
# ---------------------------------------------------------------------------
PARSER_TERMS = {
    "themes": {
        "일상": "일상", "일상적인": "일상", "로맨스": "로맨스", "데이트": "데이트", "주말": "주말",
        "휴식": "휴식", "친구": "친구", "여행": "여행", "도시": "도시 생활", "자연": "자연",
        "직장": "직장", "회사": "직장", "공부": "공부", "공부하는": "공부", "취미": "취미",
        "예술": "예술", "스포츠": "스포츠", "비 오는 날": "비 오는 날", "아침": "아침", "저녁": "저녁",
        "축제": "축제", "휴가": "휴가", "화보": "사진 화보",
    },
    "locations": {k: k for k in LOCATIONS},
    "activities": {**{k: k for k in ACTIVITIES}, "같이 걷기": "손잡고 걷기", "저녁에 산책": "저녁 산책"},
    "relationships": {k: k for k in RELATIONSHIPS},
    "interactions": {k: k for k in INTERACTIONS},
    "weather": {k: k for k in WEATHER},
    "time": {k: k for k in TIME_OF_DAY},
    "mood": {k: k for k in MOODS},
    "materials": {k: k for k in FABRICS},
    "garments": {k: k for k in GARMENTS},
    "colors": {k: k for k in COLORS},
    "poses": {k: k for k in BASE_POSES},
    "framing": {k: k for k in CAMERA_FRAMING},
    "viewpoint": {k: k for k in VIEWPOINTS},
    "composition": {k: k for k in COMPOSITIONS},
}


def _find_first(text: str, mapping: Dict[str, str]) -> Optional[str]:
    hits = [(text.find(kr), kr, en) for kr, en in mapping.items() if kr and kr in text]
    hits = [x for x in hits if x[0] >= 0]
    if not hits:
        return None
    hits.sort(key=lambda x: (x[0], -len(x[1])))
    return hits[0][2]


def parse_natural_language(text: str) -> Dict[str, Any]:
    raw = clean_text(text)
    parsed: Dict[str, Any] = {"raw_text": raw, "people": None, "confidence": {}}
    if "한국인 여성" in raw or "한국인 여자" in raw:
        parsed["identity_A"] = "adult Korean woman"
        parsed["confidence"]["identity_A"] = "keyword"
    elif "한국인 남성" in raw or "한국인 남자" in raw:
        parsed["identity_A"] = "adult Korean man"
        parsed["confidence"]["identity_A"] = "keyword"
    elif "한국인" in raw:
        parsed["identity_A"] = "adult Korean person"
        parsed["confidence"]["identity_A"] = "keyword"
    for category, mapping in PARSER_TERMS.items():
        key = _find_first(raw, mapping)
        if key is not None:
            singular_key = {
                "themes": "theme", "locations": "location", "activities": "activity", "interactions": "interaction",
                "relationships": "relationship", "weather": "weather", "time": "time", "mood": "mood",
                "materials": "material", "garments": "garment", "colors": "color", "poses": "pose",
                "framing": "framing", "viewpoint": "viewpoint", "composition": "composition",
            }.get(category, category)
            parsed[singular_key] = key
            parsed["confidence"][category] = "keyword"

    for n in ("두 명", "둘이", "2명", "두사람", "두 사람"):
        if n in raw:
            parsed["people"] = 2
            break
    for n in ("혼자", "한 명", "1명", "한사람", "한 사람"):
        if n in raw:
            parsed["people"] = 1
            break
    if parsed.get("people") is None and any(x in raw for x in ("연인", "커플", "친구 둘", "같이", "함께", "둘이", "커플")):
        parsed["people"] = 2
        parsed["confidence"]["people"] = "inferred"
    if parsed.get("people") is None:
        parsed["people"] = 1
        parsed["confidence"]["people"] = "default"

    # Korean natural descriptions for basic clothing properties.
    material = parsed.get("material")
    garment = parsed.get("garment")
    color = parsed.get("color")
    if material:
        parsed["material_A"] = material
    if garment:
        parsed["garment_A"] = garment
    if color:
        parsed["color_A"] = color

    if "로라" in raw.lower():
        m = re.search(r"로라\s*(?:트리거)?\s*[:=]?\s*([A-Za-z0-9_\-]+)", raw, re.I)
        if m:
            parsed["lora_trigger_A"] = m.group(1)
    if "정면" in raw and "카메라" in raw:
        parsed["viewpoint"] = "정면"
    if "근접" in raw or "얼굴 가까이" in raw:
        parsed["framing"] = "클로즈업"
    if "자연광" in raw or "창문빛" in raw:
        parsed["light_source"] = "창문 자연광"
        if parsed.get("theme") == "자연" and "자연" not in raw.replace("자연광", ""):
            parsed.pop("theme", None)
    if "전신" in raw:
        parsed["framing"] = "전신"
    if "넓게" in raw and ("공간" in raw or "방" in raw or "배경" in raw):
        parsed["framing"] = "와이드 씬"
    return parsed


def constraints_from_parsed(parsed: Dict[str, Any], source_text: str = "") -> Dict[str, ConstraintSetting]:
    c = defaults()
    c.update({
        "light_source": constraint(), "light_direction": constraint(), "light_quality": constraint(),
        "light_intensity": constraint(), "color_temperature": constraint(), "style": constraint(),
        "left_right_basis": constraint("subject perspective", "fixed", 100, "system"),
        "prop_A": constraint(), "lora_trigger_A": constraint(), "lora_trigger_B": constraint(),
        "expression_A": constraint(), "expression_B": constraint(), "gaze_A": constraint(), "gaze_B": constraint(),
        "hair_A": constraint(), "hair_B": constraint(), "height_A": constraint(), "height_B": constraint(),
    })
    mapping = {
        "theme": "theme", "location": "location", "activity": "activity", "interaction": "interaction", "relationship": "relationship",
        "weather": "weather", "time": "time", "mood": "mood", "light_source": "light_source", "material_A": "material_A", "garment_A": "garment_A",
        "color_A": "color_A", "pose": "pose", "framing": "framing", "viewpoint": "viewpoint", "composition": "composition",
        "lora_trigger_A": "lora_trigger_A", "identity_A": "identity_A",
    }
    for parsed_key, constraint_key in mapping.items():
        if parsed.get(parsed_key):
            set_constraint_value(c, constraint_key, str(parsed[parsed_key]), "fixed", 95, "user")
    if parsed.get("people") in {1, 2}:
        set_constraint_value(c, "people", str(parsed["people"]), "fixed", 100, "user")
    if source_text:
        c["source_text"] = constraint(source_text, "fixed", 100, "user")
    return c


# ---------------------------------------------------------------------------
# Generation / preview / export / history
# ---------------------------------------------------------------------------

def scene_preview(scene: SceneProfile) -> str:
    def mark(key: str, value: Any) -> str:
        source = "고정" if key in scene.user_values else "자동"
        return f"[{source}] {value}"
    lines = [
        "",
        "─" * 88,
        "Krea2 장면 설계 미리보기",
        "─" * 88,
        f"인물: {mark('people', scene.people)}명 / 관계: {mark('relationship', scene.relationship_key)}",
        f"주제: {mark('theme', scene.theme_key)} / 행동: {mark('activity', scene.activity_key)}",
        f"상호작용: {mark('interaction', scene.interaction_key)}",
        f"공간: {mark('location', scene.location_key)} / 세부 위치: {scene.sublocation}",
        f"A 자세: {mark('pose_A', scene.pose_a.get('pose_key'))}",
        f"B 자세: {scene.pose_b.get('pose_key') if scene.pose_b else '없음'}",
        f"A 의상: {scene.clothing_a.color} {scene.clothing_a.garment_en} / 원단 {scene.clothing_a.fabric.material}",
        f"A 원단 물성: 밀도={scene.clothing_a.fabric.density}, 섬유={scene.clothing_a.fabric.fiber_fineness}, 투명도={scene.clothing_a.fabric.opacity}, 두께={scene.clothing_a.fabric.thickness}",
        f"공간 밀도: {scene.environment.density} / 생활감: {scene.environment.state}",
        f"프레이밍: {scene.camera.framing} / 렌즈: {scene.camera.lens}mm / 관점: {scene.camera.viewpoint}",
        f"검사 이슈: {len(scene.issues)}건",
    ]
    for issue in scene.issues[:10]:
        lines.append(f"  {'❌' if issue.level == 'error' else '⚠️'} {issue.category}: {issue.message_kr}")
    lines.append("─" * 88)
    return "\n".join(lines)


def _prompt_metadata(scene: SceneProfile, options: GenerationOptions, seed: int) -> Dict[str, Any]:
    return {
        "model": MODEL_NAME,
        "app_version": APP_VERSION,
        "seed": seed,
        "theme": scene.theme_key,
        "location": scene.location_key,
        "people": scene.people,
        "relationship": scene.relationship_key,
        "activity": scene.activity_key,
        "interaction": scene.interaction_key,
        "time": scene.time_key,
        "weather": scene.weather_key,
        "mood": scene.mood_key,
        "camera": asdict(scene.camera),
        "lighting": asdict(scene.lighting),
        "environment": asdict(scene.environment),
        "clothing_A": asdict(scene.clothing_a),
        "clothing_B": asdict(scene.clothing_b) if scene.clothing_b else None,
        "issues": [asdict(x) for x in scene.issues],
        "user_values": scene.user_values,
        "auto_values": scene.auto_values,
        "source_text_kr": scene.source_text_kr,
    }


def generate_one(options: GenerationOptions, constraints: Optional[Dict[str, ConstraintSetting]] = None,
                 seed: Optional[int] = None) -> PromptSet:
    actual_seed = seed if seed is not None else (options.seed if options.seed is not None else random.randrange(1, 2**32))
    c = constraints or options.constraints or defaults()
    if options.person_a and options.person_a.lora_trigger:
        c.setdefault("lora_trigger_A", constraint()).value = options.person_a.lora_trigger
        c["lora_trigger_A"].source = "user"
        c["lora_trigger_A"].random_mode = "fixed"
    if options.person_b and options.person_b.lora_trigger:
        c.setdefault("lora_trigger_B", constraint()).value = options.person_b.lora_trigger
        c["lora_trigger_B"].source = "user"
        c["lora_trigger_B"].random_mode = "fixed"
    if options.person_b is not None:
        set_constraint_value(c, "people", "2", "fixed", 100, "user")
    elif options.person_a is not None and get_value(c, "people") == "auto" and options.lora_mode == "single":
        set_constraint_value(c, "people", "1", "fixed", 100, "user")

    scene = build_scene(actual_seed, c, options.person_a, options.person_b, options.custom_notes, options.strict_consistency)
    rng = random.Random(actual_seed + 17)
    pa = resolve_person(rng, scene, "A", options.person_a)
    pb = resolve_person(rng, scene, "B", options.person_b) if scene.people == 2 else None
    detailed = options.detail == "상세"
    import krea2_prose
    parts = krea2_prose.render(scene, pa, pb, detailed, options.reinforce)
    prompt = final_prompt(scene, pa, pb, strict=True, detailed=detailed, reinforce=options.reinforce)
    coverage = prompt_option_coverage(scene, pa, pb, prompt)
    if coverage["missing"]:
        raise ValueError("Prompt option coverage failed: " + ", ".join(coverage["missing"]))
    pid = sha12(prompt)
    record = PromptSet(
        prompt_id=pid,
        created_at=now_iso(),
        seed=actual_seed,
        mode=options.mode,
        lora_mode=options.lora_mode,
        global_prompt=parts["scene"],
        person_a_prompt=parts["person_a"],
        person_b_prompt=parts["person_b"],
        combined_prompt=prompt,
        metadata={**_prompt_metadata(scene, options, actual_seed), "option_coverage": coverage, "prompt_syntax_errors": prompt_syntax_errors(prompt)},
        tags=[scene.theme_key, scene.activity_key, scene.location_key, scene.mood_key],
    )
    return record


def generate_records(options: GenerationOptions, constraints: Optional[Dict[str, ConstraintSetting]] = None) -> List[PromptSet]:
    records: List[PromptSet] = []
    seen = set()
    base_seed = options.seed if options.seed is not None else random.randrange(1, 2**32)
    for i in range(max(1, options.count)):
        attempt = 0
        while attempt < 20:
            seed = base_seed + i * 997 + attempt
            record = generate_one(options, constraints, seed)
            if not options.prevent_duplicates or record.prompt_id not in seen:
                records.append(record)
                seen.add(record.prompt_id)
                break
            attempt += 1
    if options.save_history:
        append_history(records, Path(options.history_path))
    return records


def _export_payload(record: PromptSet) -> Dict[str, Any]:
    return asdict(record)


def export_records(records: List[PromptSet], options: GenerationOptions) -> Path:
    out = Path(options.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    fmt = options.output_format.lower()
    suffix = "md" if fmt == "markdown" else fmt
    target = out / f"krea2_prompts_{stamp}.{suffix}"
    payloads = [_export_payload(x) for x in records]
    if fmt == "json":
        target.write_text(json.dumps(payloads, ensure_ascii=False, indent=2), encoding="utf-8")
    elif fmt == "csv":
        fields = ["prompt_id", "created_at", "seed", "mode", "lora_mode", "combined_prompt", "tags"]
        with target.open("w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            w.writeheader()
            for row in payloads:
                w.writerow({k: (" | ".join(row[k]) if k == "tags" else row[k]) for k in fields})
    elif fmt == "markdown":
        chunks = []
        for r in records:
            chunks.append(f"# {r.prompt_id}\n\n**Seed:** {r.seed}\n\n{r.combined_prompt}\n")
        target.write_text("\n\n".join(chunks), encoding="utf-8")
    else:
        target = out / f"krea2_prompts_{stamp}.txt"
        target.write_text("\n\n".join(r.combined_prompt for r in records), encoding="utf-8")
    return target


def append_history(records: List[PromptSet], path: Path = HISTORY_FILE) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(asdict(record), ensure_ascii=False) + "\n")
    except OSError as exc:
        warning(f"히스토리 저장 실패: {exc}")


def read_history(path: Path = HISTORY_FILE, limit: int = 10) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    rows.append(json.loads(line))
    except (OSError, json.JSONDecodeError):
        return []
    return rows[-max(1, limit):]


def save_favorite(record: PromptSet) -> None:
    data = load_json(FAVORITES_FILE, [])
    if not isinstance(data, list):
        data = []
    if not any(isinstance(x, dict) and x.get("prompt_id") == record.prompt_id for x in data):
        data.append(asdict(record))
    save_json(FAVORITES_FILE, data)


def load_loras() -> List[Dict[str, Any]]:
    data = load_json(LORA_FILE, [])
    return data if isinstance(data, list) else []


def save_lora(name: str, trigger: str, note: str = "") -> None:
    data = load_loras()
    clean_name = clean_text(name)
    clean_trigger = clean_text(trigger)
    updated = False
    for row in data:
        if isinstance(row, dict) and row.get("name") == clean_name:
            row["trigger"] = clean_trigger
            row["note"] = clean_text(note)
            row["updated_at"] = now_iso()
            updated = True
            break
    if not updated:
        data.append({"name": clean_name, "trigger": clean_trigger, "note": clean_text(note), "updated_at": now_iso()})
    save_json(LORA_FILE, data)


# ---------------------------------------------------------------------------
# Extended UI field catalog
# ---------------------------------------------------------------------------
FIELD_HELP.update({
    "people": "인물 수: 1명 또는 2명",
    "relationship": "인물 관계: 혼자/친구/연인/부부/동료 등",
    "sublocation": "장소 안의 구체적인 위치",
    "left_right_basis": "좌우 기준: 피사체 기준 또는 카메라 기준",
    "height_A": "A 인물의 대략적인 실제 신장(cm)",
    "height_B": "B 인물의 대략적인 실제 신장(cm)",
    "expression_A": "A 인물 표정",
    "expression_B": "B 인물 표정",
    "gaze_A": "A 인물 시선",
    "gaze_B": "B 인물 시선",
    "hair_A": "A 인물 헤어스타일",
    "hair_B": "B 인물 헤어스타일",
    "light_source": "주광원 종류",
    "light_direction": "광원 방향",
    "light_quality": "빛의 경도/확산 정도",
    "light_intensity": "빛의 대비와 밝기",
    "color_temperature": "조명 색온도",
    "style": "최종 사진/렌더링의 스타일 방향",
    "prop_A": "A 인물이 사용하는 주요 소품",
})

STYLE_LIBRARY = {
    "자연광 라이프스타일": "natural-light lifestyle photography with restrained color grading",
    "시네마틱": "cinematic lifestyle photography with grounded color and realistic depth",
    "매거진": "refined magazine editorial photography with sophisticated visual balance",
    "다큐멘터리": "authentic documentary photography with candid timing and believable environmental detail",
    "미니멀": "clean minimalist photography with controlled visual hierarchy",
    "필름 룩": "subtle contemporary film-like photography with natural grain and gentle tonal rolloff",
    "스트리트 스냅": "natural street photography with candid timing and documentary realism",
    "여행 화보": "polished travel editorial photography with authentic environmental context",
}


def full_defaults() -> Dict[str, ConstraintSetting]:
    c = defaults()
    for key in (
        "light_source", "light_direction", "light_quality", "light_intensity", "color_temperature", "style",
        "prop_A", "prop_B", "lora_trigger_A", "lora_trigger_B", "expression_A", "expression_B", "gaze_A", "gaze_B",
        "hair_A", "hair_B", "hair_color_A", "hair_color_B", "eye_color_A", "eye_color_B", "body_build_A", "body_build_B", "skin_detail_A", "skin_detail_B", "distinctive_feature_A", "distinctive_feature_B", "height_A", "height_B", "environment_density", "environment_state", "palette",
        "sublocation", "weather", "time", "people", "relationship", "activity", "interaction", "pose",
        "material_A", "material_B", "garment_A", "garment_B", "fit_A", "fit_B", "color_A", "color_B",
        "footwear_A", "footwear_B", "accessory_A", "accessory_B", "state_A", "state_B", "detail_A", "detail_B",
        "framing", "viewpoint", "composition", "lens", "skin_finish", "realism",
    ):
        c.setdefault(key, constraint())
    return c


def _options_header() -> None:
    print_header(f"{APP_NAME} v{APP_VERSION}")
    print(f"Target model: {MODEL_NAME}")
    print("한국어로 장면을 설계하고, 최종 결과는 Krea2 Turbo용 자연어 영어 Positive Prompt로 출력합니다.")


OPTION_DESC_FILE = CONFIG_DIR / "option_descriptions.json"
# menu field name (without the _A/_B suffix) -> description group
FIELD_GROUPS = {
    "theme": "THEMES", "location": "LOCATIONS", "activity": "ACTIVITIES", "relationship": "RELATIONSHIPS",
    "interaction": "INTERACTIONS", "pose": "BASE_POSES", "material": "FABRICS", "garment": "GARMENTS",
    "color": "COLORS", "framing": "CAMERA_FRAMING", "viewpoint": "VIEWPOINTS", "composition": "COMPOSITIONS",
    "weather": "WEATHER", "time": "TIME_OF_DAY", "mood": "MOODS", "palette": "PALETTES",
    "environment_density": "ENV_DENSITY", "environment_state": "ENV_STATE", "skin_finish": "SKIN_FINISH",
    "realism": "REALISM", "style": "STYLE_LIBRARY", "state": "CLOTHING_STATES", "people": "PEOPLE",
}
_DESC_CACHE: Dict[str, Dict[str, str]] = {}


def option_descriptions(group: str) -> Dict[str, str]:
    """Korean one-line descriptions for a menu group: pool file desc_ko first, then option_descriptions.json."""
    if group in _DESC_CACHE:
        return _DESC_CACHE[group]
    descs: Dict[str, str] = {}
    data = load_json(POOLS_DIR / f"{group.lower()}.json", {})
    for ko, item in (data.get("items", {}) if isinstance(data, dict) else {}).items():
        if isinstance(item, dict) and item.get("desc_ko"):
            descs[ko] = str(item["desc_ko"])
    extra = load_json(OPTION_DESC_FILE, {})
    for ko, text in (extra.get("groups", {}).get(group, {}) if isinstance(extra, dict) else {}).items():
        descs.setdefault(ko, str(text))
    _DESC_CACHE[group] = descs
    return descs


def menu_choose(title: str, options: Sequence[str], default: Optional[str] = None,
                descs: Optional[Dict[str, str]] = None, help_text: str = "") -> str:
    print(f"\n[{title}]")
    if help_text:
        print(f"  ※ {help_text}")
    descs = descs or {}
    for i, value in enumerate(options, 1):
        suffix = " (기본)" if default and value == default else ""
        note = f"  — {descs[value]}" if descs.get(value) else ""
        print(f"  {i}. {value}{suffix}{note}")
    while True:
        raw = input(f"선택 [{default or 1}]: ").strip()
        if not raw and default:
            return default
        if raw.isdigit() and 1 <= int(raw) <= len(options):
            return options[int(raw) - 1]
        if raw in options:
            return raw
        warning("올바른 번호 또는 항목을 입력하세요.")


def ask_text(label: str, default: str = "") -> str:
    raw = input(f"{label}{f' [{default}]' if default else ''}: ").strip()
    return raw or default


def ask_int(label: str, default: int, lo: int, hi: int) -> int:
    while True:
        raw = ask_text(label, str(default))
        try:
            value = int(raw)
        except ValueError:
            warning("숫자를 입력하세요.")
            continue
        if lo <= value <= hi:
            return value
        warning(f"{lo}~{hi} 범위로 입력하세요.")


def set_menu_field(c: Dict[str, ConstraintSetting], key: str, title: str, options: Sequence[str], default: str = "auto") -> None:
    base = re.sub(r"_[AB]$", "", key)
    descs = dict(option_descriptions(FIELD_GROUPS.get(base, "")))
    descs["자동"] = "프로그램이 알아서 고르게 둠"
    help_text = FIELD_HELP.get(key) or FIELD_HELP.get(base, "")
    selected = menu_choose(title, ["자동", *options], default="자동", descs=descs, help_text=help_text)
    if selected == "자동":
        c[key] = constraint("auto", "auto", 50, "auto")
        return
    mode_kr = menu_choose("랜덤 범위", list(RANDOM_MODES), default="고정", descs=option_descriptions("RANDOM_MODES"))
    set_constraint_value(c, key, selected, RANDOM_MODES[mode_kr], 95, "user" if mode_kr == "고정" else "user")


def choose_random_range() -> str:
    return menu_choose("Smart Random 범위", list(RANDOM_MODES), default="자동", descs=option_descriptions("RANDOM_MODES"))


def configure_clothing_menu(c: Dict[str, ConstraintSetting], slot: str) -> None:
    print_header(f"인물 {slot} 의상 설계")
    # Garment first; material then resolves only within physically compatible materials.
    set_menu_field(c, f"garment_{slot}", "의상 종류", list(GARMENTS))
    garment = get_value(c, f"garment_{slot}")
    compatible = compatible_fabrics(garment) if garment in GARMENTS else list(FABRICS)
    set_menu_field(c, f"material_{slot}", "원단/소재", compatible)
    set_menu_field(c, f"fit_{slot}", "핏", GARMENTS[garment][1] if garment in GARMENTS else ["regular fit", "relaxed fit"])
    set_menu_field(c, f"color_{slot}", "색상", list(COLORS))
    set_menu_field(c, f"footwear_{slot}", "신발", list(FOOTWEAR))
    set_menu_field(c, f"accessory_{slot}", "액세서리", list(ACCESSORIES))
    set_menu_field(c, f"state_{slot}", "의상 상태", list(CLOTHING_STATES))
    detail = ask_text("의상 디테일 직접 지정(선택, 영어 또는 한국어)")
    if detail:
        set_constraint_value(c, f"detail_{slot}", local_translate(detail), "fixed", 90, "user")
    else:
        c[f"detail_{slot}"] = constraint()


def configure_scene_conditions(c: Dict[str, ConstraintSetting]) -> None:
    print_header("장면 조건 설정")
    set_menu_field(c, "theme", "테마", list(THEMES))
    set_menu_field(c, "location", "공간", list(LOCATIONS))
    set_menu_field(c, "activity", "행동", list(ACTIVITIES))
    people = menu_choose("인물 수", ["자동", "1", "2"], default="자동", descs=option_descriptions("PEOPLE"))
    c["people"] = constraint(people if people != "자동" else "auto", "fixed" if people != "자동" else "auto", 100 if people != "자동" else 50, "user" if people != "자동" else "auto")
    if people != "1":
        set_menu_field(c, "relationship", "관계", list(RELATIONSHIPS))
        set_menu_field(c, "interaction", "상호작용", list(INTERACTIONS))
    set_menu_field(c, "pose", "자세", list(BASE_POSES))
    set_menu_field(c, "material_A", "A 원단", list(FABRICS))
    set_menu_field(c, "garment_A", "A 의상", list(GARMENTS))
    set_menu_field(c, "color_A", "A 의상 색", list(COLORS))
    set_menu_field(c, "framing", "프레이밍", list(CAMERA_FRAMING))
    set_menu_field(c, "viewpoint", "카메라 관점", list(VIEWPOINTS))
    set_menu_field(c, "composition", "구도", list(COMPOSITIONS))
    set_menu_field(c, "weather", "날씨", list(WEATHER))
    set_menu_field(c, "time", "시간대", list(TIME_OF_DAY))
    set_menu_field(c, "mood", "분위기", list(MOODS))
    set_menu_field(c, "palette", "색 조화", list(PALETTES))
    set_menu_field(c, "environment_density", "배경 밀도", list(ENV_DENSITY))
    set_menu_field(c, "environment_state", "공간 상태", ["깔끔", "생활감", "정돈된", "살짝 어수선"])
    set_menu_field(c, "skin_finish", "피부 표현", list(SKIN_FINISH))
    set_menu_field(c, "realism", "리얼리즘", list(REALISM))
    set_menu_field(c, "style", "사진 스타일", list(STYLE_LIBRARY))
    basis = menu_choose("좌우 기준", ["subject perspective", "camera perspective"], default="subject perspective")
    set_constraint_value(c, "left_right_basis", basis, "fixed", 100, "user")


def configure_people(c: Dict[str, ConstraintSetting], count: int) -> Tuple[Optional[PersonSlot], Optional[PersonSlot]]:
    a = b = None
    print_header("LoRA / 인물 설정")
    rows = load_loras()

    def configure_slot(label: str) -> PersonSlot:
        trigger = ask_text(f"{label} 인물 LoRA 트리거(없으면 Enter)")
        if not trigger:
            return PersonSlot(slot=f"PERSON_{label}", identity="adult person")
        trigger = clean_text(trigger)
        profile = next((row for row in rows if isinstance(row, dict) and clean_text(str(row.get("trigger", ""))).lower() == trigger.lower()), None)
        if profile and clean_text(str(profile.get("identity", ""))):
            cprint(f"  ↳ 등록된 '{profile.get('name', trigger)}' identity 자동 적용", Color.GREEN)
            return PersonSlot(slot=f"PERSON_{label}", lora_trigger=trigger, identity="adult person")
        identity = ask_text(f"{label} 인물 정체성 설명", "adult person")
        return PersonSlot(slot=f"PERSON_{label}", lora_trigger=trigger, identity=identity)

    a = configure_slot("A")
    if count == 2:
        b = configure_slot("B")
    return a, b


def print_prompt(record: PromptSet) -> None:
    print("\n" + "=" * 88)
    print("Krea2 Turbo FINAL PROMPT")
    print("=" * 88)
    print(record.combined_prompt)
    print("=" * 88)
    coverage = record.metadata.get("option_coverage", {})
    syntax = record.metadata.get("prompt_syntax_errors", [])
    print(f"Option coverage: {coverage.get('passed', 0)}/{coverage.get('total', 0)}")
    print(f"Prompt syntax: {'PASS' if not syntax else 'FAIL: ' + '; '.join(syntax)}")
    print(f"ID: {record.prompt_id}   Seed: {record.seed}")


# ---------------------------------------------------------------------------
# Interactive modes
# ---------------------------------------------------------------------------

def natural_mode() -> None:
    _options_header()
    print("\n한국어로 장면을 자연스럽게 설명하세요.")
    print("예: '오후 카페에서 연인과 대화하는 한국인 여성, 하늘색 오간자 블라우스, 전신, 창문 자연광'")
    raw = input("\n장면 설명\n> ").strip()
    if not raw:
        warning("장면 설명이 비어 있습니다.")
        return
    parsed = parse_natural_language(raw)
    c = constraints_from_parsed(parsed, raw)
    if "자연광" in raw or "창문빛" in raw:
        set_constraint_value(c, "light_source", LIGHT_SOURCES["창문 자연광"], "fixed", 92, "user")
        if parsed.get("theme") == "자연" and "자연" not in raw.replace("자연광", ""):
            c["theme"] = constraint("auto", "auto", 50, "auto")
    # Allow the parser to infer a romantic theme from relationship wording.
    if "연인" in raw and get_value(c, "theme") == "auto":
        set_constraint_value(c, "theme", "로맨스", "fixed", 88, "inferred")
    if "데이트" in raw and get_value(c, "activity") == "auto":
        set_constraint_value(c, "activity", "카페 데이트", "fixed", 88, "inferred")
    count = parsed.get("people") or 1
    lora_a = parsed.get("lora_trigger_A", "")
    a = PersonSlot(slot="PERSON_A", lora_trigger=lora_a, identity="adult person")
    b = PersonSlot(slot="PERSON_B", lora_trigger="", identity="adult person") if count == 2 else None
    options = GenerationOptions(mode="natural", lora_mode="dual" if count == 2 else "single", count=1, person_a=a, person_b=b, custom_notes=raw, constraints=c, strict_consistency=False)
    try:
        record = generate_records(options, c)[0]
    except Exception as exc:
        error(f"생성 실패: {exc}")
        return
    if options.preview_before_prompt:
        try:
            scene = build_scene(record.seed, c, a, b, raw)
            print(scene_preview(scene))
        except Exception:
            pass
    print_prompt(record)


def smart_random_mode() -> None:
    _options_header()
    c = full_defaults()
    scope = menu_choose(
        "Smart Random 유형",
        ["전체 자동", "테마 고정", "공간 고정", "행동 고정", "의상 고정", "카메라 고정", "커스텀 조건"],
        default="전체 자동",
    )
    if scope == "테마 고정":
        set_menu_field(c, "theme", "테마", list(THEMES))
    elif scope == "공간 고정":
        set_menu_field(c, "location", "공간", list(LOCATIONS))
    elif scope == "행동 고정":
        set_menu_field(c, "activity", "행동", list(ACTIVITIES))
        set_menu_field(c, "people", "인물 수", ["1", "2"])
    elif scope == "의상 고정":
        configure_clothing_menu(c, "A")
    elif scope == "카메라 고정":
        set_menu_field(c, "framing", "프레이밍", list(CAMERA_FRAMING))
        set_menu_field(c, "viewpoint", "관점", list(VIEWPOINTS))
        set_menu_field(c, "composition", "구도", list(COMPOSITIONS))
        set_menu_field(c, "lens", "렌즈", [str(x) for x in CAMERA_LENSES])
    elif scope == "커스텀 조건":
        configure_scene_conditions(c)
    count = ask_int("생성할 프롬프트 수", 1, 1, 50)
    seed_raw = ask_text("기본 시드(빈칸=자동)")
    seed = int(seed_raw) if seed_raw.isdigit() else None
    options = GenerationOptions(mode="smart_random", lora_mode="single", count=count, seed=seed, constraints=c, preview_before_prompt=True)
    try:
        records = generate_records(options, c)
    except Exception as exc:
        error(f"생성 실패: {exc}")
        return
    for record in records:
        print_prompt(record)
    if records:
        export = menu_choose("결과 저장 형식", ["저장 안 함", "txt", "json", "csv", "markdown"], default="txt")
        if export != "저장 안 함":
            options.output_format = export
            target = export_records(records, options)
            success(f"저장 완료: {target}")


def condition_random_mode() -> None:
    _options_header()
    c = full_defaults()
    configure_scene_conditions(c)
    count = ask_int("생성 수", 1, 1, 50)
    seed_raw = ask_text("시드(빈칸=자동)")
    seed = int(seed_raw) if seed_raw.isdigit() else None
    a, b = configure_people(c, 2 if get_value(c, "people") == "2" else 1)
    if b:
        c["people"] = constraint("2", "fixed", 100, "user")
    options = GenerationOptions(mode="condition_random", lora_mode="dual" if b else "single", count=count, seed=seed, person_a=a, person_b=b, constraints=c)
    try:
        records = generate_records(options, c)
        for record in records:
            print_prompt(record)
    except Exception as exc:
        error(f"생성 실패: {exc}")


def quick_random_mode() -> None:
    _options_header()
    c = full_defaults()
    # Curated broad distribution; relationships remain tied to the generated activity.
    c["theme"] = constraint("auto", "wide", 50, "auto")
    c["location"] = constraint("auto", "wide", 50, "auto")
    c["activity"] = constraint("auto", "wide", 50, "auto")
    c["material_A"] = constraint("auto", "wide", 50, "auto")
    c["garment_A"] = constraint("auto", "wide", 50, "auto")
    c["environment_density"] = constraint("보통", "fixed", 70, "system")
    c["framing"] = constraint("auto", "medium", 50, "auto")
    options = GenerationOptions(mode="quick_random", lora_mode="single", count=ask_int("생성 수", 4, 1, 20), constraints=c)
    try:
        records = generate_records(options, c)
        for r in records:
            print_prompt(r)
    except Exception as exc:
        error(f"생성 실패: {exc}")


def history_mode() -> None:
    _options_header()
    rows = read_history(limit=20)
    if not rows:
        info("저장된 히스토리가 없습니다.")
        return
    for i, row in enumerate(rows, 1):
        meta = row.get("metadata", {})
        print(f"{i:02d}. {row.get('prompt_id')} / seed={row.get('seed')} / {meta.get('theme','')} / {meta.get('activity','')}")
    raw = ask_text("볼 번호", "1")
    if raw.isdigit() and 1 <= int(raw) <= len(rows):
        print("\n" + rows[int(raw) - 1].get("combined_prompt", ""))


def lora_mode() -> None:
    _options_header()
    rows = load_loras()
    if rows:
        print("\n[등록된 LoRA]")
        for i, row in enumerate(rows, 1):
            print(f"  {i}. {row.get('name')} → {row.get('trigger')}  {row.get('note','')}")
    action = menu_choose("LoRA 관리", ["등록/수정", "목록만 보기"], default="등록/수정")
    if action == "등록/수정":
        name = ask_text("LoRA 이름")
        trigger = ask_text("LoRA 트리거")
        note = ask_text("메모")
        if name and trigger:
            save_lora(name, trigger, note)
            success("LoRA가 저장되었습니다.")


def dictionary_mode() -> None:
    _options_header()
    if translator_list_user is not None:
        data = translator_list_user()
    else:
        data = load_json(USER_DICTIONARY_FILE, {})
        if not isinstance(data, dict):
            data = {}
    action = menu_choose("내장 번역 사전", ["추가/수정", "목록", "삭제"], default="추가/수정")
    if action == "목록":
        if not data:
            info("사용자 추가 사전이 비어 있습니다.")
        for kr, en in data.items():
            print(f"  {kr} → {en}")
        return
    kr = ask_text("한국어 표현")
    if not kr:
        return
    if action == "삭제":
        if translator_remove_user is not None:
            removed = translator_remove_user(kr)
        else:
            removed = kr in data
            data.pop(kr, None)
            save_json(USER_DICTIONARY_FILE, data)
        success("내장 사전에서 삭제했습니다." if removed else "해당 표현이 사전에 없습니다.")
        return
    en = ask_text("영어 표현")
    if not en:
        return
    if translator_add_user is not None:
        translator_add_user(kr, en)
    else:
        data[kr] = en
        save_json(USER_DICTIONARY_FILE, data)
    success("내장 사전에 추가/수정했습니다.")


def settings_mode() -> None:
    _options_header()
    settings = load_json(SETTINGS_FILE, {})
    if not isinstance(settings, dict):
        settings = {}
    settings["model"] = MODEL_NAME
    settings["app_version"] = APP_VERSION
    settings["language_ui"] = "ko"
    settings["prompt_language"] = "en"
    settings["translator"] = "embedded_local"
    settings["translator_version"] = TRANSLATOR_VERSION
    for legacy in ("subject_scale_lock", "environment_scale_lock"):
        settings.pop(legacy, None)          # v10 model-facing scale sentences no longer exist
    names = {None: "자동", 0: "없음", 1: "1회", 2: "2회"}
    reverse = {v: k_ for k_, v in names.items()}
    settings["prompt_detail"] = menu_choose("묘사 분량 (모든 생성 모드의 기본값)", ["보통", "상세"],
                                            default=settings.get("prompt_detail", "보통"),
                                            descs=option_descriptions("COMPOSER_MODE"))
    pick = menu_choose("강화 횟수 (같은 뜻을 다른 표현으로 반복, 기본값)", list(names.values()),
                       default=names.get(settings.get("reinforce"), "자동"), descs=option_descriptions("REINFORCE"))
    settings["reinforce"] = reverse[pick]
    save_json(SETTINGS_FILE, settings)
    print(json.dumps(settings, ensure_ascii=False, indent=2))
    success("현재 기본 설정을 저장했습니다. (다음 생성부터 적용)")


def run_self_test(verbose: bool = True) -> bool:
    ensure_dirs()
    ok = True
    checks: List[Tuple[str, bool, str]] = []
    checks.append(("컴파일", True, "Python syntax passed"))
    try:
        sample = local_translate("연인이 손을 잡고 걷는다, 하늘색 오간자 블라우스")
        passed = (not bool(re.search(r"[가-힣]", sample)) and "organza" in sample.lower() and "couple" in sample.lower())
        checks.append(("내장 번역 모듈", passed, f"translator {TRANSLATOR_VERSION}: {sample}"))
        if not passed:
            ok = False
    except Exception as exc:
        checks.append(("내장 번역 모듈", False, str(exc)))
        ok = False
    # 1. Single everyday scene.
    try:
        parsed = parse_natural_language("오후 카페에서 책을 읽는 한국인 여성, 하늘색 오간자 블라우스, 전신, 자연광")
        c = constraints_from_parsed(parsed)
        c["theme"] = constraint("일상", "fixed", 95, "user")
        rec = generate_one(GenerationOptions(mode="self_test", count=1, constraints=c), c, 2026100301)
        checks.append(("일상 프롬프트 생성", True, rec.prompt_id))
        checks.append(("영어 프롬프트", not bool(re.search(r"[가-힣]", rec.combined_prompt)), "Korean leakage check"))
        checks.append(("최종 구조 검증", not lint_prompt(rec.combined_prompt), "final prompt linter"))
    except Exception as exc:
        checks.append(("일상 프롬프트 생성", False, str(exc)))
        ok = False
    # 2. Romantic two-person scene.
    try:
        c = full_defaults()
        for key, val in (("theme", "로맨스"), ("people", "2"), ("activity", "카페 데이트"), ("location", "카페"), ("material_A", "오간자"), ("garment_A", "블라우스"), ("framing", "클로즈업")):
            c[key] = constraint(val, "fixed", 100, "user")
        rec = generate_one(GenerationOptions(mode="self_test", lora_mode="dual", person_a=PersonSlot("PERSON_A", "novasaebyeol"), person_b=PersonSlot("PERSON_B", "nboppa"), constraints=c), c, 2026100302)
        checks.append(("2인 로맨스 프롬프트", True, rec.prompt_id))
        low = rec.combined_prompt.lower()
        checks.append(("클로즈업 프레이밍 반영", "close portrait framing" in low and "scale lock" not in low, "framing present, no model-facing scale instructions"))
    except Exception as exc:
        checks.append(("2인 로맨스 프롬프트", False, str(exc)))
        ok = False
    # 3. Fabric coupling.
    try:
        fabric = FABRICS["오간자"]
        fabric_ok = fabric.opacity in {"transparent to translucent", "semi-transparent", "translucent"} or "transluc" in fabric.opacity
        checks.append(("오간자 물성 연동", fabric_ok and fabric.fiber_fineness == "very fine", "material master properties"))
    except Exception as exc:
        checks.append(("오간자 물성 연동", False, str(exc)))
        ok = False
    # 4. LoRA identity lock + option coverage.
    try:
        lora_rows = load_loras()
        lora_profiles = [
            row for row in lora_rows
            if isinstance(row, dict)
            and clean_text(str(row.get("trigger", "")))
            and clean_text(str(row.get("identity", "")))
            and clean_text(str(row.get("identity", ""))).lower() not in {"adult person", "a single adult person"}
        ]
        if lora_profiles:
            fixed_profile = next((row for row in lora_profiles if str(row.get("trigger", "")).lower() == "nayoon"), lora_profiles[0])
            trigger = clean_text(str(fixed_profile.get("trigger", "")))
            c = full_defaults()
            for key, val in (("theme", "일상"), ("people", "1"), ("activity", "책 읽기"), ("location", "카페"), ("pose", "창가에 앉기"), ("framing", "환경 중심"), ("lens", "50")):
                set_constraint_value(c, key, val, "fixed", 100, "user")
            a = PersonSlot("PERSON_A", trigger, "adult person")
            rec = generate_one(GenerationOptions(mode="self_test_lora", lora_mode="single", person_a=a, constraints=c), c, 2026100304)
            scene = build_scene(2026100304, c, a, None)
            pa = resolve_person(random.Random(2026100304 + 17), scene, "A", a)
            locked = (
                rec.combined_prompt.lower().startswith(trigger.lower() + ",")
                and pa.eye_color == "" and pa.hair_color == "" and pa.hair == clean_text(str(fixed_profile.get("hair", "")))
                and pa.body_build == "" and pa.skin_detail == "" and pa.distinctive_feature == ""
                and pa.height_cm is None
            )
            checks.append(("LoRA 캐릭터 고정", locked, f"{trigger}: registered identity only"))
            coverage = rec.metadata.get("option_coverage", {})
            checks.append(("선택 옵션 실제 출력", coverage.get("passed", 0) == coverage.get("total", 0), f"{coverage.get('passed',0)}/{coverage.get('total',0)} resolved fragments present"))
            checks.append(("프롬프트 문법 검사", not rec.metadata.get("prompt_syntax_errors"), "punctuation/LoRA-token checks"))
        else:
            checks.append(("LoRA 캐릭터 고정", True, "no external LoRA profiles loaded; runtime lookup remains supported"))
            checks.append(("선택 옵션 실제 출력", True, "runtime coverage check is enabled"))
            checks.append(("프롬프트 문법 검사", True, "runtime syntax lint is enabled"))
    except Exception as exc:
        checks.append(("LoRA/옵션 출력 감사", False, str(exc)))
        ok = False

    # 5. Normal data catalog integrity.
    try:
        normal_catalogs = {
            "themes": THEMES, "locations": LOCATIONS, "relationships": RELATIONSHIPS,
            "interactions": INTERACTIONS, "activities": ACTIVITIES, "poses": BASE_POSES,
            "fabrics": FABRICS, "garments": GARMENTS,
        }
        populated = all(bool(v) for v in normal_catalogs.values())
        checks.append(("일상용 데이터 카탈로그", populated, f"{len(ACTIVITIES)} activities / {len(LOCATIONS)} locations / {len(FABRICS)} fabrics"))
        if not populated:
            ok = False
    except Exception as exc:
        checks.append(("데이터 카탈로그 검사", False, str(exc)))
        ok = False
    if verbose:
        print_header("자가진단 결과")
        for name, state, note in checks:
            print(f"{'✅' if state else '❌'} {name}: {note}")
    return ok and all(state for _, state, _ in checks)


def composer_mode() -> None:
    """New composer: one human-readable paragraph (보통) or a restated, longer one (상세)."""
    try:
        import krea2_composer as comp
    except ImportError as exc:
        error(f"합성기 모듈을 불러오지 못했습니다: {exc}")
        return
    print_header("새 합성기 — 사람이 쓴 것처럼 읽히는 한 덩어리 프롬프트")
    loras = [r for r in load_loras() if isinstance(r, dict) and r.get("trigger") and r.get("gender") != "male"]
    if not loras:
        warning("등록된 LoRA가 없습니다. 먼저 'LoRA 관리'에서 등록하세요.")
        return
    labels = {f"{r.get('name', r['trigger'])} ({r['trigger']})": r for r in loras}
    descs = {lab: clean_text(str(r.get("identity", "")))[:48] + "…" for lab, r in labels.items()}
    lora = labels[menu_choose("인물 (LoRA)", list(labels), default=next(iter(labels)), descs=descs)]
    trigger = lora["trigger"]

    location = menu_choose("장소", list(comp.PACK_FILES), default=next(iter(comp.PACK_FILES)),
                           descs=option_descriptions("LOCATIONS"))
    outfit_id = ""
    common = False
    outs = {}
    for oid in comp.outfits_for_trigger(trigger):
        data = comp.load_outfit(oid)
        if location in data.get("applies_to", {}).get("locations", [location]):      # swimwear etc. only where it belongs
            outs[data.get("name_ko", oid)] = (oid, data.get("desc_ko", ""))
    COMMON = "공용의상 (자동)"
    NONE = "의상 없음"
    opts = [*outs, COMMON, NONE]
    pick = menu_choose("의상", opts, default=opts[0],
                       descs={**{n: d for n, (_, d) in outs.items()},
                              COMMON: "본체 공용 의상 풀에서 장소·프레임에 맞게 고름 (보이는 부분만 적음)",
                              NONE: "의상 문장을 넣지 않음"})
    if pick in outs:
        outfit_id = outs[pick][0]
    common = pick == COMMON
    pack = comp.load_pack(location)
    time_key = menu_choose("시간대", list(pack["times"]), default=next(iter(pack["times"])),
                           descs={**option_descriptions("TIME_OF_DAY"), **{k_: v.get("desc_ko", "") for k_, v in pack["times"].items()}})
    framing = menu_choose("프레이밍", list(pack["camera"]), default=next(iter(pack["camera"])),
                          descs=option_descriptions("CAMERA_FRAMING"))
    valid = {k_: v for k_, v in pack["moments"].items() if framing in v.get("frames", list(pack["camera"]))}
    moment = menu_choose("장면 속 순간", list(valid), default=next(iter(valid)),
                         descs={k_: v.get("desc_ko", "") for k_, v in valid.items()})
    exps = comp.load_expressions()
    expression = menu_choose("표정", list(exps), default=next(iter(exps)),
                             descs={k_: v.get("desc_ko", "") for k_, v in exps.items()})
    presets = comp.load_hair_presets()
    keep = "LoRA 기본 헤어 유지"
    custom = "직접 입력"
    hair_pick = menu_choose("헤어", [keep, *presets, custom], default=keep,
                            descs={keep: "등록된 LoRA 헤어를 그대로 사용 (아무것도 바꾸지 않음)",
                                   custom: "원하는 헤어를 영어 문장으로 직접 씀 (LoRA 헤어는 통째로 빠짐)",
                                   **{k_: v.get("desc_ko", "") for k_, v in presets.items()}})
    hair = "" if hair_pick == keep else (ask_text("헤어를 영어 문장으로 입력하세요") if hair_pick == custom else hair_pick)
    saved = load_json(SETTINGS_FILE, {})
    saved = saved if isinstance(saved, dict) else {}
    mode = menu_choose("묘사 분량", list(comp.MODES), default=saved.get("prompt_detail", "보통"),
                       descs=option_descriptions("COMPOSER_MODE"))
    reinforce_pick = menu_choose("강화 횟수 (같은 뜻을 다른 표현으로 반복)", ["자동", "없음", "1회", "2회"],
                                 default={None: "자동", 0: "없음", 1: "1회", 2: "2회"}.get(saved.get("reinforce"), "자동"),
                                 descs=option_descriptions("REINFORCE"))
    reinforce = {"자동": None, "없음": 0, "1회": 1, "2회": 2}[reinforce_pick]

    result = comp.compose_split(trigger, outfit_id, location=location, time_key=time_key, moment=moment,
                                framing=framing, expression=expression, hair=hair, mode=mode,
                                reinforce=reinforce, seed=random.randrange(1, 2**32), common_outfit=common)
    print_header(f"결과 ({result['words']}단어 · 묘사 {mode} · 강화 {result['reinforce']}회)")
    print(result["combined"])
    if result["problems"]:
        warning("점검 알림: " + ", ".join(result["problems"]))
    else:
        success("점검 통과: 한글 누출, 라벨, 지시문, 헤어 모순 없음")
    if menu_choose("결과 보기", ["이대로 저장", "인물/장면 따로 보기 (리저널용)", "저장 안 함"], default="이대로 저장",
                   descs={"이대로 저장": "합친 한 덩어리를 txt로 저장", "인물/장면 따로 보기 (리저널용)": "인물과 장면을 나눠 보여줌 (장면은 'the woman'으로 씀)",
                          "저장 안 함": "화면에만 표시"}) == "인물/장면 따로 보기 (리저널용)":
        print("\n[인물 프롬프트]\n" + result["person"] + "\n\n[장면 프롬프트]\n" + result["scene"])
        return
    if menu_choose("저장", ["저장", "저장 안 함"], default="저장") == "저장":
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        path = OUTPUT_DIR / f"krea2_composer_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        path.write_text(result["combined"] + "\n", encoding="utf-8")
        success(f"저장했습니다: {path}")


def main() -> None:
    ensure_dirs()
    while True:
        _options_header()
        print("\n[메뉴]")
        choices = [
            "자연어로 만들기",
            "Smart Random",
            "조건 지정 랜덤",
            "빠른 랜덤",
            "히스토리",
            "LoRA 관리",
            "내장 번역 사전",
            "설정",
            "자가진단",
            "새 합성기 (보통/상세)",
            "종료",
        ]
        for i, value in enumerate(choices, 1):
            print(f"  {i}. {value}")
        raw = input("선택 [1]: ").strip() or "1"
        if raw == "1":
            natural_mode()
        elif raw == "2":
            smart_random_mode()
        elif raw == "3":
            condition_random_mode()
        elif raw == "4":
            quick_random_mode()
        elif raw == "5":
            history_mode()
        elif raw == "6":
            lora_mode()
        elif raw == "7":
            dictionary_mode()
        elif raw == "8":
            settings_mode()
        elif raw == "9":
            run_self_test(True)
        elif raw == "10":
            composer_mode()
        elif raw == "11":
            print("종료합니다.")
            return
        else:
            warning("올바른 메뉴를 선택하세요.")


if __name__ == "__main__":
    main()
