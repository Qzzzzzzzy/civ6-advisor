"""科技 / 市政推荐：按文明倾向 + 当前局势 + 尤里卡/鼓舞 + 回合数打分，并给出理由。

每项科技/市政先打上用途标签（科技、文化、宗教、军事、防御、经济、产能、成长、扩张、海洋、政体、宜居），
再根据局势给标签加权。没收录的项目只按回合数和尤里卡排序，不会报错。
"""

from __future__ import annotations

from dataclasses import dataclass, field

from civ6_advisor.civs import ResolvedProfile, profile_for
from civ6_advisor.game import Situation
from civ6_advisor.geo import hex_distance
from civ6_advisor.names import resource_cn
from civ6_advisor.rules.base import game_phase

T = "TECH_"
C = "CIVIC_"

TAGS: dict[str, tuple[str, ...]] = {
    # ---- 远古 / 古典科技
    T + "POTTERY": ("成长", "经济"), T + "ANIMAL_HUSBANDRY": ("成长", "改良"), T + "MINING": ("产能", "改良"),
    T + "SAILING": ("海洋", "改良"), T + "ASTROLOGY": ("宗教",), T + "IRRIGATION": ("成长", "改良"),
    T + "ARCHERY": ("防御", "军事"), T + "WRITING": ("科技",), T + "MASONRY": ("防御", "奇观"),
    T + "BRONZE_WORKING": ("军事",), T + "THE_WHEEL": ("军事", "产能"),
    T + "CELESTIAL_NAVIGATION": ("海洋", "成长"), T + "CURRENCY": ("经济",), T + "HORSEBACK_RIDING": ("军事",),
    T + "IRON_WORKING": ("军事",), T + "SHIPBUILDING": ("海洋",), T + "MATHEMATICS": ("科技", "军事"),
    T + "CONSTRUCTION": ("宜居", "奇观"), T + "ENGINEERING": ("成长", "产能"),
    # ---- 中世纪 / 文艺复兴
    T + "BUTTRESS": ("奇观",), T + "MILITARY_TACTICS": ("军事",), T + "APPRENTICESHIP": ("产能",),
    T + "STIRRUPS": ("军事",), T + "MACHINERY": ("军事",), T + "EDUCATION": ("科技",),
    T + "MILITARY_ENGINEERING": ("防御",), T + "CASTLES": ("防御",),
    T + "CARTOGRAPHY": ("海洋", "扩张"), T + "MASS_PRODUCTION": ("产能",), T + "BANKING": ("经济",),
    T + "GUNPOWDER": ("防御", "军事"), T + "PRINTING": ("科技",), T + "SQUARE_RIGGING": ("海洋", "军事"),
    T + "ASTRONOMY": ("科技",), T + "METAL_CASTING": ("军事",), T + "SIEGE_TACTICS": ("军事",),
    # ---- 工业及以后
    T + "INDUSTRIALIZATION": ("产能",), T + "SCIENTIFIC_THEORY": ("科技",), T + "BALLISTICS": ("军事", "防御"),
    T + "MILITARY_SCIENCE": ("军事",), T + "STEAM_POWER": ("海洋", "产能"), T + "SANITATION": ("成长",),
    T + "ECONOMICS": ("经济",), T + "RIFLING": ("军事", "防御"), T + "FLIGHT": ("军事", "文化"),
    T + "REPLACEABLE_PARTS": ("军事",), T + "STEEL": ("防御", "军事"), T + "ELECTRICITY": ("经济", "产能"),
    T + "RADIO": ("文化",), T + "CHEMISTRY": ("科技",), T + "COMBUSTION": ("军事",),
    T + "ADVANCED_FLIGHT": ("军事",), T + "ROCKETRY": ("科技", "太空"), T + "COMPUTERS": ("文化", "科技"),
    T + "PLASTICS": ("产能",), T + "SATELLITES": ("太空", "科技"), T + "NUCLEAR_FISSION": ("军事", "科技"),
    T + "NANOTECHNOLOGY": ("太空", "科技"), T + "ROBOTICS": ("太空", "军事"), T + "NUCLEAR_FUSION": ("太空", "科技"),
    T + "FUTURE_TECH": ("科技", "太空"),
    # ---- 市政
    C + "CODE_OF_LAWS": ("政体",), C + "CRAFTSMANSHIP": ("产能", "改良"), C + "FOREIGN_TRADE": ("经济", "扩张"),
    C + "MILITARY_TRADITION": ("军事",), C + "STATE_WORKFORCE": ("产能", "奇观"), C + "EARLY_EMPIRE": ("扩张",),
    C + "MYSTICISM": ("宗教",), C + "GAMES_RECREATION": ("宜居", "文化"), C + "POLITICAL_PHILOSOPHY": ("政体", "文化"),
    C + "DRAMA_POETRY": ("文化",), C + "MILITARY_TRAINING": ("军事",), C + "DEFENSIVE_TACTICS": ("防御",),
    C + "RECORDED_HISTORY": ("科技", "文化"), C + "THEOLOGY": ("宗教", "政体"), C + "NAVAL_TRADITION": ("海洋",),
    C + "FEUDALISM": ("成长", "改良"), C + "CIVIL_SERVICE": ("成长", "政体"), C + "MERCENARIES": ("军事",),
    C + "MEDIEVAL_FAIRES": ("经济",), C + "GUILDS": ("经济", "产能"), C + "DIVINE_RIGHT": ("宗教", "政体"),
    C + "EXPLORATION": ("海洋", "扩张", "政体"), C + "HUMANISM": ("文化", "科技"), C + "DIPLOMATIC_SERVICE": ("外交",),
    C + "REFORMED_CHURCH": ("宗教",), C + "MERCANTILISM": ("经济",), C + "THE_ENLIGHTENMENT": ("科技", "文化"),
    C + "COLONIALISM": ("扩张",), C + "CIVIL_ENGINEERING": ("产能",), C + "NATIONALISM": ("军事",),
    C + "OPERA_BALLET": ("文化",), C + "NATURAL_HISTORY": ("文化",), C + "URBANIZATION": ("成长",),
    C + "SCORCHED_EARTH": ("军事",), C + "CONSERVATION": ("文化",), C + "CAPITALISM": ("经济",),
    C + "MASS_MEDIA": ("文化", "政体"), C + "MOBILIZATION": ("军事",), C + "IDEOLOGY": ("政体",),
    C + "SUFFRAGE": ("政体",), C + "TOTALITARIANISM": ("政体", "军事"), C + "CLASS_STRUGGLE": ("政体", "产能"),
    C + "CULTURAL_HERITAGE": ("文化",), C + "COLD_WAR": ("军事",), C + "PROFESSIONAL_SPORTS": ("文化", "宜居"),
    C + "RAPID_DEPLOYMENT": ("军事",), C + "SPACE_RACE": ("太空", "科技"), C + "GLOBALIZATION": ("外交",),
    C + "SOCIAL_MEDIA": ("文化",), C + "ENVIRONMENTALISM": ("文化",),
}

# 文明攻略里的倾向 → 标签
FOCUS_TAG = {"科技": "科技", "文化": "文化", "宗教": "宗教", "征服": "军事", "外交": "外交", "奇观": "奇观",
             "扩张": "扩张", "金币": "经济", "人口": "成长", "海洋": "海洋"}

# 资源改良需要的科技
RESOURCE_TECH = {
    **dict.fromkeys(("HORSES", "CATTLE", "SHEEP"), T + "ANIMAL_HUSBANDRY"),
    **dict.fromkeys(("IVORY", "FURS", "DEER", "TRUFFLES"), T + "ANIMAL_HUSBANDRY"),
    **dict.fromkeys(("BANANAS", "CITRUS", "COCOA", "COFFEE", "COTTON", "DYES", "SILK", "SPICES", "SUGAR", "TEA",
                     "TOBACCO", "WINE", "INCENSE", "OLIVES"), T + "IRRIGATION"),
    **dict.fromkeys(("COPPER", "DIAMONDS", "JADE", "SILVER", "GOLD", "MERCURY", "SALT", "STONE", "MARBLE",
                     "GYPSUM", "IRON", "NITER", "COAL"), T + "MINING"),
    **dict.fromkeys(("FISH", "CRABS", "WHALES", "PEARLS", "TURTLES", "AMBER"), T + "SAILING"),
}
LUXURIES = {"IVORY", "FURS", "TRUFFLES", "CITRUS", "COCOA", "COFFEE", "COTTON", "DYES", "SILK", "SPICES", "SUGAR",
            "TEA", "TOBACCO", "WINE", "INCENSE", "OLIVES", "DIAMONDS", "JADE", "SILVER", "GOLD", "MERCURY", "SALT",
            "MARBLE", "GYPSUM", "WHALES", "PEARLS", "TURTLES", "AMBER"}


@dataclass
class Pick:
    name: str
    type: str
    turns: int
    progress: int
    boosted: bool
    boost_desc: str
    unlocks: str
    score: float = 0.0
    reasons: list[str] = field(default_factory=list)

    @property
    def turns_text(self) -> str:
        return f"{self.turns} 回合" if self.turns > 0 else ""


@dataclass
class TrackState:
    """一条研究线（科技或市政）的状态。"""

    kind: str  # "科技" / "市政"
    current: Pick | None  # 正在研究的
    current_turns: int
    picks: list[Pick]  # 推荐（已排序，不含当前项）


# ------------------------------------------------------------------ 局势需求


def _needs(sit: Situation, prof: ResolvedProfile | None) -> dict[str, tuple[float, str]]:
    """局势 → {标签: (加分, 理由)}"""
    need: dict[str, tuple[float, str]] = {}

    def add(tag: str, pts: float, why: str):
        if tag not in need or need[tag][0] < pts:
            need[tag] = (pts, why)

    o = sit.overview
    phase = game_phase(sit)

    # 敌军压境
    hostile = {63} | {c.player_id for c in sit.diplomacy if c.is_at_war}
    close = any(
        t.owner_id in hostile and hex_distance(c.x, c.y, t.x, t.y) <= 4 for c in sit.cities for t in sit.threats
    )
    if close:
        add("防御", 30, "城市附近有敌军，需要防御")
        add("军事", 15, "城市附近有敌军")
    if any(c.is_at_war for c in sit.diplomacy):
        add("军事", 25, "正在交战")

    # 宗教：需要宗教的文明，名额越少、回合越晚越急
    left = (o.religions_max or 99) - o.religions_founded
    if prof and prof.religion == "必需" and not o.our_religion and left > 0:
        add("宗教", 35, f"{prof.name}需要尽快创立宗教")
        has_holy = any("HOLY_SITE" in d.upper() for c in sit.cities for d in (c.districts or []))
        if not has_holy and phase in ("开局", "前期"):
            pts = 40 + (15 if left <= 2 else 0)
            why = f"宗教名额只剩 {left} 个，占星术→圣地→先知是抢宗教的唯一路线，越晚越难抢"
            add("@" + T + "ASTROLOGY", pts, why)
            add("@" + C + "MYSTICISM", 15, "宗教相关")

    # 政体 / 政策
    gov = sit.government
    if gov and ("CHIEFDOM" in gov.government_type or not gov.government_type):
        # 只有这两个市政直接带来政策槽和第一个政体
        add("@" + C + "CODE_OF_LAWS", 35, "还在酋邦，先拿到第一个政体")
        add("@" + C + "POLITICAL_PHILOSOPHY", 35, "还在酋邦，先拿到第一个政体")
    elif gov and any(not s.current_policy for s in gov.slots) and not (gov.available_policies or []):
        add("政体", 10, "有空政策槽但没有能放的政策卡")

    # 扩张
    target = prof.expand if prof else 5
    if phase in ("开局", "前期") and len(sit.cities) < target:
        add("扩张", 12, "城市数还没达标")

    # 成长 / 宜居 / 金币
    if sum(1 for c in sit.cities if c.housing and c.population >= c.housing) >= max(1, len(sit.cities) // 2):
        add("成长", 15, "多座城市住房已满")
    if any(c.amenities < 0 for c in sit.cities):
        add("宜居", 15, "有城市宜居度为负")
    if o.gold_per_turn < 0:
        add("经济", 20, "金币入不敷出")
    return need


def _resource_needs(sit: Situation, prof: ResolvedProfile | None) -> dict[str, tuple[float, str]]:
    """领土内缺科技才能改良的资源 → {所需科技: (加分, 理由)}。优先用共同事实（只含看得见的资源）。"""
    out: dict[str, tuple[float, str]] = {}
    facts = sit.facts
    if facts is not None:
        has_builder = any(u.build_charges > 0 for u in sit.units)
        idle_builder = has_builder and not facts.improvable_now
        groups: dict[str, list] = {}
        for r in facts.blocked:
            groups.setdefault(r.prereq, []).append(r)
        for req, rs in groups.items():
            pts = 0.0
            for r in rs:
                pts += {"luxury": 18, "strategic": 8, "bonus": 6}.get(r.cls, 4)
            pts = min(pts, 40)
            lux = [r for r in rs if r.cls == "luxury"]
            sample = lux[0] if lux else rs[0]
            why = f"能改良{sample.city}的{'奢侈品' if lux else ''}{resource_cn(sample.resource)}"
            if len(rs) > 1:
                why += f"等 {len(rs)} 处资源"
            if prof and prof.has("improve_bonus"):
                pts += 10
                why += f"（{prof.name}改良资源有额外收益）"
            if idle_builder:
                pts += 15
                why += "，建造者正闲着"
            out[req] = (pts, why)
        return out
    # 旧逻辑：只有资源名单
    for c in sit.cities:
        for r in c.unimproved_resources:
            key = r.split("@")[0].upper().removeprefix("RESOURCE_")
            tech = RESOURCE_TECH.get(key)
            if tech and tech not in out:
                kind = "奢侈品" if key in LUXURIES else "资源"
                out[tech] = (20, f"能改良{c.name}的{kind}{resource_cn(key)}")
    return out


# ------------------------------------------------------------------ 打分


def _style_bonus(sit: Situation) -> dict[str, tuple[float, str]]:
    """开启流派时：流派路线上的科技/市政加分，下一个里程碑需要的再额外加分（落后计划加更多）。"""
    from civ6_advisor.playstyles import active, progress

    ps = active(sit)
    if not ps:
        return {}
    out = {k: (v[0], f"「{ps.name}」路线：{v[1]}") for k, v in {**ps.tech, **ps.civic}.items()}
    pr = progress(ps, sit)
    for i, st in enumerate(pr.todo[:2]):
        if st.cond[0] in ("tech", "civic"):
            pts = (30 if st in pr.late else 20) - i * 8
            base = out.get(st.cond[1], (0, ""))[0]
            out[st.cond[1]] = (base + pts, f"流派下一步：{st.text}" + ("（已落后于计划）" if st in pr.late else ""))
    return out


def _score(p: Pick, prof: ResolvedProfile | None, need, res_need, eureka_first: bool, style=None) -> Pick:
    tags = TAGS.get(p.type, ())
    why: list[tuple[float, str]] = []  # (加分, 理由)，最后按加分排序，最重要的理由排第一

    def add(pts: float, text: str):
        p.score += pts
        why.append((pts, text))

    if p.boosted:
        add(25, "已触发尤里卡/鼓舞，打折")
    if p.progress:
        p.score += p.progress * 0.2
    if p.turns > 0:
        p.score -= min(p.turns, 30) * 1.2
    if prof:
        for i, f in enumerate(prof.focus[:3]):
            if FOCUS_TAG.get(f) in tags:
                add((22, 14, 8)[i], f"{prof.name}擅长{f}")
                break
    for tag in (*tags, "@" + p.type):  # "@类型名" 是只针对某一项的加分
        if tag in need:
            add(*need[tag])
    if p.type in res_need:
        add(*res_need[p.type])
    if style and p.type in style:
        add(*style[p.type])
    if eureka_first and p.boost_desc and not p.boosted:
        add(8, "尤里卡条件：" + p.boost_desc)
    why.sort(key=lambda w: -w[0])
    p.reasons = list(dict.fromkeys(t for _, t in why))
    if p.unlocks:
        first = "、".join(u.strip() for u in p.unlocks.split(",")[:2] if u.strip())
        if first:
            p.reasons.append("解锁" + first)
    return p


def tracks(sit: Situation) -> tuple[TrackState | None, TrackState | None]:
    """返回 (科技线, 市政线)。没有科技数据时返回 (None, None)。"""
    st = sit.tech
    if not st:
        return None, None
    prof = profile_for(sit.civ.civ_type, sit.civ.leader_type) if sit.civ else None
    need = _needs(sit, prof)
    res_need = _resource_needs(sit, prof)
    eureka_first = bool(prof and prof.has("eureka_first"))
    style = _style_bonus(sit)

    techs = [
        _score(Pick(t.name, t.tech_type, t.turns, t.progress_pct, t.boosted, t.boost_desc, t.unlocks),
               prof, need, res_need, eureka_first, style)
        for t in st.available_techs
    ]
    civics = [
        _score(Pick(c.name, c.civic_type, c.turns, c.progress_pct, c.boosted, c.boost_desc, ""),
               prof, need, res_need, eureka_first, style)
        for c in st.available_civics
    ]

    def build(kind, items, current_name, current_turns):
        cur = next((p for p in items if p.name == current_name), None)
        if current_name in ("None", "", None):
            cur = None
        elif cur is None:
            cur = Pick(current_name, "", current_turns, 0, False, "", "")
        rest = sorted((p for p in items if p is not cur), key=lambda p: -p.score)
        return TrackState(kind, cur, current_turns, rest)

    return (
        build("科技", techs, st.current_research, st.current_research_turns),
        build("市政", civics, st.current_civic, st.current_civic_turns),
    )


def recommend_text(track: TrackState, n: int = 3) -> str:
    """给规则/简报用的一句话推荐。"""
    if not track.picks:
        return "打开科技树选一个。" if track.kind == "科技" else "打开市政树选一个。"
    top = track.picks[0]
    why = "；".join(top.reasons[:3])
    alts = "、".join(p.name for p in track.picks[1:n])
    s = f"推荐 {top.name}" + (f"（{top.turns_text}）" if top.turns_text else "") + (f"：{why}" if why else "")
    if not top.boosted and top.boost_desc:
        word = "尤里卡" if track.kind == "科技" else "鼓舞"
        s += f"。{word}条件：{top.boost_desc}（做到能省 40%）"
    return s + (f"。备选：{alts}" if alts else "")
