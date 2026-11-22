"""步骤日志：记录军师对游戏的每一次读取（开始/结束/耗时），每行立即落盘。

游戏如果在某次读取时崩溃，日志最后一行会停在「→ 某某」而没有「✓」，
下次启动时就能告诉玩家（和开发者）是哪一步出的事。日志文件：~/.civ6-advisor/steps.log
"""

from __future__ import annotations

import contextvars
import os
import platform
import sys
import time
from contextlib import contextmanager
from pathlib import Path

DIR = Path(os.environ.get("CIV6_ADVISOR_HOME", Path.home() / ".civ6-advisor"))
LOG_FILE = DIR / "steps.log"
REPORT_FILE = DIR / "诊断报告.txt"
MAX_BYTES = 512 * 1024

_step: contextvars.ContextVar[str] = contextvars.ContextVar("civ6_step", default="")


def _write(line: str) -> None:
    try:
        DIR.mkdir(parents=True, exist_ok=True)
        if LOG_FILE.exists() and LOG_FILE.stat().st_size > MAX_BYTES:
            keep = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-1500:]
            LOG_FILE.write_text("\n".join(keep) + "\n", encoding="utf-8")
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(time.strftime("%m-%d %H:%M:%S ") + line + "\n")
            f.flush()
            os.fsync(f.fileno())  # 游戏或军师崩溃时也不丢最后几行
    except OSError:
        pass


def note(msg: str) -> None:
    _write("· " + msg)


@contextmanager
def step(label: str):
    tok = _step.set(label)
    try:
        yield
    finally:
        _step.reset(tok)


def _label(code: str) -> str:
    cur = _step.get()
    if cur:
        return cur
    first = next((ln.strip() for ln in code.splitlines() if ln.strip() and not ln.strip().startswith("--")), "")
    return "Lua: " + first[:50]


def instrument(conn) -> None:
    """包住连接的 execute_read / execute_write：每次调用前后写日志。重复调用无副作用。"""
    if getattr(conn, "_civ6_logged", False):
        return
    for name in ("execute_read", "execute_write"):
        orig = getattr(conn, name, None)
        if orig is None:
            continue

        def make(orig=orig, name=name):
            async def wrapped(code, *a, **kw):
                label = _label(code)
                state = "界面" if name == "execute_write" else "游戏"
                _write(f"→ {label}（{state}层）")
                t0 = time.perf_counter()
                try:
                    out = await orig(code, *a, **kw)
                except Exception as e:  # noqa: BLE001
                    _write(f"✗ {label} {type(e).__name__}: {str(e)[:120]}")
                    raise
                n = len(out) if isinstance(out, list) else 0
                _write(f"✓ {label} {1000 * (time.perf_counter() - t0):.0f}ms {n}行")
                return out

            return wrapped

        setattr(conn, name, make())
    conn._civ6_logged = True


def last_unfinished() -> str | None:
    """上次运行最后一步如果只有「→」没有结束，返回那一步的名字（可能就是游戏崩溃的位置）。"""
    try:
        lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return None
    for ln in reversed(lines):
        body = ln[15:] if len(ln) > 15 else ln
        if body.startswith("· "):
            if "军师启动" in body:
                return None
            continue
        if body.startswith("→ "):
            return body[2:]
        return None
    return None


def report(extra: dict[str, str] | None = None, tail: int = 120) -> Path:
    """生成诊断报告：环境、设置、最近的步骤日志。返回文件路径。"""
    try:
        lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()[-tail:]
    except OSError:
        lines = ["（还没有日志）"]
    head = [
        "文明6军师 诊断报告",
        f"生成时间：{time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"系统：{platform.platform()}  Python {sys.version.split()[0]}",
    ]
    try:
        from importlib.metadata import version

        head.append(f"civ6-advisor {version('civ6-advisor')}  civ6-mcp {version('civ6-mcp')}")
    except Exception:  # noqa: BLE001
        pass
    for k, v in (extra or {}).items():
        head.append(f"{k}：{v}")
    unfinished = last_unfinished()
    if unfinished:
        head.append(f"⚠ 最后一步没有完成：{unfinished}（如果游戏刚崩溃，多半就是这一步）")
    text = "\n".join(head + ["", f"—— 最近 {len(lines)} 行步骤日志 ——", *lines]) + "\n"
    DIR.mkdir(parents=True, exist_ok=True)
    REPORT_FILE.write_text(text, encoding="utf-8")
    return REPORT_FILE
