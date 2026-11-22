"""帝国层面规则：经济、科技文化、政策、总督、使者、时代、宗教、建造者、开拓者、通知。"""

from __future__ import annotations

from civ6_advisor.game import Situation
from civ6_advisor.civs import ResolvedProfile, profile_for
from civ6_advisor.geo import Plot, describe, describe_sit
from civ6_advisor.names import resource_cn
from civ6_advisor.rules.base import Finding, Priority, game_phase, rule


def profile(sit: Situation) -> ResolvedProfile | None:
    return profile_for(sit.civ.civ_type, sit.civ.leader_type) if sit.civ else None


def _resource_plot(r: str) -> Plot | None:
    """'IVORY@25,10' → Plot"""
    try:
        name, xy = r.split("@")
        x, y = (int(v) for v in xy.split(","))
        return Plot(x, y, "improve", resource_cn(name))
    except ValueError:
        return None


@rule
def gold(sit: Situation):
    o = sit.overview
    if o.gold_per_turn < 0:
        turns_left = o.gold / -o.gold_per_turn if o.gold_per_turn else 999
        pr = Priority.URGENT if turns_left < 10 else Priority.HIGH
        yield Finding(
            pr,
            "经济",
            "金币入不敷出",
            f"每回合 {o.gold_per_turn:+.1f}，余额 {o.gold:.0f}，约 {turns_left:.0f} 回合后归零（归零后会自动解散单位）。"
            f" 维护费 {o.total_maintenance:.0f}，其中单位 {o.unit_maintenance}。",
            "解散过时单位，建商业中心/港口，开贸易路线。",
        )


@rule
def research_and_civics(sit: Situation):
    from civ6_advisor.research import recommend_text, tracks

    o = sit.overview
    tech, civic = tracks(sit)
    if o.current_research in ("None", "", None):
        yield Finding(Priority.HIGH, "科技文化", "没有在研究科技", "科研点数正在浪费。",
                      recommend_text(tech) if tech else _tech_hint(sit), tag="research")
    if o.current_civic in ("None", "", None):
        yield Finding(Priority.HIGH, "科技文化", "没有在推进市政", "文化点数正在浪费。",
                      recommend_text(civic) if civic else _civic_hint(sit), tag="civic")
    if sit.tech:
        # 已触发尤里卡但还没研究的科技（便宜一半），值得优先
        boosted = [t for t in sit.tech.available_techs if t.boosted and t.progress_pct < 100]
        prof = profile(sit)
        if prof and prof.has("eureka_first"):
            todo = [t for t in sit.tech.available_techs if not t.boosted and t.boost_desc]
            if todo:
                yield Finding(
                    Priority.HIGH,
                    "科技文化",
                    f"{prof.name}：去触发尤里卡（触发即完成科技）",
                    "；".join(f"{t.name}：{t.boost_desc}" for t in todo[:4]),
                    "安排单位/生产去满足这些条件，比按科研值推进快得多。",
                    tag="eureka",
                )
        elif boosted and not any(t.name == o.current_research for t in boosted):
            names = "、".join(f"{t.name}({t.turns}回合)" for t in boosted[:4])
            yield Finding(
                Priority.LOW,
                "科技文化",
                "有已触发尤里卡的科技",
                f"{names}。",
                "这些科技已经打了折，研究起来性价比高。",
                tag="eureka",
            )
        boosted_c = [c for c in sit.tech.available_civics if c.boosted and c.progress_pct < 100]
        if boosted_c and not any(c.name == o.current_civic for c in boosted_c):
            names = "、".join(f"{c.name}({c.turns}回合)" for c in boosted_c[:4])
            yield Finding(Priority.LOW, "科技文化", "有已触发鼓舞的市政", f"{names}。", "优先推进打折的市政。",
                          tag="eureka")


def _tech_hint(sit: Situation) -> str:
    if not sit.tech or not sit.tech.available_techs:
        return "打开科技树选一个。"
    cheapest = sorted(sit.tech.available_techs, key=lambda t: (t.turns <= 0, t.turns, t.cost))[:3]
    return "可选：" + "、".join(t.name + (f"（{t.turns}回合）" if t.turns > 0 else "") for t in cheapest)


def _civic_hint(sit: Situation) -> str:
    if not sit.tech or not sit.tech.available_civics:
        return "打开市政树选一个。"
    cheapest = sorted(sit.tech.available_civics, key=lambda c: (c.turns <= 0, c.turns, c.cost))[:3]
    return "可选：" + "、".join(c.name + (f"（{c.turns}回合）" if c.turns > 0 else "") for c in cheapest)


def fillable_slots(g) -> list[tuple[object, list]]:
    """空政策槽里，手上确实有政策卡能放进去的那些：[(槽, 可放的政策)]。
    开局还没有政策卡（法典之前）、或已解锁的卡都在用时，空槽不算问题。"""
    if not g:
        return []
    used = {s.current_policy for s in g.slots if s.current_policy}
    cards = [p for p in (g.available_policies or []) if p.policy_type not in used]
    out = []
    taken: set[str] = set()
    for s in g.slots:
        if s.current_policy:
            continue
        if s.slot_type == "SLOT_WILDCARD":
            fit = [p for p in cards if p.slot_type in ("SLOT_MILITARY", "SLOT_ECONOMIC", "SLOT_DIPLOMATIC", "SLOT_WILDCARD")]
        else:
            fit = [p for p in cards if p.slot_type == s.slot_type]
        fit = [p for p in fit if p.policy_type not in taken]
        if fit:
            taken.add(fit[0].policy_type)
            out.append((s, fit))
    return out


def empty_policy_slots(sit: Situation):
    g = sit.government
    fill = fillable_slots(g)
    if not fill:
        return
    kinds = {"SLOT_MILITARY": "军事", "SLOT_ECONOMIC": "经济", "SLOT_DIPLOMATIC": "外交", "SLOT_WILDCARD": "通配"}
    desc = "；".join(f"{kinds.get(s.slot_type, s.slot_type)}槽可放：" + "、".join(p.name for p in fit[:3]) for s, fit in fill)
    yield Finding(
        Priority.HIGH,
        "科技文化",
        f"{len(fill)} 个政策槽空着，手上有卡可以放",
        desc + "。",
        "完成市政时可以免费换政策（其他时候要花金币），记得把这几个槽填上。",
    )


def governors(sit: Situation):  # 被 decisions.governor_advice 取代
    g = sit.governors
    if not g:
        return
    if g.points_available > 0:
        yield Finding(
            Priority.HIGH,
            "科技文化",
            f"有 {g.points_available} 个总督头衔没用",
            "可以任命新总督或者给已有总督升级。",
            "前期常用：平哥(主城加产)、梁(建造者+1次)、阿玛尼(稳住忠诚)。",
        )
    idle = [a.name for a in g.appointed if a.assigned_city_id == -1]
    if idle:
        yield Finding(Priority.MEDIUM, "科技文化", "有总督没分配城市", "、".join(idle), "总督要放到城市里才生效。")


def envoys(sit: Situation):  # 被 decisions.envoy_advice 取代
    e = sit.envoys
    if e and e.tokens_available > 0:
        yield Finding(
            Priority.MEDIUM,
            "外交",
            f"有 {e.tokens_available} 个使者没派",
            "使者不派不会产生任何收益。",
            "优先凑到 3 个拿宗主国，或者派给加成符合当前路线的城邦。",
        )


def _era_tips(sit: Situation) -> str:
    """眼下就能做的加时代分的事（只列有把握的）。"""
    tips = []
    if any(getattr(t, "owner_id", -1) == 63 or "BARBARIAN" in t.unit_type.upper() for t in sit.threats):
        tips.append("清掉附近的蛮族营地")
    e = sit.envoys
    if e and e.tokens_available > 0:
        tips.append(f"把 {e.tokens_available} 个使者派出去，第一次当上城邦宗主有时代分")
    if sit.pantheon is not None and not sit.pantheon.has_pantheon:
        tips.append("选万神殿")
    if any("SCOUT" in u.unit_type.upper() for u in sit.units):
        tips.append("侦察兵继续探路，首次遇见文明/城邦、发现自然奇观都有分")
    if not tips:
        tips.append("建奇观、招募伟人、创立宗教、在新大陆建城")
    return "现在能做的：" + "；".join(tips) + "。"


@rule
def era_score(sit: Situation):
    o = sit.overview
    if not o.era_dark_threshold:
        return
    if o.era_score < o.era_dark_threshold:
        gap = o.era_dark_threshold - o.era_score
        yield Finding(
            Priority.MEDIUM,
            "时代",
            "时代分数不够，有进入黑暗时代的风险",
            f"当前 {o.era_score}，避免黑暗时代需要 {o.era_dark_threshold}（还差 {gap}）。",
            _era_tips(sit),
        )
    elif o.era_golden_threshold and o.era_golden_threshold - o.era_score <= 3:
        yield Finding(
            Priority.LOW,
            "时代",
            "离黄金时代只差一点",
            f"当前 {o.era_score}，黄金时代需要 {o.era_golden_threshold}。",
            "再拿几分就能进黄金时代。",
        )


@rule
def religion(sit: Situation):
    o = sit.overview
    prof = profile(sit)
    need = prof.religion if prof else "可选"
    if o.our_religion or not o.religions_max or need in ("保底", "不能"):
        return
    left = o.religions_max - o.religions_founded
    if left <= 0:
        if need == "必需":
            yield Finding(
                Priority.HIGH,
                "宗教",
                f"宗教名额已满，{prof.name}没能创立宗教",
                "这个文明的核心玩法依赖宗教，需要调整路线。",
                f"改走{'/'.join(f for f in prof.focus if f != '宗教') or '其他'}路线，或者靠征服拿下别人的圣城。",
            )
        return
    phase = game_phase(sit)
    if need == "必需" and phase in ("开局", "前期"):
        yield Finding(
            Priority.HIGH if left <= 2 else Priority.MEDIUM,
            "宗教",
            f"{prof.name}要尽快创立宗教（还剩 {left} 个名额）",
            f"已创立 {o.religions_founded}/{o.religions_max}，信仰值 {o.faith:.0f}。宗教是{prof.name}的核心。",
            "优先建圣地，用占星术/万神殿相关政策攒伟大先知点。",
        )
    elif left == 1 and phase in ("开局", "前期"):
        yield Finding(
            Priority.MEDIUM,
            "宗教",
            "只剩最后 1 个宗教名额",
            f"已创立 {o.religions_founded}/{o.religions_max}，信仰值 {o.faith:.0f}。",
            "如果想要宗教，现在就要冲圣地和大先知；不要的话可以放弃，信仰改买别的。",
        )


def _res_label(sit: Situation, r) -> str:
    from civ6_advisor.facts import CLS_CN

    return f"{resource_cn(r.resource)}（{CLS_CN.get(r.cls, '')}，{describe_sit(sit, r.x, r.y)}）"


def _blocked_text(sit: Situation, blocked) -> str:
    """'羊、牛 需要畜牧业；石头 需要采矿业'"""
    from civ6_advisor.names import type_name

    by_req: dict[str, list[str]] = {}
    for r in blocked:
        by_req.setdefault(r.prereq, []).append(resource_cn(r.resource))
    return "；".join(f"{'、'.join(dict.fromkeys(v))} 需要{type_name(k, sit)}" for k, v in by_req.items())


@rule
def builders_and_resources(sit: Situation):
    builders = [u for u in sit.units if u.build_charges > 0]
    builders_queued = [c.name for c in sit.cities if (c.currently_building or "").upper() == "UNIT_BUILDER"]
    prof = profile(sit)
    if sit.facts is None:
        yield from _builders_legacy(sit, builders, builders_queued)
        return
    from civ6_advisor.facts import IMPROVEMENT_CN

    now, blocked = sit.facts.improvable_now, sit.facts.blocked
    bonus_note = ""
    if prof and prof.has("improve_bonus"):
        bonus_note = f"（{prof.name}每改良一个资源还有额外收益）"
    plots = [Plot(r.x, r.y, "improve", resource_cn(r.resource)) for r in now[:8]]
    later = f"另外：{_blocked_text(sit, blocked)}。" if blocked else ""

    if now:
        top = now[0]
        first = f"先改{_res_label(sit, top)}，建{IMPROVEMENT_CN.get(top.improvement, top.improvement)}"
        if top.cls == "luxury":
            first += "：奢侈品直接加宜居"
        names = "、".join(_res_label(sit, r) for r in now[:5])
        if builders:
            yield Finding(Priority.MEDIUM, "单位", f"建造者现在可以改良 {len(now)} 处资源",
                          f"能改：{names}。{later}", first + "。" + bonus_note, plots=plots)
        elif builders_queued:
            yield Finding(Priority.LOW, "城市", f"{len(now)} 处资源能改良，{'、'.join(builders_queued)}正在造建造者",
                          f"能改：{names}。{later}", "建造者出来后" + first + "。" + bonus_note, plots=plots)
        else:
            yield Finding(Priority.MEDIUM, "城市", f"{len(now)} 处资源现在就能改良，但没有建造者",
                          f"能改：{names}。{later}", "出或者买一个建造者，" + first + "。" + bonus_note, plots=plots)
    elif blocked and builders:
        # 有建造者但所有资源都缺科技：说清楚缺什么，别让玩家以为能改
        yield Finding(
            Priority.MEDIUM, "单位", "建造者暂时没有资源可以改良",
            f"领土内的资源都还缺科技：{_blocked_text(sit, blocked)}。",
            _next_improve_tech(sit, blocked) + "等科技期间建造者别闲着：在淡水/平原上种农场，或者砍树换产能加速生产。",
            plots=[Plot(r.x, r.y, "improve", resource_cn(r.resource)) for r in blocked[:6]],
        )


def _next_improve_tech(sit: Situation, blocked) -> str:
    """和科技板块对上：说明推荐顺序里第一个能解锁改良的科技，以及它排在第几。"""
    from civ6_advisor.names import type_name
    from civ6_advisor.research import tracks

    tech, _ = tracks(sit)
    if not tech:
        return ""
    reqs = {r.prereq for r in blocked}
    order = ([tech.current] if tech.current else []) + tech.picks
    for i, p in enumerate(order):
        if p.type in reqs:
            got = "、".join(dict.fromkeys(resource_cn(r.resource) for r in blocked if r.prereq == p.type))
            if i == 0 and tech.current and p is tech.current:
                return f"正在研究的{p.name}完成后就能改良{got}。"
            if i == 0:
                return f"科技推荐的第一项就是{p.name}（解锁{got}的改良）。"
            first = order[0]
            return f"科技建议先{first.name}（{first.reasons[0] if first.reasons else '更紧急'}），然后{p.name}来改良{got}。"
    return ""


def _builders_legacy(sit: Situation, builders, builders_queued):
    """没读到资源事实时的旧逻辑（不知道哪些能改）。"""
    unimproved = [(c.name, r) for c in sit.cities for r in c.unimproved_resources]
    plots = [p for _, r in unimproved[:8] if (p := _resource_plot(r))]
    listing = "、".join(f"{n}:{resource_cn(r.split('@')[0])}" for n, r in unimproved[:6])
    if unimproved and not builders and builders_queued:
        yield Finding(Priority.LOW, "城市", f"{len(unimproved)} 个资源待改良，{'、'.join(builders_queued)}正在造建造者",
                      listing, "建造者出来后先改能改的奢侈品。", plots=plots)
    elif unimproved and not builders:
        yield Finding(Priority.MEDIUM, "城市", f"{len(unimproved)} 个资源没改良，但没有建造者", listing,
                      "出或者买一个建造者（注意有的资源需要先研究对应科技）。", plots=plots)
    elif unimproved and builders:
        yield Finding(Priority.LOW, "单位", f"有 {len(builders)} 个建造者，{len(unimproved)} 个资源待改良", listing,
                      "能改的先改奢侈品；缺科技的要等研究出来。", plots=plots)


@rule
def settlers(sit: Situation):
    settlers = [u for u in sit.units if "SETTLER" in u.unit_type.upper()]
    if not settlers:
        return
    plots = [Plot(u.x, u.y, "unit", "开拓者") for u in settlers]
    if sit.settle_spots:
        lines = []
        for i, c in enumerate(sit.settle_spots[:3], 1):
            water = {"fresh": "淡水", "coast": "海岸", "none": "无水源"}.get(c.water_type, c.water_type)
            extra = []
            if c.luxury_count:
                extra.append(f"{c.luxury_count}种奢侈品")
            if c.strategic_count:
                extra.append(f"{c.strategic_count}种战略资源")
            lines.append(f"{i}号：{describe_sit(sit, c.x, c.y)}（{water}，粮{c.total_food} 锤{c.total_prod}"
                         + (("，" + "、".join(extra)) if extra else "") + "）")
            plots.append(Plot(c.x, c.y, "settle", f"{i}号城址"))
        action = "推荐城址 " + "；".join(lines) + "。点这条建议会在地图上插标记。"
        if any(c.x == u.x and c.y == u.y for c in sit.settle_spots[:1] for u in settlers):
            action = "1号城址就在开拓者脚下，可以原地落城。" + action
    else:
        action = "好城址：靠河或海岸、附近有奢侈品、离现有城市 4-6 格。"
    yield Finding(
        Priority.HIGH,
        "单位",
        f"有 {len(settlers)} 个开拓者待落城",
        "开拓者越早落城，复利越大。",
        action,
        plots=plots,
    )


@rule
def expansion(sit: Situation):
    phase = game_phase(sit)
    n = len(sit.cities)
    has_settler = any("SETTLER" in u.unit_type.upper() for u in sit.units)
    if has_settler:
        return
    prof = profile(sit)
    target = prof.expand if prof else 5
    queued = [c.name for c in sit.cities if (c.currently_building or "").upper() == "UNIT_SETTLER"]
    if queued:
        return  # 已经有城市在出开拓者
    if phase in ("开局", "前期") and n < target - 1 and (phase == "前期" or sit.overview.turn >= 15):
        who = f"{prof.name}前期目标约 {target} 座城" if prof else f"前期目标约 {target} 座城"
        yield Finding(
            Priority.MEDIUM,
            "城市",
            f"只有 {n} 座城市，扩张偏慢",
            f"前期城市数量是最重要的增长来源，{who}。",
            "目前没有城市在出开拓者。首都或产能高、人口 2 以上的城市再出一个。",
        )


@rule
def action_required_notifications(sit: Situation):
    # 选科技/市政/生产这几类已经由其他规则覆盖，这里跳过避免重复
    covered = ("CHOOSE_TECH", "CHOOSE_CIVIC", "CHOOSE_PRODUCTION", "CHOOSE_CITY_PRODUCTION",
               "FILL_CIVIC_SLOT", "GOVERNOR_APPOINTMENT", "GIVE_INFLUENCE_TOKEN")
    pending = [
        n for n in sit.notifications
        if n.is_action_required and not any(k in n.type_name for k in covered)
    ]
    for n in pending[:5]:
        yield Finding(
            Priority.HIGH,
            "通知",
            n.message or n.type_name,
            n.resolution_hint or "游戏里有待处理的事项，会阻止结束回合。",
        )


@rule
def civ_strategy(sit: Situation):
    """每回合给一条按文明和阶段定制的重点。"""
    if not sit.civ:
        return
    phase = game_phase(sit)
    prof = profile(sit)
    if prof:
        tip = prof.phase_tip(phase)
        lead = f"（{prof.leader.name}：{prof.leader.tip}）" if prof.leader else ""
        yield Finding(
            Priority.MEDIUM,
            "文明",
            f"{prof.name}·{phase}重点（倾向：{prof.focus_text}）",
            prof.civ.traits + "。",
            tip + lead,
        )
    else:
        # 攻略库没收录：用游戏里读到的能力
        names = "、".join(f"{a.label}「{a.name}」" for a in sit.civ.abilities[:4])
        yield Finding(
            Priority.LOW,
            "文明",
            f"{sit.civ.civ_name}（{sit.civ.leader_name}）",
            f"攻略库没有收录这个文明。能力：{names or '未读到'}。",
            "点「问AI」让大模型结合文明能力给具体打法。",
        )
