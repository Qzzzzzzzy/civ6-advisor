"""AI 自动分析：决定新回合要不要自动问 AI（省钱的同时不漏掉关键时刻）。

模式：
  off    关闭（AI 军师开关关着）
  smart  关键回合：刚连上、出现新的紧急/重要情况、流派进入下一步、隔了一段时间时才问（推荐）
  every  每回合都问
"""

from __future__ import annotations

from dataclasses import dataclass, field

from civ6_advisor.rules.base import Priority

MODES = {"off": "关闭（只手动问）", "smart": "关键回合自动问（推荐）", "every": "每回合自动问"}
REVIEW_EVERY = 8  # smart 模式下最多隔几回合复盘一次


@dataclass
class AutoState:
    last_turn: int | None = None  # 上次自动问的回合
    seen: set[str] = field(default_factory=set)  # 上回合已有的重要情况
    last_next: str | None = None  # 上回合的流派下一步
    started: bool = False


def _important(findings) -> dict[str, object]:
    return {f.title: f for f in findings if f.priority <= Priority.HIGH and f.category != "流派"}


def auto_reason(mode: str, sit, findings, st: AutoState) -> str | None:
    """返回触发原因（会显示给玩家，也会告诉 AI 重点看什么）；不需要问时返回 None。每回合调用一次。"""
    from civ6_advisor.playstyles import active, progress

    turn = sit.overview.turn
    cur = _important(findings)
    new = [t for t in cur if t not in st.seen]
    st.seen = set(cur)
    ps = active(sit)
    nxt = progress(ps, sit).next if ps else None
    nxt_text = nxt.text if nxt else None
    step_changed = ps is not None and st.last_next is not None and nxt_text != st.last_next
    st.last_next = nxt_text
    first = not st.started
    st.started = True

    if mode == "off":
        return None
    reason = None
    if mode == "every":
        reason = "每回合分析"
    elif first:
        reason = "先做一次整体分析"
    else:
        urgent = [t for t in new if cur[t].priority == Priority.URGENT]
        if urgent:
            reason = "新的紧急情况：" + "、".join(urgent[:2])
        elif new:
            reason = "新情况：" + "、".join(new[:2])
        elif step_changed:
            reason = "流派进入下一步：" + (nxt_text or "里程碑全部完成")
        elif st.last_turn is None or turn - st.last_turn >= REVIEW_EVERY:
            reason = f"定期复盘（已经 {REVIEW_EVERY} 回合没分析）"
    if reason:
        st.last_turn = turn
    return reason


def question_for(reason: str) -> str:
    """自动分析时附给 AI 的一句话，让它把重点放在触发原因上。"""
    if reason.startswith(("新的紧急情况", "新情况")):
        return f"这回合我该做什么？先处理：{reason.split('：', 1)[1]}"
    if reason.startswith("流派进入下一步"):
        return f"这回合我该做什么？流派刚进入新阶段（{reason.split('：', 1)[1]}），说说这一阶段怎么安排。"
    return ""
