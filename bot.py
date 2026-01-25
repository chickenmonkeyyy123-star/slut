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
                u["blackjack"]["losses"] += 1
                result += f"❌ Hand {i+1} busted\n"
            elif dv > 21 or pv > dv:
                u["balance"] += bet * 2
                u["blackjack"]["wins"] += 1
                result += f"✅ Hand {i+1} wins (+{bet})\n"
            elif pv < dv:
                u["blackjack"]["losses"] += 1
                result += f"❌ Hand {i+1} loses\n"
            else:
                u["balance"] += bet
                result += f"➖ Hand {i+1} push (bet returned)\n"

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

# ---------- COINFLIP CHALLENGE VIEW ----------
class CoinflipChallengeView(View):
    def __init__(self, challenger, target, amount, choice):
        super().__init__(timeout=30)
        self.challenger = challenger
        self.target = target
        self.amount = amount
        self.choice = choice.lower()
        self.accepted = False

        # Take money from both users immediately
        u1 = get_user(self.challenger.id)
        u2 = get_user(self.target.id)

        if u1["balance"] < amount:
            raise ValueError("Challenger does not have enough balance.")
        if u2["balance"] < amount:
            raise ValueError("Target does not have enough balance.")

        u1["balance"] -= amount
        u2["balance"] -= amount
        save_data()

    async def end_game(self, interaction, winner=None):
        u1 = get_user(self.challenger.id)
        u2 = get_user(self.target.id)

        if winner is None:  # declined or timeout
            u1["balance"] += self.amount
            u2["balance"] += self.amount
            await interaction.response.edit_message(content="Challenge not accepted in time.", view=None)
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

            await interaction.response.edit_message(content=msg, view=None)

        save_data()
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
@bot.tree.command(name="bj", description="Play blackjack")
async def bj(interaction: discord.Interaction, amount: int):
    u = get_user(interaction.user.id)
    if amount <= 0 or amount > u["balance"]:
        return await interaction.response.send_message("Invalid bet.", ephemeral=True)

    u["balance"] -= amount  # take money immediately
    save_data()

    game = BlackjackGame(amount)
    view = BlackjackView(game, interaction.user)
    await interaction.response.send_message(embed=view.embed(), view=view)

@app_commands.guilds(discord.Object(id=GUILD_ID))
@bot.tree.command(name="cf", description="Flip a coin or challenge a user")
async def cf(interaction: discord.Interaction, amount: int, choice: str, user: discord.User = None):
    u = get_user(interaction.user.id)
    if amount <= 0 or amount > u["balance"]:
        return await interaction.response.send_message("Invalid bet.", ephemeral=True)

    if user and user.id != interaction.user.id:
        # Challenge another user
        target_user = user
        v = CoinflipChallengeView(interaction.user, target_user, amount, choice)
        u["balance"] -= amount  # take money from challenger
        save_data()
        await interaction.response.send_message(
            content=f"{target_user.mention}, you have been challenged to a coinflip by {interaction.user.mention} for {amount}!\nChoice: {choice}",
            view=v
        )
    else:
        # Play against AI
        u["balance"] -= amount
        result = random.choice(["heads", "tails"])
        if result == choice.lower():
            u["balance"] += amount * 2
            u["coinflip"]["wins"] += 1
            msg = f"🪙 **{result.upper()}** — You won **{amount}**!"
        else:
            u["coinflip"]["losses"] += 1
            msg = f"🪙 **{result.upper()}** — You lost **{amount}**."
        save_data()
        await interaction.response.send_message(msg)

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

