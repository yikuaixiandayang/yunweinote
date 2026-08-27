@echo off
chcp 936 >nul
setlocal
title 运维知识库 Web 服务

cd /d "%~dp0"

set "VENV_PY=%~dp0_env\Scripts\python.exe"
set "REQ=%~dp0requirements.txt"
set "FRONT=%~dp0..\frontend"

echo ========================================
echo   运维知识库 - Web 服务启动
echo ========================================
echo.

echo [1/4] 检查 Python 虚拟环境...
if exist "%VENV_PY%" (
    echo   [OK] 已找到虚拟环境 _env
    goto :DEPS
)

echo   [!] 未找到 _env，尝试用系统 Python 创建...
where python >nul 2>nul
if errorlevel 1 (
    echo   [X] 系统未安装 Python，请先安装 Python 3.11 或更高版本
    echo       下载地址: https://www.python.org/downloads/
    goto :FAIL
)
python -m venv "%~dp0_env"
if errorlevel 1 (
    echo   [X] 虚拟环境创建失败
    goto :FAIL
)
echo   [OK] 虚拟环境创建成功

:DEPS
echo.
echo [2/4] 检查后端依赖 fastapi / uvicorn ...
"%VENV_PY%" -c "import fastapi,uvicorn" >nul 2>nul
if errorlevel 1 (
    echo   [!] 依赖缺失，正在安装...
    "%VENV_PY%" -m pip install -r "%REQ%"
    if errorlevel 1 (
        echo   [X] 依赖安装失败，请手动执行下面这行:
        echo       "%VENV_PY%" -m pip install -r "%REQ%"
        goto :FAIL
    )
    echo   [OK] 依赖安装完成
) else (
    echo   [OK] 依赖已就绪
)

echo.
echo [3/4] 检查前端产物...
if exist "%FRONT%\dist\index.html" (
    echo   [OK] frontend\dist 已存在
) else (
    echo   [!] 未找到 frontend\dist，网页将无法访问
    echo       构建命令: cd /d "%FRONT%"  然后  npm install  再  npm run build
)

echo.
echo [4/4] 检查 8000 端口占用...
netstat -ano | findstr ":8000" | findstr "LISTENING" >nul 2>nul
if errorlevel 1 (
    echo   [OK] 端口空闲
) else (
    echo   [!] 端口 8000 已被占用，服务可能已在运行
    echo       如需重启，请先运行 stop.bat
    echo.
    choice /c YN /n /m "  是否仍要继续启动? [Y=继续 / N=退出] "
    if errorlevel 2 goto :ABORT
)

echo.
echo ========================================
echo   环境就绪，正在启动服务...
echo   访问地址: http://localhost:8000
echo   停止服务: 按 Ctrl+C 或运行 stop.bat
echo ========================================
echo.

"%VENV_PY%" "%~dp0main.py"

echo.
echo [服务已退出]
pause
exit /b 0

:ABORT
echo.
echo [已取消启动]
pause
exit /b 0

:FAIL
echo.
echo ========================================
echo   启动失败，请按上方提示处理
echo ========================================
pause
exit /b 1
