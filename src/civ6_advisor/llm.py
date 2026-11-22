"""调用大模型做分析（OpenAI 兼容接口，流式），可以查本地资料库。

支持任何 OpenAI 兼容服务：DeepSeek、通义千问（百炼）、Kimi、OpenRouter、本地 Ollama 等。

资料库的用法：
  1. 每次提问自动附上和当前局势最相关的资料（本文明特色、可选科技市政、可造项目、敌军数值、攻略段落）
  2. 再给模型两个工具 search_knowledge / get_entry，它觉得资料不够时可以自己查
     （模型或服务不支持工具调用时自动退回第 1 种方式）

环境变量：
  CIV6_LLM_BASE_URL   默认 https://api.deepseek.com/v1
  CIV6_LLM_API_KEY    必填
  CIV6_LLM_MODEL      默认 deepseek-flash
"""

from __future__ import annotations

import json
import os
from typing import Iterator

import httpx

OVERLAY_SYSTEM = """你是一位精通《文明6》的军师，正在看玩家的实时局势简报（由规则引擎生成）。
规则引擎给的是体检结果，你要在此基础上做判断，不要复述。

你能用的资料：
- 简报里的「文明与领袖」：能力原文来自游戏，建议必须围绕这个文明的特色来（用好特色单位/区域/建筑、走擅长的胜利路线、避开限制），不同文明的建议应当明显不同。
- 「资料库」一节：游戏数据和攻略库里与本局相关的条目，数值以它为准。
- 其中「文明攻略」是这个文明的专门打法（胜利倾向、关键时机、局势→建议、各路线、弱点）。先对照它的「关键时机」和「局势 → 建议」判断本回合该做什么；攻略和当前局势冲突时（比如敌军压境）以局势为准，并说明为什么偏离攻略。
- 如果简报里有「玩家选择的流派」：玩家想按这个流派玩。本回合建议要服务于流派的下一个里程碑和核心思路（比如砍树流就要安排马格努斯、建造者和留树），并说明这一步在流派里的作用；落后于计划时给追赶办法。但城市被威胁、金币归零这类止损永远优先；流派前提失效（如宗教名额没了）时直接说明并给转型方案。没有流派时按常规建议。
- 对手文明的反制思路：用 get_entry 查「<对手文明名>攻略」，看「对手是X时」一节。
- 工具 search_knowledge / get_entry：需要某个单位、建筑、科技、政策、信条等的具体数值或效果时去查，不要凭记忆编数值。
像高手一样判断时机，而不是罗列玩法：
1. 先排除本回合会直接吃亏的事（城市被威胁、生产/研究空转、金币归零）。
2. 再看有时间窗口、错过就没了的事：宗教名额、奇观竞争、开局扩张期、蛮族营地刚出现、尤里卡/鼓舞顺手能触发。
3. 最后才是效率优化。
建议之间必须自洽：比如资源还缺科技就不能叫建造者去改良它；推荐科技时说清楚它和本回合其他建议的先后关系。
涉及具体格子时，用简报里的方位描述（如"西安东北 3 格"）告诉玩家位置。迷雾里的信息不要编造。

回答格式（会显示在游戏上方的小悬浮窗里，必须短）：
- 如果玩家问了具体问题：直接回答这个问题，3-8 行。
- 否则：第一行一句话局势判断（不超过 30 字）；然后"本回合"最多 5 条，按先后排，每条一行，写清楚哪座城/哪个单位做什么，理由用括号简写；最后"接下来 10 回合"1-2 条方向。
- 不要用 Markdown 标题和表格，不要寒暄。
"""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_knowledge",
            "description": "在本地文明6资料库里搜索：单位、建筑、奇观、区域、改良设施、资源、科技、市政、政策、政体、信条、总督、文明、领袖，以及攻略文章。返回最相关的几条。",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "要查的名字或关键词，如「奥罗莫骑兵」「学院区 相邻加成」「忠诚度」"},
                    "kind": {"type": "string", "description": "可选，只查某一类",
                             "enum": ["单位", "建筑", "奇观", "区域", "改良设施", "科技", "市政", "政策", "政体", "信条", "总督", "文明", "领袖", "攻略"]},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_entry",
            "description": "按名字或类型名（如 UNIT_SETTLER）取一个条目的完整说明，包括数值、前置科技、替代关系、相邻加成、解锁内容。",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
    },
]

KIND_FROM_CN = {"单位": "UNIT", "建筑": "BUILDING", "奇观": "WONDER", "区域": "DISTRICT", "改良设施": "IMPROVEMENT",
                "科技": "TECH", "市政": "CIVIC", "政策": "POLICY", "政体": "GOVERNMENT", "信条": "BELIEF",
                "总督": "GOVERNOR", "文明": "CIV", "领袖": "LEADER", "攻略": "GUIDE"}
MAX_TOOL_ROUNDS = 4

_tools_unsupported = False  # 本次运行中发现服务不支持工具调用后就不再尝试
_usage_unsupported = False  # 服务不接受 stream_options 时不再要用量统计

# ------------------------------------------------------------------ 用量和花费
# DeepSeek 官方价（美元 / 百万 token，2026-11）：高峰 = 北京时间工作日 9-12、14-18 点，其余闲时（半价）。
# 键是模型名里包含的关键字；不认识的模型只统计 token，不算钱。
PRICES = {
    "deepseek-v4-pro": {"hit": 0.044, "miss": 1.32, "out": 3.96},
    "deepseek-flash": {"hit": 0.006, "miss": 0.30, "out": 1.20},
    "deepseek-v4-flash": {"hit": 0.006, "miss": 0.30, "out": 1.20},
    "deepseek-chat": {"hit": 0.006, "miss": 0.30, "out": 1.20},
    "deepseek-reasoner": {"hit": 0.006, "miss": 0.30, "out": 1.20},
}
USD_CNY = float(os.environ.get("CIV6_USD_CNY", "7.2"))


def is_peak(now=None) -> bool:
    import datetime as dt

    now = now or dt.datetime.now(dt.timezone(dt.timedelta(hours=8)))
    if now.weekday() >= 5:
        return False
    return 9 <= now.hour < 12 or 14 <= now.hour < 18


def price_for(model: str) -> dict | None:
    m = model.lower()
    for k in sorted(PRICES, key=len, reverse=True):
        if k in m:
            return PRICES[k]
    return None


class UsageBook:
    """本次运行累计用量（一次运行基本就是一局）。"""

    def __init__(self):
        self.calls = 0  # 问 AI 的次数
        self.prompt = self.hit = self.completion = 0
        self.cny = 0.0
        self.priced = True
        self.last_cny = 0.0

    def add(self, model: str, usage: dict, peak: bool | None = None) -> float:
        prompt = int(usage.get("prompt_tokens") or 0)
        hit = int(usage.get("prompt_cache_hit_tokens") or
                  (usage.get("prompt_tokens_details") or {}).get("cached_tokens") or 0)
        out = int(usage.get("completion_tokens") or 0)
        self.prompt += prompt
        self.hit += hit
        self.completion += out
        p = price_for(model)
        if p is None:
            self.priced = False
            return 0.0
        k = 1.0 if (is_peak() if peak is None else peak) else 0.5
        usd = k * (hit * p["hit"] + (prompt - hit) * p["miss"] + out * p["out"]) / 1e6
        cny = usd * USD_CNY
        self.cny += cny
        return cny

    def summary(self) -> str:
        if not self.calls:
            return ""
        toks = f"{(self.prompt + self.completion) / 1000:.0f}k token"
        if not self.priced:
            return f"本局已问 {self.calls} 次 · {toks}"
        return f"本局已问 {self.calls} 次 · 约 ¥{self.cny:.2f}（{toks}）"


USAGE = UsageBook()


class Status(str):
    """流里的状态提示（不是回答正文），比如"正在查：奥罗莫骑兵"。"""


def config() -> tuple[str, str, str]:
    base = os.environ.get("CIV6_LLM_BASE_URL", "https://api.deepseek.com/v1").rstrip("/")
    key = os.environ.get("CIV6_LLM_API_KEY", "")
    model = os.environ.get("CIV6_LLM_MODEL", "deepseek-flash")
    return base, key, model


def is_configured() -> bool:
    return bool(config()[1])


def parse_sse_obj(line: str) -> dict | None:
    if not line.startswith("data:"):
        return None
    data = line[5:].strip()
    if not data or data == "[DONE]":
        return None
    try:
        return json.loads(data)
    except json.JSONDecodeError:
        return None


def parse_sse_line(line: str) -> str | None:
    """解析一行 SSE，返回增量文本；非内容行返回 None。"""
    obj = parse_sse_obj(line)
    try:
        return obj["choices"][0]["delta"].get("content") or None if obj else None
    except (KeyError, IndexError, AttributeError):
        return None


# ------------------------------------------------------------------ 工具执行


def run_tool(kb, name: str, args_json: str) -> str:
    try:
        args = json.loads(args_json or "{}")
    except json.JSONDecodeError:
        args = {}
    if kb is None:
        return "资料库不可用。"
    if name == "search_knowledge":
        q = str(args.get("query", "")).strip()
        kinds = {KIND_FROM_CN[args["kind"]]} if args.get("kind") in KIND_FROM_CN else None
        if kinds == {"GUIDE"}:
            kinds = {"GUIDE", "CIVGUIDE"}
        hits = kb.search(q, k=5, kinds=kinds)
        if not hits:
            return f"没有找到和「{q}」相关的条目。" + ("" if kb.has_game_data else "（游戏资料库还没建立，只有攻略库）")
        return "\n\n".join(kb.render(e, 600) for e in hits)
    if name == "get_entry":
        e = kb.get(str(args.get("name", "")))
        return kb.render(e, 2000) if e else "没有这个条目。"
    return f"未知工具 {name}"


def _tool_label(name: str, args_json: str) -> str:
    try:
        a = json.loads(args_json or "{}")
    except json.JSONDecodeError:
        a = {}
    return a.get("query") or a.get("name") or name


# ------------------------------------------------------------------ 主流程


def stream_advice(brief: str, question: str = "", kb=None, context: str = "") -> Iterator[str]:
    """流式返回军师回答的文本片段；查资料时会产出 Status。出错时抛 RuntimeError（带中文说明）。"""
    global _tools_unsupported
    base, key, model = config()
    if not key:
        raise RuntimeError("没有配置大模型：请在启动器里填写 API Key（或设置环境变量 CIV6_LLM_API_KEY）")
    user = brief
    if context:
        user += "\n\n" + context
    user += ("\n\n玩家的问题：" + question) if question else "\n\n这回合我该做什么？"
    messages: list[dict] = [{"role": "system", "content": OVERLAY_SYSTEM}, {"role": "user", "content": user}]
    use_tools = kb is not None and not _tools_unsupported
    USAGE.calls += 1
    before = USAGE.cny
    try:
        yield from _advice_rounds(base, key, model, messages, use_tools, kb)
    finally:
        USAGE.last_cny = USAGE.cny - before


def _advice_rounds(base, key, model, messages, use_tools, kb):
    global _tools_unsupported

    for _round in range(MAX_TOOL_ROUNDS + 1):
        body = {"model": model, "stream": True, "temperature": 0.4, "messages": messages}
        if not _usage_unsupported:
            body["stream_options"] = {"include_usage": True}
        if use_tools and _round < MAX_TOOL_ROUNDS:
            body["tools"] = TOOLS
        try:
            calls, text = yield from _stream_once(base, key, body)
        except _ToolsRejected:
            _tools_unsupported = True
            use_tools = False
            yield Status("这个模型不支持查资料工具，改用自动附带的资料回答")
            body.pop("tools", None)
            calls, text = yield from _stream_once(base, key, body)
        if not calls:
            return
        messages.append({"role": "assistant", "content": text or None, "tool_calls": [
            {"id": c["id"], "type": "function", "function": {"name": c["name"], "arguments": c["args"]}} for c in calls
        ]})
        for c in calls:
            yield Status(f"正在查：{_tool_label(c['name'], c['args'])}")
            messages.append({"role": "tool", "tool_call_id": c["id"], "content": run_tool(kb, c["name"], c["args"])})


class _ToolsRejected(Exception):
    pass


def _stream_once(base: str, key: str, body: dict):
    """发一次流式请求：产出正文片段，返回 (工具调用列表, 正文)。"""
    global _usage_unsupported
    try:
        return (yield from _stream_once_raw(base, key, body))
    except _OptionRejected:
        _usage_unsupported = True
        body.pop("stream_options", None)
        return (yield from _stream_once_raw(base, key, body))


class _OptionRejected(Exception):
    pass


def _stream_once_raw(base: str, key: str, body: dict):
    calls: dict[int, dict] = {}
    text = []
    try:
        with httpx.stream(
            "POST", f"{base}/chat/completions", headers={"Authorization": f"Bearer {key}"},
            json=body, timeout=httpx.Timeout(90, connect=10),
        ) as r:
            if r.status_code != 200:
                r.read()
                msg = r.text[:300]
                if "tools" in body and r.status_code in (400, 404, 422) and any(
                        w in msg.lower() for w in ("tool", "function")):
                    raise _ToolsRejected()
                if "stream_options" in body and r.status_code in (400, 422) and "stream_options" in msg:
                    raise _OptionRejected()
                raise RuntimeError(f"大模型接口返回 {r.status_code}：{msg[:200]}")
            for line in r.iter_lines():
                obj = parse_sse_obj(line)
                if obj and obj.get("usage"):
                    USAGE.add(body.get("model", ""), obj["usage"])
                if not obj or not obj.get("choices"):
                    continue
                delta = obj["choices"][0].get("delta") or {}
                piece = delta.get("content")
                if piece:
                    text.append(piece)
                    yield piece
                for tc in delta.get("tool_calls") or []:
                    slot = calls.setdefault(tc.get("index", 0), {"id": "", "name": "", "args": ""})
                    slot["id"] = tc.get("id") or slot["id"]
                    fn = tc.get("function") or {}
                    slot["name"] += fn.get("name") or ""
                    slot["args"] += fn.get("arguments") or ""
    except httpx.HTTPError as e:
        raise RuntimeError(f"请求大模型失败：{e}") from e
    out = [c for _, c in sorted(calls.items()) if c["name"]]
    for i, c in enumerate(out):
        c["id"] = c["id"] or f"call_{i}"
    return out, "".join(text)
