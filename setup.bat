@echo off
REM ============================================================
REM  FaceSwap Studio — установка окружения для разработки
REM ============================================================

echo.
echo [1/4] Создание venv...
python -m venv venv
if errorlevel 1 (
    echo Не удалось создать venv. Проверь, что Python 3.10-3.11 установлен.
    pause
    exit /b 1
)

echo.
echo [2/4] Активация venv...
call venv\Scripts\activate.bat

echo.
echo [3/4] Обновление pip...
python -m pip install --upgrade pip

echo.
echo [4/4] Установка зависимостей (это займёт 3-5 минут)...
pip install -r requirements.txt

echo.
echo ============================================================
echo  Готово! Запусти приложение командой:
echo     venv\Scripts\activate.bat
echo     python main.py
echo ============================================================
pause
