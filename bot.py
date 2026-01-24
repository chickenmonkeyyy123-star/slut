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
        }
        save_data()
    return data[uid]

def total_wl(u):
    return (
        u["blackjack"]["wins"] + u["coinflip"]["wins"],
        u["blackjack"]["losses"] + u["coinflip"]["losses"],
    )

# ---------- BLACKJACK ----------
class BlackjackGame:
    def __init__(self, bet):
        self.bet = bet
        self.deck = self.new_deck()
        random.shuffle(self.deck)
        self.player = [self.deck.pop(), self.deck.pop()]
        self.dealer = [self.deck.pop(), self.deck.pop()]

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

    def hit(self):
        self.player.append(self.deck.pop())
        return self.value(self.player) > 21

    def stand(self):
        while self.value(self.dealer) < 17:
            self.dealer.append(self.deck.pop())

    def fmt(self, hand, hide=False):
        if hide:
            return "?, " + f"{hand[1]['r']}{hand[1]['s']}"
        return ", ".join(f"{c['r']}{c['s']}" for c in hand)

class BlackjackView(View):
    def __init__(self, game, user):
        super().__init__(timeout=60)
        self.game = game
        self.user = user

    def embed(self, hide):
        return discord.Embed(
            title="🃏 Blackjack",
            description=(
                f"**Your hand:** {self.game.fmt(self.game.player)} "
                f"(Value: {self.game.value(self.game.player)})\n"
                f"**Dealer:** {self.game.fmt(self.game.dealer, hide)}"
            ),
            color=discord.Color.blurple()
        )

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.green)
    async def hit(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Not your game.", ephemeral=True)
        bust = self.game.hit()
        embed = self.embed(True)
        if bust:
            embed.color = discord.Color.red()
            embed.description += "\n\n💥 **Bust! You lose.**"
            u = get_user(self.user.id)
            u["balance"] -= self.game.bet
            u["blackjack"]["losses"] += 1
            save_data()
            self.stop()
            await interaction.response.edit_message(embed=embed, view=None)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.red)
    async def stand(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Not your game.", ephemeral=True)
        self.game.stand()
        pv = self.game.value(self.game.player)
        dv = self.game.value(self.game.dealer)
        embed = self.embed(False)
        u = get_user(self.user.id)
        if dv > 21 or pv > dv:
            embed.color = discord.Color.green()
            embed.description += "\n\n✅ **You win!**"
            u["balance"] += self.game.bet
            u["blackjack"]["wins"] += 1
        elif pv < dv:
            embed.color = discord.Color.red()
            embed.description += "\n\n❌ **Dealer wins.**"
            u["balance"] -= self.game.bet
            u["blackjack"]["losses"] += 1
        else:
            embed.description += "\n\n➖ **Push (tie).**"
        save_data()
        self.stop()
        await interaction.response.edit_message(embed=embed, view=None)

# ---------- COMMANDS ----------
@bot.tree.command(name="bj")
async def bj(interaction: discord.Interaction, amount: int):
    u = get_user(interaction.user.id)
    if amount <= 0 or amount > u["balance"]:
        return await interaction.response.send_message("Invalid bet.", ephemeral=True)
    game = BlackjackGame(amount)
    view = BlackjackView(game, interaction.user)
    await interaction.response.send_message(embed=view.embed(True), view=view)

@bot.tree.command(name="tip")
@app_commands.describe(amount="Amount to tip", user="User to tip")
async def tip(interaction: discord.Interaction, amount: int, user: discord.Member):
    sender = get_user(interaction.user.id)
    receiver = get_user(user.id)

    if user.id == interaction.user.id:
        return await interaction.response.send_message("❌ You can’t tip yourself.", ephemeral=True)

    if amount <= 0:
        return await interaction.response.send_message("❌ Tip amount must be positive.", ephemeral=True)

    if sender["balance"] < amount:
        return await interaction.response.send_message("❌ You don’t have enough dabloons.", ephemeral=True)

    sender["balance"] -= amount
    receiver["balance"] += amount
    save_data()

    await interaction.response.send_message(
        f"💸 {interaction.user.mention} tipped **{amount} dabloons** to {user.mention}!"
    )

@bot.tree.command(name="sync")
async def sync(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Admins only.", ephemeral=True)
    guild = discord.Object(id=GUILD_ID)
    await bot.tree.sync(guild=guild)
    await interaction.response.send_message("✅ Commands synced.", ephemeral=True)

# ---------- READY ----------
@bot.event
async def on_ready():
    guild = discord.Object(id=GUILD_ID)
    await bot.tree.sync(guild=guild)
    print(f"Logged in as {bot.user} and synced commands to guild {GUILD_ID}")

bot.run(TOKEN)
