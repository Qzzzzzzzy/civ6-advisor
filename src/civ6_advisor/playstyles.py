"""文明流派：每个文明一个固定的「推荐流派」（比如马格努斯砍树飞天流）。

玩家在悬浮窗点流派按钮开启后：
  - 科技 / 市政推荐按流派路线加分（research.py）
  - 城市生产推荐按流派加分（production.py）
  - 规则引擎按流派的里程碑检查进度，给出「下一步」，落后于计划时提高优先级（rules/playstyle.py）
  - 问 AI 时附上流派说明，要求按流派给建议（llm.py / kb.py）
再点一次取消，恢复常规推荐。

里程碑的回合数按标准速度估计，只是参考：落后不代表失败，但说明要调整。
"""

from __future__ import annotations

from dataclasses import dataclass, field

T = "TECH_"
C = "CIVIC_"

GOV_CN = {
    "GOVERNOR_THE_RESOURCE_MANAGER": "马格努斯", "GOVERNOR_THE_BUILDER": "梁", "GOVERNOR_THE_EDUCATOR": "平哥拉",
    "GOVERNOR_THE_MERCHANT": "雷娜", "GOVERNOR_THE_CARDINAL": "莫克夏", "GOVERNOR_THE_AMBASSADOR": "阿玛尼",
    "GOVERNOR_THE_DEFENDER": "维克托", "GOVERNOR_IBRAHIM": "易卜拉欣",
}


@dataclass
class Step:
    """一个里程碑。cond 是可以从局势检查的条件：
    ("tech", 类型) ("civic", 类型) ("cities", n) ("district", 通用区域, n) ("religion",)
    ("governor", 总督类型) ("building", 建筑, n) ("units", (关键字…), n) ("government", 类型关键字)
    """

    text: str
    cond: tuple
    by: int | None = None  # 建议在第几回合前完成（标准速度）
    how: str = ""


@dataclass
class Playstyle:
    id: str
    civ: str
    name: str
    pitch: str  # 一句话
    goal: str  # 目标胜利
    core: list[str]  # 核心思路（给 AI 和展开说明）
    governors: str
    steps: list[Step]
    tech: dict[str, tuple[float, str]] = field(default_factory=dict)
    civic: dict[str, tuple[float, str]] = field(default_factory=dict)
    prod: dict[str, tuple[float, str]] = field(default_factory=dict)  # 生产项（通用区域会自动换成特色版）
    avoid: list[str] = field(default_factory=list)
    expand: int | None = None  # 覆盖前期目标城市数
    broken: list[tuple[tuple, str]] = field(default_factory=list)  # (条件, 说明)：条件成立说明流派前提没了
    leaders: tuple[str, ...] = ()  # 更适合的领袖（类型名），空 = 都适合

    def describe(self) -> str:
        lines = [f"### 流派：{self.name}（目标：{self.goal}）", self.pitch, "核心思路："]
        lines += [f"- {c}" for c in self.core]
        lines.append(f"总督：{self.governors}")
        lines.append("里程碑（回合按标准速度估计）：")
        for i, s in enumerate(self.steps, 1):
            lines.append(f"{i}. {s.text}" + (f"（约第 {s.by} 回合前）" if s.by else "") + (f"：{s.how}" if s.how else ""))
        if self.avoid:
            lines.append("不要做：" + "；".join(self.avoid))
        return "\n".join(lines)


# ------------------------------------------------------------------ 简写


def tech(t: str):
    return ("tech", T + t)


def civic(c: str):
    return ("civic", C + c)


def cities(n: int):
    return ("cities", n)


def dist(d: str, n: int = 1):
    return ("district", "DISTRICT_" + d, n)


def religion():
    return ("religion",)


def gov(g: str):
    return ("governor", g)


def units(keys, n: int):
    return ("units", tuple(keys) if isinstance(keys, (list, tuple)) else (keys,), n)


def building(b: str, n: int = 1):
    return ("building", b, n)


def government(g: str):
    return ("government", g)


NO_RELIGION_SLOT = ("no_religion_slot",)
MAGNUS = "GOVERNOR_THE_RESOURCE_MANAGER"
LIANG = "GOVERNOR_THE_BUILDER"
PINGALA = "GOVERNOR_THE_EDUCATOR"
REYNA = "GOVERNOR_THE_MERCHANT"
MOKSHA = "GOVERNOR_THE_CARDINAL"
AMANI = "GOVERNOR_THE_AMBASSADOR"
VICTOR = "GOVERNOR_THE_DEFENDER"


def techs(**kw) -> dict:
    return {T + k: v for k, v in kw.items()}


def civics(**kw) -> dict:
    return {C + k: v for k, v in kw.items()}


# 常用路线片段
SPACE_TECH = techs(WRITING=(15, "学院区"), EDUCATION=(25, "大学"), APPRENTICESHIP=(12, "工业区"),
                   INDUSTRIALIZATION=(15, "工厂"), ROCKETRY=(30, "太空港"), SCIENTIFIC_THEORY=(10, "研究实验室路线"))
RELIGION_TECH = techs(ASTROLOGY=(40, "圣地 → 宗教，抢名额"))
RELIGION_CIVIC = civics(MYSTICISM=(12, "宗教路线"), THEOLOGY=(22, "神庙信条 + 神权"))
CULTURE_CIVIC = civics(DRAMA_POETRY=(25, "剧院广场"), HUMANISM=(18, "博物馆/考古"), NATURAL_HISTORY=(18, "考古学家"),
                       CONSERVATION=(10, "国家公园"))
WAR_CIVIC = civics(MILITARY_TRADITION=(15, "侧翼/支援加成"), POLITICAL_PHILOSOPHY=(15, "寡头/独裁"))
CHOP_CIVIC = civics(CRAFTSMANSHIP=(18, "Ilkum：建造者 +30%"), STATE_WORKFORCE=(18, "第一个总督头衔"),
                    EARLY_EMPIRE=(10, "总督头衔"))


def chop_space(civ, name, pitch, extra_core=(), first=(), **kw) -> Playstyle:
    """马格努斯砍树飞天流的通用骨架，文明特色步骤放在 first 里。"""
    steps = list(first) + [
        Step("扩到 4 座以上城市（砍树要地盘和建造者）", cities(4), 60),
        Step("工匠技艺，切 Ilkum 狂出建造者", civic("CRAFTSMANSHIP"), 45),
        Step("任命马格努斯并放在主力砍树城", gov(MAGNUS), 75, "他的基础能力「收获」让砍树/采伐的产出 +50%"),
        Step("3 座学院区", dist("CAMPUS", 3), 90, "森林留着，马格努斯就位后砍进学院区"),
        Step("教育（大学）", tech("EDUCATION"), 110),
        Step("2 座工业区", dist("INDUSTRIAL_ZONE", 2), 140),
        Step("火箭学，建太空港", dist("SPACEPORT"), 240, "太空港和太空项目都能用砍树推，提前留好林子"),
    ]
    tech_ = dict(SPACE_TECH)
    tech_.update(kw.pop("tech", {}))
    civic_ = dict(CHOP_CIVIC)
    civic_.update(kw.pop("civic", {}))
    prod = {"DISTRICT_CAMPUS": (25, "流派核心：学院区"), "UNIT_BUILDER": (18, "砍树需要建造者"),
            "DISTRICT_INDUSTRIAL_ZONE": (15, "工业区"), "DISTRICT_SPACEPORT": (40, "太空港")}
    prod.update(kw.pop("prod", {}))
    return Playstyle(
        id=civ + "_CHOP", civ=civ, name=name, pitch=pitch, goal="科技",
        core=["森林/雨林先别砍，等马格努斯就位、Ilkum 开着再砍进学院区、大学、太空项目",
              "建造者是主力生产工具：每座城 1-2 个，次数用来砍树和改良", *extra_core],
        governors="马格努斯（收获：砍树 +50%，跟着砍树城走）→ 平哥拉（科研）→ 梁",
        steps=steps, tech=tech_, civic=civic_, prod=prod,
        avoid=["马格努斯就位前大规模砍树（浪费 50%）", "前期造过多军队拖慢建造者"], **kw)


def religion_rush(civ, name, pitch, goal="宗教", extra_core=(), after=(), **kw) -> Playstyle:
    steps = [
        Step("占星术", tech("ASTROLOGY"), 20),
        Step("第一座圣地", dist("HOLY_SITE"), 40),
        Step("创立宗教", religion(), 65, "大先知一出就创教"),
        Step("神学（神权、神庙信条）", civic("THEOLOGY"), 100),
        Step("任命莫克夏（信仰买东西、传教更强）", gov(MOKSHA), 110),
        *after,
    ]
    tech_ = dict(RELIGION_TECH)
    tech_.update(kw.pop("tech", {}))
    civic_ = dict(RELIGION_CIVIC)
    civic_.update(kw.pop("civic", {}))
    prod = {"DISTRICT_HOLY_SITE": (35, "流派核心：圣地"), "BUILDING_SHRINE": (15, "先知点"),
            "BUILDING_TEMPLE": (12, "使徒"), "UNIT_MISSIONARY": (10, "传教"), "UNIT_APOSTLE": (15, "使徒")}
    prod.update(kw.pop("prod", {}))
    return Playstyle(
        id=civ + "_RELIGION", civ=civ, name=name, pitch=pitch, goal=goal,
        core=["开局第一优先是宗教名额：占星术 → 圣地 → 大先知", "宗教到手后信仰是主要货币", *extra_core],
        governors="莫克夏（信仰购买、传教）→ 马格努斯或雷娜看经济",
        steps=steps, tech=tech_, civic=civic_, prod=prod,
        broken=[(NO_RELIGION_SLOT, "宗教名额已经被抢光，这个流派的核心没了")], **kw)


# ------------------------------------------------------------------ 每个文明一个流派

def _all() -> list[Playstyle]:
    P, S = Playstyle, Step
    out: list[Playstyle] = [
        P("CIVILIZATION_AMERICA_PARKS", "CIVILIZATION_AMERICA", "国家公园电影文化流",
          "高魅力地块留给国家公园，现代用电影制片厂把旅游打爆。", "文化",
          ["城市选在山、森林、自然奇观附近（魅力）", "剧院广场 + 博物馆攒伟大作品", "自然历史后信仰买自然学家建国家公园",
           "现代电影制片厂对周围文明旅游 +100%"],
          "梁（城市公园、魅力）→ 平哥拉（策展人，伟大作品旅游）",
          [S("2 座剧院广场", dist("THEATER", 2), 90), S("人文主义", civic("HUMANISM"), 130),
           S("自然历史（自然学家）", civic("NATURAL_HISTORY"), 170, "国家公园要 4 格魅力都迷人以上"),
           S("任命梁", gov(LIANG), 120), S("电影制片厂", building("FILM_STUDIO"), 230)],
          civic=CULTURE_CIVIC | civics(CULTURAL_HERITAGE=(10, "遗产旅游")),
          prod={"DISTRICT_THEATER": (25, "流派核心")},
          avoid=["砍掉高魅力的森林", "在魅力高的地方放工业区"]),
        P("CIVILIZATION_ARABIA_MADRASA", "CIVILIZATION_ARABIA", "伊斯兰学校信仰飞天流",
          "必拿最后一个先知，不用抢宗教；学院区 + 伊斯兰学校出信仰，信仰买科学家和工程师。", "科技",
          ["圣地建一个就够（保底拿先知）", "主力是学院区，大学换成伊斯兰学校后信仰暴涨", "信仰买大科学家/大工程师，太空项目前攒信仰"],
          "平哥拉（科研、伟人点）→ 莫克夏（信仰购买）",
          [S("2 座学院区", dist("CAMPUS", 2), 75), S("一座圣地（保底先知）", dist("HOLY_SITE"), 80),
           S("教育（伊斯兰学校）", tech("EDUCATION"), 110), S("任命平哥拉", gov(PINGALA), 90),
           S("4 座学院区", dist("CAMPUS", 4), 140), S("太空港", dist("SPACEPORT"), 240)],
          tech=SPACE_TECH, prod={"DISTRICT_CAMPUS": (28, "流派核心"), "DISTRICT_SPACEPORT": (40, "太空港")},
          avoid=["为抢宗教牺牲学院区（先知是保底的）"]),
        chop_space("CIVILIZATION_AUSTRALIA", "马格努斯砍树飞天流（魅力学院）",
                   "学院区放在惊艳地块拿 +3 相邻，马格努斯砍树推区域，飞天。",
                   extra_core=["学院区优先放迷人/惊艳地块（+1/+3）", "沿海建城（+3 住房）", "被宣战后 10 回合 +100% 产能，正好推太空项目"]),
        P("CIVILIZATION_AZTEC_EAGLE", "CIVILIZATION_AZTEC", "鹰武士抓奴建区流",
          "鹰武士打赢会抓对手的单位变成建造者，用建造者次数推区域。", "征服",
          ["开局出 3-4 个鹰武士打最近的邻居或城邦，抓到的建造者全部推区域", "奢侈品多给宜居和区域加成", "抓到足够建造者后再扩张"],
          "梁（建造者次数）→ 维克托",
          [S("3 个鹰武士", units(("EAGLE_WARRIOR",), 3), 25), S("扩到 4 座城", cities(4), 60),
           S("任命梁", gov(LIANG), 70), S("第一座学院区（用建造者推）", dist("CAMPUS", 1), 90)],
          tech=techs(BRONZE_WORKING=(10, "铁")), civic=WAR_CIVIC,
          prod={"UNIT_AZTEC_EAGLE_WARRIOR": (40, "流派核心")}, expand=6),
        P("CIVILIZATION_BABYLON_EUREKA", "CIVILIZATION_BABYLON_STK", "尤里卡跳科技流",
          "研究顺序完全由「下一个能触发的尤里卡」决定，每个尤里卡就是一整个科技。", "科技",
          ["每回合先看哪个尤里卡最容易触发，再安排单位和生产", "每种专业区域早建一个（汉谟拉比送首个建筑）", "基础科研只有一半，别硬研究没尤里卡的科技"],
          "平哥拉 → 马格努斯",
          [S("书写（学院区）", tech("WRITING"), 25), S("学院区", dist("CAMPUS"), 50),
           S("扩到 5 座城", cities(5), 70), S("学院、商业、剧院、圣地各一个", dist("COMMERCIAL_HUB"), 100),
           S("太空港", dist("SPACEPORT"), 230)],
          tech=SPACE_TECH, prod={"DISTRICT_CAMPUS": (20, "流派核心")}),
        P("CIVILIZATION_BRAZIL_CARNIVAL", "CIVILIZATION_BRAZIL", "雨林狂欢节伟人流",
          "保留雨林拿相邻，狂欢节区域出伟人点，伟人带动文化。", "文化",
          ["雨林不要砍（学院、圣地、剧院相邻 +1）", "狂欢节（娱乐区替代）多建", "伟人越多越强，政策带伟人点"],
          "平哥拉（伟人点）→ 梁（雨林公园）",
          [S("2 座剧院广场", dist("THEATER", 2), 90), S("狂欢节", dist("ENTERTAINMENT_COMPLEX"), 100),
           S("人文主义", civic("HUMANISM"), 140), S("任命平哥拉", gov(PINGALA), 110)],
          civic=CULTURE_CIVIC | civics(GAMES_RECREATION=(22, "狂欢节")),
          prod={"DISTRICT_ENTERTAINMENT_COMPLEX": (25, "狂欢节"), "DISTRICT_THEATER": (20, "文化")},
          avoid=["砍雨林"]),
        religion_rush("CIVILIZATION_BYZANTIUM", "圣城骑兵流",
                      "先创教把宗教传到对手圣城，然后用骑兵打（每个圣城 +3 战斗力）。", goal="征服",
                      extra_core=["竞技场送重骑兵", "进攻前先让目标城信你的宗教"],
                      after=[S("竞技场（送重骑兵）", dist("ENTERTAINMENT_COMPLEX"), 110)],
                      tech=techs(HORSEBACK_RIDING=(15, "骑兵"), STIRRUPS=(15, "骑士")),
                      civic=civics(GAMES_RECREATION=(20, "竞技场"))),
        P("CIVILIZATION_CANADA_DIPLO", "CIVILIZATION_CANADA", "冻土外交紧急状态流",
          "不能被突袭、紧急状态外交支持多，靠外交点和支持慢慢赢。", "外交",
          ["参加每个紧急状态和竞赛拿外交点", "冻土城建冰球场", "商业中心 + 外交区"],
          "阿玛尼（外交）→ 雷娜（金币）",
          [S("扩到 5 座城", cities(5), 80), S("商业中心", dist("COMMERCIAL_HUB", 2), 100),
           S("任命阿玛尼", gov(AMANI), 90), S("外交区", dist("DIPLOMATIC_QUARTER"), 150)],
          civic=civics(DIPLOMATIC_SERVICE=(15, "外交"), FOREIGN_TRADE=(10, "商路"))),
        P("CIVILIZATION_CHINA_WONDER", "CIVILIZATION_CHINA", "尤里卡奇观文化流",
          "50% 尤里卡/鼓舞加速，建造者次数推远古古典奇观，后面转文化。", "文化",
          ["研究前先看尤里卡（中国给 50%）", "秦始皇：建造者次数推金字塔、兵马俑等早期奇观", "奇观城旁剧院广场"],
          "梁（建造者次数、奇观）→ 平哥拉",
          [S("石工术", tech("MASONRY"), 25), S("一个早期奇观", building("PYRAMIDS"), 70, "金字塔、空中花园、兵马俑任选"),
           S("2 座剧院广场", dist("THEATER", 2), 100), S("任命梁", gov(LIANG), 90), S("人文主义", civic("HUMANISM"), 140)],
          tech=techs(MASONRY=(15, "奇观")), civic=CULTURE_CIVIC,
          prod={"UNIT_BUILDER": (15, "建造者推奇观"), "DISTRICT_THEATER": (18, "文化")}),
        P("CIVILIZATION_CREE_TRADE", "CIVILIZATION_CREE", "陶器商路扩张流",
          "陶器送商人，早商路 + 侦察猎鹰圈地，宽扩张。", "科技",
          ["第一个商人去建路，商路带粮", "梅克瓦普营地放在资源旁", "多建城，城市挨着"],
          "马格努斯（供给）→ 雷娜",
          [S("陶器（送商人）", tech("POTTERY"), 10), S("扩到 6 座城", cities(6), 80),
           S("对外贸易", civic("FOREIGN_TRADE"), 40), S("3 座学院区", dist("CAMPUS", 3), 120)],
          tech=techs(POTTERY=(30, "送商人")) | SPACE_TECH, expand=7),
        P("CIVILIZATION_EGYPT_RIVER", "CIVILIZATION_EGYPT", "河谷奇观文化流",
          "河边区域和奇观 +15% 产能，狮身人面像加信仰文化，奇观堆旅游。", "文化",
          ["奇观和区域挨河建", "狮身人面像放在奇观旁", "拉美西斯建奇观给大量文化"],
          "梁（奇观、公园）→ 平哥拉",
          [S("石工术", tech("MASONRY"), 25), S("一个早期奇观", building("PYRAMIDS"), 70),
           S("2 座剧院广场", dist("THEATER", 2), 100), S("人文主义", civic("HUMANISM"), 140)],
          tech=techs(MASONRY=(15, "奇观"), ASTROLOGY=(10, "圣地")), civic=CULTURE_CIVIC,
          prod={"DISTRICT_THEATER": (20, "文化")}),
        P("CIVILIZATION_ENGLAND_NAVY", "CIVILIZATION_ENGLAND", "皇家船坞海上殖民流",
          "沿海扩张 + 皇家海军船坞，跨海殖民，海军压制。", "征服",
          ["沿海建城，每座都要船坞", "跨洲殖民（外大陆城市加成）", "制图学后海军压制"],
          "维克托 → 雷娜",
          [S("航海术", tech("SAILING"), 25), S("2 座港口/船坞", dist("HARBOR", 2), 90),
           S("制图学", tech("CARTOGRAPHY"), 120), S("扩到 7 座城", cities(7), 140)],
          tech=techs(SAILING=(25, "航海"), CELESTIAL_NAVIGATION=(15, "港口"), CARTOGRAPHY=(25, "跨洋")),
          prod={"DISTRICT_HARBOR": (28, "流派核心")}),
        religion_rush("CIVILIZATION_ETHIOPIA", "丘陵信仰转文化流",
                      "丘陵建城 + 改良资源换信仰，信仰转科研文化，后期信仰买考古学家。", goal="宗教/文化",
                      extra_core=["城建在丘陵上", "同一城重复资源优先改良（信仰按平方增长）", "后期信仰买考古博物馆和考古学家"],
                      after=[S("人文主义（考古博物馆）", civic("HUMANISM"), 160)],
                      civic=civics(HUMANISM=(15, "考古博物馆"), NATURAL_HISTORY=(15, "考古学家"))),
        P("CIVILIZATION_FRANCE_WONDERS", "CIVILIZATION_FRANCE", "中世纪奇观城堡旅游流",
          "中世纪以后的奇观更快，城堡（Château）挨河挨奇观给文化旅游。", "文化",
          ["河边建城，奇观和城堡都要挨河", "中世纪以后奇观产能 +20%", "间谍偷伟大作品（凯瑟琳）"],
          "梁 → 平哥拉",
          [S("2 座剧院广场", dist("THEATER", 2), 100), S("人文主义", civic("HUMANISM"), 140),
           S("任命梁", gov(LIANG), 110), S("3 座剧院广场", dist("THEATER", 3), 160)],
          civic=CULTURE_CIVIC, prod={"DISTRICT_THEATER": (22, "文化")}),
        P("CIVILIZATION_GAUL_MINES", "CIVILIZATION_GAUL", "矿山抢地奥皮杜姆速攻",
          "矿山文化炸弹抢地，奥皮杜姆早产能，盖萨泰抱团速攻。", "征服",
          ["开局采矿、多建矿山", "区域不挨市中心", "单位抱团推进"],
          "维克托 → 马格努斯",
          [S("采矿", tech("MINING"), 12), S("铁器加工（奥皮杜姆）", tech("IRON_WORKING"), 50),
           S("2 座奥皮杜姆", dist("INDUSTRIAL_ZONE", 2), 90), S("6 个军事单位", units(("GAESATAE", "SWORDSMAN", "ARCHER"), 6), 80)],
          tech=techs(MINING=(25, "矿山"), IRON_WORKING=(25, "奥皮杜姆"), BRONZE_WORKING=(12, "铁")), civic=WAR_CIVIC,
          prod={"DISTRICT_INDUSTRIAL_ZONE": (25, "奥皮杜姆")}),
        religion_rush("CIVILIZATION_GEORGIA", "城墙信仰黄金时代流",
                      "城墙给信仰，抢宗教，保持黄金时代拿双倍信仰。",
                      after=[S("每座城古城墙", building("WALLS", 3), 90)],
                      tech=techs(MASONRY=(20, "城墙信仰")), prod={"BUILDING_WALLS": (18, "城墙给信仰")}),
        chop_space("CIVILIZATION_GERMANY", "汉萨砍树飞天流",
                   "汉萨（工业区）挨商业中心和资源，马格努斯砍树推区域，多一个区域位飞天。",
                   extra_core=["汉萨挨商业中心 +2、挨资源 +1", "多一个专业区域位，早期就区域密集"],
                   prod={"DISTRICT_INDUSTRIAL_ZONE": (25, "汉萨"), "DISTRICT_COMMERCIAL_HUB": (18, "汉萨相邻")}),
        P("CIVILIZATION_GRAN_COLOMBIA_BLITZ", "CIVILIZATION_GRAN_COLOMBIA", "机动闪电战",
          "全军 +1 移动，指挥官每时代送一个，快打快撤。", "征服",
          ["每个时代送指挥官，留给关键战役", "牧马人抱团", "庄园给经济"],
          "维克托 → 马格努斯",
          [S("骑马术", tech("HORSEBACK_RIDING"), 30), S("扩到 5 座城", cities(5), 70),
           S("军事战术或马镫", tech("STIRRUPS"), 100), S("城市达到 7 座（含攻占的）", cities(7), 120)],
          tech=techs(HORSEBACK_RIDING=(20, "骑兵")), civic=WAR_CIVIC),
        P("CIVILIZATION_GREECE_ACROPOLIS", "CIVILIZATION_GREECE", "卫城城邦文化流",
          "卫城（剧院替代）建在丘陵，多一个通配槽，城邦使者加文化。", "文化",
          ["卫城放丘陵", "使者多派给城邦（伯里克利每个宗主 +5% 文化）", "通配槽放文化/伟人政策"],
          "阿玛尼 → 平哥拉",
          [S("戏剧与诗歌（卫城）", civic("DRAMA_POETRY"), 45), S("3 座卫城", dist("THEATER", 3), 100),
           S("任命阿玛尼", gov(AMANI), 80), S("人文主义", civic("HUMANISM"), 130)],
          civic=CULTURE_CIVIC, prod={"DISTRICT_THEATER": (28, "卫城")}),
        P("CIVILIZATION_HUNGARY_LEVY", "CIVILIZATION_HUNGARY", "隔河区域征召城邦流",
          "区域建在隔河一侧拿 +50% 产能，征召城邦军队打仗。", "征服/外交",
          ["区域放在和市中心隔河的地块", "多派使者拿宗主", "征召单位当主力，免费升级"],
          "阿玛尼（宗主）→ 维克托",
          [S("任命阿玛尼，多派使者拿城邦宗主", gov(AMANI), 80), S("第一座学院区（隔河放）", dist("CAMPUS"), 100),
           S("马镫（黑军）", tech("STIRRUPS"), 120)],
          tech=techs(STIRRUPS=(15, "黑军")), civic=civics(POLITICAL_PHILOSOPHY=(15, "政体"))),
        P("CIVILIZATION_INCA_TERRACE", "CIVILIZATION_INCA", "梯田山地人口飞天流",
          "山地梯田堆人口，学院区挨山，奇帕卡班丘高地人口转科研。", "科技",
          ["山边建城，梯田挨淡水、挨山", "学院区挨山", "人口越多科研越高"],
          "平哥拉 → 马格努斯",
          [S("扩到 5 座城", cities(5), 70), S("3 座学院区", dist("CAMPUS", 3), 100),
           S("教育", tech("EDUCATION"), 110), S("太空港", dist("SPACEPORT"), 230)],
          tech=SPACE_TECH, prod={"DISTRICT_CAMPUS": (25, "流派核心")}),
        religion_rush("CIVILIZATION_INDIA", "阶梯井和平宗教流",
                      "阶梯井保人口，宗教传播 + 跟随者信条叠加（印度能吃所有宗教的跟随者信条）。",
                      extra_core=["阶梯井放在农田旁", "让多个宗教进入你的城市（每个宗教的跟随者信条都生效）"]),
        P("CIVILIZATION_INDONESIA_SEA", "CIVILIZATION_INDONESIA", "海上信仰舰队流",
          "沿海圣地出信仰，信仰买海军打沿海城市。", "征服/宗教",
          ["城沿海，区域挨海", "信仰买江（海军远程）", "甘榜加粮锤"],
          "莫克夏 → 维克托",
          [S("航海术", tech("SAILING"), 25), S("沿海圣地", dist("HOLY_SITE"), 50),
           S("创立宗教", religion(), 80), S("港口", dist("HARBOR", 2), 100)],
          tech=techs(SAILING=(25, "海"), ASTROLOGY=(25, "圣地"), SHIPBUILDING=(15, "海军")),
          prod={"DISTRICT_HOLY_SITE": (25, "信仰"), "DISTRICT_HARBOR": (20, "海军")}),
        P("CIVILIZATION_JAPAN_DISTRICTS", "CIVILIZATION_JAPAN", "区域抱团电子厂流",
          "区域挨区域多 +1，城市挤着建，后期电子厂文化。", "文化/科技",
          ["区域成团摆放（日本每个相邻区域 +1）", "城市间距 3-4 格", "工业区 → 电子厂"],
          "马格努斯 → 平哥拉",
          [S("扩到 6 座城", cities(6), 80), S("3 座学院区", dist("CAMPUS", 3), 100),
           S("3 座剧院广场", dist("THEATER", 3), 140), S("3 座工业区", dist("INDUSTRIAL_ZONE", 3), 170)],
          tech=SPACE_TECH, civic=CULTURE_CIVIC, expand=7),
        religion_rush("CIVILIZATION_KHMER", "引水渠信仰遗物流",
                      "河边圣地 + 引水渠农场信仰，普拉萨特传教士殉道得遗物。", goal="宗教/文化",
                      after=[S("引水渠", dist("AQUEDUCT", 2), 110)],
                      tech=techs(ENGINEERING=(20, "引水渠")), prod={"DISTRICT_AQUEDUCT": (20, "农场信仰 + 宜居")}),
        P("CIVILIZATION_KONGO_RELICS", "CIVILIZATION_KONGO", "遗物伟大作品文化流",
          "不能创教但遗物和伟大作品产出翻倍，姆班扎雨林城人口大。", "文化",
          ["别人的宗教传进来就行，信仰用来买伟人和使徒", "剧院广场放满作品", "姆班扎（社区替代）建在雨林/森林"],
          "平哥拉（策展人）→ 莫克夏",
          [S("2 座剧院广场", dist("THEATER", 2), 90), S("扩到 5 座城", cities(5), 80),
           S("人文主义", civic("HUMANISM"), 140), S("任命平哥拉", gov(PINGALA), 110)],
          civic=CULTURE_CIVIC, prod={"DISTRICT_THEATER": (25, "伟大作品")},
          avoid=["建圣地抢宗教（刚果不能创教）"]),
        P("CIVILIZATION_KOREA_SEOWON", "CIVILIZATION_KOREA", "书院飞天流",
          "书院（学院区替代）放在没有其他区域相邻的丘陵，基础 +4 科研。", "科技",
          ["书院独立放（相邻区域会扣它）", "矿山挨书院加科研", "人口多科研多"],
          "平哥拉 → 马格努斯",
          [S("书写", tech("WRITING"), 25), S("3 座书院", dist("CAMPUS", 3), 90),
           S("教育", tech("EDUCATION"), 110), S("太空港", dist("SPACEPORT"), 220)],
          tech=SPACE_TECH, prod={"DISTRICT_CAMPUS": (30, "书院")}, expand=6),
        P("CIVILIZATION_MACEDON_CONQUEST", "CIVILIZATION_MACEDON", "亚历山大不停征服流",
          "不厌战，占城就送奖励，一路打下去。", "征服",
          ["方阵骑兵 + 赫泰罗伊（同伴骑兵）推进", "军营 + 兵营出伟人", "每攻下一座有奇观的城都有奖励"],
          "维克托 → 马格努斯",
          [S("青铜器", tech("BRONZE_WORKING"), 30), S("军营", dist("ENCAMPMENT"), 50),
           S("8 个军事单位", units(("HYPASPIST", "HETAIROI", "SWORDSMAN", "ARCHER", "CATAPULT"), 8), 90),
           S("城市达到 5 座（含攻占的）", cities(5), 100)],
          tech=techs(BRONZE_WORKING=(20, "军营"), IRON_WORKING=(20, "持盾卫士"), HORSEBACK_RIDING=(15, "同伴骑兵")),
          civic=WAR_CIVIC, prod={"DISTRICT_ENCAMPMENT": (25, "流派核心")}),
        P("CIVILIZATION_MALI_FAITHBUY", "CIVILIZATION_MALI", "沙漠信仰购买流",
          "锤子只造区域和奇观，单位建筑用金币信仰买；宗教取胜。", "宗教",
          ["沙漠挨城市中心给粮信仰", "苏古巴挨圣地 +2 金", "曼萨：国际商路金币"],
          "雷娜（承包商：金币买区域）→ 莫克夏（信仰买区域）",
          [S("占星术", tech("ASTROLOGY"), 20), S("圣地", dist("HOLY_SITE"), 40), S("创立宗教", religion(), 65),
           S("货币（苏古巴）", tech("CURRENCY"), 60), S("2 座苏古巴", dist("COMMERCIAL_HUB", 2), 100)],
          tech=RELIGION_TECH | techs(CURRENCY=(25, "苏古巴")), civic=RELIGION_CIVIC | civics(FOREIGN_TRADE=(20, "商路")),
          prod={"DISTRICT_HOLY_SITE": (30, "宗教"), "DISTRICT_COMMERCIAL_HUB": (25, "苏古巴")},
          broken=[(NO_RELIGION_SLOT, "宗教名额已经被抢光，转外交或文化")],
          avoid=["手造单位和建筑（-30%，用金币/信仰买）"]),
        religion_rush("CIVILIZATION_MAORI", "森林马拉埃信仰流",
                      "不砍林，海上挑好地建首都，信仰和马拉埃转文化。", goal="宗教/文化",
                      extra_core=["绝对不砍树（毛利不能采伐，森林本身有锤）"]),
        P("CIVILIZATION_MAPUCHE_GOLDEN", "CIVILIZATION_MAPUCHE", "黄金时代反制征服流",
          "对方进黄金时代就打（+10），总督压忠诚夺城。", "征服",
          ["盯住邻居的时代状态", "总督派到边境城", "契马穆尔放高魅力"],
          "维克托 → 梁 → 平哥拉",
          [S("扩到 4 座城", cities(4), 60), S("2 个总督", gov(VICTOR), 90),
           S("火药", tech("GUNPOWDER"), 160)],
          tech=techs(GUNPOWDER=(20, "马隆突袭者路线")), civic=WAR_CIVIC),
        P("CIVILIZATION_MAYA_SIX", "CIVILIZATION_MAYA", "六格内天文台飞天流",
          "所有城挤在首都 6 格内，天文台周围铺农场种植园。", "科技",
          ["只在首都 6 格内建城", "天文台挨农场/种植园", "农场给住房，人口快"],
          "平哥拉 → 马格努斯",
          [S("扩到 6 座城（都在 6 格内）", cities(6), 80), S("3 座天文台", dist("CAMPUS", 3), 100),
           S("教育", tech("EDUCATION"), 110), S("太空港", dist("SPACEPORT"), 220)],
          tech=SPACE_TECH, prod={"DISTRICT_CAMPUS": (28, "天文台")}, expand=7,
          avoid=["在首都 6 格外建城（-15%）"]),
        P("CIVILIZATION_MONGOLIA_HORDE", "CIVILIZATION_MONGOLIA", "驿站骑兵征服流",
          "先派商路拿外交可见度加成，再用骑兵打。", "征服",
          ["开战前往目标派商人或代表团", "斡耳朵（军营）出骑兵", "找马"],
          "维克托 → 雷娜",
          [S("骑马术", tech("HORSEBACK_RIDING"), 30), S("对外贸易", civic("FOREIGN_TRADE"), 50),
           S("斡耳朵", dist("ENCAMPMENT"), 70), S("马镫", tech("STIRRUPS"), 110)],
          tech=techs(HORSEBACK_RIDING=(25, "骑兵"), STIRRUPS=(20, "骑士")), civic=WAR_CIVIC | civics(FOREIGN_TRADE=(20, "商路")),
          prod={"DISTRICT_ENCAMPMENT": (25, "斡耳朵")}),
        chop_space("CIVILIZATION_NETHERLANDS", "河边区域砍树飞天流",
                   "学院区、工业区挨河 +2，马格努斯砍树推区域，圩田补粮。",
                   extra_core=["学院区和工业区挨河", "沿海先建港口抢海面"]),
        P("CIVILIZATION_NORWAY_RAID", "CIVILIZATION_NORWAY", "长船劫掠狂战士流",
          "早长船沿海突袭，中世纪狂战士陆战。", "征服",
          ["航海术后早出长船（时代分 + 突袭）", "森林留给木板教堂", "狂战士配攻城"],
          "维克托 → 阿玛尼",
          [S("航海术", tech("SAILING"), 20), S("2 艘长船", units(("LONGSHIP",), 2), 40),
           S("军事战术（狂战士）", tech("MILITARY_TACTICS"), 110), S("6 个狂战士", units(("BERSERKER",), 6), 140)],
          tech=techs(SAILING=(25, "长船"), MILITARY_TACTICS=(25, "狂战士")), civic=WAR_CIVIC),
        P("CIVILIZATION_NUBIA_ARCHERS", "CIVILIZATION_NUBIA", "皮塔提弓箭手速攻",
          "投石兵 → 弓术 → 皮塔提弓箭手配近战速攻邻居。", "征服",
          ["第一个生产投石兵", "弓箭手 +30% 产能，配 2 个近战负责占城", "金字塔放沙漠"],
          "梁 → 维克托",
          [S("弓术", tech("ARCHERY"), 20), S("4 个皮塔提弓箭手", units(("PITATI", "ARCHER"), 4), 40),
           S("城市达到 3 座（含攻占的）", cities(3), 60), S("第一座学院区", dist("CAMPUS"), 90)],
          tech=techs(ARCHERY=(35, "皮塔提")), civic=WAR_CIVIC, prod={"UNIT_NUBIAN_PITATI": (35, "流派核心")}),
        P("CIVILIZATION_OTTOMAN_SIEGE", "CIVILIZATION_OTTOMAN", "投石机速攻→耶尼切里",
          "工程学投石机配弓箭手速攻，文艺复兴耶尼切里 + 射石炮。", "征服",
          ["攻城单位 +50% 产能", "易卜拉欣跟着前线（10 格）", "占领城保留人口"],
          "易卜拉欣（军事总指挥）→ 维克托",
          [S("书写", tech("WRITING"), 25), S("工程学（投石机）", tech("ENGINEERING"), 70),
           S("3 个投石机", units(("CATAPULT",), 3), 85), S("任命易卜拉欣", gov("GOVERNOR_IBRAHIM"), 90),
           S("火药（耶尼切里）", tech("GUNPOWDER"), 150)],
          tech=techs(ENGINEERING=(30, "投石机"), GUNPOWDER=(25, "耶尼切里")), civic=WAR_CIVIC),
        P("CIVILIZATION_PERSIA_IMMORTAL", "CIVILIZATION_PERSIA", "长生军突然宣战流",
          "长生军配攻城槌，突然宣战拿 10 回合移动加成斩首。", "征服",
          ["铁器 → 长生军", "居鲁士：准备好再突袭", "天堂花园放商业中心/圣地相邻"],
          "梁 → 维克托",
          [S("铁器加工", tech("IRON_WORKING"), 40), S("5 个长生军", units(("IMMORTAL",), 5), 65),
           S("寡头政体", government("OLIGARCHY"), 60), S("城市达到 5 座（含攻占的）", cities(5), 90)],
          tech=techs(BRONZE_WORKING=(15, "找铁"), IRON_WORKING=(30, "长生军"), MASONRY=(10, "攻城槌")), civic=WAR_CIVIC,
          prod={"UNIT_PERSIAN_IMMORTAL": (35, "流派核心")}),
        P("CIVILIZATION_PHOENICIA_COAST", "CIVILIZATION_PHOENICIA", "沿海殖民迁都流",
          "沿海狂扩张（本大陆沿海城满忠诚），科森加速开拓者。", "征服/科技",
          ["每座城都沿海", "科森城专门出开拓者", "中期考虑迁都"],
          "马格努斯（供给）→ 雷娜",
          [S("航海术", tech("SAILING"), 25), S("扩到 6 座沿海城", cities(6), 80),
           S("天文导航（科森）", tech("CELESTIAL_NAVIGATION"), 60), S("科森", dist("HARBOR"), 80)],
          tech=techs(SAILING=(20, "海"), CELESTIAL_NAVIGATION=(30, "科森")), prod={"DISTRICT_HARBOR": (25, "科森")}, expand=8),
        religion_rush("CIVILIZATION_POLAND", "遗物文化炸弹宗教流",
                      "启示拿先知，圣物匣遗物，军营文化炸弹抢地转化。",
                      extra_core=["军营放离市中心两格", "信条拿圣物匣和十字军"],
                      after=[S("重商主义（翼骑兵）", civic("MERCANTILISM"), 170)],
                      prod={"DISTRICT_ENCAMPMENT": (15, "文化炸弹")}),
        P("CIVILIZATION_PORTUGAL_TRADE", "CIVILIZATION_PORTUGAL", "商路航海学校飞天流",
          "国际商路 +50%，沿海商路滚金币，航海学校科研。", "科技",
          ["沿海城和港口", "多建商人，商路去沿海城", "航海学校替代大学"],
          "雷娜 → 平哥拉",
          [S("航海术", tech("SAILING"), 25), S("对外贸易", civic("FOREIGN_TRADE"), 45),
           S("2 座港口", dist("HARBOR", 2), 90), S("3 座学院区", dist("CAMPUS", 3), 120),
           S("太空港", dist("SPACEPORT"), 230)],
          tech=SPACE_TECH | techs(SAILING=(20, "海"), CELESTIAL_NAVIGATION=(20, "港口")),
          civic=civics(FOREIGN_TRADE=(25, "商路")), prod={"DISTRICT_HARBOR": (25, "港口"), "UNIT_TRADER": (20, "商路")}),
        P("CIVILIZATION_ROME_LEGION", "CIVILIZATION_ROME", "军团速推流",
          "铁器出军团，寡头 +4，攻城槌打城，每座城自带道路。", "征服",
          ["找铁", "军团配攻城槌", "图拉真：多建城拿纪念碑"],
          "维克托 → 马格努斯",
          [S("铁器加工", tech("IRON_WORKING"), 40), S("5 个军团", units(("LEGION",), 5), 70),
           S("寡头政体", government("OLIGARCHY"), 60), S("城市达到 5 座（含攻占的）", cities(5), 90)],
          tech=techs(BRONZE_WORKING=(15, "找铁"), IRON_WORKING=(30, "军团"), MASONRY=(12, "攻城槌")), civic=WAR_CIVIC,
          prod={"UNIT_ROMAN_LEGION": (35, "流派核心")}),
        religion_rush("CIVILIZATION_RUSSIA", "修道院宗教流",
                      "半价修道院先知点多，冻土扩张，极光之舞。",
                      extra_core=["城建在冻土与草原交界", "万神殿极光之舞"], expand=6),
        chop_space("CIVILIZATION_SCOTLAND", "高尔夫宜居砍树飞天流",
                   "宜居拉满拿科研产能加成，马格努斯砍树推学院和工业区。",
                   extra_core=["每座城高尔夫球场", "宜居 +5 以上狂喜"]),
        P("CIVILIZATION_SCYTHIA_HORSE", "CIVILIZATION_SCYTHIA", "双倍骑手速攻流",
          "骑手造一送二，骑射手削血、骑手占城。", "征服",
          ["畜牧业找马", "骑手为主、萨卡削血", "打残血敌人 +5，击杀回血"],
          "马格努斯（产能）→ 维克托",
          [S("骑马术", tech("HORSEBACK_RIDING"), 20), S("6 个骑兵", units(("HORSEMAN", "SAKA"), 6), 45),
           S("城市达到 4 座（含攻占的）", cities(4), 70)],
          tech=techs(ANIMAL_HUSBANDRY=(20, "马"), HORSEBACK_RIDING=(35, "骑手")), civic=WAR_CIVIC,
          prod={"UNIT_HORSEMAN": (30, "造一送二"), "UNIT_SCYTHIAN_HORSE_ARCHER": (20, "削血")}),
        religion_rush("CIVILIZATION_SPAIN", "征服者传教外大陆流",
                      "创教后跨洋殖民，征服者配宗教单位征服转化。", goal="宗教/征服",
                      after=[S("制图学（跨洋）", tech("CARTOGRAPHY"), 130), S("火药（征服者）", tech("GUNPOWDER"), 160)],
                      tech=techs(CARTOGRAPHY=(20, "外大陆"), GUNPOWDER=(15, "征服者"))),
        P("CIVILIZATION_SUMERIA_CART", "CIVILIZATION_SUMERIA", "开局战车速攻",
          "开局战车清营地、打最近的邻居，窗口在剑士城墙出现前。", "征服",
          ["第一个生产战车", "战车清蛮族营地拿奖励", "塔庙铺河边"],
          "阿玛尼 → 平哥拉",
          [S("3 辆战车", units(("WAR_CART",), 3), 25), S("城市达到 3 座（含攻占的）", cities(3), 45),
           S("扩到 5 座城", cities(5), 70)],
          civic=WAR_CIVIC, prod={"UNIT_SUMERIAN_WAR_CART": (40, "流派核心")}),
        P("CIVILIZATION_SWEDEN_MUSEUM", "CIVILIZATION_SWEDEN", "露天博物馆伟人外交流",
          "城市覆盖多种地形，伟人换外交支持，女王图书馆塞作品。", "文化/外交",
          ["沙漠/草原/平原/雪地/冻土各一座城", "伟人越多外交支持越多", "别主动开战"],
          "平哥拉 → 阿玛尼",
          [S("扩到 6 座城（覆盖多种地形）", cities(6), 90), S("2 座剧院广场", dist("THEATER", 2), 100),
           S("市政广场（女王图书馆）", dist("GOVERNMENT"), 110), S("民族主义（露天博物馆）", civic("NATIONALISM"), 170)],
          civic=CULTURE_CIVIC | civics(NATIONALISM=(15, "露天博物馆")), prod={"DISTRICT_THEATER": (20, "作品槽")}, expand=7),
        P("CIVILIZATION_VIETNAM_FOREST", "CIVILIZATION_VIETNAM", "林地区域文化流",
          "区域只建在有地貌的地块，林地区域产出高，成（Thành）挨区域给文化。", "文化",
          ["绝对不砍树", "区域都放在森林/雨林/沼泽", "成放在区域团中间"],
          "梁 → 平哥拉",
          [S("2 座剧院广场", dist("THEATER", 2), 100), S("2 座学院区", dist("CAMPUS", 2), 100),
           S("人文主义", civic("HUMANISM"), 140)],
          civic=CULTURE_CIVIC, prod={"DISTRICT_THEATER": (22, "文化")}, avoid=["砍伐地貌"]),
        P("CIVILIZATION_ZULU_CORPS", "CIVILIZATION_ZULU", "军团滚雪球流",
          "攻城时让单位占城免费升军团，伊坎达早出军团。", "征服",
          ["因皮配弓箭手推", "让要升级的单位去占城", "城内驻军加忠诚"],
          "维克托 → 马格努斯",
          [S("8 个军事单位", units(("IMPI", "SPEARMAN", "ARCHER", "SWORDSMAN"), 8), 70),
           S("城市达到 5 座（含攻占的）", cities(5), 90), S("伊坎达", dist("ENCAMPMENT"), 100), S("雇佣兵（军团）", civic("MERCENARIES"), 130)],
          tech=techs(BRONZE_WORKING=(12, "军营")), civic=WAR_CIVIC | civics(MERCENARIES=(25, "军团")),
          prod={"DISTRICT_ENCAMPMENT": (25, "伊坎达")}),
    ]
    return out


PLAYSTYLES: dict[str, Playstyle] = {p.civ: p for p in _all()}
BY_ID: dict[str, Playstyle] = {p.id: p for p in PLAYSTYLES.values()}


def playstyle_for(civ_type: str | None) -> Playstyle | None:
    return PLAYSTYLES.get(civ_type or "")


def active(sit) -> Playstyle | None:
    """局势里开启了的流派（玩家点了按钮）。"""
    pid = getattr(sit, "playstyle", None)
    return BY_ID.get(pid) if pid else None


# ------------------------------------------------------------------ 进度检查


def _district_count(sit, generic: str) -> int:
    from civ6_advisor.production import _has_district

    return sum(1 for c in sit.cities if _has_district(c, generic))


def check(cond: tuple, sit) -> bool | None:
    """条件是否已满足；读不到数据时返回 None。"""
    kind = cond[0]
    f = sit.facts
    if kind == "tech":
        if f is not None and f.techs:
            return cond[1] in f.techs
        return None
    if kind == "civic":
        if f is not None and f.civics:
            return cond[1] in f.civics
        return None
    if kind == "cities":
        return len(sit.cities) >= cond[1]
    if kind == "district":
        return _district_count(sit, cond[1]) >= cond[2]
    if kind == "religion":
        return bool(sit.overview.our_religion)
    if kind == "governor":
        if sit.governors is None:
            return None
        return any(g.governor_type == cond[1] for g in sit.governors.appointed)
    if kind == "building":
        b, n = cond[1], cond[2]
        return sum(1 for c in sit.cities if any(x.upper().removeprefix("BUILDING_").endswith(b) for x in (c.buildings or []))) >= n
    if kind == "units":
        keys, n = cond[1], cond[2]
        return sum(1 for u in sit.units if any(k in u.unit_type.upper() for k in keys)) >= n
    if kind == "government":
        g = sit.government
        return None if g is None else cond[1] in (g.government_type or "").upper()
    if kind == "no_religion_slot":
        o = sit.overview
        return not o.our_religion and o.religions_max > 0 and o.religions_founded >= o.religions_max
    return None


@dataclass
class Progress:
    ps: Playstyle
    done: list[Step]
    todo: list[Step]
    late: list[Step]  # 已经过了建议回合还没完成
    broken: list[str]

    @property
    def next(self) -> Step | None:
        return self.todo[0] if self.todo else None

    def summary(self) -> str:
        n, total = len(self.done), len(self.done) + len(self.todo)
        s = f"进度 {n}/{total}"
        if self.next:
            s += f" · 下一步：{self.next.text}"
        return s


def progress(ps: Playstyle, sit) -> Progress:
    done, todo, late = [], [], []
    mult = (getattr(sit.overview, "speed_cost_multiplier", 100) or 100) / 100
    turn = sit.overview.turn / mult  # 折算成标准速度回合
    for s in ps.steps:
        ok = check(s.cond, sit)
        if ok:
            done.append(s)
        else:
            todo.append(s)
            if s.by and turn > s.by:
                late.append(s)
    broken = [why for cond, why in ps.broken if check(cond, sit)]
    return Progress(ps, done, todo, late, broken)


def brief_section(sit) -> str:
    """给 AI 的流派段落（只在开启时）。"""
    ps = active(sit)
    if not ps:
        return ""
    pr = progress(ps, sit)
    lines = ["## 玩家选择的流派", ps.describe(), "", f"当前{pr.summary()}"]
    if pr.done:
        lines.append("已完成：" + "、".join(s.text for s in pr.done))
    if pr.late:
        lines.append("落后于计划：" + "、".join(f"{s.text}（建议第 {s.by} 回合前）" for s in pr.late))
    if pr.broken:
        lines.append("流派前提问题：" + "；".join(pr.broken))
    return "\n".join(lines)
