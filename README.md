# Vintage Story Server Status Bot

Discord бот для отображения статуса Vintage Story сервера, включая информацию об игроках, времени и темпоральных бурях.

## Функционал

- 🎮 Отображение количества онлайн игроков
- 🕒 Текущее игровое время и сезон
- ⚡ Статус темпоральной бури
- 🤖 Простая команда `!status` для получения информации

## Как это работает

1. Мод для Vintage Story создает локальный HTTP сервер на порту 8080
2. При запросе `/status` мод возвращает JSON с информацией о:
   - Количестве и именах онлайн игроков
   - Текущем игровом времени и сезоне
   - Статусе временной бури
3. Discord бот по команде `!status` делает запрос к моду
4. Полученная информация форматируется и отправляется в Discord

Пример ответа от мода:

```json
{
    "playerCount": 2,
    "players": ["Player1", "Player2"],
    "time": "Spring, Day 5, 14:30",
    "temporalStorm": "Inactive"
}
```

## Требования

- Python 3.8+
- .NET SDK 7.0+
- Vintage Story сервер
- Discord Bot Token

## Установка

### 1. Мод для Vintage Story

1. Скомпилируйте мод:
```bash
cd StatusMod
dotnet restore
dotnet build
```

2. Скопируйте архив из StatusMod.zip/statusmod.zip в папку модов Vintage Story:
- Windows: `%appdata%/VintagestoryData/Mods`
- Linux: `~/.config/VintagestoryData/Mods`
- Mac: `~/Library/Application Support/VintagestoryData/Mods`

### 2. Discord Бот

1. Создайте Discord приложение и бота на [Discord Developer Portal](https://discord.com/developers/applications)
2. Настройте конфигурацию:
```bash
cd DiscordBot
cp config.example.py config.py
# Отредактируйте config.py, добавив токен вашего бота
```

3. Установите зависимости:
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate

pip install discord.py requests
```

## Использование

1. Запустите Vintage Story сервер с установленным модом
2. Запустите Discord бота:
```bash
cd DiscordBot
python bot.py
```

3. В Discord используйте команду `!status`

## Структура проекта

```
StatusDiscordBot/
├── DiscordBot/          # Discord бот
│   ├── bot.py          # Основной код бота
│   └── config.py       # Конфигурация
└── StatusMod/          # Мод для Vintage Story
    ├── statusmodModSystem.cs    # Основной код мода
    ├── statusmod.csproj         # Проект мода
    └── modinfo.json            # Информация о моде
```

## Разработка

Бот использует:
- discord.py для взаимодействия с Discord API
- requests для HTTP запросов к моду
- Встроенные embed-сообщения Discord для красивого вывода

Мод предоставляет HTTP API на `localhost:8080/status`

## Лицензия

MIT License

## Поддержка

Если у вас возникли проблемы:
1. Убедитесь, что мод правильно установлен и сервер запущен
2. Проверьте, что бот правильно настроен и токен верный
3. Проверьте порт 8080 (он должен быть свободен)
4. Создайте Issue в репозитории с описанием проблемы
