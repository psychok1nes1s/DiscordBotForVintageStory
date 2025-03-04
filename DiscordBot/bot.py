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
            channel = await bot.fetch_channel(int(notification_channel_id))
            print(f'Канал для уведомлений найден: #{channel.name} (ID: {channel.id})')
        except discord.errors.NotFound:
            print(f'ОШИБКА: Канал с ID {notification_channel_id} не найден')
        except discord.errors.Forbidden:
            print(f'ОШИБКА: Нет доступа к каналу с ID {notification_channel_id}')
        except Exception as e:
            print(f'ОШИБКА при получении канала для уведомлений: {e}')
    else:
        print('ВНИМАНИЕ: ID канала для уведомлений не указан в config.py (NOTIFICATION_CHANNEL_ID)')
    
    # Запуск HTTP сервера для приема уведомлений от игрового сервера
    start_notification_server()

# Класс для обработки HTTP запросов с уведомлениями
class NotificationHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Подавляем стандартное логирование для снижения шума
        pass
        
    def do_POST(self):
        if self.path == '/status/notification':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            try:
                notification = json.loads(post_data.decode('utf-8'))
                print(f"Получено уведомление типа: {notification.get('type')}")
                
                # Проверяем наличие ID канала уведомлений
                if not notification_channel_id:
                    error_msg = "Канал для уведомлений не настроен в config.py"
                    print(f"ОШИБКА: {error_msg}")
                    self.send_response(500)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "error", "message": error_msg}).encode('utf-8'))
                    return
                
                # Создаем задачу отправки уведомления в Discord
                future = asyncio.run_coroutine_threadsafe(send_discord_notification(notification), bot.loop)
                
                try:
                    # Ждем выполнения корутины с таймаутом
                    result = future.result(timeout=10)
                    
                    # Отправляем успешный ответ
                    self.send_response(200)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    response_data = {"status": "ok"}
                    self.wfile.write(json.dumps(response_data).encode('utf-8'))
                except asyncio.TimeoutError:
                    print("ОШИБКА: Таймаут при отправке уведомления в Discord")
                    self.send_response(500)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "error", "message": "Таймаут при отправке уведомления"}).encode('utf-8'))
                except Exception as e:
                    print(f"ОШИБКА при отправке уведомления: {e}")
                    self.send_response(500)
                    self.send_header('Content-type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
            except json.JSONDecodeError:
                print("ОШИБКА: Получены некорректные данные JSON")
                self.send_response(400)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": "Неверный формат JSON"}).encode('utf-8'))
            except Exception as e:
                print(f"ОШИБКА при обработке уведомления: {e}")
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))
        else:
            self.send_response(404)
            self.end_headers()

# Функция для отправки уведомлений в Discord
async def send_discord_notification(notification):
    # Проверяем наличие ID канала
    if not notification_channel_id:
        print("ОШИБКА: Канал для уведомлений не настроен")
        return {"success": False, "error": "Канал для уведомлений не настроен"}
    
    try:
        # Проверяем, что бот подключен к Discord
        if not bot.is_ready():
            print(f"ОШИБКА: Бот не готов/не подключен к Discord")
            return {"success": False, "error": "Бот не готов"}
            
        # Получаем объект канала по ID
        try:
            channel_id = int(notification_channel_id)
            channel = await bot.fetch_channel(channel_id)
        except ValueError:
            print(f"ОШИБКА: Некорректный формат ID канала: {notification_channel_id}")
            return {"success": False, "error": "Некорректный ID канала"}
        except discord.errors.NotFound:
            print(f"ОШИБКА: Канал с ID {notification_channel_id} не найден")
            return {"success": False, "error": "Канал не найден"}
        except discord.errors.Forbidden:
            print(f"ОШИБКА: Нет доступа к каналу с ID {notification_channel_id}")
            return {"success": False, "error": "Нет доступа к каналу"}
        except Exception as e:
            print(f"ОШИБКА при получении канала: {e}")
            return {"success": False, "error": f"Ошибка получения канала: {str(e)}"}
        
        # Обработка разных типов уведомлений
        if notification.get('type') == 'notification' or notification.get('type') == 'storm_notification':
            # Определяем цвет в зависимости от статуса шторма
            if notification.get('type') == 'storm_notification':
                is_active = notification.get('is_active', False)
                is_warning = notification.get('is_warning', False)
                color = 0xFF0000 if is_active else 0xFFAA00 if is_warning else 0x00FF00
            else:
                storm_active = notification.get('stormActive', False)
                storm_warning = notification.get('stormWarning', False)
                color = 0xFF0000 if storm_active else 0xFFAA00 if storm_warning else 0x00FF00
            
            # Создаем embed для сообщения
            embed = discord.Embed(
                title="Уведомление с сервера", 
                description=notification.get('message', 'Нет сообщения'),
                color=color
            )
            
            if 'time' in notification:
                embed.add_field(name="Игровое время", value=notification['time'], inline=True)
                
            # Попытка отправить сообщение
            try:
                message = await channel.send(embed=embed)
                print(f"Уведомление о шторме отправлено")
                return {"success": True}
            except discord.errors.Forbidden:
                print(f"ОШИБКА: Нет прав для отправки сообщения в канал")
                return {"success": False, "error": "Нет прав для отправки сообщения"}
            except Exception as e:
                print(f"ОШИБКА при отправке сообщения: {e}")
                return {"success": False, "error": f"Ошибка отправки: {str(e)}"}
            
        elif notification.get('type') == 'season_notification':
            # Определяем цвет в зависимости от сезона
            season_colors = {
                'spring': 0x77DD77,  # Светло-зеленый
                'summer': 0xFFFF66,  # Желтый
                'autumn': 0xFF6600,  # Оранжевый
                'fall': 0xFF6600,    # Альтернативное название осени
                'winter': 0xADD8E6   # Голубой
            }
            
            season = notification.get('season', '').lower()
            color = season_colors.get(season, 0x7289DA)  # Стандартный синий Discord, если сезон не определен
            
            embed = discord.Embed(
                title=f"Смена сезона", 
                description=notification.get('message', 'Наступил новый сезон!'),
                color=color
            )
            
            if 'time' in notification:
                embed.add_field(name="Игровое время", value=notification['time'], inline=True)
            
            # Попытка отправить сообщение
            try:
                message = await channel.send(embed=embed)
                print(f"Уведомление о смене сезона отправлено")
                return {"success": True}
            except discord.errors.Forbidden:
                print(f"ОШИБКА: Нет прав для отправки сообщения в канал")
                return {"success": False, "error": "Нет прав для отправки сообщения"}
            except Exception as e:
                print(f"ОШИБКА при отправке сообщения о сезоне: {e}")
                return {"success": False, "error": f"Ошибка отправки: {str(e)}"}
        else:
            print(f"ПРЕДУПРЕЖДЕНИЕ: Получен неизвестный тип уведомления: {notification.get('type')}")
            return {"success": False, "error": f"Неизвестный тип уведомления: {notification.get('type')}"}
    except Exception as e:
        print(f"КРИТИЧЕСКАЯ ОШИБКА: {e}")
        return {"success": False, "error": f"Критическая ошибка: {str(e)}"}

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
