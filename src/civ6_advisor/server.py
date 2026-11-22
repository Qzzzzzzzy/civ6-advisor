"""文明6 军师 MCP Server（只读）。

运行方式：
  civ6-advisor              以 stdio 启动 MCP 服务（给 Claude Desktop 等客户端用）
  civ6-advisor brief        直接在终端打印一次完整简报（调试用）
  civ6-advisor watch        常驻：每进入新回合自动打印本回合优先事项

环境变量：
  CIV6_ADVISOR_MOCK=1          不连游戏，用内置演示数据
  CIV6_ADVISOR_STRICT_FOG=0    关闭严格迷雾（允许报出对手具体数值）
  CIV6_HOST / CIV6_PORT        Tuner 地址，默认 127.0.0.1:4318
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
import time

from civ_mcp import narrate as nr
from mcp.server.fastmcp import FastMCP

from civ6_advisor import report
from civ6_advisor.game import ReadOnlyGame, Situation, collect_situation
from civ6_advisor.names import unit_cn
from civ6_advisor.rules import analyze

log = logging.getLogger("civ6_advisor")

MOCK = os.environ.get("CIV6_ADVISOR_MOCK") == "1"
CACHE_TTL = 8.0  # 秒；同一次提问里多次调用工具时复用快照

CATEGORIES = ("军事", "城市", "经济", "科技文化", "单位", "外交", "宗教", "时代", "通知")

ADVISOR_PROMPT = """你是一位精通《文明6》的军师，正在实时观察玩家的这局游戏。

工作方式：
1. 先调用 suggest_next_moves 了解本回合最要紧的事；需要全貌时调用 get_situation_brief。
2. 针对具体问题再调用细分工具（城市生产选项、科技市政、外交、建造者任务、城址推荐）。
3. 规则引擎给出的是"体检结果"，你要在此基础上结合文明特性、领袖能力、难度和胜利路线做判断，
   不要只是复述。规则之间有冲突时（比如既缺兵又缺钱）要替玩家排出先后。

回答格式：
- 先用一句话概括当前局势（优势/劣势/最大风险）。
- 然后给"本回合要做的事"，最多 5 条，按先后排，每条写清楚在哪座城/哪个单位、做什么、为什么。
- 最后可以给 1-2 条中长期建议（未来 10-20 回合的方向）。
- 用中文，简洁，像一个懂行的朋友在旁边指点。

边界：你只能读取数据和提建议，不能替玩家操作游戏。工具里看不到的信息（迷雾里的东西）不要编造。
"""

mcp = FastMCP("civ6-advisor", instructions=ADVISOR_PROMPT)

_game: ReadOnlyGame | None = None
_cache: tuple[float, Situation] | None = None


def _get_game() -> ReadOnlyGame:
    global _game
    if _game is None:
        _game = ReadOnlyGame(os.environ.get("CIV6_HOST", "127.0.0.1"), int(os.environ.get("CIV6_PORT", "4318")))
    return _game


async def _situation(fresh: bool = False) -> Situation:
    global _cache
    if not fresh and _cache and time.time() - _cache[0] < CACHE_TTL:
        return _cache[1]
    if MOCK:
        from civ6_advisor.mock import mock_situation

        sit = mock_situation()
    else:
        sit = await collect_situation(_get_game())
    _cache = (time.time(), sit)
    return sit


def _friendly_error(e: Exception) -> str:
    msg = str(e)
    if isinstance(e, ConnectionError) or "connect" in msg.lower():
        return (
            "连不上文明6。请检查：\n"
            "1. 游戏已经进入对局（不是主菜单）\n"
            "2. 已开启 Tuner（Windows：游戏设置里的“Tuner (disables achievements)”；Mac/Linux：AppOptions.txt 里 EnableTuner 1），并重启了游戏\n"
            "3. Windows 需安装 Civilization VI SDK；FireTuner.exe 没有同时开着\n"
            f"原始错误：{msg}"
        )
    return f"读取失败：{msg}"


async def _safe(fn):
    try:
        return await fn()
    except Exception as e:  # noqa: BLE001
        log.exception("tool error")
        return _friendly_error(e)


def _mock_unavailable() -> str | None:
    return "演示模式下没有这项数据，连上真实游戏后可用。" if MOCK else None


# ---------------------------------------------------------------- 核心工具


@mcp.tool(annotations={"readOnlyHint": True})
async def suggest_next_moves(focus: str = "") -> str:
    """本回合最该做的几件事（军师的主入口，每回合先调用这个）。

    Args:
        focus: 可选，只看某一类：军事/城市/经济/科技文化/单位/外交/宗教/时代/通知。留空看全部。
    """

    async def run():
        sit = await _situation(fresh=True)
        findings = analyze(sit)
        if focus:
            findings = [f for f in findings if f.category == focus]
        return report.top_moves(sit, findings) + "\n\n" + report.header(sit)

    return await _safe(run)


@mcp.tool(annotations={"readOnlyHint": True})
async def get_situation_brief() -> str:
    """完整局势简报：帝国概况、城市一览、按优先级排好的全部问题和建议。"""

    async def run():
        from civ6_advisor.kb import get_kb

        sit = await _situation()
        await _ensure_kb_once()
        return report.full_brief(sit, analyze(sit)) + "\n\n" + get_kb().context_for(sit)

    return await _safe(run)


@mcp.tool(annotations={"readOnlyHint": True})
async def get_threat_report() -> str:
    """军事威胁报告：视野内所有外国军事单位、离我方城市的距离、各城防御情况。"""

    async def run():
        sit = await _situation()
        mil = [f for f in analyze(sit) if f.category in ("军事",) or "交战" in f.title]
        lines = ["# 军事威胁"]
        if sit.threats:
            lines.append("## 视野内的外国军事单位")
            for t in sorted(sit.threats, key=lambda t: t.distance):
                lines.append(
                    f"- {'蛮族' if t.owner_id == 63 else t.owner_name} {unit_cn(t.unit_type)} @({t.x},{t.y}) "
                    f"血 {t.hp}/{t.max_hp} 战力 {t.combat_strength} 远程 {t.ranged_strength} "
                    f"离我方最近 {t.distance} 格"
                )
        else:
            lines.append("视野内没有外国军事单位。")
        lines.append("\n## 城防")
        for c in sit.cities:
            lines.append(
                f"- {c.name}：防御 {c.defense_strength}，城墙 {c.wall_hp}/{c.wall_max_hp}，"
                f"驻军 {c.garrison_unit or '无'}"
            )
        lines.append("\n" + report.findings_block(mil))
        return "\n".join(lines)

    return await _safe(run)


# ---------------------------------------------------------------- 细分查询（复用 civ6-mcp 的叙述函数）


@mcp.tool(annotations={"readOnlyHint": True})
async def get_cities_detail() -> str:
    """所有城市的详细数据：产出、成长、住房、宜居、忠诚、区域、建筑、未改良资源。"""

    async def run():
        sit = await _situation()
        return nr.narrate_cities(sit.cities)

    return await _safe(run)


@mcp.tool(annotations={"readOnlyHint": True})
async def get_production_options(city_id: int) -> str:
    """某座城市现在能生产什么（单位、建筑、区域、项目）以及各需要几回合。

    Args:
        city_id: 城市 ID（从简报或 get_cities_detail 里拿）
    """
    if m := _mock_unavailable():
        return m
    return await _safe(lambda: _narr(_get_game().list_city_production(city_id), nr.narrate_city_production))


@mcp.tool(annotations={"readOnlyHint": True})
async def get_tech_civic_options() -> str:
    """当前可研究的科技和可推进的市政，含进度、回合数、尤里卡/鼓舞状态和触发条件。"""

    async def run():
        sit = await _situation()
        return nr.narrate_tech_civics(sit.tech) if sit.tech else "没有科技市政数据。"

    return await _safe(run)


@mcp.tool(annotations={"readOnlyHint": True})
async def get_diplomacy_overview() -> str:
    """已相遇文明的外交状态、关系分、军力、议程，以及城邦使者情况。"""

    async def run():
        sit = await _situation()
        out = nr.narrate_diplomacy(sit.diplomacy)
        if sit.envoys:
            out += "\n\n" + nr.narrate_city_states(sit.envoys)
        return out

    return await _safe(run)


@mcp.tool(annotations={"readOnlyHint": True})
async def get_government() -> str:
    """政体、政策槽和可用政策，以及总督状态。"""

    async def run():
        sit = await _situation()
        parts = []
        if sit.government:
            parts.append(nr.narrate_policies(sit.government))
        if sit.governors:
            parts.append(nr.narrate_governors(sit.governors))
        return "\n\n".join(parts) or "没有政体数据。"

    return await _safe(run)


@mcp.tool(annotations={"readOnlyHint": True})
async def get_units_detail() -> str:
    """我方所有单位：位置、血量、行动力、可晋升/可升级状态，附带周边威胁。"""

    async def run():
        sit = await _situation()
        return nr.narrate_units(sit.units, sit.threats)

    return await _safe(run)


@mcp.tool(annotations={"readOnlyHint": True})
async def get_builder_tasks() -> str:
    """建造者任务板：哪些地块该建什么改良设施，哪个建造者离得最近。"""
    if m := _mock_unavailable():
        return m

    async def run():
        tasks, builders = await _get_game().get_builder_tasks()
        return nr.narrate_builder_tasks(tasks, builders)

    return await _safe(run)


@mcp.tool(annotations={"readOnlyHint": True})
async def get_settle_spots() -> str:
    """在已探索区域里推荐最好的新城址（按产出、水源、防御、资源打分）。"""
    if m := _mock_unavailable():
        return m

    async def run():
        cands = await _get_game().get_global_settle_scan()
        return nr.narrate_settle_candidates(cands) if cands else "已探索区域里没有合适的城址，需要继续探索。"

    return await _safe(run)


@mcp.tool(annotations={"readOnlyHint": True})
async def get_district_placement(city_id: int, district_type: str) -> str:
    """某座城市放某个区域的最佳位置（含相邻加成）。

    Args:
        city_id: 城市 ID
        district_type: 区域类型，如 DISTRICT_CAMPUS、DISTRICT_COMMERCIAL_HUB、DISTRICT_HOLY_SITE
    """
    if m := _mock_unavailable():
        return m

    async def run():
        res = await _get_game().get_district_advisor(city_id, district_type)
        return res if isinstance(res, str) else nr.narrate_district_advisor(res, district_type)

    return await _safe(run)


@mcp.tool(annotations={"readOnlyHint": True})
async def get_victory_progress() -> str:
    """各文明在科技/文化/宗教/外交/征服胜利上的进度。"""
    if m := _mock_unavailable():
        return m
    return await _safe(lambda: _narr(_get_game().get_victory_progress(), nr.narrate_victory_progress))


async def _narr(coro, fn):
    return fn(await coro)


@mcp.tool(annotations={"readOnlyHint": True})
async def search_knowledge(query: str, kind: str = "") -> str:
    """在本地文明6资料库里搜索（游戏导出的单位/建筑/科技/政策/信条等 + 攻略文章）。

    Args:
        query: 名字或关键词，如「奥罗莫骑兵」「学院区 相邻加成」「忠诚度」
        kind: 可选：单位/建筑/奇观/区域/改良设施/科技/市政/政策/政体/信条/总督/文明/领袖/攻略
    """
    from civ6_advisor import llm as _llm
    from civ6_advisor.kb import get_kb

    await _ensure_kb_once()
    return _llm.run_tool(get_kb(), "search_knowledge", json.dumps({"query": query, "kind": kind}, ensure_ascii=False))


@mcp.tool(annotations={"readOnlyHint": True})
async def get_entry(name: str) -> str:
    """取资料库里一个条目的完整说明（数值、前置、替代关系、相邻加成、解锁内容）。

    Args:
        name: 名字或类型名，如「开拓者」或 UNIT_SETTLER
    """
    from civ6_advisor import llm as _llm
    from civ6_advisor.kb import get_kb

    await _ensure_kb_once()
    return _llm.run_tool(get_kb(), "get_entry", json.dumps({"name": name}, ensure_ascii=False))


_kb_ready = False


async def _ensure_kb_once():
    global _kb_ready
    if _kb_ready or MOCK:
        return
    try:
        from civ6_advisor.kb import ensure_game_kb

        sit = await _situation()
        await ensure_game_kb(_get_game().conn, sit.civ.civ_type if sit.civ else None)
        _kb_ready = True
    except Exception:  # noqa: BLE001  连不上游戏时只用攻略库
        pass


@mcp.prompt(name="军师", description="以文明6军师身份分析当前局势")
def advisor_prompt() -> str:
    return ADVISOR_PROMPT + "\n\n现在请分析我这局游戏，告诉我这回合该做什么。"


# ---------------------------------------------------------------- 命令行


async def _cli_brief() -> None:
    try:
        sit = await _situation(fresh=True)
    except Exception as e:  # noqa: BLE001
        print(_friendly_error(e))
        return
    print(report.full_brief(sit, analyze(sit)))


async def _cli_watch(interval: float = 3.0) -> None:
    """轮询回合数，新回合开始时打印优先事项。"""
    last_turn = None
    print("军师已就位，等待新回合……（Ctrl+C 退出）")
    while True:
        try:
            if MOCK:
                ov_turn = (await _situation(fresh=True)).overview.turn
            else:
                ov_turn = (await _get_game().get_game_overview()).turn
            if ov_turn != last_turn:
                last_turn = ov_turn
                sit = await _situation(fresh=True)
                print("\n" + "=" * 60)
                print(report.top_moves(sit, analyze(sit)))
        except Exception as e:  # noqa: BLE001
            print(_friendly_error(e).splitlines()[0])
        await asyncio.sleep(interval)


def main() -> None:
    logging.basicConfig(level=logging.WARNING, stream=sys.stderr)
    cmd = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if cmd in ("brief", "watch"):
        # Windows 终端默认 GBK，emoji 会报错
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
    if cmd == "brief":
        asyncio.run(_cli_brief())
    elif cmd == "watch":
        try:
            asyncio.run(_cli_watch())
        except KeyboardInterrupt:
            pass
    else:
        mcp.run()


if __name__ == "__main__":
    main()
