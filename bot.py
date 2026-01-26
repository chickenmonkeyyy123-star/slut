import discord
from discord.ext import commands

# ---------------- CONFIG ----------------
TOKEN = "YOUR_REAL_BOT_TOKEN_HERE"  # or from .env
GUILD_ID = 1332118870181412936  # your server ID

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Bot logged in as {bot.user} (ID: {bot.user.id})")
    
    guild = discord.Object(id=GUILD_ID)  # target guild

    print(f"Clearing all commands in guild {GUILD_ID}...")
    await bot.tree.clear_commands(guild=guild)
    await bot.tree.sync(guild=guild)
    print("All guild commands cleared successfully!")

    # stop bot after clearing
    await bot.close()

bot.run(TOKEN)
