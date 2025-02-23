import discord
from discord.ext import commands
import requests
from requests.exceptions import RequestException, Timeout
from config import Config

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='!', intents=intents)

async def fetch_server_status():
    try:
        response = requests.get(Config.VS_SERVER_URL, timeout=5)
        response.raise_for_status()
        return response.json()
    except Timeout:
        print("Request timed out")
        return None
    except RequestException as e:
        print(f"Request error: {e}")
        return None

@bot.command(name='status')
async def status(ctx):
    data = await fetch_server_status()
    
    if data is None:
        await ctx.send("❌ Cannot connect to Vintage Story server")
        return

    embed = discord.Embed(title="Vintage Story Server Status", color=0x00ff00)
    
    # Players info
    embed.add_field(
        name=f"Players Online: {data['playerCount']}", 
        value="\n".join(data['players']) if data['players'] else "No players online",
        inline=False
    )
    
    # Time
    embed.add_field(name="In-Game Time", value=data['time'], inline=True)

    # Temporal storm
    embed.add_field(
        name="Temporal Storm", 
        value=data['temporalStorm'],
        inline=False
    )

    await ctx.send(embed=embed)

@bot.event
async def on_ready():
    print(f'Bot is ready! Logged in as {bot.user}')

bot.run(Config.DISCORD_TOKEN)
