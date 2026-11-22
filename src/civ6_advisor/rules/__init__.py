"""规则引擎入口：导入各规则模块完成注册，然后统一运行。"""

from __future__ import annotations

import logging

from civ6_advisor.game import Situation
from civ6_advisor.rules import cities, decisions, empire, military, playstyle, rivals  # noqa: F401  注册规则
from civ6_advisor.rules.base import RULES, Finding, Priority, game_phase

log = logging.getLogger(__name__)

__all__ = ["analyze", "Finding", "Priority", "game_phase"]


def analyze(sit: Situation) -> list[Finding]:
    """跑所有规则，按优先级排序。单条规则出错不影响其他规则。"""
    out: list[Finding] = []
    for r in RULES:
        try:
            out.extend(r(sit))
        except Exception as e:  # noqa: BLE001
            log.warning("规则 %s 出错: %s", r.__name__, e)
    out.sort(key=lambda f: (f.priority, f.category))
    return out
