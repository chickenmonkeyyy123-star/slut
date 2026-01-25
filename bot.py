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
    card = random.choice([2,3,4,5,6,7,8,9,10,10,10,10,11])
    return card

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
        self.doubled = False

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

    @discord.ui.button(label="Double", style=discord.ButtonStyle.danger)
    async def double(self, interaction: discord.Interaction, _):
        user = get_user(self.data, interaction.user.id)
        if user["balance"] < self.bet:
            await interaction.response.send_message("Not enough balance.", ephemeral=True)
            return
        self.bet *= 2
        self.player_hand.append(draw_card())
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

# ------------------ COINFLIP ------------------

@bot.tree.command(name="cf")
@app_commands.describe(amount="Bet", choice="heads or tails", user="Optional opponent")
async def coinflip(interaction: discord.Interaction, amount: int, choice: str, user: discord.User = None):
    data = load_data()
    p1 = get_user(data, interaction.user.id)

    if p1["balance"] < amount or amount <= 0:
        await interaction.response.send_message("Invalid bet.", ephemeral=True)
        return

    result = random.choice(["heads", "tails"])

    if user:
        p2 = get_user(data, user.id)
        if p2["balance"] < amount:
            await interaction.response.send_message("Opponent lacks funds.", ephemeral=True)
            return

        winner = interaction.user if choice == result else user
        loser = user if winner == interaction.user else interaction.user

        get_user(data, winner.id)["balance"] += amount
        get_user(data, loser.id)["balance"] -= amount
    else:
        if choice == result:
            p1["balance"] += amount
            p1["coinflip"]["wins"] += 1
        else:
            p1["balance"] -= amount
            p1["coinflip"]["losses"] += 1

    save_data(data)
    await interaction.response.send_message(f"🪙 Coin landed **{result}**")

# ------------------ LEADERBOARD ------------------

@bot.tree.command(name="lb")
async def leaderboard(interaction: discord.Interaction):
    data = load_data()
    sorted_users = sorted(data.items(), key=lambda x: x[1]["balance"], reverse=True)[:15]

    embed = discord.Embed(title="🏆 Dabloons Leaderboard", color=0xf1c40f)
    for i, (uid, u) in enumerate(sorted_users, 1):
        embed.add_field(
            name=f"#{i}",
            value=f"<@{uid}> — 💰 {u['balance']}\nBJ {u['blackjack']['wins']}/{u['blackjack']['losses']} | CF {u['coinflip']['wins']}/{u['coinflip']['losses']}",
            inline=False
        )

    await interaction.response.send_message(embed=embed)

# ------------------ CLAIM ------------------

@bot.tree.command(name="claim")
async def claim(interaction: discord.Interaction):
    data = load_data()
    user = get_user(data, interaction.user.id)

    if user["balance"] >= 1000:
        await interaction.response.send_message("You already have enough dabloons.")
        return

    now = datetime.utcnow()
    last = datetime.fromisoformat(user["last_claim"]) if user["last_claim"] else None

    if last and now - last < timedelta(hours=1):
        await interaction.response.send_message("⏳ Claim available once per hour.")
        return

    user["balance"] += 1000
    user["last_claim"] = now.isoformat()
    save_data(data)
    await interaction.response.send_message("💰 Claimed 1000 dabloons!")

# ------------------ GIVEAWAY ------------------

@bot.tree.command(name="giveaway")
@app_commands.checks.has_permissions(administrator=True)
async def giveaway(interaction: discord.Interaction, amount: int, duration: int, winners: int):
    await interaction.response.send_message("🎁 Giveaway started! React 🎉")
    msg = await interaction.original_response()
    await msg.add_reaction("🎉")

    await asyncio.sleep(duration)
    msg = await interaction.channel.fetch_message(msg.id)

    users = [u for u in await msg.reactions[0].users().flatten() if not u.bot]
    if not users:
        return

    winners_list = random.sample(users, min(winners, len(users)))
    data = load_data()

    for w in winners_list:
        get_user(data, w.id)["balance"] += amount

    save_data(data)
    await interaction.followup.send("🎉 Winners: " + ", ".join(w.mention for w in winners_list))

# ------------------ READY ------------------

@bot.event
async def on_ready():
    await bot.tree.sync()
    print(f"Logged in as {bot.user}")

bot.run(TOKEN)
