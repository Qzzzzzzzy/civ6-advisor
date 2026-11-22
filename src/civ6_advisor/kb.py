"""本地资料库：游戏数据（从游戏导出）+ 攻略文档（随软件打包）+ 文明攻略（civs.py）。

提供：
  - search(query)      模糊搜索（名字精确/包含 + 中文二元组相似度），给 AI 的查资料工具用
  - get(name_or_type)  取一个条目的完整说明
  - context_for(sit)   根据当前局势自动挑出相关条目和攻略段落，附在问 AI 的请求里
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from importlib import resources

from civ6_advisor.civs import CIVS

KIND_CN = {
    "CIV": "文明", "LEADER": "领袖", "TRAIT": "能力", "UNIT": "单位", "BUILDING": "建筑", "WONDER": "奇观",
    "DISTRICT": "区域", "IMPROVEMENT": "改良设施", "RESOURCE": "资源", "TECH": "科技", "CIVIC": "市政",
    "POLICY": "政策", "GOVERNMENT": "政体", "BELIEF": "信条", "GOVERNOR": "总督", "GOV_PROMO": "总督晋升",
    "PROJECT": "项目", "GUIDE": "攻略", "CIVGUIDE": "文明攻略",
}
ATTR_CN = {
    "cost": "花费", "combat": "近战", "ranged": "远程", "range": "射程", "bombard": "轰炸", "moves": "移动",
    "tech": "需要科技", "civic": "需要市政", "resource": "战略资源", "domain": "类型", "maint": "维护费",
    "housing": "住房", "amenity": "宜居", "district": "所在区域", "slot": "政策槽", "era": "时代",
    "boost": "尤里卡/鼓舞条件", "class": "分类", "bonus": "累积加成", "title": "头衔", "level": "等级",
}
SLOT_CN = {"SLOT_MILITARY": "军事", "SLOT_ECONOMIC": "经济", "SLOT_DIPLOMATIC": "外交", "SLOT_WILDCARD": "通配",
           "SLOT_GREAT_PERSON": "伟人", "SLOT_DARKAGE": "黑暗"}


def _bigrams(s: str) -> set[str]:
    s = re.sub(r"[\s，。、；：？！?!,.（）()【】]+", "", s.lower())
    if len(s) <= 1:
        return set(s)
    return {s[i:i + 2] for i in range(len(s) - 1)}


FILLER = re.compile(r"怎么用|怎么样|怎么办|怎么|如何|是什么|什么|有什么用|有用吗|好不好|强不强|吗|呢|的|一下|介绍|请问|[？?。!！]")


def clean_query(q: str) -> str:
    out = FILLER.sub(" ", q).strip()
    return out or q.strip()


@dataclass
class Entry:
    kind: str
    type: str
    name: str
    desc: str
    attrs: dict = field(default_factory=dict)
    extra: list[str] = field(default_factory=list)  # 关系补充（替代、相邻加成、解锁…）
    tags: set[str] = field(default_factory=set)
    _grams: set[str] | None = None
    _ngrams: set[str] | None = None

    @property
    def grams(self) -> set[str]:
        if self._grams is None:
            self._grams = _bigrams(self.name + " " + self.desc[:300] + " " + " ".join(self.tags))
        return self._grams

    @property
    def name_grams(self) -> set[str]:
        if self._ngrams is None:
            self._ngrams = _bigrams(self.name) | {t for tag in self.tags for t in _bigrams(tag)}
        return self._ngrams

    def render(self, names: dict[str, str] | None = None, limit: int = 900) -> str:
        names = names or {}
        head = f"【{KIND_CN.get(self.kind, self.kind)}】{self.name}" + (f"（{self.type}）" if self.type else "")
        lines = [head]
        if self.desc:
            lines.append(self.desc)
        attrs = []
        for k, v in self.attrs.items():
            if k in ("trait", "faith", "specialty"):
                continue
            if k in ("tech", "civic", "district", "resource") and v in names:
                v = names[v]
            if k == "slot":
                v = SLOT_CN.get(v, v)
            attrs.append(f"{ATTR_CN.get(k, k)}：{v}")
        if attrs:
            lines.append("；".join(attrs))
        lines += self.extra
        text = "\n".join(lines)
        return text if len(text) <= limit else text[: limit - 1] + "…"


@dataclass
class CivDoc:
    civ_type: str
    title: str          # 首行标题，如「埃塞俄比亚（CIVILIZATION_ETHIOPIA）· 领袖：孟尼利克二世」
    text: str
    sections: dict[str, str]
    aliases: list[str] = field(default_factory=list)

    def section(self, name: str) -> str:
        if name in self.sections:
            return self.sections[name]
        for k, v in self.sections.items():  # 「对手是X时」这类标题只按前缀匹配
            if k.startswith(name):
                return v
        return ""


def parse_civ_markdown(civ_type: str, text: str) -> CivDoc:
    lines = text.strip().splitlines()
    title = lines[0].lstrip("# ").strip() if lines else civ_type
    sections: dict[str, str] = {}
    cur, buf = "", []
    for ln in lines[1:]:
        if ln.startswith("## "):
            if cur:
                sections[cur] = "\n".join(buf).strip()
            cur, buf = ln[3:].strip(), []
        else:
            buf.append(ln)
    if cur:
        sections[cur] = "\n".join(buf).strip()
    name = re.split(r"[（(·]", title)[0].strip()
    leaders = re.findall(r"领袖：(.+)$", title)
    aliases = [name] + [x.strip() for x in re.split(r"[、，,]", leaders[0])] if leaders else [name]
    return CivDoc(civ_type, title, text.strip(), sections, [a for a in aliases if a])


def load_civ_markdown() -> dict[str, CivDoc]:
    out: dict[str, CivDoc] = {}
    folder = resources.files("civ6_advisor").joinpath("knowledge/civs")
    try:
        items = list(folder.iterdir())
    except (FileNotFoundError, NotADirectoryError):
        return out
    for f in items:
        n = f.name
        if n.endswith(".md") and n.startswith("CIVILIZATION_"):
            t = n[:-3]
            out[t] = parse_civ_markdown(t, f.read_text(encoding="utf-8"))
    return out


class KnowledgeBase:
    def __init__(self, game_data: dict | None = None):
        self.entries: list[Entry] = []
        self.by_type: dict[str, Entry] = {}
        self.by_name: dict[str, list[Entry]] = {}
        self.names: dict[str, str] = {}  # 类型名 → 名字
        self.has_game_data = False
        self.civ_docs: dict[str, CivDoc] = {}
        self._load_guides()
        self._load_civ_guides()
        if game_data:
            self._load_game(game_data)

    # ---------------- 加载

    def _add(self, e: Entry):
        self.entries.append(e)
        if e.type:
            self.by_type[e.type] = e
            self.names.setdefault(e.type, e.name)
        self.by_name.setdefault(e.name.lower(), []).append(e)

    def _load_guides(self):
        text = resources.files("civ6_advisor").joinpath("knowledge/strategy.md").read_text(encoding="utf-8")
        for block in re.split(r"\n(?=## )", text):
            if not block.startswith("## "):
                continue
            lines = block.strip().splitlines()
            title = lines[0][3:].strip()
            tags = set()
            body = []
            for ln in lines[1:]:
                if ln.startswith("标签："):
                    tags = {t.strip() for t in ln[3:].split(",") if t.strip()}
                else:
                    body.append(ln)
            self._add(Entry("GUIDE", "", title, "\n".join(body).strip(), tags=tags))

    def _load_civ_guides(self):
        """文明攻略：knowledge/civs/<文明类型>.md（联网整理的详细攻略）优先，
        civs.py 里的简要档案作为补充（没有 md 的文明就只用档案）。"""
        from civ6_advisor.playstyles import PLAYSTYLES

        md = load_civ_markdown()
        for t, p in CIVS.items():
            lines = [f"倾向：{'/'.join(p.focus)}；宗教：{p.religion}；前期目标城市数约 {p.expand}", f"特色：{p.traits}"]
            lines += [f"{k}：{v}" for k, v in p.phases.items()]
            lines += [f"领袖 {ln.name}：{ln.tip}" for ln in p.leaders.values()]
            brief = "\n".join(lines)
            doc = md.pop(t, None)
            if doc:
                e = Entry("CIVGUIDE", "GUIDE_" + t, p.name + "攻略", doc.text, tags={p.name, *doc.aliases})
                e.extra.append("【简要档案】\n" + brief)
                self.civ_docs[t] = doc
            else:
                e = Entry("CIVGUIDE", "GUIDE_" + t, p.name + "攻略", brief, tags={p.name})
            ps = PLAYSTYLES.get(t)
            if ps:
                e.extra.append("【推荐流派】\n" + ps.describe())
                self._add(Entry("GUIDE", "PLAYSTYLE_" + t, ps.name, ps.describe(), tags={p.name, "流派"}))
            self._add(e)
        for t, doc in md.items():  # 档案里没有的文明（模组等）
            self.civ_docs[t] = doc
            self._add(Entry("CIVGUIDE", "GUIDE_" + t, doc.title + "攻略", doc.text, tags=set(doc.aliases)))

    def civ_excerpt(self, civ_type: str, phase: str = "", budget: int = 2800) -> str:
        """给 AI 的本文明攻略摘录：按局势挑最有用的段落，控制在预算内。"""
        doc = self.civ_docs.get(civ_type)
        if not doc:
            return ""
        order = ["速览", "关键时机", "局势 → 建议", "领袖差异"]
        order += ["开局与前期"] if phase in ("开局", "前期", "") else []
        order += ["特色怎么用", "推荐选择", "各胜利路线", "弱点与注意"]
        out = [f"【文明攻略】{doc.title}"]
        used = len(out[0])
        for name in order:
            body = doc.section(name)
            if not body:
                continue
            block = f"### {name}\n{body}"
            if used + len(block) > budget:
                room = budget - used - 20
                if room > 200:
                    out.append(block[:room].rsplit("\n", 1)[0] + "\n…")
                break
            out.append(block)
            used += len(block)
        return "\n".join(out)

    def _load_game(self, data: dict):
        for d in data.get("entries", []):
            if not d.get("name") or d["name"].startswith("LOC_"):
                continue
            self._add(Entry(d["kind"], d["type"], d["name"], d.get("desc", ""), dict(d.get("attrs", {}))))
        self.has_game_data = True
        n = self.names
        for kind, a, b in data.get("rels", []):
            ea = self.by_type.get(a)
            if kind == "REPLACES" and ea:
                ea.extra.append(f"替代：{n.get(b, b)}（这个文明不能造原版）")
                eb = self.by_type.get(b)
                if eb:
                    eb.extra.append(f"特色替代版：{ea.name}")
            elif kind == "ADJ" and ea and b:
                if len(ea.extra) < 12:
                    ea.extra.append(f"相邻加成：{b}")
            elif kind == "IMPROVES" and ea:
                ea.attrs.setdefault("improves", "")
                ea.attrs["improves"] = "、".join(x for x in (ea.attrs["improves"], n.get(b, b)) if x)
                er = self.by_type.get(b)
                if er:
                    er.extra.append(f"用「{ea.name}」改良")
            elif kind == "SLOTS" and ea:
                slot, _, cnt = b.partition("x")
                ea.extra.append(f"政策槽：{SLOT_CN.get(slot, slot)}×{cnt}")
            elif kind == "CIV_LEADER" and ea and b in self.by_type:
                ea.extra.append(f"领袖：{n.get(b, b)}")
                self.by_type[b].extra.append(f"文明：{ea.name}")
            elif kind in ("CIV_TRAIT", "LEADER_TRAIT") and ea:
                tr = self.by_type.get(b)
                if tr and tr.desc:
                    ea.extra.append(f"能力「{tr.name}」：{tr.desc}")
            elif kind == "GOV_HAS" and ea and b in self.by_type:
                p = self.by_type[b]
                ea.extra.append(f"晋升「{p.name}」：{p.desc}")
            elif kind == "PREREQ" and ea:
                ea.attrs.setdefault("前置", "")
                ea.attrs["前置"] = "、".join(x for x in (ea.attrs["前置"], n.get(b, b)) if x)
        # 科技/市政 → 解锁了什么
        unlocks: dict[str, list[str]] = {}
        for e in self.entries:
            for k in ("tech", "civic"):
                req = e.attrs.get(k)
                if req and e.kind in ("UNIT", "BUILDING", "WONDER", "DISTRICT", "IMPROVEMENT", "POLICY", "GOVERNMENT", "PROJECT"):
                    unlocks.setdefault(req, []).append(f"{KIND_CN.get(e.kind, e.kind)}{e.name}")
        for t, items in unlocks.items():
            if t in self.by_type:
                self.by_type[t].extra.append("解锁：" + "、".join(items[:12]))

    # ---------------- 查询

    def get(self, key: str) -> Entry | None:
        key = key.strip()
        if key.upper() in self.by_type:
            return self.by_type[key.upper()]
        hits = self.by_name.get(key.lower())
        if hits:
            order = ("UNIT", "BUILDING", "DISTRICT", "WONDER", "IMPROVEMENT", "TECH", "CIVIC", "POLICY",
                     "GOVERNMENT", "CIV", "LEADER", "BELIEF", "GOVERNOR", "RESOURCE", "CIVGUIDE", "GUIDE")
            return sorted(hits, key=lambda e: order.index(e.kind) if e.kind in order else 99)[0]
        res = self.search(key, k=1)
        return res[0] if res else None

    def search(self, query: str, k: int = 6, kinds: set[str] | None = None) -> list[Entry]:
        q = clean_query(query).lower()
        if not q:
            return []
        terms = [t for t in q.split() if t]
        q = "".join(terms)
        qg = _bigrams(q)
        scored = []
        for e in self.entries:
            if kinds and e.kind not in kinds:
                continue
            name = e.name.lower()
            s = 0.0
            if name == q or e.type.lower() == q:
                s = 100
            elif q in name or (len(name) >= 2 and name in q):
                s = 60 + 10 * len(name) / max(len(q), 1)
            elif q in " ".join(e.tags):
                s = 40
            elif any(len(t) >= 2 and t in name for t in terms):
                s = 50
            else:
                inter = len(qg & e.grams)
                name_hit = len(qg & e.name_grams)
                if inter or name_hit:
                    s = 25 * inter / len(qg) + 35 * name_hit / len(qg)
            if s > 6:
                scored.append((s, e))
        scored.sort(key=lambda x: -x[0])
        return [e for _, e in scored[:k]]

    def render(self, e: Entry, limit: int = 900) -> str:
        if e.kind == "CIVGUIDE":
            limit = max(limit, 6000)  # 文明攻略整篇给出
        return e.render(self.names, limit)

    # ---------------- 按局势挑资料

    def guides_for(self, tags: set[str], k: int = 4) -> list[Entry]:
        scored = []
        for e in self.entries:
            if e.kind != "GUIDE":
                continue
            hit = len(e.tags & tags)
            if hit:
                scored.append((hit, e))
        scored.sort(key=lambda x: -x[0])
        return [e for _, e in scored[:k]]

    def context_for(self, sit, budget: int = 7000) -> str:
        """当前局势最相关的资料：本文明特色、可选科技市政、空闲城市可造项目、视野内敌军、攻略段落。"""
        from civ6_advisor.civs import profile_for
        from civ6_advisor.production import city_overview
        from civ6_advisor.research import tracks
        from civ6_advisor.rules import analyze, game_phase

        parts: list[str] = []
        used = 0

        def put(text: str):
            nonlocal used
            if text and used + len(text) <= budget:
                parts.append(text)
                used += len(text)

        # 本文明攻略 + 特色内容（资料库里的完整条目，含数值和替代关系）
        if sit.civ:
            ex = self.civ_excerpt(sit.civ.civ_type, game_phase(sit), budget=min(3000, budget // 2))
            if ex:
                put(ex)
            else:
                g = self.by_type.get("GUIDE_" + sit.civ.civ_type)
                if g:
                    put(self.render(g))
            for a in sit.civ.abilities:
                if a.source in ("UNIT", "BUILDING", "DISTRICT", "IMPROVEMENT"):
                    e = self.by_type.get(a.type)
                    if e:
                        put(self.render(e, 500))
        # 科技 / 市政：推荐项和当前项
        tech, civic = tracks(sit)
        for t in (tech, civic):
            if not t:
                continue
            for p in ([t.current] if t.current else []) + t.picks[:3]:
                e = self.by_type.get(p.type) or (self.get(p.name) if p.name else None)
                if e:
                    put(self.render(e, 450))
        # 空闲城市的推荐生产项
        for r in city_overview(sit):
            for p in r.picks[:2]:
                e = self.by_type.get(p.item)
                if e:
                    put(self.render(e, 400))
        # 视野内敌军单位的数值
        seen = set()
        for t in sit.threats[:6]:
            ut = t.unit_type.replace("UNIT_BARBARIAN_", "UNIT_")
            if ut in seen:
                continue
            seen.add(ut)
            e = self.by_type.get(ut)
            if e:
                put(self.render(e, 300))
        # 当前政体
        if sit.government:
            e = self.by_type.get(sit.government.government_type)
            if e:
                put(self.render(e, 500))
        # 攻略段落：按局势打标签
        tags = {game_phase(sit)}
        prof = profile_for(sit.civ.civ_type, sit.civ.leader_type) if sit.civ else None
        if prof:
            tags |= set(prof.focus)
            tags |= {f + "胜利" for f in prof.focus}
        for f in analyze(sit):
            if f.priority <= 1:
                tags |= {f.category}
                for word in ("开拓者", "建造者", "宗教", "忠诚", "宜居", "住房", "政策", "总督", "使者", "敌军", "时代", "城墙"):
                    if word in f.title or word in f.action:
                        tags.add(word)
        for e in self.guides_for(tags, k=4):
            put(f"【攻略】{e.name}\n{e.desc}")
        if not parts:
            return ""
        return "## 资料库（本局相关条目，来自游戏数据和攻略库）\n" + "\n\n".join(parts)

    def stats(self) -> str:
        from collections import Counter

        c = Counter(e.kind for e in self.entries)
        return "、".join(f"{KIND_CN.get(k, k)}{v}" for k, v in c.most_common())


# ------------------------------------------------------------------ 单例

_KB: KnowledgeBase | None = None


def get_kb(reload: bool = False) -> KnowledgeBase:
    global _KB
    if _KB is None or reload:
        from civ6_advisor import gamedb

        _KB = KnowledgeBase(gamedb.load())
    return _KB


def set_game_data(data: dict) -> KnowledgeBase:
    global _KB
    _KB = KnowledgeBase(data)
    return _KB


async def ensure_game_kb(conn, civ_type: str | None = None, force: bool = False, progress=None) -> tuple[KnowledgeBase, bool]:
    """确保游戏资料库可用：没有缓存、本局文明不在缓存里（换了模组）或 force 时从游戏重新导出。
    返回 (资料库, 是否重建了)。"""
    from civ6_advisor import gamedb

    kb = get_kb()
    need = force or not kb.has_game_data or (civ_type and civ_type not in kb.by_type)
    if not need:
        return kb, False
    data = await gamedb.dump(conn, progress)
    gamedb.save(data)
    return set_game_data(data), True
