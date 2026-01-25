import discord
import json
import random
import asyncio
import os
from discord.ext import commands
from discord import app_commands
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
SERVER_ID = 1332118870181412936

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

# Card deck setup
SUITS = ['♠', '♥', '♦', '♣']
RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
VALUES = {rank: i+2 for i, rank in enumerate(RANKS[:-1])}
VALUES['J'] = 10
VALUES['Q'] = 10
VALUES['K'] = 10
VALUES['A'] = 11

# Admin IDs (replace with your Discord user ID)
ADMIN_IDS = ["1081808039872573544"]  # Add your admin ID here

# Active games storage
blackjack_games = {}
coinflip_games = {}
giveaway_games = {}

# Load user data
def load_data():
    try:
        with open('dabloon_data.json', 'r') as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}

# Save user data
def save_data(data):
    with open('dabloon_data.json', 'w') as f:
        json.dump(data, f, indent=4)

# Create a deck of cards
def create_deck():
    return [{'rank': rank, 'suit': suit} for suit in SUITS for rank in RANKS]

# Calculate hand value
def hand_value(hand):
    value = sum(VALUES[card['rank']] for card in hand)
    aces = sum(1 for card in hand if card['rank'] == 'A')
    
    while value > 21 and aces:
        value -= 10
        aces -= 1
    
    return value

# Format hand for display
def format_hand(hand):
    return ' '.join(f"{card['rank']}{card['suit']}" for card in hand)

# Check if user has enough balance
def check_balance(user_id, amount):
    data = load_data()
    user_id_str = str(user_id)
    
    if user_id_str not in data:
        data[user_id_str] = {
            "balance": 10000,
            "blackjack": {"wins": 0, "losses": 0},
            "coinflip": {"wins": 0, "losses": 0}
        }
        save_data(data)
    
    return data[user_id_str]["balance"] >= amount

# Update user balance
def update_balance(user_id, amount, game_type, result):
    data = load_data()
    user_id_str = str(user_id)
    
    if user_id_str not in data:
        data[user_id_str] = {
            "balance": 10000,
            "blackjack": {"wins": 0, "losses": 0},
            "coinflip": {"wins": 0, "losses": 0}
        }
    
    data[user_id_str]["balance"] += amount
    
    if game_type == "blackjack":
        if result == "win":
            data[user_id_str]["blackjack"]["wins"] += 1
        elif result == "loss":
            data[user_id_str]["blackjack"]["losses"] += 1
    elif game_type == "coinflip":
        if result == "win":
            data[user_id_str]["coinflip"]["wins"] += 1
        elif result == "loss":
            data[user_id_str]["coinflip"]["losses"] += 1
    
    save_data(data)
    return data[user_id_str]["balance"]

# Bot ready event
@bot.event
async def on_ready():
    print(f'{bot.user.name} has connected to Discord!')
    print(f'Bot is in {len(bot.guilds)} servers')
    
    # Sync commands with the server
    try:
        guild = discord.Object(id=SERVER_ID)
        synced = await bot.tree.sync(guild=guild)
        print(f"Synced {len(synced)} command(s) to guild {SERVER_ID}")
    except Exception as e:
        print(f"Failed to sync commands: {e}")

# Blackjack command
@bot.tree.command(name="bj", description="Play blackjack against the AI", guild=discord.Object(id=SERVER_ID))
@app_commands.describe(amount="The amount of dabloons to bet")
async def blackjack(interaction: discord.Interaction, amount: float):
    user_id = str(interaction.user.id)
    
    # Check if user has enough balance
    if not check_balance(user_id, amount):
        await interaction.response.send_message(f"You don't have enough dabloons to bet {amount}!")
        return
    
    # Check if user is already in a game
    if user_id in blackjack_games:
        await interaction.response.send_message("You're already in a blackjack game! Use the buttons to continue.")
        return
    
    # Create a new game
    deck = create_deck()
    random.shuffle(deck)
    
    player_hand = [deck.pop(), deck.pop()]
    dealer_hand = [deck.pop(), deck.pop()]
    
    # Check for blackjack
    player_value = hand_value(player_hand)
    dealer_value = hand_value(dealer_hand)
    
    if player_value == 21 and dealer_value == 21:
        # Both have blackjack, it's a push
        await interaction.response.send_message(f"**Blackjack Push!**\n\nYour hand: {format_hand(player_hand)} (21)\nDealer's hand: {format_hand(dealer_hand)} (21)\n\nYour bet of {amount} dabloons has been returned.")
        return
    elif player_value == 21:
        # Player has blackjack, win
        new_balance = update_balance(user_id, amount * 1.5, "blackjack", "win")
        await interaction.response.send_message(f"**Blackjack! You win!**\n\nYour hand: {format_hand(player_hand)} (21)\nDealer's hand: {format_hand(dealer_hand)} ({dealer_value})\n\nYou won {amount * 1.5} dabloons! Your new balance is {new_balance}.")
        return
    elif dealer_value == 21:
        # Dealer has blackjack, player loses
        update_balance(user_id, -amount, "blackjack", "loss")
        await interaction.response.send_message(f"**Dealer has Blackjack! You lose!**\n\nYour hand: {format_hand(player_hand)} ({player_value})\nDealer's hand: {format_hand(dealer_hand)} (21)\n\nYou lost {amount} dabloons.")
        return
    
    # Create buttons
    view = BlackjackView(user_id, amount, player_hand, dealer_hand, deck)
    
    # Send initial game state
    await interaction.response.send_message(
        f"**Blackjack**\n\nYour hand: {format_hand(player_hand)} ({player_value})\nDealer's hand: {dealer_hand[0]['rank']}{dealer_hand[0]['suit']} ?\n\nBet: {amount} dabloons",
        view=view
    )
    
    # Store game state
    blackjack_games[user_id] = {
        "deck": deck,
        "player_hand": player_hand,
        "dealer_hand": dealer_hand,
        "bet": amount,
        "doubled_down": False,
        "split": False,
        "message": None
    }

# Blackjack view with buttons
class BlackjackView(discord.ui.View):
    def __init__(self, user_id, bet, player_hand, dealer_hand, deck):
        super().__init__(timeout=60)  # 60 second timeout
        self.user_id = user_id
        self.bet = bet
        self.player_hand = player_hand
        self.dealer_hand = dealer_hand
        self.deck = deck
        self.doubled_down = False
        
        # Disable split button if cards are not the same rank
        if player_hand[0]['rank'] != player_hand[1]['rank']:
            self.children[3].disabled = True
    
    async def on_timeout(self):
        # End the game if no action is taken
        if self.user_id in blackjack_games:
            update_balance(self.user_id, -self.bet, "blackjack", "loss")
            await self.message.edit(content=f"**Game timed out! You lose!**\n\nYou lost {self.bet} dabloons.", view=None)
            del blackjack_games[self.user_id]
    
    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary)
    async def hit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if str(interaction.user.id) != self.user_id:
            await interaction.response.send_message("This is not your game!", ephemeral=True)
            return
        
        # Draw a card
        self.player_hand.append(self.deck
