"""只读游戏门面 + 局势快照采集。

ReadOnlyGame 只暴露白名单里的读取方法，从结构上保证军师不会替玩家下命令。
civ6-mcp 的 GameState 同时包含读和写；这里不直接把它交给 MCP 层。
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from civ_mcp import lua as lq
from civ_mcp.connection import GameConnection
from civ_mcp.game_state import GameState

from civ6_advisor.civ_info import CIV_IDENTITY_LUA, CivIdentity, parse_identity
from civ6_advisor.facts import FACTS_LUA, EmpireFacts, parse_facts

log = logging.getLogger(__name__)

# 允许调用的 GameState 方法（全部是只读查询）
READ_ONLY_METHODS = frozenset(
    {
        "get_game_overview",
        "get_cities",
        "get_units",
        "get_threat_scan",
        "get_tech_civics",
        "get_diplomacy",
        "get_notifications",
        "get_rival_snapshot",
        "get_policies",
        "get_governors",
        "get_city_states",
        "get_victory_progress",
        "get_great_people",
        "list_city_production",
        "get_district_advisor",
        "get_settle_advisor",
        "get_global_settle_scan",
        "get_empire_resources",
        "get_strategic_map",
        "get_trade_routes",
        "get_builder_tasks",
        "get_religion_status",
        "get_pantheon_status",
    }
)


class ReadOnlyGame:
    """GameState 的只读包装。访问白名单外的方法会直接报错。"""

    def __init__(self, host: str = "127.0.0.1", port: int = 4318):
        from civ6_advisor import steplog

        self._gs = GameState(GameConnection(host, port))
        steplog.instrument(self._gs.conn)  # 每次读取都记日志，游戏崩溃时能定位是哪一步

    @property
    def conn(self) -> GameConnection:
        return self._gs.conn

    async def get_civ_identity(self) -> CivIdentity | None:
        """读取文明/领袖类型和能力（固定的只读查询）。"""
        from civ6_advisor.steplog import step

        with step("读文明和领袖能力"):
            return parse_identity(await self._gs.conn.execute_read(CIV_IDENTITY_LUA, timeout=8.0))

    async def get_facts(self) -> EmpireFacts:
        """已研究科技/市政 + 领土内可见资源的改良状态（固定的只读查询）。"""
        from civ6_advisor.steplog import step

        with step("读科技市政/资源/地形统计"):
            return parse_facts(await self._gs.conn.execute_read(FACTS_LUA, timeout=8.0))

    def __getattr__(self, name: str) -> Any:
        if name not in READ_ONLY_METHODS:
            raise AttributeError(f"军师模式只允许读取，禁止调用 {name}")
        fn = getattr(self._gs, name)
        import inspect

        if not inspect.iscoroutinefunction(fn):
            return fn
        from civ6_advisor.steplog import step

        async def logged(*a, **kw):
            with step(name + (f"({', '.join(map(str, a))})" if a else "")):
                return await fn(*a, **kw)

        return logged


@dataclass
class Situation:
    """某一时刻的完整局势快照（只含玩家可见的信息）。"""

    overview: lq.GameOverview
    cities: list[lq.CityInfo] = field(default_factory=list)
    units: list[lq.UnitInfo] = field(default_factory=list)
    threats: list[lq.ThreatInfo] = field(default_factory=list)
    tech: lq.TechCivicStatus | None = None
    diplomacy: list[lq.CivInfo] = field(default_factory=list)
    notifications: list[lq.GameNotification] = field(default_factory=list)
    rivals: list[lq.RivalSnapshot] = field(default_factory=list)
    government: lq.GovernmentStatus | None = None
    governors: lq.GovernorStatus | None = None
    envoys: lq.EnvoyStatus | None = None
    civ: CivIdentity | None = None
    settle_spots: list[lq.SettleCandidate] = field(default_factory=list)  # 只在有开拓者时读取
    production_options: dict[int, list[lq.ProductionOption]] = field(default_factory=dict)  # 空闲城市和首都
    facts: EmpireFacts | None = None  # 已研究科技 + 资源改良状态（建造者和科技推荐共用）
    district_spots: dict = field(default_factory=dict)  # city_id -> (区域类型, [DistrictPlacement 最多 3 个])
    pantheon: object | None = None  # lq.PantheonStatus：有没有万神殿、可选信仰
    playstyle: str | None = None  # 玩家开启的流派 id（playstyles.py），None = 常规推荐
    errors: list[str] = field(default_factory=list)  # 部分查询失败时记录
    taken_at: float = field(default_factory=time.time)


MAX_PROD_CITIES = 8


async def collect_situation(game: ReadOnlyGame) -> Situation:
    """依次采集各项数据。单项失败不影响整体，失败原因记在 errors 里。

    连接层内部有锁，命令本来就是串行的，所以这里不并发。
    """
    overview = await game.get_game_overview()  # 这个失败就没法分析了，直接抛
    sit = Situation(overview=overview)

    async def grab(attr: str, coro_fn, transform=lambda x: x):
        try:
            setattr(sit, attr, transform(await coro_fn()))
        except Exception as e:  # noqa: BLE001
            log.warning("采集 %s 失败: %s", attr, e)
            sit.errors.append(f"{attr}: {e}")

    await grab("cities", game.get_cities, lambda r: r[0])
    await grab("units", game.get_units)
    await grab("threats", game.get_threat_scan)
    await grab("tech", game.get_tech_civics)
    await grab("diplomacy", game.get_diplomacy)
    await grab("notifications", game.get_notifications)
    await grab("rivals", game.get_rival_snapshot)
    await grab("government", game.get_policies)
    await grab("governors", game.get_governors)
    await grab("envoys", game.get_city_states)
    await grab("civ", game.get_civ_identity)
    await grab("facts", game.get_facts)
    await grab("pantheon", game.get_pantheon_status)
    # 读可生产列表（含金币价格）：空闲城市和首都优先，最多 8 座城，用来给出"能造的/买得起的"推荐
    def _prio(c):
        idle = (c.currently_building or "").lower() in ("", "nothing", "none")
        capital = any(b.upper().removeprefix("BUILDING_") == "PALACE" for b in (c.buildings or []))
        return (not idle, not capital)

    for c in sorted(sit.cities, key=_prio)[:MAX_PROD_CITIES]:
        if c is not None:
            try:
                sit.production_options[c.city_id] = await game.list_city_production(c.city_id)
            except Exception as e:  # noqa: BLE001
                sit.errors.append(f"production_options[{c.name}]: {e}")
    if any("SETTLER" in u.unit_type.upper() for u in sit.units):
        await grab("settle_spots", game.get_global_settle_scan, lambda r: r[:5])
    await _district_spots(game, sit)
    return sit


MAX_DISTRICT_ADVICE = 2  # 每回合最多查几座城的区域选址（游戏侧也有调用上限）


async def _district_spots(game, sit: "Situation") -> None:
    """空闲城市如果推荐建区域，顺便查最佳地块（相邻加成最高的几个）。"""
    from civ6_advisor.production import suggest_for_city

    n = 0
    for c in sit.cities:
        if n >= MAX_DISTRICT_ADVICE:
            break
        if (c.currently_building or "").lower() not in ("", "nothing", "none"):
            continue
        try:
            picks = suggest_for_city(sit, c)[:3]
        except Exception:  # noqa: BLE001
            continue
        d = next((p.item for p in picks if p.item.startswith("DISTRICT_")), None)
        if not d:
            continue
        n += 1
        try:
            res = await game.get_district_advisor(c.city_id, d)
        except Exception as e:  # noqa: BLE001
            sit.errors.append(f"district_advisor[{c.name}]: {e}")
            continue
        if isinstance(res, list) and res:
            sit.district_spots[c.city_id] = (d, sorted(res, key=lambda r: -r.total_adjacency)[:3])
