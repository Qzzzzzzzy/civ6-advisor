"""文明6 本地配置：找 AppOptions.txt、切换无边框全屏、打开 Tuner、检测 SDK 和游戏进程。

AppOptions.txt 是 "键 值" 一行一项的文本文件。修改前会备份成 AppOptions.txt.civ6advisor.bak，
可以随时恢复。
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

IS_WIN = sys.platform == "win32"
STEAM_APP_ID = "289070"
BACKUP_SUFFIX = ".civ6advisor.bak"
SDK_DIR_NAME = "Sid Meier's Civilization VI SDK"

_LINE = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_]*)(\s+)(\S+)(.*)$")


# ------------------------------------------------------------------ 找文件


def candidate_appoptions_paths() -> list[Path]:
    home = Path.home()
    paths = []
    if IS_WIN:
        local = os.environ.get("LOCALAPPDATA")
        if local:
            paths.append(Path(local) / "Firaxis Games" / "Sid Meier's Civilization VI" / "AppOptions.txt")
        paths.append(home / "Documents" / "My Games" / "Sid Meier's Civilization VI" / "AppOptions.txt")
    elif sys.platform == "darwin":
        paths.append(
            home / "Library/Application Support/Sid Meier's Civilization VI/Firaxis Games/"
            "Sid Meier's Civilization VI/AppOptions.txt"
        )
    else:
        paths.append(home / ".local/share/aspyr-media/Sid Meier's Civilization VI/AppOptions.txt")
    return paths


def find_appoptions() -> Path | None:
    found = [p for p in candidate_appoptions_paths() if p.is_file()]
    if not found:
        return None
    # 两处都有时取最近修改的那份（游戏正在用的）
    return max(found, key=lambda p: p.stat().st_mtime)


# ------------------------------------------------------------------ 读 / 改


def read_options(text: str) -> dict[str, str]:
    out = {}
    for line in text.splitlines():
        if line.lstrip().startswith(";"):
            continue
        m = _LINE.match(line)
        if m:
            out[m.group(2)] = m.group(4)
    return out


@dataclass
class PatchResult:
    text: str
    changes: list[str] = field(default_factory=list)  # 人能看懂的改动说明
    borderless_key: str | None = None  # 找到的无边框设置项名
    warnings: list[str] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.changes)


def patch_options(text: str, borderless: bool = True, tuner: bool = True) -> PatchResult:
    """返回改好的文本。只改已有的行；EnableTuner 不存在时追加到末尾。"""
    want: dict[str, str] = {}
    if tuner:
        want["EnableTuner"] = "1"
    opts = read_options(text)
    res = PatchResult(text)
    if borderless:
        want["FullScreen"] = "0"
        bkeys = [k for k in opts if "borderless" in k.lower()]
        if bkeys:
            res.borderless_key = bkeys[0]
            for k in bkeys:
                want[k] = "1"
        else:
            res.warnings.append(
                "配置文件里没找到无边框选项，只关闭了独占全屏（游戏会以窗口模式启动）。"
                "进游戏后在 设置→图形 里把窗口模式选成「无边框窗口」即可，之后会自动记住。"
            )

    lines = text.splitlines(keepends=True)
    seen = set()
    for i, line in enumerate(lines):
        if line.lstrip().startswith(";"):
            continue
        m = _LINE.match(line.rstrip("\r\n"))
        if not m or m.group(2) not in want:
            continue
        key, old = m.group(2), m.group(4)
        seen.add(key)
        new = want[key]
        if old != new:
            eol = line[len(line.rstrip("\r\n")):]
            lines[i] = f"{m.group(1)}{key}{m.group(3)}{new}{m.group(5)}{eol}"
            res.changes.append(f"{key}: {old} → {new}")

    for key, val in want.items():
        if key not in seen and key in ("EnableTuner",):
            eol = "\r\n" if "\r\n" in text else "\n"
            if lines and not lines[-1].endswith(("\n", "\r")):
                lines[-1] += eol
            lines.append(f"{key} {val}{eol}")
            res.changes.append(f"{key}: (新增) {val}")
    res.text = "".join(lines)
    return res


def describe_mode(opts: dict[str, str]) -> str:
    if any("borderless" in k.lower() and v == "1" for k, v in opts.items()):
        return "无边框全屏"
    if opts.get("FullScreen") == "1":
        return "独占全屏"
    if opts.get("FullScreen") == "0":
        return "窗口模式"
    return "未知"


def apply(path: Path, borderless: bool = True, tuner: bool = True) -> PatchResult:
    """备份（只在第一次备份，保留最原始的设置）后写入。"""
    raw = path.read_bytes()
    text = raw.decode("utf-8-sig", errors="replace")
    res = patch_options(text, borderless, tuner)
    if res.changed:
        bak = path.with_name(path.name + BACKUP_SUFFIX)
        if not bak.exists():
            shutil.copy2(path, bak)
        path.write_text(res.text, encoding="utf-8", newline="")
    return res


def restore(path: Path) -> bool:
    bak = path.with_name(path.name + BACKUP_SUFFIX)
    if not bak.exists():
        return False
    shutil.copy2(bak, path)
    bak.unlink()
    return True


def has_backup(path: Path) -> bool:
    return path.with_name(path.name + BACKUP_SUFFIX).exists()


# ------------------------------------------------------------------ Steam / SDK / 进程


def steam_root() -> Path | None:
    if IS_WIN:
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as k:
                return Path(winreg.QueryValueEx(k, "SteamPath")[0])
        except OSError:
            pass
        for p in (Path(r"C:\Program Files (x86)\Steam"), Path(r"C:\Program Files\Steam")):
            if p.exists():
                return p
        return None
    p = Path.home() / ".steam/steam"
    return p if p.exists() else None


def steam_libraries(root: Path | None = None) -> list[Path]:
    root = root or steam_root()
    if not root:
        return []
    libs = [root]
    vdf = root / "steamapps" / "libraryfolders.vdf"
    if vdf.is_file():
        for m in re.finditer(r'"path"\s+"([^"]+)"', vdf.read_text(encoding="utf-8", errors="replace")):
            p = Path(m.group(1).replace("\\\\", "\\"))
            if p not in libs:
                libs.append(p)
    return libs


def find_sdk(libs: list[Path] | None = None) -> Path | None:
    for lib in libs if libs is not None else steam_libraries():
        p = lib / "steamapps" / "common" / SDK_DIR_NAME
        if p.is_dir():
            return p
    return None


def game_running() -> bool:
    if not IS_WIN:
        return False
    try:
        out = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        ).stdout.lower()
    except (OSError, subprocess.SubprocessError):
        return False
    return "civilizationvi" in out  # CivilizationVI.exe / CivilizationVI_DX12.exe


def launch_game() -> None:
    url = f"steam://rungameid/{STEAM_APP_ID}"
    if IS_WIN:
        os.startfile(url)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", url])
    else:
        subprocess.Popen(["xdg-open", url])
