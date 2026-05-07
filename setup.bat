@echo off
chcp 65001 >nul
REM ============================================================
REM  FaceSwap Studio — установка зависимостей
REM  Использует py -3.11 — Python 3.11 должен быть установлен.
REM ============================================================

cd /d "%~dp0"

echo.
echo ============================================================
echo  FaceSwap Studio — установка
echo ============================================================
echo.

REM ----- Проверка наличия py-launcher -----
echo [1/5] Проверка наличия Python 3.11...
py -3.11 --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo ОШИБКА: Python 3.11 не найден в системе.
    echo.
    echo У тебя установлена другая версия Python — нам нужна именно 3.11.
    echo Библиотеки MediaPipe и InsightFace не работают на Python 3.13+.
    echo.
    echo Решение:
    echo   1. Скачай Python 3.11.9 с https://www.python.org/downloads/release/python-3119/
    echo      Раздел "Files" — Windows installer 64-bit
    echo   2. При установке поставь галочку "Add python.exe to PATH"
    echo   3. Запусти этот файл setup.bat снова
    echo.
    echo Python 3.11 встанет рядом с твоей текущей версией, не удаляя её.
    echo.
    pause
    exit /b 1
)

for /f "tokens=2" %%i in ('py -3.11 --version 2^>^&1') do set PYVER=%%i
echo Найден Python %PYVER% — отлично

REM ----- Создание venv на Python 3.11 -----
echo.
echo [2/5] Создание виртуального окружения на Python 3.11...
if exist venv (
    echo Окружение venv уже существует.
    echo Если хочешь пересоздать — удали папку venv и запусти setup.bat снова.
) else (
    py -3.11 -m venv venv
    if errorlevel 1 (
        echo.
        echo ОШИБКА: не удалось создать venv.
        pause
        exit /b 1
    )
)

REM ----- Активация -----
echo.
echo [3/5] Активация окружения...
call venv\Scripts\activate.bat

REM ----- Обновление pip -----
echo.
echo [4/5] Обновление pip...
python -m pip install --upgrade pip wheel setuptools

REM ----- Установка зависимостей -----
echo.
echo [5/5] Установка зависимостей (это займёт 5-10 минут, ~3 ГБ скачивания)...
echo.
pip install -r requirements.txt
if errorlevel 1 (
    echo.
    echo ОШИБКА: не удалось установить зависимости.
    echo.
    echo Возможные причины:
    echo  - Нет интернета или плохое соединение
    echo  - Кончилось место на диске (нужно ~5 ГБ свободно)
    echo  - Антивирус блокирует загрузку — добавь папку в исключения
    echo.
    pause
    exit /b 1
)

echo.
echo ============================================================
echo  Готово!
echo.
echo  Чтобы запустить приложение — двойной клик на run.bat
echo ============================================================
pause
