"""城市规则：生产闲置、成长、住房、宜居度、忠诚度、被掠夺建筑。"""

from __future__ import annotations

from civ6_advisor.game import Situation
from civ6_advisor.geo import Plot
from civ6_advisor.rules.base import Finding, Priority, game_phase, rule


def _idle(city) -> bool:
    # civ6-mcp 里空闲城市报告为 "nothing"
    return (city.currently_building or "").lower() in ("", "nothing", "none")


@rule
def idle_production(sit: Situation):
    from civ6_advisor.production import (district_spot_text, empire_status, is_capital, suggest_for_city,
                                         suggestion_text)

    st = empire_status(sit)
    for c in sit.cities:
        if _idle(c):
            picks = suggest_for_city(sit, c, st)
            action = suggestion_text(picks) if picks else _suggest_build(sit, c)
            # 金币建议已经要在这座城买第一名了：锤子就去造第二名，两条建议不打架
            from civ6_advisor.rules.decisions import buy_plan

            bought = next((b for b in buy_plan(sit) if b[2].city_id == c.city_id), None)
            if bought and picks and picks[0].item == bought[1].item_name:
                rest = [p for p in picks if p.item != bought[1].item_name]
                action = (f"直接花 {bought[1].gold_cost} 金买{picks[0].name}（{bought[3]}），"
                          + (f"锤子改造{rest[0].name}：{'；'.join(rest[0].reasons[:2])}" if rest else "锤子再挑一个项目"))
                picks = rest
            plots = [Plot(c.x, c.y, "city", c.name)]
            if picks and picks[0].item.startswith("DISTRICT_"):
                txt, spots = district_spot_text(sit, c, picks[0].item)
                if txt:
                    action += "。" + txt
                    plots = spots + plots
            yield Finding(
                Priority.HIGH,
                "城市",
                f"{'首都' if is_capital(c) else ''}{c.name} 没有在生产任何东西",
                f"每回合 {c.production:.0f} 锤正在浪费。",
                action,
                c.city_id,
                plots,
                tag="production",
            )


def _suggest_build(sit: Situation, c) -> str:
    from civ6_advisor.rules.empire import profile

    phase = game_phase(sit)
    prof = profile(sit)
    if prof and prof.has("gold_buy"):
        return f"{prof.name}手造建筑吃亏：锤子用来出单位和区域，建筑用金币/信仰买。"
    has = {d.upper() for d in c.districts}
    builders = sum(1 for u in sit.units if u.build_charges > 0)
    if phase == "开局" and len(sit.cities) <= 2:
        return "开局常见顺序：侦察兵 → 投石兵/勇士 → 开拓者。"
    if builders == 0 and c.unimproved_resources:
        return "城里有没改良的资源，又没有建造者，先出一个建造者。"
    if c.population >= 3 and not any("CAMPUS" in d or "COMMERCIAL" in d or "HOLY" in d or "THEATER" in d for d in has):
        want = {"科技": "学院区", "文化": "剧院广场", "宗教": "圣地", "金币": "商业中心", "奇观": "剧院广场",
                "征服": "军营", "外交": "商业中心"}
        first = want.get(prof.focus[0], "学院区") if prof else "学院区或商业中心"
        note = ""
        if prof and prof.has("no_adjacent_center"):
            note = "（注意：专业区不能挨着市中心）"
        elif prof and prof.has("district_features"):
            note = "（注意：专业区要建在森林/雨林/沼泽上）"
        return f"人口够了还没有专业区，按{prof.name if prof else '当前'}路线优先建{first}{note}。"
    return "挑一个符合当前胜利路线的项目，别让锤子空转。"


@rule
def growth_and_housing(sit: Situation):
    for c in sit.cities:
        if c.food_surplus <= 0 and c.population > 0:
            yield Finding(
                Priority.HIGH if c.food_surplus < 0 else Priority.MEDIUM,
                "城市",
                f"{c.name} {'在饿死' if c.food_surplus < 0 else '停止成长'}",
                f"粮食盈余 {c.food_surplus:+.1f}。",
                "换一些高粮格子耕作，建农场或粮仓，或者派建造者改良周边资源。",
                c.city_id,
            )
        elif c.housing and c.population >= c.housing:
            yield Finding(
                Priority.MEDIUM,
                "城市",
                f"{c.name} 住房已满",
                f"人口 {c.population} / 住房 {c.housing:.0f}，超过住房后成长会大幅变慢。",
                "建粮仓/引水渠/邻近河流的农场，或者造下水道（后期）。",
                c.city_id,
            )
        elif c.housing and c.population >= c.housing - 1 and c.turns_to_grow <= 5:
            yield Finding(
                Priority.LOW,
                "城市",
                f"{c.name} 快到住房上限",
                f"人口 {c.population} / 住房 {c.housing:.0f}。",
                "提前安排粮仓或引水渠。",
                c.city_id,
            )


@rule
def amenities(sit: Situation):
    for c in sit.cities:
        if c.amenities < 0:
            yield Finding(
                Priority.HIGH if c.amenities <= -3 else Priority.MEDIUM,
                "城市",
                f"{c.name} 宜居度为 {c.amenities}",
                "宜居度为负会降低产出和成长，严重时会出现叛军。",
                "改良新的奢侈品资源，建娱乐区/竞技场，或者用面包与马戏团政策。",
                c.city_id,
            )


@rule
def loyalty(sit: Situation):
    for c in sit.cities:
        if c.loyalty_per_turn < 0:
            flip = c.turns_to_loyalty_flip
            pr = Priority.URGENT if (flip and flip <= 10) or c.loyalty < 40 else Priority.HIGH
            yield Finding(
                pr,
                "城市",
                f"{c.name} 忠诚度在下降",
                f"忠诚度 {c.loyalty:.0f}/{c.loyalty_max:.0f}，每回合 {c.loyalty_per_turn:+.1f}"
                + (f"，约 {flip} 回合后倒戈。" if flip else "。"),
                "派总督过去（阿玛尼最有效），驻扎军队，提升宜居度，或者造纪念碑。",
                c.city_id,
            )


@rule
def pillaged(sit: Situation):
    for c in sit.cities:
        broken = c.pillaged_districts + c.pillaged_buildings + c.pillaged_improvements
        if broken:
            yield Finding(
                Priority.MEDIUM,
                "城市",
                f"{c.name} 有被掠夺的设施",
                "、".join(broken[:6]),
                "区域/建筑在城市生产队列里修复，改良设施让建造者修（不耗次数）。",
                c.city_id,
            )
