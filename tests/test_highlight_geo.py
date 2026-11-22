"""地图标记 Lua 代码 + 方位描述 + 文明定制规则的测试。

地图标记用 lupa（Lua 5.1，和文明6脚本引擎兼容）真实执行生成的代码，模拟 UILens/UI/Map 接口，
检查调用参数是否正确、某个接口缺失时不会报错。
"""

import dataclasses

import pytest

from civ6_advisor import geo
from civ6_advisor.geo import Plot
from civ6_advisor.highlight import build_clear, build_highlight, focus_plot
from civ6_advisor.mock import mock_situation
from civ6_advisor.rules import analyze

lupa = pytest.importorskip("lupa")
try:
    from lupa import lua51 as rt
except ImportError:  # pragma: no cover
    rt = lupa

STUBS = r"""
_out, calls = {}, {}
function print(s) table.insert(_out, s) end
local function rec(name) return function(...) table.insert(calls, {name, ...}); return true end end
Game = {GetLocalPlayer = function() return 0 end}
Map = {GetPlot = function(x, y) return {x = x, y = y} end}
Network = {BroadcastPlayerInfo = rec("broadcast")}
UILens = {CreateLensLayerHash = function(n) return n end, ClearLayerHexes = rec("lensclear"),
          ToggleLayerOff = rec("lensoff"), ToggleLayerOn = rec("lenson")}
UI = {AddWorldViewText = rec("text"), LookAtPlot = rec("look")}
-- 地图标记：模拟玩家已有一个自己的标记和一个旧的军师标记
pins, nextId = {}, 1
local function newpin(x, y, name)
  local p = {id = nextId, x = x, y = y, name = name or "", icon = ""}
  nextId = nextId + 1
  function p:GetID() return self.id end
  function p:GetName() return self.name end
  function p:SetName(n) self.name = n end
  function p:SetIconName(i) self.icon = i end
  function p:GetHexX() return self.x end
  function p:GetHexY() return self.y end
  pins[p.id] = p
  return p
end
newpin(1, 1, "我的标记")
newpin(9, 9, "军师·旧标记")
PlayerConfigurations = {[0] = {
  GetMapPins = function(self) local t = {} for _, p in pairs(pins) do table.insert(t, p) end return t end,
  GetMapPin = function(self, x, y)
    for _, p in pairs(pins) do if p.x == x and p.y == y then return p end end
    return newpin(x, y)
  end,
  DeleteMapPin = function(self, id) pins[id] = nil end,
}}
function pinlist()
  local t = {}
  for _, p in pairs(pins) do table.insert(t, p.x .. "," .. p.y .. "=" .. p.name .. "|" .. p.icon) end
  table.sort(t)
  return table.concat(t, ";")
end
"""


def run(code, stubs=STUBS):
    lua = rt.LuaRuntime()
    lua.execute(stubs)
    lua.execute(code)
    out = list(lua.eval("_out").values())
    calls = [list(c.values()) for c in lua.eval("calls").values()]
    return out, calls, lua.eval("pinlist()")


def test_pins_added_old_removed_player_pins_kept():
    plots = [Plot(17, 18, "city", "长安"), Plot(15, 20, "danger", '蛮族"骑射手'),
             Plot(1, 1, "settle", "1号城址"), Plot(24, 18, "settle", "2号城址")]
    out, calls, pins = run(build_highlight(plots, look_at=focus_plot(plots)))
    assert out[0].startswith("HL|pins:2") and "look" in out[0]
    assert "1,1=我的标记|" in pins  # 玩家自己的标记没被覆盖
    assert "9,9" not in pins  # 旧的军师标记被删掉
    assert '15,20=军师·蛮族"骑射手|ICON_MAP_PIN_X' in pins
    assert "24,18=军师·2号城址|ICON_MAP_PIN_CIRCLE" in pins
    assert "17,18" not in pins  # 城市只用来定位，不插标记
    assert any(c[0] == "broadcast" for c in calls)
    texts = [c[2] for c in calls if c[0] == "text"]
    assert '蛮族"骑射手' in texts
    assert not any(c[0] == "lenson" for c in calls)  # 不再打开透镜图层（会让地图变灰）


def test_survives_missing_apis():
    stubs = STUBS + "PlayerConfigurations = {[0] = {}} UI.AddWorldViewText = nil Network = nil"
    plots = [Plot(5, 5, "settle", "1号城址")]
    out, calls, _ = run(build_highlight(plots, look_at=plots[0]), stubs=stubs)
    assert out[0].startswith("HL|pins:0")
    assert any(c[0] == "look" for c in calls)


def test_clear_removes_only_ours_and_fixes_gray():
    out, calls, pins = run(build_clear(fix_gray=True))
    assert out[0] == "HL|cleared:1"
    assert pins == "1,1=我的标记|"
    assert sum(1 for c in calls if c[0] == "lensoff") == 4


def test_focus_order():
    ps = [Plot(1, 1, "unit"), Plot(2, 2, "settle"), Plot(3, 3, "danger")]
    assert focus_plot(ps).kind == "settle"


def test_describe_without_cities_uses_settler():
    sit = mock_situation()
    sit.cities = []
    assert geo.describe_sit(sit, 21, 15) == "开拓者原地"
    assert geo.describe_sit(sit, 23, 15) == "开拓者东 2 格"


def test_direction_and_describe():
    assert geo.direction(10, 10, 12, 10) == "东"
    assert geo.direction(10, 10, 8, 10) == "西"
    assert geo.direction(10, 10, 10, 14) == "北"  # y 增大是北
    assert geo.direction(10, 10, 10, 6) == "南"
    assert geo.direction(10, 10, 11, 12) == "东北"
    sit = mock_situation()
    assert geo.describe(sit.cities, 17, 18) == "长安"
    assert geo.describe(sit.cities, 15, 20) == "长安西北 3 格"


def test_findings_carry_plots():
    f = analyze(mock_situation())
    settle = next(x for x in f if "开拓者" in x.title)
    assert [p.kind for p in settle.plots].count("settle") == 3
    assert "1号：西安东北 6 格" in settle.action
    threat = next(x for x in f if "附近有敌军" in x.title)
    assert {p.kind for p in threat.plots} == {"city", "danger"}
    assert "骑射手" in threat.detail


# ---------------------------------------------------------------- 文明定制


def with_civ(civ_type, leader=""):
    sit = mock_situation()
    sit.civ = dataclasses.replace(sit.civ, civ_type=civ_type, leader_type=leader, abilities=[])
    return sit


def test_civ_strategy_differs_by_civ():
    china = next(x for x in analyze(mock_situation()) if x.category == "文明")
    korea = next(x for x in analyze(with_civ("CIVILIZATION_KOREA")) if x.category == "文明")
    assert "中国" in china.title and "秦始皇" in china.action
    assert "朝鲜" in korea.title and "书院" in korea.action
    assert china.action != korea.action


def test_religion_rules_follow_civ():
    sit = with_civ("CIVILIZATION_RUSSIA")
    sit.overview = dataclasses.replace(sit.overview, religions_founded=1)
    def rel(s):  # 万神殿人人都能选，不算"宗教路线"建议
        return [x for x in analyze(s) if x.category == "宗教" and "万神殿" not in x.title]

    r = rel(sit)
    assert r and "俄罗斯要尽快创立宗教" in r[0].title
    assert not rel(with_civ("CIVILIZATION_KONGO"))
    assert not rel(with_civ("CIVILIZATION_ARABIA"))


def test_expansion_target_follows_civ():
    sit = with_civ("CIVILIZATION_ROME")
    sit.units = [u for u in sit.units if u.unit_type != "UNIT_SETTLER"]  # 有开拓者时不提示扩张
    rome = [x for x in analyze(sit) if "扩张偏慢" in x.title]
    assert rome and "罗马前期目标约 8 座城" in rome[0].detail


def test_idle_city_build_hint_follows_civ():
    from civ6_advisor.production import suggest_for_city

    sit = with_civ("CIVILIZATION_MALI")
    beijing = next(c for c in sit.cities if c.name == "北京")
    picks = suggest_for_city(sit, beijing)
    monument = next(p for p in picks if p.item == "BUILDING_MONUMENT")
    assert any("用钱买" in r for r in monument.reasons)
    china = {p.item: p.score for p in suggest_for_city(mock_situation(), beijing)}
    assert monument.score < china["BUILDING_MONUMENT"]


def test_unknown_civ_falls_back_to_game_abilities():
    sit = mock_situation()
    sit.civ = dataclasses.replace(sit.civ, civ_type="CIVILIZATION_MODDED_X")
    f = next(x for x in analyze(sit) if x.category == "文明")
    assert "攻略库没有收录" in f.detail and "王朝更替" in f.detail


def test_parse_identity_cleans_markup():
    from civ6_advisor.civ_info import parse_identity

    lines = [
        "ID|CIVILIZATION_KOREA|LEADER_SEONDEOK|朝鲜|善德女王",
        "TRAIT|CIV|TRAIT_CIVILIZATION_THREE_KINGDOMS|三国|矿山 +1 [ICON_Science] 科技值。[NEWLINE]农场 +1 粮。",
        "TRAIT|CIV|TRAIT_CIVILIZATION_UNIT_KOREAN_HWACHA|火车|x",
        "TRAIT|LEADER|TRAIT_X|LOC_TRAIT_X_NAME|LOC_TRAIT_X_DESC",
        "UNIQ|DISTRICT|DISTRICT_SEOWON|书院|替代学院区。",
    ]
    ident = parse_identity(lines)
    assert ident.civ_name == "朝鲜"
    assert [a.name for a in ident.abilities] == ["三国", "书院"]
    assert ident.abilities[0].desc == "矿山 +1 科技值。 农场 +1 粮。"
