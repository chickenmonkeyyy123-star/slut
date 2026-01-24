import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
from datetime import datetime, timedelta

# =====================
# Bot setup
# =====================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# =====================
# Data storage (in-memory)
# =====================
user_data = {}
giveaways = {}

# =====================
# Helper functions
# =====================
def get_user_data(user_id):
    if user_id not in user_data:
        user_data[user_id] = {
            "balance": 1000,
            "blackjack_wins": 0,
            "blackjack_losses": 0,
            "coinflip_wins": 0,
            "coinflip_losses": 0
        }
    return user_data[user_id]

def load_data():
    pass

# =====================
# Blackjack game
# =====================
class BlackjackGame:
    def __init__(self, bet):
        self.deck = self.create_deck()
        random.shuffle(self.deck)
        self.player_hand = [self.deck.pop(), self.deck.pop()]
        self.dealer_hand = [self.deck.pop(), self.deck.pop()]
        self.bet = bet
        self.game_over = False

    def create_deck(self):
        suits = ["♠", "♥", "♦", "♣"]
        ranks = ["2","3","4","5","6","7","8","9","10","J","Q","K","A"]
        return [f"{r}{s}" for s in suits for r in ranks]

    def value(self, hand):
        total = 0
        aces = 0
        for card in hand:
            r = card[:-1]
            if r in ["J","Q","K"]:
                total += 10
            elif r == "A":
                total += 11
                aces += 1
            else:
                total += int(r)
        while total > 21 and aces:
            total -= 10
            aces -= 1
        return total

    def hit(self):
        self.player_hand.append(self.deck.pop())
        if self.value(self.player_hand) > 21:
            self.game_over = True
            return "bust"
        return "continue"

    def stand(self):
        while self.value(self.dealer_hand) < 17:
            self.dealer_hand.append(self.deck.pop())
        self.game_over = True

        p = self.value(self.player_hand)
        d = self.value(self.dealer_hand)

        if d > 21 or p > d:
            return "win"
        if p < d:
            return "lose"
        return "tie"

    def fmt(self, hand, hide=False):
        if hide:
            return f"Hidden, {hand[1]}"
        return ", ".join(hand)

# =====================
# Events
# =====================
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await bot.tree.sync()
    load_data()
    bot.loop.create_task(check_giveaways())

# =====================
# Giveaway checker
# =====================
async def check_giveaways():
    while True:
        await asyncio.sleep(10)
        now = datetime.now()
        ended = []

        for mid, g in giveaways.items():
            if now >= g["end"]:
                ended.append(mid)
                channel = bot.get_channel(g["channel"])
                if not channel:
                    continue

                if g["entries"]:
                    winners = random.sample(
                        g["entries"],
                        min(g["winners"], len(g["entries"]))
                    )
                    for w in winners:
                        get_user_data(w)["balance"] += g["amount"]
                    mentions = ", ".join(f"<@{w}>" for w in winners)
                    await channel.send(f"🎉 Giveaway ended! Winners: {mentions}")
                else:
                    await channel.send("Giveaway ended with no entries 😢")

        for mid in ended:
            giveaways.pop(mid, None)

# =====================
# Giveaway command
# =====================
@bot.tree.command(name="giveaway", description="Start a dabloons giveaway")
async def giveaway(
    interaction: discord.Interaction,
    amount: int,
    duration: int,
    winners: int = 1
):
    if amount <= 0 or duration <= 0 or winners <= 0:
        await interaction.response.send_message("Invalid values.", ephemeral=True)
        return

    embed = discord.Embed(
        title="🎉 Dabloons Giveaway 🎉",
        description=f"Amount: **{amount}**\nWinners: **{winners}**\nDuration: **{duration} minutes**",
        color=discord.Color.gold()
    )

    view = discord.ui.View()
    button = discord.ui.Button(label="Enter Giveaway", style=discord.ButtonStyle.green)

    async def enter(inter: discord.Interaction):
        g = giveaways[message.id]
        if inter.user.id not in g["entries"]:
            g["entries"].append(inter.user.id)
            await inter.response.send_message("You entered!", ephemeral=True)
        else:
            await inter.response.send_message("Already entered!", ephemeral=True)

    button.callback = enter
    view.add_item(button)

    await interaction.response.send_message(embed=embed, view=view)
    message = await interaction.original_response()

    giveaways[message.id] = {
        "amount": amount,
        "winners": winners,
        "entries": [],
        "end": datetime.now() + timedelta(minutes=duration),
        "channel": interaction.channel.id
    }

# =====================
# Blackjack command
# =====================
@bot.tree.command(name="bj", description="Play blackjack")
async def bj(interaction: discord.Interaction, amount: int):
    data = get_user_data(interaction.user.id)

    if amount <= 0:
        await interaction.response.send_message("Bet must be positive.", ephemeral=True)
        return
    if data["balance"] < amount:
        await interaction.response.send_message("Not enough dabloons.", ephemeral=True)
        return

    game = BlackjackGame(amount)

    embed = discord.Embed(
        title="♠️ Blackjack ♠️",
        description=(
            f"Your hand: {game.fmt(game.player_hand)} "
            f"({game.value(game.player_hand)})\n"
            f"Dealer: {game.fmt(game.dealer_hand, True)}"
        ),
        color=discord.Color.green()
    )

    view = discord.ui.View()
    hit = discord.ui.Button(label="Hit", style=discord.ButtonStyle.success)
    stand = discord.ui.Button(label="Stand", style=discord.ButtonStyle.danger)

    async def hit_cb(inter: discord.Interaction):
        result = game.hit()
        if result == "bust":
            data["balance"] -= amount
            data["blackjack_losses"] += 1
            await inter.response.edit_message(
                embed=discord.Embed(
                    title="💥 Busted!",
                    description=(
                        f"Your hand: {game.fmt(game.player_hand)} "
                        f"({game.value(game.player_hand)})\n"
                        f"Dealer: {game.fmt(game.dealer_hand)} "
                        f"({game.value(game.dealer_hand)})"
                    ),
                    color=discord.Color.red()
                ),
                view=None
            )
        else:
            embed.description = (
                f"Your hand: {game.fmt(game.player_hand)} "
                f"({game.value(game.player_hand)})\n"
                f"Dealer: {game.fmt(game.dealer_hand, True)}"
            )
            await inter.response.edit_message(embed=embed)

    async def stand_cb(inter: discord.Interaction):
        result = game.stand()

        if result == "win":
            data["balance"] += amount
            data["blackjack_wins"] += 1
            title = "🎉 You Win!"
            color = discord.Color.gold()
        elif result == "lose":
            data["balance"] -= amount
            data["blackjack_losses"] += 1
            title = "😢 You Lose"
            color = discord.Color.red()
        else:
            title = "🤝 Tie"
            color = discord.Color.blurple()

        await inter.response.edit_message(
            embed=discord.Embed(
                title=title,
                description=(
                    f"Your hand: {game.fmt(game.player_hand)} "
                    f"({game.value(game.player_hand)})\n"
                    f"Dealer: {game.fmt(game.dealer_hand)} "
                    f"({game.value(game.dealer_hand)})"
                ),
                color=color
            ),
            view=None
        )

    hit.callback = hit_cb
    stand.callback = stand_cb
    view.add_item(hit)
    view.add_item(stand)

    await interaction.response.send_message(embed=embed, view=view)

# =====================
# RUN BOT
# =====================
bot.run("YOUR_BOT_TOKEN_HERE")
