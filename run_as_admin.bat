@echo off
:: 检查管理员权限
net session >nul 2>&1
if %errorLevel% == 0 (
    echo [OK] 以管理员身份运行
    echo.
    python main.py
) else (
    echo [ERROR] 需要管理员权限！
    echo.
    echo 请右键点击此文件，选择"以管理员身份运行"
    echo.
    pause
)
pause
