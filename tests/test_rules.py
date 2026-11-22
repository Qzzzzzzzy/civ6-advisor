"""规则引擎测试（用演示数据，不需要游戏）。"""

import dataclasses

import pytest

from civ6_advisor.game import READ_ONLY_METHODS, ReadOnlyGame
from civ6_advisor.mock import mock_situation
from civ6_advisor.report import full_brief, top_moves
from civ6_advisor.rules import Priority, analyze
from civ6_advisor.rules.base import hex_distance


def titles(findings):
    return [f.title for f in findings]


def test_hex_distance():
    assert hex_distance(0, 0, 0, 0) == 0
    assert hex_distance(5, 5, 6, 5) == 1
    assert hex_distance(5, 5, 5, 6) == 1  # 奇数行右移，正下方相邻
    assert hex_distance(5, 5, 8, 5) == 3
    assert hex_distance(10, 10, 10, 14) == 4


def test_mock_findings_cover_known_problems():
    f = analyze(mock_situation())
    t = " ".join(titles(f))
    assert "长安 附近有敌军" in t
    assert "北京 没有在生产任何东西" in t
    assert "没有在推进市政" in t
    assert "政策：2 个空槽这样插" in t
    assert "忠诚度在下降" in t
    assert "开拓者待落城" in t


def test_sorted_by_priority():
    f = analyze(mock_situation())
    assert [x.priority for x in f] == sorted(x.priority for x in f)
    assert f[0].priority == Priority.URGENT


def test_no_duplicate_civic_notification():
    f = analyze(mock_situation())
    assert not any(x.category == "通知" and "市政" in x.title for x in f)


def test_barbarians_named_in_chinese():
    f = analyze(mock_situation())
    threat = next(x for x in f if "附近有敌军" in x.title)
    assert "蛮族" in threat.detail and "Barbarian" not in threat.detail


def test_healthy_city_has_no_city_findings():
    sit = mock_situation()
    xian = dataclasses.replace(sit.cities[0], amenities=2, housing=12)
    sit.cities = [xian]
    sit.threats = []
    f = analyze(sit)
    assert not [x for x in f if x.city_id == xian.city_id]


def test_negative_gold_is_urgent_when_running_out():
    sit = mock_situation()
    sit.overview = dataclasses.replace(sit.overview, gold=30, gold_per_turn=-8)
    f = analyze(sit)
    gold = next(x for x in f if x.title == "金币入不敷出")
    assert gold.priority == Priority.URGENT


def test_war_against_stronger_enemy():
    sit = mock_situation()
    sit.diplomacy[0] = dataclasses.replace(sit.diplomacy[0], is_at_war=True)
    f = analyze(sit)
    assert any("对方军力明显占优" in x.title for x in f)


def test_broken_rule_does_not_crash():
    sit = mock_situation()
    sit.government = "坏数据"  # type: ignore[assignment]
    analyze(sit)  # 不抛异常即可


def test_reports_render():
    sit = mock_situation()
    f = analyze(sit)
    assert "第 68 回合" in full_brief(sit, f)
    tm = top_moves(sit, f)
    assert tm.count("\n1. ") + tm.count("\n2. ") >= 2


def test_read_only_facade_blocks_writes():
    g = ReadOnlyGame()
    for name in ("end_turn", "move_unit", "set_research", "set_city_production", "propose_trade"):
        assert name not in READ_ONLY_METHODS
        with pytest.raises(AttributeError):
            getattr(g, name)
    assert callable(g.get_game_overview)


def _policy_titles(sit):
    return [f.title for f in analyze(sit) if "政策槽" in f.title]


def test_empty_slots_without_cards_not_reported():
    """开局（法典之前）有空槽但手上没有政策卡：不该提醒。"""
    import dataclasses

    sit = mock_situation()
    sit.government = dataclasses.replace(sit.government, available_policies=[])
    assert not _policy_titles(sit)


def test_empty_slots_all_cards_in_use_not_reported():
    import dataclasses

    from civ_mcp import lua as lq

    sit = mock_situation()
    used = [lq.PolicyInfo("POLICY_URBAN_PLANNING", "城市规划", "", "SLOT_ECONOMIC")]
    sit.government = dataclasses.replace(sit.government, available_policies=used)
    assert not _policy_titles(sit)


def test_empty_slots_with_cards_reported():
    sit = mock_situation()
    t = _policy_titles(sit)
    assert t == []  # 标题改成「政策：…」了，这里只确认旧标题不再出现
    titles = [f.title for f in analyze(sit)]
    assert "政策：2 个空槽这样插" in titles
