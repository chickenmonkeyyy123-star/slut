import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button


import random
import json
import os
import asyncio

from dotenv import load_dotenv
from datetime import datetime, timedelta

# ---------- LOAD .ENV ----------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN not found in .env")

# ---------- CONFIG ----------
DATA_FILE = "dabloon_data.json"
MAX_LIMBO_MULTIPLIER = 100
START_BALANCE = 1000
GUILD_ID = 1332118870181412936

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
            "limbo": {"wins": 0, "losses": 0},
        }
        save_data()
        return data[uid]

    u = data[uid]

    # ---- BACKFILL MISSING STATS FOR OLD USERS ----
    u.setdefault("balance", START_BALANCE)
    u.setdefault("blackjack", {"wins": 0, "losses": 0})
    u.setdefault("coinflip", {"wins": 0, "losses": 0})
    u.setdefault("limbo", {"wins": 0, "losses": 0})

    save_data()
    return u


def total_wl(u):
    return (
        u.get("blackjack", {}).get("wins", 0)
        + u.get("coinflip", {}).get("wins", 0)
        + u.get("limbo", {}).get("wins", 0),
        u.get("blackjack", {}).get("losses", 0)
        + u.get("coinflip", {}).get("losses", 0)
        + u.get("limbo", {}).get("losses", 0),
    )


# ---------- BLACKJACK ----------
class BlackjackGame:
    def __init__(self, bet):
        self.base_bet = bet
        self.deck = self.new_deck()
        random.shuffle(self.deck)

        self.hands = [[self.deck.pop(), self.deck.pop()]]
        self.bets = [bet]
        self.finished = [False]
        self.doubled = [False]
        self.active_hand = 0

        self.dealer = [self.deck.pop(), self.deck.pop()]

    def new_deck(self):
        suits = ["♠", "♥", "♦", "♣"]
        ranks = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "J", "Q", "K", "A"]
        deck = []

        for s in suits:
            for r in ranks:
                value = 11 if r == "A" else 10 if r in ["J", "Q", "K"] else int(r)
                deck.append({"r": r, "s": s, "v": value})

        return deck

    def value(self, hand):
        total = sum(c["v"] for c in hand)
        aces = sum(1 for c in hand if c["r"] == "A")

        while total > 21 and aces:
            total -= 10
            aces -= 1

        return total

    def can_split(self):
        hand = self.hands[self.active_hand]
        return len(hand) == 2 and hand[0]["r"] == hand[1]["r"]

    def split(self):
        h = self.hands[self.active_hand]
        c1, c2 = h

        self.hands[self.active_hand] = [c1, self.deck.pop()]
        self.hands.insert(self.active_hand + 1, [c2, self.deck.pop()])

        self.bets.insert(self.active_hand + 1, self.base_bet)
        self.finished.insert(self.active_hand + 1, False)
        self.doubled.insert(self.active_hand + 1, False)

    def hit(self):
        hand = self.hands[self.active_hand]
        hand.append(self.deck.pop())

        if self.value(hand) > 21:
            self.finished[self.active_hand] = True

    def stand(self):
        self.finished[self.active_hand] = True

    def double(self):
        self.bets[self.active_hand] *= 2
        self.doubled[self.active_hand] = True
        self.hit()
        self.finished[self.active_hand] = True

    def next_hand(self):
        while self.active_hand < len(self.hands) and self.finished[self.active_hand]:
            self.active_hand += 1

    def dealer_play(self):
        while self.value(self.dealer) < 17:
            self.dealer.append(self.deck.pop())

    def fmt(self, hand):
        return ", ".join(f"{c['r']}{c['s']}" for c in hand)


class BlackjackView(View):
    def __init__(self, game, user):
        super().__init__(timeout=90)
        self.game = game
        self.user = user

    def embed(self, hide_dealer=True):
        desc = ""

        for i, hand in enumerate(self.game.hands):
            pointer = "➡️ " if i == self.game.active_hand else ""
            desc += (
                f"{pointer}**Hand {i + 1}:** {self.game.fmt(hand)} "
                f"(Value: {self.game.value(hand)}) | Bet: {self.game.bets[i]}\n"
            )

        dealer = (
            "?, " + f"{self.game.dealer[1]['r']}{self.game.dealer[1]['s']}"
            if hide_dealer
            else self.game.fmt(self.game.dealer)
        )

        return discord.Embed(
            title="🃏 Blackjack",
            description=f"{desc}\n**Dealer:** {dealer}",
            color=discord.Color.blurple(),
        )

    async def advance(self, interaction):
        self.game.next_hand()
        if self.game.active_hand >= len(self.game.hands):
            await self.end_game(interaction)
        else:
            await interaction.response.edit_message(embed=self.embed(), view=self)

    async def end_game(self, interaction):
        self.game.dealer_play()
        dv = self.game.value(self.game.dealer)
        u = get_user(self.user.id)

        embed = self.embed(hide_dealer=False)
        result = ""

        for i, hand in enumerate(self.game.hands):
            pv = self.game.value(hand)
            bet = self.game.bets[i]

            if pv > 21:
                u["balance"] -= bet
                u["blackjack"]["losses"] += 1
                result += f"❌ Hand {i + 1} busted\n"
            elif dv > 21 or pv > dv:
                u["balance"] += bet
                u["blackjack"]["wins"] += 1
                result += f"✅ Hand {i + 1} wins\n"
            elif pv < dv:
                u["balance"] -= bet
                u["blackjack"]["losses"] += 1
                result += f"❌ Hand {i + 1} loses\n"
            else:
                result += f"➖ Hand {i + 1} push\n"

        embed.description += "\n" + result
        save_data()
        self.stop()
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.green)
    async def hit(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Not your game.", ephemeral=True)
        self.game.hit()
        await self.advance(interaction)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.red)
    async def stand(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Not your game.", ephemeral=True)
        self.game.stand()
        await self.advance(interaction)

    @discord.ui.button(label="Double", style=discord.ButtonStyle.blurple)
    async def double(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Not your game.", ephemeral=True)

        u = get_user(self.user.id)
        bet = self.game.bets[self.game.active_hand]

        if u["balance"] < bet:
            return await interaction.response.send_message("Not enough balance to double.", ephemeral=True)

        self.game.double()
        await self.advance(interaction)

    @discord.ui.button(label="Split", style=discord.ButtonStyle.gray)
    async def split(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Not your game.", ephemeral=True)

        if not self.game.can_split():
            return await interaction.response.send_message("You can't split this hand.", ephemeral=True)

        u = get_user(self.user.id)

        if u["balance"] < self.game.base_bet:
            return await interaction.response.send_message("Not enough balance to split.", ephemeral=True)

        self.game.split()
        await interaction.response.edit_message(embed=self.embed(), view=self)

# ---------- LIMBO ----------
@bot.tree.command(name="limbo", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    amount="Bet amount",
    multiplier="Target multiplier (2, 3, 4, 5, etc — no decimals)",
)
async def limbo(interaction: discord.Interaction, amount: int, multiplier: int):
    u = get_user(interaction.user.id)

    if amount <= 0 or amount > u["balance"]:
        return await interaction.response.send_message("❌ Invalid bet amount.", ephemeral=True)

    if multiplier < 2 or multiplier > MAX_LIMBO_MULTIPLIER:
    return await interaction.response.send_message(
        f"❌ Multiplier must be between **2x** and **{MAX_LIMBO_MULTIPLIER}x**.",
        ephemeral=True,
    )

    win_chance = 1 / multiplier
    roll = random.random()

    if roll <= win_chance:
        profit = amount * (multiplier - 1)
        u["balance"] += profit
        u["limbo"]["wins"] += 1
        msg = (
            f"🚀 **LIMBO WIN!**\n"
            f"🎯 Target: **{multiplier}x**\n"
            f"💰 Profit: **+{profit} dabloons**"
        )
    else:
        u["balance"] -= amount
        u["limbo"]["losses"] += 1
        msg = (
            f"💥 **LIMBO CRASHED!**\n"
            f"🎯 Target: **{multiplier}x**\n"
            f"💸 Lost: **-{amount} dabloons**"
        )

    save_data()
    await interaction.response.send_message(msg)

# ---------- COINFLIP ----------
class CoinflipView(View):
    def __init__(self, challenger, opponent, amount, choice):
        super().__init__(timeout=60)
        self.challenger = challenger
        self.opponent = opponent
        self.amount = amount
        self.choice = choice.lower()
        self.result_sent = False

    @discord.ui.button(label="Accept Coinflip", style=discord.ButtonStyle.green)
    async def accept(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.opponent.id:
            return await interaction.response.send_message(
                "You are not the opponent.", ephemeral=True
            )

        if self.result_sent:
            return

        flip_result = random.choice(["heads", "tails"])

        u = get_user(self.challenger.id)
        o = get_user(self.opponent.id)

        if flip_result == self.choice:
            u["balance"] += self.amount
            o["balance"] -= self.amount
            u["coinflip"]["wins"] += 1
            o["coinflip"]["losses"] += 1
            msg = (
                f"🪙 **{flip_result.upper()}** — "
                f"{self.challenger.mention} won **{self.amount}** dabloons!"
            )
        else:
            u["balance"] -= self.amount
            o["balance"] += self.amount
            u["coinflip"]["losses"] += 1
            o["coinflip"]["wins"] += 1
            msg = (
                f"🪙 **{flip_result.upper()}** — "
                f"{self.opponent.mention} won **{self.amount}** dabloons!"
            )

        save_data()
        self.result_sent = True
        self.stop()
        await interaction.response.edit_message(content=msg, view=None)

# ---------- COMMANDS ----------
@bot.tree.command(name="bj")
async def bj(interaction: discord.Interaction, amount: int):
    u = get_user(interaction.user.id)

    if amount <= 0 or amount > u["balance"]:
        return await interaction.response.send_message(
            "Invalid bet.", ephemeral=True
        )

    game = BlackjackGame(amount)
    view = BlackjackView(game, interaction.user)
    await interaction.response.send_message(embed=view.embed(), view=view)


@bot.tree.command(name="cf")
@app_commands.describe(
    amount="Bet amount",
    choice="heads or tails",
    user="User to coinflip against (optional)",
)
async def cf(
    interaction: discord.Interaction,
    amount: int,
    choice: str,
    user: discord.User | None = None,
):
    choice = choice.lower()
    u = get_user(interaction.user.id)

    if choice not in ["heads", "tails"]:
        return await interaction.response.send_message(
            "heads or tails only.", ephemeral=True
        )

    if amount <= 0 or amount > u["balance"]:
        return await interaction.response.send_message(
            "Invalid bet.", ephemeral=True
        )

    if user and user.id == interaction.user.id:
        return await interaction.response.send_message(
            "You can't coinflip yourself.", ephemeral=True
        )

    # AI coinflip
    if not user:
        result = random.choice(["heads", "tails"])
        if result == choice:
            u["balance"] += amount
            u["coinflip"]["wins"] += 1
            msg = f"🪙 **{result.upper()}** — You won **{amount}**!"
        else:
            u["balance"] -= amount
            u["coinflip"]["losses"] += 1
            msg = f"🪙 **{result.upper()}** — You lost **{amount}**."
        save_data()
        return await interaction.response.send_message(msg)

    # PvP coinflip
    opponent = get_user(user.id)
    if opponent["balance"] < amount:
        return await interaction.response.send_message(
            f"{user.mention} doesn't have enough balance.", ephemeral=True
        )

    view = CoinflipView(interaction.user, user, amount, choice)
    await interaction.response.send_message(
        f"🪙 **Coinflip Challenge**\n"
        f"{interaction.user.mention} vs {user.mention}\n"
        f"Bet: **{amount} dabloons**\n"
        f"{user.mention}, click **Accept Coinflip**",
        view=view,
    )


@bot.tree.command(name="lb")
async def leaderboard(interaction: discord.Interaction):
    if not data:
        return await interaction.response.send_message("No data yet.")

    sorted_users = sorted(
        data.items(), key=lambda x: x[1]["balance"], reverse=True
    )

    lines = []
    for i, (uid, u) in enumerate(sorted_users[:10], start=1):
        w, l = total_wl(u)
        lines.append(
            f"**#{i}** <@{uid}> — 💰 {u['balance']} | 🏆 {w}W ❌ {l}L"
        )

    embed = discord.Embed(
        title="🏆 Leaderboard",
        description="\n".join(lines),
        color=discord.Color.gold(),
    )
    await interaction.response.send_message(embed=embed)

# ---------- GIVEAWAY ----------
class GiveawayView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.entries = set()

    @discord.ui.button(label="🎉 Enter Giveaway", style=discord.ButtonStyle.green)
    async def enter(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id in self.entries:
            return await interaction.response.send_message(
                "❌ You already entered this giveaway.", ephemeral=True
            )

        self.entries.add(interaction.user.id)
        await interaction.response.send_message(
            "✅ You have entered the giveaway!", ephemeral=True
        )


@bot.tree.command(name="giveaway")
@app_commands.describe(
    amount="Dabloons per winner",
    duration="Duration in seconds",
    winners="Number of winners",
)
async def giveaway(
    interaction: discord.Interaction,
    amount: int,
    duration: int,
    winners: int,
):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message(
            "❌ Only server admins can start a giveaway.", ephemeral=True
        )

    if amount <= 0 or duration <= 0 or winners <= 0:
        return await interaction.response.send_message(
            "❌ Amount, duration, and winners must be positive numbers.",
            ephemeral=True,
        )

    view = GiveawayView()
    embed = discord.Embed(
        title="🎉 Dabloons Giveaway!",
        description=(
            f"💰 **{amount} dabloons** per winner\n"
            f"👑 **{winners} winner(s)**\n"
            f"⏰ Ends in **{duration} seconds**\n\n"
            f"Click 🎉 below to enter!"
        ),
        color=discord.Color.gold(),
    )

    await interaction.response.send_message(embed=embed, view=view)
    message = await interaction.original_response()

    await asyncio.sleep(duration)

    if not view.entries:
        return await message.reply(
            "❌ Giveaway ended — no one entered."
        )

    selected = random.sample(
        list(view.entries),
        k=min(winners, len(view.entries)),
    )

    mentions = []
    for user_id in selected:
        get_user(user_id)["balance"] += amount
        save_data()
        mentions.append(f"<@{user_id}>")

    await message.reply(
        f"🎊 **GIVEAWAY ENDED!**\n"
        f"🏆 Winner(s): {', '.join(mentions)}\n"
        f"💰 Each winner received **{amount} dabloons**!"
    )

# ---------- CLAIM ----------
@bot.tree.command(name="claim")
async def claim(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    user = get_user(uid)

    if user["balance"] >= 1000:
        return await interaction.response.send_message(
            f"❌ You can only claim if your balance is below 1000 dabloons.\n"
            f"💰 Your balance: {user['balance']}",
            ephemeral=True,
        )

    now = datetime.utcnow()
    last_claim_str = user.get("last_claim")

    if last_claim_str:
        last_claim = datetime.fromisoformat(last_claim_str)
        remaining = (last_claim + timedelta(hours=1)) - now

        if remaining.total_seconds() > 0:
            minutes, seconds = divmod(
                int(remaining.total_seconds()), 60
            )
            return await interaction.response.send_message(
                f"⏳ Already claimed! Come back in **{minutes}m {seconds}s**.",
                ephemeral=True,
            )

    reward = 1000
    user["balance"] += reward
    user["last_claim"] = now.isoformat()
    save_data()

    await interaction.response.send_message(
        f"🎉 You claimed **{reward} dabloons**!\n"
        f"💰 Your new balance: {user['balance']}",
        ephemeral=True,
    )

# ---------- SYNC ----------
@bot.tree.command(name="sync")
async def sync(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message(
            "❌ Only server admins can sync commands.", ephemeral=True
        )

    guild = discord.Object(id=GUILD_ID)
    await bot.tree.sync(guild=guild)

    await interaction.response.send_message(
        "✅ Commands fully resynced.", ephemeral=True
    )

# ---------- READY ----------
@bot.event
async def on_ready():
    guild = discord.Object(id=GUILD_ID)
    await bot.tree.sync(guild=guild)
    print(
        f"Logged in as {bot.user} and synced commands to guild {GUILD_ID}"
    )


bot.run(TOKEN)




