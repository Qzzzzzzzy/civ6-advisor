@echo off
REM 准备运行环境：不需要事先装 Python。没有 uv 就自动安装 uv，再由 uv 下载 Python 3.12 并安装依赖。
REM 用法：call scripts\setup_env.bat   （成功时 errorlevel=0）
cd /d "%~dp0.."
if exist .venv\.installed exit /b 0
set "UV="
where uv >nul 2>nul && set "UV=uv"
if not defined UV if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV=%USERPROFILE%\.local\bin\uv.exe"
if not defined UV if exist "%USERPROFILE%\.cargo\bin\uv.exe" set "UV=%USERPROFILE%\.cargo\bin\uv.exe"
if defined UV goto have_uv
echo [1/3] 安装 uv（Python 环境管理工具，只需一次）...
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
if exist "%USERPROFILE%\.local\bin\uv.exe" set "UV=%USERPROFILE%\.local\bin\uv.exe"
if not defined UV (
  echo 安装 uv 失败。可以手动安装 Python 3.12：https://www.python.org/downloads/ （安装时勾选 Add python.exe to PATH）后再运行。
  exit /b 1
)
:have_uv
set "UV_DEFAULT_INDEX=https://mirrors.aliyun.com/pypi/simple/"
echo [2/3] 准备 Python 3.12（没有会自动下载）...
"%UV%" venv --python 3.12 .venv
if errorlevel 1 ( echo 创建环境失败，检查网络后重试 & exit /b 1 )
echo [3/3] 安装依赖（第一次需要几分钟）...
"%UV%" pip install --python .venv\Scripts\python.exe -e ".[overlay]"
if errorlevel 1 ( echo 安装依赖失败，检查网络后重试 & exit /b 1 )
echo ok> .venv\.installed
exit /b 0
