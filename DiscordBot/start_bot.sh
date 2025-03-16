#!/bin/bash
# Скрипт запуска Discord бота для Vintage Story (Linux)

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}======================================${NC}"
echo -e "${YELLOW}= Discord бот для Vintage Story      =${NC}"
echo -e "${YELLOW}= Запуск...                          =${NC}"
echo -e "${YELLOW}======================================${NC}"
echo ""

# Перейти в директорию скрипта
cd "$(dirname "$0")"

# Проверить наличие Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}[ОШИБКА] Python3 не найден! Убедитесь, что Python установлен.${NC}"
    echo -e "${YELLOW}Для установки в Debian/Ubuntu:${NC} sudo apt install python3 python3-pip"
    echo -e "${YELLOW}Для установки в Fedora:${NC} sudo dnf install python3 python3-pip"
    echo -e "${YELLOW}Для установки в Arch Linux:${NC} sudo pacman -S python python-pip"
    read -p "Нажмите Enter для выхода..."
    exit 1
fi

# Проверить наличие файла бота
if [ ! -f "bot.py" ]; then
    echo -e "${RED}[ОШИБКА] Файл bot.py не найден в директории $(pwd)${NC}"
    read -p "Нажмите Enter для выхода..."
    exit 1
fi

# Проверить наличие requirements.txt и предложить установить зависимости
if [ -f "requirements.txt" ]; then
    if [ ! -d "venv" ]; then
        echo -e "${YELLOW}[ИНФО] Файл requirements.txt найден. Хотите установить зависимости? (y/n)${NC}"
        read -r install_deps
        if [[ $install_deps =~ ^[Yy]$ ]]; then
            echo -e "${GREEN}[ИНФО] Установка виртуального окружения и зависимостей...${NC}"
            python3 -m venv venv
            source venv/bin/activate
            pip install -r requirements.txt
            echo -e "${GREEN}[ИНФО] Зависимости установлены.${NC}"
        fi
    else
        echo -e "${GREEN}[ИНФО] Активация виртуального окружения...${NC}"
        source venv/bin/activate
    fi
fi

echo -e "${GREEN}[ИНФО] Запуск Discord бота...${NC}"
echo -e "${YELLOW}[ИНФО] Для остановки нажмите Ctrl+C${NC}"
echo ""

# Запуск бота
python3 bot.py

# Выполняется после завершения работы бота
echo ""
echo -e "${GREEN}[ИНФО] Бот завершил работу.${NC}"
read -p "Нажмите Enter для выхода..." 