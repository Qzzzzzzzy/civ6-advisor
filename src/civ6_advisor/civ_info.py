"""读取玩家的文明/领袖身份和能力（直接从游戏数据库读，自动是游戏当前语言）。

返回的能力描述来自游戏本身，所以 DLC、模组文明也能拿到准确信息；
civs.py 里的人工攻略只覆盖原版+资料片的主要文明，两者结合使用。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from civ_mcp.lua._helpers import SENTINEL

CIV_IDENTITY_LUA = (
    """
local id = Game.GetLocalPlayer()
local cfg = PlayerConfigurations[id]
local civ = cfg:GetCivilizationTypeName() or ""
local leader = cfg:GetLeaderTypeName() or ""
local function clean(s)
  if s == nil then return "" end
  local ok, t = pcall(Locale.Lookup, s)
  if not ok or t == nil then t = tostring(s) end
  t = string.gsub(t, "[\\r\\n|]", " ")
  return t
end
print("ID|" .. civ .. "|" .. leader .. "|" .. clean(cfg:GetCivilizationShortDescription()) .. "|" .. clean(cfg:GetLeaderName()))
local traits = {}
for row in GameInfo.CivilizationTraits() do
  if row.CivilizationType == civ then traits[row.TraitType] = "CIV" end
end
for row in GameInfo.LeaderTraits() do
  if row.LeaderType == leader then traits[row.TraitType] = "LEADER" end
end
for t, src in pairs(traits) do
  local tr = GameInfo.Traits[t]
  if tr and tr.Name and not tr.InternalOnly then
    print("TRAIT|" .. src .. "|" .. t .. "|" .. clean(tr.Name) .. "|" .. clean(tr.Description))
  end
end
local function uniq(kind, iter, key)
  for r in iter do
    if r.TraitType and traits[r.TraitType] then
      print("UNIQ|" .. kind .. "|" .. r[key] .. "|" .. clean(r.Name) .. "|" .. clean(r.Description))
    end
  end
end
pcall(uniq, "UNIT", GameInfo.Units(), "UnitType")
pcall(uniq, "BUILDING", GameInfo.Buildings(), "BuildingType")
pcall(uniq, "DISTRICT", GameInfo.Districts(), "DistrictType")
pcall(uniq, "IMPROVEMENT", GameInfo.Improvements(), "ImprovementType")
print("""
    + f'"{SENTINEL}"'
    + ")\n"
)

KIND_CN = {"UNIT": "特色单位", "BUILDING": "特色建筑", "DISTRICT": "特色区域", "IMPROVEMENT": "特色改良"}


@dataclass
class Ability:
    source: str  # CIV / LEADER / UNIT / BUILDING / DISTRICT / IMPROVEMENT
    type: str
    name: str
    desc: str

    @property
    def label(self) -> str:
        if self.source == "CIV":
            return "文明能力"
        if self.source == "LEADER":
            return "领袖能力"
        return KIND_CN.get(self.source, self.source)


@dataclass
class CivIdentity:
    civ_type: str
    leader_type: str
    civ_name: str
    leader_name: str
    abilities: list[Ability] = field(default_factory=list)

    def summary_lines(self, with_desc: bool = True) -> list[str]:
        order = {"CIV": 0, "LEADER": 1, "DISTRICT": 2, "BUILDING": 3, "IMPROVEMENT": 4, "UNIT": 5}
        out = []
        for a in sorted(self.abilities, key=lambda a: order.get(a.source, 9)):
            out.append(f"- {a.label}「{a.name}」" + (f"：{a.desc}" if with_desc and a.desc else ""))
        return out


_MARKUP = re.compile(r"\[ICON_[^\]]*\]|\[COLOR[^\]]*\]|\[ENDCOLOR\]")


def clean_text(s: str) -> str:
    s = s.replace("[NEWLINE]", " ")
    s = _MARKUP.sub("", s)
    return re.sub(r"\s{2,}", " ", s).strip()


def _useful(name: str, desc: str) -> bool:
    return bool(name) and not name.startswith("LOC_") and not desc.startswith("LOC_")


def parse_identity(lines: list[str]) -> CivIdentity | None:
    ident: CivIdentity | None = None
    abilities: list[Ability] = []
    seen_trait_desc: set[str] = set()
    for line in lines:
        parts = line.split("|")
        if parts[0] == "ID" and len(parts) >= 5:
            ident = CivIdentity(parts[1], parts[2], clean_text(parts[3]), clean_text(parts[4]))
        elif parts[0] == "TRAIT" and len(parts) >= 5:
            name, desc = clean_text(parts[3]), clean_text(parts[4])
            # 特色单位/建筑本身也挂着一个 trait，名字和单位一样，跳过避免重复
            if _useful(name, desc) and not parts[2].startswith(("TRAIT_CIVILIZATION_UNIT_", "TRAIT_CIVILIZATION_BUILDING_",
                                                               "TRAIT_CIVILIZATION_DISTRICT_", "TRAIT_CIVILIZATION_IMPROVEMENT_",
                                                               "TRAIT_LEADER_UNIT_")):
                if desc not in seen_trait_desc:
                    seen_trait_desc.add(desc)
                    abilities.append(Ability(parts[1], parts[2], name, desc))
        elif parts[0] == "UNIQ" and len(parts) >= 5:
            name, desc = clean_text(parts[3]), clean_text(parts[4])
            if _useful(name, desc or "x"):
                abilities.append(Ability(parts[1], parts[2], name, desc))
    if ident:
        ident.abilities = abilities
    return ident
