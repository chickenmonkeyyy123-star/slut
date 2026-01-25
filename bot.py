import os
import discord
from discord.ext import commands
from dotenv import load_dotenv
import asyncio
import json
import random

load_dotenv()
TOKEN = os.getenv('DISCORD_BOT_TOKEN')
if not TOKEN:
    raise ValueError("DISCORD_BOT_TOKEN not set in .env file!")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix='/', intents=intents)

DATA_FILE = 'dabloon_data.json'

# Utility functions to load/save balances
def load_balances():
    try:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
        balances = {}
        for user_id_str, user_data in data.items():
            if isinstance(user_data, dict) and "balance" in user_data:
                balances[user_id_str] = user_data["balance"]
        return balances
    except FileNotFoundError:
        return {}

def save_balance(user_id, amount):
    try:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}
    user_id_str = str(user_id)
    if user_id_str not in data or not isinstance(data[user_id_str], dict):
        data[user_id_str] = {}
    data[user_id_str]["balance"] = amount
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)

def update_balance(user_id, delta):
    try:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}
    user_id_str = str(user_id)
    if user_id_str not in data or not isinstance(data[user_id_str], dict):
        data[user_id_str] = {}
    current = data[user_id_str].get("balance", 0)
    new_balance = current + delta
    data[user_id_str]["balance"] = new_balance
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=4)
    return new_balance

# Blackjack game implementation
# Card deck
cards = [2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 11]  # 10s for face cards, 11 for Ace

def deal_card():
    return random.choice(cards)

def calculate_score(hand):
    total = sum(hand)
    aces = hand.count(11)
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total

async def blackjack_game(interaction, amount):
    user_id = interaction.user.id
    balance = get_balance(user_id)
    if amount > balance:
        await interaction.response.send_message("You don't have enough dabloons.", ephemeral=True)
        return

    # Initial deal
    player_hand = [deal_card(), deal_card()]
    dealer_hand = [deal_card(), deal_card()]

    # Check for blackjack
    player_score = calculate_score(player_hand)
    dealer_score = calculate_score(dealer_hand)

    # Check for immediate blackjack
    if player_score == 21:
        # Player gets 1.5x payout
        update_balance(user_id, amount * 1.5)
        await interaction.response.send_message(f"Blackjack! You win 1.5x your bet!", ephemeral=True)
        return

    # Game loop
    def format_hand(hand):
        return ", ".join(str(card) for card in hand)

    # Player turn
    while True:
        embed = discord.Embed(title="Blackjack", description=f"Your Hand: {format_hand(player_hand)} (Score: {calculate_score(player_hand)})\nDealer shows: {dealer_hand[0]}")
        embed.set_footer(text="Type hit, stand, double, or split (if applicable).")
        await interaction.response.send_message(embed=embed, view=None, ephemeral=True)

        # Present options
        class BlackjackView(discord.ui.View):
            def __init__(self):
                super().__init__(timeout=60)
            @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary)
            async def hit(self, button, interaction2):
                if interaction2.user.id != user_id:
                    return
                player_hand.append(deal_card())
                score = calculate_score(player_hand)
                if score > 21:
                    await interaction2.response.edit_message(embed=discord.Embed(title="Bust!", description=f"Your hand: {format_hand(player_hand)} (Score: {score})\nYou lose!"), view=None)
                    update_balance(user_id, -amount)
                    self.stop()
                else:
                    await interaction2.response.edit_message(embed=discord.Embed(title="Blackjack", description=f"Your Hand: {format_hand(player_hand)} (Score: {score})\nDealer shows: {dealer_hand[0]}"), view=self)
            @discord.ui.button(label="Stand", style=discord.ButtonStyle.secondary)
            async def stand(self, button, interaction2):
                if interaction2.user.id != user_id:
                    return
                # Dealer turn
                dealer_score = calculate_score(dealer_hand)
                while dealer_score < 17:
                    dealer_hand.append(deal_card())
                    dealer_score = calculate_score(dealer_hand)
                player_score = calculate_score(player_hand)
                # Determine result
                if dealer_score > 21 or player_score > dealer_score:
                    # Player wins
                    update_balance(user_id, amount)
                    await interaction2.response.edit_message(embed=discord.Embed(title="Win!", description=f"Your hand: {format_hand(player_hand)} (Score: {player_score})\nDealer: {format_hand(dealer_hand)} (Score: {dealer_score})\nYou win!"), view=None)
                elif player_score == dealer_score:
                    # Push
                    await interaction2.response.edit_message(embed=discord.Embed(title="Push", description=f"Your hand: {format_hand(player_hand)}\nDealer: {format_hand(dealer_hand)}\nIt's a tie!"), view=None)
                else:
                    # Dealer wins
                    update_balance(user_id, -amount)
                    await interaction2.response.edit_message(embed=discord.Embed(title="Lose!", description=f"Your hand: {format_hand(player_hand)}\nDealer: {format_hand(dealer_hand)}\nYou lose!"), view=None)
                self.stop()
            @discord.ui.button(label="Double", style=discord.ButtonStyle.danger)
            async def double(self, button, interaction2):
                if interaction2.user.id != user_id:
                    return
                # Double the bet
                if amount > get_balance(user_id):
                    await interaction2.response.send_message("Not enough balance to double.", ephemeral=True)
                    return
                update_balance(user_id, -amount)
                new_amount = amount * 2
                player_hand.append(deal_card())
                score = calculate_score(player_hand)
                # Dealer turn
                dealer_score = calculate_score(dealer_hand)
                while dealer_score < 17:
                    dealer_hand.append(deal_card())
                    dealer_score = calculate_score(dealer_hand)
                # Determine result
                if score > 21:
                    # Bust
                    await interaction2.response.edit_message(embed=discord.Embed(title="Bust!", description=f"Your hand: {format_hand(player_hand)} (Score: {score})\nYou lose!"), view=None)
                    update_balance(user_id, -amount)
                elif dealer_score > 21 or score > dealer_score:
                    update_balance(user_id, new_amount)
                    await interaction2.response.edit_message(embed=discord.Embed(title="Win!", description=f"Your hand: {format_hand(player_hand)} (Score: {score})\nDealer: {format_hand(dealer_hand)} (Score: {dealer_score})\nYou win double!"), view=None)
                elif score == dealer_score:
                    # Push
                    await interaction2.response.edit_message(embed=discord.Embed(title="Push", description=f"Your hand: {format_hand(player_hand)}\nDealer: {format_hand(dealer_hand)}\nIt's a tie!"), view=None)
                else:
                    await interaction2.response.edit_message(embed=discord.Embed(title="Lose!", description=f"Your hand: {format_hand(player_hand)}\nDealer: {format_hand(dealer_hand)}\nYou lose!"), view=None)
                    update_balance(user_id, -amount)
                self.stop()
        view = BlackjackView()
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        await view.wait()
        return

# Command to start blackjack
@bot.tree.command(name="bj", description="Play blackjack")
async def start_blackjack(interaction: discord.Interaction, amount: float):
    await blackjack_game(interaction, amount)

# Run the bot
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await bot.tree.sync()

# Helper to get balance
def get_balance(user_id):
    data = load_balances()
    return data.get(str(user_id), 0)

# Run
bot.run(TOKEN)
