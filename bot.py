import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
import random
import json
import os
from dotenv import load_dotenv

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

# ---------- COINFLIP VIEW ----------
class CoinflipView(View):
    def __init__(self, initiator, opponent, bet, choice):
        super().__init__(timeout=60)
        self.initiator = initiator
        self.opponent = opponent
        self.bet = bet
        self.choice = choice

    @discord.ui.button(label="Accept Coinflip", style=discord.ButtonStyle.green)
    async def accept(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.opponent.id:
            return await interaction.response.send_message("This isn't for you.", ephemeral=True)

        u1 = get_user(self.initiator.id)
        u2 = get_user(self.opponent.id)

        if u2["balance"] < self.bet:
            return await interaction.response.send_message("You don't have enough balance.", ephemeral=True)

        result = random.choice(["heads", "tails"])
        self.stop()

        if result == self.choice:
            u1["balance"] += self.bet
            u2["balance"] -= self.bet
            u1["coinflip"]["wins"] += 1
            u2["coinflip"]["losses"] += 1
            winner = self.initiator
        else:
            u2["balance"] += self.bet
            u1["balance"] -= self.bet
            u2["coinflip"]["wins"] += 1
            u1["coinflip"]["losses"] += 1
            winner = self.opponent

        save_data()

        await interaction.response.edit_message(
            content=f"🪙 **{result.upper()}**\n🏆 {winner.mention} won **{self.bet} dabloons**",
            view=None
        )

# ---------- COMMANDS ----------
@bot.tree.command(name="bj")
async def bj(interaction: discord.Interaction, amount: int):
    u = get_user(interaction.user.id)
    if amount <= 0 or amount > u["balance"]:
        return await interaction.response.send_message("Invalid bet.", ephemeral=True)

    game = BlackjackGame(amount)
    view = BlackjackView(game, interaction.user)
    await interaction.response.send_message(embed=view.embed(True), view=view)

@bot.tree.command(name="cf")
@app_commands.describe(
    amount="Bet amount",
    choice="heads or tails",
    user="User to coinflip against (optional)"
)
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
    if user and user.id == interaction.user.id:
        return await interaction.response.send_message("You can't coinflip yourself.", ephemeral=True)

    # ---- AI COINFLIP ----
    if not user:
        result = random.choice(["heads", "tails"])
        if result == choice:
            u["balance"] += amount
            u["coinflip"]["wins"] += 1
            msg = f"🪙 **{result.upper()}** — You won **{amount}**!"
        else:
            u["balance"] -= amount
            u["coinflip"]["losses"] += 1
            msg = f"🪙 **{result.upper()}** — You lost **{amount}**."

        save_data()
        return await interaction.response.send_message(msg)

    # ---- PvP COINFLIP ----
    opponent = get_user(user.id)
    if opponent["balance"] < amount:
        return await interaction.response.send_message(
            f"{user.mention} doesn't have enough balance.",
            ephemeral=True
        )

    view = CoinflipView(interaction.user, user, amount, choice)
    await interaction.response.send_message(
        f"🪙 **Coinflip Challenge**\n"
        f"{interaction.user.mention} vs {user.mention}\n"
        f"Bet: **{amount} dabloons**\n"
        f"{user.mention}, click **Accept Coinflip**",
        view=view
    )

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

    # =========================
# GIVEAWAY SYSTEM
# =========================

import asyncio
import random
import discord
from discord.ui import View, Button
from discord import app_commands


class GiveawayView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.entries = set()

    @discord.ui.button(label="🎉 Enter Giveaway", style=discord.ButtonStyle.green)
    async def enter(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id in self.entries:
            await interaction.response.send_message(
                "❌ You already entered this giveaway.",
                ephemeral=True
            )
            return

        self.entries.add(interaction.user.id)
        await interaction.response.send_message(
            "✅ You have entered the giveaway!",
            ephemeral=True
        )


@bot.tree.command(name="giveaway", description="Start a dabloons giveaway")
@app_commands.describe(
    amount="Dabloons per winner",
    duration="Duration in seconds",
    winners="Number of winners"
)
async def giveaway(
    interaction: discord.Interaction,
    amount: int,
    duration: int,
    winners: int
):
    if amount <= 0 or duration <= 0 or winners <= 0:
        await interaction.response.send_message(
            "❌ Amount, duration, and winners must be positive numbers.",
            ephemeral=True
        )
        return

    view = GiveawayView()

    embed = discord.Embed(
        title="🎉 Dabloons Giveaway!",
        description=(
            f"💰 **{amount} dabloons** per winner\n"
            f"👑 **{winners} winner(s)**\n"
            f"⏰ Ends in **{duration} seconds**\n\n"
            f"Click 🎉 below to enter!"
        ),
        color=discord.Color.gold()
    )

    await interaction.response.send_message(embed=embed, view=view)
    message = await interaction.original_response()

    await asyncio.sleep(duration)

    if not view.entries:
        await message.reply("❌ Giveaway ended — no one entered.")
        return

    selected = random.sample(
        list(view.entries),
        k=min(winners, len(view.entries))
    )

    mentions = []
    for user_id in selected:
        update_balance(user_id, amount)
        mentions.append(f"<@{user_id}>")

    await message.reply(
        f"🎊 **GIVEAWAY ENDED!**\n"
        f"🏆 Winner(s): {', '.join(mentions)}\n"
        f"💰 Each winner received **{amount} dabloons**!"
    )


# ---------- READY ----------
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")

bot.run(TOKEN)
