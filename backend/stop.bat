@echo off
chcp 936 >nul
setlocal
title 停止 运维知识库 Web 服务

echo ========================================
echo   停止 运维知识库 Web 服务
echo ========================================
echo.

set "HIT=0"

:: ---------- [1/3] 按端口定位并停止 ----------
:: 说明：不用 wmic（输出带双 CR 会让 PID 拼上 \r 导致 taskkill 失败，且 Win11 已废弃）
echo [1/3] 按 8000 端口查找监听进程...
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":8000" ^| findstr "LISTENING"') do (
    echo   [-] 停止 PID: %%a
    taskkill /PID %%a /T /F >nul 2>&1
    if errorlevel 1 (
        echo       [!] 停止失败，可能已退出
    ) else (
        echo       [OK] 已停止
        set "HIT=1"
    )
)
if "%HIT%"=="0" echo   [-] 端口 8000 无监听进程

:: ---------- [2/3] 兜底清理未监听的残留 ----------
:: 场景：服务正在启动尚未 listen，或端口被换过，用命令行特征二次清理
echo.
echo [2/3] 兜底清理命令行含 main.py 的 python 进程...
:: 注意：整条 PowerShell 命令包在双引号里，内部的 | 不会被 cmd 当管道，不能写成 ^|
:: 内部一律用单引号，避免 cmd 与 PowerShell 的引号打架；提示语用 ASCII 免受代码页影响
powershell -NoProfile -ExecutionPolicy Bypass -Command "$t = Get-CimInstance Win32_Process | Where-Object { $_.Name -eq 'python.exe' -and $_.CommandLine -like '*main.py*' }; if ($t) { foreach ($p in $t) { Write-Host ('  [-] kill PID: ' + $p.ProcessId); Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue } } else { Write-Host '  [-] no residual process' }"

:: 等待 2 秒让端口释放（不用 timeout，stdin 被重定向时 timeout 会报错）
ping -n 3 127.0.0.1 >nul 2>&1

:: ---------- [3/3] 复检 ----------
echo.
echo [3/3] 复检端口与残留...
netstat -ano 2>nul | findstr ":8000" | findstr "LISTENING" >nul
if errorlevel 1 (
    echo   [OK] 8000 端口已释放
) else (
    echo   [X] 8000 端口仍被占用，请手动执行: netstat -ano ^| findstr :8000
)

tasklist /FI "IMAGENAME eq python.exe" 2>nul | findstr /i "python.exe" >nul
if errorlevel 1 (
    echo   [OK] 无 python.exe 残留
) else (
    echo   [i] 系统仍有其它 python.exe 进程（可能与本服务无关）
)

echo.
echo ========================================
echo   Web 服务已停止
echo   重新启动请运行 start.bat
echo ========================================
pause
exit /b 0
