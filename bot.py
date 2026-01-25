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
            desc += f"{pointer}**Hand {i+1}:** {self.game.fmt(hand)} (Value: {self.game.value(hand)})\n"

        dealer = "?, " + f"{self.game.dealer[1]['r']}{self.game.dealer[1]['s']}" if hide_dealer else self.game.fmt(self.game.dealer)
        return discord.Embed(
            title="🃏 Blackjack",
            description=f"{desc}\n**Dealer:** {dealer}",
            color=discord.Color.blurple()
        )

    async def advance(self, interaction):
        self.game.next_hand()
        if self.game.active_hand >= len(self.game.hands):
            await self.end_game(interaction)
        else:
            await interaction.response.edit_message(embed=self.embed(), view=self)

    async def end_game(self, interaction):
        self.game.dealer_play()
        dv = self.game.value(self.game.dealer)
        u = get_user(self.user.id)
        embed = self.embed(False)
        result = ""

        for hand in self.game.hands:
            pv = self.game.value(hand)
            if pv > 21 or pv < dv <= 21:
                u["balance"] -= self.game.base_bet
                u["blackjack"]["losses"] += 1
                result += "❌ Loss\n"
            elif pv > dv or dv > 21:
                u["balance"] += self.game.base_bet
                u["blackjack"]["wins"] += 1
                result += "✅ Win\n"
            else:
                result += "➖ Push\n"

        embed.description += "\n" + result
        save_data()
        self.stop()
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.green)
    async def hit(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user.id:
            return
        self.game.hit()
        await self.advance(interaction)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.red)
    async def stand(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user.id:
            return
        self.game.stand()
        await self.advance(interaction)

# ---------- COINFLIP PvP ----------
class CoinflipView(View):
    def __init__(self, challenger, opponent, amount):
        super().__init__(timeout=60)
        self.challenger = challenger
        self.opponent = opponent
        self.amount = amount

    @discord.ui.button(label="Accept Coinflip", style=discord.ButtonStyle.green)
    async def accept(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.opponent.id:
            return await interaction.response.send_message("Not for you.", ephemeral=True)

        u1 = get_user(self.challenger.id)
        u2 = get_user(self.opponent.id)

        if u1["balance"] < self.amount or u2["balance"] < self.amount:
            return await interaction.response.edit_message("❌ Someone lacks balance.", view=None)

        u1["balance"] -= self.amount
        u2["balance"] -= self.amount

        winner = random.choice([self.challenger.id, self.opponent.id])
        if winner == self.challenger.id:
            u1["balance"] += self.amount * 2
            u1["coinflip"]["wins"] += 1
            u2["coinflip"]["losses"] += 1
            msg = f"🪙 {self.challenger.mention} WON **{self.amount*2}**"
        else:
            u2["balance"] += self.amount * 2
            u2["coinflip"]["wins"] += 1
            u1["coinflip"]["losses"] += 1
            msg = f"🪙 {self.opponent.mention} WON **{self.amount*2}**"

        save_data()
        self.stop()
        await interaction.response.edit_message(msg, view=None)

# ---------- COMMANDS ----------
@bot.tree.command(name="bj")
async def bj(interaction: discord.Interaction, amount: int):
    u = get_user(interaction.user.id)
    if amount <= 0 or amount > u["balance"]:
        return await interaction.response.send_message("Invalid bet.", ephemeral=True)
    game = BlackjackGame(amount)
    await interaction.response.send_message(embed=BlackjackView(game, interaction.user).embed(), view=BlackjackView(game, interaction.user))

@bot.tree.command(name="cf")
async def cf(
    interaction: discord.Interaction,
    amount: int,
    choice: str,
    user: discord.User | None = None
):
    choice = choice.lower()
    u = get_user(interaction.user.id)

    if choice not in ["heads", "tails"]:
        return await interaction.response.send_message("heads or tails only.", ephemeral=True)
    if amount <= 0 or amount > u["balance"]:
        return await interaction.response.send_message("Invalid bet.", ephemeral=True)

    if user is None:
        result = random.choice(["heads", "tails"])
        if result == choice:
            u["balance"] += amount
            u["coinflip"]["wins"] += 1
            msg = f"🪙 **{result.upper()}** — You won {amount}\n💰 Balance: {u['balance']}"
        else:
            u["balance"] -= amount
            u["coinflip"]["losses"] += 1
            msg = f"🪙 **{result.upper()}** — You lost {amount}\n💰 Balance: {u['balance']}"
        save_data()
        return await interaction.response.send_message(msg)

    if user.id == interaction.user.id:
        return await interaction.response.send_message("You can't coinflip yourself.", ephemeral=True)

    opp = get_user(user.id)
    if opp["balance"] < amount:
        return await interaction.response.send_message("Opponent lacks balance.", ephemeral=True)

    view = CoinflipView(interaction.user, user, amount)
    await interaction.response.send_message(
        f"🪙 **Coinflip Challenge**\n{interaction.user.mention} vs {user.mention}\nBet: {amount}",
        view=view
    )

# ---------- LEADERBOARD ----------
@bot.tree.command(name="leaderboard")
async def leaderboard(interaction: discord.Interaction):
    sorted_users = sorted(data.items(), key=lambda x: x[1]["balance"], reverse=True)
    lines = []
    for i, (uid, u) in enumerate(sorted_users[:10], start=1):
        w, l = total_wl(u)
        lines.append(f"**#{i}** <@{uid}> — 💰 {u['balance']} | 🏆 {w}W ❌ {l}L")
    await interaction.response.send_message(embed=discord.Embed(title="🏆 Leaderboard", description="\n".join(lines)))

# ---------- READY ----------
@bot.event
async def on_ready():
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    print(f"✅ Logged in as {bot.user} | Commands synced")

bot.run(TOKEN)
