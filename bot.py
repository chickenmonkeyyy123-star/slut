import discord
from discord import Object
from dotenv import load_dotenv
import os
import asyncio

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1332118870181412936  # your server ID

intents = discord.Intents.default()
bot = discord.Client(intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")

    guild = Object(id=GUILD_ID)

    # Fetch all guild commands
    commands = await bot.tree.fetch_commands(guild=guild)

    # Delete each command
    for cmd in commands:
        await bot.tree.delete_command(cmd.id, guild=guild)
        print(f"Deleted {cmd.name}")

    print("✅ All commands cleared!")
    await bot.close()

async def main():
    async with bot:
        await bot.start(TOKEN)

asyncio.run(main())
