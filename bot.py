import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
import random
import json
import os
from dotenv import load_dotenv
import asyncio
from datetime import datetime, timedelta

# ---------- LOAD .ENV ----------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN not found in .env")

# ---------- CONFIG ----------
DATA_FILE = "dabloon_data.json"
START_BALANCE = 1000
GUILD_ID = 1332118870181412936  # replace with your server ID

# ---------- BOT ----------
intents = discord.Intents.default()
intents.guilds = True  # ✅ REQUIRED for slash commands
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------- DATA ----------
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

data = load_data()

def get_user(uid):
    uid = str(uid)
    if uid not in data:
        data[uid] = {
            "balance": START_BALANCE,
            "blackjack": {"wins": 0, "losses": 0},
            "coinflip": {"wins": 0, "losses": 0},
        }
        save_data()
    return data[uid]

def total_wl(u):
    return (
        u["blackjack"]["wins"] + u["coinflip"]["wins"],
        u["blackjack"]["losses"] + u["coinflip"]["losses"],
    )

# ---------- READY ----------
@bot.event
async def on_ready():
    guild = discord.Object(id=GUILD_ID)
    await bot.tree.sync(guild=guild)  # ✅ Sync commands to guild
    print(f"Logged in as {bot.user} and synced commands to guild {GUILD_ID}")

# ---------- SYNC COMMAND ----------
@bot.tree.command(name="sync")
async def sync(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Only admins can sync.", ephemeral=True)
    guild = discord.Object(id=GUILD_ID)
    await bot.tree.sync(guild=guild)
    await interaction.response.send_message("✅ Commands fully synced.", ephemeral=True)

# ---------- NOW ADD YOUR COMMANDS ----------
# /bj, /cf, /lb, /giveaway, /claim
# Keep all previous command code exactly the same
# Just make sure all @bot.tree.command decorators are applied

# Example:
@bot.tree.command(name="bj")
async def bj(interaction: discord.Interaction, amount: int):
    # Blackjack logic here
    ...

# ---------- RUN ----------
bot.run(TOKEN)
