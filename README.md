# Vintage Story Server Status Discord Bot

Интеграция вашего Vintage Story сервера с Discord для получения актуальной информации и уведомлений.

## Функциональность

- **Мониторинг игроков**: Количество и имена онлайн игроков
- **Игровое время**: Текущий сезон, день и время
- **Уведомления о штормах**: Автоматические оповещения о темпоральных бурях
- **Уведомления о смене сезонов**: Автоматические оповещения о смене сезонов
- **Discord-команды**: Команда `!status` для информации о сервере

## Требования

- **Python 3.8+**
- **Vintage Story Server**
- **Discord Bot Token**
- **Порты**: 8080 и 8081

## Установка

### 1. Установка мода для сервера

1. **Скачайте** последний релиз `StatusMod.zip` из раздела [Releases](https://github.com/psychok1nes1s/DiscordBotForVintageStory/releases).
2. **Распакуйте** файлы мода в папку модов Vintage Story:
   - Windows: `%appdata%/VintagestoryData/Mods`
   - Linux: `~/.config/VintagestoryData/Mods`
   - Mac: `~/Library/Application Support/VintagestoryData/Mods`
3. **Убедитесь**, что порт 8080 не занят другими приложениями.

### 2. Настройка Discord Bot

1. **Создайте Discord-бота**:
   - Перейдите на [Discord Developer Portal](https://discord.com/developers/applications).
   - Создайте новое приложение ("New Application").
   - Перейдите во вкладку "Bot" и нажмите "Add Bot".
   - Включите настройки "Privileged Gateway Intents": MESSAGE CONTENT INTENT.
   - Скопируйте токен бота ("Token").

2. **Настройте бота**:
   - Клонируйте репозиторий или распакуйте папку `DiscordBot` из архива релиза.
   - Переименуйте `config.example.py` в `config.py`.
   - Отредактируйте `config.py`, указав токен вашего бота и другие настройки:

```python
class Config:
    DISCORD_TOKEN = 'YOUR_DISCORD_BOT_TOKEN'  # Токен Discord-бота
    VS_SERVER_URL = 'http://localhost:8080/status/'  # URL API мода
    REQUEST_TIMEOUT = 30  # Таймаут запросов в секундах
    
    # ID канала Discord для отправки уведомлений о шторме
    NOTIFICATION_CHANNEL_ID = "YOUR_CHANNEL_ID"  # ID канала для уведомлений
    # Порт для HTTP сервера, принимающего уведомления
    NOTIFICATION_PORT = 8081 
    SERVER_NAME = "YOUR_SERVER_NAME"  # Название вашего сервера
```

3. **Установите зависимости**:

```bash
# Создание виртуального окружения
python -m venv venv

# Активация виртуального окружения
# Windows:
venv\Scripts\activate
# Linux/Mac:
source venv/bin/activate

# Установка зависимостей
pip install discord.py requests
```

4. **Добавьте бота на ваш сервер Discord**:
   - В [Discord Developer Portal](https://discord.com/developers/applications) перейдите к вашему приложению.
   - Во вкладке "OAuth2" → "URL Generator" выберите scope "bot" и разрешения: Send Messages, Embed Links.
   - Скопируйте сгенерированную ссылку и откройте ее в браузере.
   - Выберите сервер, на который нужно добавить бота.

## Использование

### Запуск

1. **Запустите Vintage Story сервер** с установленным модом Status Mod.
2. **Запустите Discord бота**:
```bash
cd путь/к/папке/DiscordBot
python bot.py
```

### Команды в Discord

- **!status** - Показывает текущий статус сервера

## API

- **Endpoint**: `http://localhost:8080/status/`
- **Метод**: GET
- **Формат ответа**: JSON

## Устранение неполадок

- **Бот не может подключиться к серверу**:
  - Убедитесь, что сервер Vintage Story запущен с модом Status Mod.
  - Проверьте, что порт 8080 не блокируется брандмауэром.
  - Убедитесь, что порт 8080 не используется другими приложениями.

- **Бот не отправляет сообщения в Discord**:
  - Проверьте правильность токена бота в `config.py`.
  - Убедитесь, что бот имеет права на отправку сообщений и встраиваемых ссылок.
  - Проверьте, что ID канала для уведомлений указан корректно.

- **Не приходят уведомления о штормах**:
  - Убедитесь, что порт 8081 не блокируется брандмауэром.
  - Проверьте, что ID канала для уведомлений в `config.py` указан правильно.

## Лицензия

MIT License