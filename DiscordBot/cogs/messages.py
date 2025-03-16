import os
import json
import logging
import discord
from discord.ext import commands
import functools
from config import Config

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

class Messages(commands.Cog):
    """Cog для управления сообщениями бота"""
    
    def __init__(self, bot):
        self.bot = bot
        
        # Пути к файлам сообщений
        self.BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.DATA_DIR = os.path.join(self.BASE_DIR, 'data')
        self.STORM_MESSAGES_FILE = os.path.join(self.DATA_DIR, 'storm_messages.json')
        self.SEASON_MESSAGES_FILE = os.path.join(self.DATA_DIR, 'season_messages.json')
        
        # Загрузка сообщений
        self.storm_messages = self.load_messages('storm')
        self.season_messages = self.load_messages('season')
    
    def load_messages(self, message_type):
        """Загружает сообщения указанного типа из файла"""
        try:
            file_path = ''
            if message_type == 'storm':
                file_path = self.STORM_MESSAGES_FILE
            elif message_type == 'season':
                file_path = self.SEASON_MESSAGES_FILE
            
            if file_path and os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {}
        except Exception as e:
            logger.error(f"Ошибка при загрузке сообщений типа {message_type}: {e}")
            return {}
    
    def save_messages(self, message_type, messages):
        """Сохраняет сообщения указанного типа в файл"""
        try:
            file_path = ''
            if message_type == 'storm':
                file_path = self.STORM_MESSAGES_FILE
            elif message_type == 'season':
                file_path = self.SEASON_MESSAGES_FILE
            
            if file_path:
                with open(file_path, 'w', encoding='utf-8') as f:
                    json.dump(messages, f, ensure_ascii=False, indent=2)
                return True
            return False
        except Exception as e:
            logger.error(f"Ошибка при сохранении сообщений типа {message_type}: {e}")
            return False
    
    @commands.command(name='reload_messages', aliases=['перезагрузить_сообщения'])
    @admin_only()
    async def reload_messages(self, ctx):
        """Перезагружает все сообщения из файлов"""
        try:
            # Обновляем сообщения в текущем модуле
            self.storm_messages = self.load_messages('storm')
            self.season_messages = self.load_messages('season')
            
            # Обновляем сообщения в модуле Notifications, если он загружен
            notifications_cog = self.bot.get_cog('Notifications')
            if notifications_cog:
                notifications_cog.storm_messages = notifications_cog.load_messages('storm')
                notifications_cog.season_messages = notifications_cog.load_messages('season')
                logger.info("Сообщения в модуле Notifications успешно обновлены")
            
            await ctx.send("✅ Сообщения успешно перезагружены.")
        except Exception as e:
            logger.error(f"Ошибка при перезагрузке сообщений: {e}")
            await ctx.send(f"❌ Произошла ошибка при перезагрузке сообщений: {e}")
    
    @commands.command(name='list_messages', aliases=['список_сообщений'])
    @admin_only()
    async def list_messages(self, ctx, message_type=None):
        """Отображает список доступных сообщений указанного типа"""
        try:
            if not message_type:
                embed = discord.Embed(
                    title="Типы сообщений",
                    description="Доступные типы сообщений:",
                    color=discord.Color.blue()
                )
                
                embed.add_field(
                    name="🌩️ Шторм",
                    value="Сообщения о штормах\nКоманда: `!список_сообщений storm`",
                    inline=True
                )
                
                embed.add_field(
                    name="🌱 Сезоны",
                    value="Сообщения о смене сезонов\nКоманда: `!список_сообщений season`",
                    inline=True
                )
                
                await ctx.send(embed=embed)
                return
            
            messages = None
            if message_type.lower() == "storm":
                messages = self.storm_messages
                message_title = "🌩️ Сообщения о штормах"
            elif message_type.lower() == "season":
                messages = self.season_messages
                message_title = "🌱 Сообщения о сезонах"
            else:
                await ctx.send(f"❌ Неизвестный тип сообщений: {message_type}")
                return
            
            # Создаем эмбед со списком сообщений
            embed = discord.Embed(
                title=message_title,
                description=f"Тип сообщений: {message_type}",
                color=discord.Color.blue()
            )
            
            # Добавляем сообщения в эмбед
            if not messages:
                embed.add_field(name="Нет сообщений", value="Для этого типа нет настроенных сообщений", inline=False)
            else:
                for key, value in messages.items():
                    if isinstance(value, list):
                        # Если значение - список сообщений
                        message_list = "\n".join([f"- {msg}" for msg in value])
                        embed.add_field(name=key, value=message_list if message_list else "Пусто", inline=False)
                    else:
                        # Если значение - одиночное сообщение
                        embed.add_field(name=key, value=value, inline=False)
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Ошибка при выполнении команды list_messages: {e}")
            await ctx.send("❌ Произошла ошибка при получении списка сообщений.")
    
    @commands.command(name='add_message', aliases=['добавить_сообщение'])
    @admin_only()
    async def add_message(self, ctx, message_type=None, message_key=None, *, message_text=None):
        """Добавляет новое сообщение указанного типа.
        
        Использование:
        !add_message [тип_сообщений] [ключ] [текст_сообщения]
        
        Доступные типы сообщений:
        - storm
        - season
        
        Примеры ключей:
        - start (для storm)
        - spring (для season)
        - summer (для season)
        - autumn (для season)
        - winter (для season)
        """
        try:
            if not message_type or not message_key or not message_text:
                await ctx.send("❌ Не все параметры указаны. Используйте команду `!add_message [тип_сообщений] [ключ] [текст_сообщения]`")
                return
            
            # Получаем сообщения указанного типа
            messages = {}
            if message_type == 'storm':
                messages = self.storm_messages
            elif message_type == 'season':
                messages = self.season_messages
            else:
                await ctx.send(f"❌ Неизвестный тип сообщений: {message_type}. Используйте команду `!list_messages` для просмотра доступных типов.")
                return
            
            # Добавляем сообщение
            if message_key in messages and isinstance(messages[message_key], list):
                # Если ключ уже существует и это список, добавляем сообщение в список
                messages[message_key].append(message_text)
            elif message_key in messages:
                # Если ключ уже существует, но это не список, преобразуем в список
                messages[message_key] = [messages[message_key], message_text]
            else:
                # Если ключ не существует, создаем новый список
                messages[message_key] = [message_text]
            
            # Сохраняем изменения
            if message_type == 'storm':
                self.storm_messages = messages
            elif message_type == 'season':
                self.season_messages = messages
            
            # Сохраняем сообщения в файл
            if self.save_messages(message_type, messages):
                await ctx.send(f"✅ Сообщение успешно добавлено к типу '{message_type}' с ключом '{message_key}'.")
            else:
                await ctx.send("❌ Произошла ошибка при сохранении сообщения.")
            
        except Exception as e:
            logger.error(f"Ошибка при выполнении команды add_message: {e}")
            await ctx.send("❌ Произошла ошибка при добавлении сообщения.")
    
    @commands.command(name='remove_message', aliases=['удалить_сообщение'])
    @admin_only()
    async def remove_message(self, ctx, message_type=None, message_key=None, message_index: int = None):
        """Удаляет сообщение указанного типа.
        
        Использование:
        !remove_message [тип_сообщений] [ключ] [индекс]
        
        Индекс - это номер сообщения в списке (начиная с 0).
        Если индекс не указан, будут удалены все сообщения с указанным ключом.
        
        Доступные типы сообщений:
        - storm
        - season
        """
        try:
            if not message_type or not message_key:
                await ctx.send("❌ Не все параметры указаны. Используйте команду `!remove_message [тип_сообщений] [ключ] [индекс]`")
                return
            
            # Получаем сообщения указанного типа
            messages = {}
            if message_type == 'storm':
                messages = self.storm_messages
            elif message_type == 'season':
                messages = self.season_messages
            else:
                await ctx.send(f"❌ Неизвестный тип сообщений: {message_type}. Используйте команду `!list_messages` для просмотра доступных типов.")
                return
            
            # Проверяем существование ключа
            if message_key not in messages:
                await ctx.send(f"❌ Ключ '{message_key}' не найден в сообщениях типа '{message_type}'.")
                return
            
            # Удаляем сообщение
            if message_index is not None:
                # Если указан индекс, удаляем конкретное сообщение
                if isinstance(messages[message_key], list):
                    if 0 <= message_index < len(messages[message_key]):
                        removed_message = messages[message_key].pop(message_index)
                        success_message = f"✅ Сообщение с индексом {message_index} успешно удалено из типа '{message_type}' с ключом '{message_key}'."
                        
                        # Если список пуст, удаляем ключ
                        if not messages[message_key]:
                            del messages[message_key]
                            success_message += f" Ключ '{message_key}' удален, так как список сообщений пуст."
                    else:
                        await ctx.send(f"❌ Индекс {message_index} выходит за пределы списка сообщений.")
                        return
                else:
                    await ctx.send(f"❌ Сообщение с ключом '{message_key}' не является списком.")
                    return
            else:
                # Если индекс не указан, удаляем все сообщения с указанным ключом
                del messages[message_key]
                success_message = f"✅ Все сообщения успешно удалены из типа '{message_type}' с ключом '{message_key}'."
            
            # Сохраняем изменения
            if message_type == 'storm':
                self.storm_messages = messages
            elif message_type == 'season':
                self.season_messages = messages
            
            # Сохраняем сообщения в файл
            if self.save_messages(message_type, messages):
                await ctx.send(success_message)
            else:
                await ctx.send("❌ Произошла ошибка при сохранении изменений.")
            
        except Exception as e:
            logger.error(f"Ошибка при выполнении команды remove_message: {e}")
            await ctx.send("❌ Произошла ошибка при удалении сообщения.")

async def setup(bot):
    """Настройка cog"""
    await bot.add_cog(Messages(bot)) 