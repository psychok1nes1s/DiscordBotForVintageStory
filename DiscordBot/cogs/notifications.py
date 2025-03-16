import os
import json
import logging
import threading
import http.server
import random
import discord
from discord.ext import commands
import asyncio
from datetime import datetime
from config import Config
import functools

logger = logging.getLogger('discord_bot')

# Декоратор для проверки наличия прав администратора
def admin_only():
    """Декоратор для ограничения доступа к командам только для администраторов"""
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, ctx, *args, **kwargs):
            # Получаем ID роли администратора из конфигурации
            admin_role_id = getattr(Config, 'ADMIN_ROLE_ID', None)
            
            # Если ID роли не настроен, возвращаем False
            if not admin_role_id or admin_role_id == "000000000000000000":
                await ctx.send("❌ ID роли администратора не настроен в конфигурации.")
                return
                
            # Преобразуем строковый ID в int
            try:
                admin_role_id = int(admin_role_id)
            except ValueError:
                await ctx.send("❌ Некорректный формат ID роли администратора в конфигурации.")
                return
                
            # Проверяем наличие роли у пользователя
            user_roles = [role.id for role in ctx.author.roles]
            if admin_role_id not in user_roles:
                await ctx.send("❌ У вас нет доступа к этой команде. Требуется роль администратора.")
                return

            return await func(self, ctx, *args, **kwargs)
        return wrapper
    return decorator

class NotificationHandler(http.server.BaseHTTPRequestHandler):
    """Обработчик HTTP запросов для получения уведомлений от игрового сервера"""
    
    def _set_response(self, status_code=200, content_type='application/json'):
        """Устанавливает заголовки ответа"""
        self.send_response(status_code)
        self.send_header('Content-type', content_type)
        self.end_headers()
    
    def do_POST(self):
        """Обрабатывает POST запросы от игрового сервера"""
        try:
            # Проверяем путь запроса
            if self.path != "/status/notification":
                logger.warning(f"Получен запрос по неправильному пути: {self.path}")
                self._set_response(404)
                self.wfile.write(json.dumps({"error": "Not found"}).encode('utf-8'))
                return
                
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            # Парсим JSON данные
            notification = json.loads(post_data.decode('utf-8'))
            
            # Проверяем, содержит ли уведомление необходимые поля
            if 'type' not in notification:
                logger.warning("Получено уведомление без поля 'type'")
                self._set_response(400)
                self.wfile.write(json.dumps({"error": "Missing 'type' field"}).encode('utf-8'))
                return
            
            # Получаем доступ к экземпляру Notifications cog
            notifications_cog = getattr(self.server, 'notifications_cog', None)
            if notifications_cog is None:
                logger.error("Ошибка: HTTP сервер не имеет атрибута notifications_cog")
                self._set_response(500)
                self.wfile.write(json.dumps({"error": "Server configuration error"}).encode('utf-8'))
                return
                
            # Запускаем асинхронную обработку уведомления
            asyncio.run_coroutine_threadsafe(
                notifications_cog.process_notification(notification),
                notifications_cog.bot.loop
            )
            
            self._set_response()
            self.wfile.write(json.dumps({"status": "success"}).encode('utf-8'))
            
        except json.JSONDecodeError as e:
            logger.error(f"Ошибка декодирования JSON: {e}")
            self._set_response(400)
            self.wfile.write(json.dumps({"error": "Invalid JSON"}).encode('utf-8'))
        except Exception as e:
            logger.error(f"Ошибка при обработке POST запроса: {e}")
            self._set_response(500)
            self.wfile.write(json.dumps({"error": str(e)}).encode('utf-8'))
    
    def do_GET(self):
        """Обрабатывает GET запросы (для проверки работоспособности)"""
        self._set_response(200, 'text/html')
        self.wfile.write("Notification server is running".encode('utf-8'))
    
    def log_message(self, format, *args):
        """Переопределяет стандартное логирование HTTP сервера"""
        logger.debug(f"HTTP: {format % args}")

def create_notifications_server(host='', port=8081, notifications_cog=None):
    """Создает HTTP сервер для приема уведомлений"""
    server = http.server.HTTPServer((host, port), NotificationHandler)
    server.notifications_cog = notifications_cog
    return server

class Notifications(commands.Cog):
    """Cog для обработки уведомлений от игрового сервера"""
    
    def __init__(self, bot):
        self.bot = bot
        self.http_server = None
        self.notification_channel = None
        
        # Пути к файлам сообщений
        self.BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.DATA_DIR = os.path.join(self.BASE_DIR, 'data')
        self.STORM_MESSAGES_FILE = os.path.join(self.DATA_DIR, 'storm_messages.json')
        self.SEASON_MESSAGES_FILE = os.path.join(self.DATA_DIR, 'season_messages.json')
        self.SERVER_STATUS_FILE = os.path.join(self.DATA_DIR, 'server_status.json')
        
        # Загрузка сообщений
        self.storm_messages = self.load_messages('storm')
        self.season_messages = self.load_messages('season')
        
        # Время последнего уведомления по типу
        self.last_notification_time = {}
        
        # Запускаем HTTP сервер для уведомлений
        self.start_http_server()
    
    def cog_unload(self):
        """Вызывается при выгрузке cog"""
        if self.http_server:
            self.http_server.shutdown()
            logger.warning("HTTP сервер для уведомлений остановлен")
    
    def load_messages(self, message_type):
        """Загружает сообщения указанного типа из файла"""
        try:
            file_path = ''
            if message_type == 'storm':
                file_path = self.STORM_MESSAGES_FILE
            elif message_type == 'season':
                file_path = self.SEASON_MESSAGES_FILE
            
            # Удаляем избыточное логирование
            # logger.info(f"Загрузка сообщений типа {message_type} из файла {file_path}")
            
            if file_path and os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    messages = json.load(f)
                    # logger.info(f"Загружены сообщения: {messages.keys()}")
                    return messages
            else:
                logger.warning(f"Файл {file_path} не найден")
            return {}
        except Exception as e:
            logger.error(f"Ошибка при загрузке сообщений типа {message_type}: {e}")
            logger.error("Трейс ошибки:", exc_info=True)
            return {}
    
    def start_http_server(self):
        """Запускает HTTP сервер для приема уведомлений от игрового сервера"""
        try:
            logger.warning(f"Запуск HTTP сервера для уведомлений на порту {Config.NOTIFICATION_PORT}")
            
            # Проверяем, что порт указан корректно
            if Config.NOTIFICATION_PORT <= 0:
                logger.error(f"Некорректный порт для HTTP сервера: {Config.NOTIFICATION_PORT}")
                return False
            
            # Создаем HTTP сервер с правильно настроенным доступом к экземпляру cog
            self.http_server = create_notifications_server(
                port=Config.NOTIFICATION_PORT, 
                notifications_cog=self
            )
            
            # Запускаем сервер в отдельном потоке
            server_thread = threading.Thread(target=self.http_server.serve_forever)
            server_thread.daemon = True
            server_thread.start()
            
            logger.warning(f"HTTP сервер успешно запущен и слушает порт {Config.NOTIFICATION_PORT}")
            return True
        except Exception as e:
            logger.error(f"Ошибка при запуске HTTP сервера для уведомлений: {e}")
            logger.error("Трейс ошибки:", exc_info=True)
            return False
    
    async def process_notification(self, notification):
        """Обрабатывает полученное уведомление"""
        try:
            # Получаем тип уведомления
            notification_type = notification.get('type', '')
            
            # Удаляем избыточное логирование данных
            # logger.info(f"Получено уведомление типа: {notification_type}, данные: {notification}")
            
            # Проверяем готовность бота
            if not self.bot.is_ready():
                logger.error("Бот не готов к обработке уведомлений")
                return False
            
            # Проверяем режим технического обслуживания
            manual_maintenance_active = False
            try:
                if os.path.exists(self.SERVER_STATUS_FILE):
                    with open(self.SERVER_STATUS_FILE, 'r', encoding='utf-8') as f:
                        server_status = json.load(f)
                        manual_maintenance_active = server_status.get('manual_maintenance', {}).get('active', False)
            except Exception as e:
                logger.error(f"Ошибка при проверке режима техобслуживания: {e}")
            
            # Если включен режим техобслуживания, не отправляем уведомления о штормах и сезонах
            if manual_maintenance_active:
                # logger.info("Режим техобслуживания активен. Уведомления о штормах и сезонах отключены.")
                # Исключение: сервисные уведомления обрабатываем всегда
                if notification_type == 'server_status':
                    # logger.info("Обработка сервисного уведомления даже в режиме техобслуживания")
                    pass
                else:
                    return False
            
            # Убеждаемся, что канал для уведомлений инициализирован
            if not self.notification_channel:
                if Config.NOTIFICATION_CHANNEL_ID:
                    self.notification_channel = self.bot.get_channel(Config.NOTIFICATION_CHANNEL_ID)
                    if not self.notification_channel:
                        try:
                            self.notification_channel = await self.bot.fetch_channel(Config.NOTIFICATION_CHANNEL_ID)
                        except Exception as e:
                            logger.error(f"Ошибка при получении канала: {e}")
                        return False
                else:
                    logger.error("ID канала для уведомлений не указан в конфигурации")
                    return False

            # Обработка пакета уведомлений
            if notification_type == 'notification_batch':
                notifications = notification.get('notifications', [])
                for sub_notification in notifications:
                    await self.process_notification(sub_notification)
                return True

            # Получаем данные уведомления
            notification_data = notification.get('data', notification)
            actual_type = notification_data.get('type', notification_type)

            # Проверяем частоту уведомлений
            current_time = datetime.now()
            last_time = self.last_notification_time.get(actual_type, datetime.min)
            time_diff = (current_time - last_time).total_seconds()
            
            if time_diff < Config.Timers.NOTIFICATION_COOLDOWN:
                return False
            
            # Обновляем время последнего уведомления
            self.last_notification_time[actual_type] = current_time
            
            # Формируем сообщение в зависимости от типа уведомления
            embed = None
            
            # Обработка уведомлений о шторме
            if actual_type == 'storm_notification' or (notification_type == 'шторме' and notification_data.get('type') == 'storm_notification'):
                # logger.info("Обработка уведомления о шторме")
                # Получаем состояние шторма (начался/закончился)
                storm_active = notification_data.get('is_active', False)
                is_warning = notification_data.get('is_warning', False)
                game_time = notification_data.get('time', '')
                
                description = ""
                color = discord.Color.yellow()
                
                if is_warning:
                    if Config.USE_EXTENDED_NOTIFICATIONS and self.storm_messages.get('storm_warning'):
                        description = random.choice(self.storm_messages.get('storm_warning'))
                    else:
                        description = "⚠️ **Внимание!** Приближается шторм! ⚠️"
                    color = discord.Color.yellow()
                elif storm_active:
                    if Config.USE_EXTENDED_NOTIFICATIONS and self.storm_messages.get('storm_start'):
                        description = random.choice(self.storm_messages.get('storm_start'))
                    else:
                        description = "⚡ **На сервере начался шторм!** ⚡"
                    color = discord.Color.red()
                else:
                    if Config.USE_EXTENDED_NOTIFICATIONS and self.storm_messages.get('storm_end'):
                        description = random.choice(self.storm_messages.get('storm_end'))
                    else:
                        description = "☀️ **Шторм на сервере закончился** ☀️"
                    color = discord.Color.green()
                
                # Создаем эмбед
                embed = discord.Embed(
                    title="Штормовое предупреждение" if storm_active or is_warning else "Шторм закончился",
                    description=description,
                    color=color
                )
                
                # Добавляем время из игры, если оно есть
                if game_time:
                    embed.add_field(name="Игровое время", value=game_time, inline=False)
            
            # Обработка уведомлений о смене сезона
            elif actual_type == 'season_notification' or notification_type == 'season':
                # Получаем сезон и конвертируем название
                season_raw = notification_data.get('season', '')
                season_raw = season_raw.lower() if season_raw else ''
                
                # Маппинг русских названий на английские
                season_ru_to_eng = {
                    'весна': 'spring',
                    'лето': 'summer',
                    'осень': 'autumn',
                    'зима': 'winter'
                }
                
                # Маппинг английских названий на русские
                season_eng_to_ru = {
                    'spring': 'весна',
                    'summer': 'лето',
                    'autumn': 'осень',
                    'winter': 'зима'
                }
                
                # Определяем сезон (сначала проверяем русское название, потом английское)
                season_eng = season_ru_to_eng.get(season_raw, season_raw)
                if season_eng not in ['spring', 'summer', 'autumn', 'winter']:
                    season_eng = season_raw  # оставляем как есть, если это уже английское название
                
                season_ru = season_eng_to_ru.get(season_eng, season_raw)
                
                game_time = notification_data.get('time', '')
                
                # Определяем цвет в зависимости от сезона
                colors = {
                    'spring': discord.Color.green(),
                    'summer': discord.Color(0x2ecc71),  # Более яркий зеленый
                    'autumn': discord.Color.yellow(),
                    'winter': discord.Color.blue()
                }
                color = colors.get(season_eng, discord.Color.blue())
                
                # Получаем сообщение из файла
                description = ""
                if season_eng and season_eng in self.season_messages:
                    messages = self.season_messages[season_eng]
                    description = random.choice(messages)
                else:
                    default_messages = {
                        'spring': "🌱 **Наступила весна!** Время пробуждения природы и новых начинаний.",
                        'summer': "☀️ **Наступило лето!** Пора расцвета и изобилия.",
                        'autumn': "🍂 **Наступила осень!** Время сбора урожая и подготовки к зиме.",
                        'winter': "❄️ **Наступила зима!** Время холодов и долгих ночей."
                    }
                    description = default_messages.get(season_eng, "Наступил новый сезон!")
                
                # Создаем эмбед
                embed = discord.Embed(
                    title="Смена сезона",
                    description=description,
                    color=color
                )
                
                # Добавляем время из игры, если оно есть
                if game_time:
                    embed.add_field(name="Игровое время", value=game_time, inline=False)

            # Обработка уведомлений о статусе сервера
            elif actual_type == 'server_status':
                return True

            # Если сформирован эмбед, отправляем его
            if embed:
                try:
                    await self.notification_channel.send(embed=embed)
                    return True
                except discord.Forbidden as e:
                    logger.error(f"Нет прав для отправки сообщения в канал: {e}")
                    return False
                except discord.HTTPException as e:
                    logger.error(f"Ошибка HTTP при отправке сообщения: {e}")
                    return False
                except Exception as e:
                    logger.error(f"Неожиданная ошибка при отправке уведомления: {e}")
                    return False
            
            return False
            
        except Exception as e:
            logger.error(f"Ошибка при обработке уведомления: {e}")
            return False

    @commands.command(name='test_storm', aliases=['тест_шторм'])
    @admin_only()
    async def test_storm(self, ctx, storm_type="start"):
        """Отправляет тестовое уведомление о шторме
        
        Параметры:
        storm_type - тип уведомления: start (начало), warning (предупреждение), end (конец)
        """
        try:
            if storm_type == "warning":
                test_data = {
                    "type": "storm_notification",
                    "data": {
                        "is_active": False,
                        "is_warning": True,
                        "time": "1 января 1 года, 12:00"
                    }
                }
                message = "Отправляю тестовое уведомление о предупреждении шторма"
            elif storm_type == "end":
                test_data = {
                    "type": "storm_notification",
                    "data": {
                        "is_active": False,
                        "is_warning": False,
                        "time": "1 января 1 года, 12:00"
                    }
                }
                message = "Отправляю тестовое уведомление о конце шторма"
            else:  # start по умолчанию
                test_data = {
                    "type": "storm_notification",
                    "data": {
                        "is_active": True,
                        "is_warning": False,
                        "time": "1 января 1 года, 12:00"
                    }
                }
                message = "Отправляю тестовое уведомление о начале шторма"
            
            await ctx.send(message)
            result = await self.process_notification(test_data)
            
            if result:
                await ctx.send("✅ Тестовое уведомление успешно отправлено")
            else:
                await ctx.send("❌ Не удалось отправить тестовое уведомление")
                
        except Exception as e:
            logger.error(f"Ошибка при отправке тестового уведомления: {e}")
            await ctx.send(f"❌ Произошла ошибка: {str(e)}")

    @commands.command(name='test_season', aliases=['тест_сезон'])
    @admin_only()
    async def test_season(self, ctx, season_type="spring"):
        """Отправляет тестовое уведомление о смене сезона
        
        Параметры:
        season_type - тип сезона: spring (весна), summer (лето), autumn (осень), winter (зима)
        """
        try:
            # Проверяем корректность типа сезона
            if season_type not in ["spring", "summer", "autumn", "winter"]:
                await ctx.send("❌ Неизвестный тип сезона. Используйте: spring, summer, autumn, winter")
                return
                
            # Маппинг английских названий на русские
            season_eng_to_ru = {
                'spring': 'весна',
                'summer': 'лето',
                'autumn': 'осень',
                'winter': 'зима'
            }
            
            # Формируем тестовые данные для уведомления
            test_data = {
                "type": "season_notification",
                "data": {
                    "season": season_type,
                    "time": "1 января 1 года, 12:00"
                }
            }
            
            message = f"Отправляю тестовое уведомление о смене сезона на {season_eng_to_ru.get(season_type, season_type)}"
            await ctx.send(message)
            
            result = await self.process_notification(test_data)
            
            if result:
                await ctx.send("✅ Тестовое уведомление успешно отправлено")
            else:
                await ctx.send("❌ Не удалось отправить тестовое уведомление")
            
        except Exception as e:
            logger.error(f"Ошибка при отправке тестового уведомления о сезоне: {e}")
            await ctx.send(f"❌ Произошла ошибка: {str(e)}")

async def setup(bot):
    """Настройка cog"""
    await bot.add_cog(Notifications(bot)) 