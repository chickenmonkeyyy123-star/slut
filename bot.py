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
        self.doubled = [False]
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
                f"{pointer}**Hand {i+1}:** {self.game.fmt(hand)} "
                f"(Value: {self.game.value(hand)}) | Bet: {self.game.bets[i]}\n"
            )
        dealer = (
            "?, " + f"{self.game.dealer[1]['r']}{self.game.dealer[1]['s']}"
            if hide_dealer else self.game.fmt(self.game.dealer)
        )
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
        embed = self.embed(hide_dealer=False)
        result = ""

        for i, hand in enumerate(self.game.hands):
            pv = self.game.value(hand)
            bet = self.game.bets[i]

            if pv > 21:
                u["balance"] -= bet
                u["blackjack"]["losses"] += 1
                result += f"❌ Hand {i+1} busted\n"
            elif dv > 21 or pv > dv:
                u["balance"] += bet
                u["blackjack"]["wins"] += 1
                result += f"✅ Hand {i+1} wins\n"
            elif pv < dv:
                u["balance"] -= bet
                u["blackjack"]["losses"] += 1
                result += f"❌ Hand {i+1} loses\n"
            else:
                result += f"➖ Hand {i+1} push\n"

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

# ---------- COINFLIP ----------
class CoinflipView(View):
    def __init__(self, challenger: discord.User, opponent: discord.User, amount: int, choice: str):
        super().__init__(timeout=60)
        self.challenger = challenger
        self.opponent = opponent
        self.amount = amount
        self.choice = choice.lower()
        self.result_sent = False

    @discord.ui.button(label="Accept Coinflip", style=discord.ButtonStyle.green)
    async def accept(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.opponent.id:
            return await interaction.response.send_message("You are not the opponent.", ephemeral=True)
        if self.result_sent:
            return
        flip_result = random.choice(["heads", "tails"])
        u = get_user(self.challenger.id)
        o = get_user(self.opponent.id)

        if flip_result == self.choice:
            u["balance"] += self.amount
            o["balance"] -= self.amount
            u["coinflip"]["wins"] += 1
            o["coinflip"]["losses"] += 1
            msg = f"🪙 **{flip_result.upper()}** — {self.challenger.mention} won **{self.amount}** dabloons!"
        else:
            u["balance"] -= self.amount
            o["balance"] += self.amount
            u["coinflip"]["losses"] += 1
            o["coinflip"]["wins"] += 1
            msg = f"🪙 **{flip_result.upper()}** — {self.opponent.mention} won **{self.amount}** dabloons!"

        save_data()
        self.result_sent = True
        self.stop()
        await interaction.response.edit_message(content=msg, view=None)

# ---------- COMMANDS ----------
# You can now continue with your /bj, /cf, /lb, /giveaway, /claim, /sync commands exactly as you had before
# All indentation in the Blackjack logic has been corrected.

# ---------- RUN BOT ----------
@bot.event
async def on_ready():
    guild = discord.Object(id=GUILD_ID)
    await bot.tree.sync(guild=guild)
    print(f"Logged in as {bot.user} and synced commands to guild {GUILD_ID}")

bot.run(TOKEN)
