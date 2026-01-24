import discord
from discord.ext import commands
from discord import app_commands
import random
import asyncio
import json
from datetime import datetime, timedelta

# Bot setup
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# Data storage
user_data = {}  # Format: {user_id: {"balance": 1000, "blackjack_wins": 0, "blackjack_losses": 0, "coinflip_wins": 0, "coinflip_losses": 0}}
giveaways = {}  # Format: {message_id: {"amount": 100, "winners": 1, "entries": [], "end_time": datetime}}
coinflip_games = {}  # Format: {message_id: {"creator": user_id, "amount": 100, "choice": "heads", "opponent": None}}

# Helper functions
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

def save_data():
    # In a real bot, you'd save to a file or database
    pass

def load_data():
    # In a real bot, you'd load from a file or database
    pass

# Blackjack game logic
class BlackjackGame:
    def __init__(self, bet_amount):
        self.deck = self.create_deck()
        self.deck.shuffle()
        self.player_hand = []
        self.dealer_hand = []
        self.bet_amount = bet_amount
        self.game_over = False
        
        # Initial deal
        self.player_hand.append(self.deck.pop())
        self.dealer_hand.append(self.deck.pop())
        self.player_hand.append(self.deck.pop())
        self.dealer_hand.append(self.deck.pop())
    
    def create_deck(self):
        suits = ['♠', '♥', '♦', '♣']
        ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        deck = [f"{rank}{suit}" for suit in suits for rank in ranks]
        random.shuffle(deck)
        return deck
    
    def calculate_hand_value(self, hand):
        value = 0
        aces = 0
        
        for card in hand:
            rank = card[:-1]  # Get rank without suit
            if rank in ['J', 'Q', 'K']:
                value += 10
            elif rank == 'A':
                value += 11
                aces += 1
            else:
                value += int(rank)
        
        # Adjust for aces
        while value > 21 and aces > 0:
            value -= 10
            aces -= 1
        
        return value
    
    def hit(self):
        self.player_hand.append(self.deck.pop())
        if self.calculate_hand_value(self.player_hand) > 21:
            self.game_over = True
            return "bust"
        return "continue"
    
    def stand(self):
        # Dealer plays
        while self.calculate_hand_value(self.dealer_hand) < 17:
            self.dealer_hand.append(self.deck.pop())
        
        self.game_over = True
        player_value = self.calculate_hand_value(self.player_hand)
        dealer_value = self.calculate_hand_value(self.dealer_hand)
        
        if dealer_value > 21:
            return "win"  # Dealer bust
        elif player_value > dealer_value:
            return "win"
        elif player_value < dealer_value:
            return "lose"
        else:
            return "tie"
    
    def format_hand(self, hand, hide_first=False):
        if hide_first:
            return f"Hidden, {hand[1]}"
        return ", ".join(hand)

# Bot events
@bot.event
async def on_ready():
    print(f"{bot.user} has connected to Discord!")
    load_data()
    
    # Start the giveaway checker
    bot.loop.create_task(check_giveaways())

async def check_giveaways():
    while True:
        await asyncio.sleep(10)  # Check every 10 seconds
        
        current_time = datetime.now()
        completed_giveaways = []
        
        for message_id, giveaway in giveaways.items():
            if current_time >= giveaway["end_time"]:
                completed_giveaways.append(message_id)
                
                # Select winners
                if giveaway["entries"]:
                    winners = random.sample(
                        giveaway["entries"], 
                        min(giveaway["winners"], len(giveaway["entries"]))
                    )
                    
                    # Award dabloons to winners
                    for winner_id in winners:
                        user_data[winner_id]["balance"] += giveaway["amount"]
                    
                    # Announce winners
                    channel = bot.get_channel(giveaway["channel_id"])
                    if channel:
                        winner_mentions = [f"<@!{w}>" for w in winners]
                        await channel.send(
                            f"🎉 Giveaway ended! {giveaway['amount']} dabloons awarded to: {', '.join(winner_mentions)}!"
                        )
                else:
                    # No entries
                    channel = bot.get_channel(giveaway["channel_id"])
                    if channel:
                        await channel.send("The giveaway ended with no entries. 😢")
        
        # Remove completed giveaways
        for message_id in completed_giveaways:
            giveaways.pop(message_id, None)

# Bot commands
@bot.tree.command(name="giveaway", description="Start a dabloons giveaway")
@app_commands.describe(amount="Amount of dabloons to give away", duration="Duration in minutes", winners="Number of winners")
async def giveaway(interaction: discord.Interaction, amount: int, duration: int, winners: int = 1):
    if amount <= 0 or duration <= 0 or winners <= 0:
        await interaction.response.send_message("All values must be positive!", ephemeral=True)
        return
    
    # Create giveaway message
    embed = discord.Embed(
        title="🎉 Dabloons Giveaway! 🎉",
        description=f"**Amount:** {amount} dabloons\n**Winners:** {winners}\n**Duration:** {duration} minutes\n\nClick the button below to enter!",
        color=discord.Color.gold()
    )
    embed.set_footer(text="Ends at:")
    
    view = discord.ui.View()
    button = discord.ui.Button(label="Enter Giveaway", style=discord.ButtonStyle.green, emoji="🎉")
    
    async def button_callback(interaction: discord.Interaction):
        user_id = interaction.user.id
        if user_id not in giveaways[interaction.message.id]["entries"]:
            giveaways[interaction.message.id]["entries"].append(user_id)
            await interaction.response.send_message("You've entered the giveaway! Good luck!", ephemeral=True)
        else:
            await interaction.response.send_message("You've already entered this giveaway!", ephemeral=True)
    
    button.callback = button_callback
    view.add_item(button)
    
    await interaction.response.send_message(embed=embed, view=view)
    message = await interaction.original_response()
    
    # Store giveaway info
    giveaways[message.id] = {
        "amount": amount,
        "winners": winners,
        "entries": [],
        "end_time": datetime.now() + timedelta(minutes=duration),
        "channel_id": interaction.channel.id
    }

@bot.tree.command(name="bj", description="Play blackjack against the AI")
@app_commands.describe(amount="Amount of dabloons to bet")
async def bj(interaction: discord.Interaction, amount: int):
    user_id = interaction.user.id
    data = get_user_data(user_id)
    
    if amount <= 0:
        await interaction.response.send_message("Bet amount must be positive!", ephemeral=True)
        return
    
    if data["balance"] < amount:
        await interaction.response.send_message("You don't have enough dabloons!", ephemeral=True)
        return
    
    # Start game
    game = BlackjackGame(amount)
    
    embed = discord.Embed(
        title="♠️ Blackjack ♠️",
        description=f"**Bet:** {amount} dabloons\n\n**Your hand:** {game.format_hand(game.player_hand)} (Value: {game.calculate_hand_value(game.player_hand)})\n**Dealer's hand:** {game.format_hand(game.dealer_hand, hide_first=True)}",
        color=discord.Color.dark_green()
    )
    
    view = discord.ui.View()
    
    hit_button = discord.ui.Button(label="Hit", style=discord.ButtonStyle.success)
    stand_button = discord.ui.Button(label="Stand", style=discord.ButtonStyle.danger)
    
    async def hit_callback(interaction: discord.Interaction):
        result = game.hit()
        
        if result == "bust":
            # Player busted
            data["balance"] -= amount
            data["blackjack_losses"] += 1
            
            embed = discord.Embed(
                title="♠️ Blackjack - Busted! ♠️",
                description=f"**Your hand:** {game.format_hand(game.player_hand)} (Value: {game.calculate_hand_value(game.player_hand)})\n**Dealer's hand:** {game.format_hand(game.dealer_hand)} (Value: {game.calculate_hand_value(game.dealer_hand)})\n\nYou busted