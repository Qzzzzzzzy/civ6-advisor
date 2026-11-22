"""离线演示数据：不开游戏也能测试 MCP 和规则。

设置环境变量 CIV6_ADVISOR_MOCK=1 启用。数据是一局标准速度、第 68 回合的中国开局，
刻意放了几个问题（城市空闲、蛮族逼近、政策槽空着、宜居度为负等）。
"""

from __future__ import annotations

from civ_mcp import lua as lq

from civ6_advisor.civ_info import Ability, CivIdentity
from civ6_advisor.facts import EmpireFacts, ResourceTile
from civ6_advisor.game import Situation


def mock_situation() -> Situation:
    ov = lq.GameOverview(
        turn=68, player_id=0, civ_name="中国", leader_name="秦始皇",
        gold=520.0, gold_per_turn=6.5, science_yield=24.3, culture_yield=13.8, faith=85.0,
        current_research="数学", current_civic="None", num_cities=3, num_units=9,
        score=142, total_population=17, era_name="古典时代", era_score=19,
        era_dark_threshold=24, era_golden_threshold=36, difficulty="神级", game_speed_name="标准",
        speed_cost_multiplier=100, explored_land=410, total_land=1200,
        religions_founded=3, religions_max=4, gold_income=21.5, total_maintenance=15.0, unit_maintenance=9,
    )
    cities = [
        lq.CityInfo(city_id=65536, name="西安", x=20, y=14, population=8, food=14, production=19, gold=6,
                    science=11, culture=5, faith=2, housing=8, amenities=-1, turns_to_grow=9,
                    food_surplus=2.5, currently_building="DISTRICT_CAMPUS", production_turns_left=6, buildings=["PALACE", "MONUMENT"],
                    defense_strength=28, garrison_unit="弓箭手", wall_max_hp=100, wall_hp=100,
                    districts=["DISTRICT_CITY_CENTER", "DISTRICT_HOLY_SITE"]),
        lq.CityInfo(city_id=131073, name="北京", x=24, y=11, population=5, food=9, production=11, gold=3,
                    science=6, culture=3, faith=1, housing=7, amenities=1, turns_to_grow=6,
                    food_surplus=3.0, currently_building="nothing", defense_strength=18,
                    unimproved_resources=["IVORY@25,10", "HORSES@23,12"],
                    districts=["DISTRICT_CITY_CENTER"]),
        lq.CityInfo(city_id=196610, name="长安", x=17, y=18, population=4, food=6, production=7, gold=2,
                    science=4, culture=2, faith=0, housing=5, amenities=0, turns_to_grow=99,
                    food_surplus=0.0, currently_building="UNIT_SLINGER", production_turns_left=4,
                    defense_strength=15, loyalty=72, loyalty_per_turn=-3.0, turns_to_loyalty_flip=24,
                    districts=["DISTRICT_CITY_CENTER"]),
    ]
    units = [
        lq.UnitInfo(unit_id=1, unit_index=1, name="弓箭手", unit_type="UNIT_ARCHER", x=20, y=14,
                    moves_remaining=2, max_moves=2, health=100, max_health=100, combat_strength=15,
                    ranged_strength=25),
        lq.UnitInfo(unit_id=2, unit_index=2, name="剑士", unit_type="UNIT_SWORDSMAN", x=16, y=19,
                    moves_remaining=2, max_moves=2, health=30, max_health=100, combat_strength=36,
                    needs_promotion=True),
        lq.UnitInfo(unit_id=3, unit_index=3, name="勇士", unit_type="UNIT_WARRIOR", x=22, y=13,
                    moves_remaining=2, max_moves=2, health=100, max_health=100, combat_strength=20,
                    can_upgrade=True, upgrade_target="剑士", upgrade_cost=110),
        lq.UnitInfo(unit_id=4, unit_index=4, name="开拓者", unit_type="UNIT_SETTLER", x=21, y=15,
                    moves_remaining=2, max_moves=2, health=100, max_health=100),
    ]
    threats = [
        lq.ThreatInfo(unit_type="UNIT_BARBARIAN_HORSE_ARCHER", x=15, y=20, hp=100, max_hp=100,
                      combat_strength=25, ranged_strength=25, distance=1),
        lq.ThreatInfo(unit_type="UNIT_SPEARMAN", x=14, y=19, hp=100, max_hp=100,
                      combat_strength=25, ranged_strength=0, distance=2),
        lq.ThreatInfo(unit_type="UNIT_HORSEMAN", x=27, y=9, hp=100, max_hp=100, combat_strength=36,
                      ranged_strength=0, distance=3, owner_id=1, owner_name="蒙古"),
    ]
    tech = lq.TechCivicStatus(
        current_research="数学", current_research_turns=5, current_civic="None", current_civic_turns=0,
        available_techs=[
            lq.TechOption(name="数学", tech_type="TECH_MATHEMATICS", cost=200, progress_pct=40, turns=5,
                          boosted=False, boost_desc="", unlocks=""),
            lq.TechOption(name="建造", tech_type="TECH_CONSTRUCTION", cost=200, progress_pct=50, turns=3,
                          boosted=True, boost_desc="", unlocks="竞技场"),
        ],
        available_civics=[
            lq.CivicOption(name="政治哲学", civic_type="CIVIC_POLITICAL_PHILOSOPHY", cost=110, progress_pct=50,
                           turns=4, boosted=True, boost_desc=""),
            lq.CivicOption(name="戏剧与诗歌", civic_type="CIVIC_DRAMA_POETRY", cost=110, progress_pct=0,
                           turns=8, boosted=False, boost_desc=""),
        ],
    )
    diplomacy = [
        lq.CivInfo(player_id=1, civ_name="蒙古", leader_name="成吉思汗", has_met=True, is_at_war=False,
                   diplomatic_state="DENOUNCED", military_strength=310, num_cities=4),
        lq.CivInfo(player_id=2, civ_name="希腊", leader_name="伯里克利", has_met=True, is_at_war=False,
                   diplomatic_state="FRIENDLY", military_strength=150, num_cities=5),
    ]
    rivals = [
        lq.RivalSnapshot(id=1, name="蒙古", score=150, cities=4, pop=19, sci=20.0, cul=10.0, gold=12, mil=310,
                         techs=14, civics=10, faith=20, sci_vp=0, diplo_vp=2),
        lq.RivalSnapshot(id=2, name="希腊", score=171, cities=5, pop=22, sci=27.0, cul=25.0, gold=10, mil=150,
                         techs=15, civics=14, faith=40, sci_vp=0, diplo_vp=4),
    ]
    government = lq.GovernmentStatus(
        government_name="古典共和", government_type="GOVERNMENT_CLASSICAL_REPUBLIC",
        slots=[
            lq.PolicySlot(0, "SLOT_ECONOMIC", "POLICY_URBAN_PLANNING", "城市规划"),
            lq.PolicySlot(1, "SLOT_ECONOMIC", None, None),
            lq.PolicySlot(2, "SLOT_DIPLOMATIC", "POLICY_CHARISMATIC_LEADER", "魅力领袖"),
            lq.PolicySlot(3, "SLOT_WILDCARD", None, None),
        ],
        available_policies=[
            lq.PolicyInfo("POLICY_URBAN_PLANNING", "城市规划", "+1 生产力", "SLOT_ECONOMIC"),
            lq.PolicyInfo("POLICY_GOD_KING", "神王", "+1 信仰 +1 金币", "SLOT_ECONOMIC"),
            lq.PolicyInfo("POLICY_CHARISMATIC_LEADER", "魅力领袖", "+2 影响力", "SLOT_DIPLOMATIC"),
            lq.PolicyInfo("POLICY_DISCIPLINE", "纪律", "对蛮族 +5", "SLOT_MILITARY"),
        ],
    )
    governors = lq.GovernorStatus(points_available=1, points_spent=1, can_appoint=True)
    envoys = lq.EnvoyStatus(tokens_available=2, city_states=[
        lq.CityStateInfo(70, "日内瓦", "Scientific", 2, -1, "None", True),
        lq.CityStateInfo(71, "卡布尔", "Militaristic", 0, -1, "None", True),
        lq.CityStateInfo(72, "安特卫普", "Industrial", 1, 3, "蒙古", True),
    ])
    pantheon = lq.PantheonStatus(False, None, None, 85, [
        lq.BeliefInfo("BELIEF_RELIGIOUS_SETTLEMENTS", "宗教定居点", "送一个开拓者"),
        lq.BeliefInfo("BELIEF_MONUMENT_TO_THE_GODS", "众神纪念碑", "远古古典奇观 +15%"),
        lq.BeliefInfo("BELIEF_GOD_OF_THE_OPEN_SKY", "开阔天空之神", "牧场 +1 文化"),
        lq.BeliefInfo("BELIEF_DIVINE_SPARK", "神圣火花", "伟人点 +1"),
    ])
    notifications = [
        lq.GameNotification(type_name="NOTIFICATION_CHOOSE_CIVIC", message="选择一项市政", turn=68, x=-1, y=-1,
                            is_action_required=True),
    ]
    civ = CivIdentity(
        "CIVILIZATION_CHINA", "LEADER_QIN", "中国", "秦始皇",
        [
            Ability("CIV", "TRAIT_CIVILIZATION_DYNASTIC_CYCLE", "王朝更替", "尤里卡和鼓舞提供科技和市政 50% 的进度，而非 40%。"),
            Ability("LEADER", "FIRST_EMPEROR_TRAIT", "始皇帝", "建造者额外获得 1 次使用次数。建造者可以使用次数完成远古和古典时代奇观 15% 的进度。"),
            Ability("UNIT", "UNIT_CHINESE_CROUCHING_TIGER", "虎蹲炮", "中国特色中世纪远程单位。"),
            Ability("IMPROVEMENT", "IMPROVEMENT_GREAT_WALL", "长城", "只能建在边境上，提供防御、金币和文化。"),
        ],
    )
    settle_spots = [
        lq.SettleCandidate(x=24, y=18, score=88.0, total_food=14, total_prod=9, water_type="fresh",
                           resources=["L:SILK", "B:RICE"], luxury_count=1, strategic_count=0),
        lq.SettleCandidate(x=13, y=12, score=80.0, total_food=11, total_prod=12, water_type="coast",
                           resources=["S:IRON", "L:WINE"], luxury_count=1, strategic_count=1),
        lq.SettleCandidate(x=27, y=15, score=71.0, total_food=10, total_prod=8, water_type="none",
                           resources=[], luxury_count=0, strategic_count=0),
    ]
    production_options = {
        131073: [lq.ProductionOption("UNIT", u, cost, turns, gold) for u, cost, turns, gold in (
            ("UNIT_SETTLER", 80, 8, 320), ("UNIT_BUILDER", 50, 5, 200), ("UNIT_SLINGER", 35, 4, 140),
            ("UNIT_ARCHER", 60, 6, 240), ("UNIT_SCOUT", 30, 3, 120))] + [
            lq.ProductionOption("BUILDING", "BUILDING_MONUMENT", 60, 6, 240),
            lq.ProductionOption("BUILDING", "BUILDING_GRANARY", 65, 6, 260),
            lq.ProductionOption("DISTRICT", "DISTRICT_CAMPUS", 54, 5),
            lq.ProductionOption("DISTRICT", "DISTRICT_HOLY_SITE", 54, 5),
        ],
    }
    facts = EmpireFacts(
        techs={"TECH_POTTERY", "TECH_MINING", "TECH_WRITING", "TECH_BRONZE_WORKING"},
        civics={"CIVIC_CODE_OF_LAWS", "CIVIC_FOREIGN_TRADE"},
        resources=[
            ResourceTile("北京", 25, 10, "RESOURCE_IVORY", "luxury", "IMPROVEMENT_CAMP", "TECH_ANIMAL_HUSBANDRY", False),
            ResourceTile("北京", 23, 12, "RESOURCE_HORSES", "strategic", "IMPROVEMENT_PASTURE", "TECH_ANIMAL_HUSBANDRY", False),
            ResourceTile("西安", 19, 13, "RESOURCE_STONE", "bonus", "IMPROVEMENT_QUARRY", "TECH_MINING", True),
        ],
        terrain={"TERRAIN_GRASS": 20, "TERRAIN_PLAINS": 14, "HILLS": 9, "FEATURE_FOREST": 8, "RIVER": 7,
                 "RES_IMPROVEMENT_PASTURE": 5, "RES_IMPROVEMENT_CAMP": 2, "RESOURCECLASS_LUXURY": 3},
    )
    return Situation(
        overview=ov, civ=civ, settle_spots=settle_spots, production_options=production_options, facts=facts, cities=cities, units=units, threats=threats, tech=tech, diplomacy=diplomacy,
        notifications=notifications, rivals=rivals, government=government, governors=governors, envoys=envoys,
        pantheon=pantheon,
    )
