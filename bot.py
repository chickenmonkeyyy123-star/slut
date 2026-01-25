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
        self.base_bet = bet
        self.deck = self.new_deck()
        random.shuffle(self.deck)
        self.hands = [[self.deck.pop(), self.deck.pop()]]
        self.bets = [bet]
        self.finished = [False]
        self.active_hand = 0
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
        self.hands[self.active_hand].append(self.deck.pop())
        if self.value(self.hands[self.active_hand]) > 21:
            self.finished[self.active_hand] = True

    def stand(self):
        self.finished[self.active_hand] = True

    def next_hand(self):
        while self.active_hand < len(self.hands) and self.finished[self.active_hand]:
            self.active_hand += 1

    def dealer_play(self):
        while self.value(self.dealer) < 17:
            self.dealer.append(self.deck.pop())

    def fmt(self, hand):
        return ", ".join(f"{c['r']}{c['s']}" for c in hand)

class BlackjackView(View):
    def __init__(self, game, user):
        super().__init__(timeout=90)
        self.game = game
        self.user = user

    def embed(self, hide_dealer=True):
        desc = ""
        for i, hand in enumerate(self.game.hands):
            pointer = "➡️ " if i == self.game.active_hand else ""
            desc += f"{pointer}**Hand {i+1}:** {self.game.fmt(hand)} ({self.game.value(hand)}) | Bet: {self.game.bets[i]}\n"

        dealer = "?, ?" if hide_dealer else self.game.fmt(self.game.dealer)
        return discord.Embed(
            title="🃏 Blackjack",
            description=f"{desc}\n**Dealer:** {dealer}",
            color=discord.Color.blurple()
        )

    async def end_game(self, interaction):
        self.game.dealer_play()
        dv = self.game.value(self.game.dealer)
        u = get_user(self.user.id)

        result = ""
        for i, hand in enumerate(self.game.hands):
            pv = self.game.value(hand)
            bet = self.game.bets[i]
            if pv > 21 or (dv <= 21 and pv < dv):
                u["balance"] -= bet
                u["blackjack"]["losses"] += 1
                result += f"❌ Hand {i+1} lost\n"
            elif pv > dv or dv > 21:
                u["balance"] += bet
                u["blackjack"]["wins"] += 1
                result += f"✅ Hand {i+1} won\n"
            else:
                result += f"➖ Hand {i+1} push\n"

        save_data()
        embed = self.embed(False)
        embed.description += f"\n{result}\n💰 **New balance:** {u['balance']}"
        self.stop()
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.green)
    async def hit(self, interaction: discord.Interaction, _):
        if interaction.user.id != self.user.id:
            return
        self.game.hit()
        self.game.next_hand()
        if self.game.active_hand >= len(self.game.hands):
            await self.end_game(interaction)
        else:
            await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.red)
    async def stand(self, interaction: discord.Interaction, _):
        if interaction.user.id != self.user.id:
            return
        self.game.stand()
        self.game.next_hand()
        if self.game.active_hand >= len(self.game.hands):
            await self.end_game(interaction)
        else:
            await interaction.response.edit_message(embed=self.embed(), view=self)

# ---------- COINFLIP ----------
class CoinflipView(View):
    def __init__(self, a, b, amount):
        super().__init__(timeout=60)
        self.a = a
        self.b = b
        self.amount = amount

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green)
    async def accept(self, interaction: discord.Interaction, _):
        if interaction.user.id != self.b.id:
            return

        u1 = get_user(self.a.id)
        u2 = get_user(self.b.id)

        if u1["balance"] < self.amount or u2["balance"] < self.amount:
            return await interaction.response.edit_message("❌ Not enough balance.", view=None)

        u1["balance"] -= self.amount
        u2["balance"] -= self.amount

        winner = random.choice([self.a.id, self.b.id])
        if winner == self.a.id:
            u1["balance"] += self.amount * 2
            u1["coinflip"]["wins"] += 1
            u2["coinflip"]["losses"] += 1
            msg = f"🪙 {self.a.mention} wins!\n💰 New balance: {u1['balance']}"
        else:
            u2["balance"] += self.amount * 2
            u2["coinflip"]["wins"] += 1
            u1["coinflip"]["losses"] += 1
            msg = f"🪙 {self.b.mention} wins!\n💰 New balance: {u2['balance']}"

        save_data()
        self.stop()
        await interaction.response.edit_message(content=msg, view=None)

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
async def cf(interaction: discord.Interaction, amount: int, user: discord.User | None = None):
    u = get_user(interaction.user.id)
    if amount <= 0 or amount > u["balance"]:
        return await interaction.response.send_message("Invalid bet.", ephemeral=True)

    if not user:
        result = random.choice(["heads", "tails"])
        if random.choice([True, False]):
            u["balance"] += amount
            u["coinflip"]["wins"] += 1
            msg = f"🪙 You won!\n💰 New balance: {u['balance']}"
        else:
            u["balance"] -= amount
            u["coinflip"]["losses"] += 1
            msg = f"🪙 You lost.\n💰 New balance: {u['balance']}"
        save_data()
        return await interaction.response.send_message(msg)

    view = CoinflipView(interaction.user, user, amount)
    await interaction.response.send_message(
        f"🪙 {interaction.user.mention} challenged {user.mention} for **{amount}** dabloons!",
        view=view
    )

@bot.tree.command(name="leaderboard")
async def leaderboard(interaction: discord.Interaction):
    sorted_users = sorted(data.items(), key=lambda x: x[1]["balance"], reverse=True)[:10]
    lines = []
    for i, (uid, u) in enumerate(sorted_users, 1):
        w, l = total_wl(u)
        lines.append(f"**#{i}** <@{uid}> — 💰 {u['balance']} | 🏆 {w}W ❌ {l}L")
    await interaction.response.send_message(
        embed=discord.Embed(title="🏆 Leaderboard", description="\n".join(lines))
    )

@bot.tree.command(name="sync")
async def sync(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Admin only.", ephemeral=True)
    await bot.tree.sync()
    await interaction.response.send_message("✅ Commands synced globally.", ephemeral=True)

# ---------- READY ----------
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")

bot.run(TOKEN)
