import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button
import random, json, os, asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
DATA_FILE = "dabloon_data.json"

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ------------------ DATA HELPERS ------------------

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r") as f:
        return json.load(f)

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=2)

def get_user(data, user_id):
    uid = str(user_id)
    if uid not in data:
        data[uid] = {
            "balance": 1000,
            "blackjack": {"wins": 0, "losses": 0},
            "coinflip": {"wins": 0, "losses": 0},
            "last_claim": None
        }
    return data[uid]

# ------------------ BLACKJACK LOGIC ------------------

def draw_card():
    return random.choice([2,3,4,5,6,7,8,9,10,10,10,10,11])

def hand_value(hand):
    total = sum(hand)
    aces = hand.count(11)
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total

# ------------------ BLACKJACK VIEW ------------------

class BlackjackView(View):
    def __init__(self, interaction, bet, data):
        super().__init__(timeout=60)
        self.interaction = interaction
        self.bet = bet
        self.data = data
        self.player_hand = [draw_card(), draw_card()]
        self.dealer_hand = [draw_card(), draw_card()]

    async def update(self, end=False):
        pv = hand_value(self.player_hand)
        dv = hand_value(self.dealer_hand if end else [self.dealer_hand[0]])

        embed = discord.Embed(title="🃏 Blackjack", color=0x2ecc71)
        embed.add_field(name="Your Hand", value=f"{self.player_hand} = {pv}", inline=False)
        embed.add_field(name="Dealer", value=f"{self.dealer_hand if end else [self.dealer_hand[0]]} = {dv}", inline=False)

        if end:
            self.clear_items()

        await self.interaction.edit_original_response(embed=embed, view=self)

    async def finish(self):
        while hand_value(self.dealer_hand) < 17:
            self.dealer_hand.append(draw_card())

        pv = hand_value(self.player_hand)
        dv = hand_value(self.dealer_hand)
        user = get_user(self.data, self.interaction.user.id)

        if pv > 21 or (dv <= 21 and dv > pv):
            user["balance"] -= self.bet
            user["blackjack"]["losses"] += 1
            result = "❌ You lost!"
        elif pv == 21 and len(self.player_hand) == 2:
            win = int(self.bet * 1.5)
            user["balance"] += win
            user["blackjack"]["wins"] += 1
            result = f"🎉 BLACKJACK! +{win}"
        else:
            user["balance"] += self.bet
            user["blackjack"]["wins"] += 1
            result = "✅ You won!"

        save_data(self.data)
        await self.update(end=True)
        await self.interaction.followup.send(result)

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary)
    async def hit(self, interaction: discord.Interaction, _):
        self.player_hand.append(draw_card())
        if hand_value(self.player_hand) >= 21:
            await self.finish()
        else:
            await self.update()

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary)
    async def stand(self, interaction: discord.Interaction, _):
        await self.finish()

# ------------------ SLASH COMMANDS ------------------

@bot.tree.command(name="bj")
@app_commands.describe(amount="Bet amount")
async def blackjack(interaction: discord.Interaction, amount: int):
    data = load_data()
    user = get_user(data, interaction.user.id)

    if amount <= 0 or user["balance"] < amount:
        await interaction.response.send_message("Invalid bet.", ephemeral=True)
        return

    view = BlackjackView(interaction, amount, data)
    await interaction.response.send_message("🃏 Blackjack started", view=view)
    await view.update()

# ------------------ COINFLIP PVP VIEW ------------------

class CoinflipRequest(View):
    def __init__(self, challenger, opponent, amount, choice):
        super().__init__(timeout=60)
        self.challenger = challenger
        self.opponent = opponent
        self.amount = amount
        self.choice = choice
        self.accepted = False

    async def interaction_check(self, interaction):
        return interaction.user.id == self.opponent.id

    async def on_timeout(self):
        if not self.accepted:
            self.clear_items()
            await self.message.edit(content="⏰ Coinflip request expired.", view=self)

    @discord.ui.button(label="Accept", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, _):
        self.accepted = True
        self.clear_items()

        data = load_data()
        p1 = get_user(data, self.challenger.id)
        p2 = get_user(data, self.opponent.id)

        if p1["balance"] < self.amount or p2["balance"] < self.amount:
            await interaction.response.edit_message(content="❌ One player lacks funds.", view=None)
            return

        result = random.choice(["heads", "tails"])
        winner = self.challenger if self.choice == result else self.opponent
        loser = self.opponent if winner == self.challenger else self.challenger

        get_user(data, winner.id)["balance"] += self.amount
        get_user(data, loser.id)["balance"] -= self.amount

        save_data(data)

        await interaction.response.edit_message(
            content=f"🪙 Coin landed **{result}**\n🏆 Winner: {winner.mention}",
            view=None
        )

    @discord.ui.button(label="Decline", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, _):
        self.clear_items()
        await interaction.response.edit_message(content="❌ Coinflip declined.", view=None)

# ------------------ COINFLIP COMMAND ------------------

@bot.tree.command(name="cf")
@app_commands.describe(amount="Bet", choice="heads or tails", user="Opponent")
async def coinflip(interaction: discord.Interaction, amount: int, choice: str, user: discord.User):
    if choice not in ["heads", "tails"]:
        await interaction.response.send_message("Choice must be heads or tails.", ephemeral=True)
        return

    data = load_data()
    p1 = get_user(data, interaction.user.id)
    p2 = get_user(data, user.id)

    if amount <= 0 or p1["balance"] < amount or p2["balance"] < amount:
        await interaction.response.send_message("Invalid bet or insufficient funds.", ephemeral=True)
        return

    view = CoinflipRequest(interaction.user, user, amount, choice)
    await interaction.response.send_message(
        f"🪙 **Coinflip Challenge**\n"
        f"{interaction.user.mention} vs {user.mention}\n"
        f"💰 Bet: {amount}\n"
        f"🎯 {interaction.user.mention} chose **{choice}**\n"
        f"⏰ Expires in 60 seconds",
        view=view
    )
    view.message = await interaction.original_response()

# ------------------ READY ------------------

@bot.event
async def on_ready():
    guild = discord.Object(id=1332118870181412936)
    bot.tree.copy_global_to(guild=guild)
    await bot.tree.sync(guild=guild)
    print(f"✅ Synced commands to guild {guild.id}")
    print(f"🤖 Logged in as {bot.user}")

bot.run(TOKEN)
