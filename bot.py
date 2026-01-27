import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button

import random
import json
import os
import asyncio

from dotenv import load_dotenv
from datetime import datetime, timedelta

# ---------- LOAD .ENV ----------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN not found in .env")

# ---------- CONFIG ----------
DATA_FILE = "dabloon_data.json"
MAX_LIMBO_MULTIPLIER = 100
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
            "limbo": {"wins": 0, "losses": 0},
        }
        save_data()
        return data[uid]

    u = data[uid]

    # ---- BACKFILL MISSING STATS FOR OLD USERS ----
    u.setdefault("balance", START_BALANCE)
    u.setdefault("blackjack", {"wins": 0, "losses": 0})
    u.setdefault("coinflip", {"wins": 0, "losses": 0})
    u.setdefault("limbo", {"wins": 0, "losses": 0})

    save_data()
    return u

def total_wl(u):
    return (
        u.get("blackjack", {}).get("wins", 0)
        + u.get("coinflip", {}).get("wins", 0)
        + u.get("limbo", {}).get("wins", 0),
        u.get("blackjack", {}).get("losses", 0)
        + u.get("coinflip", {}).get("losses", 0)
        + u.get("limbo", {}).get("losses", 0),
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
        self.doubled = [False]
        self.active_hand = 0

        self.dealer = [self.deck.pop(), self.deck.pop()]

    def new_deck(self):
        suits = ["♠", "♥", "♦", "♣"]
        ranks = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
        deck = []

        for s in suits:
            for r in ranks:
                value = 11 if r == "A" else 10 if r in ["J", "Q", "K"] else int(r)
                deck.append({"r": r, "s": s, "v": value})

        return deck

    def value(self, hand):
        total = sum(c["v"] for c in hand)
        aces = sum(1 for c in hand if c["r"] == "A")

        while total > 21 and aces:
            total -= 10
            aces -= 1

        return total

    def can_split(self):
        hand = self.hands[self.active_hand]
        return len(hand) == 2 and hand[0]["r"] == hand[1]["r"]

    def split(self):
        h = self.hands[self.active_hand]
        c1, c2 = h

        self.hands[self.active_hand] = [c1, self.deck.pop()]
        self.hands.insert(self.active_hand + 1, [c2, self.deck.pop()])

        self.bets.insert(self.active_hand + 1, self.base_bet)
        self.finished.insert(self.active_hand + 1, False)
        self.doubled.insert(self.active_hand + 1, False)

    def hit(self):
        hand = self.hands[self.active_hand]
        hand.append(self.deck.pop())

        if self.value(hand) > 21:
            self.finished[self.active_hand] = True

    def stand(self):
        self.finished[self.active_hand] = True

    def double(self):
        self.bets[self.active_hand] *= 2
        self.doubled[self.active_hand] = True
        self.hit()
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
            desc += (
                f"{pointer}**Hand {i + 1}:** {self.game.fmt(hand)} "
                f"(Value: {self.game.value(hand)}) | Bet: {self.game.bets[i]}\n"
            )

        dealer = (
            "?, " + f"{self.game.dealer[1]['r']}{self.game.dealer[1]['s']}"
            if hide_dealer
            else self.game.fmt(self.game.dealer)
        )

        return discord.Embed(
            title="🃏 Blackjack",
            description=f"{desc}\n**Dealer:** {dealer}",
            color=discord.Color.blurple(),
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

        embed = self.embed(hide_dealer=False)
        result = ""

        for i, hand in enumerate(self.game.hands):
            pv = self.game.value(hand)
            bet = self.game.bets[i]

            if pv > 21:
                u["balance"] -= bet
                u["blackjack"]["losses"] += 1
                result += f"❌ Hand {i + 1} busted\n"
            elif dv > 21 or pv > dv:
                u["balance"] += bet
                u["blackjack"]["wins"] += 1
                result += f"✅ Hand {i + 1} wins\n"
            elif pv < dv:
                u["balance"] -= bet
                u["blackjack"]["losses"] += 1
                result += f"❌ Hand {i + 1} loses\n"
            else:
                result += f"➖ Hand {i + 1} push\n"

        embed.description += "\n" + result
        save_data()
        self.stop()
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.green)
    async def hit(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Not your game.", ephemeral=True)
        self.game.hit()
        await self.advance(interaction)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.red)
    async def stand(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Not your game.", ephemeral=True)
        self.game.stand()
        await self.advance(interaction)

    @discord.ui.button(label="Double", style=discord.ButtonStyle.blurple)
    async def double(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Not your game.", ephemeral=True)

        u = get_user(self.user.id)
        bet = self.game.bets[self.game.active_hand]

        if u["balance"] < bet:
            return await interaction.response.send_message("Not enough balance to double.", ephemeral=True)

        self.game.double()
        await self.advance(interaction)

    @discord.ui.button(label="Split", style=discord.ButtonStyle.gray)
    async def split(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Not your game.", ephemeral=True)

        if not self.game.can_split():
            return await interaction.response.send_message("You can't split this hand.", ephemeral=True)

        u = get_user(self.user.id)

        if u["balance"] < self.game.base_bet:
            return await interaction.response.send_message("Not enough balance to split.", ephemeral=True)

        self.game.split()
        await interaction.response.edit_message(embed=self.embed(), view=self)

# ---------- CHICKEN GAME (MANUAL BOOST) ----------
class ChickenGame:
    def __init__(self, bet):
        self.bet = bet
        self.multiplier = 1
        self.crash = random.randint(10, 100) / 10  # 1.0x–10.0x
        self.finished = False

    def boost(self):
        if self.finished:
            return False
        self.multiplier += 0.1
        if self.multiplier >= self.crash:
            self.finished = True
            return False
        return True

    def cashout(self):
        self.finished = True
        return self.bet * self.multiplier

class ChickenView(View):
    def __init__(self, game, user):
        super().__init__(timeout=60)
        self.game = game
        self.user = user
        self.active = True

    def embed(self):
        return discord.Embed(
            title="🐔 Chicken Game",
            description=(
                f"💰 Bet: {self.game.bet}\n"
                f"🚀 Multiplier: {self.game.multiplier:.1f}x\n"
                f"⚠️ Crash at: ???"
            ),
            color=discord.Color.orange(),
        )

    @discord.ui.button(label="⬆️ Boost", style=discord.ButtonStyle.green)
    async def boost(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Not your game!", ephemeral=True)
        if not self.active:
            return

        alive = self.game.boost()
        if alive:
            await interaction.response.edit_message(embed=self.embed(), view=self)
        else:
            # Crashed
            u = get_user(self.user.id)
            u["balance"] -= self.game.bet
            u.setdefault("chicken", {"wins": 0, "losses": 0})
            u["chicken"]["losses"] += 1
            save_data()
            self.active = False
            self.stop()
            await interaction.response.edit_message(
                content=f"💥 Chicken crashed at **{self.game.multiplier:.1f}x**! You lost **{self.game.bet} dabloons**.",
                embed=None, view=None
            )

    @discord.ui.button(label="💰 Cash Out", style=discord.ButtonStyle.blurple)
    async def cashout(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Not your game!", ephemeral=True)
        if not self.active:
            return

        winnings = self.game.cashout()
        u = get_user(self.user.id)
        u["balance"] += int(winnings)
        u.setdefault("chicken", {"wins": 0, "losses": 0})
        u["chicken"]["wins"] += 1
        save_data()

        self.active = False
        self.stop()
        await interaction.response.edit_message(
            content=f"🏆 You cashed out at **{self.game.multiplier:.1f}x** and won **{int(winnings)} dabloons!**",
            embed=None, view=None
        )

# ---------- LIMBO ----------
@bot.tree.command(name="limbo", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    amount="Bet amount",
    multiplier="Target multiplier (2–100)",
)
async def limbo(interaction: discord.Interaction, amount: int, multiplier: int):
    u = get_user(interaction.user.id)

    if amount <= 0 or amount > u["balance"]:
        return await interaction.response.send_message(
            "❌ Invalid bet amount.", ephemeral=True
        )

    if multiplier < 2 or multiplier > MAX_LIMBO_MULTIPLIER:
        return await interaction.response.send_message(
            f"❌ Multiplier must be between **2x** and **{MAX_LIMBO_MULTIPLIER}x**.",
            ephemeral=True,
        )

    win_chance = 1 / multiplier
    roll = random.random()

    if roll <= win_chance:
        profit = amount * (multiplier - 1)
        u["balance"] += profit
        u["limbo"]["wins"] += 1
        msg = (
            f"🚀 **LIMBO WIN!**\n"
            f"🎯 Target: **{multiplier}x**\n"
            f"💰 Profit: **+{profit} dabloons**"
        )
    else:
        u["balance"] -= amount
        u["limbo"]["losses"] += 1
        msg = (
            f"💥 **LIMBO CRASHED!**\n"
            f"🎯 Target: **{multiplier}x**\n"
            f"💸 Lost: **-{amount} dabloons**"
        )

    save_data()
    await interaction.response.send_message(msg)

# ---------- CHICKEN COMMAND ----------
@bot.tree.command(name="chicken", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(amount="Bet amount")
async def chicken(interaction: discord.Interaction, amount: int):
    u = get_user(interaction.user.id)

    if amount <= 0 or amount > u["balance"]:
        return await interaction.response.send_message(
            "❌ Invalid bet.", ephemeral=True
        )

    game = ChickenGame(amount)
    view = ChickenView(game, interaction.user)
    await interaction.response.send_message(embed=view.embed(), view=view)

# ---------- OTHER COMMANDS OMITTED FOR BREVITY ----------
# Keep all other code (coinflip, blackjack, claim, giveaway, leaderboard, sync, ready) unchanged

# ---------- RUN BOT ----------
bot.run(TOKEN)
