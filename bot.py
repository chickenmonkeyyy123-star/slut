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

# ---------- BLACKJACK ----------
# [Keep all BlackjackGame and BlackjackView classes as-is]

# ---------- COINFLIP ----------
# [Keep CoinflipView class as-is]

# ---------- COMMANDS ----------

@bot.tree.command(name="bj")
async def bj(interaction: discord.Interaction, amount: int):
    u = get_user(interaction.user.id)
    if amount <= 0 or amount > u["balance"]:
        return await interaction.response.send_message("Invalid bet.", ephemeral=True)
    game = BlackjackGame(amount)
    view = BlackjackView(game, interaction.user)
    await interaction.response.send_message(embed=view.embed(), view=view)

@bot.tree.command(name="cf")
@app_commands.describe(
    amount="Bet amount",
    choice="heads or tails",
    user="User to coinflip against (optional)"
)
async def cf(interaction: discord.Interaction, amount: int, choice: str, user: discord.User | None = None):
    # [Keep cf logic as-is]

@bot.tree.command(name="leaderboard")
async def leaderboard(interaction: discord.Interaction):
    # [Keep leaderboard logic as-is]

# ---------- GIVEAWAY ----------
# [Keep GiveawayView and giveaway logic as-is]

# ---------- CLAIM ----------
# [Keep claim logic as-is]

# ---------- SYNC ----------
@bot.tree.command(name="sync")
async def sync(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Only admins can sync.", ephemeral=True)
    guild = discord.Object(id=GUILD_ID)
    await bot.tree.sync(guild=guild)
    await interaction.response.send_message("✅ Commands fully synced.", ephemeral=True)

# ---------- CLEAR COMMAND ----------
@bot.tree.command(name="clear")
async def clear(interaction: discord.Interaction):
    """Clears all guild commands before re-syncing"""
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Only admins can clear commands.", ephemeral=True)

    guild = discord.Object(id=GUILD_ID)
    commands_list = await bot.tree.fetch_commands(guild=guild)
    for cmd in commands_list:
        await bot.tree.delete_command(cmd.id, guild=guild)
    await interaction.response.send_message("✅ Cleared all guild commands.", ephemeral=True)

# ---------- ON READY ----------
@bot.event
async def on_ready():
    guild = discord.Object(id=GUILD_ID)
    await bot.tree.sync(guild=guild)  # auto-sync on startup
    print(f"Logged in as {bot.user} and synced commands to guild {GUILD_ID}")

bot.run(TOKEN)
