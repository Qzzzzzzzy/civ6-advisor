@echo off
REM 打包成单个 exe：dist\Civ6Advisor.exe
cd /d "%~dp0"
uv sync --extra overlay
uv run --extra overlay --with pyinstaller pyinstaller --noconfirm --clean --windowed --onefile --name Civ6Advisor --paths src --collect-data civ6_advisor scripts\launcher_entry.py
echo.
echo 完成：dist\Civ6Advisor.exe
pause
