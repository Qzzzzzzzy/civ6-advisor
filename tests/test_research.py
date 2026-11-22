"""科技/市政推荐测试：不同文明、不同局势应该推荐不同的东西。"""

import dataclasses

from civ_mcp import lua as lq

from civ6_advisor.facts import EmpireFacts, ResourceTile
from civ6_advisor.mock import mock_situation
from civ6_advisor.research import recommend_text, tracks
from civ6_advisor.rules import analyze

ANCIENT_TECHS = [
    ("制陶术", "POTTERY", 5, ""), ("畜牧业", "ANIMAL_HUSBANDRY", 5, ""), ("采矿业", "MINING", 5, ""),
    ("航海术", "SAILING", 8, ""), ("占星术", "ASTROLOGY", 8, ""), ("灌溉", "IRRIGATION", 8, "种植园"),
    ("弓术", "ARCHERY", 8, "弓箭手"), ("书写", "WRITING", 8, "学院区"), ("石工术", "MASONRY", 8, "古城墙"),
    ("青铜器", "BRONZE_WORKING", 8, "枪兵"),
]
ANCIENT_CIVICS = [("法典", "CODE_OF_LAWS", 4), ("技艺", "CRAFTSMANSHIP", 8), ("对外贸易", "FOREIGN_TRADE", 8),
                  ("早期帝国", "EARLY_EMPIRE", 9), ("神秘主义", "MYSTICISM", 9)]


def start_game(civ: str, leader: str = "") -> object:
    """第 5 回合左右：一座城，酋邦，什么都没研究。"""
    sit = mock_situation()
    sit.civ = dataclasses.replace(sit.civ, civ_type=civ, leader_type=leader, abilities=[])
    sit.overview = dataclasses.replace(sit.overview, turn=5, current_research="None", current_civic="None",
                                       religions_founded=0, num_cities=1)
    sit.cities = [dataclasses.replace(sit.cities[0], amenities=1, housing=10, population=2, unimproved_resources=[])]
    sit.threats = []
    sit.diplomacy = []
    sit.facts = EmpireFacts()  # 领土内没有资源，各测试按需添加
    sit.government = lq.GovernmentStatus("酋邦", "GOVERNMENT_CHIEFDOM", [lq.PolicySlot(0, "SLOT_MILITARY", None, None)])
    sit.tech = lq.TechCivicStatus(
        "None", 0, "None", 0,
        [lq.TechOption(n, "TECH_" + t, 50, 0, turns, False, "", u) for n, t, turns, u in ANCIENT_TECHS],
        [lq.CivicOption(n, "CIVIC_" + t, 30, 0, turns, False, "") for n, t, turns in ANCIENT_CIVICS],
    )
    return sit


def top(sit):
    t, c = tracks(sit)
    return t.picks[0], c.picks[0]


def test_religious_civ_wants_astrology():
    tech, civic = top(start_game("CIVILIZATION_RUSSIA"))
    assert tech.name == "占星术" and "俄罗斯需要尽快创立宗教" in tech.reasons


def test_science_civ_wants_writing():
    tech, _ = top(start_game("CIVILIZATION_KOREA"))
    assert tech.name == "书写" and any("朝鲜擅长科技" in r for r in tech.reasons)


def test_threat_pushes_defense():
    sit = start_game("CIVILIZATION_KOREA")
    c = sit.cities[0]
    sit.threats = [lq.ThreatInfo("UNIT_BARBARIAN_HORSE_ARCHER", c.x + 2, c.y, 100, 100, 25, 25, 2)]
    tech, _ = top(sit)
    assert tech.name in ("弓术", "石工术") and "城市附近有敌军，需要防御" in tech.reasons


def test_chiefdom_wants_code_of_laws():
    _, civic = top(start_game("CIVILIZATION_ZULU"))
    assert civic.name == "法典" and "还在酋邦，先拿到第一个政体" in civic.reasons


def test_unimproved_luxury_unlocks():
    sit = start_game("CIVILIZATION_ZULU")
    sit.facts.resources = [ResourceTile("西安", 21, 15, "RESOURCE_SILK", "luxury", "IMPROVEMENT_PLANTATION",
                                        "TECH_IRRIGATION", False)]
    t, _ = tracks(sit)
    irrigation = next(p for p in t.picks if p.name == "灌溉")
    assert irrigation.reasons[0] == "能改良西安的奢侈品丝绸"


def test_legacy_resource_list_still_works():
    sit = start_game("CIVILIZATION_ZULU")
    sit.facts = None
    sit.cities[0] = dataclasses.replace(sit.cities[0], unimproved_resources=["SILK@21,15"])
    t, _ = tracks(sit)
    irrigation = next(p for p in t.picks if p.name == "灌溉")
    assert any("能改良西安的奢侈品丝绸" in r for r in irrigation.reasons)


def test_different_civs_get_different_advice():
    picks = {civ: top(start_game(civ))[0].name for civ in
             ("CIVILIZATION_RUSSIA", "CIVILIZATION_KOREA", "CIVILIZATION_ZULU")}
    assert len(set(picks.values())) >= 2, picks


def test_current_research_shown_with_next_pick():
    sit = start_game("CIVILIZATION_KOREA")
    sit.tech = dataclasses.replace(sit.tech, current_research="书写", current_research_turns=7)
    t, _ = tracks(sit)
    assert t.current.name == "书写" and t.current_turns == 7
    assert all(p.name != "书写" for p in t.picks)


def test_research_findings_are_tagged_and_use_recommendation():
    f = analyze(start_game("CIVILIZATION_RUSSIA"))
    r = next(x for x in f if x.tag == "research")
    assert "推荐 占星术" in r.action
    assert next(x for x in f if x.tag == "civic")


def test_recommend_text_alternatives():
    t, _ = tracks(start_game("CIVILIZATION_KOREA"))
    s = recommend_text(t)
    assert s.startswith("推荐 书写") and "备选：" in s


# ---------------------------------------------------------------- 你截图里的场景：第 12 回合的埃塞俄比亚


def ethiopia_t12(builder: bool = True):
    """一座城、有建造者，领土里有柑橘(缺灌溉)、羊(缺畜牧业)、石头(缺采矿)、螃蟹(缺航海)，还没有宗教。"""
    sit = start_game("CIVILIZATION_ETHIOPIA", "LEADER_MENELIK")
    sit.overview = dataclasses.replace(sit.overview, turn=12, religions_founded=0, religions_max=4)
    sit.cities = [dataclasses.replace(sit.cities[0], name="亚的斯亚贝巴", x=30, y=18, districts=["DISTRICT_CITY_CENTER"])]
    sit.tech.available_techs = [t for t in sit.tech.available_techs if t.tech_type != "TECH_POTTERY"]
    sit.facts = EmpireFacts(techs={"TECH_POTTERY"}, resources=[
        ResourceTile("亚的斯亚贝巴", 30, 20, "RESOURCE_CITRUS", "luxury", "IMPROVEMENT_PLANTATION", "TECH_IRRIGATION", False),
        ResourceTile("亚的斯亚贝巴", 29, 17, "RESOURCE_SHEEP", "bonus", "IMPROVEMENT_PASTURE", "TECH_ANIMAL_HUSBANDRY", False),
        ResourceTile("亚的斯亚贝巴", 31, 17, "RESOURCE_STONE", "bonus", "IMPROVEMENT_QUARRY", "TECH_MINING", False),
        ResourceTile("亚的斯亚贝巴", 27, 18, "RESOURCE_CRABS", "bonus", "IMPROVEMENT_FISHING_BOATS", "TECH_SAILING", False),
    ])
    from civ_mcp import lua as lq2

    sit.units = [lq2.UnitInfo(unit_id=9, unit_index=9, name="建造者", unit_type="UNIT_BUILDER", x=30, y=19,
                              moves_remaining=2, max_moves=2, health=100, max_health=100, build_charges=3)] if builder else []
    return sit


def test_ethiopia_t12_astrology_first_and_builder_is_consistent():
    sit = ethiopia_t12()
    t, _ = tracks(sit)
    assert t.picks[0].name == "占星术", [(p.name, round(p.score)) for p in t.picks[:4]]
    assert any("宗教名额只剩 4 个" in r for r in t.picks[0].reasons)
    # 改良类科技：理由写明能改良什么，并提到建造者闲着
    irr = next(p for p in t.picks if p.name == "灌溉")
    assert irr.reasons[0].startswith("能改良亚的斯亚贝巴的奢侈品柑橘") and "建造者正闲着" in irr.reasons[0]
    # 建造者建议不再说"去改良"，而是说明都缺科技
    f = analyze(sit)
    b = next(x for x in f if "建造者" in x.title)
    assert b.title == "建造者暂时没有资源可以改良"
    assert "柑橘 需要灌溉" in b.detail and "羊 需要畜牧业" in b.detail
    assert not any("优先改良" in x.action for x in f)


def test_luxury_beats_bonus_resource_tech():
    sit = ethiopia_t12()
    t, _ = tracks(sit)
    score = {p.name: p.score for p in t.picks}
    assert score["灌溉"] > score["畜牧业"]  # 柑橘（奢侈品）比羊（加成资源）重要


def test_holy_site_already_built_no_rush():
    sit = ethiopia_t12()
    sit.cities[0] = dataclasses.replace(sit.cities[0], districts=["DISTRICT_CITY_CENTER", "DISTRICT_HOLY_SITE"])
    t, _ = tracks(sit)
    astro = next(p for p in t.picks if p.name == "占星术")
    assert not any("宗教名额只剩" in r for r in astro.reasons)
