@echo off
chcp 65001 >nul
REM 一键安装：准备环境、注册到 Claude 桌面版（MCP）
cd /d "%~dp0"
call scripts\setup_env.bat
if errorlevel 1 ( pause & exit /b 1 )
echo 注册到 Claude 桌面版...
.venv\Scripts\python.exe scripts\install_claude_mcp.py
pause
