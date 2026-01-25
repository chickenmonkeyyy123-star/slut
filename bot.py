import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import asyncio
import json
import random

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_BOT_TOKEN')

# Check token
if not TOKEN:
    raise ValueError("Discord bot token not found! Please set DISCORD_BOT_TOKEN in your .env file.")

# Set intents
intents = discord.Intents.default()
intents.message_content = True  # For message content if needed
bot = commands.Bot(command_prefix='/', intents=intents)

DATA_FILE = 'dabloon_data.json'

# Utility functions to load/save balances
def load_balances():
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_balances(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

# Event: Bot ready
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    await bot.tree.sync()

# /bj command (placeholder)
@bot.tree.command(name="bj", description="Play blackjack against AI")
async def blackjack(interaction: discord.Interaction, amount: float):
    await interaction.response.send_message(f"Blackjack game starting with {amount} dabloons...", ephemeral=True)
    # Implement blackjack logic here

# /cf command (placeholder)
@bot.tree.command(name="cf", description="Coinflip with AI")
async def coinflip(interaction: discord.Interaction, amount: float, choice: str, user: discord.User):
    choice = choice.lower()
    if choice not in ['heads', 'tails']:
        await interaction.response.send_message("Choice must be 'heads' or 'tails'.", ephemeral=True)
        return
    flip_result = random.choice(['heads', 'tails'])
    balances = load_balances()
    user_id_str = str(user.id)
    balances.setdefault(user_id_str, 0)

    if choice == flip_result:
        balances[user_id_str] += amount
        outcome = f"{user.mention} wins {amount} dabloons!"
    else:
        balances[user_id_str] -= amount
        outcome = f"{user.mention} loses {amount} dabloons."

    save_balances(balances)
    await interaction.response.send_message(f"{interaction.user.mention} flipped the coin with {user.mention}. It landed on {flip_result}.\n{outcome}", ephemeral=False)

# /leaderboard command with profile pictures
@bot.tree.command(name="leaderboard", description="Show the leaderboard of dabloons")
async def leaderboard(interaction: discord.Interaction):
    balances = load_balances()
    sorted_data = sorted(balances.items(), key=lambda item: item[1], reverse=True)

    embed = discord.Embed(title="🏆 Dabloon Leaderboard", color=discord.Color.gold())

    top_users = sorted_data[:10]
    for rank, (user_id_str, amount) in enumerate(top_users, start=1):
        try:
            user = await bot.fetch_user(int(user_id_str))
            name = user.name
            avatar_url = user.display_avatar.url
        except:
            name = "Unknown User"
            avatar_url = None

        embed.add_field(
            name=f"{rank}. {name}",
            value=f"{amount} dabloons",
            inline=False
        )

    # Set the thumbnail to the top user's avatar for a clean look
    if top_users:
        try:
            top_user = await bot.fetch_user(int(top_users[0][0]))
            embed.set_thumbnail(url=top_user.display_avatar.url)
        except:
            pass

    await interaction.response.send_message(embed=embed, ephemeral=True)

# Helper to update user balance
def update_user_balance(user_id, amount):
    balances = load_balances()
    user_id_str = str(user_id)
    balances.setdefault(user_id_str, 0)
    balances[user_id_str] += amount
    save_balances(balances)

# /giveaway command
@bot.tree.command(name="giveaway", description="Start a giveaway for dabloons")
async def giveaway(interaction: discord.Interaction, amount: float, duration: int, winners: int):
    embed = discord.Embed(title="🎉 Giveaway! 🎉",
                          description=f"{winners} winner(s) will share {amount} dabloons!\nDuration: {duration} seconds.")
    message = await interaction.response.send_message(embed=embed)
    giveaway_message = await interaction.original_response()
    await giveaway_message.add_reaction("🎉")

    # Wait for duration
    await asyncio.sleep(duration)

    # Fetch message again for reactions
    message = await interaction.channel.fetch_message(giveaway_message.id)
    users = set()
    for reaction in message.reactions:
        if str(reaction.emoji) == "🎉":
            async for user in reaction.users():
                if user != bot.user:
                    users.add(user)

    if not users:
        await interaction.followup.send("No entries received. Giveaway canceled.")
        return

    winners_list = random.sample(users, min(winners, len(users)))
    winners_mentions = ', '.join([winner.mention for winner in winners_list])
    # Distribute prize among winners
    for winner in winners_list:
        update_user_balance(winner.id, amount / len(winners_list))
    await interaction.followup.send(f"Congratulations {winners_mentions}! You won {amount} dabloons!")

# /sync command
@bot.tree.command(name="sync", description="Sync commands with Discord")
async def sync(interaction: discord.Interaction):
    await bot.tree.sync()
    await interaction.response.send_message("Commands synchronized.", ephemeral=True)

# Run the bot
bot.run(TOKEN)
