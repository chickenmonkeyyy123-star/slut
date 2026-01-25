import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button
import random, json, os, asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv

# ================== SETUP ==================

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
DATA_FILE = "dabloon_data.json"
GUILD_ID = 1332118870181412936

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ================== DATA ==================

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_user(data, uid):
    uid = str(uid)
    if uid not in data:
        data[uid] = {
            "balance": 1000,
            "blackjack": {"wins": 0, "losses": 0},
            "coinflip": {"wins": 0, "losses": 0},
            "last_claim": None
        }
    return data[uid]

# ================== BLACKJACK ==================

CARDS = [2,3,4,5,6,7,8,9,10,10,10,10,11]

def hand_value(hand):
    total = sum(hand)
    aces = hand.count(11)
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total

def fmt_hand(hand):
    names = []
    for c in hand:
        if c == 11:
            names.append("A")
        elif c == 10:
            names.append(random.choice(["10","J","Q","K"]))
        else:
            names.append(str(c))
    return " ".join(names)

class BlackjackView(View):
    def __init__(self, interaction, bet, data):
        super().__init__(timeout=120)
        self.i = interaction
        self.bet = bet
        self.data = data
        self.player = [random.choice(CARDS), random.choice(CARDS)]
        self.dealer = [random.choice(CARDS), random.choice(CARDS)]
        self.finished = False

    def embed(self, reveal=False):
        pv = hand_value(self.player)
        dv = hand_value(self.dealer if reveal else [self.dealer[0]])

        e = discord.Embed(title="🃏 Blackjack", color=0x2ecc71)
        e.add_field(
            name="🧍 Your Hand",
            value=f"`{fmt_hand(self.player)}` → **{pv}**",
            inline=False
        )
        e.add_field(
            name="🎩 Dealer",
            value=f"`{fmt_hand(self.dealer) if reveal else fmt_hand([self.dealer[0]]) + ' ❓'}` → **{dv}**",
            inline=False
        )
        e.set_footer(text=f"Bet: {self.bet} dabloons")
        return e

    async def end(self):
        while hand_value(self.dealer) < 17:
            self.dealer.append(random.choice(CARDS))

        pv = hand_value(self.player)
        dv = hand_value(self.dealer)
        user = get_user(self.data, self.i.user.id)

        if pv > 21 or (dv <= 21 and dv > pv):
            user["balance"] -= self.bet
            user["blackjack"]["losses"] += 1
            result = "❌ You lost"
        elif pv == 21 and len(self.player) == 2:
            win = int(self.bet * 1.5)
            user["balance"] += win
            user["blackjack"]["wins"] += 1
            result = f"🎉 **BLACKJACK!** +{win}"
        else:
            user["balance"] += self.bet
            user["blackjack"]["wins"] += 1
            result = "✅ You won"

        save_data(self.data)
        self.clear_items()
        await self.i.edit_original_response(embed=self.embed(True), view=self)
        await self.i.followup.send(result)

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary)
    async def hit(self, interaction: discord.Interaction, _):
        self.player.append(random.choice(CARDS))
        if hand_value(self.player) >= 21:
            await self.end()
        else:
            await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary)
    async def stand(self, interaction: discord.Interaction, _):
        await self.end()

    @discord.ui.button(label="Double", style=discord.ButtonStyle.danger)
    async def double(self, interaction: discord.Interaction, _):
        user = get_user(self.data, interaction.user.id)
        if user["balance"] < self.bet:
            await interaction.response.send_message("Not enough balance", ephemeral=True)
            return
        self.bet *= 2
        self.player.append(random.choice(CARDS))
        await self.end()

# ================== COMMANDS ==================

@bot.tree.command(name="bj")
async def bj(interaction: discord.Interaction, amount: int):
    data = load_data()
    user = get_user(data, interaction.user.id)
    if amount <= 0 or user["balance"] < amount:
        await interaction.response.send_message("Invalid bet", ephemeral=True)
        return

    view = BlackjackView(interaction, amount, data)
    await interaction.response.send_message(embed=view.embed(), view=view)

# ================== COINFLIP (LIVE TIMER) ==================

@bot.tree.command(name="cf")
async def cf(interaction: discord.Interaction, amount: int, opponent: discord.User):
    data = load_data()
    p1 = get_user(data, interaction.user.id)
    p2 = get_user(data, opponent.id)

    if p1["balance"] < amount or p2["balance"] < amount:
        await interaction.response.send_message("One player lacks funds", ephemeral=True)
        return

    msg = await interaction.response.send_message(
        f"🪙 **Coinflip Challenge**\n{opponent.mention}, you have **60 seconds** to accept!",
        view=None
    )

    message = await interaction.original_response()

    for t in range(60, 0, -1):
        await message.edit(content=f"🪙 **Coinflip Challenge**\n⏳ Time left: **{t}s**")
        await asyncio.sleep(1)

    winner = random.choice([interaction.user, opponent])
    loser = opponent if winner == interaction.user else interaction.user

    get_user(data, winner.id)["balance"] += amount
    get_user(data, loser.id)["balance"] -= amount
    save_data(data)

    await message.edit(content=f"🎉 **{winner.mention} won {amount} dabloons!**")

# ================== LEADERBOARD ==================

@bot.tree.command(name="lb")
async def lb(interaction: discord.Interaction):
    data = load_data()
    top = sorted(data.items(), key=lambda x: x[1]["balance"], reverse=True)[:10]

    e = discord.Embed(title="🏆 Dabloons Leaderboard", color=0xf1c40f)
    for i, (uid, u) in enumerate(top, 1):
        e.add_field(
            name=f"#{i}",
            value=f"<@{uid}> — 💰 {u['balance']}",
            inline=False
        )

    await interaction.response.send_message(embed=e)

# ================== READY ==================

@bot.event
async def on_ready():
    guild = discord.Object(id=GUILD_ID)
    bot.tree.clear_commands(guild=guild)
    await bot.tree.sync(guild=guild)
    bot.tree.copy_global_to(guild=guild)
    await bot.tree.sync(guild=guild)
    print("✅ Commands synced")

bot.run(TOKEN)
