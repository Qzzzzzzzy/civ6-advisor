"""在游戏地图上标出建议涉及的格子：地图标记（图钉）+ 格子上方飘字 + 移动镜头。

用的是游戏自带的「地图标记」功能（玩家手动插图钉的那个），不会改变地图颜色。
军师插的标记名字都以「军师·」开头，每次刷新只删除自己插的，不会动玩家自己的标记。
所有调用都包在 pcall 里，某个接口不可用时只会跳过。

旧版本用透镜着色图层上色，会让整张地图变灰；cleanup 会把那些图层关掉恢复画面。
"""

from __future__ import annotations

from typing import Iterable

from civ_mcp.lua._helpers import SENTINEL

from civ6_advisor.geo import Plot

PIN_PREFIX = "军师·"

# 标记图标（游戏自带的地图标记图标）
PIN_ICONS = {
    "danger": "ICON_MAP_PIN_X",
    "settle": "ICON_MAP_PIN_CIRCLE",
    "move": "ICON_MAP_PIN_TRIANGLE",
    "improve": "ICON_MAP_PIN_DIAMOND",
    "city": "ICON_MAP_PIN_SQUARE",
    "unit": "ICON_MAP_PIN_SQUARE",
    "district": "ICON_MAP_PIN_DIAMOND",
}

# 旧版本误开的透镜图层，清理时关掉
LEGACY_LAYERS = ("Hex_Coloring_Religion", "Hex_Coloring_Appeal_Level", "Hex_Coloring_Great_People", "Hex_Coloring_Movement")

# 点建议时镜头优先看哪类格子
FOCUS_ORDER = ("settle", "danger", "move", "improve", "city", "unit")

# 不给这类格子插标记（我方单位/城市自己就看得见），只用来定位镜头
NO_PIN_KINDS = ("unit", "city")


def lua_str(s: str) -> str:
    out = ['"']
    for ch in s:
        if ch in '\\"':
            out.append("\\" + ch)
        elif ord(ch) < 32:
            out.append(" ")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def focus_plot(plots: list[Plot]) -> Plot | None:
    for kind in FOCUS_ORDER:
        for p in plots:
            if p.kind == kind:
                return p
    return plots[0] if plots else None


_REMOVE_OURS = (
    "local pid = Game.GetLocalPlayer() "
    "local cfg = PlayerConfigurations and PlayerConfigurations[pid] or {} "
    f"local PREFIX = {lua_str(PIN_PREFIX)} "
    "local res = {} "
    "local removed = 0 "
    "local others = {} "  # 玩家自己的标记所在格子，不覆盖
    "pcall(function() "
    "  local pins = cfg:GetMapPins() "
    "  for _, pin in pairs(pins) do "
    "    local n = pin:GetName() or '' "
    "    if string.sub(n, 1, #PREFIX) == PREFIX then "
    "      cfg:DeleteMapPin(pin:GetID()) removed = removed + 1 "
    "    else others[pin:GetHexX() .. ',' .. pin:GetHexY()] = true end "
    "  end "
    "end) "
)

_FIX_GRAY = (
    "for _, n in ipairs({" + ",".join(f'"{n}"' for n in LEGACY_LAYERS) + "}) do "
    "  local ok, h = pcall(function() return UILens.CreateLensLayerHash(n) end) "
    "  if ok and h then pcall(function() UILens.ClearLayerHexes(h) end) pcall(function() UILens.ToggleLayerOff(h) end) end "
    "end "
)


def build_clear(fix_gray: bool = False) -> str:
    return (
        _REMOVE_OURS
        + (_FIX_GRAY if fix_gray else "")
        + "pcall(function() Network.BroadcastPlayerInfo() end) "
        + f'print("HL|cleared:" .. removed) print("{SENTINEL}")'
    )


def build_highlight(plots: Iterable[Plot], look_at: Plot | None = None, labels: bool = True) -> str:
    """插地图标记（+可选飘字和镜头移动）。坐标都是整数，名字经过转义。"""
    plots = list(plots)
    parts = [_REMOVE_OURS, "local added = 0 "]
    seen: set[tuple[int, int]] = set()
    for p in plots:
        x, y = int(p.x), int(p.y)
        if p.kind in NO_PIN_KINDS or (x, y) in seen:
            continue
        seen.add((x, y))
        name = lua_str(PIN_PREFIX + (p.label or p.kind))
        icon = PIN_ICONS.get(p.kind, "ICON_MAP_PIN_CIRCLE")
        parts.append(
            f"if not others['{x},{y}'] then pcall(function() "
            f"local pin = cfg:GetMapPin({x}, {y}) "
            f"if pin then pin:SetName({name}) pcall(pin.SetIconName, pin, \"{icon}\") added = added + 1 end "
            f"end) end "
        )
    parts.append("pcall(function() Network.BroadcastPlayerInfo() end) ")
    parts.append("table.insert(res, 'pins:' .. added) ")
    if labels:
        for p in plots:
            if p.label:
                parts.append(f"pcall(function() UI.AddWorldViewText(0, {lua_str(p.label)}, {int(p.x)}, {int(p.y)}, 0) end) ")
    if look_at:
        parts.append(
            f"do local okp, lp = pcall(function() return Map.GetPlot({int(look_at.x)}, {int(look_at.y)}) end) "
            "if okp and lp then if pcall(function() UI.LookAtPlot(lp) end) then table.insert(res, 'look') end end end "
        )
    parts.append(f'print("HL|" .. table.concat(res, ",")) print("{SENTINEL}")')
    return "".join(parts)


def build_look(plot: Plot) -> str:
    """只移动镜头，不改任何游戏数据（最安全）。"""
    return (
        f"local res = {{}} do local okp, lp = pcall(function() return Map.GetPlot({int(plot.x)}, {int(plot.y)}) end) "
        "if okp and lp then if pcall(function() UI.LookAtPlot(lp) end) then table.insert(res, 'look') end end end "
        f'print("HL|" .. table.concat(res, ",")) print("{SENTINEL}")'
    )


class Highlighter:
    """只做地图标记的通道。"""

    def __init__(self, conn):
        self.conn = conn

    async def show(self, plots: list[Plot], look: bool = True, labels: bool = True) -> str:
        if not plots:
            return await self.clear()
        lines = await self.conn.execute_write(build_highlight(plots, focus_plot(plots) if look else None, labels))
        return next((ln for ln in lines if ln.startswith("HL|")), "HL|noresult")

    async def look(self, plot: Plot) -> str:
        lines = await self.conn.execute_write(build_look(plot))
        return next((ln for ln in lines if ln.startswith("HL|")), "HL|noresult")

    async def clear(self, fix_gray: bool = False) -> str:
        lines = await self.conn.execute_write(build_clear(fix_gray))
        return next((ln for ln in lines if ln.startswith("HL|")), "HL|noresult")
