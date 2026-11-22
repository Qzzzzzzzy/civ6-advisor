"""具体决策规则：政策卡、万神殿、总督、使者、金币购买、尤里卡时机。"""

import dataclasses

from civ_mcp import lua as lq
from test_research import start_game

from civ6_advisor.mock import mock_situation
from civ6_advisor.rules import analyze
from civ6_advisor.rules.decisions import plan_policies


def titles(sit):
    return {f.title: f for f in analyze(sit)}


def find(sit, prefix):
    return next((f for f in analyze(sit) if f.title.startswith(prefix)), None)


def test_policy_colonization_when_building_settlers():
    sit = mock_situation()
    sit.cities = [dataclasses.replace(c, currently_building="UNIT_SETTLER") if c.name == "西安" else c for c in sit.cities]
    sit.government = lq.GovernmentStatus("酋邦", "GOVERNMENT_CHIEFDOM", [
        lq.PolicySlot(0, "SLOT_ECONOMIC", "POLICY_URBAN_PLANNING", "城市规划"),
        lq.PolicySlot(1, "SLOT_MILITARY", None, None)], [
        lq.PolicyInfo("POLICY_URBAN_PLANNING", "城市规划", "", "SLOT_ECONOMIC"),
        lq.PolicyInfo("POLICY_COLONIZATION", "殖民", "", "SLOT_ECONOMIC"),
        lq.PolicyInfo("POLICY_DISCIPLINE", "纪律", "", "SLOT_MILITARY"),
        lq.PolicyInfo("POLICY_AGOGE", "斯巴达教育", "", "SLOT_MILITARY")])
    plan = {x["slot"].slot_index: x for x in plan_policies(sit)}
    assert plan[0]["best"].policy_type == "POLICY_COLONIZATION"  # 在造开拓者：殖民 > 城市规划
    # 长安在造投石兵：斯巴达教育（+50%）比纪律更实在
    assert plan[1]["best"].policy_type == "POLICY_AGOGE" and "在造近战/远程" in plan[1]["reason"]
    f = find(sit, "政策：建议换卡")
    assert f and "殖民" in f.detail and "免费换" in f.action


def test_no_policy_swap_for_small_gain():
    sit = mock_situation()
    sit.government = lq.GovernmentStatus("酋邦", "GOVERNMENT_CHIEFDOM", [
        lq.PolicySlot(0, "SLOT_ECONOMIC", "POLICY_URBAN_PLANNING", "城市规划")], [
        lq.PolicyInfo("POLICY_LAND_SURVEYORS", "土地测量员", "", "SLOT_ECONOMIC")])
    assert not find(sit, "政策")


def test_pantheon_follows_terrain():
    sit = start_game("CIVILIZATION_MALI")
    sit.facts.terrain = {"TERRAIN_DESERT": 9, "TERRAIN_DESERT_HILLS": 2}
    sit.pantheon = lq.PantheonStatus(False, None, None, 30, [
        lq.BeliefInfo("BELIEF_DESERT_FOLKLORE", "沙漠民俗", ""),
        lq.BeliefInfo("BELIEF_DIVINE_SPARK", "神圣火花", ""),
        lq.BeliefInfo("BELIEF_GOD_OF_THE_OPEN_SKY", "开阔天空之神", "")])
    f = find(sit, "现在就能选万神殿")
    assert f and f.title.endswith("沙漠民俗") and "沙漠 11 格" in f.detail


def test_pantheon_waits_until_close():
    sit = start_game("CIVILIZATION_KOREA")
    sit.pantheon = lq.PantheonStatus(False, None, None, 5, [lq.BeliefInfo("BELIEF_DIVINE_SPARK", "神圣火花", "")])
    assert not find(sit, "现在就能选万神殿") and not find(sit, "万神殿快攒够")


def test_governor_victor_when_threatened_magnus_when_expanding():
    sit = mock_situation()  # 长安有蛮族
    assert find(sit, "总督：任命维克托")
    sit.threats = []
    sit.cities = [dataclasses.replace(c, loyalty_per_turn=0) for c in sit.cities]
    f = find(sit, "总督：任命")
    assert f and "马格努斯" in f.title


def test_governor_promotion_when_all_appointed():
    sit = mock_situation()
    sit.threats = []
    promo = [lq.GovernorPromotion("P1", "测量员", "x", 1), lq.GovernorPromotion("P2", "供给", "开拓者不掉人口", 1)]
    sit.governors = lq.GovernorStatus(1, 1, False, [
        lq.AppointedGovernor("GOVERNOR_THE_RESOURCE_MANAGER", "马格努斯", 65536, "西安", True, 0, promo)])
    f = find(sit, "总督：给马格努斯升")
    assert f and "供给" in f.title


def test_envoy_targets_named_city_state():
    f = find(mock_situation(), "使者：")
    assert f and "日内瓦" in f.title and "3 个" in f.detail


def test_buy_military_when_threatened_without_garrison():
    sit = mock_situation()
    chang = next(c for c in sit.cities if c.name == "长安")
    sit.production_options[chang.city_id] = [lq.ProductionOption("UNIT", "UNIT_SLINGER", 35, 4, 140),
                                             lq.ProductionOption("UNIT", "UNIT_SETTLER", 80, 8, 320)]
    f = find(sit, "金币：")
    assert f and f.title.startswith("金币：长安 直接买投石兵") and f.priority <= 1


def test_buy_respects_budget():
    sit = mock_situation()
    sit.overview = dataclasses.replace(sit.overview, gold=100)
    assert not find(sit, "金币：")


def test_boost_timing_hint():
    sit = mock_situation()
    t = sit.tech
    opt = lq.TechOption("灌溉", "TECH_IRRIGATION", 50, 30, 3, False, "给小麦/大米/玉米建农场", "")
    sit.tech = dataclasses.replace(t, current_research="灌溉", current_research_turns=3,
                                   available_techs=[opt] + list(t.available_techs))
    f = find(sit, "「灌溉」尤里卡还没触发")
    assert f and "小麦" in f.detail


def test_recommend_text_mentions_boost():
    from civ6_advisor.research import recommend_text, tracks

    tech, _ = tracks(start_game("CIVILIZATION_KOREA"))
    txt = recommend_text(tech)
    top = tech.picks[0]
    if top.boost_desc and not top.boosted:
        assert "尤里卡条件" in txt


def test_buy_one_item_per_city_and_idle_uses_next_pick():
    sit = mock_situation()
    f = find(sit, "金币：")
    assert f and f.detail.count("北京 买") == 1
    idle = next(x for x in analyze(sit) if x.tag == "production")
    assert idle.action.startswith("直接花 320 金买开拓者") and "锤子改造建造者" in idle.action


def test_neighbor_military_warning_uses_same_scale():
    sit = mock_situation()
    sit.facts.military = 100
    sit.diplomacy = [dataclasses.replace(c, diplomatic_state="DENOUNCED", military_strength=260, is_at_war=False,
                                         has_met=True) for c in sit.diplomacy[:1]]
    f = next((x for x in analyze(sit) if "军力是你的" in x.title), None)
    assert f and "2.6 倍" in f.title
    sit.facts.military = None  # 没有同口径数据就不比较
    assert not any("军力是你的" in x.title for x in analyze(sit))
