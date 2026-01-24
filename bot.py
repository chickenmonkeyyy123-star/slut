import discord
from discord.ext import commands
import random
import asyncio
import json
import os
from datetime import datetime, timedelta
from discord.ui import Button, View

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='/', intents=intents)

# Data storage
DATA_FILE = "dabloon_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, 'r') as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

# Initialize data
data = load_data()

# Helper functions
def get_user_data(user_id):
    if str(user_id) not in data:
        data[str(user_id)] = {
            "balance": 1000,
            "blackjack": {"wins": 0, "losses": 0},
            "coinflip": {"wins": 0, "losses": 0}
        }
        save_data(data)
    return data[str(user_id)]

def update_balance(user_id, amount):
    user_data = get_user_data(user_id)
    user_data["balance"] += amount
    save_data(data)

def update_stats(user_id, game, result):
    user_data = get_user_data(user_id)
    user_data[game][result] += 1
    save_data(data)

# Blackjack game logic
class BlackjackGame:
    def __init__(self, bet):
        self.deck = self.create_deck()
        self.deck = self.shuffle_deck(self.deck)
        self.player_hand = []
        self.dealer_hand = []
        self.bet = bet
        self.game_over = False
        
        # Deal initial cards
        self.player_hand.append(self.deck.pop())
        self.dealer_hand.append(self.deck.pop())
        self.player_hand.append(self.deck.pop())
        self.dealer_hand.append(self.deck.pop())
    
    def create_deck(self):
        suits = ['♠', '♥', '♦', '♣']
        ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        deck = []
        for suit in suits:
            for rank in ranks:
                if rank in ['J', 'Q', 'K']:
                    value = 10
                elif rank == 'A':
                    value = 11
                else:
                    value = int(rank)
                deck.append({'rank': rank, 'suit': suit, 'value': value})
        return deck
    
    def shuffle_deck(self, deck):
        random.shuffle(deck)
        return deck
    
    def hand_value(self, hand):
        value = 0
        aces = 0
        
        for card in hand:
            value += card['value']
            if card['rank'] == 'A':
                aces += 1
        
        while value > 21 and aces > 0:
            value -= 10
            aces -= 1
        
        return value
    
    def hit(self):
        self.player_hand.append(self.deck.pop())
        
        if self.hand_value(self.player_hand) > 21:
            self.game_over = True
            return "bust"
        return "continue"
    
    def stand(self):
        while self.hand_value(self.dealer_hand) < 17:
            self.dealer_hand.append(self.deck.pop())
        
        self.game_over = True
        
        player_value = self.hand_value(self.player_hand)
        dealer_value = self.hand_value(self.dealer_hand)
        
        if dealer_value > 21:
            return "win"
        elif player_value > dealer_value:
            return "win"
        elif player_value < dealer_value:
            return "lose"
        else:
            return "tie"
    
    def format_hand(self, hand, hide_first=False):
        if hide_first:
            return f"?, {hand[1]['rank']}{hand[1]['suit']}"
        return ", ".join([f"{card['rank']}{card['suit']}" for card in hand])

# Giveaway view
class GiveawayView(View):
    def __init__(self, amount, duration, winners_count):
        super().__init__(timeout=None)
        self.amount = amount
        self.duration = duration
        self.winners_count = winners_count
        self.participants = []
        self.message = None
    
    @discord.ui.button(label="Enter Giveaway", style=discord.ButtonStyle.green, custom_id="giveaway_enter")
    async def enter_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id not in self.participants:
            self.participants.append(interaction.user.id)
            await interaction.response.send_message("You've entered the giveaway!", ephemeral=True)
        else:
            await interaction.response.send_message("You've already entered the giveaway!", ephemeral=True)

# Coinflip view
class CoinflipView(View):
    def __init__(self, amount, choice, challenger=None, is_ai=False):
        super().__init__(timeout=60)
        self.amount = amount
        self.choice = choice
        self.challenger = challenger
        self.is_ai = is_ai
        self.accepted = False
        self.message = None
    
    @discord.ui.button(label="Accept", style=discord.ButtonStyle.green, custom_id="coinflip_accept")
    async def accept_button(self, interaction: discord.Interaction, button: Button):
        if not self.is_ai and interaction.user.id != self.challenger.id:
            await interaction.response.send_message("This isn't your coinflip!", ephemeral=True)
            return
        
        self.accepted = True
        self.stop()
        await interaction.response.edit_message(view=None, content="Coinflip accepted! Flipping...")
        
        # Determine winner
        result = random.choice(["heads", "tails"])
        winner = None
        
        if not self.is_ai:
            # User vs User
            initiator = interaction.message.mentions[0] if interaction.message.mentions else interaction.user
            challenger = interaction.user
            
            if result == self.choice:
                winner = initiator
                update_balance(initiator.id, self.amount)
                update_balance(challenger.id, -self.amount)
                update_stats(initiator.id, "coinflip", "wins")
                update_stats(challenger.id, "coinflip", "losses")
            else:
                winner = challenger
                update_balance(challenger.id, self.amount)
                update_balance(initiator.id, -self.amount)
                update_stats(challenger.id, "coinflip", "wins")
                update_stats(initiator.id, "coinflip", "losses")
            
            await interaction.channel.send(
                f"The coin landed on **{result}**!\n"
                f"{winner.mention} won {self.amount} dabloons!"
            )
        else:
            # User vs AI
            user = interaction.user
            
            if result == self.choice:
                winner = user
                update_balance(user.id, self.amount)
                update_stats(user.id, "coinflip", "wins")
                await interaction.channel.send(
                    f"The coin landed on **{result}**!\n"
                    f"{winner.mention} won {self.amount} dabloons!"
                )
            else:
                update_balance(user.id, -self.amount)
                update_stats(user.id, "coinflip", "losses")
                await interaction.channel.send(
                    f"The coin landed on **{result}**!\n"
                    f"The AI won {self.amount} dabloons!"
                )

# Bot events
@bot.event
async def on_ready():
    print(f'{bot.user} has connected to Discord!')
    print(f'Bot is in {len(bot.guilds)} servers')
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(e)

# Bot commands (slash commands)
@bot.tree.command(name="giveaway", description="Start a giveaway for dabloons")
async def giveaway(interaction: discord.Interaction, amount: int, duration: int, winners: int):
    """Start a giveaway for dabloons"""
    if amount <= 0 or duration <= 0 or winners <= 0:
        await interaction.response.send_message("Amount, duration, and winners must be positive numbers!")
        return
    
    # Create giveaway view
    view = GiveawayView(amount, duration, winners)
    
    # Create giveaway embed
    embed = discord.Embed(
        title="🎉 Dabloon Giveaway 🎉",
        description=f"Prize: {amount} dabloons\nWinners: {winners}\nDuration: {duration} minutes",
        color=discord.Color.gold()
    )
    embed.set_footer(text=f"Hosted by {interaction.user.display_name}")
    
    # Send giveaway message
    await interaction.response.send_message(embed=embed, view=view)
    message = await interaction.original_response()
    view.message = message
    
    # Wait for duration
    await asyncio.sleep(duration * 60)
    
    # Select winners
    if len(view.participants) < winners:
        await message.reply("Not enough participants for the giveaway!")
        return
    
    selected_winners = random.sample(view.participants, min(winners, len(view.participants)))
    
    # Announce winners
    winners_text = ", ".join([
