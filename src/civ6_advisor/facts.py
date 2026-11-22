"""本回合的共同事实：已研究的科技/市政、领土内资源的改良状态。

建造者建议、科技推荐、AI 简报都从这里取数据，保证互相一致：
建造者只会被要求去改良「现在就能改」的资源；改不了的资源会说明缺哪个科技，
科技推荐也会把「能改良你城里的哪个资源」算进去。

只读取玩家看得见的资源（战略资源要研究出对应科技后才可见）。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from civ_mcp.lua._helpers import SENTINEL

FACTS_LUA = (
    r"""
local me = Game.GetLocalPlayer()
local p = Players[me]
local techs = p:GetTechs()
local culture = p:GetCulture()
local function hasTech(t)
  if t == nil then return true end
  local info = GameInfo.Technologies[t]
  if info == nil then return true end
  local ok, r = pcall(function() return techs:HasTech(info.Index) end)
  return ok and r
end
local function hasCivic(t)
  if t == nil then return true end
  local info = GameInfo.Civics[t]
  if info == nil then return true end
  local ok, r = pcall(function() return culture:HasCivic(info.Index) end)
  return ok and r
end
for t in GameInfo.Technologies() do if hasTech(t.TechnologyType) then print("TECH|" .. t.TechnologyType) end end
for c in GameInfo.Civics() do if hasCivic(c.CivicType) then print("CIVIC|" .. c.CivicType) end end

-- 资源 → 通用改良设施（不含其他文明的特色改良）
local impFor = {}
for r in GameInfo.Improvement_ValidResources() do
  local imp = GameInfo.Improvements[r.ImprovementType]
  if imp and imp.TraitType == nil then
    impFor[r.ResourceType] = impFor[r.ResourceType] or {}
    table.insert(impFor[r.ResourceType], imp)
  end
end
local pres = p:GetResources()
local seen = {}
for _, city in p:GetCities():Members() do
  local cname = Locale.Lookup(city:GetName()):gsub("|", "/")
  local cx, cy = city:GetX(), city:GetY()
  for dy = -3, 3 do for dx = -3, 3 do
    local plot = Map.GetPlot(cx + dx, cy + dy)
    if plot and plot:GetOwner() == me and not seen[plot:GetIndex()] then
      seen[plot:GetIndex()] = true
      local rt = plot:GetResourceType()
      if rt >= 0 and plot:GetImprovementType() < 0 then
        local ri = GameInfo.Resources[rt]
        local visible = true
        if ri then
          local ok, v = pcall(function() return pres:IsResourceVisible(ri.Hash) end)
          if ok then visible = v end
        end
        if ri and visible then
          local best, bestOk, bestReq = "", false, ""
          for _, imp in ipairs(impFor[ri.ResourceType] or {}) do
            local ok = hasTech(imp.PrereqTech) and hasCivic(imp.PrereqCivic)
            if best == "" or (ok and not bestOk) then
              best, bestOk, bestReq = imp.ImprovementType, ok, (imp.PrereqTech or imp.PrereqCivic or "")
            end
          end
          print("RES|" .. cname .. "|" .. plot:GetX() .. "|" .. plot:GetY() .. "|" .. ri.ResourceType .. "|" ..
                (ri.ResourceClassType or "") .. "|" .. best .. "|" .. bestReq .. "|" .. (bestOk and "1" or "0"))
        end
      end
    end
  end end
end

-- 城市周围 3 格（自己的或无主的地块）的地形/地貌/资源统计：选万神殿、判断地图用
local cnt, seen2 = {}, {}
local function add(k) cnt[k] = (cnt[k] or 0) + 1 end
for _, city in p:GetCities():Members() do
  local cx, cy = city:GetX(), city:GetY()
  for dy = -3, 3 do for dx = -3, 3 do
    local plot = Map.GetPlot(cx + dx, cy + dy)
    if plot and not seen2[plot:GetIndex()] and (plot:GetOwner() == me or plot:GetOwner() < 0)
       and Map.GetPlotDistance(cx, cy, plot:GetX(), plot:GetY()) <= 3 then
      seen2[plot:GetIndex()] = true
      pcall(function()
        local ti = GameInfo.Terrains[plot:GetTerrainType()]
        if ti then add(ti.TerrainType) end
        if plot:IsHills() then add("HILLS") end
        local fi = plot:GetFeatureType() >= 0 and GameInfo.Features[plot:GetFeatureType()] or nil
        if fi then add(fi.FeatureType) end
        if plot:IsRiver() then add("RIVER") end
        local okA, ap = pcall(function() return plot:GetAppeal() end)
        if okA and ap and ap >= 4 then add("BREATHTAKING") end
        local rt = plot:GetResourceType()
        if rt >= 0 then
          local ri = GameInfo.Resources[rt]
          local imps = ri and impFor[ri.ResourceType]
          if imps and imps[1] then add("RES_" .. imps[1].ImprovementType) end
          if ri then add(ri.ResourceClassType or "RESOURCECLASS_BONUS") end
        end
      end)
    end
  end end
end
for k, n in pairs(cnt) do print("TERR|" .. k .. "|" .. n) end
local okM, myMil = pcall(function() return p:GetStats():GetMilitaryStrength() end)
if okM and myMil then print("MIL|" .. math.floor(myMil)) end
print("""
    + f'"{SENTINEL}"'
    + ")\n"
)


@dataclass
class ResourceTile:
    city: str
    x: int
    y: int
    resource: str  # RESOURCE_CITRUS
    cls: str  # luxury / strategic / bonus
    improvement: str  # IMPROVEMENT_PLANTATION（空 = 没有可用的改良设施）
    prereq: str  # 需要的科技/市政类型名，空 = 不需要
    can_now: bool


@dataclass
class EmpireFacts:
    techs: set[str] = field(default_factory=set)
    civics: set[str] = field(default_factory=set)
    resources: list[ResourceTile] = field(default_factory=list)
    terrain: dict[str, int] = field(default_factory=dict)  # 城市 3 格内地形/地貌/资源计数
    military: int | None = None  # 游戏算的我方军力（和对手的军力同一口径）

    def count(self, *keys: str) -> int:
        return sum(self.terrain.get(k, 0) for k in keys)

    @property
    def improvable_now(self) -> list[ResourceTile]:
        return [r for r in self.resources if r.can_now and r.improvement]

    @property
    def blocked(self) -> list[ResourceTile]:
        return [r for r in self.resources if not r.can_now and r.improvement]


CLS = {"RESOURCECLASS_LUXURY": "luxury", "RESOURCECLASS_STRATEGIC": "strategic", "RESOURCECLASS_BONUS": "bonus"}


def parse_facts(lines: list[str]) -> EmpireFacts:
    f = EmpireFacts()
    for ln in lines:
        parts = ln.split("|")
        if parts[0] == "TECH" and len(parts) > 1:
            f.techs.add(parts[1])
        elif parts[0] == "CIVIC" and len(parts) > 1:
            f.civics.add(parts[1])
        elif parts[0] == "MIL" and len(parts) >= 2 and parts[1].lstrip("-").isdigit():
            f.military = int(parts[1])
        elif parts[0] == "TERR" and len(parts) >= 3 and parts[2].isdigit():
            f.terrain[parts[1]] = int(parts[2])
        elif parts[0] == "RES" and len(parts) >= 9:
            try:
                f.resources.append(ResourceTile(parts[1], int(parts[2]), int(parts[3]), parts[4],
                                                CLS.get(parts[5], "bonus"), parts[6], parts[7], parts[8] == "1"))
            except ValueError:
                continue
    # 奢侈品 > 战略 > 加成
    order = {"luxury": 0, "strategic": 1, "bonus": 2}
    f.resources.sort(key=lambda r: (order.get(r.cls, 3), r.city))
    return f


CLS_CN = {"luxury": "奢侈品", "strategic": "战略资源", "bonus": "加成资源"}
IMPROVEMENT_CN = {
    "IMPROVEMENT_FARM": "农场", "IMPROVEMENT_MINE": "矿山", "IMPROVEMENT_QUARRY": "采石场",
    "IMPROVEMENT_PASTURE": "牧场", "IMPROVEMENT_CAMP": "营地", "IMPROVEMENT_PLANTATION": "种植园",
    "IMPROVEMENT_FISHING_BOATS": "渔船", "IMPROVEMENT_OIL_WELL": "油井", "IMPROVEMENT_OFFSHORE_OIL_RIG": "海上钻井平台",
    "IMPROVEMENT_LUMBER_MILL": "伐木场",
}
