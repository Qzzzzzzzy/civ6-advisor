"""规则引擎基础类型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import IntEnum
from typing import Callable, Iterable

from civ6_advisor.game import Situation
from civ6_advisor.geo import Plot, describe, hex_distance  # noqa: F401  (hex_distance 供其他规则导入)


class Priority(IntEnum):
    URGENT = 0  # 本回合不处理会直接吃亏（丢城、单位被杀、负债）
    HIGH = 1  # 明显的效率浪费（生产/研究闲置、成长卡住）
    MEDIUM = 2  # 值得做的优化
    LOW = 3  # 提示信息

    @property
    def label(self) -> str:
        return {0: "🔴 紧急", 1: "🟠 重要", 2: "🟡 建议", 3: "⚪ 提示"}[self.value]


@dataclass
class Finding:
    priority: Priority
    category: str  # 军事 / 城市 / 经济 / 科技文化 / 单位 / 外交 / 宗教 / 时代
    title: str
    detail: str
    action: str = ""  # 具体建议做什么
    city_id: int | None = None
    plots: list[Plot] = field(default_factory=list)  # 涉及的格子，悬浮窗点击后在地图上标出
    tag: str = ""  # research / civic / eureka：悬浮窗放到科技市政板块，不进建议列表

    def render(self) -> str:
        s = f"{self.priority.label}【{self.category}】{self.title}\n  {self.detail}"
        if self.action:
            s += f"\n  → {self.action}"
        if self.plots:
            s += "\n  📍 " + "；".join(f"{p.label or p.kind} ({p.x},{p.y})" for p in self.plots[:6])
        return s


Rule = Callable[[Situation], Iterable[Finding]]
RULES: list[Rule] = []


def rule(fn: Rule) -> Rule:
    """装饰器：注册一条规则。"""
    RULES.append(fn)
    return fn


def game_phase(sit: Situation) -> str:
    """按游戏速度折算后的阶段：开局 / 前期 / 中期 / 后期。"""
    mult = (sit.overview.speed_cost_multiplier or 100) / 100
    t = sit.overview.turn / mult  # 折算成标准速度回合
    if t <= 30:
        return "开局"
    if t <= 100:
        return "前期"
    if t <= 200:
        return "中期"
    return "后期"
