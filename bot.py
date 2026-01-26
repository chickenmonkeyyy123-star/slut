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

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

DATA_FILE = 'dabloon_data.json'
CLAIM_COOLDOWN_HOURS = 1

def load_data():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, 'r') as f:
        return json.load(f)

def save_data():
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

data = load_data()

def get_user_data(user_id):
    user_id_str = str(user_id)
    if user_id_str not in data:
        data[user_id_str] = {
            'balance': 1000,
            'wins': 0,
            'losses': 0,
            'last_claim': '1970-01-01T00:00:00'
        }
        save_data()
    return data[user_id_str]

async def reset_commands():
    await bot.tree.clear_commands(guild=discord.Object(id=GUILD_ID))
    await bot.tree.sync(guild=discord.Object(id=GUILD_ID))
    print("Commands reset and synced.")

# --- Blackjack class ---
class BlackjackGame:
    def __init__(self, interaction, user_id, bet):
        self.interaction = interaction
        self.user_id = user_id
        self.bet = bet
        self.deck = self.create_deck()
        self.player_hands = [[]]
        self.dealer_hand = []
        self.active_hand_idx = 0
        self.game_over = False
        self.result = None

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
        hand.append(self.deck.pop())

    def hand_value(self, hand):
        total = 0
        aces = 0
        for r, s in hand:
            if r in ['J', 'Q', 'K']:
                total += 10
            elif r == 'A':
                total += 11
                aces += 1
            else:
                total += int(r)
        while total > 21 and aces:
            total -= 10
            aces -= 1
        return total

    def get_hand_str(self, hand, hide_dealer=False):
        if hide_dealer:
            return "?? " + ' '.join([f"{r}{s}" for r, s in hand[1:]])
        return ' '.join([f"{r}{s}" for r, s in hand])

    async def start(self):
        # Deal initial cards
        self.deal_card(self.player_hands[0])
        self.deal_card(self.player_hands[0])
        self.deal_card(self.dealer_hand)
        self.deal_card(self.dealer_hand)

        # Check blackjack
        if self.hand_value(self.player_hands[0]) == 21:
            self.result = 'blackjack'
            await self.resolve()
            return
        await self.player_turn()

    async def player_turn(self):
        for idx in range(len(self.player_hands)):
            self.active_hand_idx = idx
            hand = self.player_hands[idx]
            while True:
                total = self.hand_value(hand)
                embed = discord.Embed(title="Blackjack", description="", color=0x00ff00)
                embed.add_field(name="Your Hand", value=self.get_hand_str(hand) + f" (Total: {total})")
                embed.add_field(name="Dealer", value=self.get_hand_str(self.dealer_hand, hide_dealer=True))
                # Send embed
                if idx == 0:
                    await self.interaction.response.send_message(embed=embed)
                else:
                    await self.interaction.followup.send(embed=embed)

                message = await self.interaction.original_response() if idx == 0 else None
                if message is None:
                    message = await self.interaction.followup.send(embed=embed)
                await message.add_reaction('✅')  # Hit
                await message.add_reaction('🛑')  # Stand
                await message.add_reaction('🔄')  # Double
                await message.add_reaction('❌')  # Surrender

                def check(reaction, user):
                    return user.id == self.user_id and str(reaction.emoji) in ['✅', '🛑', '🔄', '❌'] and reaction.message.id == message.id

                try:
                    reaction, user = await bot.wait_for('reaction_add', timeout=60.0, check=check)
                except asyncio.TimeoutError:
                    # Default to stand
                    break

                emoji = str(reaction.emoji)
                if emoji == '✅':
                    self.deal_card(hand)
                    total = self.hand_value(hand)
                    if total > 21:
                        await self.interaction.followup.send(f"Bust! Your hand: {self.get_hand_str(hand)} Total: {total}")
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
                            await self.interaction.followup.send(f"Bust after double! Your hand: {self.get_hand_str(hand)} Total: {total}")
                        break
                    else:
                        await self.interaction.followup.send("Not enough dabloons to double.")
                elif emoji == '❌':
                    # Surrender
                    user_data = get_user_data(self.user_id)
                    user_data['balance'] += self.bet // 2
                    self.result = 'surrender'
                    await self.resolve()
                    return

        # Dealer turn
        self.dealer_play()
        await self.resolve()

    def dealer_play(self):
        while self.hand_value(self.dealer_hand) < 17:
            self.deal_card(self.dealer_hand)

    async def resolve(self):
        dealer_total = self.hand_value(self.dealer_hand)
        user_data = get_user_data(self.user_id)
        # Apply outcomes
        for hand in self.player_hands:
            total = self.hand_value(hand)
            if self.result == 'surrender':
                # Already handled
                continue
            if total > 21:
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
        for idx, hand in enumerate(self.player_hands):
            total = self.hand_value(hand)
            embed.add_field(name=f"Hand {idx+1}", value=self.get_hand_str(hand) + f" (Total: {total})")
        embed.add_field(name="Dealer", value=self.get_hand_str(self.dealer_hand))
        await self.interaction.followup.send(embed=embed)

# --- Commands ---

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await reset_commands()
    print("Bot is ready.")

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
    await game.start()
    save_data()

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
        # Challenge
        challenge_msg = await interaction.response.send_message(f"{opponent.mention}, {interaction.user.mention} challenges you to a coin flip for {amount} dabloons! React with ✅ to accept or ❌ to decline within 60 seconds.", ephemeral=False)
        challenge_msg_obj = await interaction.original_response()
        await challenge_msg_obj.add_reaction('✅')
        await challenge_msg_obj.add_reaction('❌')

        def check(reaction, user):
            return user.id == opponent.id and str(reaction.emoji) in ['✅', '❌'] and reaction.message.id == challenge_msg_obj.id

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

        # Flip result
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
            user_data['balance'] += amount
            await interaction.followup.send(f"{opponent.mention} wins the coin flip! You get your bet back.")
        save_data()

    else:
        flip_result = random.choice(['h', 't'])
        if (flip_result in ['h', 'heads'] and choice in ['h', 'heads']) or (flip_result in ['t', 'tails'] and choice in ['t', 'tails']):
            user_data['balance'] += amount * 2
            user_data['wins'] += 1
            await interaction.response.send_message(f"You won the coin flip! You earn {amount*2} dabloons.")
        else:
            await interaction.response.send_message("You lost the coin flip.")
        save_data()

@bot.tree.command(name='lb', description='Show leaderboard')
async def lb(interaction: discord.Interaction):
    sorted_users = sorted(data.items(), key=lambda x: x[1]['balance'], reverse=True)
    embed = discord.Embed(title="Leaderboard", color=0x00ff00)
    for idx, (user_id_str, info) in enumerate(sorted_users[:15], start=1):
        user = await bot.fetch_user(int(user_id_str))
        embed.add_field(name=f"{idx}. {user.name}", value=f"Balance: {info['balance']} | Wins: {info.get('wins', 0)} | Losses: {info.get('losses', 0)}", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name='claim', description='Claim 1000 dabloons (1-hour cooldown)')
async def claim(interaction: discord.Interaction):
    user_id = interaction.user.id
    user_data = get_user_data(user_id)
    last_claim = datetime.fromisoformat(user_data['last_claim'])
    now = datetime.utcnow()
    if now - last_claim < timedelta(hours=CLAIM_COOLDOWN_HOURS):
        remaining = timedelta(hours=CLAIM_COOLDOWN_HOURS) - (now - last_claim)
        await interaction.response.send_message(f"You can claim again in {str(remaining).split('.')[0]}.", ephemeral=True)
        return
    if user_data['balance'] >= 1000:
        await interaction.response.send_message("You already have 1000 or more dabloons.", ephemeral=True)
        return
    user_data['balance'] += 1000
    user_data['last_claim'] = now.isoformat()
    save_data()
    await interaction.response.send_message("You have claimed 1000 dabloons!", ephemeral=True)

@bot.tree.command(name='giveaway', description='Start a giveaway')
@commands.has_permissions(administrator=True)
async def giveaway(interaction: discord.Interaction, amount: int, duration: int, winners: int):
    if amount <= 0 or duration <= 0 or winners <= 0:
        await interaction.response.send_message("All values must be positive.", ephemeral=True)
        return
    msg = await interaction.response.send_message(f"React with 🎉 to enter a giveaway of {amount} dabloons! Duration: {duration} seconds. Winners: {winners}", fetch_response=True)
    msg_obj = await msg
    await msg_obj.add_reaction('🎉')
    await asyncio.sleep(duration)
    msg_final = await interaction.fetch_message(msg_obj.id)

    users_in = set()
    for reaction in msg_final.reactions:
        if str(reaction.emoji) == '🎉':
            async for user in reaction.users():
                if not user.bot:
                    users_in.add(user.id)

    if len(users_in) < winners:
        winners = len(users_in)
    if winners == 0:
        await interaction.followup.send("No participants.")
        return
    winner_ids = random.sample(users_in, winners)
    for wid in winner_ids:
        user_info = get_user_data(wid)
        user_info['balance'] += amount
        save_data()
        user = await bot.fetch_user(wid)
        await user.send(f"Congratulations! You won {amount} dabloons in the giveaway!")

    mention_list = ', '.join([f"<@{wid}>" for wid in winner_ids])
    await interaction.followup.send(f"Giveaway ended! Winners: {mention_list}")

@tasks.loop(minutes=5)
async def save_periodically():
    save_data()

# --- on_ready ---
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await reset_commands()
    save_periodically.start()

# Run the bot
bot.run(TOKEN)
