"""AI 自动分析的触发逻辑 + 用量/花费统计。"""

import dataclasses
import datetime as dt
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from civ6_advisor import autoask, llm
from civ6_advisor.mock import mock_situation
from civ6_advisor.playstyles import playstyle_for
from civ6_advisor.rules import Finding, Priority, analyze


def _turn(sit, n):
    sit.overview = dataclasses.replace(sit.overview, turn=n)
    return sit


def test_off_never_asks():
    st = autoask.AutoState()
    sit = mock_situation()
    assert autoask.auto_reason("off", sit, analyze(sit), st) is None


def test_every_always_asks():
    st = autoask.AutoState()
    sit = mock_situation()
    for t in (10, 11, 12):
        assert autoask.auto_reason("every", _turn(sit, t), analyze(sit), st)


def test_smart_triggers():
    st = autoask.AutoState()
    sit = mock_situation()
    f = analyze(sit)
    assert "整体分析" in autoask.auto_reason("smart", _turn(sit, 68), f, st)
    # 下回合什么都没变：不问
    assert autoask.auto_reason("smart", _turn(sit, 69), f, st) is None
    # 出现新的紧急情况：问，并点名
    f2 = f + [Finding(Priority.URGENT, "军事", "西安 即将被攻破", "")]
    r = autoask.auto_reason("smart", _turn(sit, 70), f2, st)
    assert r and "西安 即将被攻破" in r and r.startswith("新的紧急情况")
    assert "先处理" in autoask.question_for(r)
    # 同样的情况持续：不重复问
    assert autoask.auto_reason("smart", _turn(sit, 71), f2, st) is None
    # 隔了 8 回合：定期复盘
    assert "定期复盘" in autoask.auto_reason("smart", _turn(sit, 70 + autoask.REVIEW_EVERY), f2, st)


def test_smart_playstyle_step_change():
    st = autoask.AutoState()
    sit = mock_situation()
    sit.playstyle = playstyle_for(sit.civ.civ_type).id
    f = analyze(sit)
    autoask.auto_reason("smart", _turn(sit, 68), f, st)
    sit.facts.techs.add("TECH_MASONRY")  # 完成「石工术」里程碑
    r = autoask.auto_reason("smart", _turn(sit, 69), f, st)
    assert r and r.startswith("流派进入下一步")


def test_usage_cost_peak_offpeak():
    book = llm.UsageBook()
    u = {"prompt_tokens": 10000, "prompt_cache_hit_tokens": 4000, "completion_tokens": 1000}
    peak = book.add("deepseek-flash", u, peak=True)
    off = book.add("deepseek-flash", u, peak=False)
    usd_peak = (4000 * 0.006 + 6000 * 0.30 + 1000 * 1.20) / 1e6
    assert peak == pytest.approx(usd_peak * llm.USD_CNY)
    assert off == pytest.approx(peak / 2)
    book.calls = 2
    assert "¥" in book.summary()
    unknown = llm.UsageBook()
    unknown.add("qwen-plus", u)
    unknown.calls = 1
    assert not unknown.priced and "¥" not in unknown.summary()


def test_is_peak():
    tz = dt.timezone(dt.timedelta(hours=8))
    assert llm.is_peak(dt.datetime(2026, 11, 20, 10, 0, tzinfo=tz))  # 周五上午
    assert not llm.is_peak(dt.datetime(2026, 11, 20, 13, 0, tzinfo=tz))
    assert not llm.is_peak(dt.datetime(2026, 11, 21, 10, 0, tzinfo=tz))  # 周六


@pytest.fixture
def usage_server():
    seen = {"bodies": []}

    class H(BaseHTTPRequestHandler):
        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            seen["bodies"].append(body)
            if seen.get("reject_opts") and "stream_options" in body:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'{"error":"unknown field stream_options"}')
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(f"data: {json.dumps({'choices': [{'delta': {'content': '好'}}]})}\n\n".encode())
            usage = {"prompt_tokens": 8000, "prompt_cache_hit_tokens": 0, "completion_tokens": 500}
            self.wfile.write(f"data: {json.dumps({'choices': [], 'usage': usage})}\n\n".encode())
            self.wfile.write(b"data: [DONE]\n\n")

        def log_message(self, *a):
            pass

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}/v1", seen
    srv.shutdown()


def test_stream_records_usage(monkeypatch, usage_server):
    url, seen = usage_server
    monkeypatch.setenv("CIV6_LLM_BASE_URL", url)
    monkeypatch.setenv("CIV6_LLM_API_KEY", "sk-test")
    monkeypatch.setenv("CIV6_LLM_MODEL", "deepseek-flash")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setattr(llm, "USAGE", llm.UsageBook())
    monkeypatch.setattr(llm, "_usage_unsupported", False)
    assert "".join(llm.stream_advice("简报")) == "好"
    assert seen["bodies"][0]["stream_options"] == {"include_usage": True}
    assert llm.USAGE.calls == 1 and llm.USAGE.prompt == 8000 and llm.USAGE.last_cny > 0


def test_stream_options_rejected_falls_back(monkeypatch, usage_server):
    url, seen = usage_server
    seen["reject_opts"] = True
    monkeypatch.setenv("CIV6_LLM_BASE_URL", url)
    monkeypatch.setenv("CIV6_LLM_API_KEY", "sk-test")
    monkeypatch.setenv("NO_PROXY", "127.0.0.1")
    monkeypatch.setattr(llm, "USAGE", llm.UsageBook())
    monkeypatch.setattr(llm, "_usage_unsupported", False)
    assert "".join(llm.stream_advice("简报")) == "好"
    assert "stream_options" not in seen["bodies"][-1]
