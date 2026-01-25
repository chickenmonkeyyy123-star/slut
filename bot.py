import discord
from discord.ext import commands, tasks
import json
import os
import asyncio
import random
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv()
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
GUILD_ID = 1332118870181412936

# Initialize bot with intents for message content
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

# Data file path
DATA_FILE = 'dabloon_data.json'
CLAIM_COOLDOWN_HOURS = 1

# Load or create data
def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, 'r') as f:
        return json.load(f)

def save_data():
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

# Initialize data
data = load_data()

# Helper: ensure user data exists
def get_user_data(user_id):
    user_id_str = str(user_id)
    if user_id_str not in data:
        data[user_id_str] = {
            "balance": 1000,
            "wins": 0,
            "losses": 0,
            "last_claim": "1970-01-01T00:00:00",
            "blackjack": None
        }
    return data[user_id_str]

# Clear all previous commands and sync fresh commands to guild
async def reset_commands():
    await bot.tree.clear_commands(guild=discord.Object(id=GUILD_ID))
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    print("Commands wiped and synced to guild.")

# Blackjack game class with full rules
class BlackjackGame:
    def __init__(self, ctx, user_id, bet):
        self.ctx = ctx
        self.user_id = user_id
        self.bet = bet
        self.deck = self.create_deck()
        self.player_hands = [[]]  # support split
        self.dealer_hand = []
        self.player_hands_total = [0]
        self.active_hand_index = 0
        self.game_over = False
        self.result = None
        self.split = False

    def create_deck(self, num_decks=6):
        ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        suits = ['♠', '♥', '♦', '♣']
        deck = []
        for _ in range(num_decks):
            for suit in suits:
                for rank in ranks:
                    deck.append((rank, suit))
        random.shuffle(deck)
        return deck

    def deal_card(self, hand):
        card = self.deck.pop()
        hand.append(card)

    def hand_value(self, hand):
        total = 0
        aces = 0
        for rank, suit in hand:
            if rank in ['J', 'Q', 'K']:
                total += 10
            elif rank == 'A':
                total += 11
                aces += 1
            else:
                total += int(rank)
        while total > 21 and aces:
            total -= 10
            aces -= 1
        return total

    def start(self):
        # Deal initial cards
        for _ in range(2):
            self.deal_card(self.player_hands[0])
            self.deal_card(self.dealer_hand)
        # Handle split if possible
        if self.can_split():
            self.split = True

    def can_split(self):
        # Check if first two cards are same rank for split
        hand = self.player_hands[0]
        return len(hand) == 2 and hand[0][0] == hand[1][0]

    def get_hand_str(self, hand, hide_dealer=False):
        if hide_dealer:
            return "?? " + ' '.join([f"{r}{s}" for r,s in hand[1:]])
        else:
            return ' '.join([f"{r}{s}" for r,s in hand])

    async def play(self):
        self.start()
        # Check for blackjack
        if self.hand_value(self.player_hands[0]) == 21:
            self.result = 'blackjack'
            await self.resolve()
            return

        # Player turn for each hand
        for idx in range(len(self.player_hands)):
            self.active_hand_index = idx
            while True:
                hand = self.player_hands[idx]
                total = self.hand_value(hand)
                embed = discord.Embed(title="Blackjack", color=0x00ff00)
                embed.add_field(name="Your Hand", value=self.get_hand_str(hand) + f" (Total: {total})")
                embed.add_field(name="Dealer", value=self.get_hand_str(self.dealer_hand, hide_dealer=True))
                embed.set_footer(text="React with ✅ Hit | 🛑 Stand | 🔄 Double | ❌ Surrender" )
                msg = await self.ctx.send(embed=embed)

                for emoji in ['✅', '🛑', '🔄', '❌']:
                    await msg.add_reaction(emoji)

                def check(reaction, user):
                    return user.id == self.user_id and str(reaction.emoji) in ['✅', '🛑', '🔄', '❌'] and reaction.message.id == msg.id

                try:
                    reaction, user = await bot.wait_for('reaction_add', timeout=60.0, check=check)
                except asyncio.TimeoutError:
                    # Default to stand
                    break

                emoji = str(reaction.emoji)
                if emoji == '✅':
                    # Hit
                    self.deal_card(hand)
                    total = self.hand_value(hand)
                    if total > 21:
                        await self.ctx.send(f"Bust! Your hand: {self.get_hand_str(hand)} Total: {total}")
                        break
                elif emoji == '🛑':
                    # Stand
                    break
                elif emoji == '🔄':
                    # Double
                    user_data = get_user_data(self.user_id)
                    if user_data['balance'] >= self.bet:
                        user_data['balance'] -= self.bet
                        self.bet *= 2
                        self.deal_card(hand)
                        total = self.hand_value(hand)
                        if total > 21:
                            await self.ctx.send(f"Bust after double! Your hand: {self.get_hand_str(hand)} Total: {total}")
                        break
                    else:
                        await self.ctx.send("Not enough dabloons to double.")
                elif emoji == '❌':
                    # Surrender
                    user_data = get_user_data(self.user_id)
                    user_data['balance'] += self.bet // 2
                    self.result = 'surrender'
                    await self.resolve()
                    return

        # Dealer's turn
        self.dealer_play()
        await self.resolve()

    def dealer_play(self):
        while self.hand_value(self.dealer_hand) < 17:
            self.deal_card(self.dealer_hand)

    async def resolve(self):
        # Final reveal
        dealer_total = self.hand_value(self.dealer_hand)
        results = []
        for hand in self.player_hands:
            total = self.hand_value(hand)
            user_data = get_user_data(self.user_id)
            if self.result == 'surrender':
                # Already handled
                break
            if total > 21:
                # Bust
                user_data['losses'] += 1
            elif dealer_total > 21 or total > dealer_total:
                # Win
                winnings = self.bet * 2
                user_data['balance'] += winnings
                user_data['wins'] += 1
            elif total == dealer_total:
                # Push
                user_data['balance'] += self.bet
            else:
                # Loss
                user_data['losses'] += 1
        save_data()
        # Show final hands
        embed = discord.Embed(title="Final Results", color=0x00ff00)
        embed.add_field(name="Your Hand(s)", value='')
        for idx, hand in enumerate(self.player_hands):
            total = self.hand_value(hand)
            embed.add_field(name=f"Hand {idx+1}", value=f"{self.get_hand_str(hand)} (Total: {total})", inline=False)
        embed.add_field(name="Dealer", value=self.get_hand_str(self.dealer_hand))
        await self.ctx.send(embed=embed)

# Commands

@bot.event
async def on_ready():
    print(f'Logged in as {bot.user}')
    await reset_commands()

# /bj command
@bot.tree.command(name='bj', description='Start a blackjack game')
async def bj(interaction: discord.Interaction, amount: int):
    user_id = interaction.user.id
    user_data = get_user_data(user_id)
    if amount <= 0:
        await interaction.response.send_message("Bet must be positive.", ephemeral=True)
        return
    if user_data['balance'] < amount:
        await interaction.response.send_message("Not enough dabloons.", ephemeral=True)
        return
    # Deduct bet
    user_data['balance'] -= amount
    save_data()
    await interaction.response.send_message(f"{interaction.user.mention} has started a blackjack with {amount} dabloons.", ephemeral=False)
    game = BlackjackGame(interaction, user_id, amount)
    await game.play()
    save_data()

# /cf command
@bot.tree.command(name='cf', description='Coin flip')
async def cf(interaction: discord.Interaction, amount: int, choice: str, opponent: discord.Member = None):
    user_id = interaction.user.id
    user_data = get_user_data(user_id)
    if amount <= 0:
        await interaction.response.send_message("Bet must be positive.", ephemeral=True)
        return
    if user_data['balance'] < amount:
        await interaction.response.send_message("Not enough dabloons.", ephemeral=True)
        return
    choice = choice.lower()
    if choice not in ['h', 'heads', 't', 'tails']:
        await interaction.response.send_message("Choice must be 'h'/'heads' or 't'/'tails'.", ephemeral=True)
        return
    user_data['balance'] -= amount
    save_data()

    if opponent:
        # Send challenge
        challenge_msg = await interaction.response.send_message(f"{opponent.mention}, {interaction.user.mention} challenges you to a coin flip for {amount} dabloons! React with ✅ to accept or ❌ to decline within 60 seconds.", ephemeral=False)
        # Add reactions
        challenge_msg = await interaction.original_response()
        await challenge_msg.add_reaction('✅')
        await challenge_msg.add_reaction('❌')

        def check(reaction, user):
            return user.id == opponent.id and str(reaction.emoji) in ['✅', '❌'] and reaction.message.id == challenge_msg.id

        try:
            reaction, user = await bot.wait_for('reaction_add', timeout=60.0, check=check)
        except asyncio.TimeoutError:
            await interaction.followup.send(f"{opponent.mention} did not respond. Challenge canceled.")
            user_data['balance'] += amount
            save_data()
            return

        if str(reaction.emoji) == '❌':
            await interaction.followup.send(f"{opponent.mention} declined the challenge.")
            user_data['balance'] += amount
            save_data()
            return

        # Flip
        flip_result = random.choice(['h', 't'])
        winner_id = None
        if flip_result in ['h', 'heads']:
            winner_id = user_id if choice in ['h', 'heads'] else opponent.id
        else:
            winner_id = user_id if choice in ['t', 'tails'] else opponent.id

        if winner_id == user_id:
            user_data['balance'] += amount * 2
            user_data['wins'] += 1
            await interaction.followup.send(f"{interaction.user.mention} wins the coin flip and earns {amount*2} dabloons!")
        else:
            # Opponent wins, but they declined, so refund
            user_data['balance'] += amount
            await interaction.followup.send(f"{opponent.mention} wins the coin flip! You get your bet back.")
        save_data()

    else:
        # AI flip
        flip_result = random.choice(['h', 't'])
        if (flip_result in ['h', 'heads'] and choice in ['h', 'heads']) or (flip_result in ['t', 'tails'] and choice in ['t', 'tails']):
            user_data['balance'] += amount * 2
            user_data['wins'] += 1
            await interaction.response.send_message(f"You won the coin flip! You earn {amount*2} dabloons.")
        else:
            await interaction.response.send_message("You lost the coin flip.")
        save_data()

# /lb command
@bot.tree.command(name='lb', description='Leaderboard')
async def lb(interaction: discord.Interaction):
    sorted_users = sorted(data.items(), key=lambda x: x[1]['balance'], reverse=True)
    embed = discord.Embed(title="Leaderboard", color=0x00ff00)
    for idx, (user_id_str, info) in enumerate(sorted_users[:15], start=1):
        user = await bot.fetch_user(int(user_id_str))
        embed.add_field(name=f"{idx}. {user.name}", value=f"Balance: {info['balance']} | Wins: {info['wins']} | Losses: {info['losses']}", inline=False)
    await interaction.response.send_message(embed=embed)

# /claim command
@bot.tree.command(name='claim', description='Claim 1000 dabloons (1-hour cooldown)')
async def claim(interaction: discord.Interaction):
    user_id = interaction.user.id
    user_data = get_user_data(user_id)
    last_claim_time = datetime.fromisoformat(user_data['last_claim'])
    now = datetime.utcnow()
    if now - last_claim_time < timedelta(hours=CLAIM_COOLDOWN_HOURS):
        remaining = timedelta(hours=CLAIM_COOLDOWN_HOURS) - (now - last_claim_time)
        await interaction.response.send_message(f"You can claim again in {str(remaining).split('.')[0]}.", ephemeral=True)
        return
    if user_data['balance'] >= 1000:
        await interaction.response.send_message("You already have 1000 or more dabloons.", ephemeral=True)
        return
    user_data['balance'] += 1000
    user_data['last_claim'] = now.isoformat()
    save_data()
    await interaction.response.send_message("You claimed 1000 dabloons!", ephemeral=True)

# /giveaway command
@bot.tree.command(name='giveaway', description='Start a giveaway')
@commands.has_permissions(administrator=True)
async def giveaway(interaction: discord.Interaction, amount: int, duration: int, winners: int):
    if amount <= 0 or duration <= 0 or winners <= 0:
        await interaction.response.send_message("All values must be positive.", ephemeral=True)
        return
    # Collect participants
    message = await interaction.response.send_message(f"React with 🎉 to enter a giveaway of {amount} dabloons! Duration: {duration} seconds. Winners: {winners}", fetch_response=True)
    msg = await message
    await msg.add_reaction('🎉')
    await asyncio.sleep(duration)

    msg = await interaction.fetch_message(msg.id)
    users_in_giveaway = set()
    for reaction in msg.reactions:
        if str(reaction.emoji) == '🎉':
            async for user in reaction.users():
                if not user.bot:
                    users_in_giveaway.add(user.id)

    if len(users_in_giveaway) < winners:
        winners = len(users_in_giveaway)
    if winners == 0:
        await interaction.followup.send("No participants for the giveaway.")
        return
    winner_ids = random.sample(users_in_giveaway, winners)
    for wid in winner_ids:
        user_info = get_user_data(wid)
        user_info['balance'] += amount
        save_data()
        user = await bot.fetch_user(wid)
        await user.send(f"Congratulations! You won {amount} dabloons in the giveaway!")

    winner_mentions = ', '.join([f"<@{wid}>" for wid in winner_ids])
    await interaction.followup.send(f"Giveaway ended! Winners: {winner_mentions}")

# Save data periodically
@tasks.loop(minutes=5)
async def periodic_save():
    save_data()

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await reset_commands()
    periodic_save.start()

bot.run(TOKEN)
