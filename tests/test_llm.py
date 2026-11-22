"""大模型调用测试：用本地假服务模拟 OpenAI 兼容的流式接口。"""

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from civ6_advisor import llm


def test_parse_sse_line():
    line = "data: " + json.dumps({"choices": [{"delta": {"content": "你好"}}]})
    assert llm.parse_sse_line(line) == "你好"
    assert llm.parse_sse_line("data: [DONE]") is None
    assert llm.parse_sse_line(": keep-alive") is None
    assert llm.parse_sse_line("data: {bad json") is None


def test_missing_key(monkeypatch):
    monkeypatch.delenv("CIV6_LLM_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="CIV6_LLM_API_KEY"):
        list(llm.stream_advice("brief"))


@pytest.fixture
def fake_server():
    seen = {}

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            seen["body"] = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen["auth"] = self.headers["Authorization"]
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            for piece in ["局势：", "前期偏弱"]:
                self.wfile.write(f"data: {json.dumps({'choices': [{'delta': {'content': piece}}]})}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/v1", seen
    srv.shutdown()


def test_stream_roundtrip(monkeypatch, fake_server):
    url, seen = fake_server
    monkeypatch.setenv("CIV6_LLM_BASE_URL", url)
    monkeypatch.setenv("CIV6_LLM_API_KEY", "sk-test")
    monkeypatch.setenv("CIV6_LLM_MODEL", "test-model")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    out = "".join(llm.stream_advice("简报内容"))
    assert out == "局势：前期偏弱"
    assert seen["auth"] == "Bearer sk-test"
    assert seen["body"]["model"] == "test-model" and seen["body"]["stream"] is True
    assert "简报内容" in seen["body"]["messages"][1]["content"]


# ---------------------------------------------------------------- 查资料工具


@pytest.fixture
def tool_server():
    """第一次请求：模型要求调用 get_entry 查「奥罗莫骑兵」；第二次（带工具结果）：给出回答。
    mode=reject 时，带 tools 的请求一律返回 400（模拟不支持工具的服务）。"""
    state = {"requests": [], "mode": "ok"}

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            state["requests"].append(body)
            if state["mode"] == "reject" and "tools" in body:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'{"error":"tools is not supported for this model"}')
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()

            def send(delta):
                self.wfile.write(f"data: {json.dumps({'choices': [{'delta': delta}]}, ensure_ascii=False)}\n\n".encode())

            has_tool_result = any(m["role"] == "tool" for m in body["messages"])
            if "tools" in body and not has_tool_result:
                send({"tool_calls": [{"index": 0, "id": "c1", "function": {"name": "get_entry", "arguments": '{"na'}}]})
                send({"tool_calls": [{"index": 0, "function": {"arguments": 'me": "奥罗莫骑兵"}'}}]})
            else:
                send({"content": "奥罗莫骑兵移动力 5，"})
                send({"content": "适合骚扰。"})
            self.wfile.write(b"data: [DONE]\n\n")

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/v1", state
    srv.shutdown()


class FakeKB:
    has_game_data = True

    def get(self, name):
        return name if name == "奥罗莫骑兵" else None

    def render(self, e, limit=900):
        return "【单位】奥罗莫骑兵 近战：48；移动：5"

    def search(self, q, k=5, kinds=None):
        return []


def _env(monkeypatch, url):
    monkeypatch.setenv("CIV6_LLM_BASE_URL", url)
    monkeypatch.setenv("CIV6_LLM_API_KEY", "sk-test")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setattr(llm, "_tools_unsupported", False)


def test_tool_call_roundtrip(monkeypatch, tool_server):
    url, state = tool_server
    _env(monkeypatch, url)
    out = list(llm.stream_advice("简报", "奥罗莫骑兵怎么用", kb=FakeKB(), context="## 资料库\n..."))
    statuses = [x for x in out if isinstance(x, llm.Status)]
    text = "".join(x for x in out if not isinstance(x, llm.Status))
    assert statuses == ["正在查：奥罗莫骑兵"]
    assert text == "奥罗莫骑兵移动力 5，适合骚扰。"
    second = state["requests"][1]["messages"]
    assert second[-2]["tool_calls"][0]["function"] == {"name": "get_entry", "arguments": '{"name": "奥罗莫骑兵"}'}
    assert second[-1] == {"role": "tool", "tool_call_id": "c1", "content": "【单位】奥罗莫骑兵 近战：48；移动：5"}
    assert "## 资料库" in state["requests"][0]["messages"][1]["content"]
    assert "玩家的问题：奥罗莫骑兵怎么用" in state["requests"][0]["messages"][1]["content"]


def test_tools_rejected_falls_back(monkeypatch, tool_server):
    url, state = tool_server
    state["mode"] = "reject"
    _env(monkeypatch, url)
    out = list(llm.stream_advice("简报", kb=FakeKB()))
    assert any(isinstance(x, llm.Status) and "不支持" in x for x in out)
    assert "".join(x for x in out if not isinstance(x, llm.Status)) == "奥罗莫骑兵移动力 5，适合骚扰。"
    assert "tools" not in state["requests"][-1]
    # 之后不再尝试工具
    list(llm.stream_advice("简报", kb=FakeKB()))
    assert "tools" not in state["requests"][-1]


def test_run_tool_search_and_unknown():
    from civ6_advisor.kb import KnowledgeBase

    kb = KnowledgeBase(None)
    assert "忠诚" in llm.run_tool(kb, "search_knowledge", '{"query": "忠诚度掉了", "kind": "攻略"}')
    assert "没有找到" in llm.run_tool(kb, "search_knowledge", '{"query": "zzzzqqq"}')
    assert llm.run_tool(kb, "nope", "{}").startswith("未知工具")
