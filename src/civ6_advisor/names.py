"""常见单位、资源的中文名（游戏内部类型名 → 中文）。没收录的保持原样。"""

from __future__ import annotations

UNITS = {
    "WARRIOR": "勇士", "SLINGER": "投石兵", "ARCHER": "弓箭手", "SPEARMAN": "枪兵", "HEAVY_CHARIOT": "重型战车",
    "HORSEMAN": "骑手", "HORSE_ARCHER": "骑射手", "SWORDSMAN": "剑士", "CATAPULT": "投石机", "GALLEY": "桨帆船",
    "QUADRIREME": "四段帆船", "SCOUT": "侦察兵", "BUILDER": "建造者", "SETTLER": "开拓者", "TRADER": "商人",
    "MAN_AT_ARMS": "重装步兵", "CROSSBOWMAN": "弩手", "PIKEMAN": "长枪兵", "KNIGHT": "骑士", "TREBUCHET": "抛石机",
    "COURSER": "轻骑兵", "MUSKETMAN": "火枪手", "BOMBARD": "射石炮", "FIELD_CANNON": "野战炮", "CAVALRY": "骑兵",
    "CUIRASSIER": "胸甲骑兵", "LINE_INFANTRY": "线列步兵", "PIKE_AND_SHOT": "长矛火枪兵", "INFANTRY": "步兵",
    "ARTILLERY": "火炮", "TANK": "坦克", "MACHINE_GUN": "机枪", "ANTI_TANK_GUN": "反坦克炮", "AT_CREW": "反坦克炮",
    "MODERN_ARMOR": "现代装甲", "MECHANIZED_INFANTRY": "机械化步兵", "ROCKET_ARTILLERY": "火箭炮",
    "FRIGATE": "护卫舰", "IRONCLAD": "铁甲舰", "DESTROYER": "驱逐舰", "BATTLESHIP": "战列舰", "SUBMARINE": "潜艇",
    "PRIVATEER": "私掠船", "CARAVEL": "轻帆船", "AIRCRAFT_CARRIER": "航空母舰", "BIPLANE": "双翼飞机",
    "FIGHTER": "战斗机", "BOMBER": "轰炸机", "MISSIONARY": "传教士", "APOSTLE": "使徒", "SPY": "间谍",
    "RANGER": "游侠", "SPEC_OPS": "特种部队", "MILITARY_ENGINEER": "军事工程师", "ARCHAEOLOGIST": "考古学家",
    "NATURALIST": "自然学家", "MEDIC": "医疗兵", "SUPPLY_CONVOY": "补给车队", "BATTERING_RAM": "攻城槌",
    "SIEGE_TOWER": "攻城塔", "OBSERVATION_BALLOON": "观测气球", "GIANT_DEATH_ROBOT": "巨型死亡机器人",
}

RESOURCES = {
    "IRON": "铁", "HORSES": "马", "NITER": "硝石", "COAL": "煤", "OIL": "石油", "ALUMINUM": "铝", "URANIUM": "铀",
    "WHEAT": "小麦", "RICE": "稻米", "CATTLE": "牛", "SHEEP": "羊", "DEER": "鹿", "BANANAS": "香蕉", "FISH": "鱼",
    "CRABS": "螃蟹", "STONE": "石头", "COPPER": "铜", "MAIZE": "玉米",
    "IVORY": "象牙", "SILK": "丝绸", "WINE": "葡萄酒", "SPICES": "香料", "SUGAR": "糖", "TEA": "茶", "COFFEE": "咖啡",
    "COTTON": "棉花", "DYES": "染料", "FURS": "皮毛", "INCENSE": "熏香", "JADE": "玉石", "MARBLE": "大理石",
    "MERCURY": "水银", "PEARLS": "珍珠", "SALT": "盐", "SILVER": "银", "GOLD": "黄金", "DIAMONDS": "钻石",
    "TOBACCO": "烟草", "TRUFFLES": "松露", "WHALES": "鲸鱼", "CITRUS": "柑橘", "COCOA": "可可", "GYPSUM": "石膏",
    "AMBER": "琥珀", "OLIVES": "橄榄", "HONEY": "蜂蜜", "TURTLES": "海龟",
}


def unit_cn(unit_type: str) -> str:
    key = unit_type.upper().removeprefix("UNIT_").removeprefix("BARBARIAN_")
    return UNITS.get(key, key.replace("_", " ").title())


def resource_cn(name: str) -> str:
    key = name.upper().removeprefix("RESOURCE_")
    return RESOURCES.get(key, key.title())


BUILDINGS = {
    "PALACE": "宫殿", "MONUMENT": "纪念碑", "GRANARY": "粮仓", "WATER_MILL": "水磨", "WALLS": "古城墙",
    "CASTLE": "中世纪城墙", "STAR_FORT": "星形要塞", "SHRINE": "神社", "TEMPLE": "神庙", "LIBRARY": "图书馆",
    "UNIVERSITY": "大学", "RESEARCH_LAB": "研究实验室", "MARKET": "市场", "BANK": "银行", "STOCK_EXCHANGE": "证券交易所",
    "AMPHITHEATER": "圆形剧场", "MUSEUM_ART": "艺术博物馆", "MUSEUM_ARTIFACT": "考古博物馆", "ARENA": "竞技场",
    "ZOO": "动物园", "BARRACKS": "兵营", "STABLE": "马厩", "ARMORY": "军械库", "LIGHTHOUSE": "灯塔",
    "SHIPYARD": "造船厂", "WORKSHOP": "工作坊", "FACTORY": "工厂", "POWER_PLANT": "发电厂", "SEWER": "下水道",
    "BROADCAST_CENTER": "广播中心", "AIRPORT": "机场", "HANGAR": "机库",
}

DISTRICTS = {
    "CITY_CENTER": "市中心", "CAMPUS": "学院区", "THEATER": "剧院广场", "HOLY_SITE": "圣地",
    "COMMERCIAL_HUB": "商业中心", "HARBOR": "港口", "INDUSTRIAL_ZONE": "工业区", "ENCAMPMENT": "军营",
    "ENTERTAINMENT_COMPLEX": "娱乐中心", "WATER_ENTERTAINMENT_COMPLEX": "水上乐园", "AQUEDUCT": "引水渠",
    "NEIGHBORHOOD": "社区", "SPACEPORT": "太空港", "GOVERNMENT": "市政广场", "DIPLOMATIC_QUARTER": "外交区",
    "DAM": "水坝", "CANAL": "运河", "AERODROME": "航空港", "PRESERVE": "保护区",
}


def production_cn(item: str | None) -> str:
    """生产项类型名 → 中文。空闲返回 ''，项目（无法识别）返回 '城市项目'。"""
    if not item or item.lower() in ("nothing", "none"):
        return ""
    if item == "UNKNOWN":
        return "城市项目"
    if item.startswith("UNIT_"):
        return unit_cn(item)
    if item.startswith("BUILDING_"):
        k = item.removeprefix("BUILDING_")
        return BUILDINGS.get(k, k.replace("_", " ").title())
    if item.startswith("DISTRICT_"):
        k = item.removeprefix("DISTRICT_")
        return DISTRICTS.get(k, k.replace("_", " ").title())
    if item.startswith("PROJECT_"):
        return "城市项目"
    return item  # 已经是中文或其他格式


def is_idle(item: str | None) -> bool:
    return not item or item.lower() in ("nothing", "none")


# 没导出游戏资料库时的兜底中文名（远古到中世纪常用的）
TECH_CIVIC_CN = {
    "TECH_POTTERY": "制陶术", "TECH_ANIMAL_HUSBANDRY": "畜牧业", "TECH_MINING": "采矿业", "TECH_SAILING": "航海术",
    "TECH_ASTROLOGY": "占星术", "TECH_IRRIGATION": "灌溉", "TECH_WRITING": "书写", "TECH_ARCHERY": "弓术",
    "TECH_MASONRY": "石工术", "TECH_BRONZE_WORKING": "青铜器", "TECH_THE_WHEEL": "轮子", "TECH_CURRENCY": "货币",
    "TECH_CELESTIAL_NAVIGATION": "天文导航", "TECH_HORSEBACK_RIDING": "骑马术", "TECH_IRON_WORKING": "铁器加工",
    "TECH_SHIPBUILDING": "造船术", "TECH_MATHEMATICS": "数学", "TECH_CONSTRUCTION": "建造", "TECH_ENGINEERING": "工程学",
    "TECH_APPRENTICESHIP": "学徒", "TECH_MACHINERY": "机械", "TECH_EDUCATION": "教育", "TECH_STIRRUPS": "马镫",
    "TECH_MILITARY_TACTICS": "军事战术", "TECH_MILITARY_ENGINEERING": "军事工程", "TECH_CASTLES": "城堡",
    "TECH_CARTOGRAPHY": "制图学", "TECH_GUNPOWDER": "火药", "TECH_ROCKETRY": "火箭学",
    "CIVIC_CODE_OF_LAWS": "法典", "CIVIC_CRAFTSMANSHIP": "工匠技艺", "CIVIC_FOREIGN_TRADE": "对外贸易",
    "CIVIC_MILITARY_TRADITION": "军事传统", "CIVIC_STATE_WORKFORCE": "国家劳动力", "CIVIC_EARLY_EMPIRE": "早期帝国",
    "CIVIC_MYSTICISM": "神秘主义", "CIVIC_GAMES_RECREATION": "游戏与娱乐", "CIVIC_POLITICAL_PHILOSOPHY": "政治哲学",
    "CIVIC_DRAMA_POETRY": "戏剧与诗歌", "CIVIC_MILITARY_TRAINING": "军事训练", "CIVIC_DEFENSIVE_TACTICS": "防御战术",
    "CIVIC_RECORDED_HISTORY": "有记载的历史", "CIVIC_THEOLOGY": "神学", "CIVIC_NAVAL_TRADITION": "航海传统",
    "CIVIC_FEUDALISM": "封建主义", "CIVIC_CIVIL_SERVICE": "文官制度", "CIVIC_MERCENARIES": "雇佣兵",
    "CIVIC_HUMANISM": "人文主义", "CIVIC_MERCANTILISM": "重商主义", "CIVIC_NATURAL_HISTORY": "自然历史",
    "CIVIC_NATIONALISM": "民族主义", "CIVIC_CONSERVATION": "自然保护", "CIVIC_CULTURAL_HERITAGE": "文化遗产",
}


def type_name(t: str, sit=None) -> str:
    """科技/市政/改良等类型名 → 名字：先查本局可选科技市政，再查资料库，最后美化类型名。"""
    if not t:
        return ""
    if sit is not None and sit.tech:
        for o in sit.tech.available_techs:
            if o.tech_type == t:
                return o.name
        for o in sit.tech.available_civics:
            if o.civic_type == t:
                return o.name
    try:
        from civ6_advisor.kb import get_kb

        n = get_kb().names.get(t)
        if n:
            return n
    except Exception:  # noqa: BLE001
        pass
    from civ6_advisor.facts import IMPROVEMENT_CN

    if t in TECH_CIVIC_CN:
        return TECH_CIVIC_CN[t]
    if t in IMPROVEMENT_CN:
        return IMPROVEMENT_CN[t]
    if t.startswith("RESOURCE_"):
        return resource_cn(t)
    for pre in ("TECHNOLOGY_", "TECH_", "CIVIC_", "IMPROVEMENT_"):
        t = t.removeprefix(pre)
    return t.replace("_", " ").title()
