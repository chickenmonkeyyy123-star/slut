import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import asyncio
import random

load_dotenv()
TOKEN = os.getenv('DISCORD_BOT_TOKEN')

intents = discord.Intents.default()
bot = commands.Bot(command_prefix='/', intents=intents)

# Sync commands on startup
@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    await bot.tree.sync()

# /bj command: Blackjack against AI
@bot.tree.command(name="bj", description="Play blackjack against AI")
async def blackjack(interaction: discord.Interaction, amount: float):
    await interaction.response.send_message(f"Starting blackjack with {amount} dabloons...", ephemeral=True)
    # Implement blackjack game logic here

# /cf command: Coinflip with AI
@bot.tree.command(name="cf", description="Coinflip with AI")
async def coinflip(interaction: discord.Interaction, amount: float, choice: str, user: discord.User):
    choice = choice.lower()
    if choice not in ['heads', 'tails']:
        await interaction.response.send_message("Choice must be 'heads' or 'tails'.", ephemeral=True)
        return
    flip_result = random.choice(['heads', 'tails'])
    result_message = f"The coin landed on {flip_result}."
    if choice == flip_result:
        outcome = f"{user.mention} wins {amount} dabloons!"
        # Update user balance here
    else:
        outcome = f"{user.mention} loses {amount} dabloons."
        # Deduct user balance here
    await interaction.response.send_message(f"{interaction.user.mention} flipped a coin with {user.mention}. {result_message}\n{outcome}", ephemeral=False)

# /leaderboard command
@bot.tree.command(name="leaderboard", description="Show the leaderboard of dabloons")
async def leaderboard(interaction: discord.Interaction):
    # Placeholder leaderboard data
    leaderboard_data = [
        ("User1", 500),
        ("User2", 300),
        ("User3", 150),
    ]
    embed = discord.Embed(title="Leaderboard")
    for rank, (user, amount) in enumerate(leaderboard_data, start=1):
        embed.add_field(name=f"{rank}. {user}", value=f"{amount} dabloons", inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# /giveaway command
@bot.tree.command(name="giveaway", description="Start a giveaway for dabloons")
async def giveaway(interaction: discord.Interaction, amount: float, duration: int, winners: int):
    embed = discord.Embed(title="🎉 Giveaway! 🎉",
                          description=f"{winners} winner(s) will share {amount} dabloons!\nDuration: {duration} seconds.")
    message = await interaction.response.send_message(embed=embed)

    # Add reaction to collect entries
    giveaway_message = await interaction.original_response()
    await giveaway_message.add_reaction("🎉")

    await asyncio.sleep(duration)

    # Fetch message again to get reactions
    message = await interaction.channel.fetch_message(giveaway_message.id)
    users = set()
    for reaction in message.reactions:
        if str(reaction.emoji) == "🎉":
            async for user in reaction.users():
                if user != bot.user:
                    users.add(user)

    if len(users) == 0:
        await interaction.followup.send("No entries received. Giveaway canceled.")
        return

    winners_list = random.sample(users, min(winners, len(users)))
    winners_mentions = ', '.join([winner.mention for winner in winners_list])
    await interaction.followup.send(f"Congratulations {winners_mentions}! You won {amount} dabloons!")

# /sync command to manually sync commands if needed
@bot.tree.command(name="sync", description="Sync commands with Discord")
async def sync(interaction: discord.Interaction):
    await bot.tree.sync()
    await interaction.response.send_message("Commands synchronized.", ephemeral=True)

# Run the bot
bot.run(TOKEN)
