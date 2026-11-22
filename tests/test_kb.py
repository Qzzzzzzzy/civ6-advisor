"""资料库测试：导出 Lua 在 Lua 5.1 里跑通（模拟 GameInfo），解析、关联、检索、按局势挑资料。"""

import pytest

from civ6_advisor import gamedb
from civ6_advisor.kb import KnowledgeBase
from civ6_advisor.mock import mock_situation

lupa = pytest.importorskip("lupa")
try:
    from lupa import lua51 as rt
except ImportError:  # pragma: no cover
    rt = lupa

# 模拟游戏数据库：GameInfo.X() 返回迭代器，GameInfo.X[key] 按主键取
FAKE_DB = r"""
_out = {}
function print(s) table.insert(_out, s) end
Locale = {Lookup = function(s)
  local t = {LOC_UNIT_WARRIOR = "勇士", LOC_UNIT_ETH = "奥罗莫骑兵", LOC_UNIT_ETH_DESC = "埃塞俄比亚特色中世纪轻骑兵。|视野+1",
             LOC_UNIT_COURSER = "轻骑兵", LOC_TECH_POTTERY = "制陶术", LOC_BOOST_POTTERY = "没有",
             LOC_CIVIC_COL = "法典", LOC_BOOST_COL = "建立首都", LOC_D_CAMPUS = "学院区", LOC_ADJ_MTN = "+1 科技值（每个相邻山脉）",
             LOC_POLICY_AGOGE = "阿哥革", LOC_POLICY_AGOGE_DESC = "远古和古典时代近战远程单位生产+50%",
             LOC_CIV_ETH = "埃塞俄比亚", LOC_LEADER_MEN = "孟尼利克二世", LOC_TR = "内阁会议",
             LOC_TR_DESC = "获得等同于建在丘陵上的城市所产生信仰值15%的科技值和文化值。",
             LOC_GOV_CHIEF = "酋邦", LOC_GOV_CHIEF_DESC = "无", LOC_RES_HORSES = "马", LOC_IMP_PASTURE = "牧场"}
  return t[s] or s
end}
local function tbl(rows, key)
  local t = {}
  setmetatable(t, {__call = function() local i = 0 return function() i = i + 1 return rows[i] end end,
                   __index = function(_, k) for _, r in ipairs(rows) do if r[key] == k then return r end end end})
  return t
end
GameInfo = {
  Civilizations = tbl({{CivilizationType = "CIVILIZATION_ETHIOPIA", Name = "LOC_CIV_ETH", StartingCivilizationLevelType = "CIVILIZATION_LEVEL_FULL_CIV"},
                       {CivilizationType = "CIVILIZATION_CS", Name = "LOC_CS", StartingCivilizationLevelType = "CIVILIZATION_LEVEL_CITY_STATE"}}),
  Leaders = tbl({{LeaderType = "LEADER_MENELIK", Name = "LOC_LEADER_MEN", InheritFrom = "LEADER_DEFAULT"}}),
  CivilizationLeaders = tbl({{CivilizationType = "CIVILIZATION_ETHIOPIA", LeaderType = "LEADER_MENELIK"}}),
  CivilizationTraits = tbl({}),
  LeaderTraits = tbl({{LeaderType = "LEADER_MENELIK", TraitType = "TRAIT_MEN"}}),
  Traits = tbl({{TraitType = "TRAIT_MEN", Name = "LOC_TR", Description = "LOC_TR_DESC"}}, "TraitType"),
  Units = tbl({{UnitType = "UNIT_WARRIOR", Name = "LOC_UNIT_WARRIOR", Cost = 40, Combat = 20, BaseMoves = 2},
               {UnitType = "UNIT_ETH", Name = "LOC_UNIT_ETH", Description = "LOC_UNIT_ETH_DESC", Cost = 200, Combat = 48,
                BaseMoves = 5, TraitType = "TRAIT_X", PrereqTech = "TECH_POTTERY"},
               {UnitType = "UNIT_COURSER", Name = "LOC_UNIT_COURSER", Cost = 200, Combat = 44, BaseMoves = 5},
               {UnitType = "UNIT_BARBARIAN_HORSE_ARCHER", Name = "x", Cost = 1}}),
  UnitReplaces = tbl({{CivUniqueUnitType = "UNIT_ETH", ReplacesUnitType = "UNIT_COURSER"}}),
  Buildings = tbl({}), BuildingReplaces = tbl({}), Building_YieldChanges = tbl({}),
  Districts = tbl({{DistrictType = "DISTRICT_CAMPUS", Name = "LOC_D_CAMPUS", Cost = 54, PrereqTech = "TECH_WRITING"}}),
  DistrictReplaces = tbl({}),
  District_Adjacencies = tbl({{DistrictType = "DISTRICT_CAMPUS", YieldChangeId = "Mountains_Science1"}}),
  Adjacency_YieldChanges = tbl({{ID = "Mountains_Science1", Description = "LOC_ADJ_MTN"}}, "ID"),
  Improvements = tbl({{ImprovementType = "IMPROVEMENT_PASTURE", Name = "LOC_IMP_PASTURE", PrereqTech = "TECH_POTTERY"}}),
  Improvement_ValidResources = tbl({{ImprovementType = "IMPROVEMENT_PASTURE", ResourceType = "RESOURCE_HORSES"}}),
  Resources = tbl({{ResourceType = "RESOURCE_HORSES", Name = "LOC_RES_HORSES", ResourceClassType = "RESOURCECLASS_STRATEGIC"}}),
  Boosts = tbl({{TechnologyType = "TECH_POTTERY", TriggerDescription = "LOC_BOOST_POTTERY"},
                {CivicType = "CIVIC_CODE_OF_LAWS", TriggerDescription = "LOC_BOOST_COL"}}),
  Technologies = tbl({{TechnologyType = "TECH_POTTERY", Name = "LOC_TECH_POTTERY", Cost = 25, EraType = "ERA_ANCIENT"}}),
  Civics = tbl({{CivicType = "CIVIC_CODE_OF_LAWS", Name = "LOC_CIVIC_COL", Cost = 20}}),
  TechnologyPrereqs = tbl({}), CivicPrereqs = tbl({}),
  Policies = tbl({{PolicyType = "POLICY_AGOGE", Name = "LOC_POLICY_AGOGE", Description = "LOC_POLICY_AGOGE_DESC",
                   GovernmentSlotType = "SLOT_MILITARY", PrereqCivic = "CIVIC_CODE_OF_LAWS"}}),
  ObsoletePolicies = tbl({}),
  Governments = tbl({{GovernmentType = "GOVERNMENT_CHIEFDOM", Name = "LOC_GOV_CHIEF", InherentBonusDesc = "LOC_GOV_CHIEF_DESC"}}),
  Government_SlotCounts = tbl({{GovernmentType = "GOVERNMENT_CHIEFDOM", GovernmentSlotType = "SLOT_MILITARY", NumSlots = 1}}),
  Beliefs = tbl({}), Governors = tbl({}), GovernorPromotions = tbl({}), GovernorPromotionSets = tbl({}),
  -- Projects 表不存在（模拟旧版本），导出代码要能跳过
}
"""


def fake_game_data() -> dict:
    lua = rt.LuaRuntime()
    lua.execute(FAKE_DB)
    data = {"entries": [], "rels": []}
    for name in gamedb._TABLES:
        lua.execute("_out = {}")
        lua.execute(gamedb.build_table_lua(name))
        lines = list(lua.eval("_out").values())
        assert lines[-1] == "---END---" or "END" in lines[-1]
        gamedb.parse_lines(lines, data)
    return data


def test_dump_lua_runs_and_parses():
    data = fake_game_data()
    kinds = {(e["kind"], e["type"]) for e in data["entries"]}
    assert ("UNIT", "UNIT_ETH") in kinds and ("CIV", "CIVILIZATION_ETHIOPIA") in kinds
    assert ("CIV", "CIVILIZATION_CS") not in kinds  # 城邦不导出
    assert not any("BARBARIAN" in t for _, t in kinds)
    eth = next(e for e in data["entries"] if e["type"] == "UNIT_ETH")
    assert eth["name"] == "奥罗莫骑兵" and "|" not in eth["desc"]  # 描述里的 | 被替换
    assert eth["attrs"]["combat"] == "48" and eth["attrs"]["moves"] == "5"
    pot = next(e for e in data["entries"] if e["type"] == "TECH_POTTERY")
    assert pot["attrs"]["boost"] == "没有"
    assert ["REPLACES", "UNIT_ETH", "UNIT_COURSER"] in data["rels"]
    assert ["ADJ", "DISTRICT_CAMPUS", "+1 科技值（每个相邻山脉）"] in data["rels"]


def test_kb_links_and_render():
    kb = KnowledgeBase(fake_game_data())
    eth = kb.get("奥罗莫骑兵")
    text = kb.render(eth)
    assert "替代：轻骑兵" in text and "近战：48" in text and "需要科技：制陶术" in text
    assert "特色替代版：奥罗莫骑兵" in kb.render(kb.get("UNIT_COURSER"))
    assert "相邻加成：+1 科技值" in kb.render(kb.get("学院区"))
    assert "解锁：" in kb.render(kb.get("制陶术")) and "奥罗莫骑兵" in kb.render(kb.get("制陶术"))
    assert "用「牧场」改良" in kb.render(kb.get("马"))
    assert "政策槽：军事×1" in kb.render(kb.get("酋邦"))
    men = kb.render(kb.get("LEADER_MENELIK"))
    assert "内阁会议" in men and "文明：埃塞俄比亚" in men


def test_search_fuzzy_and_guides():
    kb = KnowledgeBase(fake_game_data())
    assert kb.search("奥罗莫")[0].name == "奥罗莫骑兵"
    assert kb.search("骑兵怎么用")[0].kind in ("UNIT", "GUIDE")
    g = kb.search("开拓者 城址", kinds={"GUIDE"})
    assert g and "扩张" in g[0].name
    assert kb.get("埃塞俄比亚攻略").kind == "CIVGUIDE"


def test_guides_work_without_game_data():
    kb = KnowledgeBase(None)
    assert not kb.has_game_data
    assert len([e for e in kb.entries if e.kind == "GUIDE"]) >= 15
    assert kb.get("中国攻略") is not None


def test_context_for_situation():
    kb = KnowledgeBase(fake_game_data())
    ctx = kb.context_for(mock_situation())
    assert ctx.startswith("## 资料库")
    assert "【文明攻略】中国" in ctx
    assert "【攻略】" in ctx
    assert len(ctx) <= 7200


def test_cache_roundtrip(tmp_path):
    data = fake_game_data()
    p = tmp_path / "kb.json"
    gamedb.save(data, p)
    assert gamedb.load(p)["entries"] == data["entries"]
    assert gamedb.load(tmp_path / "missing.json") is None


def test_dump_paginated_matches_full():
    """分页导出（每页 2 行）结果和一次导出完全一致。"""
    import asyncio

    lua = rt.LuaRuntime()
    lua.execute(FAKE_DB)

    class FakeConn:
        async def execute_read(self, code, timeout=30.0):
            lua.execute("_out = {}")
            lua.execute(code)
            return list(lua.eval("_out").values())

    old = gamedb.PAGE_ROWS
    gamedb.PAGE_ROWS = 2
    try:
        paged = asyncio.run(gamedb.dump(FakeConn()))
    finally:
        gamedb.PAGE_ROWS = old
    full = fake_game_data()
    def key(d):
        return sorted(map(str, d["entries"])), sorted(map(str, d["rels"]))

    assert key(paged) == key(full) and paged["entries"]
