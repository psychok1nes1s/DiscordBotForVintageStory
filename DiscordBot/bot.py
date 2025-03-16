import os
import logging
import asyncio
import discord
from discord.ext import commands
import aiohttp
from config import Config

# Настройка логирования
logging.basicConfig(
    level=logging.ERROR,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("discord_bot.log", encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger('discord_bot')

# Инициализация бота
intents = discord.Intents.default()
intents.message_content = True  # Разрешаем боту читать содержимое сообщений
bot = commands.Bot(command_prefix=['!', '/'], description="Бот для управления сервером Vintage Story", intents=intents)

# Путь к директории с cogs
COGS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'cogs')

# Список расширений (cogs) для загрузки
EXTENSIONS = [
    'cogs.server_status',
    'cogs.notifications',
    'cogs.guides',
    'cogs.messages'
]

@bot.event
async def on_ready():
    """Выполняется при успешном подключении бота к Discord"""
    logger.warning(f'Бот {bot.user.name} успешно подключен к Discord! ID: {bot.user.id}')
    
    # Устанавливаем начальный статус бота
    await bot.change_presence(
        activity=discord.Game(name=f"{Config.SERVER_NAME}: Подключение к серверу..."),
        status=discord.Status.idle
    )
    
    # Логируем информацию о серверах, к которым подключен бот
    guilds_info = ", ".join([f"{guild.name} (ID: {guild.id})" for guild in bot.guilds])
    logger.warning(f"Подключен к следующим серверам: {guilds_info}")

@bot.event
async def on_command_error(ctx, error):
    """Обработчик ошибок команд"""
    if isinstance(error, commands.CommandNotFound):
        return  # Игнорируем ошибки о ненайденных командах
    
    if isinstance(error, commands.MissingRequiredArgument):
        await ctx.send(f"❌ Отсутствует обязательный аргумент: {error.param.name}")
        return
    
    if isinstance(error, commands.BadArgument):
        await ctx.send(f"❌ Неверный формат аргумента: {error}")
        return
    
    # Логируем необработанные ошибки
    logger.error(f"Ошибка при выполнении команды {ctx.command}: {error}")
    await ctx.send("❌ Произошла ошибка при выполнении команды. Проверьте журнал для получения подробностей.")

@bot.command(name='ping', aliases=['пинг'])
async def ping(ctx):
    """Проверяет время отклика бота"""
    latency = round(bot.latency * 1000)
    await ctx.send(f"Pong! 🏓 Задержка: {latency} мс")

@bot.command(name='uptime', aliases=['аптайм'])
async def uptime(ctx):
    """Показывает время работы бота"""
    import datetime
    uptime = datetime.datetime.now() - bot.start_time
    days = uptime.days
    hours, remainder = divmod(uptime.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    
    uptime_str = f"{days} дн. {hours} ч. {minutes} мин. {seconds} сек."
    
    embed = discord.Embed(
        title="Время работы бота",
        description=f"Бот работает: {uptime_str}",
        color=discord.Color.blue()
    )
    
    await ctx.send(embed=embed)

async def load_extensions():
    """Загружает все расширения (cogs)"""
    for extension in EXTENSIONS:
        try:
            await bot.load_extension(extension)
            # Не логируем успешную загрузку
        except Exception as e:
            logger.error(f"Не удалось загрузить расширение {extension}: {e}")

async def main():
    """Основная функция запуска бота"""
    try:
        # Сохраняем время запуска бота
        bot.start_time = discord.utils.utcnow()
        
        # Загружаем расширения
        await load_extensions()
        
        # Запускаем бота
        await bot.start(Config.DISCORD_TOKEN)
    except aiohttp.ClientConnectorError:
        logger.error("Не удалось подключиться к Discord. Проверьте интернет-соединение.")
    except discord.errors.LoginFailure:
        logger.error("Не удалось авторизоваться в Discord. Проверьте токен бота.")
    except Exception as e:
        logger.error(f"Произошла ошибка при запуске бота: {e}")
    finally:
        if not bot.is_closed():
            await bot.close()

if __name__ == "__main__":
    # Запускаем бота в цикле событий asyncio
    asyncio.run(main())
