import discord
from discord import app_commands
from discord.ext import commands, tasks
from discord.ui import View, Button
import random
import json
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import asyncio

# ---------- LOAD ENV ----------
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = int(os.getenv("GUILD_ID", "1332118870181412936"))
if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN not found in .env")

# ---------- DATA ----------
DATA_FILE = "dabloon_data.json"
START_BALANCE = 1000

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
            "blackjack": {"wins":0,"losses":0},
            "coinflip": {"wins":0,"losses":0},
            "daily_claim": None
        }
        save_data()
    return data[uid]

# ---------- BOT ----------
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ---------- BLACKJACK ----------
class BlackjackGame:
    def __init__(self, bet):
        self.deck = self.new_deck()
        random.shuffle(self.deck)
        self.hands = [[self.deck.pop(), self.deck.pop()]]
        self.current_hand = 0
        self.bets = [bet]
        self.finished = [False]
        self.dealer = [self.deck.pop(), self.deck.pop()]

    def new_deck(self):
        suits = ["♠","♥","♦","♣"]
        ranks = ["2","3","4","5","6","7","8","9","10","J","Q","K","A"]
        deck = []
        for s in suits:
            for r in ranks:
                v = 11 if r=="A" else 10 if r in ["J","Q","K"] else int(r)
                deck.append({"r":r,"s":s,"v":v})
        return deck

    def value(self, hand):
        total = sum(c["v"] for c in hand)
        aces = sum(1 for c in hand if c["r"]=="A")
        while total > 21 and aces:
            total -= 10
            aces -= 1
        return total

    def is_soft(self, hand):
        return any(c["r"]=="A" for c in hand) and self.value(hand)<=21

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
        if len(hand)==2:
            self.bets[self.current_hand]*=2
            hand.append(self.deck.pop())
            self.finished[self.current_hand]=True
            return True
        return False

    def can_double(self):
        return len(self.hands[self.current_hand])==2

    def can_split(self):
        hand = self.hands[self.current_hand]
        return len(hand)==2 and hand[0]["r"]==hand[1]["r"]

    def split(self):
        if not self.can_split():
            return False
        hand = self.hands[self.current_hand]
        c1,c2 = hand
        self.hands[self.current_hand] = [c1,self.deck.pop()]
        self.hands.append([c2,self.deck.pop()])
        self.bets.append(self.bets[self.current_hand])
        self.finished.append(False)
        return True

    def dealer_play(self):
        while self.value(self.dealer) <17 or (self.value(self.dealer)==17 and self.is_soft(self.dealer)):
            self.dealer.append(self.deck.pop())

    def fmt(self, hand, hide=True):
        if hide:
            return "?, "+f"{hand[1]['r']}{hand[1]['s']}"
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
            elif dealer_val>21 or pv>dealer_val:
                result = f"✅ Hand {idx+1}: Win! Gain {bet}"
                u["balance"] += bet
                u["blackjack"]["wins"] += 1
            elif pv<dealer_val:
                result = f"❌ Hand {idx+1}: Dealer wins. Lose {bet}"
                u["balance"] -= bet
                u["blackjack"]["losses"] += 1
            else:
                result = f"➖ Hand {idx+1}: Push (tie)."
            messages.append(result)
        save_data()
        final_embed = discord.Embed(
            title="🃏 Blackjack - Game Over",
            description="\n".join(messages) + f"\n\n**Dealer hand:** {self.game.fmt(self.game.dealer, hide=False)} (Value: {dealer_val})",
            color=discord.Color.gold()
        )
        await self.message.edit(embed=final_embed, view=None)

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.green)
    async def hit(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Not your game.", ephemeral=True)
        bust = self.game.hit()
        if bust:
            self.game.current_hand += 1
        if self.game.current_hand >= len(self.game.hands):
            await self.end_game()
            return
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.red)
    async def stand(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Not your game.", ephemeral=True)
        self.game.stand()
        self.game.current_hand += 1
        if self.game.current_hand >= len(self.game.hands):
            await self.end_game()
            return
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="Double", style=discord.ButtonStyle.blurple)
    async def double(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Not your game.", ephemeral=True)
        if self.game.can_double():
            self.game.double()
            self.game.current_hand +=1
            if self.game.current_hand>=len(self.game.hands):
                await self.end_game()
                return
            await interaction.response.edit_message(embed=self.embed(), view=self)
        else:
            await interaction.response.send_message("Cannot double now.", ephemeral=True)

    @discord.ui.button(label="Split", style=discord.ButtonStyle.gray)
    async def split(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("Not your game.", ephemeral=True)
        u = get_user(self.user.id)
        if not self.game.can_split():
            return await interaction.response.send_message("Cannot split now.", ephemeral=True)
        if u["balance"]<self.game.bets[self.game.current_hand]:
            return await interaction.response.send_message("Not enough balance to split.", ephemeral=True)
        u["balance"] -= self.game.bets[self.game.current_hand]
        self.game.split()
        save_data()
        await interaction.response.edit_message(embed=self.embed(), view=self)

# ---------- COMMANDS ----------
@bot.tree.command(name="bj")
@app_commands.describe(amount="Amount to bet")
async def bj(interaction: discord.Interaction, amount: int):
    u = get_user(interaction.user.id)
    if amount<=0 or amount>u["balance"]:
        return await interaction.response.send_message("Invalid bet.", ephemeral=True)
    game = BlackjackGame(amount)
    view = BlackjackView(game, interaction.user)
    msg = await interaction.response.send_message(embed=view.embed(True), view=view)
    view.message = await interaction.original_response()

@bot.tree.command(name="cf")
@app_commands.describe(amount="Amount to bet", choice="Heads or Tails")
async def cf(interaction: discord.Interaction, amount: int, choice: str):
    u = get_user(interaction.user.id)
    choice = choice.lower()
    if choice not in ["heads","tails"]:
        return await interaction.response.send_message("Pick heads or tails.", ephemeral=True)
    if amount<=0 or amount>u["balance"]:
        return await interaction.response.send_message("Invalid amount.", ephemeral=True)
    result = random.choice(["heads","tails"])
    if choice==result:
        u["balance"] += amount
        u["coinflip"]["wins"] += 1
        outcome = f"✅ You won! {amount} added."
    else:
        u["balance"] -= amount
        u["coinflip"]["losses"] += 1
        outcome = f"❌ You lost! {amount} deducted."
    save_data()
    await interaction.response.send_message(f"The coin landed on **{result}**.\n{outcome}")

@bot.tree.command(name="leaderboard")
async def leaderboard(interaction: discord.Interaction):
    sorted_users = sorted(data.items(), key=lambda x:x[1]["balance"], reverse=True)[:10]
    desc = ""
    for i,(uid,u) in enumerate(sorted_users,1):
        wins = u["blackjack"]["wins"]+u["coinflip"]["wins"]
        losses = u["blackjack"]["losses"]+u["coinflip"]["losses"]
        member = interaction.guild.get_member(int(uid))
        name = member.name if member else uid
        desc += f"**{i}. {name}** - Balance: {u['balance']} | W/L: {wins}/{losses}\n"
    embed = discord.Embed(title="🏆 Leaderboard", description=desc, color=discord.Color.gold())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="claim")
async def claim(interaction: discord.Interaction):
    u = get_user(interaction.user.id)
    now = datetime.utcnow()
    last = u.get("daily_claim")
    if last:
        last_time = datetime.fromisoformat(last)
        if now - last_time < timedelta(hours=24):
            rem = timedelta(hours=24) - (now - last_time)
            h,m = divmod(int(rem.total_seconds()),3600)
            m //= 60
            return await interaction.response.send_message(f"You already claimed daily. Try again in {h}h {m}m.", ephemeral=True)
    u["balance"] += 500
    u["daily_claim"] = now.isoformat()
    save_data()
    await interaction.response.send_message("✅ You claimed 500 coins!")

# ---------- GIVEAWAY ----------
giveaways = {} # message.id: {"prize":str, "end":datetime, "entries":set}

@bot.tree.command(name="giveaway")
@app_commands.describe(prize="Prize to give away", duration="Duration in minutes")
async def giveaway(interaction: discord.Interaction, prize:str, duration:int):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("Only admins.", ephemeral=True)
    end = datetime.utcnow()+timedelta(minutes=duration)
    msg = await interaction.response.send_message(f"🎉 **GIVEAWAY:** {prize}\nReact to enter!\nEnds in {duration} minutes.")
    message = await interaction.original_response()
    await message.add_reaction("🎉")
    giveaways[message.id] = {"prize":prize,"end":end,"entries":set()}

@tasks.loop(seconds=30)
async def check_giveaways():
    to_remove=[]
    for mid,g in giveaways.items():
        if datetime.utcnow()>g["end"]:
            channel = bot.get_channel(bot.get_channel(GUILD_ID).id)
            try:
                msg = await channel.fetch_message(mid)
            except:
                to_remove.append(mid)
                continue
            users=[]
            for reaction in msg.reactions:
                if str(reaction.emoji)=="🎉":
                    async for u in reaction.users():
                        if not u.bot:
                            users.append(u)
            if users:
                winner=random.choice(users)
                await msg.reply(f"🎉 Giveaway ended! Winner: {winner.mention} | Prize: {g['prize']}")
            else:
                await msg.reply("No participants. Giveaway cancelled.")
            to_remove.append(mid)
    for mid in to_remove:
        giveaways.pop(mid,None)

# ---------- SYNC ----------
@bot.tree.command(name="sync")
async def sync(interaction: discord.Interaction):
    if not interaction.user.guild_permissions.administrator:
        return await interaction.response.send_message("❌ Only admins.", ephemeral=True)
    guild = discord.Object(id=GUILD_ID)
    await bot.tree.sync(guild=guild)
    await interaction.response.send_message("✅ Commands synced.", ephemeral=True)

# ---------- READY ----------
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    guild = discord.Object(id=GUILD_ID)
    await bot.tree.sync(guild=guild)
    print(f"✅ Commands synced to guild {GUILD_ID}")
    check_giveaways.start()

bot.run(TOKEN)
