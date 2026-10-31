#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Scene consistency check: python tests/scene_consistency.py [seeds]

Counts automatically resolved scenes whose parts contradict each other (pose vs interaction, activity vs pose,
light vs time/weather/place, clothing vs place/weather). The detectors are written independently of
krea2_rules.py so they can catch mistakes in the rules too. Exit code 1 when anything is found.
"""
import collections
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import krea2_prompt_studio as k  # noqa: E402

SEATED_POSES = {"벤치에 앉기", "소파에 편하게 앉기", "의자에 앉아 읽기", "책상에 앉아 공부하기", "바닥에 앉기", "무릎 꿇고 앉기",
                "바닥에 다리를 뻗고 앉기", "다리를 꼬고 앉기", "창가에 앉기", "나란히 앉기", "마주 앉기", "기타 연주", "피아노 연주"}
WALK_POSES = {"걷기", "천천히 걷기", "손잡고 걷기", "달리기 동작"}
STAND_POSES = {"편안하게 서기", "한쪽 다리에 기대 서기", "벽에 기대 서기", "난간에 기대기", "창가에 서기", "서로 마주 보기",
               "가볍게 스트레칭", "포옹하기"}
SEATED_I = {"마주 앉아 대화", "나란히 앉아 대화", "함께 책 보기", "함께 사진 보기", "함께 음악 듣기"}
WALK_I = {"나란히 걷기"}
STAND_I = {"가벼운 포옹", "하이파이브", "선물 건네기", "함께 쇼핑하기", "함께 전시 관람", "함께 요리하기", "커피 건네기"}
SEAT_ACT = {"책 읽기", "잡지 보기", "공부하기", "노트북 작업", "화상회의", "그림 그리기", "글쓰기", "영화 보기", "게임하기",
            "보드게임", "아침 식사", "저녁 식사", "음악 듣기", "업무 보기"}
WALK_ACT = {"산책", "저녁 산책", "비 오는 날 산책", "해변 산책", "바닷가 산책", "손잡고 걷기"}
STAND_ACT = {"요리하기", "베이킹", "식물 돌보기", "정리하기", "사진 찍기", "기념사진", "함께 요리하기", "전시 관람", "서점 구경"}
DAY_SRC = {"창문 자연광", "부드러운 북향광", "오후 햇빛", "골든아워", "맑은 정오"}
SUN_SRC = {"골든아워", "맑은 정오", "오후 햇빛"}
WARM = {"울 코트", "트렌치코트", "니트 스웨터", "블레이저", "데님 재킷"}
LIGHT_G = {"반바지", "반팔 티셔츠", "가벼운 원피스"}
SPORT = {"운동복 상의", "운동용 레깅스", "조거 팬츠"}


def main(seeds=None, quiet=False) -> int:
    if seeds is None:
        seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 400
    src_by_en = {v: key for key, v in k.LIGHT_SOURCES.items()}
    count, hits, examples, total = collections.Counter(), collections.Counter(), {}, 0

    def hit(name, detail):
        hits[name] += 1
        examples.setdefault(name, detail)

    for seed in range(1, seeds + 1):
        for people in (1, 2):
            c = k.defaults()
            k.set_constraint_value(c, "people", str(people))
            try:
                sc = k.build_scene(seed, c, None, None, "", False)
            except Exception as exc:  # noqa: BLE001
                hit("build failed", repr(exc)[:80])
                continue
            total += 1
            pa = sc.pose_a["pose_key"]
            pb = sc.pose_b["pose_key"] if sc.pose_b else None
            act, inter = sc.activity_key, sc.interaction_key
            if people == 2:
                if inter in SEATED_I and not (pa in SEATED_POSES and pb in SEATED_POSES):
                    hit("앉는 상호작용인데 자세가 앉기 아님", (inter, pa, pb))
                if inter in WALK_I and not (pa in WALK_POSES and pb in WALK_POSES):
                    hit("걷는 상호작용인데 자세가 걷기 아님", (inter, pa, pb))
                if inter in STAND_I and not (pa in STAND_POSES and pb in STAND_POSES):
                    hit("서서 하는 상호작용인데 자세가 서기 아님", (inter, pa, pb))
                if act in SEAT_ACT and inter in WALK_I | STAND_I:
                    hit("앉는 활동에 서거나 걷는 상호작용", (act, inter))
                if act in WALK_ACT and inter in SEATED_I | STAND_I:
                    hit("걷는 활동에 앉거나 서는 상호작용", (act, inter))
            if act in SEAT_ACT and pa not in SEATED_POSES and k.get_value(c, "pose") == "auto":
                hit("앉는 활동인데 앉는 자세가 아님", (act, pa))
            if act in WALK_ACT and pa not in WALK_POSES:
                hit("걷는 활동인데 걷는 자세가 아님", (act, pa))
            if act in STAND_ACT and pa not in STAND_POSES:
                hit("서서 하는 활동인데 서는 자세가 아님", (act, pa))
            src = src_by_en.get(sc.lighting.source, sc.lighting.source)
            outdoor = k.LOCATIONS[sc.location_key].get("outdoor")
            if sc.time_key in {"밤", "심야"} and src in DAY_SRC:
                hit("밤인데 낮 광원", (sc.time_key, src, sc.location_key))
            if outdoor and sc.time_key in {"밤", "심야"} and sc.location_key in {"해변", "공원", "산책로"} and src == "도시 야간광":
                hit("해변/공원/산책로에 도시 야간광", (sc.location_key, src))
            if sc.weather_key in {"비", "폭우", "눈", "안개"} and src in SUN_SRC:
                hit("비/눈/안개인데 맑은 날 햇빛", (sc.weather_key, src))
            garment = next((gk for gk, gv in k.GARMENTS.items() if gv[0] == sc.clothing_a.garment_en), None)
            if garment in WARM and sc.location_key == "해변":
                hit("해변에 두꺼운 겉옷", (garment, sc.location_key))
            if garment in LIGHT_G and sc.weather_key in {"눈", "폭우"} and outdoor:
                hit("눈/폭우 야외에 반바지·반팔", (garment, sc.weather_key))
            if garment == "파자마" and outdoor:
                hit("파자마로 야외", (garment, sc.location_key))
            if garment in SPORT and sc.location_key in {"미술관", "호텔 로비", "서점", "도서관"}:
                hit("격식 장소에 운동복", (garment, sc.location_key))
            if "slippers" in sc.clothing_a.footwear.lower() and outdoor:
                hit("실내 슬리퍼로 야외", (sc.clothing_a.footwear, sc.location_key))
    if not quiet or hits:
        print(f"{total} scenes checked, {sum(hits.values())} contradictions")
        for name, n in sorted(hits.items()):
            print(f"  {n:4d} ({100 * n / total:4.1f}%) {name} 예: {examples[name]}")
    return 1 if hits else 0


if __name__ == "__main__":
    sys.exit(main())
