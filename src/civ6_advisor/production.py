"""城市生产：识别首都、每座城在造什么，空闲时按局势和文明推荐造什么，并检查全国的生产缺口。

推荐候选（按局势打分）：开拓者、建造者、军事单位、古城墙、侦察兵、纪念碑、粮仓、专业区。
如果读到了该城的可生产列表，只推荐真正能造的项目，并使用游戏给的回合数。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from civ6_advisor.civs import ResolvedProfile, profile_for
from civ6_advisor.game import Situation
from civ6_advisor.geo import hex_distance
from civ6_advisor.names import is_idle, production_cn
from civ6_advisor.rules.base import game_phase

# 军事单位按时代从强到弱的偏好（选能造的里面最靠前的）
MILITARY_PREF = (
    "UNIT_INFANTRY", "UNIT_LINE_INFANTRY", "UNIT_MUSKETMAN", "UNIT_PIKE_AND_SHOT", "UNIT_CROSSBOWMAN",
    "UNIT_MAN_AT_ARMS", "UNIT_PIKEMAN", "UNIT_SWORDSMAN", "UNIT_ARCHER", "UNIT_SPEARMAN", "UNIT_SLINGER",
    "UNIT_WARRIOR",
)
FOCUS_DISTRICT = {
    "科技": "DISTRICT_CAMPUS", "文化": "DISTRICT_THEATER", "宗教": "DISTRICT_HOLY_SITE",
    "金币": "DISTRICT_COMMERCIAL_HUB", "外交": "DISTRICT_COMMERCIAL_HUB", "奇观": "DISTRICT_THEATER",
    "征服": "DISTRICT_ENCAMPMENT", "海洋": "DISTRICT_HARBOR", "扩张": "DISTRICT_COMMERCIAL_HUB",
    "人口": "DISTRICT_CAMPUS",
}
# 特色区域替代的通用区域
UNIQUE_DISTRICT_OF = {
    "DISTRICT_SEOWON": "DISTRICT_CAMPUS", "DISTRICT_OBSERVATORY": "DISTRICT_CAMPUS",
    "DISTRICT_ACROPOLIS": "DISTRICT_THEATER", "DISTRICT_LAVRA": "DISTRICT_HOLY_SITE",
    "DISTRICT_SUGUBA": "DISTRICT_COMMERCIAL_HUB", "DISTRICT_HANSA": "DISTRICT_INDUSTRIAL_ZONE",
    "DISTRICT_OPPIDUM": "DISTRICT_INDUSTRIAL_ZONE", "DISTRICT_IKANDA": "DISTRICT_ENCAMPMENT",
    "DISTRICT_THANH": "DISTRICT_ENCAMPMENT", "DISTRICT_ROYAL_NAVY_DOCKYARD": "DISTRICT_HARBOR",
    "DISTRICT_COTHON": "DISTRICT_HARBOR", "DISTRICT_STREET_CARNIVAL": "DISTRICT_ENTERTAINMENT_COMPLEX",
    "DISTRICT_HIPPODROME": "DISTRICT_ENTERTAINMENT_COMPLEX", "DISTRICT_MBANZA": "DISTRICT_NEIGHBORHOOD",
    "DISTRICT_BATH": "DISTRICT_AQUEDUCT", "DISTRICT_ORDU": "DISTRICT_ENCAMPMENT",
}


@dataclass
class Suggestion:
    item: str  # 类型名，如 UNIT_SETTLER
    name: str  # 中文名
    turns: int
    score: float
    reasons: list[str] = field(default_factory=list)


@dataclass
class CityProd:
    city: object  # CityInfo
    is_capital: bool
    building: str  # 中文名；空闲为 ""
    turns_left: int
    idle: bool
    picks: list[Suggestion] = field(default_factory=list)  # 只有空闲城市才有


def is_capital(city) -> bool:
    return any(b.upper().removeprefix("BUILDING_") == "PALACE" for b in (city.buildings or []))


def _has_district(city, generic: str) -> bool:
    for d in city.districts or []:
        d = d.upper()
        if not d.startswith("DISTRICT_"):
            d = "DISTRICT_" + d
        if d == generic or UNIQUE_DISTRICT_OF.get(d) == generic:
            return True
    return False


def _has_building(city, b: str) -> bool:
    return any(x.upper().removeprefix("BUILDING_") == b for x in (city.buildings or []))


def empire_status(sit: Situation) -> dict:
    """全国层面：已有/在造的开拓者、建造者，目标城市数。"""
    prof = profile_for(sit.civ.civ_type, sit.civ.leader_type) if sit.civ else None
    queued = [c.currently_building or "" for c in sit.cities]
    return {
        "prof": prof,
        "settlers": sum(1 for u in sit.units if "SETTLER" in u.unit_type.upper()),
        "settlers_queued": sum(1 for q in queued if q.upper() == "UNIT_SETTLER"),
        "builders": sum(1 for u in sit.units if u.build_charges > 0 or "BUILDER" in u.unit_type.upper()),
        "builders_queued": sum(1 for q in queued if q.upper() == "UNIT_BUILDER"),
        "target": _target(sit, prof),
        "phase": game_phase(sit),
    }


def _target(sit: Situation, prof) -> int:
    from civ6_advisor.playstyles import active

    ps = active(sit)
    if ps and ps.expand:
        return ps.expand
    return prof.expand if prof else 5


def _threatened(sit: Situation, city) -> bool:
    hostile = {63} | {c.player_id for c in sit.diplomacy if c.is_at_war}
    return any(t.owner_id in hostile and hex_distance(city.x, city.y, t.x, t.y) <= 4 for t in sit.threats)


def suggest_for_city(sit: Situation, city, st: dict | None = None) -> list[Suggestion]:
    st = st or empire_status(sit)
    prof: ResolvedProfile | None = st["prof"]
    phase = st["phase"]
    opts = sit.production_options.get(city.city_id) if sit.production_options else None
    avail = {o.item_name: o for o in opts} if opts else None
    cands: dict[str, Suggestion] = {}

    def add(item: str, score: float, why: str):
        if avail is not None and item not in avail:
            return
        turns = avail[item].turns if avail is not None else 0
        s = cands.setdefault(item, Suggestion(item, production_cn(item), turns, 0.0))
        s.score += score
        s.reasons.append(why)

    capital = is_capital(city)
    n_cities = len(sit.cities)
    threatened = _threatened(sit, city)

    # 开拓者
    going = n_cities + st["settlers"] + st["settlers_queued"]
    if phase in ("开局", "前期") and going < st["target"] and city.population >= 2:
        who = f"{prof.name}前期目标约 {st['target']} 座城" if prof else f"前期目标约 {st['target']} 座城"
        add("UNIT_SETTLER", 50 + (10 if capital else 0), f"现有+在路上 {going} 座，{who}")
        from civ6_advisor.rules.rivals import city_benchmark

        bench = city_benchmark(sit.overview.turn)
        if going < bench:
            add("UNIT_SETTLER", 10, f"第 {sit.overview.turn} 回合一般该有约 {bench} 座城，落后了")
        t = avail["UNIT_SETTLER"].turns if avail is not None and "UNIT_SETTLER" in avail else 0
        if t and t <= 12:
            add("UNIT_SETTLER", 6, f"只要 {t} 回合（12 回合内能出就值得造）")
        elif t and t > 15:
            add("UNIT_SETTLER", -12, f"要 {t} 回合太慢，最好用金币买或者先长人口/产能")
    # 建造者
    if sit.facts is not None:
        unimproved = len(sit.facts.improvable_now)  # 只算现在就能改良的（共同事实）
        blocked = len(sit.facts.blocked)
    else:
        unimproved = sum(len(c.unimproved_resources) for c in sit.cities)
        blocked = 0
    if st["builders"] + st["builders_queued"] == 0:
        if unimproved:
            add("UNIT_BUILDER", 45, f"全国没有建造者，有 {unimproved} 处资源现在就能改良")
        else:
            add("UNIT_BUILDER", 25, "全国没有建造者" + ("（资源还缺科技，先种田/砍树）" if blocked else ""))
        if prof and prof.leader and "建造者" in prof.leader.tip:
            add("UNIT_BUILDER", 10, f"{prof.leader.name}的建造者更强")
    # 防御
    if threatened or not city.garrison_unit and phase == "开局" and capital and n_cities == 1:
        early = sit.overview.turn <= 30 and not threatened and (avail is None or "UNIT_SLINGER" in avail)
        mil = "UNIT_SLINGER" if early else next((u for u in MILITARY_PREF if avail is None or u in avail), "UNIT_WARRIOR")
        add(mil, 75 if threatened else 20, "附近有敌军" if threatened else
            "首都还没有驻军，防蛮族" + ("；投石兵击杀单位还能触发弓术尤里卡" if mil == "UNIT_SLINGER" else ""))
    if threatened and city.wall_max_hp == 0 and city.population >= 2:
        add("BUILDING_WALLS", 35, "附近有敌军，城里还没有城墙")
    # 侦察
    o = sit.overview
    scouts = sum(1 for u in sit.units if "SCOUT" in u.unit_type.upper())
    explored = o.explored_land / o.total_land if o.total_land else 1
    if o.turn <= 25 and scouts == 0 and explored < 0.15 and capital:
        add("UNIT_SCOUT", 30, "还没有侦察兵，早探索能拿部落村庄和首次遇见的时代分")
    # 纪念碑
    if not _has_building(city, "MONUMENT") and phase in ("开局", "前期"):
        low = o.culture_yield < 5 and o.turn < 45
        add("BUILDING_MONUMENT", 24 if low else 16,
            "还没有纪念碑" + (f"：文化只有 {o.culture_yield:.0f}/回合，前 35 回合最好有两座纪念碑（政策和政体靠它）" if low
                          else "，早期文化和忠诚的主要来源"))
    # 商人：有了对外贸易、商路空着
    traders = sum(1 for u in sit.units if "TRADER" in u.unit_type.upper()) + \
        sum(1 for c in sit.cities if (c.currently_building or "").upper() == "UNIT_TRADER")
    if (sit.facts is not None and "CIVIC_FOREIGN_TRADE" in sit.facts.civics and traders == 0
            and o.turn > 20 and not threatened and city.population >= 3):
        add("UNIT_TRADER", 24 if capital else 14, "已有对外贸易但没有商人：国内商路给新城送粮锤，还顺路修路")
    # 粮仓
    if city.housing and city.population >= city.housing - 1 and not _has_building(city, "GRANARY"):
        add("BUILDING_GRANARY", 22, "住房快满了")
    # 专业区
    if city.population >= 3 and prof:
        for i, f in enumerate(prof.focus[:2]):
            d = FOCUS_DISTRICT.get(f)
            if not d or _has_district(city, d):
                continue
            # 特色区域：能造的列表里有它的替代版就用替代版
            unique = next((u for u, g in UNIQUE_DISTRICT_OF.items() if g == d and avail is not None and u in avail), None)
            if prof.religion == "必需" and d == "DISTRICT_HOLY_SITE" and o.our_religion:
                continue
            add(unique or d, (28, 20)[i], f"{prof.name}擅长{f}")
    if city.population >= 3 and not prof and not any(_has_district(city, d) for d in ("DISTRICT_CAMPUS", "DISTRICT_COMMERCIAL_HUB")):
        add("DISTRICT_CAMPUS", 20, "人口够了还没有专业区")
    # 宗教：需要宗教的文明，全国还没有圣地
    if prof and prof.religion == "必需" and not o.our_religion and not any(_has_district(c, "DISTRICT_HOLY_SITE") for c in sit.cities):
        unique = next((u for u, g in UNIQUE_DISTRICT_OF.items() if g == "DISTRICT_HOLY_SITE" and avail is not None and u in avail), None)
        add(unique or "DISTRICT_HOLY_SITE", 40, f"{prof.name}需要宗教，全国还没有圣地")
    # 流派：路线上的生产项加分（威胁时不加，安全第一）
    _style_prod(sit, city, add, avail, threatened)
    # 马里/葡萄牙：建筑靠买，锤子用来出单位和区域
    if prof and prof.has("gold_buy"):
        for s in cands.values():
            if s.item.startswith("BUILDING_"):
                s.score -= 15
                s.reasons.append(f"{prof.name}手造建筑吃亏，最好用钱买")
    out = sorted(cands.values(), key=lambda s: (-s.score, s.turns or 99))
    for s in out:
        s.reasons = list(dict.fromkeys(s.reasons))
    return out


def _has_cn(item: str) -> bool:
    n = production_cn(item)
    return bool(n) and not n.isascii()


def _style_prod(sit: Situation, city, add, avail, threatened: bool):
    from civ6_advisor.playstyles import active, progress

    ps = active(sit)
    if not ps or threatened:
        return
    for item, (pts, why) in ps.prod.items():
        if item.startswith("DISTRICT_"):
            if _has_district(city, item):
                continue
            unique = next((u for u, g in UNIQUE_DISTRICT_OF.items() if g == item and avail is not None and u in avail), None)
            add(unique or item, pts, f"「{ps.name}」：{why}")
        elif avail is not None or _has_cn(item):  # 读不到可造列表时，只推荐有中文名的通用项
            if item.startswith("BUILDING_") and _has_building(city, item.removeprefix("BUILDING_")):
                continue
            add(item, pts, f"「{ps.name}」：{why}")
    # 下一个里程碑是区域/单位时额外加分
    pr = progress(ps, sit)
    st = pr.next
    if st and st.cond[0] == "district" and not _has_district(city, st.cond[1]) and city.population >= 2:
        unique = next((u for u, g in UNIQUE_DISTRICT_OF.items() if g == st.cond[1] and avail is not None and u in avail), None)
        add(unique or st.cond[1], 25 if st in pr.late else 15, f"流派下一步：{st.text}")
    if st and st.cond[0] == "cities" and city.population >= 2:
        add("UNIT_SETTLER", 15, f"流派下一步：{st.text}")


def city_overview(sit: Situation) -> list[CityProd]:
    """所有城市的生产状态，首都排第一。"""
    st = empire_status(sit)
    rows = []
    for c in sit.cities:
        idle = is_idle(c.currently_building)
        rows.append(CityProd(
            city=c, is_capital=is_capital(c), building=production_cn(c.currently_building),
            turns_left=c.production_turns_left, idle=idle,
            picks=suggest_for_city(sit, c, st) if idle else [],
        ))
    rows.sort(key=lambda r: (not r.is_capital, not r.idle))
    return rows


ADJ_CN = {"science": "科研", "culture": "文化", "faith": "信仰", "gold": "金币", "production": "生产力", "food": "食物"}


def district_spot_text(sit: Situation, city, item: str) -> tuple[str, list]:
    """区域最佳地块的说明和要标的格子。"""
    from civ6_advisor.geo import Plot, describe

    spot = sit.district_spots.get(city.city_id) if sit.district_spots else None
    if not spot or spot[0] != item or not spot[1]:
        return "", []
    best = spot[1][0]
    adj = "、".join(f"{ADJ_CN.get(k, k)} +{v}" for k, v in best.adjacency.items() if v) or "无相邻加成"
    where = describe(sit.cities, best.x, best.y)
    text = f"最佳位置：{where}（{best.terrain_desc}，{adj}）"
    if len(spot[1]) > 1:
        alt = spot[1][1]
        text += f"；次选相邻 +{alt.total_adjacency}"
    plots = [Plot(p.x, p.y, "district", f"{production_cn(item)} +{p.total_adjacency}") for p in spot[1]]
    return text, plots


def suggestion_text(picks: list[Suggestion], n: int = 3) -> str:
    if not picks:
        return "挑一个符合当前路线的项目，别让锤子空转。"
    top = picks[0]
    s = f"推荐 {top.name}" + (f"（{top.turns} 回合）" if top.turns > 0 else "") + "：" + "；".join(top.reasons[:2])
    alts = "、".join(p.name for p in picks[1:n])
    return s + (f"。备选：{alts}" if alts else "")
