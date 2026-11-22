"""步骤日志：每次读取前后落盘；最后一步没完成能被识别；诊断报告包含日志。"""

import asyncio
import importlib

import pytest


@pytest.fixture
def sl(tmp_path, monkeypatch):
    monkeypatch.setenv("CIV6_ADVISOR_HOME", str(tmp_path))
    import civ6_advisor.steplog as m

    return importlib.reload(m)


class Conn:
    async def execute_read(self, code, timeout=5.0):
        return ["a", "b"]

    async def execute_write(self, code, timeout=5.0):
        raise RuntimeError("boom")


def test_log_and_unfinished(sl):
    c = Conn()
    sl.instrument(c)
    sl.instrument(c)  # 重复包装无副作用
    with sl.step("读城市"):
        assert asyncio.run(c.execute_read("print(1)")) == ["a", "b"]
    with pytest.raises(RuntimeError):
        asyncio.run(c.execute_write("UI.LookAtPlot(p)"))
    text = sl.LOG_FILE.read_text(encoding="utf-8")
    assert "→ 读城市（游戏层）" in text and "✓ 读城市" in text and "2行" in text
    assert "✗ Lua: UI.LookAtPlot(p) RuntimeError: boom" in text
    assert sl.last_unfinished() is None
    sl._write("→ get_cities（游戏层）")  # 模拟崩溃：只有开始没有结束
    assert sl.last_unfinished() == "get_cities（游戏层）"
    p = sl.report({"AI 军师": "关"})
    body = p.read_text(encoding="utf-8")
    assert "最后一步没有完成：get_cities" in body and "AI 军师：关" in body
    sl.note("军师启动")
    assert sl.last_unfinished() is None


def test_readonly_game_logs_method_names(sl, monkeypatch):
    from civ6_advisor import game

    g = game.ReadOnlyGame()
    assert getattr(g._gs.conn, "_civ6_logged", False)  # 连接已被包装

    async def fake(*a, **kw):
        return "ok"

    monkeypatch.setattr(g._gs, "get_cities", fake)
    assert asyncio.run(g.get_cities()) == "ok"
    with pytest.raises(AttributeError):
        g.end_turn  # noqa: B018  白名单外的方法
