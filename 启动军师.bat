@echo off
chcp 65001 >nul
REM 第一次运行会自动准备环境（不需要事先装 Python）；之后直接打开启动器
cd /d "%~dp0"
if not exist .venv\.installed (
  echo 第一次运行，正在准备环境（需要联网，几分钟）...
  call scripts\setup_env.bat
  if errorlevel 1 ( pause & exit /b 1 )
)
start "" .venv\Scripts\pythonw.exe -m civ6_advisor.launcher
