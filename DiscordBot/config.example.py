class Config:
    DISCORD_TOKEN = 'YOUR_DISCORD_BOT_TOKEN'  # Замените на ваш токен Discord
    VS_SERVER_URL = 'http://localhost:8080/status/'  # URL вашего сервера (с завершающим слешем)
    REQUEST_TIMEOUT = 30  # Таймаут запроса в секундах
    
    # ID канала Discord для отправки уведомлений о шторме
    NOTIFICATION_CHANNEL_ID = "YOUR_CHANNEL_ID"  # Замените на ID вашего канала Discord
    # Порт для HTTP сервера, который будет принимать уведомления от игрового сервера
    NOTIFICATION_PORT = 8081 
    SERVER_NAME = "YOUR_SERVER_NAME"  # Название вашего сервера 