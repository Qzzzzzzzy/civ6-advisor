"""把 civ6-advisor 注册到 Claude 桌面版（写入 claude_desktop_config.json），只增改自己的条目，原有配置保留并备份。

用法：.venv\\Scripts\\python.exe scripts\\install_claude_mcp.py [--remove]
"""

from __future__ import annotations

import glob
import json
import os
import shutil
import sys
from pathlib import Path

NAME = "civ6-advisor"


def config_paths() -> list[Path]:
    """普通安装版在 %APPDATA%\\Claude；应用商店（MSIX）版在 Packages 目录下。"""
    out = []
    appdata = os.environ.get("APPDATA")
    if appdata:
        out.append(Path(appdata) / "Claude" / "claude_desktop_config.json")
    local = os.environ.get("LOCALAPPDATA")
    if local:
        for d in glob.glob(os.path.join(local, "Packages", "Claude_*", "LocalCache", "Roaming", "Claude")):
            out.append(Path(d) / "claude_desktop_config.json")
    if sys.platform == "darwin":
        out.append(Path.home() / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json")
    # 优先已经存在的目录（说明装了那个版本）
    existing = [p for p in out if p.parent.exists()]
    return existing or out[:1]


def entry(root: Path) -> dict:
    py = root / ".venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return {"command": str(py), "args": ["-m", "civ6_advisor.server"], "env": {"PYTHONIOENCODING": "utf-8"}}


def update(path: Path, root: Path, remove: bool = False) -> str:
    data = {}
    if path.exists():
        raw = path.read_text(encoding="utf-8-sig").strip()
        if raw:
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                return f"跳过 {path}：文件不是合法 JSON，请手动修好后再运行"
        shutil.copy2(path, path.with_suffix(".json.civ6advisor.bak"))
    servers = data.setdefault("mcpServers", {})
    if remove:
        servers.pop(NAME, None)
    else:
        servers[NAME] = entry(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return f"{'已移除' if remove else '已写入'}：{path}"


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    remove = "--remove" in sys.argv
    for p in config_paths():
        print(update(p, root, remove))
    if not remove:
        print("\n完成。请完全退出 Claude 桌面版（托盘图标右键退出）再重新打开。")
        print("进入文明6对局后，在 Claude 里问：这回合我该做什么？")
    return 0


if __name__ == "__main__":
    sys.exit(main())
