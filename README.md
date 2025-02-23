# Vintage Story Server Status Bot

Discord бот для отображения статуса Vintage Story сервера: количество игроков, игровое время и статус темпоральных бурь.

## Функционал

- 🎮 Количество и имена онлайн игроков
- 🕒 Текущее игровое время и сезон
- ⚡ Статус темпоральной бури
- 🤖 Команда `!status`

## Требования

- Python 3.8+
- Vintage Story сервер
- Discord Bot Token

## Установка

### 1. Мод
1. Скачайте последний релиз `Statusmod.zip`
2. Распакуйте `statusmod.zip` из архива в папку модов Vintage Story:
   - Windows: `%appdata%/VintagestoryData/Mods`
   - Linux: `~/.config/VintagestoryData/Mods`
   - Mac: `~/Library/Application Support/VintagestoryData/Mods`

### 2. Discord Бот
1. Создайте бота на [Discord Developer Portal](https://discord.com/developers/applications)
2. Распакуйте папку `bot` из архива
3. Переименуйте `config.example.py` в `config.py` и добавьте токен бота
4. Установите зависимости:
```bash
python -m venv venv
# Windows
venv\Scripts\activate
# Linux/Mac
source venv/bin/activate

pip install discord.py requests
```

## Использование

1. Запустите Vintage Story сервер
2. Запустите бота: `python bot.py`
3. В Discord используйте `!status`

Пример ответа:

```json
{
    "playerCount": 2,
    "players": ["Player1", "Player2"],
    "time": "Spring, Day 5, 14:30",
    "temporalStorm": "Inactive"
}
```

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

## Поддержка

При проблемах проверьте:
1. Мод установлен и сервер запущен
2. Токен бота правильный
3. Порт 8080 свободен
4. Создайте Issue если проблема осталась

## Лицензия

MIT License
