"""具体决策：政策卡怎么插、万神殿选哪个、总督给谁放哪、使者派给谁、金币买什么、尤里卡要不要等。

目标是"实在"：每条建议都点名具体的卡/信仰/总督/城邦/城市和数字，而不是"记得用政策卡"。
经验规则整理自社区攻略（CivFanatics 的开局与政策讨论、theahura《On Towards the Stars》、
Comrade Kaine 的万神殿指南、游民星空/文明6吧的过神思路），数值是主观权重，可以按需调整。
"""

from __future__ import annotations

from civ6_advisor.civs import profile_for
from civ6_advisor.game import Situation
from civ6_advisor.names import production_cn, type_name


def _has_district(city, generic):  # 延迟导入，避免 production ↔ rules 循环导入
    from civ6_advisor.production import _has_district as f

    return f(city, generic)


def _threatened(sit, city):
    from civ6_advisor.production import _threatened as f

    return f(sit, city)


def empire_status(sit):
    from civ6_advisor.production import empire_status as f

    return f(sit)

from civ6_advisor.rules.base import Finding, Priority, game_phase, rule

BARB = 63

# ------------------------------------------------------------------ 公共小工具


def _focus(sit: Situation) -> tuple[str, ...]:
    prof = profile_for(sit.civ.civ_type, sit.civ.leader_type) if sit.civ else None
    return prof.focus if prof else ()


def _building(sit: Situation, *keys: str) -> list:
    """正在生产名字里含这些关键字的城市。"""
    return [c for c in sit.cities if any(k in (c.currently_building or "").upper() for k in keys)]


def _count_district(sit: Situation, generic: str) -> int:
    return sum(1 for c in sit.cities if _has_district(c, generic))


def _barb_near(sit: Situation) -> bool:
    return any(getattr(t, "owner_id", -1) == BARB or "BARBARIAN" in t.unit_type.upper() for t in sit.threats)


def _at_war(sit: Situation) -> bool:
    return any(c.is_at_war for c in sit.diplomacy)


def _need_settlers(sit: Situation) -> bool:
    st = empire_status(sit)
    return len(sit.cities) + st["settlers"] + st["settlers_queued"] < st["target"]


MELEE_RANGED = ("WARRIOR", "SLINGER", "ARCHER", "SPEARMAN", "SWORDSMAN", "PIKEMAN", "CROSSBOW", "LEGION",
                "HOPLITE", "IMMORTAL", "PITATI", "EAGLE", "IMPI", "SAMURAI", "BERSERKER", "MUSKETMAN", "SCOUT")
CAVALRY = ("HORSEMAN", "HEAVY_CHARIOT", "CHARIOT", "KNIGHT", "HORSE_ARCHER", "SAKA", "WAR_CART", "COURSER",
           "CAVALRY", "MAMLUK", "HETAIROI", "COMPANION")
NAVAL = ("GALLEY", "BIREME", "TRIREME", "QUADRIREME", "CARAVEL", "FRIGATE", "LONGSHIP", "PRIVATEER")
EARLY_WONDERS = ("PYRAMIDS", "HANGING_GARDENS", "STONEHENGE", "ORACLE", "TEMPLE_ARTEMIS", "GREAT_BATH",
                 "ETEMENANKI", "COLOSSUS", "GREAT_LIGHTHOUSE", "PETRA", "TERRACOTTA_ARMY", "COLOSSEUM",
                 "GREAT_LIBRARY", "MAHABODHI_TEMPLE", "APADANA", "JEBEL_BARKAL", "MAUSOLEUM_AT_HALICARNASSUS")


def _swap_timing(sit: Situation) -> tuple[str, bool]:
    """换政策的时机：完成市政那回合免费换。返回 (说明, 是否马上就能免费换)。"""
    t = sit.tech
    if not t or not t.current_civic or t.current_civic in ("None", "NONE"):
        return "现在没有在推市政：选一个市政，完成那回合可以免费换卡", False
    n = t.current_civic_turns
    if n is not None and 0 < n <= 1:
        return f"下回合「{t.current_civic}」完成时免费换", True
    return f"约 {n} 回合后「{t.current_civic}」完成时免费换（现在换要花金币）", False


# ------------------------------------------------------------------ 政策卡


def _policy_score(sit: Situation, ptype: str) -> tuple[float, str]:
    """一张政策卡在当前局势下的价值和理由。不认识的卡返回 (0, "")。"""
    p = ptype.upper().removeprefix("POLICY_")
    turn = sit.overview.turn
    focus = _focus(sit)
    pan = sit.pantheon
    has_pantheon = bool(pan and pan.has_pantheon) or bool(sit.overview.our_religion)
    builders = _building(sit, "BUILDER")
    settlers = _building(sit, "SETTLER")
    units = sum(1 for u in sit.units if u.combat_strength > 0 or u.ranged_strength > 0)

    def n(lst):
        return len(lst)

    if p == "GOD_KING":
        faith = (pan.faith_balance if pan and pan.faith_balance is not None else sit.overview.faith) or 0
        if not has_pantheon and faith >= PANTHEON_COST:
            return 4, "信仰已经够选万神殿了，先去选万神殿，这张卡用处不大"
        if not has_pantheon:
            return 30, "还没有万神殿：+1 信仰让万神殿早几回合到手"
        return 0, "已经有万神殿，这张卡可以换掉"
    if p == "URBAN_PLANNING":
        return (22 if turn < 90 else 8), "每座城 +1 生产力，前期最通用"
    if p == "ILKUM":
        return (38 if builders else 6), (f"{n(builders)} 座城在造建造者：建造者 +30% 生产力" if builders else "造建造者时才有用")
    if p == "COLONIZATION":
        if settlers:
            return 42, f"{n(settlers)} 座城在造开拓者：开拓者 +50% 生产力"
        return (14 if _need_settlers(sit) else 3), "还要继续铺城时，配合造开拓者用"
    if p == "CORVEE":
        w = _building(sit, *EARLY_WONDERS)
        return (36 if w else 2), (f"{w[0].name} 在造古代/古典奇观：+15% 生产力" if w else "只对远古/古典奇观有用")
    if p == "LAND_SURVEYORS":
        return 4, "买地块便宜，钱多时才值得"
    if p == "CARAVANSARIES":
        traders = sum(1 for u in sit.units if "TRADER" in u.unit_type.upper())
        return (8 + 6 * traders if traders >= 2 else 2), f"每条商路 +2 金币（现有 {traders} 个商人）"
    if p == "DISCIPLINE":
        return (30 if _barb_near(sit) else (14 if turn < 40 else 3)), ("附近有蛮族：打蛮族 +5 战斗力" if _barb_near(sit) else "打蛮族 +5，清营地时用")
    if p == "SURVEY":
        scouts = sum(1 for u in sit.units if "SCOUT" in u.unit_type.upper())
        return (16 if scouts and turn < 40 else 2), "侦察单位经验翻倍，开局探路时用"
    if p == "AGOGE":
        mil = _building(sit, *MELEE_RANGED)
        if mil:
            return 36, f"{n(mil)} 座城在造近战/远程单位：+50% 生产力"
        return (16 if _threatened_any(sit) or _at_war(sit) else 5), "要出近战/远程单位时用"
    if p == "MANEUVER":
        cav = _building(sit, *CAVALRY)
        return (36 if cav else 4), (f"{n(cav)} 座城在造骑兵：+50% 生产力" if cav else "造骑兵时才有用")
    if p == "MARITIME_INDUSTRIES":
        nav = _building(sit, *NAVAL)
        return (32 if nav else 3), ("在造古典/远古海军：+100% 生产力" if nav else "造远古/古典海军时用")
    if p == "CONSCRIPTION":
        return (20 if units >= 6 else 6) + (8 if _at_war(sit) else 0), f"每个单位维护费 -1（现有 {units} 个军事单位）"
    if p == "LIMITANEI":
        return (20 if _loyalty_trouble(sit) else 4), "有驻军的城 +2 忠诚"
    if p == "VETERANCY":
        e = _building(sit, "ENCAMPMENT", "HARBOR", "BARRACKS", "STABLE", "LIGHTHOUSE")
        return (26 if e else 4), "军营/港口和里面的建筑 +30% 生产力"
    if p == "BASTIONS":
        return (24 if _threatened_any(sit) else 4), "城防 +6、城市远程攻击 +5"
    if p == "RETAINERS":
        return (16 if _amenity_trouble(sit) else 3), "有驻军的城 +1 宜居"
    if p in ("FEUDAL_CONTRACT",):
        mil = _building(sit, *MELEE_RANGED)
        return (30 if mil else 4), "近战/远程/反骑兵 +50% 生产力"
    if p == "SERFDOM":
        return (34 if builders else 8), "新建造者 +2 次数"
    if p == "PUBLIC_WORKS":
        return (30 if builders else 6), "建造者 +30% 生产力、+2 次数"
    if p == "NATURAL_PHILOSOPHY":
        k = _count_district(sit, "DISTRICT_CAMPUS")
        return (8 + 6 * k if k else 0), f"学院区相邻加成 +100%（有 {k} 座学院区）"
    if p == "SCRIPTURE":
        k = _count_district(sit, "DISTRICT_HOLY_SITE")
        return (6 + 6 * k if k else 0), f"圣地相邻加成 +100%（有 {k} 座圣地）"
    if p == "AESTHETICS":
        k = _count_district(sit, "DISTRICT_THEATER")
        return (6 + 6 * k if k else 0), f"剧院广场相邻加成 +100%（有 {k} 座剧院）"
    if p == "TOWN_CHARTERS":
        k = _count_district(sit, "DISTRICT_COMMERCIAL_HUB")
        return (6 + 6 * k if k else 0), f"商业中心相邻加成 +100%（有 {k} 座商业中心）"
    if p == "INSULAE":
        k = sum(1 for c in sit.cities if c.housing and c.population >= c.housing - 1)
        return (10 + 6 * k if k else 3), f"住房 +1（{k} 座城住房满了）"
    if p == "MEDINA_QUARTER":
        k = sum(1 for c in sit.cities if c.housing and c.population >= c.housing - 1)
        return (12 + 6 * k if k else 3), f"有 3 个以上专业区域的城住房 +2（{k} 座城住房满了）"
    if p == "CHARISMATIC_LEADER":
        return 15, "每回合 +2 影响力，更快拿使者"
    if p == "DIPLOMATIC_LEAGUE":
        return 10, "给每个城邦派的第一个使者额外 +1"
    if p == "MERCHANT_CONFEDERATION":
        suz = sum(1 for cs in (sit.envoys.city_states if sit.envoys else []) if cs.envoys_sent >= 3)
        return (6 + 4 * suz if suz else 2), f"每个城邦使者 +1 金币"
    if p == "REVELATION":
        prof = profile_for(sit.civ.civ_type, sit.civ.leader_type) if sit.civ else None
        want = prof and prof.religion in ("必需", "保底") and not sit.overview.our_religion
        return (30 if want else 3), "伟大先知点 +2，抢宗教用"
    if p == "INSPIRATION":
        return (12 if "科技" in focus else 5), "伟大科学家点 +2"
    if p == "STRATEGOS":
        return (10 if "征服" in focus else 3), "伟大将军点 +2"
    if p == "RATIONALISM":
        k = _count_district(sit, "DISTRICT_CAMPUS")
        return (5 + 4 * k if k >= 2 else 2), "学院区建筑科研 +50%（城市人口高时更多）"
    if p == "FREE_MARKET":
        k = _count_district(sit, "DISTRICT_COMMERCIAL_HUB")
        return (5 + 4 * k if k >= 2 else 2), "商业中心建筑金币 +50%"
    if p == "GRAND_OPERA":
        k = _count_district(sit, "DISTRICT_THEATER")
        return (5 + 4 * k if k >= 2 else 2), "剧院广场建筑文化 +50%"
    if p == "GOTHIC_ARCHITECTURE":
        return 3, "中世纪/文艺复兴奇观加速"
    return 0, ""


def _threatened_any(sit: Situation) -> bool:
    return any(_threatened(sit, c) for c in sit.cities)


def _loyalty_trouble(sit: Situation) -> bool:
    return any((getattr(c, "loyalty_per_turn", 0) or 0) < 0 for c in sit.cities)


def _amenity_trouble(sit: Situation) -> bool:
    return any(c.amenities < 0 for c in sit.cities)


SLOT_CN = {"SLOT_MILITARY": "军事", "SLOT_ECONOMIC": "经济", "SLOT_DIPLOMATIC": "外交", "SLOT_WILDCARD": "通配",
           "SLOT_GREAT_PERSON": "伟人"}
WILD_OK = {"SLOT_MILITARY", "SLOT_ECONOMIC", "SLOT_DIPLOMATIC", "SLOT_WILDCARD", "SLOT_GREAT_PERSON"}


def plan_policies(sit: Situation) -> list[dict]:
    """每个政策槽推荐放什么。返回 [{slot, current, current_score, best, best_score, reason}]。"""
    g = sit.government
    if not g or not g.slots:
        return []
    cards: dict[str, tuple] = {}
    for p in g.available_policies or []:
        cards[p.policy_type] = (p, *_policy_score(sit, p.policy_type))
    # 已经插着的卡可能不在"可用"列表里，补上分数
    cur_score = {s.current_policy: _policy_score(sit, s.current_policy)[0] for s in g.slots if s.current_policy}
    taken: set[str] = set()
    out = []
    # 先填专用槽，再填通配槽（通配槽能插任何卡，留到最后挑剩下最好的）
    order = sorted(g.slots, key=lambda s: s.slot_type == "SLOT_WILDCARD")
    for s in order:
        fits = [(sc, why, p) for t, (p, sc, why) in cards.items() if t not in taken and
                (p.slot_type == s.slot_type or (s.slot_type == "SLOT_WILDCARD" and p.slot_type in WILD_OK))]
        fits.sort(key=lambda x: -x[0])
        best = fits[0] if fits else None
        cur = s.current_policy
        cur_sc = cur_score.get(cur, 0) if cur else -1
        # 现在这张卡也算候选：比它好得不多就别折腾
        if best and cur and best[2].policy_type != cur and best[0] - cur_sc < 12:
            best = None
        if best:
            taken.add(best[2].policy_type)
        elif cur:
            taken.add(cur)
        out.append({"slot": s, "current": cur, "current_name": getattr(s, "current_policy_name", None) or cur,
                    "current_score": cur_sc, "best": best[2] if best else None,
                    "best_score": best[0] if best else None, "reason": best[1] if best else ""})
    return out


@rule
def policy_advice(sit: Situation):
    plan = plan_policies(sit)
    if not plan:
        return
    empty = [x for x in plan if not x["current"] and x["best"]]
    swaps = [x for x in plan if x["current"] and x["best"] and x["best"].policy_type != x["current"]]
    timing, free_now = _swap_timing(sit)
    def why(x):
        if (x["best_score"] or 0) < 8:  # 空着不如插一张，哪怕作用不大
            eff = (x["best"].description or "").strip()[:30]
            return "暂时没有更合适的，先插上" + (f"：{eff}" if eff else "")
        return x["reason"]

    if empty:
        desc = "；".join(f"{SLOT_CN.get(x['slot'].slot_type, '')}槽 → {x['best'].name}（{why(x)}）" for x in empty)
        yield Finding(Priority.HIGH, "科技文化", f"政策：{len(empty)} 个空槽这样插", desc + "。",
                      "空槽现在就可以免费插卡（政府界面）。" if not swaps else f"空槽现在就插；其他调整：{timing}。")
    if swaps:
        desc = "；".join(
            f"{SLOT_CN.get(x['slot'].slot_type, '')}槽 {type_name(x['current'], sit) if x['current'] else ''}"
            f" → {x['best'].name}（{x['reason']}）" for x in swaps)
        yield Finding(Priority.MEDIUM if free_now else Priority.LOW, "科技文化",
                      "政策：建议换卡" + ("（下回合免费）" if free_now else ""), desc + "。", timing + "。")


# ------------------------------------------------------------------ 万神殿

PANTHEON_COST = 25  # 标准速度


def _pantheon_score(sit: Situation, btype: str) -> tuple[float, str]:
    f = sit.facts
    t = (lambda *k: f.count(*k)) if f is not None else (lambda *k: 0)
    civ = sit.civ.civ_type if sit.civ else ""
    focus = _focus(sit)
    b = btype.upper().removeprefix("BELIEF_")
    if b == "RELIGIOUS_SETTLEMENTS":
        return (22 + (10 if _need_settlers(sit) else 0)), "送一个开拓者 + 边界扩张更快，还要铺城时最稳"
    if b == "GOD_OF_THE_FORGE":
        war = _at_war(sit) or _threatened_any(sit) or "征服" in focus
        return (18 + (16 if war else 0)), "远古/古典军事单位 +25% 生产力" + ("，正好要打仗" if war else "")
    if b == "MONUMENT_TO_THE_GODS":
        w = bool(_building(sit, *EARLY_WONDERS)) or civ in ("CIVILIZATION_CHINA", "CIVILIZATION_EGYPT", "CIVILIZATION_FRANCE")
        return (14 + (16 if w else 0)), "远古/古典奇观 +15% 生产力" + ("，你在冲奇观" if w else "")
    if b == "DANCE_OF_THE_AURORA":
        n = t("TERRAIN_TUNDRA", "TERRAIN_TUNDRA_HILLS")
        bonus = 10 if civ in ("CIVILIZATION_RUSSIA", "CIVILIZATION_CANADA") else 0
        return (8 + 5 * n + bonus if n >= 3 else 4), f"圣地每相邻冻土 +1 信仰（周围冻土 {n} 格）"
    if b == "DESERT_FOLKLORE":
        n = t("TERRAIN_DESERT", "TERRAIN_DESERT_HILLS")
        bonus = 10 if civ in ("CIVILIZATION_MALI", "CIVILIZATION_EGYPT", "CIVILIZATION_NUBIA") else 0
        return (8 + 4 * n + bonus if n >= 4 else 4), f"圣地每相邻沙漠 +1 信仰（周围沙漠 {n} 格）"
    if b == "SACRED_PATH":
        n = t("FEATURE_JUNGLE")
        return (8 + 4 * n if n >= 4 else 4), f"圣地每相邻雨林 +1 信仰（周围雨林 {n} 格）"
    if b == "RIVER_GODDESS":
        n = t("RIVER")
        rel = "宗教" in focus
        return ((10 + n if n >= 6 else 6) + (6 if rel else 0)), f"挨河的圣地 +2 宜居 +2 住房（周围河流地块 {n} 个）"
    if b in ("GODDESS_OF_FESTIVALS", "ORAL_TRADITION"):
        n = t("RES_IMPROVEMENT_PLANTATION")
        return (10 + 4 * n if n >= 4 else 5), f"种植园加产出（周围种植园资源 {n} 个）"
    if b == "GOD_OF_THE_OPEN_SKY":
        n = t("RES_IMPROVEMENT_PASTURE")
        return (10 + 4 * n if n >= 4 else 5), f"牧场 +1 文化（周围牧场资源 {n} 个）"
    if b == "GODDESS_OF_THE_HUNT":
        n = t("RES_IMPROVEMENT_CAMP")
        return (10 + 3 * n if n >= 5 else 4), f"营地 +1 粮 +1 锤（周围营地资源 {n} 个）"
    if b in ("FIRE_GODDESS", "GODDESS_OF_FIRE"):
        n = t("FEATURE_VOLCANO", "FEATURE_GEOTHERMAL_FISSURE")
        return (8 + 5 * n if n >= 2 else 2), f"火山土/地热 +信仰（周围 {n} 处）"
    if b == "LADY_OF_THE_REEDS_AND_MARSHES":
        n = t("FEATURE_MARSH", "FEATURE_OASIS", "FEATURE_FLOODPLAINS", "FEATURE_FLOODPLAINS_GRASSLAND",
              "FEATURE_FLOODPLAINS_PLAINS")
        return (8 + 4 * n if n >= 4 else 4), f"沼泽/绿洲/泛滥平原 +2 锤（周围 {n} 格）"
    if b == "RELIGIOUS_IDOLS":
        n = t("RES_IMPROVEMENT_MINE")
        return (8 + 3 * n if n >= 4 else 4), f"奢侈品/加成资源上的矿山 +2 信仰（周围可开矿资源 {n} 个）"
    if b == "GOD_OF_THE_SEA":
        n = t("RES_IMPROVEMENT_FISHING_BOATS")
        return (8 + 3 * n if n >= 3 else 3), f"渔船 +1 锤（周围海洋资源 {n} 个）"
    if b == "EARTH_GODDESS":
        n = t("BREATHTAKING")
        return (8 + 3 * n if n >= 4 else 4), f"惊艳魅力地块 +2 信仰（周围惊艳地块 {n} 个）"
    if b == "STONE_CIRCLES":
        n = t("RES_IMPROVEMENT_QUARRY")
        return (8 + 4 * n if n >= 3 else 3), f"采石场 +2 信仰（周围可建采石场资源 {n} 个）"
    if b == "DIVINE_SPARK":
        return 15, "伟人点 +1（哪种路线都能用的保底选择）"
    if b == "FERTILITY_RITES":
        return (12 + (4 if _need_settlers(sit) else 0)), "送一个建造者、城市成长 +10%"
    if b == "GOD_OF_CRAFTSMEN":
        n = t("RESOURCECLASS_STRATEGIC")
        return (6 + 3 * n if n >= 3 else 4), f"战略资源矿山加产出（周围战略资源 {n} 个）"
    if b == "CITY_PATRON_GODDESS":
        return 9, "小城建第一个区域 +25% 生产力"
    if b == "INITIATION_RITES":
        return 6, "清蛮族营地 +50 信仰"
    if b == "GOD_OF_WAR":
        return 4, "圣地附近击杀给信仰"
    if b == "GOD_OF_HEALING":
        return 3, "圣地附近单位回血更快"
    return 6, ""


@rule
def pantheon_advice(sit: Situation):
    pan = sit.pantheon
    if not pan or pan.has_pantheon or not pan.available_beliefs:
        return
    faith = pan.faith_balance if pan.faith_balance is not None else sit.overview.faith
    if faith < PANTHEON_COST * 0.6:
        return
    ranked = sorted(((*_pantheon_score(sit, b.belief_type), b) for b in pan.available_beliefs), key=lambda x: -x[0])
    best = ranked[0]
    alts = "、".join(f"{x[2].name}" for x in ranked[1:3])
    if faith >= PANTHEON_COST:
        yield Finding(Priority.HIGH, "宗教", f"现在就能选万神殿：{best[2].name}",
                      f"{best[1]}。备选：{alts}。万神殿先到先得，别人选走就没了。",
                      f"宗教界面选「{best[2].name}」。")
    else:
        yield Finding(Priority.LOW, "宗教", f"万神殿快攒够了（{faith:.0f}/{PANTHEON_COST}），打算选 {best[2].name}",
                      f"{best[1]}。备选：{alts}。", "攒够信仰后马上选，没有万神殿前可以插「君主崇拜」加速。")


# ------------------------------------------------------------------ 总督

GOV = {
    "GOVERNOR_THE_RESOURCE_MANAGER": "马格努斯", "GOVERNOR_THE_EDUCATOR": "平哥拉", "GOVERNOR_THE_BUILDER": "梁",
    "GOVERNOR_THE_AMBASSADOR": "阿玛尼", "GOVERNOR_THE_DEFENDER": "维克托", "GOVERNOR_THE_MERCHANT": "雷娜",
    "GOVERNOR_THE_CARDINAL": "莫克夏", "GOVERNOR_IBRAHIM": "易卜拉欣",
}
# 升级时优先的头衔（中英文名关键字都认）
GOOD_PROMOTIONS = {
    "GOVERNOR_THE_RESOURCE_MANAGER": ("供给", "Provision"),
    "GOVERNOR_THE_EDUCATOR": ("鉴赏家", "Connoisseur", "研究员", "Researcher", "资助", "Grants"),
    "GOVERNOR_THE_BUILDER": ("护城河", "Guildmaster", "行会", "Zoning", "分区"),
    "GOVERNOR_THE_AMBASSADOR": ("使节", "Emissary", "宗主", "Puppeteer"),
    "GOVERNOR_THE_DEFENDER": ("驻防", "Garrison", "要塞", "Embrasure"),
    "GOVERNOR_THE_MERCHANT": ("林业", "Forestry", "承包商", "Contractor"),
    "GOVERNOR_THE_CARDINAL": ("主教", "Bishop", "神圣建筑师", "Divine Architect"),
}


def _capital(sit: Situation):
    for c in sit.cities:
        if any(b.upper().removeprefix("BUILDING_") == "PALACE" for b in (c.buildings or [])):
            return c
    return sit.cities[0] if sit.cities else None


def _governor_plan(sit: Situation, gtype: str) -> tuple[float, str, object]:
    """(分数, 理由, 推荐城市)。"""
    from civ6_advisor.playstyles import active

    focus = _focus(sit)
    cap = _capital(sit)
    ps = active(sit)
    style_first = bool(ps and GOV.get(gtype, "?") and ps.governors.startswith(GOV.get(gtype, "?")))
    style_bonus = 18 if style_first else (6 if ps and GOV.get(gtype, "?") in ps.governors else 0)
    loyal = [c for c in sit.cities if (getattr(c, "loyalty_per_turn", 0) or 0) < 0]
    threat = [c for c in sit.cities if _threatened(sit, c)]
    if gtype == "GOVERNOR_THE_DEFENDER":
        if threat:
            return 40 + style_bonus, f"{threat[0].name} 附近有敌军：维克托就位后城防大增", threat[0]
        return 5 + style_bonus, "防守型，边境城用", cap
    if gtype == "GOVERNOR_THE_AMBASSADOR":
        if loyal:
            return 34 + style_bonus, f"{loyal[0].name} 忠诚在掉：阿玛尼放过去 +8 忠诚", loyal[0]
        return 12 + style_bonus + (8 if "外交" in focus else 0), "也可以派到城邦当宗主（时代分 + 宗主奖励）", None
    if gtype == "GOVERNOR_THE_RESOURCE_MANAGER":
        exp = _need_settlers(sit)
        return 24 + style_bonus + (12 if exp else 0), ("还要铺城：马格努斯砍树/采伐 +50%，升「供给」后出开拓者不掉人口"
                                                         if exp else "砍树/采伐产出 +50%，放在要砍树推区域的城"), cap
    if gtype == "GOVERNOR_THE_EDUCATOR":
        sc = "科技" in focus or "文化" in focus
        return 22 + style_bonus + (10 if sc else 0), "首都科研文化 +15%，升「鉴赏家」每人口 +1 文化（前期文化最缺）", cap
    if gtype == "GOVERNOR_THE_BUILDER":
        civ = sit.civ.civ_type if sit.civ else ""
        w = civ in ("CIVILIZATION_CHINA", "CIVILIZATION_EGYPT", "CIVILIZATION_FRANCE") or bool(_building(sit, *EARLY_WONDERS))
        return 12 + style_bonus + (14 if w else 0), "城里新建造者 +1 次数，建筑/区域加速" + ("，适合冲奇观" if w else ""), cap
    if gtype == "GOVERNOR_THE_MERCHANT":
        late = sit.overview.turn > 90
        return 8 + style_bonus + (10 if late else 0), "金币和商路型，中后期放商业中心多的城", cap
    if gtype == "GOVERNOR_THE_CARDINAL":
        rel = bool(sit.overview.our_religion)
        holy = next((c for c in sit.cities if _has_district(c, "DISTRICT_HOLY_SITE")), cap)
        return 6 + style_bonus + (18 if rel and "宗教" in focus else 0), "圣地信仰和传教加成，宗教路线用", holy
    if gtype == "GOVERNOR_IBRAHIM":
        return 10 + style_bonus + (25 if _at_war(sit) else 0), "打仗时攻城加成", threat[0] if threat else cap
    return 5, "", cap


@rule
def governor_advice(sit: Situation):
    g = sit.governors
    if not g:
        return
    if g.points_available > 0:
        pool = g.available_to_appoint
        if g.can_appoint and not pool:
            # 读不到可任命列表时，按没任命过的总督估算
            have = {a.governor_type for a in g.appointed}
            pool = [type("G", (), {"governor_type": t, "name": n})() for t, n in GOV.items()
                    if t not in have and t != "GOVERNOR_IBRAHIM"]
        if g.can_appoint and pool:
            ranked = sorted(((*_governor_plan(sit, x.governor_type), x) for x in pool), key=lambda r: -r[0])
            sc, why, city, info = ranked[0]
            name = GOV.get(info.governor_type, info.name)
            where = f"，放在{city.name}" if city is not None else ""
            alt = "、".join(GOV.get(r[3].governor_type, r[3].name) for r in ranked[1:3])
            yield Finding(Priority.HIGH, "科技文化", f"总督：任命{name}{where}",
                          f"{why}。备选：{alt}。", f"总督界面任命{name}" + (f"并指派到{city.name}。" if city else "。"))
        elif g.appointed:
            ranked = sorted(((*_governor_plan(sit, a.governor_type), a) for a in g.appointed if a.available_promotions),
                            key=lambda r: -r[0])
            if ranked:
                a = ranked[0][3]
                keys = GOOD_PROMOTIONS.get(a.governor_type, ())
                promo = next((p for p in a.available_promotions if any(k in p.name for k in keys)), a.available_promotions[0])
                name = GOV.get(a.governor_type, a.name)
                yield Finding(Priority.HIGH, "科技文化", f"总督：给{name}升「{promo.name}」",
                              promo.description[:80] or "", f"总督界面给{name}选「{promo.name}」。")
    for a in g.appointed:
        if a.assigned_city_id == -1:
            _, why, city, = _governor_plan(sit, a.governor_type)
            name = GOV.get(a.governor_type, a.name)
            yield Finding(Priority.MEDIUM, "科技文化", f"{name}还没指派城市",
                          why + "。", f"指派到{city.name}。" if city is not None else "总督要放到城市里才生效。")


# ------------------------------------------------------------------ 使者

CS_TYPE_CN = {"Scientific": "科技", "Cultural": "文化", "Religious": "宗教", "Trade": "商业", "Industrial": "工业",
              "Militaristic": "军事"}
CS_FOR_FOCUS = {"科技": "Scientific", "文化": "Cultural", "宗教": "Religious", "金币": "Trade", "外交": "Trade",
                "奇观": "Industrial", "征服": "Militaristic"}


@rule
def envoy_advice(sit: Situation):
    e = sit.envoys
    if not e or e.tokens_available <= 0:
        return
    focus = _focus(sit)
    want = {CS_FOR_FOCUS[f] for f in focus if f in CS_FOR_FOCUS}
    me = sit.overview.player_id
    cand = []
    for cs in e.city_states:
        if not cs.can_send_envoy:
            continue
        sc, notes = 10.0, []
        typ = CS_TYPE_CN.get(cs.city_state_type, cs.city_state_type)
        if cs.city_state_type in want:
            sc += 12
            notes.append(f"{typ}型，合你的路线")
        n = cs.envoys_sent
        nxt = 1 if n < 1 else 3 if n < 3 else 6 if n < 6 else n + 1
        need = nxt - n
        if need <= e.tokens_available:
            sc += 10 if nxt in (1, 3) else 6
        theirs = cs.suzerain_id not in (-1, me)
        if n >= 2 and not theirs:
            sc += 8
            notes.append("再派就能当宗主" if n >= 2 else "")
        if theirs:
            sc -= 6
            notes.append(f"宗主是{cs.suzerain_name}，要抢得多派")
        cand.append((sc, cs, need, nxt, typ, [x for x in notes if x]))
    if not cand:
        tip = "、".join(CS_TYPE_CN[CS_FOR_FOCUS[f]] for f in focus if f in CS_FOR_FOCUS) or "合你路线"
        yield Finding(Priority.MEDIUM, "外交", f"有 {e.tokens_available} 个使者没派",
                      "使者不派没有收益。", f"优先派给{tip}型城邦，凑到 3 个拿区域加成，最多的当宗主。")
        return
    cand.sort(key=lambda x: -x[0])
    sc, cs, need, nxt, typ, notes = cand[0]
    tier = {1: "第 1 个使者：首都加产出", 3: "3 个使者：对应区域加产出", 6: "6 个使者：更多区域加成"}.get(nxt, "巩固宗主")
    alt = "、".join(c[1].name for c in cand[1:3])
    yield Finding(Priority.MEDIUM, "外交", f"使者：派 {min(need, e.tokens_available)} 个给 {cs.name}",
                  f"{typ}型城邦，你已有 {cs.envoys_sent} 个；凑到 {nxt} 个拿「{tier}」。" + ("；".join(notes) + "。" if notes else "")
                  + (f"备选：{alt}。" if alt else ""),
                  f"城邦界面给 {cs.name} 派使者（手上 {e.tokens_available} 个）。")


# ------------------------------------------------------------------ 金币购买


def _buy_value(sit: Situation, city, item: str, st: dict) -> tuple[float, str]:
    u = item.upper()
    threatened = _threatened(sit, city)
    garrison = (city.garrison_hp or 0) > 0
    if threatened and not garrison and u.startswith("UNIT_") and any(k in u for k in MELEE_RANGED + CAVALRY) and "SCOUT" not in u:
        return 60, f"{city.name} 附近有敌军、城里没驻军"
    if threatened and u == "BUILDING_WALLS":
        return 48, f"{city.name} 附近有敌军，城墙能挡住早期进攻"
    if u == "UNIT_SETTLER" and city.population >= 2 and _need_settlers(sit):
        return 42, f"还要铺城（目标约 {st['target']} 座），金币买开拓者比锤子划算"
    if u == "UNIT_BUILDER" and st["builders"] + st["builders_queued"] == 0 and sit.facts is not None and sit.facts.improvable_now:
        return 38, f"全国没有建造者，有 {len(sit.facts.improvable_now)} 处资源等着改良"
    if u == "BUILDING_MONUMENT" and sit.overview.turn < 60 and sit.overview.culture_yield < 6:
        return 22, f"文化只有 {sit.overview.culture_yield:.0f}/回合，纪念碑加快市政"
    if u == "BUILDING_GRANARY" and city.housing and city.population >= city.housing - 1:
        return 20, f"{city.name} 住房满了"
    if u == "UNIT_TRADER" and not any("TRADER" in x.unit_type.upper() for x in sit.units) and sit.overview.turn > 25:
        return 20, "还没有商人：商路给粮锤或金币，越早越值"
    return 0, ""


def buy_plan(sit: Situation) -> list[tuple]:
    """值得用金币买的东西（最多 2 件，总价不超过可用金币）：[(价值, 选项, 城市, 理由, 是否正在造)]。"""
    o = sit.overview
    if not sit.production_options or o.gold <= 0:
        return []
    st = empire_status(sit)
    reserve = max(0.0, -o.gold_per_turn * 8)  # 入不敷出时留点钱
    budget = o.gold - reserve
    by_id = {c.city_id: c for c in sit.cities}
    cands = []
    for cid, opts in sit.production_options.items():
        city = by_id.get(cid)
        if city is None:
            continue
        for opt in opts:
            if opt.gold_cost is None or opt.gold_cost <= 0:
                continue
            val, why = _buy_value(sit, city, opt.item_name, st)
            if val <= 0:
                continue
            building_now = (city.currently_building or "").upper() == opt.item_name.upper()
            if building_now and city.production_turns_left and city.production_turns_left <= 1:
                continue  # 下回合就造好了，不用买
            cands.append((val, opt, city, why, building_now))
    cands.sort(key=lambda x: (-x[0], x[1].gold_cost))
    shown, spent, seen, used_city = [], 0, set(), set()
    for val, opt, city, why, building_now in cands:
        key = opt.item_name
        if key in seen or city.city_id in used_city:  # 每座城一回合只买一样，同样东西只买一次
            continue
        if opt.gold_cost + spent > budget:
            continue
        seen.add(key)
        used_city.add(city.city_id)
        spent += opt.gold_cost
        shown.append((val, opt, city, why, building_now))
        if len(shown) >= 2:
            break
    return shown


@rule
def buy_advice(sit: Situation):
    o = sit.overview
    shown = buy_plan(sit)
    if shown:
        top = shown[0]
        lines = []
        for val, opt, city, why, building_now in shown:
            save = f"，省下 {city.production_turns_left} 回合" if building_now and city.production_turns_left else ""
            lines.append(f"{city.name} 买{production_cn(opt.item_name)}（{opt.gold_cost} 金{save}）：{why}")
        yield Finding(Priority.HIGH if top[0] >= 45 else Priority.MEDIUM, "经济",
                      f"金币：{top[2].name} 直接买{production_cn(top[1].item_name)}",
                      "；".join(lines) + f"。你有 {o.gold:.0f} 金。",
                      "城市生产界面切到金币购买。", city_id=top[2].city_id)
    elif o.gold > 300 + 100 * len(sit.cities):
        yield Finding(Priority.LOW, "经济", f"囤了 {o.gold:.0f} 金币，没有急需买的",
                      "目前没有特别值得买的单位或建筑。", "可以买关键地块（资源/奇观位），或者给前线单位升级。")


# ------------------------------------------------------------------ 尤里卡/鼓舞时机


@rule
def boost_timing(sit: Situation):
    """研究快完成但尤里卡没触发：可以先换别的，触发后再回来（社区常用技巧）。"""
    t = sit.tech
    if not t:
        return
    for kind, cur, turns, opts in (("科技", t.current_research, t.current_research_turns, t.available_techs),
                                   ("市政", t.current_civic, t.current_civic_turns, t.available_civics)):
        if not cur or cur in ("None", "NONE"):
            continue
        o = next((x for x in opts if x.name == cur or getattr(x, "tech_type", getattr(x, "civic_type", "")) == cur), None)
        if not o or o.boosted or not o.boost_desc:
            continue
        if turns and 1 < turns <= 4 and o.progress_pct < 60:
            word = "尤里卡" if kind == "科技" else "鼓舞"
            yield Finding(Priority.LOW, "科技文化", f"「{o.name}」{word}还没触发",
                          f"还要 {turns} 回合；{word}条件：{o.boost_desc}。触发能省 40%（中国 50%）。",
                          f"如果几回合内能做到，可以先换研究别的，{word}触发后再回来。")
