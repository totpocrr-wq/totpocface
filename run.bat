@echo off
chcp 65001 >nul
REM ============================================================
REM  FaceSwap Studio — запуск приложения
REM ============================================================

cd /d "%~dp0"

if not exist "venv\Scripts\activate.bat" (
    echo.
    echo ОШИБКА: окружение venv не найдено.
    echo.
    echo Сначала запусти setup.bat — он установит все зависимости.
    echo.
    pause
    exit /b 1
)

echo Запуск FaceSwap Studio...
call venv\Scripts\activate.bat
python main.py

REM Если приложение упало с ошибкой — окно не закроется сразу
if errorlevel 1 (
    echo.
    echo Приложение завершилось с ошибкой.
    pause
)
