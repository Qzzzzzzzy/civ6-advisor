"""格子坐标工具：距离、方位、"在哪座城什么方向几格"的描述。

文明6 的格子用 offset 坐标 (x, y)：奇数行向右错半格，y 越大越靠北（地图底部是 y=0）。
游戏界面默认不显示坐标，所以给玩家看的位置都换算成"相对最近城市的方位+距离"。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

Y_UP = True  # y 增大是向北。如果实测方向南北反了，把这里改成 False

DIRS = ["东", "东北", "北", "西北", "西", "西南", "南", "东南"]


def _cube(x: int, y: int) -> tuple[int, int, int]:
    q = x - (y - (y & 1)) // 2
    return q, y, -q - y


def hex_distance(x1: int, y1: int, x2: int, y2: int) -> int:
    a, b = _cube(x1, y1), _cube(x2, y2)
    return max(abs(a[0] - b[0]), abs(a[1] - b[1]), abs(a[2] - b[2]))


def _center(x: int, y: int) -> tuple[float, float]:
    """格子中心的平面坐标（单位：格宽）。"""
    px = x + (0.5 if y & 1 else 0.0)
    py = y * math.sqrt(3) / 2
    return px, (py if Y_UP else -py)


def direction(fx: int, fy: int, tx: int, ty: int) -> str:
    """从 (fx,fy) 看 (tx,ty) 在哪个方向（八方位）。"""
    ax, ay = _center(fx, fy)
    bx, by = _center(tx, ty)
    ang = math.degrees(math.atan2(by - ay, bx - ax)) % 360
    return DIRS[int((ang + 22.5) // 45) % 8]


@dataclass
class Plot:
    """建议里涉及的格子。kind 决定地图上的颜色。"""

    x: int
    y: int
    kind: str  # danger 敌军 / settle 城址 / move 建议去的位置 / improve 待改良 / city 城市 / unit 我方单位
    label: str = ""


KIND_COLOR = {  # 悬浮窗里的颜色（地图标记的图标见 highlight.py）
    "danger": "#ff5c5c",
    "settle": "#51cf66",
    "move": "#4dabf7",
    "improve": "#ffd43b",
    "city": "#d6aa50",
    "unit": "#ffa94d",
    "district": "#b197fc",
}

KIND_CN = {"danger": "敌军", "settle": "城址", "move": "目标", "improve": "待改良", "city": "城市", "unit": "单位", "district": "区域位"}


def nearest_city(cities, x: int, y: int):
    best, bd = None, 10**9
    for c in cities:
        d = hex_distance(c.x, c.y, x, y)
        if d < bd:
            best, bd = c, d
    return best, bd


def describe_sit(sit, x: int, y: int) -> str:
    """有城市时相对最近城市描述；还没建城时相对开拓者/其他单位描述。"""
    if sit.cities:
        return describe(sit.cities, x, y)
    units = sorted(sit.units, key=lambda u: 0 if "SETTLER" in u.unit_type.upper() else 1)
    if not units:
        return f"({x},{y})"
    u, d = nearest_city(units[:1] if "SETTLER" in units[0].unit_type.upper() else units, x, y)
    if d == 0:
        return f"{u.name}原地"
    return f"{u.name}{direction(u.x, u.y, x, y)} {d} 格"


def describe(cities, x: int, y: int) -> str:
    """'西安东北 3 格'；就在城上返回城名；没有城市时返回坐标。"""
    c, d = nearest_city(cities, x, y)
    if c is None:
        return f"({x},{y})"
    if d == 0:
        return c.name
    return f"{c.name}{direction(c.x, c.y, x, y)} {d} 格"
