"""透明悬浮窗：置顶浮在游戏上方，每回合自动刷新军师建议。

运行：uv run civ6-overlay      （演示数据：设置 CIV6_ADVISOR_MOCK=1）

操作：
  - 按住窗口任意位置拖动；右下角拉伸
  - 点一条建议：游戏镜头移到对应格子，并在地图上插标记（名字以「军师·」开头）
  - 右下角托盘图标：显示/隐藏、鼠标穿透、地图自动标记、问AI、退出

快捷键（Windows 全局热键，游戏里也能用）：
  Ctrl+Shift+F1  切换鼠标穿透（穿透时点击会落到游戏上）
  Ctrl+Shift+F2  显示 / 隐藏
  Ctrl+Shift+F3  问 AI 军师

注意：文明6 需要「无边框窗口」或「窗口化」，独占全屏下任何悬浮窗都会被盖住（启动器会自动设置）。
"""

from __future__ import annotations

import asyncio
import html
import os
import sys
import time

from PySide6.QtCore import QMetaObject, QObject, QPoint, QRectF, QSettings, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QActionGroup, QColor, QFont, QIcon, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMenu,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSizeGrip,
    QSlider,
    QSystemTrayIcon,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from civ_mcp.lua._helpers import SENTINEL

from civ6_advisor import autoask, llm, report, steplog
from civ6_advisor.kb import ensure_game_kb, get_kb
from civ6_advisor.civs import profile_for
from civ6_advisor.game import ReadOnlyGame, Situation, collect_situation
from civ6_advisor.geo import KIND_COLOR, Plot, describe_sit
from civ6_advisor.highlight import Highlighter, focus_plot
from civ6_advisor.production import city_overview, empire_status
from civ6_advisor.playstyles import playstyle_for, progress
from civ6_advisor.research import Pick, TrackState, tracks
from civ6_advisor.rules import Finding, Priority, analyze, game_phase

IS_WIN = sys.platform == "win32"
MOCK = os.environ.get("CIV6_ADVISOR_MOCK") == "1"
POLL_SECONDS = 3.0
NEW_TURN_SETTLE = 4.0  # 新回合稳定几秒后再读取
FIRST_CONNECT_SETTLE = 8.0  # 刚进对局等几秒再开始读取
MAX_SHOWN = 6
AUTO_MARK_TOP = 5  # 新回合自动在地图上标出前几条建议的格子
DRAG_THRESHOLD = 5

PRIORITY_COLORS = {0: "#ff5c5c", 1: "#ffa94d", 2: "#ffd43b", 3: "#adb5bd"}

STYLE = """
QWidget { color: #e9ecef; font-size: 13px; }
QLabel { background: transparent; }
QLabel#title { font-size: 14px; font-weight: bold; color: #f8f0d8; }
QLabel#status { color: #8f96a3; font-size: 11px; }
QLabel#hint { color: #6c7380; font-size: 10px; }
QPushButton {
  background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.12);
  border-radius: 4px; padding: 2px 8px; color: #e9ecef;
}
QPushButton:hover { background: rgba(255,255,255,0.18); }
QPushButton#ask { background: rgba(214,170,80,0.35); border-color: rgba(214,170,80,0.6); }
QPushButton#ask:hover { background: rgba(214,170,80,0.55); }
QPushButton#ask:checked { background: rgba(116,192,252,0.45); border-color: rgba(116,192,252,0.9); color: #ffffff; }
QPushButton#style { text-align: left; padding: 3px 8px; color: #e9d8a6; }
QPushButton#style:checked { background: rgba(116,192,252,0.40); border-color: rgba(116,192,252,0.85); color: #ffffff; }
QFrame#civ { background: rgba(214,170,80,0.08); border: 1px solid rgba(214,170,80,0.35); border-radius: 8px; }
QFrame#track { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.10); border-radius: 8px; }
QFrame#track[warn="true"] { border-color: rgba(255,120,90,0.65); background: rgba(255,120,90,0.07); }
QLabel#chip { border-radius: 7px; padding: 0px 6px; font-size: 11px; }
QLabel#civname { font-size: 15px; font-weight: bold; color: #f0d796; }
QLabel#muted { color: #8f96a3; font-size: 11px; }
QLabel#ability { color: #b8bfca; font-size: 12px; }
QLabel#trackhead { font-size: 12px; color: #c9ced6; font-weight: bold; }
QLabel#trackname { font-size: 14px; font-weight: bold; color: #f1f3f5; }
QLabel#trackrec { font-size: 14px; font-weight: bold; color: #f0d796; }
QProgressBar { background: rgba(255,255,255,0.10); border: none; border-radius: 2px; max-height: 4px; }
QProgressBar::chunk { background: #4dabf7; border-radius: 2px; }
QFrame#row { background: transparent; border-radius: 6px; }
QFrame#row:hover { background: rgba(255,255,255,0.07); }
QFrame#row[active="true"] { background: rgba(77,171,247,0.16); }
QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; border: none; }
QTextBrowser { background: rgba(0,0,0,0.25); border: none; border-radius: 6px; padding: 4px; }
QLineEdit#ask { background: rgba(0,0,0,0.30); border: 1px solid rgba(214,170,80,0.40); border-radius: 6px;
  padding: 4px 8px; color: #e9ecef; }
QLineEdit#ask:focus { border-color: rgba(214,170,80,0.85); }
QScrollBar:vertical { width: 6px; background: transparent; }
QScrollBar::handle:vertical { background: rgba(255,255,255,0.25); border-radius: 3px; min-height: 20px; }
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page { height: 0; background: none; }
QSlider::groove:horizontal { height: 3px; background: rgba(255,255,255,0.2); }
QSlider::handle:horizontal { width: 10px; margin: -4px 0; border-radius: 5px; background: #d6aa50; }
"""


# ------------------------------------------------------------------ 后台：读游戏 + 地图标记


class GameWorker(QObject):
    """在独立线程里跑 asyncio：轮询回合、采集分析、执行地图标记。游戏只允许一个连接，全部走这里。"""

    updated = Signal(object, object)  # Situation, list[Finding]
    status = Signal(str)

    def __init__(self):
        super().__init__()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._game: ReadOnlyGame | None = None
        self._last_turn: int | None = None
        self._force = False
        self._timer: QTimer | None = None
        self.auto_mark = False  # 地图插旗默认关闭：改地图标记有让游戏崩溃的风险
        self._placed = False  # 本次运行插过旗才需要清理
        self.want_kb = False  # 只有开了 AI 军师才导出游戏资料库（给 AI 用）
        self._ready_since = 0.0  # 连上并确认已在对局里的时间
        self._pending_turn: int | None = None  # 新回合先等游戏处理完再读
        self._pending_since = 0.0
        self._cleaned = False  # 连上后先清理一次（修复旧版本导致的灰屏）
        self._kb_checked = False
        self._kb_force = False
        self.playstyle: str | None = None  # 开启的流派 id
        self._last_sit: Situation | None = None

    @Slot()
    def start(self):
        self._loop = asyncio.new_event_loop()
        self._timer = QTimer()
        self._timer.timeout.connect(self._tick)
        self._timer.start(int(POLL_SECONDS * 1000))
        self._tick()

    @Slot()
    def stop(self):
        if self._timer:
            self._timer.stop()
        if self._placed:
            self.clear_marks()  # 退出时删掉军师插的地图标记（没插过就不碰游戏）

    @Slot()
    def rebuild_kb(self):
        self._kb_force = True
        self._kb_checked = False
        if MOCK:
            self.status.emit("演示模式：资料库只有攻略库，连上游戏后才能导出游戏数据")
            return
        self._tick()

    def _ensure_kb(self, sit: Situation):
        if self._kb_checked or MOCK or self._game is None:
            return
        self._kb_checked = True
        civ = sit.civ.civ_type if sit.civ else None
        try:
            kb, rebuilt = self._run(ensure_game_kb(
                self._game.conn, civ, force=self._kb_force,
                progress=lambda t: self.status.emit(f"正在建立本地资料库：{t}…（首次约 10-30 秒）")))
            self._kb_force = False
            if rebuilt:
                self.status.emit(f"资料库已建立：{kb.stats()}")
        except Exception as e:  # noqa: BLE001
            self.status.emit(f"资料库建立失败：{str(e)[:50]}（只用攻略库）")

    @Slot()
    def clear_marks(self):
        if MOCK or self._game is None:
            return
        try:
            self._run(Highlighter(self._game.conn).clear(fix_gray=True))
            self.status.emit("已清除地图标记")
        except Exception:  # noqa: BLE001
            pass

    @Slot(object)
    def set_playstyle(self, pid):
        """开启/取消流派：用上一次读到的局势立刻重新分析，不用等下回合。"""
        self.playstyle = pid or None
        if self._last_sit is not None:
            self._emit(self._last_sit)

    @Slot()
    def refresh(self):
        self._force = True
        self._tick()

    @Slot(bool)
    def set_want_kb(self, on: bool):
        self.want_kb = on
        if on and self._last_sit is not None and not MOCK and self._game is not None:
            self._ensure_kb(self._last_sit)

    @Slot(bool)
    def set_auto_mark(self, on: bool):
        self.auto_mark = on
        if not on and self._placed:
            self._mark([], look=False)

    @Slot(object)
    def focus(self, plots: list[Plot]):
        """点击建议：镜头移过去；开了「地图插旗」才插标记和飘字。"""
        if self.auto_mark:
            self._mark(plots, look=True, labels=True)
            return
        fp = focus_plot(plots)
        if fp is None:
            return
        if MOCK:
            self.status.emit(f"演示模式：镜头移到 ({fp.x},{fp.y})")
            return
        if self._game is None:
            return
        try:
            self._run(Highlighter(self._game.conn).look(fp))
        except Exception as e:  # noqa: BLE001
            self.status.emit(f"移动镜头失败：{str(e)[:50]}")

    def _mark(self, plots: list[Plot], look: bool, labels: bool = False):
        if MOCK:
            fp = focus_plot(plots)
            if plots:
                self.status.emit(f"演示模式：会标出 {len(plots)} 个格子" + (f"，镜头移到 ({fp.x},{fp.y})" if look and fp else ""))
            return
        if self._game is None:
            return
        try:
            res = self._run(Highlighter(self._game.conn).show(plots, look=look, labels=labels))
            self._placed = bool(plots)
            if look and "pins:0" in res and "look" in res:
                self.status.emit("镜头已移动（这个版本没能插地图标记）")
        except Exception as e:  # noqa: BLE001
            self.status.emit(f"地图标记失败：{str(e)[:50]}")

    async def _ingame_ready(self) -> bool:
        """界面层（InGame）能执行代码且本地玩家有效，才算真正进了对局。"""
        try:
            lines = await self._game.conn.execute_write(
                f'local p = Game.GetLocalPlayer() print("READY|" .. tostring(p)) print("{SENTINEL}")', timeout=5.0)
        except Exception:  # noqa: BLE001
            return False
        return any(ln.startswith("READY|") and ln[6:].lstrip("-").isdigit() and int(ln[6:]) >= 0 for ln in lines)

    def _run(self, coro):
        return self._loop.run_until_complete(coro)

    def _tick(self):
        try:
            if MOCK:
                from civ6_advisor.mock import mock_situation

                if self._last_turn is None or self._force:
                    self._emit(mock_situation())
                self.status.emit("演示模式")
                return
            if self._game is None:
                self._game = ReadOnlyGame(os.environ.get("CIV6_HOST", "127.0.0.1"),
                                          int(os.environ.get("CIV6_PORT", "4318")))
            turn = self._run(self._game.get_game_overview()).turn
            # 刚进对局时界面可能还没加载完（加载画面、"开始游戏"按钮）：确认界面层可用并稳定几秒后才开始读
            if not self._ready_since:
                if not self._run(self._ingame_ready()):
                    self.status.emit("等待进入对局…")
                    return
                self._ready_since = time.time()
            if time.time() - self._ready_since < FIRST_CONNECT_SETTLE:
                self.status.emit("已进入对局，稍等几秒再读取…")
                return
            if turn != self._last_turn and not self._force:
                # 回合号刚变时游戏可能还在处理 AI 回合/自动存档，这时大量读取有让游戏崩溃的风险：等几秒再读
                if self._pending_turn != turn:
                    self._pending_turn, self._pending_since = turn, time.time()
                    self.status.emit(f"第 {turn} 回合，等游戏处理完…")
                    return
                if time.time() - self._pending_since < NEW_TURN_SETTLE:
                    return
            if turn != self._last_turn or self._force:
                self.status.emit(f"第 {turn} 回合，读取中…")
                sit = self._run(collect_situation(self._game))
                self._emit(sit)
                if self.want_kb:
                    self._ensure_kb(sit)
            self.status.emit(f"已连接 · {time.strftime('%H:%M:%S')}")
        except Exception as e:  # noqa: BLE001
            self._game = None
            self._last_turn = None
            self._cleaned = False
            self._ready_since = 0.0
            self._kb_checked = False
            msg = str(e)
            self.status.emit("未连接文明6（需进入对局并开启 Tuner）" if "connect" in msg.lower() or "states not found" in msg
                             else f"读取出错：{msg[:60]}")
        finally:
            self._force = False

    def _emit(self, sit: Situation):
        sit.playstyle = self.playstyle
        self._last_sit = sit
        self._last_turn = sit.overview.turn
        findings = analyze(sit)
        self.updated.emit(sit, findings)
        if self.auto_mark:
            plots = [p for f in findings[:AUTO_MARK_TOP] if f.category != "文明" for p in f.plots]
            self._mark(plots, look=False, labels=False)


# ------------------------------------------------------------------ 后台：问大模型


class LLMWorker(QThread):
    chunk = Signal(str)
    status = Signal(str)
    failed = Signal(str)

    def __init__(self, brief: str, question: str, context: str):
        super().__init__()
        self.brief, self.question, self.context = brief, question, context

    def run(self):
        try:
            for piece in llm.stream_advice(self.brief, self.question, kb=get_kb(), context=self.context):
                if isinstance(piece, llm.Status):
                    self.status.emit(str(piece))
                else:
                    self.chunk.emit(piece)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


# ------------------------------------------------------------------ Windows 全局热键 / 鼠标穿透

if IS_WIN:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    GWL_EXSTYLE = -20
    WS_EX_LAYERED = 0x00080000
    WS_EX_TRANSPARENT = 0x00000020
    WS_EX_NOACTIVATE = 0x08000000
    WM_HOTKEY = 0x0312
    MOD_CONTROL, MOD_SHIFT, MOD_NOREPEAT = 0x2, 0x4, 0x4000
    VK_F1, VK_F2, VK_F3 = 0x70, 0x71, 0x72
    _get_ex = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
    _set_ex = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
    _get_ex.restype = ctypes.c_ssize_t
    _get_ex.argtypes = [wintypes.HWND, ctypes.c_int]
    _set_ex.restype = ctypes.c_ssize_t
    _set_ex.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]

HOTKEY_CLICK_THROUGH, HOTKEY_TOGGLE, HOTKEY_ASK = 1, 2, 3


# ------------------------------------------------------------------ 小部件


def make_icon() -> QIcon:
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(28, 30, 38))
    p.setPen(QColor(214, 170, 80))
    p.drawEllipse(3, 3, 58, 58)
    p.setPen(QColor(240, 215, 150))
    f = QFont()
    f.setPixelSize(34)
    f.setBold(True)
    p.setFont(f)
    p.drawText(QRectF(0, 0, 64, 62), Qt.AlignCenter, "军")
    p.end()
    return QIcon(pm)


class DragMixin:
    """让子控件也能拖动整个悬浮窗：移动超过阈值算拖动，否则算点击。"""

    def _drag_press(self, e):
        self._press_global = e.globalPosition().toPoint()
        self._dragging = False

    def _drag_move(self, e) -> bool:
        if getattr(self, "_press_global", None) is None:
            return False
        delta = e.globalPosition().toPoint() - self._press_global
        if not self._dragging and delta.manhattanLength() > DRAG_THRESHOLD:
            self._dragging = True
            self._win_origin = self.window().pos()
        if self._dragging:
            self.window().move(self._win_origin + delta)
        return self._dragging

    def _drag_release(self) -> bool:
        """返回 True 表示这次是点击（没拖动）。"""
        was_click = getattr(self, "_press_global", None) is not None and not self._dragging
        self._press_global = None
        self._dragging = False
        return was_click


class ClickFrame(QFrame, DragMixin):
    clicked = Signal()

    def __init__(self, name: str):
        super().__init__()
        self.setObjectName(name)
        self.setCursor(Qt.PointingHandCursor)
        self._press_global = None
        self._dragging = False

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_press(e)

    def mouseMoveEvent(self, e):
        self._drag_move(e)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self._drag_release():
            self.clicked.emit()


def passthrough_label(text: str = "", rich: bool = True) -> QLabel:
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setTextFormat(Qt.RichText if rich else Qt.PlainText)
    lab.setAttribute(Qt.WA_TransparentForMouseEvents)  # 让鼠标事件落到外层，方便拖动/点击
    return lab


def plots_html(sit: Situation, plots: list[Plot], limit: int = 4) -> str:
    chips = []
    for p in plots[:limit]:
        c = KIND_COLOR.get(p.kind, "#ccc")
        where = describe_sit(sit, p.x, p.y)
        name = p.label or p.kind
        text = name if where == name else f"{name}·{where}"
        chips.append(f"<span style='color:{c}'>■</span> {html.escape(text)}")
    more = f"  +{len(plots) - limit}" if len(plots) > limit else ""
    return "&nbsp;&nbsp;".join(chips) + more



CHIP_COLORS = {
    "科技": "#4dabf7", "文化": "#cc5de8", "宗教": "#ffd43b", "征服": "#ff6b6b", "外交": "#63e6be",
    "奇观": "#f0d796", "扩张": "#69db7c", "金币": "#fcc419", "人口": "#8ce99a", "海洋": "#3bc9db",
}
ABILITY_CHIP = {"CIV": ("文明", "#f0d796"), "LEADER": ("领袖", "#e599f7"), "UNIT": ("单位", "#ff8787"),
                "BUILDING": ("建筑", "#74c0fc"), "DISTRICT": ("区域", "#74c0fc"), "IMPROVEMENT": ("改良", "#8ce99a")}


def chip(text: str, color: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("chip")
    c = QColor(color)
    lab.setStyleSheet(
        f"color: {color}; background: rgba({c.red()},{c.green()},{c.blue()},0.16);"
        f" border: 1px solid rgba({c.red()},{c.green()},{c.blue()},0.45);"
    )
    lab.setAttribute(Qt.WA_TransparentForMouseEvents)
    lab.setFixedHeight(18)
    lab.setAlignment(Qt.AlignCenter)
    return lab


def short(desc: str, n: int = 26) -> str:
    """取第一句，最多 n 个字。"""
    first = desc.split("。")[0].split("；")[0].strip()
    return first if len(first) <= n else first[: n - 1] + "…"


class TrackCard(QFrame):
    """科技 / 市政 板块。"""

    def __init__(self, icon: str):
        super().__init__()
        self.setObjectName("track")
        self.icon = icon
        lay = QVBoxLayout(self)
        lay.setContentsMargins(9, 6, 9, 7)
        lay.setSpacing(3)
        head = QHBoxLayout()
        self.head = passthrough_label("", rich=False)
        self.head.setObjectName("trackhead")
        self.head.setWordWrap(False)
        head.addWidget(self.head)
        head.addStretch()
        self.state = QLabel()
        self.state.setObjectName("chip")
        self.state.setFixedHeight(18)
        self.state.setAlignment(Qt.AlignCenter)
        self.state.setAttribute(Qt.WA_TransparentForMouseEvents)
        head.addWidget(self.state, 0, Qt.AlignVCenter)
        lay.addLayout(head)
        self.name = passthrough_label("", rich=False)
        lay.addWidget(self.name)
        self.bar = QProgressBar()
        self.bar.setTextVisible(False)
        self.bar.setRange(0, 100)
        lay.addWidget(self.bar)
        self.detail = passthrough_label()
        self.detail.setObjectName("muted")
        lay.addWidget(self.detail)

    def _state(self, text: str, color: str):
        c = QColor(color)
        self.state.setText(text)
        self.state.setStyleSheet(f"color:{color}; background: rgba({c.red()},{c.green()},{c.blue()},0.16);"
                                 f" border:1px solid rgba({c.red()},{c.green()},{c.blue()},0.5);")

    def show_track(self, t: TrackState | None):
        if t is None:
            self.hide()
            return
        self.show()
        self.head.setText(f"{self.icon} {t.kind}")
        if t.current:
            self.setProperty("warn", False)
            self._state("进行中", "#4dabf7")
            self.name.setObjectName("trackname")
            turns = t.current_turns or t.current.turns
            self.name.setText(t.current.name + (f"  ·  {turns} 回合" if turns and turns > 0 else ""))
            self.bar.setValue(max(0, min(100, t.current.progress)))
            self.bar.show()
            nxt = t.picks[0] if t.picks else None
            self.detail.setText(f"之后建议：<span style='color:#d6c08a'>{html.escape(nxt.name)}</span>"
                                + (f" · {html.escape(nxt.reasons[0])}" if nxt and nxt.reasons else "")
                                if nxt else "")
            self.setToolTip("")
        else:
            self.setProperty("warn", True)
            self._state("未选择", "#ff8a65")
            self.bar.hide()
            top = t.picks[0] if t.picks else None
            self.name.setObjectName("trackrec")
            if top is None:
                self.name.setText("打开科技树选一个" if t.kind == "科技" else "打开市政树选一个")
                self.detail.setText("")
            else:
                self.name.setText(f"推荐 {top.name}" + (f"  ·  {top.turns} 回合" if top.turns > 0 else ""))
                why = "<br>".join("· " + html.escape(r) for r in top.reasons[:3])
                alts = "、".join(html.escape(p.name) for p in t.picks[1:3])
                self.detail.setText(why + (f"<br><span style='color:#6c7380'>备选：{alts}</span>" if alts else ""))
                tip = "\n".join(top.reasons)
                if top.boost_desc and not top.boosted:
                    tip += f"\n尤里卡/鼓舞条件：{top.boost_desc}"
                self.setToolTip(tip)
        for w in (self, self.name):
            w.style().unpolish(w)
            w.style().polish(w)


class ProductionCard(QFrame):
    """城市生产板块：首都★在前，空闲城市标红并给推荐。点城市跳镜头。"""

    city_clicked = Signal(object)  # list[Plot]
    MAX_ROWS = 5

    def __init__(self):
        super().__init__()
        self.setObjectName("track")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(9, 6, 9, 7)
        self.lay.setSpacing(2)
        head = QHBoxLayout()
        h = passthrough_label("🏗 城市生产", rich=False)
        h.setObjectName("trackhead")
        h.setWordWrap(False)
        head.addWidget(h)
        head.addStretch()
        self.state = QLabel()
        self.state.setObjectName("chip")
        self.state.setFixedHeight(18)
        self.state.setAlignment(Qt.AlignCenter)
        head.addWidget(self.state, 0, Qt.AlignVCenter)
        self.lay.addLayout(head)
        self.summary = passthrough_label()
        self.summary.setObjectName("muted")
        self.lay.addWidget(self.summary)
        self.rows = QVBoxLayout()
        self.rows.setSpacing(1)
        self.lay.addLayout(self.rows)
        self.expanded = False
        self._sit = None

    def show_sit(self, sit: Situation):
        self._sit = sit
        if not sit.cities:
            self.hide()
            return
        self.show()
        rows = city_overview(sit)
        st = empire_status(sit)
        idle = sum(1 for r in rows if r.idle)
        color = "#ff8a65" if idle else "#4dabf7"
        c = QColor(color)
        self.state.setText(f"{idle} 座空闲" if idle else "全部在生产")
        self.state.setStyleSheet(f"color:{color}; background: rgba({c.red()},{c.green()},{c.blue()},0.16);"
                                 f" border:1px solid rgba({c.red()},{c.green()},{c.blue()},0.5);")
        self.setProperty("warn", bool(idle))
        self.style().unpolish(self)
        self.style().polish(self)

        def cnt(have, queued, name):
            col = "#ff8a65" if have + queued == 0 else "#c9ced6"
            return f"<span style='color:{col}'>{name} 已有 {have} · 在造 {queued}</span>"

        self.summary.setText(cnt(st["settlers"], st["settlers_queued"], "开拓者") + "　｜　"
                             + cnt(st["builders"], st["builders_queued"], "建造者"))

        while self.rows.count():
            w = self.rows.takeAt(0).widget()
            if w:
                w.deleteLater()
        shown = rows if self.expanded else rows[: self.MAX_ROWS]
        for r in shown:
            self.rows.addWidget(self._row(r))
        rest = len(rows) - len(shown)
        if rest > 0 or (self.expanded and len(rows) > self.MAX_ROWS):
            more = ClickFrame("row")
            ml = QVBoxLayout(more)
            ml.setContentsMargins(4, 0, 4, 0)
            ml.addWidget(passthrough_label(
                f"<span style='color:#d6aa50;font-size:11px'>{'另外 %d 座城 ▾' % rest if rest > 0 else '收起 ▴'}</span>"))
            more.clicked.connect(self._toggle)
            self.rows.addWidget(more)

    def _toggle(self):
        self.expanded = not self.expanded
        if self._sit:
            self.show_sit(self._sit)

    def _row(self, r) -> QFrame:
        row = ClickFrame("row")
        row.setToolTip("点击：镜头移到这座城")
        lay = QVBoxLayout(row)
        lay.setContentsMargins(4, 2, 4, 2)
        lay.setSpacing(0)
        star = "<span style='color:#f0d796'>★</span> " if r.is_capital else "　"
        name = f"<b>{html.escape(r.city.name)}</b>"
        if r.idle:
            text = f"{star}{name}　<span style='color:#ff8a65'>空闲</span>"
            if r.picks:
                top = r.picks[0]
                t = f"（{top.turns} 回合）" if top.turns > 0 else ""
                text += (f"<br><span style='font-size:12px'>　→ 推荐 <span style='color:#f0d796'>{html.escape(top.name)}</span>{t}"
                         f"<span style='color:#8f96a3'> · {html.escape(top.reasons[0])}</span></span>")
                alts = "、".join(html.escape(p.name) for p in r.picks[1:3])
                if alts:
                    text += f"<br><span style='color:#6c7380;font-size:11px'>　　备选：{alts}</span>"
                row.setToolTip("\n".join(f"{p.name}：{'；'.join(p.reasons)}" for p in r.picks[:4]))
        else:
            turns = f" · {r.turns_left} 回合" if r.turns_left else ""
            text = f"{star}{name}　<span style='color:#c9ced6'>{html.escape(r.building)}</span><span style='color:#8f96a3'>{turns}</span>"
        lay.addWidget(passthrough_label(text))
        c = r.city
        row.clicked.connect(lambda c=c: self.city_clicked.emit([Plot(c.x, c.y, "city", c.name)]))
        return row


# ------------------------------------------------------------------ 悬浮窗


class Overlay(QWidget, DragMixin):
    request_refresh = Signal()
    request_focus = Signal(object)
    request_auto_mark = Signal(bool)
    request_clear_marks = Signal()
    request_rebuild_kb = Signal()
    request_playstyle = Signal(object)  # 流派 id 或 None
    request_want_kb = Signal(bool)
    closed = Signal()

    def __init__(self, quit_on_close: bool = True):
        super().__init__()
        self.quit_on_close = quit_on_close
        self.settings = QSettings("civ6-advisor", "overlay")
        self.click_through = False
        self.bg_alpha = int(self.settings.value("alpha", 190))
        self.sit: Situation | None = None
        self.findings: list[Finding] = []
        self.expanded = False
        self.civ_expanded = False
        self._style_restore = True
        self.ai_on = self.settings.value("ai_on", False, type=bool)  # AI 军师开关
        self._auto = autoask.AutoState()
        self._ai_auto_reason = ""  # 第一次读到文明时恢复上次的流派开关
        self.active: Finding | None = None
        self.llm_worker: LLMWorker | None = None
        self._hotkeys_ok = False
        self._press_global = None
        self._dragging = False
        self._quitting = False
        self._tray_hint_shown = False

        self.setWindowTitle("文明6军师")
        self.setWindowIcon(make_icon())
        self.setWindowFlags(
            Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setStyleSheet(STYLE)
        self.setMinimumSize(320, 200)
        self._build_ui()
        self._build_tray()
        self._restore_geometry()

        self.thread = QThread(self)
        self.worker = GameWorker()
        self.worker.auto_mark = self.settings.value("map_pins", False, type=bool)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.start)
        self.worker.updated.connect(self.on_update)
        self.worker.status.connect(self._set_status)
        self.request_refresh.connect(self.worker.refresh)
        self.request_focus.connect(self.worker.focus)
        self.request_auto_mark.connect(self.worker.set_auto_mark)
        self.request_clear_marks.connect(self.worker.clear_marks)
        self.request_rebuild_kb.connect(self.worker.rebuild_kb)
        self.request_playstyle.connect(self.worker.set_playstyle)
        self.request_want_kb.connect(self.worker.set_want_kb)
        self.set_ai_on(self.ai_on)  # 恢复上次的 AI 军师开关
        prev = steplog.last_unfinished()
        steplog.note("军师启动")
        if prev:
            self._set_status(f"⚠ 上次运行停在「{prev}」：如果游戏当时崩溃了，托盘「导出诊断报告」发给开发者")
        self.thread.start()

    # ---------------- UI

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 8)
        root.setSpacing(6)

        bar = QHBoxLayout()
        self.title = passthrough_label("⚔ 文明6军师", rich=False)
        self.title.setObjectName("title")
        self.title.setWordWrap(False)
        bar.addWidget(self.title, 1)
        self.btn_ask = QPushButton("AI军师")
        self.btn_ask.setObjectName("ask")
        self.btn_ask.setCheckable(True)
        self.btn_ask.setToolTip("开启：AI 在关键回合自动给攻略，也可以在下方提问；关闭：只用本地分析（Ctrl+Shift+F3）")
        self.btn_ask.clicked.connect(lambda: self.set_ai_on(not self.ai_on))
        btn_refresh = QPushButton("⟳")
        btn_refresh.setToolTip("立即刷新")
        btn_refresh.clicked.connect(self.request_refresh.emit)
        btn_hide = QPushButton("—")
        btn_hide.setToolTip("隐藏到托盘（右下角图标可恢复或退出）")
        btn_hide.clicked.connect(self.hide_to_tray)
        for b in (self.btn_ask, btn_refresh, btn_hide):
            b.setCursor(Qt.PointingHandCursor)
            bar.addWidget(b)
        root.addLayout(bar)

        self.status = passthrough_label("启动中…", rich=False)
        self.status.setObjectName("status")
        root.addWidget(self.status)

        # 文明攻略卡片
        self.civ_box = ClickFrame("civ")
        self.civ_box.setToolTip("点击展开/收起文明能力")
        cl = QVBoxLayout(self.civ_box)
        cl.setContentsMargins(10, 7, 10, 7)
        cl.setSpacing(4)
        top = QHBoxLayout()
        top.setSpacing(5)
        self.civ_name = passthrough_label("", rich=False)
        self.civ_name.setObjectName("civname")
        self.civ_name.setWordWrap(False)
        self.civ_leader = passthrough_label("", rich=False)
        self.civ_leader.setObjectName("muted")
        self.civ_leader.setWordWrap(False)
        top.addWidget(self.civ_name)
        top.addWidget(self.civ_leader, 0, Qt.AlignBottom)
        top.addStretch()
        self.civ_chips = QHBoxLayout()
        self.civ_chips.setSpacing(3)
        top.addLayout(self.civ_chips)
        cl.addLayout(top)
        self.civ_tip = passthrough_label()
        cl.addWidget(self.civ_tip)
        self.civ_leader_tip = passthrough_label()
        self.civ_leader_tip.setObjectName("muted")
        cl.addWidget(self.civ_leader_tip)
        # 流派按钮：点一下按流派推荐，再点取消
        self.style_btn = QPushButton("")
        self.style_btn.setObjectName("style")
        self.style_btn.setCheckable(True)
        self.style_btn.setCursor(Qt.PointingHandCursor)
        self.style_btn.clicked.connect(self._toggle_playstyle)
        self.style_btn.hide()
        cl.addWidget(self.style_btn)
        self.style_progress = passthrough_label()
        self.style_progress.hide()
        cl.addWidget(self.style_progress)
        self.civ_abilities = QVBoxLayout()
        self.civ_abilities.setSpacing(2)
        cl.addLayout(self.civ_abilities)
        self.civ_toggle = passthrough_label("", rich=False)
        self.civ_toggle.setObjectName("muted")
        cl.addWidget(self.civ_toggle)
        self.civ_box.clicked.connect(self._toggle_civ)
        self.civ_box.hide()
        root.addWidget(self.civ_box)

        # 科技 / 市政 板块
        tr = QHBoxLayout()
        tr.setSpacing(6)
        self.tech_card = TrackCard("🔬")
        self.civic_card = TrackCard("📜")
        tr.addWidget(self.tech_card, 1)
        tr.addWidget(self.civic_card, 1)
        self.tech_card.hide()
        self.civic_card.hide()
        root.addLayout(tr)

        # 城市生产 板块
        self.prod_card = ProductionCard()
        self.prod_card.city_clicked.connect(lambda plots: self.request_focus.emit(plots))
        self.prod_card.hide()
        root.addWidget(self.prod_card)

        # 建议列表
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_host = QWidget()
        self.list_layout = QVBoxLayout(self.list_host)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(2)
        self.list_layout.addStretch()
        self.scroll.setWidget(self.list_host)
        root.addWidget(self.scroll, 3)

        self.ai = QTextBrowser()
        self.ai.setOpenLinks(False)
        self.ai.hide()
        root.addWidget(self.ai, 2)

        self.ask_box = QLineEdit()
        self.ask_box.setObjectName("ask")
        self.ask_box.setPlaceholderText("问军师：比如「奥罗莫骑兵怎么用」「下一座城放哪」，回车发送")
        self.ask_box.returnPressed.connect(self._submit_question)
        self.ask_box.installEventFilter(self)
        root.addWidget(self.ask_box)
        self.ask_box.hide()

        foot = QHBoxLayout()
        hint = passthrough_label("点建议：镜头跳过去，并在地图上插标记")
        hint.setObjectName("hint")
        foot.addWidget(hint, 1)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(60, 250)
        self.slider.setValue(self.bg_alpha)
        self.slider.setFixedWidth(56)
        self.slider.setToolTip("背景透明度")
        self.slider.valueChanged.connect(self._set_alpha)
        foot.addWidget(self.slider)
        foot.addWidget(QSizeGrip(self), 0, Qt.AlignBottom | Qt.AlignRight)
        root.addLayout(foot)

    def _build_tray(self):
        self.tray = QSystemTrayIcon(make_icon(), self)
        self.tray.setToolTip("文明6军师")
        menu = QMenu()
        self.act_show = QAction("隐藏悬浮窗", menu)
        self.act_show.triggered.connect(self.toggle_visible)
        self.act_through = QAction("鼠标穿透", menu, checkable=True)
        self.act_through.toggled.connect(self.set_click_through)
        self.act_mark = QAction("地图插旗（实验：可能导致游戏不稳定）", menu, checkable=True)
        self.act_mark.setChecked(self.settings.value("map_pins", False, type=bool))
        self.act_mark.toggled.connect(self._set_auto_mark)
        act_ask = QAction("AI 军师", menu, checkable=True)
        act_ask.triggered.connect(lambda on: self.set_ai_on(on))
        self.act_ai = act_ask
        act_diag = QAction("导出诊断报告（游戏崩溃/建议异常时用）", menu)
        act_diag.triggered.connect(self.export_report)
        act_copy = QAction("复制局势简报（粘贴给 Claude 等聊天 AI）", menu)
        act_copy.triggered.connect(self.copy_brief)
        act_refresh = QAction("立即刷新", menu)
        act_refresh.triggered.connect(self.request_refresh.emit)
        act_clear = QAction("清除地图标记", menu)
        act_clear.triggered.connect(self.request_clear_marks.emit)
        act_kb = QAction("重建资料库（换了模组/DLC 后用）", menu)
        act_kb.triggered.connect(self.request_rebuild_kb.emit)
        act_reset = QAction("窗口位置复位", menu)
        act_reset.triggered.connect(self._reset_position)
        act_quit = QAction("退出", menu)
        act_quit.triggered.connect(self.quit_app)
        for a in (self.act_show, self.act_through, self.act_mark, act_clear, act_ask, act_copy, act_refresh, act_kb, act_diag, act_reset):
            menu.addAction(a)
        menu.addSeparator()
        menu.addAction(act_quit)
        self.tray_menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        self.tray.show()

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = QPainterPath()
        path.addRoundedRect(self.rect().adjusted(0, 0, -1, -1), 10, 10)
        alpha = self.bg_alpha // 2 if self.click_through else self.bg_alpha
        p.fillPath(path, QColor(18, 20, 26, alpha))
        p.setPen(QColor(214, 170, 80, 90 if not self.click_through else 40))
        p.drawPath(path)

    def _set_alpha(self, v: int):
        self.bg_alpha = v
        self.settings.setValue("alpha", v)
        self.update()

    def _set_status(self, text: str):
        self.status.setText(text)

    # ---------------- 数据

    @Slot(object, object)
    def on_update(self, sit: Situation, findings: list[Finding]):
        new_turn = self.sit is None or sit.overview.turn != self.sit.overview.turn
        self.sit, self.findings = sit, findings
        o = sit.overview
        who = f"{sit.civ.civ_name} · {sit.civ.leader_name}" if sit.civ else f"{o.civ_name} · {o.leader_name}"
        self.title.setText(f"⚔ 第 {o.turn} 回合 · {who}")
        self.tray.setToolTip(f"文明6军师 · 第 {o.turn} 回合")
        self.active = None
        self._render_civ()
        tech, civic = tracks(sit)
        self.tech_card.show_track(tech)
        self.civic_card.show_track(civic)
        self.prod_card.show_sit(sit)
        self._render_list()
        if new_turn:
            self._maybe_auto_ask(sit, findings)

    def _maybe_auto_ask(self, sit, findings) -> bool:
        """新回合按自动分析设置决定要不要自动问 AI。返回是否发起了。"""
        reason = autoask.auto_reason("smart" if self.ai_on else "off", sit, findings, self._auto)
        if not reason or not llm.is_configured() or not self.isVisible():
            return False
        if self.llm_worker and self.llm_worker.isRunning():
            return False
        self.ask_ai(autoask.question_for(reason), auto_reason=reason)
        return True

    def _render_civ(self):
        sit = self.sit
        if not sit or not sit.civ:
            self.civ_box.hide()
            return
        c = sit.civ
        prof = profile_for(c.civ_type, c.leader_type)
        phase = game_phase(sit)
        self.civ_name.setText(prof.name if prof else c.civ_name)
        self.civ_leader.setText(c.leader_name)

        while self.civ_chips.count():
            w = self.civ_chips.takeAt(0).widget()
            if w:
                w.deleteLater()
        if prof:
            for f in prof.focus[:3]:
                self.civ_chips.addWidget(chip(f, CHIP_COLORS.get(f, "#adb5bd")))
            if prof.religion in ("必需", "不能"):
                self.civ_chips.addWidget(chip("必需宗教" if prof.religion == "必需" else "无法创教",
                                              "#ffd43b" if prof.religion == "必需" else "#868e96"))
            self.civ_tip.setText(f"<span style='color:#d6aa50'>【{phase}】</span>{html.escape(prof.phase_tip(phase))}")
            self.civ_leader_tip.setText(html.escape(prof.leader.tip) if prof.leader else "")
            self.civ_leader_tip.setVisible(bool(prof.leader))
        else:
            self.civ_tip.setText("<span style='color:#c9b27a'>攻略库未收录这个文明，可以开启「AI军师」</span>")
            self.civ_leader_tip.hide()

        self._render_playstyle()

        while self.civ_abilities.count():
            w = self.civ_abilities.takeAt(0).widget()
            if w:
                w.deleteLater()
        if self.civ_expanded:
            for a in c.abilities:
                label, color = ABILITY_CHIP.get(a.source, (a.source, "#adb5bd"))
                row = QLabel(f"<span style='color:{color}'>{label}</span>　<b>{html.escape(a.name)}</b><br>"
                             f"<span style='color:#9aa3b0'>{html.escape(a.desc)}</span>")
                row.setObjectName("ability")
                row.setTextFormat(Qt.RichText)
                row.setWordWrap(True)  # 展开后显示完整描述
                row.setContentsMargins(0, 2, 0, 2)
                row.setTextInteractionFlags(Qt.NoTextInteraction)  # 不吃鼠标按下，拖动/点击交给卡片
                row.setToolTip(f"{a.name}\n{a.desc}")
                self.civ_abilities.addWidget(row)
        n = len(c.abilities)
        self.civ_toggle.setText(("收起 ▴" if self.civ_expanded else f"展开文明能力（{n} 项）▾") if n else "")
        self.civ_toggle.setVisible(bool(n))
        self.civ_box.show()

    def _render_playstyle(self):
        sit = self.sit
        ps = playstyle_for(sit.civ.civ_type) if sit and sit.civ else None
        if not ps:
            self.style_btn.hide()
            self.style_progress.hide()
            return
        on = sit.playstyle == ps.id
        # 记住上次的选择：这个文明开过流派，新连上时自动恢复
        if not on and self._style_restore and self.settings.value(f"playstyle/{ps.civ}", False, type=bool):
            self._style_restore = False
            self.request_playstyle.emit(ps.id)
        self._style_restore = False
        self.style_btn.blockSignals(True)
        self.style_btn.setChecked(on)
        self.style_btn.blockSignals(False)
        self.style_btn.setText(("✔ 流派：" if on else "☆ 流派：") + ps.name + ("（再点取消）" if on else "（点击开启）"))
        self.style_btn.setToolTip(ps.describe())
        self.style_btn.show()
        if on:
            pr = progress(ps, sit)
            nxt = pr.next
            txt = f"<span style='color:#74c0fc'>{html.escape(ps.pitch)}</span><br>"
            txt += f"<span style='color:#d6aa50'>{len(pr.done)}/{len(pr.done) + len(pr.todo)}</span> "
            if pr.broken:
                txt += f"<span style='color:#ff8787'>⚠ {html.escape(pr.broken[0])}</span>"
            elif nxt:
                late = nxt in pr.late
                txt += ("<span style='color:#ff8787'>落后 · </span>" if late else "") + "下一步：" + html.escape(nxt.text)
            else:
                txt += "<span style='color:#8ce99a'>里程碑全部完成</span>"
            self.style_progress.setText(txt)
            self.style_progress.show()
        else:
            self.style_progress.hide()

    def _toggle_playstyle(self):
        sit = self.sit
        ps = playstyle_for(sit.civ.civ_type) if sit and sit.civ else None
        if not ps:
            return
        turn_on = sit.playstyle != ps.id
        self.settings.setValue(f"playstyle/{ps.civ}", turn_on)
        self._set_status(f"已开启流派「{ps.name}」，推荐按流派调整" if turn_on else "已取消流派，恢复常规推荐")
        self.request_playstyle.emit(ps.id if turn_on else None)

    def _toggle_civ(self):
        self.civ_expanded = not self.civ_expanded
        self._render_civ()

    def _clear_rows(self):
        while self.list_layout.count() > 1:
            w = self.list_layout.takeAt(0).widget()
            if w:
                w.deleteLater()

    def _render_list(self):
        self._clear_rows()
        # 文明重点、科技市政相关的已经在上面的卡片里显示
        items = [f for f in self.findings if f.category != "文明" and f.tag not in ("research", "civic", "eureka", "production")]
        if not items:
            self.list_layout.insertWidget(0, passthrough_label("<span style='color:#8ce99a'>✓ 没有发现需要处理的问题</span>"))
            return
        limit = 3 if self.ai.isVisible() else MAX_SHOWN - 1
        shown = items if self.expanded else items[:limit]
        for f in shown:
            self.list_layout.insertWidget(self.list_layout.count() - 1, self._make_row(f))
        rest = len(items) - len(shown)
        if rest > 0 or (self.expanded and len(items) > limit):
            more = ClickFrame("row")
            ml = QVBoxLayout(more)
            ml.setContentsMargins(8, 2, 8, 2)
            ml.addWidget(passthrough_label(
                f"<span style='color:#d6aa50'>{'展开其余 %d 条 ▾' % rest if rest > 0 else '收起 ▴'}</span>"))
            more.clicked.connect(self._toggle_expand)
            self.list_layout.insertWidget(self.list_layout.count() - 1, more)

    def _make_row(self, f: Finding) -> QFrame:
        row = ClickFrame("row")
        row.setProperty("active", f is self.active)
        lay = QVBoxLayout(row)
        lay.setContentsMargins(8, 4, 8, 4)
        lay.setSpacing(1)
        c = PRIORITY_COLORS[int(f.priority)]
        text = (f"<span style='color:{c}'>●</span> <b>{html.escape(f.title)}</b><br>"
                f"<span style='color:#aab1bc;font-size:12px'>{html.escape(f.action or f.detail)}</span>")
        if f.plots and self.sit:
            text += f"<br><span style='font-size:11px;color:#9aa3b0'>{plots_html(self.sit, f.plots)}</span>"
        lay.addWidget(passthrough_label(text))
        if f.plots:
            row.setToolTip("点击：镜头移到这里，并在地图上标出相关格子")
        row.clicked.connect(lambda f=f: self.on_row_clicked(f))
        return row

    def on_row_clicked(self, f: Finding):
        if not f.plots:
            return
        self.active = f
        self.request_focus.emit(list(f.plots))
        self._render_list()

    def _toggle_expand(self):
        self.expanded = not self.expanded
        self._render_list()

    # ---------------- 问 AI

    def export_report(self):
        """诊断报告：环境、设置、最近读取日志、本回合采集错误。写文件并复制到剪贴板。"""
        extra = {"AI 军师": "开" if self.ai_on else "关", "地图插旗": "开" if self.worker.auto_mark else "关"}
        if self.sit:
            o = self.sit.overview
            extra["对局"] = f"第 {o.turn} 回合 · {self.sit.civ.civ_name if self.sit.civ else o.civ_name}"
            if self.sit.errors:
                extra["本回合读取失败"] = "；".join(self.sit.errors)[:500]
        try:
            from civ6_advisor import gameconfig

            path = gameconfig.find_appoptions()
            extra["显示设置"] = (gameconfig.describe_mode(gameconfig.read_options(path.read_text(encoding="utf-8", errors="replace")))
                            if path else "没找到 AppOptions.txt")
        except Exception as e:  # noqa: BLE001
            extra["显示设置"] = f"读取失败：{e}"
        path = steplog.report(extra)
        QApplication.clipboard().setText(path.read_text(encoding="utf-8"))
        self._set_status(f"诊断报告已保存到 {path}，内容也已复制，可以直接粘贴发送")

    def copy_brief(self):
        """把发给 AI 的同一份内容（系统提示 + 局势简报 + 相关资料）复制到剪贴板，方便贴进任何聊天 AI。"""
        if not self.sit:
            self._set_status("还没有读到游戏数据")
            return
        text = "\n\n".join([
            "【请按下面的要求当我的文明6军师】\n" + llm.OVERLAY_SYSTEM,
            report.full_brief(self.sit, self.findings),
            get_kb().context_for(self.sit),
            "这回合我该做什么？",
        ])
        QApplication.clipboard().setText(text)
        self._set_status(f"已复制第 {self.sit.overview.turn} 回合局势简报（{len(text)} 字），粘贴到聊天里即可")

    def set_ai_on(self, on: bool):
        """AI 军师开关：开启后马上分析一次，之后在关键回合自动给攻略；关闭恢复纯本地分析。"""
        if on and not llm.is_configured():
            on = False
            self.ai.show()
            self.ai.setPlainText("还没配置大模型：在启动器里填写 API Key 后再开启 AI 军师。")
        else:
            self.ai.setVisible(on)
        self.ai_on = on
        self.request_want_kb.emit(on)
        self.settings.setValue("ai_on", on)
        self.btn_ask.setChecked(on)
        self.btn_ask.setText("AI军师 ✔" if on else "AI军师")
        self.act_ai.setChecked(on)
        self.ask_box.setVisible(on)
        if not on and self.ask_box.hasFocus():
            self._enable_typing(False)
        self._render_list()
        if on:
            self._auto = autoask.AutoState()  # 重新开启时当作刚连上，先整体分析一次
            if self.sit:
                self._maybe_auto_ask(self.sit, self.findings)
            else:
                self.ai.setPlainText("AI 军师已开启，读到游戏数据后开始分析。")
        self._set_status("AI 军师已开启" if on else "AI 军师已关闭，只用本地分析")

    def ask_ai(self, question: str = "", auto_reason: str = ""):
        if not self.ai_on:
            return
        if self.llm_worker and self.llm_worker.isRunning():
            return
        if not self.isVisible():
            self.toggle_visible()
        self.ai.show()
        if not self.sit:
            self.ai.setPlainText("还没有读到游戏数据，进入对局后再问。")
            return
        if not llm.is_configured():
            self.ai.setPlainText(
                "还没配置大模型。在启动器里填写 API Key，或设置环境变量后重启：\n"
                "CIV6_LLM_API_KEY=你的key\n"
                "CIV6_LLM_BASE_URL=https://api.deepseek.com/v1（默认）\n"
                "CIV6_LLM_MODEL=deepseek-flash（默认）"
            )
            return
        self._ai_q = "" if auto_reason else question
        self._ai_auto_reason = auto_reason
        self._ai_text = ""
        self._ai_status = "军师思考中…"
        self._show_ai()
        self._render_list()
        context = get_kb().context_for(self.sit)
        self.llm_worker = LLMWorker(report.full_brief(self.sit, self.findings), question, context)
        self.llm_worker.chunk.connect(self._on_chunk)
        self.llm_worker.status.connect(self._on_ai_status)
        self.llm_worker.failed.connect(lambda m: self.ai.setPlainText("❌ " + m))
        self.llm_worker.finished.connect(self._ai_done)
        self.llm_worker.start()

    # ---------------- 提问框：平时不抢游戏焦点，点输入框时才临时允许打字

    def eventFilter(self, obj, ev):
        from PySide6.QtCore import QEvent

        if obj is self.ask_box:
            if ev.type() == QEvent.MouseButtonPress:
                self._enable_typing(True)
            elif ev.type() == QEvent.KeyPress and ev.key() == Qt.Key_Escape:
                self._enable_typing(False)
                return True
            elif ev.type() == QEvent.FocusOut:
                self._enable_typing(False, give_back=False)
        return super().eventFilter(obj, ev)

    def _enable_typing(self, on: bool, give_back: bool = True):
        if on == getattr(self, "_typing", False):
            return
        self._typing = on
        if IS_WIN:
            hwnd = int(self.winId())
            ex = _get_ex(hwnd, GWL_EXSTYLE)
            if on:
                self._prev_fg = user32.GetForegroundWindow()
                _set_ex(hwnd, GWL_EXSTYLE, ex & ~WS_EX_NOACTIVATE)
                user32.SetForegroundWindow(hwnd)
            else:
                _set_ex(hwnd, GWL_EXSTYLE, ex | WS_EX_NOACTIVATE)
                if give_back and getattr(self, "_prev_fg", None):
                    user32.SetForegroundWindow(self._prev_fg)  # 焦点还给游戏
        if on:
            self.activateWindow()
            self.ask_box.setFocus()
        else:
            self.ask_box.clearFocus()

    def _submit_question(self):
        q = self.ask_box.text().strip()
        self._enable_typing(False)
        if q:
            self.ask_ai(q)

    def _show_ai(self):
        parts = []
        if self._ai_auto_reason:
            parts.append(f"<span style='color:#74c0fc'>🤖 自动分析 · {html.escape(self._ai_auto_reason)}</span>")
        if self._ai_q:
            parts.append(f"<span style='color:#d6aa50'>问：{html.escape(self._ai_q)}</span>")
        if self._ai_status:
            parts.append(f"<span style='color:#8f96a3'>🔎 {html.escape(self._ai_status)}</span>")
        if self._ai_text:
            parts.append(html.escape(self._ai_text).replace("\n", "<br>"))
        self.ai.setHtml("<br>".join(parts))
        sb = self.ai.verticalScrollBar()
        sb.setValue(sb.maximum())

    def _on_ai_status(self, text: str):
        self._ai_status = text
        self._show_ai()

    def _on_chunk(self, piece: str):
        self._ai_status = ""
        self._ai_text += piece
        self._show_ai()

    def _ai_done(self):
        self.ask_box.clear()
        self.ask_box.setPlaceholderText("继续问军师…（回车发送）")

    # ---------------- 托盘 / 显示

    def toggle_visible(self):
        self.setVisible(not self.isVisible())

    def setVisible(self, visible: bool):
        super().setVisible(visible)
        if hasattr(self, "act_show"):
            self.act_show.setText("隐藏悬浮窗" if visible else "显示悬浮窗")

    def hide_to_tray(self):
        self.hide()
        if not self._tray_hint_shown and QSystemTrayIcon.supportsMessages():
            self.tray.showMessage("文明6军师", "已隐藏到托盘，点图标可恢复，右键可退出。", make_icon(), 3000)
            self._tray_hint_shown = True

    def _tray_activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.toggle_visible()

    def _set_auto_mark(self, on: bool):
        self.settings.setValue("map_pins", on)
        self.request_auto_mark.emit(on)

    def _reset_position(self):
        scr = QApplication.primaryScreen().availableGeometry()
        self.resize(420, 760)
        self.move(scr.right() - 440, scr.top() + 60)
        self.show()

    def quit_app(self):
        self._quitting = True
        self.close()
        QApplication.quit()

    # ---------------- 穿透 / 热键（Windows）

    @Slot(bool)
    def set_click_through(self, on: bool):
        if on == self.click_through:
            return
        self.click_through = on
        if IS_WIN:
            hwnd = int(self.winId())
            ex = _get_ex(hwnd, GWL_EXSTYLE) | WS_EX_LAYERED | WS_EX_NOACTIVATE
            ex = ex | WS_EX_TRANSPARENT if on else ex & ~WS_EX_TRANSPARENT
            _set_ex(hwnd, GWL_EXSTYLE, ex)
        else:
            self.setWindowFlag(Qt.WindowTransparentForInput, on)
            self.show()
        self.act_through.blockSignals(True)
        self.act_through.setChecked(on)
        self.act_through.blockSignals(False)
        self.status.setText("🔒 鼠标穿透中（Ctrl+Shift+F1 或托盘菜单解除）" if on else "🖱 可操作")
        self.update()

    def showEvent(self, e):
        super().showEvent(e)
        if IS_WIN and not self._hotkeys_ok:
            hwnd = int(self.winId())
            mods = MOD_CONTROL | MOD_SHIFT | MOD_NOREPEAT
            ok = all(
                user32.RegisterHotKey(hwnd, hid, mods, vk)
                for hid, vk in ((HOTKEY_CLICK_THROUGH, VK_F1), (HOTKEY_TOGGLE, VK_F2), (HOTKEY_ASK, VK_F3))
            )
            self._hotkeys_ok = True
            if not ok:
                self.status.setText("部分快捷键注册失败（可能被其他软件占用），可用托盘菜单代替")
            _set_ex(hwnd, GWL_EXSTYLE, _get_ex(hwnd, GWL_EXSTYLE) | WS_EX_NOACTIVATE)

    def nativeEvent(self, event_type, message):
        if IS_WIN and event_type == b"windows_generic_MSG":
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_HOTKEY:
                hid = msg.wParam
                if hid == HOTKEY_CLICK_THROUGH:
                    self.set_click_through(not self.click_through)
                elif hid == HOTKEY_TOGGLE:
                    self.toggle_visible()  # 隐藏后窗口句柄仍在，热键照常可用
                elif hid == HOTKEY_ASK:
                    self.set_ai_on(not self.ai_on)
                return True, 0
        return super().nativeEvent(event_type, message)

    # ---------------- 拖动（窗口任意空白处）/ 位置记忆

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self._drag_press(e)

    def mouseMoveEvent(self, e):
        self._drag_move(e)

    def mouseReleaseEvent(self, _):
        self._drag_release()
        self.settings.setValue("geometry", self.saveGeometry())

    def _restore_geometry(self):
        geo = self.settings.value("geometry")
        if geo:
            self.restoreGeometry(geo)
        else:
            scr = QApplication.primaryScreen().availableGeometry()
            self.resize(420, 760)
            self.move(scr.right() - 440, scr.top() + 60)
        # 防止上次停在已拔掉的副屏上
        if not any(s.availableGeometry().intersects(self.frameGeometry()) for s in QApplication.screens()):
            self._reset_position()

    def closeEvent(self, e):
        # 只有托盘「退出」才真正关闭；其他关闭请求（如 Alt+F4）都隐藏到托盘
        if not self._quitting:
            e.ignore()
            self.hide_to_tray()
            return
        self.settings.setValue("geometry", self.saveGeometry())
        if IS_WIN:
            for hid in (HOTKEY_CLICK_THROUGH, HOTKEY_TOGGLE, HOTKEY_ASK):
                user32.UnregisterHotKey(int(self.winId()), hid)
        QMetaObject.invokeMethod(self.worker, "stop", Qt.BlockingQueuedConnection)
        self.thread.quit()
        self.thread.wait(2000)
        self.tray.hide()
        super().closeEvent(e)
        self.closed.emit()
        if self.quit_on_close:
            QApplication.quit()


def main() -> None:
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 隐藏到托盘时不退出
    app.setFont(QFont("Microsoft YaHei UI" if IS_WIN else "Noto Sans CJK SC", 10))
    w = Overlay()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
