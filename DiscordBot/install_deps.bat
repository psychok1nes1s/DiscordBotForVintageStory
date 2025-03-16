@echo off
title Dependency Installation for Discord Bot
chcp 65001 > nul
echo ======================================
echo = Dependency Installation            =
echo = Discord Bot for Vintage Story      =
echo ======================================
echo.

:: Переход в директорию с ботом
cd /d %~dp0

:: Проверка установки Python
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Python not found! Make sure Python is installed and added to PATH.
    echo Visit https://www.python.org/downloads/ to install Python.
    pause
    exit /b 1
)

:: Проверка наличия requirements.txt
if not exist requirements.txt (
    echo [ERROR] File requirements.txt not found in directory %cd%
    pause
    exit /b 1
)

echo [INFO] Installing dependencies...
echo.

:: Проверка наличия pip
python -m pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [INFO] Installing pip...
    python -m ensurepip --upgrade
)

:: Обновление pip
echo [INFO] Updating pip...
python -m pip install --upgrade pip

:: Установка зависимостей
echo [INFO] Installing dependencies from requirements.txt...
python -m pip install -r requirements.txt

:: Проверка успешности установки
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] There was a problem installing dependencies.
    pause
    exit /b 1
) else (
    echo.
    echo [INFO] Dependencies successfully installed!
    echo.
    echo You can now start the bot using:
    echo - start_discord_bot.bat (normal start)
    echo - start_discord_bot_admin.bat (start with administrator rights)
    echo.
    pause
) 