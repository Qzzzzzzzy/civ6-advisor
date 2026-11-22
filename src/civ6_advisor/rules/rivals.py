"""与已相遇文明的对比。

注：rivals 数据里有对手的产出数字。游戏界面本身能看到排行和部分数据，
但精确数值属于灰色信息，所以默认只给排名，不报具体数字（STRICT_FOG=0 可关闭）。
"""

from __future__ import annotations

import os

from civ6_advisor.game import Situation
from civ6_advisor.rules.base import Finding, Priority, rule


def strict_fog() -> bool:
    return os.environ.get("CIV6_ADVISOR_STRICT_FOG", "1") != "0"


def rank_of(mine: float, others: list[float]) -> int:
    return 1 + sum(1 for v in others if v > mine)


# 社区常见的铺城节奏（标准速度，较高难度）：T30 两座、T50 三四座、T70 六座左右、T100 八座以上
CITY_BENCH = ((30, 2), (50, 4), (70, 6), (100, 8))


def city_benchmark(turn: int) -> int:
    prev_t, prev_n = 0, 1
    for t, n in CITY_BENCH:
        if turn <= t:
            return max(1, round(prev_n + (n - prev_n) * (turn - prev_t) / (t - prev_t)))
        prev_t, prev_n = t, n
    return CITY_BENCH[-1][1]


def _expand_fix(sit: Situation) -> str:
    b = city_benchmark(sit.overview.turn)
    have = len(sit.cities)
    if have >= b:
        return "城市数量本身达标，对手只是铺得更快；注意抢好地"
    return (f"第 {sit.overview.turn} 回合一般应有约 {b} 座城（你 {have} 座）。开拓者优先：插「殖民」、金币直接买开拓者，"
            "马格努斯升「供给」出开拓者不掉人口")


@rule
def yield_ranking(sit: Situation):
    if not sit.rivals:
        return
    o = sit.overview
    n = len(sit.rivals) + 1
    metrics = [
        ("科研", o.science_yield, [r.sci for r in sit.rivals], "学院区、图书馆、科研类城邦"),
        ("文化", o.culture_yield, [r.cul for r in sit.rivals], "剧院广场、纪念碑、文化类城邦"),
        ("城市数", len(sit.cities), [r.cities for r in sit.rivals], _expand_fix(sit)),
    ]
    from civ6_advisor.rules.empire import profile

    prof = profile(sit)
    for name, mine, others, fix in metrics:
        if name == "科研" and prof and prof.has("low_science_ok"):
            continue
        rk = rank_of(mine, others)
        if rk == n and n >= 3:
            detail = f"在已相遇的 {n} 个文明里排最后。"
            if not strict_fog():
                detail += f" 我方 {mine:.0f}，最高 {max(others):.0f}。"
            yield Finding(Priority.MEDIUM, "外交", f"{name}垫底", detail, f"补短板：{fix}。")


@rule
def runaway_rival(sit: Situation):
    """有对手在某条胜利线上大幅领先时提醒。"""
    for r in sit.rivals:
        if r.sci_vp and r.sci_vp >= 30:
            yield Finding(
                Priority.HIGH,
                "外交",
                f"{r.name} 科技胜利进度很快",
                "对方已经进入太空竞赛后段。",
                "考虑联合其他文明对它宣战，或者派间谍破坏太空港。",
            )
        if r.diplo_vp and r.diplo_vp >= 15:
            yield Finding(
                Priority.HIGH,
                "外交",
                f"{r.name} 外交胜利点数接近 20",
                "世界议会上要投反对票压它。",
                "在议会提案里投票让它扣外交胜利点。",
            )
