import discord
from discord.ext import commands
import random
import sqlite3
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Get variables from .env file
TOKEN = os.getenv('DISCORD_TOKEN')

# Hardcoded channel and category IDs
ALLOWED_CATEGORY_ID = 1332118870181412938  # Text Channels Category
GAMBLING_CHANNEL_ID = 1464725219892793476  # Gambling Channel
LOG_CHANNEL_ID = 1464725054326702080  # Log Channel WL

# Initialize bot
bot = commands.Bot(command_prefix='/', intents=discord.Intents.default())

# Database setup
conn = sqlite3.connect('slut_bot.db')
cursor = conn.cursor()

# Create tables if they don't exist
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    dabloons INTEGER DEFAULT 1000,
    coinflip_wins INTEGER DEFAULT 0,
    coinflip_losses INTEGER DEFAULT 0,
    blackjack_wins INTEGER DEFAULT 0,
    blackjack_losses INTEGER DEFAULT 0
)
""")
conn.commit()

# Create transactions table for logging
cursor.execute("""
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    game TEXT,
    amount INTEGER,
    result TEXT,  -- 'win' or 'loss'
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
)
""")
conn.commit()

# Helper functions
def get_user_balance(user_id):
    cursor.execute("SELECT dabloons FROM users WHERE user_id=?", (user_id,))
    result = cursor.fetchone()
    return result[0] if result else 1000

def update_balance(user_id, amount):
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    cursor.execute("UPDATE users SET dabloons=dabloons+? WHERE user_id=?", (amount, user_id))
    conn.commit()

def update_game_stats(user_id, game, won):
    wins_col = f"{game}_wins"
    losses_col = f"{game}_losses"
    if won:
        cursor.execute(f"UPDATE users SET {wins_col}={wins_col}+1 WHERE user_id=?", (user_id,))
    else:
        cursor.execute(f"UPDATE users SET {losses_col}={losses_col}+1 WHERE user_id=?", (user_id,))
    conn.commit()

def log_transaction(user_id, game, amount, result):
    cursor.execute("""
    INSERT INTO transactions (user_id, game, amount, result)
    VALUES (?, ?, ?, ?)
    """, (user_id, game, amount, result))
    conn.commit()

async def log_to_channel(message):
    try:
        log_channel = bot.get_channel(LOG_CHANNEL_ID)
        if log_channel:
            await log_channel.send(message)
    except Exception as e:
        print(f"Error logging to channel: {e}")

# Check function to verify the channel
def is_allowed_channel(ctx):
    return ctx.channel.id == GAMBLING_CHANNEL_ID and ctx.channel.category_id == ALLOWED_CATEGORY_ID

# Commands
@bot.command(name='coinflip')
@commands.check(is_allowed_channel)
async def coinflip(ctx, user: discord.User = None, amount: int = 0):
    if amount <= 0:
        await ctx.send("Please specify a valid amount to bet!")
        return
    
    # Check if user has enough balance
    balance = get_user_balance(ctx.author.id)
    if amount > balance:
        await ctx.send("You don't have enough dabloons for this bet!")
        return
    
    # Determine opponent
    opponent = user if user else "AI"
    
    # Flip coin
    result = random.choice(["heads", "tails"])
    won = random.choice([True, False])  # 50/50 chance
    
    if won:
        update_balance(ctx.author.id, amount)
        update_game_stats(ctx.author.id, "coinflip", True)
        log_transaction(ctx.author.id, "coinflip", amount, "win")
        await ctx.send(f"You won {amount} dabloons! The coin landed on {result}.")
        await log_to_channel(f"🪙 {ctx.author.mention} won {amount} dabloons in coinflip against {opponent}!")
    else:
        update_balance(ctx.author.id, -amount)
        update_game_stats(ctx.author.id, "coinflip", False)
        log_transaction(ctx.author.id, "coinflip", amount, "loss")
        await ctx.send(f"You lost {amount} dabloons! The coin landed on {result}.")
        await log_to_channel(f"🪙 {ctx.author.mention} lost {amount} dabloons in coinflip against {opponent}!")

@bot.command(name='blackjack')
@commands.check(is_allowed_channel)
async def blackjack(ctx, amount: int = 0):
    if amount <= 0:
        await ctx.send("Please specify a valid amount to bet!")
        return
    
    # Check if user has enough balance
    balance = get_user_balance(ctx.author.id)
    if amount > balance:
        await ctx.send("You don't have enough dabloons for this bet!")
        return
    
    # Simplified blackjack implementation
    player_hand = [random.randint(2, 11), random.randint(2, 11)]
    dealer_hand = [random.randint(2, 11), random.randint(2, 11)]
    
    player_total = sum(player_hand)
    dealer_total = sum(dealer_hand)
    
    # Basic game logic (you'd want to expand this)
    if player_total > 21:
        won = False
    elif dealer_total > 21:
        won = True
    elif player_total > dealer_total:
        won = True
    else:
        won = False
    
    if won:
        update_balance(ctx.author.id, amount)
        update_game_stats(ctx.author.id, "blackjack", True)
        log_transaction(ctx.author.id, "blackjack", amount, "win")
        await ctx.send(f"You won {amount} dabloons! Your hand: {player_hand} vs Dealer: {dealer_hand}")
        await log_to_channel(f"🃏 {ctx.author.mention} won {amount} dabloons in blackjack!")
    else:
        update_balance(ctx.author.id, -amount)
        update_game_stats(ctx.author.id, "blackjack", False)
        log_transaction(ctx.author.id, "blackjack", amount, "loss")
        await ctx.send(f"You lost {amount} dabloons! Your hand: {player_hand} vs Dealer: {dealer_hand}")
        await log_to_channel(f"🃏 {ctx.author.mention} lost {amount} dabloons in blackjack!")

@bot.command(name='leaderboard')
@commands.check(is_allowed_channel)
async def leaderboard(ctx, user: discord.User = None):
    if user:
        # Show specific user stats
        cursor.execute("""
        SELECT coinflip_wins, coinflip_losses, blackjack_wins, blackjack_losses, dabloons 
        FROM users WHERE user_id=?
        """, (user.id,))
        result = cursor.fetchone()
        if result:
            cf_wins, cf_losses, bj_wins, bj_losses, dabloons = result
            cf_ratio = cf_wins / (cf_wins + cf_losses) if (cf_wins + cf_losses) > 0 else 0
            bj_ratio = bj_wins / (bj_wins + bj_losses) if (bj_wins + bj_losses) > 0 else 0
            
            embed = discord.Embed(title=f"{user.display_name}'s Stats")
            embed.add_field(name="Dabloons", value=str(dabloons), inline=False)
            embed.add_field(name="Coinflip", value=f"Wins: {cf_wins}, Losses: {cf_losses}, Win Rate: {cf_ratio:.2%}")
            embed.add_field(name="Blackjack", value=f"Wins: {bj_wins}, Losses: {bj_losses}, Win Rate: {bj_ratio:.2%}")
            await ctx.send(embed=embed)
        else:
            await ctx.send("User not found in database!")
    else:
        # Show overall leaderboard
        cursor.execute("""
        SELECT user_id, dabloons, 
               coinflip_wins, coinflip_losses,
               blackjack_wins, blackjack_losses
        FROM users 
        ORDER BY dabloons DESC
        LIMIT 10
        """)
        
        results = cursor.fetchall()
        
        embed = discord.Embed(title="Dabloons Leaderboard")
        embed.description = ""
        
        for i, (user_id, dabloons, cf_wins, cf_losses, bj_wins, bj_losses) in enumerate(results, 1):
            try:
                user = await bot.fetch_user(user_id)
                username = user.display_name
            except:
                username = f"User {user_id}"
            
            cf_ratio = cf_wins / (cf_wins + cf_losses) if (cf_wins + cf_losses) > 0 else 0
            bj_ratio = bj_wins / (bj_wins + bj_losses) if (bj_wins + bj_losses) > 0 else 0
            
            embed.description += f"**#{i}** {username}: {dabloons} dabloons\n"
            embed.description += f"  Coinflip: {cf_ratio:.2%} | Blackjack: {bj_ratio:.2%}\n\n"
        
        await ctx.send(embed=embed)

@bot.command(name='history')
@commands.check(is_allowed_channel)
async def history(ctx, limit: int = 10):
    cursor.execute("""
    SELECT game, amount, result, timestamp 
   
