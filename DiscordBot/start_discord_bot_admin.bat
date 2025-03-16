@echo off
title Discord Bot for Vintage Story (Administrator)
chcp 65001 > nul

:: Проверка на права администратора и перезапуск с повышением прав при необходимости
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Starting with administrator rights...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

echo ======================================
echo = Discord Bot for Vintage Story      =
echo = Starting with admin rights         =
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

:: Проверка наличия основного файла бота
if not exist bot.py (
    echo [ERROR] File bot.py not found in directory %cd%
    pause
    exit /b 1
)

echo [INFO] Starting Discord bot with administrator rights...
echo [INFO] To stop, press Ctrl+C, then Y to confirm.
echo.

:: Запуск бота
python bot.py

:: Это выполнится только если бот завершит работу
echo.
echo [INFO] Bot has stopped.
echo [INFO] Press any key to exit...
pause > nul 