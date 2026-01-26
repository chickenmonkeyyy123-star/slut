import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

# ---------- LOAD .ENV ----------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = os.getenv("GUILD_ID")  # optional: use if you want to clear guild commands only

# ---------- BOT SETUP ----------
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    
    # ---------- CLEAR COMMANDS ----------
    guild = None
    if GUILD_ID:
        guild = discord.Object(id=int(GUILD_ID))

    print("Clearing all commands...")
    # Clear commands globally or in a guild
    await bot.tree.clear_commands(guild=guild)
    await bot.tree.sync(guild=guild)
    print("All commands cleared successfully!")

    # Optional: stop the bot after clearing
    await bot.close()

bot.run(TOKEN)
