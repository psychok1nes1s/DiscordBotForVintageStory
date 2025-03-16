import os
import json
import logging
import asyncio
import discord
from discord.ext import commands, tasks
from datetime import datetime
import aiohttp
import hashlib
import requests
from config import Config

logger = logging.getLogger('discord_bot')

class ServerStatus(commands.Cog):
    """Cog для управления статусом сервера и отображения информации о сервере"""
    
    def __init__(self, bot):
        self.bot = bot
        self.server_online = False
        self.player_count = 0
        self.manual_maintenance_mode = False  # Флаг ручного режима техобслуживания
        self.maintenance_reason = ""  # Причина техобслуживания
        self.channel_update_lock = asyncio.Lock()
        
        # Пути к файлам
        self.BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.DATA_DIR = os.path.join(self.BASE_DIR, 'data')
        self.SERVER_STATUS_FILE = os.path.join(self.DATA_DIR, 'server_status.json')
        
        # Запуск задач
        self.status_update_task.start()
    
    def cog_unload(self):
        """Вызывается при выгрузке cog"""
        self.status_update_task.cancel()
    
    async def fetch_server_status(self):
        """Получает информацию о статусе сервера"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(Config.VS_SERVER_URL, timeout=Config.REQUEST_TIMEOUT) as response:
                    if response.status == 200:
                        try:
                            # Более надежный способ декодирования JSON
                            content_type = response.headers.get('Content-Type', '').lower()
                            logger.debug(f"Content-Type ответа: {content_type}")
                            
                            if 'application/json' in content_type:
                                data = await response.json(content_type=None)
                            else:
                                # Считываем текст и пробуем вручную декодировать JSON
                                text = await response.text()
                                logger.info(f"Получен ответ не в формате JSON. Content-Type: {content_type}")
                                logger.debug(f"Текст ответа: {text[:200]}")
                                
                                # Пытаемся парсить как JSON в любом случае
                                try:
                                    import json
                                    data = json.loads(text)
                                except json.JSONDecodeError as e:
                                    logger.error(f"Не удалось распарсить ответ как JSON: {e}")
                                    return {'online': False}
                            
                            # Полная диагностика данных от сервера
                            logger.debug(f"Ответ от сервера: {data}")
                            
                            # Если в ответе есть игроки, но статус "offline", исправляем на "online"
                            if (not data.get('online', False) and 
                                (data.get('players') and len(data.get('players', [])) > 0 or 
                                 data.get('playerCount', 0) > 0)):
                                data['online'] = True
                                logger.info("Сервер вернул статус 'offline', но есть игроки онлайн. Исправлено на 'online'.")
                            
                            return data
                        except aiohttp.ClientResponseError as e:
                            logger.error(f"Ошибка при декодировании JSON-ответа: {e}")
                            return {'online': False}
                    else:
                        logger.info(f"Ошибка получения статуса сервера. Статус: {response.status}")
                        return {'online': False}
        except aiohttp.ClientConnectorError:
            logger.info("Не удалось подключиться к серверу. Сервер оффлайн или недоступен.")
            return {'online': False}
        except asyncio.TimeoutError:
            logger.info("Таймаут при получении статуса сервера.")
            return {'online': False}
        except Exception as e:
            logger.error(f"Ошибка при получении статуса сервера: {e}")
            return {'online': False}
    
    def ensure_server_status_file(self):
        """Создает файл статуса сервера, если он не существует"""
        os.makedirs(self.DATA_DIR, exist_ok=True)
        
        if not os.path.exists(self.SERVER_STATUS_FILE):
            server_status = {
                "server": {
                    "online": False,
                    "player_count": 0,
                    "max_players": Config.DEFAULT_MAX_PLAYERS,
                    "last_checked": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "players": []
                },
                "manual_maintenance": {
                    "active": False,
                    "reason": ""
                }
            }
            
            with open(self.SERVER_STATUS_FILE, 'w', encoding='utf-8') as f:
                json.dump(server_status, f, ensure_ascii=False, indent=2)
            
            logger.warning(f"Создан файл статуса сервера: {self.SERVER_STATUS_FILE}")
        else:
            # Если файл существует, проверяем есть ли в нем поле manual_maintenance
            try:
                with open(self.SERVER_STATUS_FILE, 'r', encoding='utf-8') as f:
                    server_status = json.load(f)
                
                # Если поля нет, добавляем его
                if "manual_maintenance" not in server_status:
                    server_status["manual_maintenance"] = {
                        "active": False,
                        "reason": ""
                    }
                    
                    # Сохраняем обновленный статус
                    with open(self.SERVER_STATUS_FILE, 'w', encoding='utf-8') as f:
                        json.dump(server_status, f, ensure_ascii=False, indent=2)
                    
                    logger.warning(f"Добавлено поле manual_maintenance в файл статуса сервера")
            except Exception as e:
                logger.error(f"Ошибка при обработке файла статуса сервера: {e}")
    
    def get_current_server_status(self):
        """Получает текущий статус сервера из файла"""
        try:
            # Убедимся, что файл статуса существует
            self.ensure_server_status_file()
            
            # Читаем данные из файла
            with open(self.SERVER_STATUS_FILE, 'r', encoding='utf-8') as f:
                server_status = json.load(f)
                
            return server_status
        except Exception as e:
            logger.error(f"Ошибка при получении текущего статуса сервера: {e}")
            # Возвращаем базовую структуру в случае ошибки
            return {
                "server": {
                    "online": False,
                    "player_count": 0,
                    "max_players": Config.DEFAULT_MAX_PLAYERS,
                    "last_checked": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "players": []
                },
                "manual_maintenance": {
                    "active": False,
                    "reason": ""
                }
            }
    
    def create_server_status_embed(self, server_info, maintenance_info=None):
        """Создает эмбед с информацией о статусе сервера"""
        try:
            embed = discord.Embed(title=f"Статус сервера: {Config.SERVER_NAME}", color=discord.Color.blue())
            
            # Получаем информацию о сервере из нового формата данных
            server_data = server_info.get('server', {}) if isinstance(server_info, dict) else {}
            manual_maintenance_data = server_info.get('manual_maintenance', {}) if isinstance(server_info, dict) else {}
            
            # Проверяем ручной режим техобслуживания
            manual_maintenance_active = manual_maintenance_data.get('active', False)
            manual_maintenance_reason = manual_maintenance_data.get('reason', '')
            
            # Если включен ручной режим техобслуживания
            if manual_maintenance_active:
                embed.color = discord.Color.orange()
                embed.add_field(name="Статус", value="🟠 Тех. обслуживание", inline=True)
                
                # Если есть сообщение о тех. обслуживании
                if manual_maintenance_reason:
                    embed.add_field(name="Причина", value=manual_maintenance_reason, inline=False)
                else:
                    embed.add_field(name="Информация", value="Сервер находится на техническом обслуживании. Пожалуйста, подождите.", inline=False)
                
                # Добавляем информацию о времени последней проверки
                last_checked = server_data.get('last_checked', '') if server_data else server_info.get('lastChecked', '')
                if last_checked:
                    embed.set_footer(text=f"Последнее обновление: {last_checked}")
                
                return embed
            
            # Определяем статус сервера
            is_online = server_data.get('online', False) if server_data else server_info.get('online', False)
            
            # Если сервер онлайн
            if is_online:
                # Получаем данные о сервере
                player_count = server_data.get('player_count', 0) if server_data else server_info.get('playerCount', 0)
                max_players = server_data.get('max_players', Config.DEFAULT_MAX_PLAYERS) if server_data else server_info.get('maxPlayers', Config.DEFAULT_MAX_PLAYERS)
                tps = server_data.get('tps', 0) if server_data else server_info.get('tps', 0)
                uptime = server_data.get('uptime', '') if server_data else server_info.get('uptime', '')
                version = server_data.get('version', '') if server_data else server_info.get('version', '')
                temporal_storm = server_data.get('temporal_storm', 'Неактивен') if server_data else server_info.get('temporalStorm', 'Неактивен')
                pretty_date = server_data.get('pretty_date', '') if server_data else server_info.get('prettyDate', '')
                
                # Если есть игроки в списке, но player_count равен 0, используем длину списка игроков
                players = server_data.get('players', []) if server_data else server_info.get('players', [])
                if len(players) > 0 and player_count == 0:
                    player_count = len(players)
                
                # Если есть игроки в списке, но player_count равен 0, используем длину списка игроков
                if len(players) > 0 and player_count == 0:
                    player_count = len(players)
                
                # Определяем правильное склонение слова "игрок"
                if player_count == 0:
                    players_text = "нет игроков"
                elif player_count == 1:
                    players_text = "1 игрок"
                elif 2 <= player_count <= 4:
                    players_text = f"{player_count} игрока"
                else:
                    players_text = f"{player_count} игроков"
                
                embed.color = discord.Color.green()
                embed.add_field(name="Статус", value="🟢 Онлайн", inline=True)
                embed.add_field(name="Игроков", value=str(player_count), inline=True)
                
                if tps:
                    embed.add_field(name="TPS", value=f"{tps:.1f}", inline=True)
                
                if uptime:
                    embed.add_field(name="Время работы", value=uptime, inline=True)
                
                if version:
                    embed.add_field(name="Версия", value=version, inline=True)
                
                # Добавляем информацию о темпоральном шторме
                storm_emoji = "⚡" if temporal_storm == "Активен" else "☀️"
                embed.add_field(name="Темпоральный шторм", value=f"{storm_emoji} {temporal_storm}", inline=True)
                
                # Добавляем информацию о текущей дате в игре
                if pretty_date:
                    embed.add_field(name="Дата в игре", value=pretty_date, inline=True)
                
                # Если есть игроки онлайн
                if players:
                    player_names = ", ".join(players)
                    if len(player_names) > 1024:
                        player_names = player_names[:1020] + "..."
                    embed.add_field(name=f"Игроки онлайн ({len(players)})", value=player_names, inline=False)
                else:
                    embed.add_field(name="Игроки онлайн", value="На сервере нет игроков", inline=False)
            
            # Если сервер оффлайн
            else:
                embed.color = discord.Color.red()
                embed.add_field(name="Статус", value="🔴 Оффлайн", inline=True)
                embed.add_field(name="Информация", value="Сервер в данный момент недоступен.", inline=False)
            
            # Добавляем время последней проверки
            last_checked = server_data.get('last_checked', '') if server_data else server_info.get('lastChecked', '')
            if last_checked:
                embed.set_footer(text=f"Последнее обновление: {last_checked}")
            
            return embed
            
        except Exception as e:
            logger.error(f"Ошибка при создании эмбеда: {e}")
            # Возвращаем базовый эмбед в случае ошибки
            basic_embed = discord.Embed(title=f"Статус сервера: {Config.SERVER_NAME}", color=discord.Color.red())
            basic_embed.add_field(name="Ошибка", value="Произошла ошибка при получении информации о сервере.", inline=False)
            return basic_embed
    
    async def update_bot_presence(self, server_info):
        """Обновляет статус бота в Discord на основе статуса сервера"""
        if not self.bot.is_ready():
            # logger.info("Бот не готов. Пропускаем обновление статуса.")
            return
            
        server_data = server_info.get('server', {})
        # logger.info(f"update_bot_presence - server_info: {server_info}")
        # logger.info(f"update_bot_presence - server_data: {server_data}")
        
        # Проверяем режим обслуживания
        maintenance_active = server_info.get('manual_maintenance', {}).get('active', False)
        
        if maintenance_active:
            # Получаем причину обслуживания
            maintenance_reason = server_info.get('manual_maintenance', {}).get('reason', 'Тех. обслуживание')
            
            # Устанавливаем статус "Не беспокоить" с сообщением о техобслуживании
            status_text = f"{Config.SERVER_NAME}: {maintenance_reason}"
            await self.bot.change_presence(
                activity=discord.Game(name=status_text),
                status=discord.Status.dnd
            )
            return
            
        # Если сервер онлайн, показываем количество игроков и игровое время
        if server_data.get('online', False):
            # Получаем базовую информацию
            player_count = server_data.get('player_count', 0)
            max_players = server_data.get('max_players', Config.DEFAULT_MAX_PLAYERS)
            
            # Если player_count равен 0, но список игроков не пуст, исправляем
            if player_count == 0 and server_data.get('players') and len(server_data.get('players', [])) > 0:
                player_count = len(server_data.get('players', []))
                # logger.info(f"update_bot_presence - окончательное количество игроков: {player_count}")
                
            # Получаем игровое время, если оно доступно
            game_time = server_data.get('pretty_date', '')
            storm_status = server_data.get('temporal_storm', 'Неактивен')
            
            # Строим статусную строку
            status_text = f"{Config.SERVER_NAME}: {player_count}/{max_players} игроков"
            
            # Если есть шторм, добавляем информацию о нем
            if storm_status != 'Неактивен':
                status_text += f" | Шторм активен!"
                
            # Устанавливаем статус "Онлайн" с информацией о сервере
            # logger.info(f"update_bot_presence - установка статуса: {status_text}")
            await self.bot.change_presence(
                activity=discord.Game(name=status_text),
                status=discord.Status.online
            )
        else:
            # Если сервер оффлайн, устанавливаем статус "Неактивен"
            await self.bot.change_presence(
                activity=discord.Game(name=f"{Config.SERVER_NAME}: Оффлайн"),
                status=discord.Status.idle
            )
    
    async def update_server_status(self):
        """Обновляет информацию о статусе сервера"""
        # Проверяем режим технического обслуживания
        current_status = self.get_current_server_status()
        maintenance_active = current_status.get('manual_maintenance', {}).get('active', False)
        
        if maintenance_active:
            logger.warning(f"Режим тех.обслуживания активен: {current_status.get('manual_maintenance', {})}")
            # Проверяем, что классовые переменные тоже установлены правильно
            self.manual_maintenance_mode = True
            self.maintenance_reason = current_status.get('manual_maintenance', {}).get('reason', '')
            return current_status
        
        try:
            # Получаем текущий статус сервера
            current_status = self.get_current_server_status()
            
            # Получаем информацию о сервере из API
            server_info = await self.fetch_server_status()
            
            # Логируем текущий статус
            # logger.info(f"Текущий статус: online={current_status.get('server', {}).get('online', False)}, " +
            #             f"player_count={current_status.get('server', {}).get('player_count', 0)}")
            
            # Проверяем изменение статуса онлайн
            prev_online = current_status.get('server', {}).get('online', False)
            curr_online = server_info.get('online', False)
            
            if not prev_online and curr_online:
                logger.warning("Сервер снова онлайн!")
                # TODO: Отправить уведомление о восстановлении сервера
            elif prev_online and not curr_online:
                logger.warning("Сервер перешел в оффлайн режим!")
                # TODO: Отправить уведомление о недоступности сервера
            
            # Обновляем информацию о статусе
            if 'server' not in current_status:
                current_status['server'] = {}
            
            current_status['server']['online'] = server_info.get('online', False)
            
            # Определяем количество игроков
            player_count = server_info.get('playerCount', 0)
            players_list = server_info.get('players', [])
            
            # Если количество игроков равно 0, но список игроков не пустой, используем длину списка
            if player_count == 0 and len(players_list) > 0:
                player_count = len(players_list)
                # logger.info(f"Исправлено количество игроков с 0 на {player_count} на основе списка игроков")
            
            # Если есть игроки, но сервер почему-то помечен как оффлайн, исправляем
            if player_count > 0 and not current_status['server']['online']:
                current_status['server']['online'] = True
                logger.warning("Сервер помечен как оффлайн, но есть игроки онлайн. Исправлено на 'online'.")
            
            current_status['server']['player_count'] = player_count
            current_status['server']['players'] = players_list
            
            current_status['server']['max_players'] = server_info.get('maxPlayers', Config.DEFAULT_MAX_PLAYERS)
            current_status['server']['last_checked'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            current_status['server']['temporal_storm'] = server_info.get('temporalStorm', 'Неактивен')
            current_status['server']['pretty_date'] = server_info.get('prettyDate', '')
            
            # Фиксируем, изменилось ли количество игроков
            player_count_changed = False
            if 'player_count_changed' in current_status:
                old_player_count = current_status.get('server', {}).get('player_count', 0)
                new_player_count = player_count
                player_count_changed = old_player_count != new_player_count
                current_status['player_count_changed'] = player_count_changed
            
            # Обновляем глобальные переменные
            self.server_online = server_info.get('online', False)
            self.player_count = player_count
            
            # Сохраняем обновленный статус в файл
            with open(self.SERVER_STATUS_FILE, 'w', encoding='utf-8') as f:
                json.dump(current_status, f, ensure_ascii=False, indent=2)
            
            # Обновляем статус бота
            await self.update_bot_presence(current_status)
            
            return current_status
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении статуса сервера: {e}")
            return None
    
    @tasks.loop(seconds=15)  # Обновление каждые 15 секунд
    async def status_update_task(self):
        """Задача для обновления статуса сервера"""
        try:
            await self.update_server_status()
        except Exception as e:
            logger.error(f"Ошибка в задаче обновления статуса сервера: {e}")
    
    @status_update_task.before_loop
    async def before_status_update(self):
        """Выполняется перед запуском задачи обновления статуса"""
        await self.bot.wait_until_ready()
        logger.warning("Задача обновления статуса сервера запущена")
    
    @commands.command(name='status', aliases=['статус'])
    async def status(self, ctx):
        """Отображает текущий статус сервера"""
        try:
            # Получаем статус сервера
            server_info = await self.update_server_status()
            
            if not server_info:
                await ctx.send("❌ Не удалось получить информацию о сервере.")
                return
            
            # Создаем и отправляем эмбед с информацией о статусе
            embed = self.create_server_status_embed(server_info)
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Ошибка при выполнении команды status: {e}")
            await ctx.send("❌ Произошла ошибка при получении статуса сервера.")

    @commands.command(name='maintenance', aliases=['тех_работы'])
    @commands.has_permissions(administrator=True)
    async def maintenance(self, ctx, *, reason=None):
        """Включает или выключает режим технического обслуживания сервера.
        
        Использование:
        !тех_работы [причина] - включает режим тех. работ с указанной причиной
        !тех_работы - выключает режим тех. работ, если он был включен
        """
        try:
            # Получаем текущий статус сервера
            current_status = None
            if os.path.exists(self.SERVER_STATUS_FILE):
                with open(self.SERVER_STATUS_FILE, 'r', encoding='utf-8') as f:
                    current_status = json.load(f)
            
            if not current_status:
                current_status = {
                    "server": {
                        "online": False,
                        "player_count": 0,
                        "max_players": Config.DEFAULT_MAX_PLAYERS,
                        "last_checked": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        "players": []
                    },
                    "manual_maintenance": {
                        "active": False,
                        "reason": ""
                    }
                }
            
            # Если в структуре нет раздела для ручного техобслуживания, добавляем его
            if "manual_maintenance" not in current_status:
                current_status["manual_maintenance"] = {
                    "active": False,
                    "reason": ""
                }
            
            # Получаем текущее состояние ручного режима техобслуживания
            is_maintenance_active = current_status["manual_maintenance"]["active"]
            
            # Если причина не указана, выключаем режим техобслуживания
            if not reason:
                if not is_maintenance_active:
                    await ctx.send("❌ Режим технического обслуживания уже выключен.")
                    return
                
                # Выключаем режим техобслуживания
                current_status["manual_maintenance"]["active"] = False
                current_status["manual_maintenance"]["reason"] = ""
                
                self.manual_maintenance_mode = False
                self.maintenance_reason = ""
                
                # Сохраняем изменения в файл
                with open(self.SERVER_STATUS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(current_status, f, ensure_ascii=False, indent=2)
                
                # Обновляем статус бота
                await self.update_bot_presence(current_status)
                
                await ctx.send("✅ Режим технического обслуживания выключен.")
            else:
                # Включаем режим техобслуживания с указанной причиной
                current_status["manual_maintenance"]["active"] = True
                current_status["manual_maintenance"]["reason"] = reason
                
                self.manual_maintenance_mode = True
                self.maintenance_reason = reason
                
                # Сохраняем изменения в файл
                with open(self.SERVER_STATUS_FILE, 'w', encoding='utf-8') as f:
                    json.dump(current_status, f, ensure_ascii=False, indent=2)
                
                # Обновляем статус бота
                await self.update_bot_presence(current_status)
                
                await ctx.send(f"✅ Режим технического обслуживания включен с причиной: {reason}")
            
        except Exception as e:
            logger.error(f"Ошибка при выполнении команды maintenance: {e}")
            await ctx.send("❌ Произошла ошибка при управлении режимом технического обслуживания.")

    @maintenance.error
    async def maintenance_error(self, ctx, error):
        """Обработка ошибок команды maintenance"""
        if isinstance(error, commands.MissingPermissions):
            await ctx.send("❌ У вас недостаточно прав для выполнения этой команды. Требуются права администратора.")
        else:
            logger.error(f"Ошибка при выполнении команды maintenance: {error}")
            await ctx.send("❌ Произошла ошибка при выполнении команды.")

async def setup(bot):
    """Настройка cog"""
    await bot.add_cog(ServerStatus(bot)) 