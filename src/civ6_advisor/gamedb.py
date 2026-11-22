"""从游戏数据库导出资料（只读）：名字和描述用游戏当前语言，DLC / 模组内容都包含在内。

导出结果缓存在本机（~/.civ6-advisor/game_kb.json）。本局的文明在缓存里找不到（换了模组）
或者用户手动「重建资料库」时会重新导出。

输出格式：每行一个条目
  KB|种类|类型名|名字|描述|键=值;键=值
  REL|关系|A|B
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from civ_mcp.lua._helpers import SENTINEL

CACHE_DIR = Path.home() / ".civ6-advisor"
CACHE_FILE = CACHE_DIR / "game_kb.json"

_PRELUDE = r"""
local function clean(s)
  if s == nil then return "" end
  local ok, t = pcall(Locale.Lookup, s)
  if not ok or t == nil then t = tostring(s) end
  t = string.gsub(t, "[\r\n]", " ")
  t = string.gsub(t, "|", "/")
  return t
end
local function v(x) if x == nil then return "" end return string.gsub(tostring(x), "[|;=\r\n]", " ") end
local function kv(t)
  local parts = {}
  for _, p in ipairs(t) do
    if p[2] ~= nil and p[2] ~= "" and p[2] ~= false and p[2] ~= 0 then
      table.insert(parts, p[1] .. "=" .. v(p[2]))
    end
  end
  return table.concat(parts, ";")
end
local function emit(kind, typ, name, desc, extra)
  print("KB|" .. kind .. "|" .. v(typ) .. "|" .. clean(name) .. "|" .. clean(desc) .. "|" .. (extra or ""))
end
local function rel(kind, a, b) print("REL|" .. kind .. "|" .. v(a) .. "|" .. v(b)) end
local function all(tbl, fn)  -- 建查找表用：每页都完整遍历，不输出、不计入分页
  if tbl == nil then return end
  pcall(function() for r in tbl() do pcall(fn, r) end end)
end
local function each(tbl, fn)
  if tbl == nil then return end
  if __depth > 0 then  -- 回调里嵌套遍历的表不计入分页
    pcall(function() for r in tbl() do pcall(fn, r) end end)
    return
  end
  __depth = 1
  pcall(function() for r in tbl() do
    __n = __n + 1
    if __n > __lo and __n <= __hi then pcall(fn, r) end
  end end)
  __depth = 0
end
"""

# 每张表一段代码，分开执行，避免单次输出过大
_TABLES: dict[str, str] = {
    "civs": r"""
each(GameInfo.Civilizations, function(r)
  if r.StartingCivilizationLevelType == "CIVILIZATION_LEVEL_FULL_CIV" or r.StartingCivilizationLevelType == nil then
    emit("CIV", r.CivilizationType, r.Name, r.Description, "")
  end
end)
each(GameInfo.Leaders, function(r)
  if r.InheritFrom == "LEADER_DEFAULT" then emit("LEADER", r.LeaderType, r.Name, "", "") end
end)
each(GameInfo.CivilizationLeaders, function(r) rel("CIV_LEADER", r.CivilizationType, r.LeaderType) end)
each(GameInfo.CivilizationTraits, function(r) rel("CIV_TRAIT", r.CivilizationType, r.TraitType) end)
each(GameInfo.LeaderTraits, function(r) rel("LEADER_TRAIT", r.LeaderType, r.TraitType) end)
each(GameInfo.Traits, function(r)
  if r.Name and not r.InternalOnly then emit("TRAIT", r.TraitType, r.Name, r.Description, "") end
end)
""",
    "units": r"""
each(GameInfo.Units, function(r)
  if string.find(r.UnitType, "BARBARIAN") == nil then
    emit("UNIT", r.UnitType, r.Name, r.Description, kv({{"cost", r.Cost}, {"combat", r.Combat},
      {"ranged", r.RangedCombat}, {"range", r.Range}, {"bombard", r.Bombard}, {"moves", r.BaseMoves},
      {"tech", r.PrereqTech}, {"civic", r.PrereqCivic}, {"trait", r.TraitType}, {"resource", r.StrategicResource},
      {"domain", r.Domain}, {"class", r.PromotionClass}, {"maint", r.Maintenance}, {"faith", r.PurchaseYield == "YIELD_FAITH" and 1 or 0}}))
  end
end)
each(GameInfo.UnitReplaces, function(r) rel("REPLACES", r.CivUniqueUnitType, r.ReplacesUnitType) end)
""",
    "buildings": r"""
each(GameInfo.Buildings, function(r)
  emit(r.IsWonder and "WONDER" or "BUILDING", r.BuildingType, r.Name, r.Description, kv({{"cost", r.Cost},
    {"tech", r.PrereqTech}, {"civic", r.PrereqCivic}, {"district", r.PrereqDistrict}, {"trait", r.TraitType},
    {"maint", r.Maintenance}, {"housing", r.Housing}, {"amenity", r.Entertainment}, {"era", r.ObsoleteEra}}))
end)
each(GameInfo.BuildingReplaces, function(r) rel("REPLACES", r.CivUniqueBuildingType, r.ReplacesBuildingType) end)
each(GameInfo.Building_YieldChanges, function(r) rel("YIELD", r.BuildingType, r.YieldType .. "+" .. r.YieldChange) end)
""",
    "districts": r"""
each(GameInfo.Districts, function(r)
  emit("DISTRICT", r.DistrictType, r.Name, r.Description, kv({{"cost", r.Cost}, {"tech", r.PrereqTech},
    {"civic", r.PrereqCivic}, {"trait", r.TraitType}, {"housing", r.Housing}, {"amenity", r.Entertainment},
    {"specialty", r.RequiresPopulation}}))
end)
each(GameInfo.DistrictReplaces, function(r) rel("REPLACES", r.CivUniqueDistrictType, r.ReplacesDistrictType) end)
each(GameInfo.District_Adjacencies, function(r)
  local a = GameInfo.Adjacency_YieldChanges and GameInfo.Adjacency_YieldChanges[r.YieldChangeId]
  if a then rel("ADJ", r.DistrictType, clean(a.Description)) end
end)
""",
    "improvements": r"""
each(GameInfo.Improvements, function(r)
  emit("IMPROVEMENT", r.ImprovementType, r.Name, r.Description, kv({{"tech", r.PrereqTech},
    {"civic", r.PrereqCivic}, {"trait", r.TraitType}, {"housing", r.Housing}}))
end)
each(GameInfo.Improvement_ValidResources, function(r) rel("IMPROVES", r.ImprovementType, r.ResourceType) end)
each(GameInfo.Resources, function(r)
  emit("RESOURCE", r.ResourceType, r.Name, "", kv({{"class", r.ResourceClassType}, {"tech", r.PrereqTech}}))
end)
""",
    "techs": r"""
local boosts = {}
all(GameInfo.Boosts, function(r)
  if r.TechnologyType then boosts[r.TechnologyType] = r.TriggerDescription end
  if r.CivicType then boosts[r.CivicType] = r.TriggerDescription end
end)
each(GameInfo.Technologies, function(r)
  emit("TECH", r.TechnologyType, r.Name, r.Description, kv({{"cost", r.Cost}, {"era", r.EraType},
    {"boost", boosts[r.TechnologyType] and clean(boosts[r.TechnologyType]) or nil}}))
end)
each(GameInfo.Civics, function(r)
  emit("CIVIC", r.CivicType, r.Name, r.Description, kv({{"cost", r.Cost}, {"era", r.EraType},
    {"boost", boosts[r.CivicType] and clean(boosts[r.CivicType]) or nil}}))
end)
each(GameInfo.TechnologyPrereqs, function(r) rel("PREREQ", r.Technology, r.PrereqTech) end)
each(GameInfo.CivicPrereqs, function(r) rel("PREREQ", r.Civic, r.PrereqCivic) end)
""",
    "government": r"""
each(GameInfo.Policies, function(r)
  emit("POLICY", r.PolicyType, r.Name, r.Description, kv({{"slot", r.GovernmentSlotType}, {"civic", r.PrereqCivic}}))
end)
each(GameInfo.Policies_XP1 or nil, function(r) if r.MinimumGameEra then rel("POLICY_ERA", r.PolicyType, r.MinimumGameEra) end end)
each(GameInfo.ObsoletePolicies, function(r) rel("OBSOLETE", r.PolicyType, r.ObsoletePolicy) end)
each(GameInfo.Governments, function(r)
  emit("GOVERNMENT", r.GovernmentType, r.Name, r.InherentBonusDesc, kv({{"civic", r.PrereqCivic},
    {"bonus", r.AccumulatedBonusShortDesc and clean(r.AccumulatedBonusShortDesc) or nil}}))
end)
each(GameInfo.Government_SlotCounts, function(r) rel("SLOTS", r.GovernmentType, r.GovernmentSlotType .. "x" .. r.NumSlots) end)
""",
    "religion": r"""
each(GameInfo.Beliefs, function(r)
  emit("BELIEF", r.BeliefType, r.Name, r.Description, kv({{"class", r.BeliefClassType}}))
end)
each(GameInfo.Governors, function(r)
  if r.Name then emit("GOVERNOR", r.GovernorType, r.Name, r.Description, kv({{"title", r.Title and clean(r.Title) or nil}})) end
end)
each(GameInfo.GovernorPromotions, function(r)
  emit("GOV_PROMO", r.GovernorPromotionType, r.Name, r.Description, kv({{"level", r.Level}}))
end)
each(GameInfo.GovernorPromotionSets, function(r) rel("GOV_HAS", r.GovernorType, r.GovernorPromotion) end)
each(GameInfo.Projects, function(r)
  emit("PROJECT", r.ProjectType, r.Name, r.Description, kv({{"cost", r.Cost}, {"district", r.PrereqDistrict}}))
end)
""",
}


PAGE_ROWS = 120  # 每次只导出这么多行，分多次读，避免一次输出太大


def build_table_lua(name: str, lo: int = 0, hi: int = 10**9) -> str:
    """lo/hi：只输出第 lo+1..hi 行（按这段代码遍历到的行累计计数），最后打印总行数。"""
    head = f"local __n, __lo, __hi, __depth = 0, {int(lo)}, {int(hi)}, 0\n"
    return head + _PRELUDE + _TABLES[name] + f'\nprint("KBN|" .. __n)\nprint("{SENTINEL}")\n'


def parse_lines(lines: list[str], out: dict) -> None:
    for line in lines:
        parts = line.split("|")
        if parts[0] == "KB" and len(parts) >= 6:
            _, kind, typ, name, desc, extra = parts[:6]
            attrs = {}
            for kvs in extra.split(";"):
                if "=" in kvs:
                    k, val = kvs.split("=", 1)
                    attrs[k] = val
            out["entries"].append({"kind": kind, "type": typ, "name": name.strip(), "desc": desc.strip(), "attrs": attrs})
        elif parts[0] == "REL" and len(parts) >= 4:
            out["rels"].append([parts[1], parts[2], parts[3]])


async def dump(conn, progress=None) -> dict:
    """逐表导出。progress(表名) 用来更新界面状态。"""
    out: dict = {"version": 1, "built_at": time.time(), "entries": [], "rels": []}
    import asyncio

    for name in _TABLES:
        lo = 0
        while True:
            if progress:
                progress(name if lo == 0 else f"{name} {lo}+")
            lines = await conn.execute_read(build_table_lua(name, lo, lo + PAGE_ROWS), timeout=30.0)
            parse_lines(lines, out)
            total = next((int(ln[4:]) for ln in lines if ln.startswith("KBN|") and ln[4:].isdigit()), 0)
            lo += PAGE_ROWS
            await asyncio.sleep(0.2)  # 给游戏喘口气
            if total <= lo:
                break
    return out


def save(data: dict, path: Path = CACHE_FILE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def load(path: Path = CACHE_FILE) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
