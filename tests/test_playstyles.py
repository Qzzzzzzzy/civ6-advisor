"""流派：数据完整、开启后推荐跟着流派走、取消后恢复。"""

import dataclasses

from test_research import start_game

from civ_mcp import lua as lq
from civ6_advisor.civs import CIVS
from civ6_advisor.mock import mock_situation
from civ6_advisor.playstyles import PLAYSTYLES, brief_section, check, playstyle_for, progress
from civ6_advisor.production import city_overview
from civ6_advisor.report import full_brief
from civ6_advisor.research import TAGS, tracks
from civ6_advisor.rules import analyze

KINDS = {"tech", "civic", "cities", "district", "religion", "governor", "building", "units", "government"}


def test_every_civ_has_one_playstyle():
    assert set(PLAYSTYLES) == set(CIVS)
    for ps in PLAYSTYLES.values():
        assert ps.steps and ps.core and ps.name and ps.pitch
        for s in ps.steps:
            assert s.cond[0] in KINDS, (ps.id, s.cond)
            if s.cond[0] in ("tech", "civic"):
                assert s.cond[1] in TAGS, (ps.id, s.cond)
        for k in (*ps.tech, *ps.civic):
            assert k in TAGS, (ps.id, k)


def _on(sit):
    sit.playstyle = playstyle_for(sit.civ.civ_type).id
    return sit


def test_off_by_default_no_style_findings():
    sit = mock_situation()
    assert not any(f.category == "流派" for f in analyze(sit))
    assert "玩家选择的流派" not in full_brief(sit, analyze(sit))


def test_chop_style_pushes_crafts_and_magnus():
    sit = start_game("CIVILIZATION_AUSTRALIA")
    base_civic = [p.type for p in tracks(sit)[1].picks]
    sit = _on(sit)
    civic = tracks(sit)[1].picks
    ranks = [p.type for p in civic]
    assert ranks.index("CIVIC_CRAFTSMANSHIP") < base_civic.index("CIVIC_CRAFTSMANSHIP")
    craft = next(p for p in civic if p.type == "CIVIC_CRAFTSMANSHIP")
    assert any("流派" in r or "砍树" in r for r in craft.reasons)
    fs = [f for f in analyze(sit) if f.category == "流派"]
    assert fs and fs[0].title.startswith("流派下一步")


def test_late_step_raises_priority():
    sit = _on(start_game("CIVILIZATION_SUMERIA"))
    sit.overview = dataclasses.replace(sit.overview, turn=60)
    f = next(f for f in analyze(sit) if f.category == "流派")
    assert "已落后" in f.title and f.priority <= 1


def test_religion_style_broken_when_slots_gone():
    sit = _on(start_game("CIVILIZATION_RUSSIA"))
    sit.overview = dataclasses.replace(sit.overview, religions_founded=4, religions_max=4, our_religion=None)
    assert progress(playstyle_for("CIVILIZATION_RUSSIA"), sit).broken
    assert any("前提失效" in f.title for f in analyze(sit))


def test_production_follows_style():
    sit = _on(mock_situation())  # 中国，北京空闲
    sit.threats = []  # 有敌军时流派加分会让位给防御
    rows = [r for r in city_overview(sit) if r.idle]
    name = playstyle_for("CIVILIZATION_CHINA").name
    assert rows and any(name in why for p in rows[0].picks for why in p.reasons)


def test_brief_has_style_section():
    sit = _on(mock_situation())
    text = full_brief(sit, analyze(sit))
    assert "玩家选择的流派" in text and "里程碑" in text
    assert brief_section(sit).count("进度") == 1


def test_checks():
    sit = mock_situation()
    assert check(("cities", 1), sit)
    assert check(("tech", "TECH_WRITING"), sit)
    assert not check(("tech", "TECH_ROCKETRY"), sit)
    sit.governors = lq.GovernorStatus(0, 1, False, [lq.AppointedGovernor("GOVERNOR_THE_RESOURCE_MANAGER", "Magnus", -1, "", False)])
    assert check(("governor", "GOVERNOR_THE_RESOURCE_MANAGER"), sit)


def test_threat_beats_style():
    sit = _on(mock_situation())
    rows = [r for r in city_overview(sit) if r.idle]
    if rows and any("敌军" in w for p in rows[0].picks for w in p.reasons):
        assert not any("流派" in w for w in rows[0].picks[0].reasons)
