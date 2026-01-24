import os
import discord
from discord.ext import commands
from discord import app_commands
from dotenv import load_dotenv
import random
import asyncio
from datetime import datetime, timedelta
import math

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
mines_games = {}  # Store active mines games

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
            "mines_wins": 0,
            "mines_losses": 0,
        }
    return user_data[user_id]

def get_mines_multiplier(mines_count):
    """Calculate multiplier based on number of mines"""
    multipliers = {
        1: 1.3,
        2: 1.5,
        3: 1.8,
        4: 2.2,
        5: 2.8,
        6: 3.5,
        7: 4.5,
        8: 6.0,
        9: 8.0,
        10: 12.0
    }
    return multipliers.get(mines_count, 1.0)

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
# Mines game
# =====================
class MinesGame:
    def __init__(self, mines_count, bet):
        self.mines_count = mines_count
        self.bet = bet
        self.grid_size = 5
        self.grid = [[0 for _ in range(self.grid_size)] for _ in range(self.grid_size)]
        self.revealed = [[False for _ in range(self.grid_size)] for _ in range(self.grid_size)]
        self.game_over = False
        self.multiplier = get_mines_multiplier(mines_count)
        self.revealed_count = 0
        self.current_multiplier = 1.0
        
        # Place mines randomly
        positions = [(i, j) for i in range(self.grid_size) for j in range(self.grid_size)]
        random.shuffle(positions)
        for i in range(mines_count):
            row, col = positions[i]
            self.grid[row][col] = 1  # 1 represents a mine
    
    def reveal(self, row, col):
        if self.game_over or self.revealed[row][col]:
            return False, self.game_over
        
        self.revealed[row][col] = True
        self.revealed_count += 1
        
        if self.grid[row][col] == 1:  # Hit a mine
            self.game_over = True
            return False, True
        
        # Calculate current multiplier based on revealed cells
        safe_cells = self.grid_size * self.grid_size - self.mines_count
        self.current_multiplier = 1.0 + (self.multiplier - 1.0) * (self.revealed_count / safe_cells)
        return True, False
    
    def cashout(self):
        if self.game_over:
            return 0
        
        return self.bet * self.current_multiplier
    
    def get_display(self):
        display = []
        for i in range(self.grid_size):
            row = []
            for j in range(self.grid_size):
                if self.revealed[i][j]:
                    if self.grid[i][j] == 1:
                        row.append("💣")  # Mine
                    else:
                        row.append("💎")  # Safe
                else:
                    row.append("⬜")  # Unrevealed
            display.append(" ".join(row))
        return "\n".join(display)

# =====================
# Events
# =====================
@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"✅ Logged in as {bot.user}")

# =====================
# Win/Loss command
# =====================
@bot.tree.command(name="wl", description="Show win/loss stats and balance")
async def wl(interaction: discord.Interaction, user: discord.Member = None):
    target_user = user if user else interaction.user
    data = get_user_data(target_user.id)
    
    # Calculate win rates
    bj_total = data["blackjack_wins"] + data["blackjack_losses"]
    bj_winrate = (data["blackjack_wins"] / bj_total * 100) if bj_total > 0 else 0
    
    cf_total = data["coinflip_wins"] + data["coinflip_losses"]
    cf_winrate = (data["coinflip_wins"] / cf_total * 100) if cf_total > 0 else 0
    
    mines_total = data["mines_wins"] + data["mines_losses"]
    mines_winrate = (data["mines_wins"] / mines_total * 100) if mines_total > 0 else 0
    
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
    
    embed.add_field(
        name="💣 Mines",
        value=f"Wins: {data['mines_wins']}\nLosses: {data['mines_losses']}\nWin Rate: {mines_winrate:.2f}%",
        inline=True
    )
    
    await interaction.response.send_message(embed=embed)

# =====================
# Mines command
# =====================
@bot.tree.command(name="mines", description="Play mines game")
async def mines(interaction: discord.Interaction, mines_count: int, amount: int):
    if mines_count < 1 or mines_count > 10:
        await interaction.response.send_message("Number of mines must be between 1 and 10.", ephemeral=True)
        return
    
    data = get_user_data(interaction.user.id)
    
    if amount <= 0:
        await interaction.response.send_message("Bet amount must be positive.", ephemeral=True)
        return
    
    if data["balance"] < amount:
        await interaction.response.send_message("Not enough coins.", ephemeral=True)
        return
    
    # Create a new game
    game = MinesGame(mines_count, amount)
    game_id = f"{interaction.user.id}_{datetime.now().timestamp()}"
    mines_games[game_id] = game
    
    # Create the game view
    view = discord.ui.View(timeout=300)
    
    # Add buttons for the grid
    for i in range(5):
        for j in range(5):
            button = discord.ui.Button(
                label=f"{i*5 + j + 1}",
                style=discord.ButtonStyle.secondary,
                row=i
            )
            
            async
