"""流派规则：玩家开启流派后，按里程碑给出「下一步」，落后于计划或前提失效时提醒。"""

from __future__ import annotations

from civ6_advisor.game import Situation
from civ6_advisor.playstyles import GOV_CN, active, progress
from civ6_advisor.rules.base import Finding, Priority, rule


def _how(step) -> str:
    c = step.cond
    if c[0] == "governor":
        return step.how or f"总督界面任命{GOV_CN.get(c[1], c[1])}"
    return step.how


@rule
def playstyle_progress(sit: Situation):
    ps = active(sit)
    if not ps:
        return
    pr = progress(ps, sit)
    if pr.broken:
        yield Finding(Priority.HIGH, "流派", f"「{ps.name}」的前提失效",
                      "；".join(pr.broken), "考虑再点一次流派按钮取消，恢复常规推荐；或问 AI 怎么转型。", tag="playstyle")
    st = pr.next
    if st is None:
        yield Finding(Priority.LOW, "流派", f"「{ps.name}」里程碑全部完成",
                      f"{len(pr.done)} 个里程碑都已达成，按目标（{ps.goal}）收官。", tag="playstyle")
        return
    late = st in pr.late
    by = f"，建议第 {st.by} 回合前（标准速度）" if st.by else ""
    yield Finding(
        Priority.HIGH if late else Priority.MEDIUM, "流派",
        f"流派下一步：{st.text}" + ("（已落后）" if late else ""),
        f"「{ps.name}」{pr.summary().split(' · ')[0]}{by}。",
        _how(st), tag="playstyle")
    for other in pr.late:
        if other is not st:
            yield Finding(Priority.MEDIUM, "流派", f"落后于计划：{other.text}",
                          f"「{ps.name}」建议第 {other.by} 回合前完成。", _how(other), tag="playstyle")
