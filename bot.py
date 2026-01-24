import os
import random
from typing import Optional

import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv

# ======================
# CONFIG
# ======================
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1332118870181412936
START_BALANCE = 1000

# ======================
# INTENTS (IMPORTANT)
# ======================
intents = discord.Intents.default()
intents.guilds = True

bot = commands.Bot(command_prefix="!", intents=intents)
tree = bot.tree

# ======================
# DATA (in-memory)
# ======================
balances = {}
stats = {}


def ensure_user(user: discord.User):
    if user.id not in balances:
        balances[user.id] = START_BALANCE
    if user.id not in stats:
        stats[user.id] = {
            "bj_w": 0, "bj_l": 0,
            "cf_w": 0, "cf_l": 0
        }


def can_afford(user, amount):
    ensure_user(user)
    return balances[user.id] >= amount


# ======================
# BLACKJACK HELPERS
# ======================
def draw_card():
    return random.choice([2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 11])


def hand_value(hand):
    total = sum(hand)
    aces = hand.count(11)
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


# ======================
# GIVEAWAY VIEW
# ======================
class GiveawayView(discord.ui.View):
    def __init__(self, amount, winners, duration):
        super().__init__(timeout=duration)
        self.amount = amount
        self.winners = winners
        self.entries = set()

    @discord.ui.button(label="🎉 Enter Giveaway", style=discord.ButtonStyle.green)
    async def enter(self, interaction: discord.Interaction, button: discord.ui.Button):
        ensure_user(interaction.user)
        self.entries.add(interaction.user.id)
        await interaction.response.send_message(
            "You entered the giveaway!", ephemeral=True
        )

    async def on_timeout(self):
        if not self.entries:
            return

        winners = random.sample(
            list(self.entries),
            min(self.winners, len(self.entries))
        )

        msg = "🎊 **Giveaway Results** 🎊\n"
        for uid in winners:
            balances[uid] += self.amount
            user = self.message.guild.get_member(uid)
            msg += f"- {user.mention} won **{self.amount} dabloons**\n"

        await self.message.channel.send(msg)


# ======================
# COINFLIP VIEW
# ======================
class CoinflipView(discord.ui.View):
    def __init__(self, challenger, target, amount, choice):
        super().__init__(timeout=120)
        self.challenger = challenger
        self.target = target
        self.amount = amount
        self.choice = choice
        self.resolved = False

    @discord.ui.button(label="Accept Coinflip", style=discord.ButtonStyle.blurple)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.target and interaction.user.id != self.target.id:
            await interaction.response.send_message(
                "This coinflip isn’t for you.", ephemeral=True
            )
            return

        await self.resolve(interaction.user, interaction.channel)
        await interaction.response.defer()

    async def resolve(self, opponent, channel):
        if self.resolved:
            return
        self.resolved = True

        flip = random.choice(["heads", "tails"])
        winner = self.challenger if flip == self.choice else opponent
        loser = opponent if winner == self.challenger else self.challenger

        balances[winner.id] += self.amount
        balances[loser.id] -= self.amount

        stats[winner.id]["cf_w"] += 1
        stats[loser.id]["cf_l"] += 1

        await channel.send(
            f"🪙 Coin landed **{flip.upper()}**!\n"
            f"🏆 {winner.mention} won **{self.amount} dabloons**"
        )

    async def on_timeout(self):
        if self.target or self.resolved:
            return

        flip = random.choice(["heads", "tails"])
        if flip == self.choice:
            balances[self.challenger.id] += self.amount
            stats[self.challenger.id]["cf_w"] += 1
            result = "won"
        else:
            balances[self.challenger.id] -= self.amount
            stats[self.challenger.id]["cf_l"] += 1
            result = "lost"

        await self.message.channel.send(
            f"🪙 AI coinflip landed **{flip.upper()}** — "
            f"You {result} **{self.amount} dabloons**"
        )


# ======================
# SLASH COMMANDS
# ======================
@tree.command(name="bj", description="Play blackjack vs AI")
async def bj(interaction: discord.Interaction, amount: int):
    ensure_user(interaction.user)

    if not can_afford(interaction.user, amount):
        await interaction.response.send_message(
            "Not enough dabloons.", ephemeral=True
        )
        return

    player = [draw_card(), draw_card()]
    dealer = [draw_card(), draw_card()]

    while hand_value(player) < 17:
        player.append(draw_card())
    while hand_value(dealer) < 17:
        dealer.append(draw_card())

    p, d = hand_value(player), hand_value(dealer)

    if p > 21 or (d <= 21 and d > p):
        balances[interaction.user.id] -= amount
        stats[interaction.user.id]["bj_l"] += 1
        result = "You lost"
    else:
        balances[interaction.user.id] += amount
        stats[interaction.user.id]["bj_w"] += 1
        result = "You won"

    await interaction.response.send_message(
        f"🃏 **Blackjack**\n"
        f"Your hand: {player} ({p})\n"
        f"Dealer: {dealer} ({d})\n"
        f"**{result} {amount} dabloons**"
    )


@tree.command(name="cf", description="Coinflip vs user or AI")
async def cf(
    interaction: discord.Interaction,
    amount: int,
    choice: str,
    user: Optional[discord.Member] = None
):
    ensure_user(interaction.user)

    if choice not in ("heads", "tails"):
        await interaction.response.send_message(
            "Choice must be heads or tails.", ephemeral=True
        )
        return

    if not can_afford(interaction.user, amount):
        await interaction.response.send_message(
            "Not enough dabloons.", ephemeral=True
        )
        return

    view = CoinflipView(interaction.user, user, amount, choice)
    await interaction.response.send_message(
        f"🪙 **Coinflip**\n"
        f"Bet: {amount}\nChoice: {choice}\n"
        f"{'Waiting for opponent...' if user else 'AI will play after 120s'}",
        view=view
    )
    view.message = await interaction.original_response()


@tree.command(name="giveaway", description="Start a dabloon giveaway")
async def giveaway(interaction: discord.Interaction, amount: int, duration: int, winners: int):
    winners = max(1, min(4, winners))
    view = GiveawayView(amount, winners, duration)

    await interaction.response.send_message(
        f"🎉 **Giveaway Started** 🎉\n"
        f"Amount: {amount}\nWinners: {winners}\nDuration: {duration}s",
        view=view
    )
    view.message = await interaction.original_response()


@tree.command(name="wl", description="View win/loss stats and balance")
async def wl(interaction: discord.Interaction, user: Optional[discord.Member] = None):
    target = user or interaction.user
    ensure_user(target)
    s = stats[target.id]

    await interaction.response.send_message(
        f"📊 **Stats for {target.display_name}**\n"
        f"💰 Balance: {balances[target.id]} dabloons\n\n"
        f"🃏 Blackjack: {s['bj_w']}W / {s['bj_l']}L\n"
        f"🪙 Coinflip: {s['cf_w']}W / {s['cf_l']}L"
    )


@tree.command(name="leaderboard", description="Top dabloon holders")
async def leaderboard(interaction: discord.Interaction):
    if not balances:
        await interaction.response.send_message(
            "No data yet.", ephemeral=True
        )
        return

    top = sorted(balances.items(), key=lambda x: x[1], reverse=True)[:10]

    medals = ["🥇", "🥈", "🥉"]
    lines = []

    for i, (uid, bal) in enumerate(top):
        member = interaction.guild.get_member(uid)
        if not member:
            continue
        prefix = medals[i] if i < 3 else f"`#{i+1}`"
        lines.append(f"{prefix} **{member.display_name}** — {bal} dabloons")

    await interaction.response.send_message(
        "🏆 **Dabloon Leaderboard** 🏆\n\n" + "\n".join(lines)
    )


# ======================
# COMMAND REGISTRATION
# ======================
@bot.event
async def setup_hook():
    guild = discord.Object(id=GUILD_ID)
    await tree.sync(guild=guild)


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


# ======================
# START BOT
# ======================
bot.run(TOKEN)
