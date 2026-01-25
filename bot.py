import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import asyncio
import json
import random

load_dotenv()
TOKEN = os.getenv('DISCORD_BOT_TOKEN')

if not TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN not set in .env file!")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

DATA_FILE = 'dabloon_data.json'

# Utility functions
def load_balances():
    try:
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_balances(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def get_balance(user_id):
    balances = load_balances()
    user_id_str = str(user_id)
    return balances.get(user_id_str, 0)

def set_balance(user_id, amount):
    balances = load_balances()
    user_id_str = str(user_id)
    balances[user_id_str] = amount
    save_balances(balances)

def update_balance(user_id, delta):
    balances = load_balances()
    user_id_str = str(user_id)
    current = balances.get(user_id_str, 0)
    new_balance = current + delta
    balances[user_id_str] = new_balance
    save_balances(balances)
    return new_balance

# Event: on_ready
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await bot.tree.sync()

# /bj - Placeholder
@bot.tree.command(name="bj", description="Blackjack against AI")
async def blackjack(interaction: discord.Interaction, amount: float):
    await interaction.response.send_message(f"Blackjack with {amount} dabloons coming soon!", ephemeral=True)

# /cf - Coinflip
@bot.tree.command(name="cf", description="Coinflip with AI or optionally PvP")
async def coinflip(interaction: discord.Interaction, amount: float, choice: str, user: discord.User = None):
    choice = choice.lower()
    if choice not in ['heads', 'tails']:
        await interaction.response.send_message("Choice must be 'heads' or 'tails'.", ephemeral=True)
        return

    # Determine opponent: AI if user not provided
    opponent_user = user or interaction.user

    # Initialize balances
    update_balance(opponent_user.id, 0)  # ensure user exists
    # Get balances
    opponent_balance = get_balance(opponent_user.id)

    # Check if user has enough balance
    if get_balance(interaction.user.id) < amount:
        await interaction.response.send_message("You don't have enough dabloons.", ephemeral=True)
        return

    flip_result = random.choice(['heads', 'tails'])
    outcome_msg = f"The coin landed on {flip_result}."

    # Determine if the user (or opponent) wins
    if choice == flip_result:
        # Winner gets the amount
        update_balance(opponent_user.id, amount)
        update_balance(interaction.user.id, -amount)
        winner = opponent_user
        winner_msg = f"{winner.mention} wins {amount} dabloons!"
    else:
        # Opponent wins
        update_balance(opponent_user.id, -amount)
        update_balance(interaction.user.id, amount)
        winner = interaction.user
        winner_msg = f"{winner.mention} wins {amount} dabloons!"

    await interaction.response.send_message(
        f"{interaction.user.mention} flipped a coin with {opponent_user.mention}. It landed on {flip_result}.\n{winner_msg}",
        ephemeral=False
    )

# /leaderboard with profile pics
@bot.tree.command(name="leaderboard", description="Show top dabloon holders")
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

    # Set thumbnail to top user avatar for a cleaner look
    if top_users:
        try:
            top_user = await bot.fetch_user(int(top_users[0][0]))
            embed.set_thumbnail(url=top_user.display_avatar.url)
        except:
            pass

    await interaction.response.send_message(embed=embed, ephemeral=True)

# /giveaway
@bot.tree.command(name="giveaway", description="Start a giveaway for dabloons")
async def giveaway(interaction: discord.Interaction, amount: float, duration: int, winners: int):
    embed = discord.Embed(
        title="🎉 Giveaway! 🎉",
        description=f"{winners} winner(s) will share {amount} dabloons!\nDuration: {duration} seconds."
    )
    message = await interaction.response.send_message(embed=embed)
    giveaway_msg = await interaction.original_response()
    await giveaway_msg.add_reaction("🎉")

    # Wait for the duration
    await asyncio.sleep(duration)

    # Fetch the message again
    msg = await interaction.channel.fetch_message(giveaway_msg.id)
    users = set()
    for reaction in msg.reactions:
        if str(reaction.emoji) == "🎉":
            async for user in reaction.users():
                if user != bot.user:
                    users.add(user)

    if not users:
        await interaction.followup.send("No entries received. Giveaway canceled.")
        return

    winners_list = random.sample(users, min(winners, len(users)))
    winners_mentions = ', '.join([winner.mention for winner in winners_list])

    # Distribute prize to winners
    for winner in winners_list:
        update_balance(winner.id, amount / len(winners_list))
    await interaction.followup.send(f"Congratulations {winners_mentions}! You won {amount} dabloons!")

# /sync
@bot.tree.command(name="sync", description="Sync slash commands")
async def sync(interaction: discord.Interaction):
    await bot.tree.sync()
    await interaction.response.send_message("Commands synchronized.", ephemeral=True)

# Run the bot
bot.run(TOKEN)
