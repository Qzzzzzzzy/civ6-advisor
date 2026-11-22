"""FACTS_LUA 在 Lua 5.1 里真实执行（模拟游戏接口），确认能输出科技、资源和地形统计。"""

import pytest

from civ6_advisor.facts import FACTS_LUA, parse_facts

lupa = pytest.importorskip("lupa")
try:
    from lupa import lua51 as rt
except ImportError:  # pragma: no cover
    rt = lupa

STUBS = r"""
_out = {}
print = function(s) table.insert(_out, tostring(s)) end
local function tbl(rows, key)
  local t = {}
  for i, r in ipairs(rows) do r.Index = i - 1; t[r[key]] = r; t[i - 1] = r end
  setmetatable(t, {__call = function() local i = 0 return function() i = i + 1 return rows[i] end end})
  return t
end
GameInfo = {
  Technologies = tbl({{TechnologyType="TECH_POTTERY"}, {TechnologyType="TECH_MINING"}, {TechnologyType="TECH_ANIMAL_HUSBANDRY"}}, "TechnologyType"),
  Civics = tbl({{CivicType="CIVIC_CODE_OF_LAWS"}}, "CivicType"),
  Improvements = tbl({{ImprovementType="IMPROVEMENT_PASTURE", PrereqTech="TECH_ANIMAL_HUSBANDRY"},
                      {ImprovementType="IMPROVEMENT_QUARRY", PrereqTech="TECH_MINING"}}, "ImprovementType"),
  Resources = tbl({{ResourceType="RESOURCE_SHEEP", ResourceClassType="RESOURCECLASS_BONUS", Hash=1},
                   {ResourceType="RESOURCE_STONE", ResourceClassType="RESOURCECLASS_BONUS", Hash=2}}, "ResourceType"),
  Terrains = tbl({{TerrainType="TERRAIN_DESERT"}, {TerrainType="TERRAIN_GRASS"}}, "TerrainType"),
  Features = tbl({{FeatureType="FEATURE_FOREST"}}, "FeatureType"),
}
local ivr = {{ImprovementType="IMPROVEMENT_PASTURE", ResourceType="RESOURCE_SHEEP"},
             {ImprovementType="IMPROVEMENT_QUARRY", ResourceType="RESOURCE_STONE"}}
GameInfo.Improvement_ValidResources = function() local i = 0 return function() i = i + 1 return ivr[i] end end
Locale = {Lookup = function(s) return s end}
local researched = {[1] = true}  -- TECH_MINING
local function mkplot(x, y)
  local p = {x=x, y=y}
  function p:GetX() return self.x end
  function p:GetY() return self.y end
  function p:GetIndex() return self.y * 100 + self.x end
  function p:GetOwner() if math.abs(self.x - 10) <= 1 and math.abs(self.y - 10) <= 1 then return 0 end return -1 end
  function p:GetResourceType() if self.x == 11 and self.y == 10 then return 0 elseif self.x == 9 and self.y == 10 then return 1 end return -1 end
  function p:GetImprovementType() return -1 end
  function p:GetTerrainType() if self.x < 10 then return 0 end return 1 end
  function p:IsHills() return self.y == 11 end
  function p:GetFeatureType() if self.y == 9 then return 0 end return -1 end
  function p:IsRiver() return false end
  function p:GetAppeal() return 1 end
  return p
end
Map = {GetPlot = function(x, y) return mkplot(x, y) end,
       GetPlotDistance = function(a, b, c, d) return math.max(math.abs(a - c), math.abs(b - d)) end}
local city = {GetName=function() return "西安" end, GetX=function() return 10 end, GetY=function() return 10 end}
Game = {GetLocalPlayer = function() return 0 end}
Players = {[0] = {
  GetTechs = function() return {HasTech = function(_, i) return researched[i] == true end} end,
  GetCulture = function() return {HasCivic = function(_, i) return i == 0 end} end,
  GetResources = function() return {IsResourceVisible = function() return true end} end,
  GetCities = function() return {Members = function() return ipairs({city}) end} end,
  GetStats = function() return {GetMilitaryStrength = function() return 123.7 end} end,
}}
"""


def test_facts_lua_runs_with_terrain():
    lua = rt.LuaRuntime()
    lua.execute(STUBS)
    lua.execute(FACTS_LUA)
    lines = list(lua.eval("_out").values())
    f = parse_facts(lines)
    assert "TECH_MINING" in f.techs and "CIVIC_CODE_OF_LAWS" in f.civics
    stone = next(r for r in f.resources if r.resource == "RESOURCE_STONE")
    sheep = next(r for r in f.resources if r.resource == "RESOURCE_SHEEP")
    assert stone.can_now and not sheep.can_now and sheep.prereq == "TECH_ANIMAL_HUSBANDRY"
    assert f.terrain["TERRAIN_DESERT"] > 0 and f.terrain["FEATURE_FOREST"] > 0 and f.terrain["HILLS"] > 0
    assert f.count("RES_IMPROVEMENT_PASTURE", "RES_IMPROVEMENT_QUARRY") == 2
    assert f.military == 123
    assert lines[-1].endswith("END---")
