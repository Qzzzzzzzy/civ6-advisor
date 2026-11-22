"""空闲城市推荐建区域时，查最佳地块并写进建议、标在地图上。"""

import asyncio
import dataclasses

from civ_mcp import lua as lq

from civ6_advisor import game
from civ6_advisor.mock import mock_situation
from civ6_advisor.rules import analyze


def _campus_city(sit):
    """让北京只能造学院区，这样推荐第一名就是区域。"""
    bj = next(c for c in sit.cities if c.name == "北京")
    sit.production_options[bj.city_id] = [lq.ProductionOption("DISTRICT", "DISTRICT_CAMPUS", 54, 5)]
    return bj


def test_collect_district_spots_with_fake_game():
    sit = mock_situation()
    bj = _campus_city(sit)
    calls = []

    class FakeGame:
        async def get_district_advisor(self, city_id, d):
            calls.append((city_id, d))
            return [lq.DistrictPlacement(26, 11, {"science": 1}, 1, "平原"),
                    lq.DistrictPlacement(27, 12, {"science": 3}, 3, "平原丘陵")]

    asyncio.run(game._district_spots(FakeGame(), sit))
    assert calls == [(bj.city_id, "DISTRICT_CAMPUS")]
    d, spots = sit.district_spots[bj.city_id]
    assert d == "DISTRICT_CAMPUS" and spots[0].total_adjacency == 3  # 按相邻加成排序


def test_idle_finding_names_best_tile():
    sit = mock_situation()
    bj = _campus_city(sit)
    sit.district_spots = {bj.city_id: ("DISTRICT_CAMPUS", [
        lq.DistrictPlacement(27, 12, {"science": 3}, 3, "平原丘陵"),
        lq.DistrictPlacement(26, 11, {"science": 1}, 1, "平原")])}
    f = next(x for x in analyze(sit) if x.tag == "production")
    assert "最佳位置" in f.action and "科研 +3" in f.action and "次选相邻 +1" in f.action
    assert any(p.kind == "district" and (p.x, p.y) == (27, 12) for p in f.plots)


def test_advisor_error_is_recorded_not_raised():
    sit = mock_situation()
    _campus_city(sit)

    class Bad:
        async def get_district_advisor(self, *a):
            raise RuntimeError("no")

    asyncio.run(game._district_spots(Bad(), sit))
    assert any("district_advisor" in e for e in sit.errors) and not sit.district_spots
