"""文明6军师启动器：检查环境 → 自动改好游戏设置 → 启动游戏 → 弹出悬浮窗。

运行：uv run civ6-launcher   （打包成 exe 见 build_exe.bat）
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from civ6_advisor import gameconfig as gc

IS_WIN = sys.platform == "win32"

LLM_PRESETS = {
    "DeepSeek": ("https://api.deepseek.com/v1", "deepseek-flash"),
    "阿里云百炼（通义）": ("https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen-plus"),
    "本地 Ollama": ("http://localhost:11434/v1", "qwen2.5:14b"),
    "自定义": ("", ""),
}

STYLE = """
QWidget { background: #15171d; color: #e9ecef; font-size: 13px; }
QLabel#h1 { font-size: 20px; font-weight: bold; color: #f0d796; }
QLabel#sub { color: #8f96a3; }
QLabel#section { font-size: 14px; font-weight: bold; color: #d6aa50; margin-top: 6px; }
QLabel[kind="ok"] { color: #8ce99a; } QLabel[kind="bad"] { color: #ff8787; } QLabel[kind="warn"] { color: #ffd43b; }
QFrame#card QLabel, QFrame#card QCheckBox { background: transparent; }
QFrame#card { background: #1d2028; border: 1px solid #2c303a; border-radius: 8px; }
QLineEdit, QComboBox {
  background: #0f1116; border: 1px solid #343944; border-radius: 4px; padding: 5px 8px; color: #e9ecef;
}
QPushButton {
  background: #2a2e38; border: 1px solid #3a3f4b; border-radius: 6px; padding: 7px 14px;
}
QPushButton:hover { background: #343945; }
QPushButton:disabled { color: #5c6370; }
QPushButton#primary {
  background: #b8892f; border-color: #d6aa50; color: #111; font-size: 15px; font-weight: bold; padding: 11px;
}
QPushButton#primary:hover { background: #d6aa50; }
QCheckBox { spacing: 6px; }
"""


def status_label(text: str, kind: str) -> QLabel:
    lab = QLabel(text)
    lab.setProperty("kind", kind)
    lab.setWordWrap(False)
    return lab


class Launcher(QWidget):
    def __init__(self):
        super().__init__()
        self.settings = QSettings("civ6-advisor", "launcher")
        self.overlay = None
        self.setWindowTitle("文明6军师")
        self.setStyleSheet(STYLE)
        self.setFixedWidth(520)
        self._build()
        self.refresh_checks()
        # 游戏进程状态每 5 秒刷新一次
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_checks)
        self.timer.start(5000)

    # ------------------------------------------------------------ 界面

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 20, 22, 18)
        root.setSpacing(10)

        h1 = QLabel("⚔ 文明6军师")
        h1.setObjectName("h1")
        sub = QLabel("实时读取对局，每回合告诉你该做什么")
        sub.setObjectName("sub")
        root.addWidget(h1)
        root.addWidget(sub)

        # 环境检查
        sec = QLabel("环境检查")
        sec.setObjectName("section")
        root.addWidget(sec)
        card = QFrame()
        card.setObjectName("card")
        self.grid = QGridLayout(card)
        self.grid.setContentsMargins(14, 10, 14, 10)
        self.grid.setHorizontalSpacing(14)
        self.grid.setVerticalSpacing(6)
        self.grid.setColumnStretch(1, 1)
        root.addWidget(card)

        self.auto_config = QCheckBox("启动时自动切换为「无边框全屏」并开启 Tuner（推荐，看起来和全屏一样）")
        self.auto_config.setChecked(self.settings.value("auto_config", True, type=bool))
        self.auto_config.toggled.connect(lambda v: self.settings.setValue("auto_config", v))
        root.addWidget(self.auto_config)

        # 大模型
        sec2 = QLabel("AI 军师（可选，不填也能用规则建议）")
        sec2.setObjectName("section")
        root.addWidget(sec2)
        card2 = QFrame()
        card2.setObjectName("card")
        g2 = QGridLayout(card2)
        g2.setContentsMargins(14, 10, 14, 10)
        g2.setVerticalSpacing(6)
        self.preset = QComboBox()
        self.preset.addItems(LLM_PRESETS)
        self.base = QLineEdit(self.settings.value("llm_base", LLM_PRESETS["DeepSeek"][0]))
        self.model = QLineEdit(self.settings.value("llm_model", LLM_PRESETS["DeepSeek"][1]))
        self.key = QLineEdit(self.settings.value("llm_key", ""))
        self.key.setEchoMode(QLineEdit.Password)
        self.key.setPlaceholderText("sk-...")
        self.preset.setCurrentText(self.settings.value("llm_preset", "DeepSeek"))
        self.preset.currentTextChanged.connect(self._apply_preset)
        # 旧版默认的 deepseek-chat 换成现在的 deepseek-flash
        if self.model.text().strip() == "deepseek-chat" and "deepseek.com" in self.base.text():
            self.model.setText("deepseek-flash")
        for row, (name, w) in enumerate(
            [("服务", self.preset), ("接口地址", self.base), ("模型", self.model), ("API Key", self.key)]
        ):
            g2.addWidget(QLabel(name), row, 0)
            g2.addWidget(w, row, 1)
        root.addWidget(card2)

        # 按钮
        self.btn_start = QPushButton("启动文明6 + 军师")
        self.btn_start.setObjectName("primary")
        self.btn_start.setCursor(Qt.PointingHandCursor)
        self.btn_start.clicked.connect(self.start_all)
        root.addWidget(self.btn_start)

        row = QHBoxLayout()
        self.btn_overlay = QPushButton("只开军师（游戏已在运行）")
        self.btn_overlay.clicked.connect(self.open_overlay)
        self.btn_restore = QPushButton("恢复原始游戏设置")
        self.btn_restore.clicked.connect(self.restore_settings)
        row.addWidget(self.btn_overlay)
        row.addWidget(self.btn_restore)
        root.addLayout(row)

        self.msg = QLabel("")
        self.msg.setObjectName("sub")
        self.msg.setWordWrap(True)
        root.addWidget(self.msg)

        note = QLabel("提示：开启 Tuner 的存档不能获得 Steam 成就。军师只读取数据，不会替你操作游戏。")
        note.setObjectName("sub")
        note.setWordWrap(True)
        root.addWidget(note)

    def _apply_preset(self, name: str):
        base, model = LLM_PRESETS[name]
        if base:
            self.base.setText(base)
            self.model.setText(model)

    def _set_row(self, row: int, name: str, text: str, kind: str):
        """状态行只创建一次，之后只更新文字和颜色，避免刷新时闪烁。"""
        if not hasattr(self, "_rows"):
            self._rows = {}
        if row not in self._rows:
            self.grid.addWidget(QLabel(name), row, 0, Qt.AlignTop)
            lab = status_label("", kind)
            self.grid.addWidget(lab, row, 1)
            self._rows[row] = lab
        lab = self._rows[row]
        mark = {"ok": "✓ ", "bad": "✗ ", "warn": "! "}[kind]
        lab.setText(mark + text)
        lab.setProperty("kind", kind)
        lab.style().unpolish(lab)
        lab.style().polish(lab)

    # ------------------------------------------------------------ 检查

    def refresh_checks(self):
        path = gc.find_appoptions()
        self.appoptions = path
        if path:
            opts = gc.read_options(path.read_text(encoding="utf-8-sig", errors="replace"))
            self._set_row(0, "游戏配置", "已找到 " + path.name, "ok")
            self._rows[0].setToolTip(str(path))
            mode = gc.describe_mode(opts)
            if mode == "独占全屏":
                self._set_row(1, "显示模式", "独占全屏（悬浮窗会被盖住，启动时会自动改为无边框）", "warn")
            else:
                self._set_row(1, "显示模式", mode, "ok")
            if opts.get("EnableTuner") == "1":
                self._set_row(2, "Tuner", "已开启", "ok")
            else:
                self._set_row(2, "Tuner", "未开启（启动时会自动开启）", "warn")
        else:
            self._set_row(0, "游戏配置", "没找到 AppOptions.txt（请先正常启动一次游戏）", "bad")
            self._set_row(1, "显示模式", "未知", "warn")
            self._set_row(2, "Tuner", "未知", "warn")

        if IS_WIN:
            sdk = gc.find_sdk()
            if sdk:
                self._set_row(3, "SDK", "已安装", "ok")
            else:
                self._set_row(3, "SDK", "未安装（Steam 库 → 工具 → Civilization VI SDK）", "bad")
        from civ6_advisor import gamedb

        data = gamedb.load()
        if data:
            import time as _t

            n = len(data.get("entries", []))
            when = _t.strftime("%m-%d %H:%M", _t.localtime(data.get("built_at", 0)))
            self._set_row(5, "资料库", f"已建立（{n} 条游戏资料，{when}）+ 攻略库", "ok")
        else:
            self._set_row(5, "资料库", "攻略库已就绪；游戏资料会在第一次进入对局时自动导出", "warn")
        running = gc.game_running()
        self._set_row(4, "游戏", "正在运行" if running else "未运行", "ok" if running else "warn")
        self.btn_restore.setEnabled(bool(path and gc.has_backup(path)))

    # ------------------------------------------------------------ 动作

    def _save_llm(self):
        self.settings.setValue("llm_preset", self.preset.currentText())
        self.settings.setValue("llm_base", self.base.text().strip())
        self.settings.setValue("llm_model", self.model.text().strip())
        self.settings.setValue("llm_key", self.key.text().strip())
        os.environ["CIV6_LLM_BASE_URL"] = self.base.text().strip()
        os.environ["CIV6_LLM_MODEL"] = self.model.text().strip()
        if self.key.text().strip():
            os.environ["CIV6_LLM_API_KEY"] = self.key.text().strip()
        else:
            os.environ.pop("CIV6_LLM_API_KEY", None)

    def start_all(self):
        self._save_llm()
        if gc.game_running():
            r = QMessageBox.question(
                self, "游戏已在运行",
                "文明6 已经在运行。设置修改要重启游戏才生效。\n\n直接打开军师悬浮窗吗？",
            )
            if r == QMessageBox.Yes:
                self.open_overlay()
            return

        notes = []
        if self.auto_config.isChecked() and self.appoptions:
            try:
                res = gc.apply(self.appoptions, borderless=True, tuner=True)
                notes += res.changes and ["已修改游戏设置：" + "，".join(res.changes)] or []
                notes += res.warnings
            except OSError as e:
                notes.append(f"修改游戏设置失败：{e}")
        elif self.auto_config.isChecked():
            notes.append("没找到游戏配置文件，这次无法自动设置。进游戏后在设置里开启 Tuner、选无边框窗口。")

        try:
            gc.launch_game()
            notes.append("正在通过 Steam 启动文明6…进入对局后军师会自动连上。")
        except OSError as e:
            notes.append(f"启动游戏失败：{e}（可以手动打开游戏）")
        self.msg.setText("\n".join(notes))
        self.open_overlay()

    def open_overlay(self):
        self._save_llm()
        if self.overlay is None:
            from civ6_advisor.overlay import Overlay

            self.overlay = Overlay(quit_on_close=False)
            self.overlay.closed.connect(self._overlay_closed)
        self.overlay.show()
        self.showMinimized()

    def _overlay_closed(self):
        self.overlay = None
        self.showNormal()
        self.activateWindow()

    def closeEvent(self, e):
        # 悬浮窗还在运行时，关掉启动器只是隐藏它；从托盘「退出」才结束程序
        if self.overlay is not None:
            e.ignore()
            self.hide()
            return
        super().closeEvent(e)
        QApplication.quit()

    def restore_settings(self):
        if self.appoptions and gc.restore(self.appoptions):
            self.msg.setText("已恢复原始游戏设置（下次启动游戏生效）。")
        self.refresh_checks()


def main() -> None:
    app = QApplication(sys.argv)
    app.setApplicationName("文明6军师")
    app.setQuitOnLastWindowClosed(False)
    app.setFont(QFont("Microsoft YaHei UI" if IS_WIN else "Noto Sans CJK SC", 10))
    w = Launcher()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
