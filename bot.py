import os
import json
import random
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv

import discord
from discord import app_commands
from discord.ext import commands
from discord.ui import View, Button

# ==========================================
# ---------- CONFIGURATION & LOAD ----------
# ==========================================

load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN not found in .env")

DATA_FILE = "dabloon_data.json"
MAX_LIMBO_MULTIPLIER = 100
START_BALANCE = 1000
GUILD_ID = 1332118870181412936

# ==========================================
# ---------- DATA CORE FUNCTIONS -----------
# ==========================================

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
            "chicken": {"wins": 0, "losses": 0},
            "limbo": {"wins": 0, "losses": 0}, # Added for logic consistency
        }
        save_data()

    # Ensure all users have necessary stats for all games
    data[uid].setdefault("chicken", {"wins": 0, "losses": 0})
    data[uid].setdefault("limbo", {"wins": 0, "losses": 0})

    return data[uid]

def total_wl(u):
    wins = (
        u.get("blackjack", {}).get("wins", 0) +
        u.get("coinflip", {}).get("wins", 0) +
        u.get("chicken", {}).get("wins", 0) +
        u.get("limbo", {}).get("wins", 0)
    )
    losses = (
        u.get("blackjack", {}).get("losses", 0) +
        u.get("coinflip", {}).get("losses", 0) +
        u.get("chicken", {}).get("losses", 0) +
        u.get("limbo", {}).get("losses", 0)
    )
    return wins, losses

# ==========================================
# ---------- BLACKJACK GAME LOGIC ----------
# ==========================================

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
                v = 11 if r == "A" else 10 if r in ["J", "Q", "K"] else int(r)
                deck.append({"r": r, "s": s, "v": v})
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
                f"{pointer}**Hand {i+1}:** {self.game.fmt(hand)} "
                f"(Value: {self.game.value(hand)}) | Bet: {self.game.bets[i]}\n"
            )

        dealer = (
            "?, " + f"{self.game.dealer[1]['r']}{self.game.dealer[1]['s']}"
            if hide_dealer else self.game.fmt(self.game.dealer)
        )

        return discord.Embed(
            title="🃏 Blackjack",
            description=f"{desc}\n**Dealer:** {dealer}",
            color=discord.Color.blurple()
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
                u["blackjack"]["losses"] += 1
                result += f"❌ Hand {i+1} busted\n"

            elif dv > 21 or pv > dv:
                u["balance"] += bet * 2
                u["blackjack"]["wins"] += 1
                result += f"✅ Hand {i+1} wins\n"

            elif pv < dv:
                u["blackjack"]["losses"] += 1
                result += f"❌ Hand {i+1} loses\n"

            else:
                u["balance"] += bet
                result += f"➖ Hand {i+1} push\n"

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

        u["balance"] -= bet
        self.game.double()
        save_data()
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

        u["balance"] -= self.game.base_bet
        self.game.split()
        save_data()
        await interaction.response.edit_message(embed=self.embed(), view=self)


# ==========================================
# ---------- COINFLIP COMPONENTS -----------
# ==========================================

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
            return await interaction.response.send_message("You are not the opponent.", ephemeral=True)
        if self.result_sent:
            return

        flip = random.choice(["heads", "tails"])
        u = get_user(self.challenger.id)
        o = get_user(self.opponent.id)

        if flip == self.choice:
            u["balance"] += self.amount
            o["balance"] -= self.amount
            u["coinflip"]["wins"] += 1
            o["coinflip"]["losses"] += 1
            msg = f"🪙 **{flip.upper()}** — {self.challenger.mention} won **{self.amount}**!"
        else:
            u["balance"] -= self.amount
            o["balance"] += self.amount
            u["coinflip"]["losses"] += 1
            o["coinflip"]["wins"] += 1
            msg = f"🪙 **{flip.upper()}** — {self.opponent.mention} won **{self.amount}**!"

        save_data()
        self.result_sent = True
        self.stop()
        await interaction.response.edit_message(content=msg, view=None)

# ==========================================
# ---------- GIVEAWAY COMPONENTS -----------
# ==========================================

class GiveawayView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.entries = set()

    @discord.ui.button(label="🎉 Enter Giveaway", style=discord.ButtonStyle.green)
    async def enter(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id in self.entries:
            await interaction.response.send_message("❌ You already entered this giveaway.", ephemeral=True)
            return
        self.entries.add(interaction.user.id)
        await interaction.response.send_message("✅ You have entered the giveaway!", ephemeral=True)

# ==========================================
# ---------- CHICKEN GAME LOGIC ------------
# ==========================================
import random

class ChickenGame:
    def __init__(self, bet, user):
        self.bet = bet
        self.multiplier = 1.0
        self.finished = False

        if user.id == 886841288211726356:
            self.crash = 10.0
        else:
            self.crash = min((1 / random.random()) * 0.97, 10.0)

    def boost(self):
        if self.finished:
            return False
        self.multiplier += 0.5
        if self.multiplier >= self.crash:
            self.finished = True
            return False
        return True

    def cashout(self):
        self.finished = True
        return int(self.bet * self.multiplier)


class ChickenView(View):
    def __init__(self, game, user):
        super().__init__(timeout=60)
        self.game = game
        self.user = user
        self.active = True

    def embed(self):
        return discord.Embed(
            title="🐔 Chicken Game",
            description=(
                f"💰 Bet: **{self.game.bet}**\n"
                f"🚀 Multiplier: **{self.game.multiplier:.1f}x**\n"
                f"⚠️ Crash at: **???**"
            ),
            color=discord.Color.orange(),
        )

    @discord.ui.button(label="⬆️ Boost", style=discord.ButtonStyle.green)
    async def boost(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Not your game.", ephemeral=True)
        if not self.active:
            return

        alive = self.game.boost()

        if alive:
            await interaction.response.edit_message(embed=self.embed(), view=self)
        else:
            u = get_user(self.user.id)
            u["balance"] -= self.game.bet
            u["chicken"]["losses"] += 1
            save_data()

            self.active = False
            self.stop()
            await interaction.response.edit_message(
                content=f"💥 **CRASHED at {self.game.multiplier:.1f}x** — You lost **{self.game.bet} dabloons**.",
                embed=None,
                view=None
            )

    @discord.ui.button(label="💰 Cash Out", style=discord.ButtonStyle.blurple)
    async def cashout(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Not your game.", ephemeral=True)
        if not self.active:
            return

        winnings = self.game.cashout()
        u = get_user(self.user.id)
        u["balance"] += winnings
        u["chicken"]["wins"] += 1
        save_data()

        self.active = False
        self.stop()
        await interaction.response.edit_message(
            content=f"🏆 **Cashed out at {self.game.multiplier:.1f}x** — You won **{winnings} dabloons!**",
            embed=None,
            view=None
        )




# ==========================================
# ---------- POKER GAME LOGIC ------------
# ==========================================

import random
import discord
from discord.ui import View, Button

RANKS = "23456789TJQKA"
SUITS = "♠♥♦♣"

def new_deck():
    return [r+s for r in RANKS for s in SUITS]

def rv(r):
    return RANKS.index(r)

def hand_rank(cards):
    vals = sorted([rv(c[0]) for c in cards], reverse=True)
    suits = [c[1] for c in cards]
    counts = {v: vals.count(v) for v in set(vals)}
    freq = sorted(counts.values(), reverse=True)

    flush = len(set(suits)) == 1
    straight = vals == list(range(vals[0], vals[0]-5, -1))

    if straight and flush: return (8, vals)
    if 4 in freq: return (7, vals)
    if freq == [3,2]: return (6, vals)
    if flush: return (5, vals)
    if straight: return (4, vals)
    if 3 in freq: return (3, vals)
    if freq == [2,2,1]: return (2, vals)
    if 2 in freq: return (1, vals)
    return (0, vals)

class PokerGame:
    def __init__(self, players, buyin):
        self.players = players
        self.active = players.copy()
        self.buyin = buyin
        self.contributions = {p.id: buyin for p in players}
        self.pot = buyin * len(players)
        self.deck = new_deck()
        random.shuffle(self.deck)
        self.hands = {p.id: [self.deck.pop(), self.deck.pop()] for p in players}
        self.board = []
        self.turn = 0
        self.round = 0

    def deal_next(self):
        self.round += 1
        if self.round == 1:
            self.board += [self.deck.pop() for _ in range(3)]
        elif self.round in (2, 3):
            self.board.append(self.deck.pop())

# ------------------------------------------
# ---------- POKER VIEW --------------------
# ------------------------------------------

class PokerView(View):
    def __init__(self, game, channel):
        super().__init__(timeout=180)
        self.game = game
        self.channel = channel

    def current(self):
        return self.game.active[self.game.turn % len(self.game.active)]

    def embed(self):
        return discord.Embed(
            title="♠️ Texas Hold’em",
            description=(
                f"🃏 Board: {' '.join(self.game.board) or '—'}\n"
                f"💰 Pot: {self.game.pot}\n"
                f"➡️ Turn: {self.current().mention}"
            ),
            color=discord.Color.gold()
        )

    async def next_turn(self):
        self.game.turn += 1
        if self.game.turn % len(self.game.active) == 0:
            self.game.deal_next()
        if self.game.round >= 4 or len(self.game.active) == 1:
            await self.finish()
        else:
            await self.channel.send(embed=self.embed(), view=self)

    async def finish(self):
        ranks = {p.id: hand_rank(self.game.hands[p.id] + self.game.board) for p in self.game.active}
        best = max(ranks.values())
        winners = [p for p in self.game.active if ranks[p.id] == best]
        payout = self.game.pot // len(winners)

        for w in winners:
            get_user(w.id)["balance"] += payout
        save_data()

        desc = f"🃏 Board: {' '.join(self.game.board)}\n\n"
        for p in self.game.players:
            spent = self.game.contributions[p.id]
            earned = payout if p in winners else 0
            profit = earned - spent
            sign = "+" if profit >= 0 else ""
            desc += f"{p.mention}: {' '.join(self.game.hands[p.id])}\n💵 **{sign}{profit} dabloons**\n\n"

        await self.channel.send(embed=discord.Embed(title="🏆 Poker Showdown", description=desc, color=discord.Color.green()))
        self.stop()

    @discord.ui.button(label="Check / Call", style=discord.ButtonStyle.green)
    async def call(self, interaction: discord.Interaction, _):
        if interaction.user != self.current():
            return await interaction.response.send_message("Not your turn.", ephemeral=True)
        await interaction.response.defer()
        await self.next_turn()

    @discord.ui.button(label="Raise", style=discord.ButtonStyle.blurple)
    async def raise_bet(self, interaction: discord.Interaction, _):
        if interaction.user != self.current():
            return await interaction.response.send_message("Not your turn.", ephemeral=True)

        u = get_user(interaction.user.id)
        if u["balance"] < self.game.buyin:
            return await interaction.response.send_message("Not enough balance.", ephemeral=True)

        u["balance"] -= self.game.buyin
        self.game.pot += self.game.buyin
        self.game.contributions[interaction.user.id] += self.game.buyin
        save_data()

        await interaction.response.defer()
        await self.next_turn()

    @discord.ui.button(label="Fold", style=discord.ButtonStyle.red)
    async def fold(self, interaction: discord.Interaction, _):
        if interaction.user != self.current():
            return await interaction.response.send_message("Not your turn.", ephemeral=True)

        self.game.active.remove(interaction.user)
        await interaction.response.defer()
        await self.next_turn()





class PokerRequestView(View):
    def __init__(self, challenger, opponents, buyin):
        super().__init__(timeout=120)
        self.challenger = challenger
        self.opponents = {u.id: u for u in opponents}
        self.buyin = buyin
        self.accepted = {challenger.id}  # challenger auto-accepts
        self.done = False

    async def try_start(self, interaction):
        # Start game if all accepted
        if set(self.accepted) == set(self.opponents.keys()) | {self.challenger.id}:
            self.done = True
            # Deduct buy-ins
            all_players = [self.challenger] + list(self.opponents.values())
            for p in all_players:
                get_user(p.id)["balance"] -= self.buyin
            save_data()

            # Initialize game
            game = PokerGame(all_players, self.buyin)
            view = PokerView(game, interaction.channel)

            # DM hands
            for p in all_players:
                try:
                    await p.send(embed=discord.Embed(
                        title="🂡 Your Poker Hand",
                        description=" ".join(game.hands[p.id]),
                        color=discord.Color.blurple()
                    ))
                except discord.Forbidden:
                    # Refund everyone if DM fails
                    for r in all_players:
                        get_user(r.id)["balance"] += self.buyin
                    save_data()
                    await interaction.channel.send(f"⚠️ Could not DM {p.mention}. Game cancelled.")
                    self.stop()
                    return

            # Send main game message
            await interaction.channel.send(embed=view.embed(), view=view)
            self.stop()

    @discord.ui.button(label="Accept Poker", style=discord.ButtonStyle.green)
    async def accept(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in self.opponents:
            return await interaction.response.send_message("You're not invited to this game.", ephemeral=True)
        if interaction.user.id in self.accepted:
            return await interaction.response.send_message("You already accepted.", ephemeral=True)

        self.accepted.add(interaction.user.id)
        await interaction.response.send_message("✅ You accepted the poker game!", ephemeral=True)
        await self.try_start(interaction)

    @discord.ui.button(label="Decline Poker", style=discord.ButtonStyle.red)
    async def decline(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in self.opponents:
            return await interaction.response.send_message("You're not invited to this game.", ephemeral=True)
        self.done = True
        await interaction.channel.send(f"❌ {interaction.user.mention} declined the poker game. Game cancelled.")
        self.stop()



# ==========================================
# ---------- BOT INITIALIZATION ------------
# ==========================================

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# ==========================================
# ---------- TREE SLASH COMMANDS -----------
# ==========================================

@bot.tree.command(name="bj", guild=discord.Object(id=GUILD_ID))
async def bj(interaction: discord.Interaction, amount: int):
    u = get_user(interaction.user.id)

    if amount <= 0 or amount > u["balance"]:
        return await interaction.response.send_message("Invalid bet.", ephemeral=True)

    # 🔒 TAKE MONEY UPFRONT
    u["balance"] -= amount
    save_data()

    game = BlackjackGame(amount)
    view = BlackjackView(game, interaction.user)
    await interaction.response.send_message(embed=view.embed(), view=view)


@bot.tree.command(name="cf", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(amount="Bet", choice="heads or tails", user="Opponent (optional)")
async def cf(interaction: discord.Interaction, amount: int, choice: str, user: discord.User | None = None):
    choice = choice.lower()
    u = get_user(interaction.user.id)

    if choice not in ["heads", "tails"]:
        return await interaction.response.send_message("heads or tails only.", ephemeral=True)
    if amount <= 0 or amount > u["balance"]:
        return await interaction.response.send_message("Invalid bet.", ephemeral=True)
    if user and user.id == interaction.user.id:
        return await interaction.response.send_message("You can't coinflip yourself.", ephemeral=True)

    if not user:
        flip = random.choice(["heads", "tails"])
        if flip == choice:
            u["balance"] += amount
            u["coinflip"]["wins"] += 1
            msg = f"🪙 **{flip.upper()}** — You won **{amount}**!"
        else:
            u["balance"] -= amount
            u["coinflip"]["losses"] += 1
            msg = f"🪙 **{flip.upper()}** — You lost **{amount}**."
        save_data()
        return await interaction.response.send_message(msg)

    opponent = get_user(user.id)
    if opponent["balance"] < amount:
        return await interaction.response.send_message(f"{user.mention} doesn't have enough balance.", ephemeral=True)

    view = CoinflipView(interaction.user, user, amount, choice)
    await interaction.response.send_message(
        f"🪙 **Coinflip Challenge**\n{interaction.user.mention} vs {user.mention}\n"
        f"Bet: **{amount} dabloons**\n{user.mention}, click **Accept Coinflip**",
        view=view
    )

@bot.tree.command(name="giveaway")
@app_commands.describe(amount="Dabloons per winner", duration="Duration in seconds", winners="Number of winners")
async def giveaway(interaction: discord.Interaction, amount: int, duration: int, winners: int):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Only server admins can start a giveaway.", ephemeral=True)
    if amount <= 0 or duration <= 0 or winners <= 0:
        return await interaction.response.send_message("❌ Amount, duration, and winners must be positive numbers.", ephemeral=True)
    
    view = GiveawayView()
    embed = discord.Embed(
        title="🎉 Dabloons Giveaway!",
        description=f"💰 **{amount} dabloons** per winner\n👑 **{winners} winner(s)**\n⏰ Ends in **{duration} seconds**\n\nClick 🎉 below to enter!",
        color=discord.Color.gold()
    )
    await interaction.response.send_message(embed=embed, view=view)
    message = await interaction.original_response()
    await asyncio.sleep(duration)
    
    if not view.entries:
        return await message.reply("❌ Giveaway ended — no one entered.")
        
    selected = random.sample(list(view.entries), k=min(winners, len(view.entries)))
    mentions = []
    for user_id in selected:
        get_user(user_id)["balance"] += amount
        save_data()
        mentions.append(f"<@{user_id}>")
    await message.reply(f"🎊 **GIVEAWAY ENDED!**\n🏆 Winner(s): {', '.join(mentions)}\n💰 Each winner received **{amount} dabloons**!")

@bot.tree.command(name="limbo", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(amount="Bet amount", multiplier="Target multiplier (2–100)")
async def limbo(interaction: discord.Interaction, amount: int, multiplier: int):
    u = get_user(interaction.user.id)

    if amount <= 0 or amount > u["balance"]:
        return await interaction.response.send_message("❌ Invalid bet amount.", ephemeral=True)

    if multiplier < 2 or multiplier > MAX_LIMBO_MULTIPLIER:
        return await interaction.response.send_message(f"❌ Multiplier must be between **2x** and **{MAX_LIMBO_MULTIPLIER}x**.", ephemeral=True)

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

@bot.tree.command(name="chicken", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(amount="Bet amount")
async def chicken(interaction: discord.Interaction, amount: int):
    u = get_user(interaction.user.id)

    if amount <= 0:
        return await interaction.response.send_message("❌ Invalid bet.", ephemeral=True)

    if amount > u["balance"]:
        return await interaction.response.send_message("❌ You don't have enough balance.", ephemeral=True)

    game = ChickenGame(amount)
    view = ChickenView(game, interaction.user)
    await interaction.response.send_message(embed=view.embed(), view=view)

@bot.tree.command(name="lb", guild=discord.Object(id=GUILD_ID))
async def leaderboard(interaction: discord.Interaction):
    if not data:
        return await interaction.response.send_message("No data yet.")
    sorted_users = sorted(data.items(), key=lambda x: x[1]["balance"], reverse=True)
    lines = []
    for i, (uid, u) in enumerate(sorted_users[:10], start=1):
        w, l = total_wl(u)
        lines.append(f"**#{i}** <@{uid}> — 💰 {u['balance']} | 🏆 {w}W ❌ {l}L")
    embed = discord.Embed(title="🏆 Leaderboard", description="\n".join(lines), color=discord.Color.gold())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="claim", guild=discord.Object(id=GUILD_ID))
async def claim(interaction: discord.Interaction):
    user = get_user(interaction.user.id)
    if user["balance"] >= 1000:
        return await interaction.response.send_message("Balance too high to claim.", ephemeral=True)

    now = datetime.utcnow()
    last = user.get("last_claim")
    if last:
        last = datetime.fromisoformat(last)
        if now - last < timedelta(hours=1):
            remaining = timedelta(hours=1) - (now - last)
            m, s = divmod(int(remaining.total_seconds()), 60)
            return await interaction.response.send_message(f"⏳ Come back in {m}m {s}s.", ephemeral=True)

    user["balance"] += 1000
    user["last_claim"] = now.isoformat()
    save_data()
    await interaction.response.send_message("🎉 You claimed **1000 dabloons**!", ephemeral=True)



@bot.tree.command(name="tip", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(
    amount="Amount of dabloons to tip",
    user="User to tip"
)
async def tip(interaction: discord.Interaction, amount: int, user: discord.User):
    if amount <= 0:
        return await interaction.response.send_message(
            "❌ Tip amount must be positive.",
            ephemeral=True
        )

    if user.id == interaction.user.id:
        return await interaction.response.send_message(
            "❌ You can’t tip yourself.",
            ephemeral=True
        )

    sender = get_user(interaction.user.id)
    receiver = get_user(user.id)

    if sender["balance"] < amount:
        return await interaction.response.send_message(
            "❌ You don’t have enough dabloons.",
            ephemeral=True
        )

    sender["balance"] -= amount
    receiver["balance"] += amount
    save_data()

    await interaction.response.send_message(
        f"💸 **{interaction.user.mention} tipped {user.mention} `{amount}` dabloons!**"
    )



@bot.tree.command(name="p", guild=discord.Object(id=GUILD_ID))
async def poker(interaction: discord.Interaction, amount: int,
                user1: discord.User | None = None,
                user2: discord.User | None = None,
                user3: discord.User | None = None):

    players = [u for u in (user1, user2, user3) if u]
    if not 1 <= len(players) <= 3:
        return await interaction.response.send_message("You must invite 1–3 opponents.", ephemeral=True)

    all_players = [interaction.user] + players

    # Check balances before sending request
    for p in all_players:
        if get_user(p.id)["balance"] < amount:
            return await interaction.response.send_message(f"{p.mention} lacks balance.", ephemeral=True)

    view = PokerRequestView(interaction.user, players, amount)
    await interaction.response.send_message(
        f"🃏 {interaction.user.mention} has challenged {', '.join(u.mention for u in players)} to a poker game!\n"
        f"💰 Buy-in: **{amount} dabloons** each\n\n"
        f"All invited players must accept to start the game.",
        view=view
    )


@bot.tree.command(name="give", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(amount="Amount of dabloons to give", user="User to receive dabloons")
async def give(interaction: discord.Interaction, amount: int, user: discord.User):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Only admins can use this command.", ephemeral=True)
    
    if amount <= 0:
        return await interaction.response.send_message("❌ Amount must be positive.", ephemeral=True)

    u = get_user(user.id)
    u["balance"] += amount
    save_data()
    await interaction.response.send_message(f"✅ Gave **{amount} dabloons** to {user.mention}.")

@bot.tree.command(name="take", guild=discord.Object(id=GUILD_ID))
@app_commands.describe(amount="Amount of dabloons to take", user="User to remove dabloons from")
async def take(interaction: discord.Interaction, amount: int, user: discord.User):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Only admins can use this command.", ephemeral=True)
    
    if amount <= 0:
        return await interaction.response.send_message("❌ Amount must be positive.", ephemeral=True)

    u = get_user(user.id)
    u["balance"] = max(u["balance"] - amount, 0)
    save_data()
    await interaction.response.send_message(f"✅ Took **{amount} dabloons** from {user.mention}.")



# ==========================================
# ---------- BOT READY & STARTUP -----------
# ==========================================

@bot.event
async def on_ready():
    guild = discord.Object(id=GUILD_ID)
    await bot.tree.sync(guild=guild)
    print(f"Logged in as {bot.user}")

bot.run(TOKEN)


















