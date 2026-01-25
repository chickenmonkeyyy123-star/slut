import discord
import os
from discord import Object
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1332118870181412936  # replace with your server ID

intents = discord.Intents.default()
bot = discord.Client(intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    guild = Object(id=GUILD_ID)
    commands = await bot.http.get_guild_application_commands(bot.user.id, GUILD_ID)
    
    for cmd in commands:
        await bot.http.delete_guild_application_command(bot.user.id, GUILD_ID, cmd['id'])
        print(f"Deleted {cmd['name']}")
    
    print("All commands cleared!")
    await bot.close()

bot.run(TOKEN)
