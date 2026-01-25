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

# Load balances and extract 'balance'
def load_balances():
    try:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
        balances = {}
        for user_id_str, user_data in data.items():
            if isinstance(user_data, dict) and "balance" in user_data:
                balances[user_id_str] = user_data["balance"]
        return balances
    except FileNotFoundError:
        return {}

def save_balance(user_id, amount):
    # Read full data
    try:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}
    user_id_str = str(user_id)
    # Ensure user exists
    if user_id_str not in data or not isinstance(data[user_id_str], dict):
        data[user_id_str] = {}
    # Update only 'balance' field
    data[user_id_str]["balance"] = amount
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def update_balance(user_id, delta):
    # Load full data
    try:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}
    user_id_str = str(user_id)
    if user_id_str not in data or not isinstance(data[user_id_str], dict):
        data[user_id_str] = {}
    current_balance = data[user_id_str].get("balance", 0)
    new_balance = current_balance + delta
    data[user_id_str]["balance"] = new_balance
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)
    return new_balance

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await bot.tree.sync()

# /bj placeholder
@bot.tree.command(name="bj", description="Blackjack against AI")
async def blackjack(interaction: discord.Interaction, amount: float):
    await interaction.response.send_message(f"Blackjack with {amount} dabloons is coming soon!", ephemeral=True)

# /cf command with optional user for PvP
@bot.tree.command(name="cf", description="Coinflip with AI or a user")
async def coinflip(interaction: discord.Interaction, amount: float, choice: str, user: discord.User = None):
    choice = choice.lower()
    if choice not in ['heads', 'tails']:
        await interaction.response.send_message("Choice must be 'heads' or 'tails'.", ephemeral=True)
        return

    opponent_user = user or interaction.user
    # Check if user has enough balance
    if get_balance(interaction.user.id) < amount:
        await interaction.response.send_message("You don't have enough dabloons.", ephemeral=True)
        return

    # Initialize opponent if not exists
    update_balance(opponent_user.id, 0)

    flip_result = random.choice(['heads', 'tails'])
    # Determine winner
    if choice == flip_result:
        # User wins
        update_balance(interaction.user.id, -amount)
        update_balance(opponent_user.id, amount)
        winner_mention = interaction.user.mention
    else:
        # Opponent wins
        update_balance(interaction.user.id, amount)
        update_balance(opponent_user.id, -amount)
        winner_mention = opponent_user.mention

    await interaction.response.send_message(
        f"{interaction.user.mention} flipped a coin with {opponent_user.mention}. It landed on {flip_result}.\n"
        f"{winner_mention} wins {amount} dabloons!",
        ephemeral=False
    )

# /leaderboard with profile pics
@bot.tree.command(name="leaderboard", description="Show top dabloon holders")
async def leaderboard(interaction: discord.Interaction):
    balances = load_balances()
    # Filter out invalid data
    balances = {k: v for k, v in balances.items() if isinstance(v, (int, float))}
    sorted_data = sorted(balances.items(), key=lambda item: item[1], reverse=True)
    embed = discord.Embed(title="🏆 Dabloon Leaderboard", color=discord.Color.gold())

    top_users = sorted_data[:10]
    for rank, (user_id_str, amount) in enumerate(top_users, start=1):
        try:
            user = await bot.fetch_user(int(user_id_str))
            name = user.name
        except:
            name = "Unknown User"
        embed.add_field(
            name=f"{rank}. {name}",
            value=f"{amount} dabloons",
            inline=False
        )

    if top_users:
        try:
            top_user = await bot.fetch_user(int(top_users[0][0]))
            embed.set_thumbnail(url=top_user.display_avatar.url)
        except:
            pass

    await interaction.response.send_message(embed=embed, ephemeral=True)

# /giveaway
@bot.tree.command(name="giveaway", description="Start a giveaway")
async def giveaway(interaction: discord.Interaction, amount: float, duration: int, winners: int):
    embed = discord.Embed(title="🎉 Giveaway! 🎉", description=f"{winners} winners will share {amount} dabloons!\nDuration: {duration} seconds.")
    message = await interaction.response.send_message(embed=embed)
    giveaway_msg = await interaction.original_response()
    await giveaway_msg.add_reaction("🎉")
    await asyncio.sleep(duration)

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
    winners_mentions = ', '.join([w.mention for w in winners_list])
    # Distribute prize
    for winner in winners_list:
        update_balance(winner.id, amount / len(winners_list))
    await interaction.followup.send(f"Congratulations {winners_mentions}! You won {amount} dabloons!")

# /sync
@bot.tree.command(name="sync", description="Sync commands")
async def sync(interaction: discord.Interaction):
    await bot.tree.sync()
    await interaction.response.send_message("Commands synchronized.", ephemeral=True)

def get_balance(user_id):
    data = load_balances()
    return data.get(str(user_id), 0)

# Run the bot
bot.run(TOKEN)
