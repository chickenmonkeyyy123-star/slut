import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button
import random
import json
import os
from dotenv import load_dotenv
import asyncio
from datetime import datetime, timedelta

# ---------- LOAD .ENV ----------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN not found in .env")

# ---------- CONFIG ----------
DATA_FILE = "dabloon_data.json"
START_BALANCE = 1000
GUILD_ID = 1332118870181412936  # Your server ID

# ---------- BOT ----------
intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------- DATA ----------
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data():
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

data = load_data()

def get_user(uid):
    uid = str(uid)
    if uid not in data:
        data[uid] = {
            "balance": START_BALANCE,
            "blackjack": {"wins": 0, "losses": 0},
            "coinflip": {"wins": 0, "losses": 0},
        }
        save_data()
    return data[uid]

def total_wl(u):
    return (
        u["blackjack"]["wins"] + u["coinflip"]["wins"],
        u["blackjack"]["losses"] + u["coinflip"]["losses"],
    )

# ---------- BLACKJACK ----------
class BlackjackGame:
    def __init__(self, bet):
        self.deck = self.new_deck()
        random.shuffle(self.deck)
        self.hands = [[self.deck.pop(), self.deck.pop()]]  # player hands
        self.current_hand = 0
        self.bets = [bet]
        self.finished = [False]
        self.dealer = [self.deck.pop(), self.deck.pop()]

    def new_deck(self):
        suits = ["♠", "♥", "♦", "♣"]
        ranks = ["2","3","4","5","6","7","8","9","10","J","Q","K","A"]
        deck = []
        for s in suits:
            for r in ranks:
                v = 11 if r == "A" else 10 if r in ["J","Q","K"] else int(r)
                deck.append({"r": r, "s": s, "v": v})
        return deck

    def value(self, hand):
        total = sum(c["v"] for c in hand)
        aces = sum(1 for c in hand if c["r"] == "A")
        while total > 21 and aces:
            total -= 10
            aces -= 1
        return total

    def is_soft(self, hand):
        return any(c["r"] == "A" for c in hand) and self.value(hand) <= 21

    def hit(self):
        hand = self.hands[self.current_hand]
        hand.append(self.deck.pop())
        if self.value(hand) > 21:
            self.finished[self.current_hand] = True
            return True
        return False

    def stand(self):
        self.finished[self.current_hand] = True

    def double(self):
        hand = self.hands[self.current_hand]
        if len(hand) == 2:
            self.bets[self.current_hand] *= 2
            hand.append(self.deck.pop())
            self.finished[self.current_hand] = True
            return True
        return False

    def can_double(self):
        return len(self.hands[self.current_hand]) == 2

    def can_split(self):
        hand = self.hands[self.current_hand]
        return len(hand) == 2 and hand[0]["r"] == hand[1]["r"]

    def split(self):
        if not self.can_split():
            return False
        hand = self.hands[self.current_hand]
        c1, c2 = hand
        self.hands[self.current_hand] = [c1, self.deck.pop()]
        self.hands.append([c2, self.deck.pop()])
        self.bets.append(self.bets[self.current_hand])
        self.finished.append(False)
        return True

    def dealer_play(self):
        while self.value(self.dealer) < 17 or (self.value(self.dealer) == 17 and self.is_soft(self.dealer)):
            self.dealer.append(self.deck.pop())

    def fmt(self, hand, hide=False):
        if hide:
            return "?, " + f"{hand[1]['r']}{hand[1]['s']}"
        return ", ".join(f"{c['r']}{c['s']}" for c in hand)

class BlackjackView(View):
    def __init__(self, game, user):
        super().__init__(timeout=120)
        self.game = game
        self.user = user
        self.message = None

    def embed(self, hide=True):
        hand = self.game.hands[self.game.current_hand]
        embed = discord.Embed(
            title=f"🃏 Blackjack (Hand {self.game.current_hand+1}/{len(self.game.hands)})",
            description=(
                f"**Your hand:** {self.game.fmt(hand)} (Value: {self.game.value(hand)})\n"
                f"**Dealer:** {self.game.fmt(self.game.dealer, hide)}\n"
                f"**Bet:** {self.game.bets[self.game.current_hand]}"
            ),
            color=discord.Color.blurple()
        )
        return embed

    async def end_game(self):
        self.game.dealer_play()
        dealer_val = self.game.value(self.game.dealer)
        messages = []
        u = get_user(self.user.id)

        for idx, hand in enumerate(self.game.hands):
            pv = self.game.value(hand)
            bet = self.game.bets[idx]
            if pv > 21:
                result = f"💥 Hand {idx+1}: Bust! Lose {bet}"
                u["balance"] -= bet
                u["blackjack"]["losses"] += 1
            elif dealer_val > 21 or pv > dealer_val:
                result = f"✅ Hand {idx+1}: Win! Gain {bet}"
                u["balance"] += bet
                u["blackjack"]["wins"] += 1
            elif pv < dealer_val:
                result = f"❌ Hand {idx+1}: Dealer wins. Lose {bet}"
                u["balance"] -= bet
                u["blackjack"]["losses"] += 1
            else:
                result = f"➖ Hand {idx+1}: Push (tie)."
            messages.append(result)
        save_data()
        final_embed = discord.Embed(
            title="🃏 Blackjack - Game Over",
            description="\n".join(messages) + f"\n\n**Dealer hand:** {self.game.fmt(self.game.dealer)} (Value: {dealer_val})",
            color=discord.Color.gold()
        )
        await self.message.edit(embed=final_embed, view=None)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return interaction.user.id == self.user.id

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.green)
    async def hit(self, interaction: discord.Interaction, button: Button):
        bust = self.game.hit()
        if bust:
            self.game.current_hand += 1
        if self.game.current_hand >= len(self.game.hands):
            await self.end_game()
        else:
            await interaction.response.edit_message(embed=self.embed(), view=self)
            await interaction.response.defer()

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.red)
    async def stand(self, interaction: discord.Interaction, button: Button):
        self.game.stand()
        self.game.current_hand += 1
        if self.game.current_hand >= len(self.game.hands):
            await self.end_game()
        else:
            await interaction.response.edit_message(embed=self.embed(), view=self)
            await interaction.response.defer()

    @discord.ui.button(label="Double", style=discord.ButtonStyle.blurple)
    async def double(self, interaction: discord.Interaction, button: Button):
        if not self.game.can_double():
            return await interaction.response.send_message("Cannot double now.", ephemeral=True)
        self.game.double()
        self.game.current_hand += 1
        if self.game.current_hand >= len(self.game.hands):
            await self.end_game()
        else:
            await interaction.response.edit_message(embed=self.embed(), view=self)
            await interaction.response.defer()

    @discord.ui.button(label="Split", style=discord.ButtonStyle.gray)
    async def split(self, interaction: discord.Interaction, button: Button):
        u = get_user(self.user.id)
        if not self.game.can_split():
            return await interaction.response.send_message("Cannot split now.", ephemeral=True)
        if u["balance"] < self.game.bets[self.game.current_hand]:
            return await interaction.response.send_message("Not enough balance to split.", ephemeral=True)
        u["balance"] -= self.game.bets[self.game.current_hand]
        self.game.split()
        save_data()
        await interaction.response.edit_message(embed=self.embed(), view=self)
        await interaction.response.defer()

# ---------- BLACKJACK COMMAND ----------
@bot.tree.command(name="bj")
async def bj(interaction: discord.Interaction, amount: int):
    u = get_user(interaction.user.id)
    if amount <= 0 or amount > u["balance"]:
        return await interaction.response.send_message("Invalid bet.", ephemeral=True)
    u["balance"] -= amount
    game = BlackjackGame(amount)
    view = BlackjackView(game, interaction.user)
    msg = await interaction.response.send_message(embed=view.embed(True), view=view)
    view.message = await interaction.original_response()
    save_data()

# ---------- CLAIM ----------
@bot.tree.command(name="claim")
async def claim(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    user = get_user(uid)
    if user["balance"] >= 1000:
        return await interaction.response.send_message(
            f"❌ You can only claim if your balance is below 1000 dabloons.\n💰 Your balance: {user['balance']}",
            ephemeral=True
        )
    now = datetime.utcnow()
    last_claim_str = user.get("last_claim")
    if last_claim_str:
        last_claim = datetime.fromisoformat(last_claim_str)
        remaining = (last_claim + timedelta(hours=1)) - now
        if remaining.total_seconds() > 0:
            minutes, seconds = divmod(int(remaining.total_seconds()), 60)
            return await interaction.response.send_message(
                f"⏳ Already claimed! Come back in **{minutes}m {seconds}s**.",
                ephemeral=True
            )
    reward = 1000
    user["balance"] += reward
    user["last_claim"] = now.isoformat()
    save_data()
    await interaction.response.send_message(
        f"🎉 You claimed **{reward} dabloons**!\n💰 Your new balance: {user['balance']}",
        ephemeral=True
    )

# ---------- SYNC ----------
@bot.tree.command(name="sync")
async def sync(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message(
            "❌ Only server admins can sync commands.",
            ephemeral=True
        )
    guild = discord.Object(id=GUILD_ID)
    await bot.tree.sync(guild=guild)
    await interaction.response.send_message("✅ Commands fully resynced.", ephemeral=True)

# ---------- READY ----------
@bot.event
async def on_ready():
    guild = discord.Object(id=GUILD_ID)
    await bot.tree.sync(guild=guild)
    print(f"Logged in as {bot.user} and synced commands to guild {GUILD_ID}")

bot.run(TOKEN)
