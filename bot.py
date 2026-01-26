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
GUILD_ID = 1332118870181412936

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
            "timeout": None  # <--- timeout field
        }
        save_data()
    return data[uid]

def total_wl(u):
    return (
        u["blackjack"]["wins"] + u["coinflip"]["wins"],
        u["blackjack"]["losses"] + u["coinflip"]["losses"],
    )

# ---------- CHECK TIMEOUT ----------
def is_timed_out(uid):
    u = get_user(uid)
    if u.get("timeout"):
        timeout_end = datetime.fromisoformat(u["timeout"])
        if datetime.utcnow() < timeout_end:
            return True, (timeout_end - datetime.utcnow())
        else:
            # Timeout expired
            u["timeout"] = None
            save_data()
    return False, None

# ---------- BLACKJACK & COINFLIP (same as your code) ----------
# ... keep all BlackjackGame, BlackjackView, CoinflipView code unchanged ...

# For example, before letting user play, check timeout:
async def check_timeout(interaction: discord.Interaction):
    timed_out, remaining = is_timed_out(interaction.user.id)
    if timed_out:
        minutes, seconds = divmod(int(remaining.total_seconds()), 60)
        await interaction.response.send_message(
            f"⏳ You are timed out from gambling commands for another {minutes}m {seconds}s.",
            ephemeral=True
        )
        return True
    return False

# Example usage in /bj
@bot.tree.command(name="bj")
async def bj(interaction: discord.Interaction, amount: int):
    if await check_timeout(interaction):
        return
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
    if await check_timeout(interaction):
        return
    # ... rest of /cf code unchanged ...

# ---------- LEADERBOARD ----------
@bot.tree.command(name="leaderboard")
async def leaderboard(interaction: discord.Interaction):
    if not data:
        return await interaction.response.send_message("No data yet.")
    sorted_users = sorted(data.items(), key=lambda x: x[1]["balance"], reverse=True)
    lines = []
    for i, (uid, u) in enumerate(sorted_users[:10], start=1):
        w, l = total_wl(u)
        lines.append(f"**#{i}** <@{uid}> — 💰 {u['balance']} | 🏆 {w}W ❌ {l}L")
    embed = discord.Embed(
        title="🏆 Leaderboard",
        description="\n".join(lines),
        color=discord.Color.gold()
    )
    await interaction.response.send_message(embed=embed)

# ---------- TIMEOUT COMMAND ----------
@bot.tree.command(name="timeout")
@app_commands.describe(
    user="User to timeout",
    length="Length of timeout in hours"
)
async def timeout(interaction: discord.Interaction, user: discord.User, length: float):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Only admins can timeout users.", ephemeral=True)
    if length <= 0:
        return await interaction.response.send_message("❌ Timeout length must be positive.", ephemeral=True)

    u = get_user(user.id)
    timeout_end = datetime.utcnow() + timedelta(hours=length)
    u["timeout"] = timeout_end.isoformat()
    save_data()
    await interaction.response.send_message(
        f"⏱️ {user.mention} has been timed out from gambling commands for {length} hours.",
        ephemeral=False
    )

# ---------- SYNC ----------
@bot.tree.command(name="sync")
async def sync(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Only admins can sync commands.", ephemeral=True)
    guild = discord.Object(id=GUILD_ID)
    await bot.tree.sync(guild=guild)
    await interaction.response.send_message("✅ Commands fully synced.", ephemeral=True)

# ---------- READY ----------
@bot.event
async def on_ready():
    guild = discord.Object(id=GUILD_ID)
    await bot.tree.sync(guild=guild)
    print(f"Logged in as {bot.user} — Commands synced to guild {GUILD_ID}")

bot.run(TOKEN)
