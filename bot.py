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
MAX_CHICKEN_BET = 15000
MAX_LIMBO_MULTIPLIER = 100
GUILD_ID = 1332118870181412936
HOUSE_ID = "1464519481077399715"

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
            "chicken": {"wins": 0, "losses": 0},
            "limbo": {"wins": 0, "losses": 0},
        }
        save_data()
    return data[uid]

# ensure house exists
get_user(HOUSE_ID)

def house_transfer(amount):
    house = get_user(HOUSE_ID)
    house["balance"] += amount

def total_wl(u):
    return (
        sum(v.get("wins", 0) for v in u.values() if isinstance(v, dict)),
        sum(v.get("losses", 0) for v in u.values() if isinstance(v, dict)),
    )

# ---------- BLACKJACK ----------
class BlackjackGame:
    def __init__(self, bet):
        self.bet = bet
        self.deck = self.new_deck()
        random.shuffle(self.deck)
        self.player = [self.deck.pop(), self.deck.pop()]
        self.dealer = [self.deck.pop(), self.deck.pop()]
        self.finished = False

    def new_deck(self):
        suits = ["♠", "♥", "♦", "♣"]
        ranks = ["2","3","4","5","6","7","8","9","10","J","Q","K","A"]
        deck = []
        for s in suits:
            for r in ranks:
                v = 11 if r == "A" else 10 if r in ["J","Q","K"] else int(r)
                deck.append({"r": r, "s": s, "v": v})
        return deck

    def value(self, hand):
        total = sum(c["v"] for c in hand)
        aces = sum(1 for c in hand if c["r"] == "A")
        while total > 21 and aces:
            total -= 10
            aces -= 1
        return total

class BlackjackView(View):
    def __init__(self, game, user):
        super().__init__(timeout=60)
        self.game = game
        self.user = user

    def embed(self, reveal=False):
        dealer = "?, " + f"{self.game.dealer[1]['r']}{self.game.dealer[1]['s']}" if not reveal else ", ".join(
            f"{c['r']}{c['s']}" for c in self.game.dealer
        )
        return discord.Embed(
            title="🃏 Blackjack",
            description=(
                f"**Your Hand:** {', '.join(f'{c['r']}{c['s']}' for c in self.game.player)} "
                f"(Value {self.game.value(self.game.player)})\n"
                f"**Dealer:** {dealer}"
            ),
            color=discord.Color.blurple()
        )

    async def finish(self, interaction):
        while self.game.value(self.game.dealer) < 17:
            self.game.dealer.append(self.game.deck.pop())

        pv = self.game.value(self.game.player)
        dv = self.game.value(self.game.dealer)
        u = get_user(self.user.id)

        if pv > 21 or (dv <= 21 and dv > pv):
            u["balance"] -= self.game.bet
            u["blackjack"]["losses"] += 1
            house_transfer(self.game.bet)
            result = "❌ You lost"
        elif dv > 21 or pv > dv:
            u["balance"] += self.game.bet
            u["blackjack"]["wins"] += 1
            house_transfer(-self.game.bet)
            result = "✅ You won"
        else:
            result = "➖ Push"

        save_data()
        self.stop()
        await interaction.response.edit_message(
            embed=self.embed(reveal=True).add_field(name="Result", value=result),
            view=None
        )

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.green)
    async def hit(self, interaction: discord.Interaction, button: Button):
        self.game.player.append(self.game.deck.pop())
        if self.game.value(self.game.player) >= 21:
            await self.finish(interaction)
        else:
            await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.red)
    async def stand(self, interaction: discord.Interaction, button: Button):
        await self.finish(interaction)

@bot.tree.command(name="bj")
async def bj(interaction: discord.Interaction, amount: int):
    u = get_user(interaction.user.id)
    if amount <= 0 or amount > u["balance"]:
        return await interaction.response.send_message("Invalid bet.", ephemeral=True)
    view = BlackjackView(BlackjackGame(amount), interaction.user)
    await interaction.response.send_message(embed=view.embed(), view=view)

# ---------- COINFLIP ----------
@bot.tree.command(name="cf")
@app_commands.describe(amount="Bet", choice="heads or tails", user="Opponent (optional)")
async def cf(interaction: discord.Interaction, amount: int, choice: str, user: discord.User | None = None):
    choice = choice.lower()
    u = get_user(interaction.user.id)

    if choice not in ["heads", "tails"]:
        return await interaction.response.send_message("heads or tails only.", ephemeral=True)
    if amount <= 0 or amount > u["balance"]:
        return await interaction.response.send_message("Invalid bet.", ephemeral=True)

    flip = random.choice(["heads", "tails"])

    if not user:
        if flip == choice:
            u["balance"] += amount
            u["coinflip"]["wins"] += 1
            house_transfer(-amount)
            msg = f"🪙 **{flip.upper()}** — You won {amount}"
        else:
            u["balance"] -= amount
            u["coinflip"]["losses"] += 1
            house_transfer(amount)
            msg = f"🪙 **{flip.upper()}** — You lost {amount}"
        save_data()
        return await interaction.response.send_message(msg)

# ---------- LIMBO ----------
@bot.tree.command(name="limbo")
async def limbo(interaction: discord.Interaction, amount: int, multiplier: int):
    u = get_user(interaction.user.id)

    if amount <= 0 or amount > u["balance"]:
        return await interaction.response.send_message("Invalid bet.", ephemeral=True)
    if multiplier < 2 or multiplier > MAX_LIMBO_MULTIPLIER:
        return await interaction.response.send_message("Invalid multiplier.", ephemeral=True)

    if random.random() <= 1 / multiplier:
        profit = amount * (multiplier - 1)
        u["balance"] += profit
        u["limbo"]["wins"] += 1
        house_transfer(-profit)
        msg = f"🚀 WIN +{profit}"
    else:
        u["balance"] -= amount
        u["limbo"]["losses"] += 1
        house_transfer(amount)
        msg = f"💥 LOST -{amount}"

    save_data()
    await interaction.response.send_message(msg)

# ---------- CHICKEN ----------
@bot.tree.command(name="chicken")
async def chicken(interaction: discord.Interaction, amount: int):
    u = get_user(interaction.user.id)
    if amount <= 0 or amount > u["balance"]:
        return await interaction.response.send_message("Invalid bet.", ephemeral=True)

    crash = random.uniform(1.5, 6.0)
    mult = random.uniform(1.0, crash)

    if mult < crash:
        win = int(amount * mult)
        u["balance"] += win
        u["chicken"]["wins"] += 1
        house_transfer(-win)
        msg = f"🐔 Cashed out at {mult:.2f}x — +{win}"
    else:
        u["balance"] -= amount
        u["chicken"]["losses"] += 1
        house_transfer(amount)
        msg = f"💥 Crashed — -{amount}"

    save_data()
    await interaction.response.send_message(msg)

# ---------- TIP ----------
@bot.tree.command(name="tip")
async def tip(interaction: discord.Interaction, amount: int, user: discord.User):
    sender = get_user(interaction.user.id)
    receiver = get_user(user.id)

    if amount <= 0 or sender["balance"] < amount:
        return await interaction.response.send_message("Invalid amount.", ephemeral=True)

    sender["balance"] -= amount
    receiver["balance"] += amount
    save_data()

    await interaction.response.send_message(
        f"💸 {interaction.user.mention} tipped {user.mention} {amount} dabloons"
    )

# ---------- LEADERBOARD ----------
@bot.tree.command(name="lb")
async def lb(interaction: discord.Interaction):
    sorted_users = sorted(data.items(), key=lambda x: x[1]["balance"], reverse=True)
    lines = []
    for i, (uid, u) in enumerate(sorted_users[:10], start=1):
        w, l = total_wl(u)
        lines.append(f"**#{i}** <@{uid}> — 💰 {u['balance']} | 🏆 {w} ❌ {l}")
    await interaction.response.send_message(
        embed=discord.Embed(title="🏆 Leaderboard", description="\n".join(lines))
    )

# ---------- READY ----------
@bot.event
async def on_ready():
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"Logged in as {bot.user}")

bot.run(TOKEN)
