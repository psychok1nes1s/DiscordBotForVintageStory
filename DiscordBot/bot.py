import discord
from discord.ext import commands
import requests
from requests.exceptions import RequestException, Timeout
from config import Config
import json
import traceback
import socket
import asyncio
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading


intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

# Канал для уведомлений о шторме
notification_channel_id = None

def check_server_available(host="localhost", port=8080):
    """Проверяет, доступен ли сервер по указанному адресу и порту"""
    try:
        socket.create_connection((host, port), timeout=3)
        return True
    except (socket.timeout, socket.error) as e:
        print(f"Не удается подключиться к {host}:{port} - {e}")
        return False

async def fetch_server_status():
    try:
        # Проверяем доступность сервера
        if not check_server_available():
            print("Сервер недоступен на localhost:8080")
            return None

        # Используем настраиваемый таймаут из конфигурации
        timeout = getattr(Config, 'REQUEST_TIMEOUT', 30)
        
        # Используем session для лучшей производительности
        with requests.Session() as session:
            session.headers.update({'User-Agent': 'DiscordBot/1.0'})
            response = session.get(Config.VS_SERVER_URL, timeout=timeout)
            response.raise_for_status()
            
            data = response.json()
            return data
    except Timeout:
        print("Превышено время ожидания запроса")
        return None
    except RequestException as e:
        print(f"Ошибка запроса: {e}")
        return None
    except Exception as e:
        print(f"Неожиданная ошибка: {e}")
        traceback.print_exc()
        return None

@bot.command(name='status')
async def status(ctx):
    try:
        # Отправляем начальное сообщение
        message = await ctx.send("⏳ Получение информации с сервера...")
        
        # Получаем данные
        data = await fetch_server_status()
        
        # Удаляем начальное сообщение
        await message.delete()
        
        if data is None:
            await ctx.send("❌ Невозможно подключиться к серверу " + Config.SERVER_NAME)
            return

        # Отправляем новое сообщение с данными
        embed = discord.Embed(title="Статус сервера " + Config.SERVER_NAME , color=0x00ff00)
        
        # Players info
        embed.add_field(
            name=f"Игроков онлайн: {data['playerCount']}", 
            value="\n".join(data['players']) if data['players'] else "На сервере нет игроков",
            inline=False
        )
        
        # Time
        embed.add_field(name="Игровое время", value=data['time'], inline=True)

        # Temporal storm
        embed.add_field(
            name="Временной шторм", 
            value=data['temporalStorm'],
            inline=False
        )

        await ctx.send(embed=embed)
    except Exception as e:
        print(f"Ошибка при выполнении команды status: {e}")
        traceback.print_exc()
        await ctx.send(f"❌ Произошла ошибка: {str(e)}")

@bot.event
async def on_ready():
    print(f'Бот готов! Вход выполнен как {bot.user}')
    print(f'URL сервера: {Config.VS_SERVER_URL}')
    
    # Ищем канал для уведомлений
    global notification_channel_id
    notification_channel_id = getattr(Config, 'NOTIFICATION_CHANNEL_ID', None)
    if notification_channel_id:
        try:
            channel = await bot.fetch_channel(notification_channel_id)
            print(f'Канал для уведомлений: #{channel.name}')
        except Exception as e:
            print(f'Ошибка при получении канала для уведомлений: {e}')
    
    # Запуск HTTP сервера для приема уведомлений от игрового сервера
    start_notification_server()

# Класс для обработки HTTP запросов с уведомлениями
class NotificationHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/status/notification':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            try:
                notification = json.loads(post_data.decode('utf-8'))
                print(f"Получено уведомление: {notification}")
                
                # Отправляем уведомление в Discord
                asyncio.run_coroutine_threadsafe(send_discord_notification(notification), bot.loop)
                
                # Отправляем успешный ответ
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "ok"}).encode('utf-8'))
            except Exception as e:
                print(f"Ошибка при обработке уведомления: {e}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

# Функция для отправки уведомлений в Discord
async def send_discord_notification(notification):
    if not notification_channel_id:
        print("Канал для уведомлений не настроен")
        return
    
    try:
        channel = await bot.fetch_channel(notification_channel_id)
        
        if notification.get('type') == 'notification':
            color = 0xFF0000 if notification.get('stormActive', False) else 0xFFAA00 if notification.get('stormWarning', False) else 0x00FF00
            
            embed = discord.Embed(
                title="Уведомление с сервера", 
                description=notification.get('message', 'Нет сообщения'),
                color=color
            )
            
            if 'time' in notification:
                embed.add_field(name="Игровое время", value=notification['time'], inline=True)
            
            await channel.send(embed=embed)
    except Exception as e:
        print(f"Ошибка при отправке уведомления в Discord: {e}")

# Функция для запуска HTTP сервера в отдельном потоке
def start_notification_server():
    try:
        # Используем порт из конфигурации или 8081 по умолчанию
        port = getattr(Config, 'NOTIFICATION_PORT', 8081)
        server = HTTPServer(('localhost', port), NotificationHandler)
        
        print(f'Запускаю HTTP сервер для уведомлений на порту {port}')
        
        # Запускаем сервер в отдельном потоке
        server_thread = threading.Thread(target=server.serve_forever)
        server_thread.daemon = True
        server_thread.start()
    except Exception as e:
        print(f"Ошибка при запуске сервера уведомлений: {e}")

bot.run(Config.DISCORD_TOKEN)
