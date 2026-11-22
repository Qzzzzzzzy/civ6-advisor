"""把局势快照 + 规则发现渲染成给 LLM 读的中文简报。"""

from __future__ import annotations

from civ6_advisor.civs import profile_for
from civ6_advisor.game import Situation
from civ6_advisor.rules import Finding, Priority, game_phase
from civ6_advisor.rules.rivals import rank_of, strict_fog


def header(sit: Situation) -> str:
    o = sit.overview
    lines = [
        f"# 第 {o.turn} 回合 · {o.civ_name}（{o.leader_name}）· {o.era_name or '未知时代'} · {game_phase(sit)}",
        f"难度 {o.difficulty or '?'} · 速度 {o.game_speed_name or '?'} · 分数 {o.score}",
        "",
        "## 帝国概况",
        f"- 城市 {o.num_cities} 座 · 总人口 {o.total_population} · 单位 {o.num_units} 个",
        f"- 金币 {o.gold:.0f}（{o.gold_per_turn:+.1f}/回合）· 科研 {o.science_yield:.1f} · 文化 {o.culture_yield:.1f} · 信仰 {o.faith:.0f}",
        f"- 正在研究：{o.current_research} · 正在推进：{o.current_civic}",
        f"- 已探索陆地 {o.explored_land}/{o.total_land}"
        + (f"（{o.explored_land * 100 // o.total_land}%）" if o.total_land else ""),
    ]
    if o.era_dark_threshold:
        lines.append(
            f"- 时代分 {o.era_score}（黑暗 <{o.era_dark_threshold}，黄金 ≥{o.era_golden_threshold}）"
        )
    if sit.government:
        lines.append(f"- 政体：{sit.government.government_name}")
    if sit.rivals:
        n = len(sit.rivals) + 1
        sci = rank_of(o.science_yield, [r.sci for r in sit.rivals])
        cul = rank_of(o.culture_yield, [r.cul for r in sit.rivals])
        sc = rank_of(o.score, [r.score for r in sit.rivals])
        lines.append(f"- 已相遇 {n - 1} 个文明；我方排名：分数第{sc} · 科研第{sci} · 文化第{cul}（共{n}）")
    return "\n".join(lines)


def civ_section(sit: Situation) -> str:
    """文明与领袖：游戏里读到的能力原文 + 攻略库的打法。给大模型做定制分析用。"""
    if not sit.civ:
        return ""
    c = sit.civ
    lines = [f"## 文明与领袖：{c.civ_name} · {c.leader_name}（{c.civ_type} / {c.leader_type}）"]
    lines += c.summary_lines()
    prof = profile_for(c.civ_type, c.leader_type)
    if prof:
        phase = game_phase(sit)
        lines.append(f"- 攻略倾向：{prof.focus_text}；宗教：{prof.religion}；前期目标城市数约 {prof.expand}")
        lines.append(f"- 当前阶段（{phase}）重点：{prof.phase_tip(phase)}")
        if prof.leader:
            lines.append(f"- 领袖打法：{prof.leader.name}：{prof.leader.tip}")
    else:
        lines.append("- 攻略库未收录该文明，请根据上面的能力原文判断打法")
    return "\n".join(lines)


def resources_section(sit: Situation) -> str:
    """资源改良状态（建造者和科技推荐的共同依据）。"""
    f = sit.facts
    if not f or not f.resources:
        return ""
    from civ6_advisor.facts import CLS_CN, IMPROVEMENT_CN
    from civ6_advisor.geo import describe_sit
    from civ6_advisor.names import resource_cn, type_name

    lines = ["## 领土内未改良的资源（只含看得见的）"]
    for r in f.resources[:12]:
        imp = IMPROVEMENT_CN.get(r.improvement, type_name(r.improvement, sit)) if r.improvement else "无可用改良"
        state = "现在就能改" if r.can_now else f"需要先研究 {type_name(r.prereq, sit)}"
        lines.append(f"- {resource_cn(r.resource)}（{CLS_CN.get(r.cls, '')}，{describe_sit(sit, r.x, r.y)}）→ {imp}：{state}")
    builders = sum(1 for u in sit.units if u.build_charges > 0)
    lines.append(f"- 建造者 {builders} 个")
    return "\n".join(lines)


def city_table(sit: Situation) -> str:
    if not sit.cities:
        return "## 城市\n（无）"
    from civ6_advisor.names import production_cn
    from civ6_advisor.production import is_capital

    rows = ["## 城市", "| 城市 | 人口/住房 | 粮 | 锤 | 宜居 | 忠诚 | 在造 |", "|---|---|---|---|---|---|---|"]
    for c in sorted(sit.cities, key=lambda c: not is_capital(c)):
        building = production_cn(c.currently_building) or "⚠️空闲"
        if c.production_turns_left and building != "⚠️空闲":
            building += f"({c.production_turns_left})"
        name = ("★" if is_capital(c) else "") + c.name
        rows.append(
            f"| {name} | {c.population}/{c.housing:.0f} | {c.food_surplus:+.1f} | {c.production:.0f} "
            f"| {c.amenities:+d} | {c.loyalty:.0f} | {building} |"
        )
    return "\n".join(rows)


def findings_block(findings: list[Finding], limit: int | None = None) -> str:
    if not findings:
        return "## 需要处理的事项\n目前没有发现明显问题。"
    shown = findings[:limit] if limit else findings
    body = "\n\n".join(f.render() for f in shown)
    more = f"\n\n（另有 {len(findings) - len(shown)} 条低优先级提示省略）" if limit and len(findings) > limit else ""
    return "## 需要处理的事项（按优先级）\n" + body + more


def full_brief(sit: Situation, findings: list[Finding]) -> str:
    from civ6_advisor.playstyles import brief_section

    parts = [header(sit), civ_section(sit), brief_section(sit), city_table(sit), resources_section(sit),
             findings_block(findings)]
    parts = [p for p in parts if p]
    if sit.errors:
        parts.append("## 数据缺失\n部分数据读取失败，相关分析可能不完整：\n- " + "\n- ".join(sit.errors))
    if strict_fog():
        parts.append("_（严格迷雾模式：只使用玩家在游戏里能看到的信息）_")
    return "\n\n".join(parts)


def top_moves(sit: Situation, findings: list[Finding], n: int = 5) -> str:
    """精简版：只给最重要的几件事，适合每回合快速看一眼。"""
    o = sit.overview
    urgent = [f for f in findings if f.priority <= Priority.HIGH]
    picked = (urgent or findings)[:n]
    lines = [f"# 第 {o.turn} 回合 · 本回合优先处理"]
    for i, f in enumerate(picked, 1):
        lines.append(f"{i}. {f.priority.label} {f.title}：{f.action or f.detail}")
    if not picked:
        lines.append("没有发现需要立刻处理的问题，可以按原计划推进。")
    rest = len(findings) - len(picked)
    if rest > 0:
        lines.append(f"\n（还有 {rest} 条次要建议，调用 get_situation_brief 查看完整分析）")
    return "\n".join(lines)
