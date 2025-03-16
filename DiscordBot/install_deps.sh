#!/bin/bash
# Скрипт установки зависимостей для Discord бота (Linux)

# Цвета для вывода
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${YELLOW}======================================${NC}"
echo -e "${YELLOW}= Установка зависимостей            =${NC}"
echo -e "${YELLOW}= Discord бот для Vintage Story     =${NC}"
echo -e "${YELLOW}======================================${NC}"
echo ""

# Перейти в директорию скрипта
cd "$(dirname "$0")"

# Проверить наличие Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}[ОШИБКА] Python3 не найден! Убедитесь, что Python установлен.${NC}"
    echo -e "${YELLOW}Для установки в Debian/Ubuntu:${NC} sudo apt install python3 python3-pip python3-venv"
    echo -e "${YELLOW}Для установки в Fedora:${NC} sudo dnf install python3 python3-pip python3-venv"
    echo -e "${YELLOW}Для установки в Arch Linux:${NC} sudo pacman -S python python-pip"
    read -p "Нажмите Enter для выхода..."
    exit 1
fi

# Проверить наличие requirements.txt
if [ ! -f "requirements.txt" ]; then
    echo -e "${RED}[ОШИБКА] Файл requirements.txt не найден в директории $(pwd)${NC}"
    read -p "Нажмите Enter для выхода..."
    exit 1
fi

echo -e "${GREEN}[ИНФО] Установка зависимостей...${NC}"
echo ""

# Спросить пользователя о предпочитаемом методе установки
echo -e "${YELLOW}Выберите метод установки зависимостей:${NC}"
echo "1) Установить глобально (требуются права администратора)"
echo "2) Установить в виртуальное окружение (рекомендуется)"
read -p "Ваш выбор (1/2): " install_method

case $install_method in
    1)
        echo -e "${GREEN}[ИНФО] Установка зависимостей глобально...${NC}"
        pip3 install -r requirements.txt
        install_status=$?
        ;;
    2)
        echo -e "${GREEN}[ИНФО] Создание виртуального окружения...${NC}"
        python3 -m venv venv
        
        echo -e "${GREEN}[ИНФО] Активация виртуального окружения...${NC}"
        source venv/bin/activate
        
        echo -e "${GREEN}[ИНФО] Обновление pip...${NC}"
        pip install --upgrade pip
        
        echo -e "${GREEN}[ИНФО] Установка зависимостей в виртуальное окружение...${NC}"
        pip install -r requirements.txt
        install_status=$?
        
        # Создаем скрипт-активатор для удобства
        echo -e "${GREEN}[ИНФО] Создание скрипта для активации виртуального окружения...${NC}"
        echo '#!/bin/bash
source "$(dirname "$0")/venv/bin/activate"
echo "Виртуальное окружение активировано. Используйте команду deactivate для выхода."' > activate_venv.sh
        chmod +x activate_venv.sh
        ;;
    *)
        echo -e "${RED}[ОШИБКА] Некорректный выбор.${NC}"
        read -p "Нажмите Enter для выхода..."
        exit 1
        ;;
esac

# Проверка успешности установки
if [ $install_status -ne 0 ]; then
    echo ""
    echo -e "${RED}[ОШИБКА] Возникла проблема при установке зависимостей.${NC}"
    read -p "Нажмите Enter для выхода..."
    exit 1
else
    echo ""
    echo -e "${GREEN}[ИНФО] Зависимости успешно установлены!${NC}"
    echo ""
    echo -e "Теперь вы можете запустить бота с помощью:"
    echo -e "- ${YELLOW}./start_bot.sh${NC} (обычный запуск)"
    echo -e "- ${YELLOW}./start_bot_sudo.sh${NC} (запуск с правами суперпользователя)"
    echo ""
    
    if [ "$install_method" -eq 2 ]; then
        echo -e "${YELLOW}Примечание:${NC} При обычном запуске виртуальное окружение будет активировано автоматически."
        echo -e "Для ручной активации окружения используйте команду: ${YELLOW}source venv/bin/activate${NC}"
        echo -e "или выполните скрипт: ${YELLOW}./activate_venv.sh${NC}"
    fi
    
    read -p "Нажмите Enter для выхода..."
fi 