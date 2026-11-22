"""城市生产：首都识别、空闲判断、推荐和缺口检查。"""

import dataclasses

from civ_mcp import lua as lq

from civ6_advisor.mock import mock_situation
from civ6_advisor.names import is_idle, production_cn
from civ6_advisor.production import city_overview, suggest_for_city
from civ6_advisor.rules import analyze


def test_names_and_idle():
    assert is_idle("nothing") and is_idle("NONE") and is_idle("") and not is_idle("UNIT_SETTLER")
    assert production_cn("UNIT_SETTLER") == "开拓者"
    assert production_cn("DISTRICT_CAMPUS") == "学院区"
    assert production_cn("BUILDING_MONUMENT") == "纪念碑"
    assert production_cn("UNKNOWN") == "城市项目"


def test_overview_capital_first_and_idle_has_picks():
    rows = city_overview(mock_situation())
    assert rows[0].is_capital and rows[0].city.name == "西安" and rows[0].building == "学院区"
    beijing = next(r for r in rows if r.city.name == "北京")
    assert beijing.idle and beijing.picks
    assert all(not r.picks for r in rows if not r.idle)


def test_idle_finding_detected_with_nothing():
    f = analyze(mock_situation())
    idle = next(x for x in f if x.tag == "production")
    assert "北京 没有在生产" in idle.title and idle.action.startswith(("推荐 ", "直接花")) and "建造者" in idle.action


def test_only_recommends_buildable_items():
    sit = mock_situation()
    sit.production_options[131073] = [lq.ProductionOption("UNIT", "UNIT_WARRIOR", 40, 4)]
    beijing = next(c for c in sit.cities if c.name == "北京")
    assert {p.item for p in suggest_for_city(sit, beijing)} <= {"UNIT_WARRIOR"}


def test_settler_not_pushed_when_already_queued():
    sit = mock_situation()
    sit.units = [u for u in sit.units if u.unit_type != "UNIT_SETTLER"]
    sit.cities[0] = dataclasses.replace(sit.cities[0], currently_building="UNIT_SETTLER")
    beijing = next(c for c in sit.cities if c.name == "北京")
    items = [p.item for p in suggest_for_city(sit, beijing)]
    # 4 座目标：现有 3 + 西安在造 1 = 4 < 5 仍可再出；改成 4 座城后就不该再推
    sit.cities.append(dataclasses.replace(sit.cities[2], city_id=9, name="洛阳", currently_building="UNIT_WARRIOR"))
    items2 = [p.item for p in suggest_for_city(sit, beijing)]
    assert "UNIT_SETTLER" in items and "UNIT_SETTLER" not in items2
    assert not [x for x in analyze(sit) if "扩张偏慢" in x.title]


def test_builder_queued_softens_warning():
    sit = mock_situation()
    sit.cities[2] = dataclasses.replace(sit.cities[2], currently_building="UNIT_BUILDER")
    f = analyze(sit)
    assert any("正在造建造者" in x.title for x in f)
    assert not any("但没有建造者" in x.title for x in f)
    beijing = next(c for c in sit.cities if c.name == "北京")
    assert "UNIT_BUILDER" not in [p.item for p in suggest_for_city(sit, beijing)]


def test_threat_pushes_military_and_walls():
    sit = mock_situation()
    beijing = next(c for c in sit.cities if c.name == "北京")
    sit.threats.append(lq.ThreatInfo("UNIT_BARBARIAN_SPEARMAN", beijing.x + 1, beijing.y, 100, 100, 25, 0, 1))
    picks = suggest_for_city(sit, beijing)
    assert picks[0].item == "UNIT_ARCHER" and "附近有敌军" in picks[0].reasons


def test_religious_civ_wants_holy_site():
    sit = mock_situation()
    sit.civ = dataclasses.replace(sit.civ, civ_type="CIVILIZATION_RUSSIA", leader_type="")
    beijing = next(c for c in sit.cities if c.name == "北京")
    items = [p.item for p in suggest_for_city(sit, beijing)][:3]
    assert "DISTRICT_HOLY_SITE" in items
