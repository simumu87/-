#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scene consistency rules (v11): which activity, interaction, pose and light belong together.

The rules are data: krea2_prompt_configs/scene_rules.json overrides the built-in defaults below, so they can be
edited without touching the program. Families:

    seated / walking / standing / active      pose and activity families
    free                                      an activity that does not force a posture (conversation, coffee ...)

An interaction belongs to one family, or is "any" (hand holding, hugging an arm ...) and then follows the activity.
"""
from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_RULES: Dict[str, Any] = {
    "pose_family": {
        "standing": ["편안하게 서기", "한쪽 다리에 기대 서기", "벽에 기대 서기", "난간에 기대기", "창가에 서기",
                     "서로 마주 보기", "가볍게 스트레칭", "포옹하기"],
        "walking": ["걷기", "천천히 걷기", "손잡고 걷기", "달리기 동작"],
        "seated": ["벤치에 앉기", "소파에 편하게 앉기", "의자에 앉아 읽기", "책상에 앉아 공부하기", "바닥에 앉기",
                   "무릎 꿇고 앉기", "바닥에 다리를 뻗고 앉기", "다리를 꼬고 앉기", "창가에 앉기", "나란히 앉기",
                   "마주 앉기", "기타 연주", "피아노 연주"],
        "active": ["요가 자세", "자전거 타기"],
    },
    "activity_family": {
        "seated": ["책 읽기", "잡지 보기", "공부하기", "노트북 작업", "화상회의", "그림 그리기", "글쓰기", "영화 보기",
                   "게임하기", "보드게임", "아침 식사", "저녁 식사", "음악 듣기", "업무 보기", "피아노 연주",
                   "기타 연주", "악기 연주"],
        "walking": ["산책", "저녁 산책", "비 오는 날 산책", "해변 산책", "바닷가 산책", "손잡고 걷기", "여행 출발"],
        "standing": ["요리하기", "베이킹", "식물 돌보기", "정리하기", "사진 찍기", "기념사진", "사진 촬영",
                     "함께 요리하기", "전시 관람", "서점 구경", "기차 기다리기", "호텔 체크인", "아침 준비",
                     "여행 준비", "가볍게 포옹하기"],
        "active": ["조깅", "자전거", "자전거 타기", "요가하기", "가볍게 운동하기"],
    },
    "interaction_family": {
        "seated": ["마주 앉아 대화", "나란히 앉아 대화", "함께 책 보기", "함께 사진 보기", "함께 음악 듣기"],
        "walking": ["나란히 걷기"],
        "standing": ["가벼운 포옹", "하이파이브", "선물 건네기", "함께 쇼핑하기", "함께 전시 관람", "함께 요리하기",
                     "커피 건네기"],
        "any": ["없음", "손잡기", "팔짱", "어깨에 기대기", "장난스럽게 웃기"],
    },
    # two-person poses forced by an interaction: [pose A, pose B]
    "interaction_poses": {
        "마주 앉아 대화": ["마주 앉기", "마주 앉기"],
        "나란히 앉아 대화": ["나란히 앉기", "나란히 앉기"],
        "함께 책 보기": ["나란히 앉기", "나란히 앉기"],
        "함께 사진 보기": ["나란히 앉기", "나란히 앉기"],
        "함께 음악 듣기": ["나란히 앉기", "나란히 앉기"],
        "나란히 걷기": ["걷기", "걷기"],
        "가벼운 포옹": ["포옹하기", "포옹하기"],
        "하이파이브": ["서로 마주 보기", "서로 마주 보기"],
        "선물 건네기": ["서로 마주 보기", "서로 마주 보기"],
        "커피 건네기": ["서로 마주 보기", "서로 마주 보기"],
        "함께 쇼핑하기": ["편안하게 서기", "편안하게 서기"],
        "함께 전시 관람": ["편안하게 서기", "편안하게 서기"],
        "함께 요리하기": ["편안하게 서기", "편안하게 서기"],
    },
    # poses of an "any" interaction follow the activity family: [pose A, pose B]
    "family_pair_poses": {
        "seated": ["나란히 앉기", "나란히 앉기"],
        "walking": ["걷기", "걷기"],
        "standing": ["편안하게 서기", "편안하게 서기"],
        "active": ["편안하게 서기", "편안하게 서기"],
        "free": ["편안하게 서기", "편안하게 서기"],
    },
    "light": {
        "daylight_sources": ["창문 자연광", "부드러운 북향광", "오후 햇빛", "골든아워", "맑은 정오"],
        "sun_sources": ["골든아워", "맑은 정오", "오후 햇빛"],
        "indoor_night_sources": ["스탠드 램프", "벽 스콘스", "천장 확산광", "카페 펜던트"],
        "night_times": ["밤", "심야"],
        "city_locations": ["도시 거리", "기차역"],
        "outdoor_night_source": "달빛",
        "city_night_source": "도시 야간광",
    },
    "clothing": {
        "warm_garments": ["울 코트", "트렌치코트", "니트 스웨터", "블레이저", "데님 재킷"],
        "light_garments": ["반바지", "반팔 티셔츠", "가벼운 원피스"],
        "sport_garments": ["운동복 상의", "운동용 레깅스", "조거 팬츠"],
        "sleep_garments": ["파자마"],
        "hot_locations": ["해변"],
        "formal_locations": ["미술관", "호텔 로비", "서점", "도서관"],
        "harsh_weather": ["눈", "폭우"],
        "indoor_only_footwear": ["실내 슬리퍼"],
    },
}


class Rules:
    """Loaded rules with small helper queries (cached)."""

    def __init__(self, path: Optional[Path] = None) -> None:
        self.data = json.loads(json.dumps(DEFAULT_RULES))
        if path and path.exists():
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                for key, value in loaded.items():
                    if key in self.data and isinstance(value, dict):
                        self.data[key].update(value)
            except (OSError, ValueError):
                pass
        self.pose_to_family = {p: f for f, ps in self.data["pose_family"].items() for p in ps}
        self.activity_to_family = {a: f for f, acts in self.data["activity_family"].items() for a in acts}
        self.interaction_to_family = {i: f for f, its in self.data["interaction_family"].items() for i in its}

    # --- families ---------------------------------------------------------------------------
    def pose_family(self, pose_key: str) -> str:
        return self.pose_to_family.get(pose_key, "free")

    def activity_family(self, activity_key: str) -> str:
        return self.activity_to_family.get(activity_key, "free")

    def interaction_family(self, interaction_key: str) -> str:
        return self.interaction_to_family.get(interaction_key, "any")

    # --- interaction ------------------------------------------------------------------------
    def interaction_fits(self, interaction_key: str, activity_key: str) -> bool:
        fam_i = self.interaction_family(interaction_key)
        fam_a = self.activity_family(activity_key)
        return fam_i == "any" or fam_a in ("free",) or fam_i == fam_a or (fam_a == "active" and fam_i == "any")

    def interaction_candidates(self, activity_key: str) -> List[str]:
        fam_a = self.activity_family(activity_key)
        pool: List[str] = []
        for fam, items in self.data["interaction_family"].items():
            if fam == "any" or fam_a == "free" or fam == fam_a:
                pool += items
        pool = [x for x in pool if x != "없음"]
        return pool or ["장난스럽게 웃기"]

    # --- poses ------------------------------------------------------------------------------
    def pair_poses(self, interaction_key: str, activity_key: str) -> Tuple[str, str]:
        forced = self.data["interaction_poses"].get(interaction_key)
        if forced:
            return forced[0], forced[1]
        fam_a = self.activity_family(activity_key)
        if interaction_key == "손잡기" and fam_a == "walking":
            return "손잡고 걷기", "손잡고 걷기"
        pair = self.data["family_pair_poses"].get(fam_a, self.data["family_pair_poses"]["free"])
        return pair[0], pair[1]

    def pose_fits_activity(self, pose_key: str, activity_key: str) -> bool:
        fam_a = self.activity_family(activity_key)
        fam_p = self.pose_family(pose_key)
        return fam_a in ("free", fam_p) or (fam_a == "active" and fam_p in ("active", "walking"))

    # --- light ------------------------------------------------------------------------------
    def light_ok(self, source_key: str, time_key: str, weather_key: str, outdoor: bool, location_key: str) -> bool:
        light = self.data["light"]
        night = time_key in light["night_times"]
        if night and source_key in light["daylight_sources"]:
            return False
        if weather_key in ("비", "폭우", "눈", "안개", "흐림") and source_key in light["sun_sources"]:
            return False
        if not outdoor and night and source_key not in light["indoor_night_sources"] and source_key != "갤러리 조명":
            return source_key in ("비 오는 날 확산광",) and False
        if outdoor and source_key == light["city_night_source"] and location_key not in light["city_locations"] and night:
            return False
        return True

    def night_source(self, outdoor: bool, location_key: str, rng: random.Random) -> str:
        light = self.data["light"]
        if not outdoor:
            return rng.choice(light["indoor_night_sources"])
        return light["city_night_source"] if location_key in light["city_locations"] else light["outdoor_night_source"]

    # --- clothing ---------------------------------------------------------------------------
    def clothing_ok(self, garment_key: str, footwear_key: str, location_key: str, weather_key: str, outdoor: bool) -> bool:
        cl = self.data["clothing"]
        if garment_key in cl["warm_garments"] and location_key in cl["hot_locations"]:
            return False
        if garment_key in cl["light_garments"] and outdoor and weather_key in cl["harsh_weather"]:
            return False
        if garment_key in cl["sleep_garments"] and outdoor:
            return False
        if garment_key in cl["sport_garments"] and location_key in cl["formal_locations"]:
            return False
        if footwear_key in cl["indoor_only_footwear"] and outdoor:
            return False
        return True


_CACHE: Dict[str, Rules] = {}


def get_rules(config_dir: Path) -> Rules:
    key = str(config_dir)
    if key not in _CACHE:
        _CACHE[key] = Rules(config_dir / "scene_rules.json")
    return _CACHE[key]


def export_rules(config_dir: Path, force: bool = False) -> Path:
    """Write the built-in rules to scene_rules.json so they can be edited."""
    path = config_dir / "scene_rules.json"
    if force or not path.exists():
        config_dir.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(DEFAULT_RULES, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path
