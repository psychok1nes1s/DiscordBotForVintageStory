import os
from dotenv import load_dotenv
import logging

# Загружаем переменные окружения из .env файла
load_dotenv()

class Config:
    # Основные настройки бота
    DISCORD_TOKEN = os.getenv('DISCORD_TOKEN', '')
    VS_SERVER_URL = os.getenv('VS_SERVER_URL', 'http://localhost:8080/status/')
    REQUEST_TIMEOUT = int(os.getenv('REQUEST_TIMEOUT', '30'))
    
    # Значение максимального количества игроков по умолчанию
    DEFAULT_MAX_PLAYERS = int(os.getenv('DEFAULT_MAX_PLAYERS', '32'))
    
    # ID канала Discord для отправки уведомлений о шторме
    NOTIFICATION_CHANNEL_ID = int(os.getenv('NOTIFICATION_CHANNEL_ID', '0'))
    # Порт для HTTP сервера, который будет принимать уведомления от игрового сервера
    NOTIFICATION_PORT = int(os.getenv('NOTIFICATION_PORT', '8081'))
    SERVER_NAME = os.getenv('SERVER_NAME', 'Vintage Story Server')
    
    # ID роли администратора, которая будет иметь доступ к специальным командам
    ADMIN_ROLE_ID = os.getenv('ADMIN_ROLE_ID', '0')
    
    # ID канала для информационного табло статуса сервера
    STATUS_CHANNEL_ID = int(os.getenv('STATUS_CHANNEL_ID', '0'))
    
    # Настройки оповещений
    # Включить расширенные оповещения (True - использовать случайные сообщения из JSON, False - использовать базовые сообщения)
    USE_EXTENDED_NOTIFICATIONS = bool(os.getenv('USE_EXTENDED_NOTIFICATIONS', 'True').lower() in ('true', '1', 't'))
    
    # Настройки таймеров и кулдаунов (в минутах, если не указано иное)
    # Все таймеры указаны в минутах, если не указано иное
    class Timers:
        # Проверка статуса сервера (значение в минутах)
        SERVER_STATUS_CHECK = float(os.getenv('SERVER_STATUS_CHECK', '0.5'))  # 30 секунд по умолчанию
        
        # Обновление информационного табло
        STATUS_UPDATE = float(os.getenv('STATUS_UPDATE', '0.5'))
        
        # Проверка режима обслуживания
        MAINTENANCE_CHECK = int(os.getenv('MAINTENANCE_CHECK', '2'))
        
        # Таймаут для HTTP запросов
        HTTP_TIMEOUT = int(os.getenv('HTTP_TIMEOUT', '30'))
        
        # Минимальный интервал между уведомлениями одного типа (в секундах)
        # Используется для предотвращения спама уведомлениями
        NOTIFICATION_COOLDOWN = int(os.getenv('NOTIFICATION_COOLDOWN', '5'))
        
        # Время ожидания перед повторной попыткой подключения к серверу (в секундах)
        RECONNECT_DELAY = int(os.getenv('RECONNECT_DELAY', '60'))

# Проверяем наличие токена Discord
if not Config.DISCORD_TOKEN:
    logging.warning("DISCORD_TOKEN не указан в .env файле. Бот не сможет подключиться к Discord.")

# Проверяем наличие URL сервера
if not Config.VS_SERVER_URL:
    logging.warning("VS_SERVER_URL не указан в .env файле. Бот не сможет получить информацию о сервере.")

# Проверяем наличие ID канала для уведомлений
if Config.NOTIFICATION_CHANNEL_ID == 0:
    logging.warning("NOTIFICATION_CHANNEL_ID не указан в .env файле. Бот не сможет отправлять уведомления.")

# Проверяем наличие ID канала для статуса сервера
if Config.STATUS_CHANNEL_ID == 0:
    logging.warning("STATUS_CHANNEL_ID не указан в .env файле. Бот не сможет отправлять обновления статуса сервера.")
