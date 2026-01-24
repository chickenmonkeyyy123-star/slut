import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import random
import asyncio
from datetime import datetime, timedelta

# =====================
# Load environment
# =====================
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN not found in .env")

# =====================
# Bot setup
# =====================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# =====================
# Data storage (memory)
# =====================
user_data = {}
giveaways = {}

# =====================
# Helpers
# =====================
def get_user_data(user_id):
    if user_id not in user_data:
        user_data[user_id] = {
            "balance": 1000,
            "blackjack_wins": 0,
            "blackjack_losses": 0,
            "coinflip_wins": 0,
            "coinflip_losses": 0,
        }
    return user_data[user_id]

# =====================
# Blackjack game
# =====================
class BlackjackGame:
    def __init__(self, bet):
        self.deck = self.create_deck()
        random.shuffle(self.deck)
        self.player = [self.deck.pop(), self.deck.pop()]
        self.dealer = [self.deck.pop(), self.deck.pop()]
        self.bet = bet

    def create_deck(self):
        suits = ["♠", "♥", "♦", "♣"]
        ranks = ["2","3","4","5","6","7","8","9","10","J","Q","K","A"]
        return [f"{r}{s}" for s in suits for r in ranks]

    def value(self, hand):
        total, aces = 0, 0
        for card in hand:
            r = card[:-1]
            if r in "JQK":
                total += 10
            elif r == "A":
                total += 11
                aces += 1
            else:
                total += int(r)
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
        return f"Hidden, {hand[1]}" if hide else ", ".join(hand)

# =====================
# Events
# =====================
@bot.event
async def on_ready():
    try:
        # Sync commands globally (can take up to an hour to update)
        await bot.tree.sync()
        print(f"✅ Logged in as {bot.user}")
        print(f"✅ Commands synced globally")
        
        # If you want instant updates for testing, sync to specific guild:
        # GUILD_ID = YOUR_GUILD_ID_HERE  # Replace with your server ID
        # await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
        # print(f"✅ Commands synced to guild {GUILD_ID}")
    except Exception as e:
        print(f"❌ Failed to sync commands: {e}")

# =====================
# Win/Loss command
# =====================
@bot.tree.command(name="wl", description="Show win/loss stats and balance")
@app_commands.describe(user="The user to check stats for (optional)")
async def wl(interaction: discord.Interaction, user: discord.Member = None):
    target_user = user if user else interaction.user
    data = get_user_data(target_user.id)
    
    # Calculate win rates
    bj_total = data["blackjack_wins"] + data["blackjack_losses"]
    bj_winrate = (data["blackjack_wins"] / bj_total * 100) if bj_total > 0 else 0
    
    cf_total = data["coinflip_wins"] + data["coinflip_losses"]
    cf_winrate = (data["coinflip_wins"] / cf_total * 100) if cf_total > 0 else 0
    
    embed = discord.Embed(
        title=f"📊 {target_user.display_name}'s Statistics",
        color=discord.Color.blue()
    )
    
    embed.add_field(name="💰 Balance", value=f"{data['balance']} coins", inline=False)
    
    embed.add_field(
        name="🃏 Blackjack",
        value=f"Wins: {data['blackjack_wins']}\nLosses: {data['blackjack_losses']}\nWin Rate: {bj_winrate:.2f}%",
        inline=True
    )
    
    embed.add_field(
        name="🪙 Coinflip",
        value=f"Wins: {data['coinflip_wins']}\nLosses: {data['coinflip_losses']}\nWin Rate: {cf_winrate:.2f}%",
        inline=True
    )
    
    await interaction.response.send_message(embed=embed)

# =====================
# Coinflip command
# =====================
@bot.tree.command(name="cf", description="Flip a coin and bet on the outcome")
@app_commands.describe(side="Choose heads or tails", amount="Amount to bet")
@app_commands.choices(side=[
    discord.app_commands.Choice(name="Heads", value="heads"),
    discord.app_commands.Choice(name="Tails", value="tails")
])
async def cf(interaction: discord.Interaction, side: str, amount: int):
    data = get_user_data(interaction.user.id)
    
    if amount <= 0:
        await interaction.response.send_message("Bet amount must be positive.", ephemeral=True)
        return
    
    if data["balance"] < amount:
        await interaction.response.send_message("Not enough coins.", ephemeral=True)
        return
    
    # Flip the coin
    result = random.choice(["heads", "tails"])
    won = result == side
    
    # Update balance and stats
    if won:
        data["balance"] += amount
        data["coinflip_wins"] += 1
        title = "🎉 You Won!"
        color = discord.Color.gold()
        description = f"The coin landed on **{result}**! You won {amount} coins!"
    else:
        data["balance"] -= amount
        data["coinflip_losses"] += 1
        title = "😢 You Lost"
        color = discord.Color.red()
        description = f"The coin landed on **{result}**! You lost {amount} coins."
    
    embed = discord.Embed(
        title=title,
        description=description,
        color=color
    )
    
    embed.add_field(name="New Balance", value=f"{data['balance']} coins")
    
    await interaction.response.send_message(embed=embed)

# =====================
# Blackjack command
# =====================
@bot.tree.command(name="bj", description="Play blackjack")
async def bj(interaction: discord.Interaction, amount: int):
    data = get_user_data(interaction.user.id)
    if amount <= 0:
        await interaction.response.send_message("Bet must be positive.", ephemeral=True)
        return
    if data["balance"] < amount:
        await interaction.response.send_message("Not enough dabloons.", ephemeral=True)
        return
    game = BlackjackGame(amount)
    embed = discord.Embed(
        title="♠️ Blackjack ♠️",
        description=(
            f"Your hand: {game.fmt(game.player)} ({game.value(game.player)})\n"
            f"Dealer: {game.fmt(game.dealer, True)}"
        ),
        color=discord.Color.green()
    )
    view = discord.ui.View(timeout=60)
    hit = discord.ui.Button(label="Hit", style=discord.ButtonStyle.success)
    stand = discord.ui.Button(label="Stand", style=discord.ButtonStyle.danger)
    async def hit_cb(inter):
        if game.hit():
            data["balance"] -= amount
            data["blackjack_losses"] += 1
            await inter.response.edit_message(
                embed=discord.Embed(
                    title="💥 Busted!",
                    description=f"Your hand: {game.fmt(game.player)} ({game.value(game.player)})",
                    color=discord.Color.red()
                ),
                view=None
            )
        else:
            embed.description = (
                f"Your hand: {game.fmt(game.player)} ({game.value(game.player)})\n"
                f"Dealer: {game.fmt(game.dealer, True)}"
            )
            await inter.response.edit_message(embed=embed)
    async def stand_cb(inter):
        game.stand()
        p, d = game.value(game.player), game.value(game.dealer)
        if d > 21 or p > d:
            data["balance"] += amount
            data["blackjack_wins"] += 1
            title, color = "🎉 You Win!", discord.Color.gold()
        elif p < d:
            data["balance"] -= amount
            data["blackjack_losses"] += 1
            title, color = "😢 You Lose", discord.Color.red()
        else:
            title, color = "🤝 Tie", discord.Color.blurple()
        await inter.response.edit_message(
            embed=discord.Embed(
                title=title,
                description=(
                    f"Your hand: {game.fmt(game.player)} ({p})\n"
                    f"Dealer: {game.fmt(game.dealer)} ({d})"
                ),
                color=color
            ),
            view=None
        )
    hit.callback = hit_cb
