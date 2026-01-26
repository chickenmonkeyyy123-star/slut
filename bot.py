import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

# ---------------- LOAD TOKEN ----------------
# Try loading from .env first
load_dotenv(dotenv_path="/home/container/.env")  # adjust path if needed
TOKEN = os.getenv("DISCORD_TOKEN")

# Fallback: hardcode token if not loaded from .env
if not TOKEN:
    TOKEN = "YOUR_REAL_BOT_TOKEN_HERE"  # replace with your bot token
    print("Using hardcoded token!")

print("Token loaded. First 5 chars:", TOKEN[:5], "...")  # debug, never print full token

# ---------------- CONFIG ----------------
GUILD_ID = os.getenv("GUILD_ID")  # optional: clear commands only in a guild
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------------- EVENT ----------------
@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user} (ID: {bot.user.id})")

    # If GUILD_ID is set, only clear that guild's commands
    guild = discord.Object(id=int(GUILD_ID)) if GUILD_ID else None

    print("Clearing all commands...")
    await bot.tree.clear_commands(guild=guild)
    await bot.tree.sync(guild=guild)
    print("All commands cleared successfully!")

    # Stop the bot automatically after clearing
    await bot.close()

# ---------------- RUN BOT ----------------
bot.run(TOKEN)
