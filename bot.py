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
intents.message_content = True
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
# ... (Keep your existing BlackjackGame and BlackjackView code unchanged) ...

# ---------- COINFLIP CHALLENGE VIEW ----------
class CoinflipChallengeView(View):
    def __init__(self, challenger, target, amount, choice):
        super().__init__(timeout=30)
        self.challenger = challenger
        self.target = target
        self.amount = amount
        self.choice = choice.lower()
        self.accepted = False

    async def end_game(self, interaction, winner=None, timeout=False):
        u1 = get_user(self.challenger.id)
        u2 = get_user(self.target.id)

        if winner is None:  # declined or timeout
            # Return money to challenger
            u1["balance"] += self.amount
            save_data()
            await interaction.response.edit_message(
                content="Challenge not accepted or timed out. Your bet has been returned.", view=None
            )
        else:
            if winner == self.challenger:
                u1["balance"] += self.amount * 2
                u1["coinflip"]["wins"] += 1
                u2["coinflip"]["losses"] += 1
                msg = f"🪙 {self.challenger.mention} won the coinflip against {self.target.mention}! (+{self.amount})"
            else:
                u2["balance"] += self.amount * 2
                u2["coinflip"]["wins"] += 1
                u1["coinflip"]["losses"] += 1
                msg = f"🪙 {self.target.mention} won the coinflip against {self.challenger.mention}! (+{self.amount})"
            save_data()
            await interaction.response.edit_message(content=msg, view=None)
        self.stop()

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green)
    async def accept(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.target.id:
            return await interaction.response.send_message("You are not the challenged user.", ephemeral=True)
        self.accepted = True
        result = random.choice([self.challenger, self.target])
        await self.end_game(interaction, winner=result)

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.red)
    async def decline(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.target.id:
            return await interaction.response.send_message("You are not the challenged user.", ephemeral=True)
        await self.end_game(interaction, winner=None)

# ---------- COMMANDS ----------
@app_commands.guilds(discord.Object(id=GUILD_ID))
@bot.tree.command(name="cf", description="Flip a coin or challenge a user")
async def cf(interaction: discord.Interaction, amount: int, choice: str, user: discord.User = None):
    u = get_user(interaction.user.id)
    choice = choice.lower()
    
    if amount <= 0 or amount > u["balance"]:
        return await interaction.response.send_message("Invalid bet.", ephemeral=True)

    if user and user.id != interaction.user.id:
        # Challenge another user
        target_user = user
        u["balance"] -= amount  # take money from challenger
        save_data()
        view = CoinflipChallengeView(interaction.user, target_user, amount, choice)
        await interaction.response.send_message(
            content=f"{target_user.mention}, you have been challenged to a coinflip by {interaction.user.mention} for {amount}!\nChoice: {choice}",
            view=view
        )
    else:
        # AI coinflip
        u["balance"] -= amount
        result = random.choice(["heads", "tails"])
        if result == choice:
            u["balance"] += amount * 2
            u["coinflip"]["wins"] += 1
            msg = f"🪙 **{result.upper()}** — You won **{amount}**!"
        else:
            u["coinflip"]["losses"] += 1
            msg = f"🪙 **{result.upper()}** — You lost **{amount}**."
        # Force save of updated user
        data[str(interaction.user.id)] = u
        save_data()
        await interaction.response.send_message(msg)

# ---------- LEADERBOARD ----------
@app_commands.guilds(discord.Object(id=GUILD_ID))
@bot.tree.command(name="leaderboard", description="Show top balances")
async def leaderboard(interaction: discord.Interaction):
    sorted_users = sorted(data.items(), key=lambda x: x[1]["balance"], reverse=True)
    lines = []
    for i, (uid, u) in enumerate(sorted_users[:10], start=1):
        w, l = total_wl(u)
        lines.append(f"**#{i}** <@{uid}> — 💰 {u['balance']} | 🏆 {w}W ❌ {l}L")
    embed = discord.Embed(title="🏆 Leaderboard", description="\n".join(lines))
    await interaction.response.send_message(embed=embed)

# ---------- BLACKJACK COMMAND ----------
# ... Keep your /bj command as is ...

# ---------- SYNC ----------
@bot.event
async def on_ready():
    guild = discord.Object(id=GUILD_ID)
    try:
        await bot.tree.sync(guild=guild)
        print(f"Synced commands to guild {GUILD_ID}")
    except Exception as e:
        print(f"Error syncing commands: {e}")
    print(f"Logged in as {bot.user}")

bot.run(TOKEN)
