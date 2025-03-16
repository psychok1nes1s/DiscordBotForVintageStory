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

class Guides(commands.Cog):
    """Cog для работы с гайдами"""
    
    def __init__(self, bot):
        self.bot = bot
        
        # Пути к файлам
        self.BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        self.DATA_DIR = os.path.join(self.BASE_DIR, 'data')
        self.GUIDES_FILE = os.path.join(self.DATA_DIR, 'guides.json')
        
        # Загрузка гайдов
        self.guides_data = self.load_guides()
    
    def load_guides(self):
        """Загружает данные гайдов из файла"""
        try:
            if os.path.exists(self.GUIDES_FILE):
                with open(self.GUIDES_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            return {"guides": []}
        except Exception as e:
            logger.error(f"Ошибка при загрузке гайдов: {e}")
            return {"guides": []}
    
    def save_guides(self):
        """Сохраняет данные гайдов в файл"""
        try:
            with open(self.GUIDES_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.guides_data, f, ensure_ascii=False, indent=2)
            return True
        except Exception as e:
            logger.error(f"Ошибка при сохранении гайдов: {e}")
            return False
    
    @commands.command(name='guides', aliases=['гайды'])
    async def guides(self, ctx):
        """Отображает список доступных гайдов"""
        try:
            guides = self.guides_data.get('guides', [])
            
            if not guides:
                await ctx.send("❌ На данный момент нет доступных гайдов.")
                return
            
            # Создаем эмбед со списком гайдов
            embed = discord.Embed(
                title="Доступные гайды",
                description="Используйте команду `!гайд [номер]` для просмотра конкретного гайда",
                color=discord.Color.blue()
            )
            
            # Добавляем информацию о каждом гайде
            for i, guide in enumerate(guides, 1):
                embed.add_field(
                    name=f"{i}. {guide.get('title', 'Без названия')}",
                    value=guide.get('short_description', 'Без описания')[:100] + "..." if len(guide.get('short_description', 'Без описания')) > 100 else guide.get('short_description', 'Без описания'),
                    inline=False
                )
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Ошибка при выполнении команды guides: {e}")
            await ctx.send("❌ Произошла ошибка при получении списка гайдов.")
    
    @commands.command(name='guide', aliases=['гайд'])
    async def guide(self, ctx, guide_id: int = None):
        """Отображает конкретный гайд по его номеру"""
        try:
            guides = self.guides_data.get('guides', [])
            
            if not guides:
                await ctx.send("❌ На данный момент нет доступных гайдов.")
                return
            
            if guide_id is None:
                await ctx.send("❌ Вы не указали номер гайда. Используйте команду `!гайды` для просмотра доступных гайдов.")
                return
            
            # Проверяем валидность ID гайда
            if guide_id < 1 or guide_id > len(guides):
                await ctx.send(f"❌ Гайд с номером {guide_id} не найден. Используйте команду `!гайды` для просмотра доступных гайдов.")
                return
            
            # Получаем информацию о гайде
            guide = guides[guide_id - 1]
            
            # Создаем эмбед с информацией о гайде
            embed = discord.Embed(
                title=guide.get('title', 'Без названия'),
                description=guide.get('content', 'Без содержания'),
                color=discord.Color.blue()
            )
            
            # Добавляем изображение, если оно есть
            image_url = guide.get('image_url')
            if image_url:
                embed.set_image(url=image_url)
            
            # Добавляем разделы гайда
            sections = guide.get('sections', [])
            for section in sections:
                embed.add_field(
                    name=section.get('title', 'Без названия'),
                    value=section.get('content', 'Без содержания'),
                    inline=False
                )
            
            # Добавляем информацию об авторе, если она есть
            author = guide.get('author')
            if author:
                embed.set_footer(text=f"Автор: {author}")
            
            await ctx.send(embed=embed)
            
        except Exception as e:
            logger.error(f"Ошибка при выполнении команды guide: {e}")
            await ctx.send("❌ Произошла ошибка при получении информации о гайде.")
    
    @commands.command(name='add_guide', aliases=['добавить_гайд'])
    @admin_only()
    async def add_guide(self, ctx, *, args=None):
        """Добавляет новый гайд.
        
        Использование:
        !add_guide title | description | [image_url] | [author]
        """
        try:
            if not args:
                await ctx.send("❌ Вы не указали параметры гайда. Используйте команду `!add_guide title | description | [image_url] | [author]`")
                return
            
            # Разбиваем аргументы на параметры гайда
            params = args.split('|')
            
            if len(params) < 2:
                await ctx.send("❌ Недостаточно параметров. Используйте команду `!add_guide title | description | [image_url] | [author]`")
                return
            
            # Получаем параметры гайда
            title = params[0].strip()
            description = params[1].strip()
            image_url = params[2].strip() if len(params) > 2 else ""
            author = params[3].strip() if len(params) > 3 else ""
            
            # Создаем новый гайд
            new_guide = {
                'title': title,
                'description': description,
                'image_url': image_url,
                'author': author,
                'sections': []
            }
            
            # Добавляем гайд в список
            self.guides_data['guides'].append(new_guide)
            
            # Сохраняем изменения
            if self.save_guides():
                await ctx.send(f"✅ Гайд '{title}' успешно добавлен.")
            else:
                await ctx.send("❌ Произошла ошибка при сохранении гайда.")
            
        except Exception as e:
            logger.error(f"Ошибка при выполнении команды add_guide: {e}")
            await ctx.send("❌ Произошла ошибка при добавлении гайда.")
    
    @commands.command(name='add_section', aliases=['добавить_раздел'])
    @admin_only()
    async def add_section(self, ctx, guide_id: int = None, *, args=None):
        """Добавляет новый раздел к существующему гайду.
        
        Использование:
        !add_section [guide_id] title | content
        """
        try:
            if guide_id is None or not args:
                await ctx.send("❌ Вы не указали ID гайда или параметры раздела. Используйте команду `!add_section [guide_id] title | content`")
                return
            
            guides = self.guides_data.get('guides', [])
            
            # Проверяем валидность ID гайда
            if guide_id < 1 or guide_id > len(guides):
                await ctx.send(f"❌ Гайд с номером {guide_id} не найден. Используйте команду `!гайды` для просмотра доступных гайдов.")
                return
            
            # Разбиваем аргументы на параметры раздела
            params = args.split('|')
            
            if len(params) < 2:
                await ctx.send("❌ Недостаточно параметров. Используйте команду `!add_section [guide_id] title | content`")
                return
            
            # Получаем параметры раздела
            title = params[0].strip()
            content = params[1].strip()
            
            # Создаем новый раздел
            new_section = {
                'title': title,
                'content': content
            }
            
            # Добавляем раздел к гайду
            self.guides_data['guides'][guide_id - 1]['sections'].append(new_section)
            
            # Сохраняем изменения
            if self.save_guides():
                await ctx.send(f"✅ Раздел '{title}' успешно добавлен к гайду #{guide_id}.")
            else:
                await ctx.send("❌ Произошла ошибка при сохранении раздела.")
            
        except Exception as e:
            logger.error(f"Ошибка при выполнении команды add_section: {e}")
            await ctx.send("❌ Произошла ошибка при добавлении раздела.")
    
    @commands.command(name='remove_guide', aliases=['удалить_гайд'])
    @admin_only()
    async def remove_guide(self, ctx, guide_id: int = None):
        """Удаляет гайд по его номеру.
        
        Использование:
        !remove_guide [guide_id]
        """
        try:
            if guide_id is None:
                await ctx.send("❌ Вы не указали номер гайда. Используйте команду `!гайды` для просмотра доступных гайдов.")
                return
            
            guides = self.guides_data.get('guides', [])
            
            # Проверяем валидность ID гайда
            if guide_id < 1 or guide_id > len(guides):
                await ctx.send(f"❌ Гайд с номером {guide_id} не найден. Используйте команду `!гайды` для просмотра доступных гайдов.")
                return
            
            # Получаем название гайда для подтверждения
            guide_title = guides[guide_id - 1].get('title', 'Без названия')
            
            # Удаляем гайд
            del self.guides_data['guides'][guide_id - 1]
            
            # Сохраняем изменения
            if self.save_guides():
                await ctx.send(f"✅ Гайд '{guide_title}' успешно удален.")
            else:
                await ctx.send("❌ Произошла ошибка при удалении гайда.")
            
        except Exception as e:
            logger.error(f"Ошибка при выполнении команды remove_guide: {e}")
            await ctx.send("❌ Произошла ошибка при удалении гайда.")

async def setup(bot):
    """Настройка cog"""
    await bot.add_cog(Guides(bot)) 