"""军事规则：城市威胁、战争实力对比、残血单位。"""

from __future__ import annotations

from collections import defaultdict

from civ6_advisor.game import Situation
from civ6_advisor.geo import Plot, describe, describe_sit, nearest_city
from civ6_advisor.names import unit_cn
from civ6_advisor.rules.base import Finding, Priority, hex_distance, rule

DANGER_RADIUS = 4  # 敌军离城市多少格以内算威胁
WATCH_RADIUS = 6


def _hostile_ids(sit: Situation) -> set[int]:
    ids = {63}  # 蛮族
    ids |= {c.player_id for c in sit.diplomacy if c.is_at_war}
    return ids


def _short(unit_type: str) -> str:
    return unit_cn(unit_type)


def _owner(t) -> str:
    return "蛮族" if t.owner_id == 63 else t.owner_name


@rule
def city_threats(sit: Situation):
    hostile = _hostile_ids(sit)
    unfriendly = {
        c.player_id
        for c in sit.diplomacy
        if c.diplomatic_state in ("DENOUNCED", "UNFRIENDLY") and not c.is_at_war
    }
    for city in sit.cities:
        near_hostile, near_watch = [], []
        for t in sit.threats:
            d = hex_distance(city.x, city.y, t.x, t.y)
            if t.owner_id in hostile and d <= DANGER_RADIUS:
                near_hostile.append((d, t))
            elif t.owner_id in unfriendly and d <= WATCH_RADIUS:
                near_watch.append((d, t))

        if near_hostile:
            near_hostile.sort(key=lambda p: p[0])
            enemy_power = sum(max(t.combat_strength, t.ranged_strength) for _, t in near_hostile)
            desc = "、".join(
                f"{_owner(t)}的{_short(t.unit_type)}(战力{max(t.combat_strength, t.ranged_strength)}，"
                f"在{describe([city], t.x, t.y)})"
                for d, t in near_hostile[:5]
            )
            plots = [Plot(city.x, city.y, "city", city.name)] + [
                Plot(t.x, t.y, "danger", f"{_owner(t)}{_short(t.unit_type)}") for _, t in near_hostile[:5]
            ]
            no_walls = city.wall_max_hp == 0
            no_garrison = not city.garrison_unit
            weak = enemy_power > city.defense_strength * 1.5 or (no_garrison and len(near_hostile) >= 2)
            pr = Priority.URGENT if (weak or near_hostile[0][0] <= 2) else Priority.HIGH
            tips = []
            if no_garrison:
                tips.append("城里没有驻军，调一个近战单位进城")
            if no_walls and city.population >= 3:
                tips.append("考虑插队造古城墙")
            if city.attack_targets:
                tips.append("城市本回合可以远程攻击，别忘了打")
            if not tips:
                tips.append("集中单位守住城市周边的丘陵/河流地形")
            yield Finding(
                pr,
                "军事",
                f"{city.name} 附近有敌军",
                f"{desc}。城防 {city.defense_strength}，敌方合计战力约 {enemy_power}。",
                "；".join(tips) + "。",
                city.city_id,
                plots,
            )
        elif near_watch:
            names = sorted({t.owner_name for _, t in near_watch})
            yield Finding(
                Priority.MEDIUM,
                "军事",
                f"{city.name} 附近有关系不好的文明集结军队",
                f"{'、'.join(names)} 的 {len(near_watch)} 个军事单位在 {WATCH_RADIUS} 格内。",
                "盯着动向，适当补防御，必要时提前造城墙。",
                city.city_id,
                [Plot(t.x, t.y, "danger", t.owner_name) for _, t in near_watch[:5]],
            )


def my_military(sit: Situation) -> tuple[int, bool]:
    """我方军力：优先用游戏算的（和对手同口径）；读不到就用单位战力粗算。返回 (军力, 是否同口径)。"""
    if sit.facts is not None and sit.facts.military:
        return sit.facts.military, True
    return sum(max(u.combat_strength, u.ranged_strength) for u in sit.units), False


HOSTILE_STATES = ("UNFRIENDLY", "DENOUNCED", "冷淡", "谴责", "敌对")


@rule
def neighbor_military(sit: Situation):
    """和平时期：关系差、军力明显比我强的邻居 → 提前备战（只在同口径数据下判断）。"""
    my_mil, same = my_military(sit)
    if not same or my_mil <= 0:
        return
    for civ in sit.diplomacy:
        if civ.is_at_war or not civ.has_met or not civ.military_strength:
            continue
        hostile = any(h in (civ.diplomatic_state or "").upper() for h in HOSTILE_STATES) or civ.grievances >= 20
        ratio = civ.military_strength / my_mil
        if hostile and ratio >= 1.5:
            border = [c.name for c in sit.cities if _threatened_by(sit, c, civ.player_id)]
            where = f"，{'、'.join(border[:2])} 附近已经有他们的兵" if border else ""
            yield Finding(
                Priority.HIGH if border or ratio >= 2.5 else Priority.MEDIUM,
                "外交",
                f"{civ.civ_name} 关系差、军力是你的 {ratio:.1f} 倍",
                f"对方军力 {civ.military_strength}，你 {my_mil}（游戏统计）{where}。AI 看到你兵少更容易宣战。",
                "边境城先造城墙；补两三个当代主力单位或升级旧单位；军事槽插「堡垒」(城防 +6)；"
                "也可以送点东西改善关系、和对方的敌人结盟。",
            )


def _threatened_by(sit: Situation, city, owner_id: int) -> bool:
    from civ6_advisor.geo import hex_distance

    return any(getattr(t, "owner_id", -1) == owner_id and hex_distance(city.x, city.y, t.x, t.y) <= 6
               for t in sit.threats)


@rule
def war_balance(sit: Situation):
    my_mil, same = my_military(sit)
    for civ in sit.diplomacy:
        if not civ.is_at_war or not civ.military_strength:
            continue
        ratio = civ.military_strength / max(my_mil, 1)
        if ratio > 1.3:
            yield Finding(
                Priority.URGENT,
                "外交",
                f"正在与 {civ.civ_name} 交战，对方军力明显占优",
                f"对方军力约 {civ.military_strength}，我方{'约 ' if same else '单位战力合计约 '}{my_mil}。",
                "转入防守，城市优先造城墙和远程单位；如果对方接受，尽早求和。",
            )
        else:
            yield Finding(
                Priority.MEDIUM,
                "外交",
                f"正在与 {civ.civ_name} 交战",
                f"对方军力约 {civ.military_strength}，我方{'约 ' if same else '单位战力合计约 '}{my_mil}。",
                "兵力不吃亏，可以考虑集中兵力拿下对方边境城市。",
            )


@rule
def wounded_units(sit: Situation):
    hostile = _hostile_ids(sit)
    enemy_pos = [(t.x, t.y) for t in sit.threats if t.owner_id in hostile]
    for u in sit.units:
        if u.combat_strength == 0 and u.ranged_strength == 0:
            continue
        if u.max_health and u.health / u.max_health < 0.4:
            in_danger = any(hex_distance(u.x, u.y, x, y) <= 2 for x, y in enemy_pos)
            if in_danger:
                safe, d = nearest_city(sit.cities, u.x, u.y)
                plots = [Plot(u.x, u.y, "unit", u.name)]
                action = "撤回后方回血，别让它白白被杀。"
                if safe is not None:
                    plots.append(Plot(safe.x, safe.y, "move", f"撤到{safe.name}"))
                    action = f"撤回 {safe.name}（{d} 格）回血，别让它白白被杀。"
                yield Finding(
                    Priority.HIGH,
                    "单位",
                    f"{u.name} 残血且身边有敌人",
                    f"血量 {u.health}/{u.max_health}，在{describe_sit(sit, u.x, u.y)}。",
                    action,
                    plots=plots,
                )


@rule
def promotions_upgrades(sit: Situation):
    promo = [u.name for u in sit.units if u.needs_promotion]
    if promo:
        wounded = [u.name for u in sit.units if u.needs_promotion and u.health < u.max_health * 0.6]
        yield Finding(
            Priority.MEDIUM if wounded else Priority.LOW,
            "单位",
            f"{len(promo)} 个单位可以晋升" + ("（有残血的，晋升能回血）" if wounded else ""),
            "、".join(promo[:6]) + ("等" if len(promo) > 6 else ""),
            "晋升会回满血，残血单位尤其应该先晋升。",
        )
    gold = sit.overview.gold
    ups = [u for u in sit.units if u.can_upgrade and u.upgrade_cost and u.upgrade_cost <= gold]
    if ups:
        by_target: dict[str, int] = defaultdict(int)
        for u in ups:
            by_target[f"{u.name}→{u.upgrade_target}"] += 1
        yield Finding(
            Priority.LOW,
            "单位",
            f"{len(ups)} 个单位现在买得起升级",
            "、".join(f"{k}×{v}" if v > 1 else k for k, v in by_target.items()),
            "打仗或备战时优先升级前线单位。",
        )
