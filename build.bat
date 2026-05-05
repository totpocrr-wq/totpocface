@echo off
REM ============================================================
REM  FaceSwap Studio — сборка .exe
REM ============================================================

call venv\Scripts\activate.bat

echo.
echo [1/2] Сборка через PyInstaller...
pyinstaller --noconfirm --clean build.spec
if errorlevel 1 (
    echo Сборка PyInstaller провалилась.
    pause
    exit /b 1
)

echo.
echo [2/2] Сборка установщика через Inno Setup...
echo Если Inno Setup не установлен — скачай: https://jrsoftware.org/isinfo.php
where ISCC >nul 2>nul
if errorlevel 1 (
    echo ISCC.exe не найден в PATH.
    echo Запусти Inno Setup Compiler вручную: открой installer.iss и нажми F9.
    pause
    exit /b 0
)

ISCC installer.iss

echo.
echo ============================================================
echo  Готово!
echo  - Папка приложения:  dist\FaceSwapStudio\
echo  - Установщик:        Output\FaceSwapStudio_Setup.exe
echo ============================================================
pause
