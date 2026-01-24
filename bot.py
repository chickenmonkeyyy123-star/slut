import discord
from discord.ext import commands
import random
import json
import os
from discord.ui import Button, View

# ----------------- Bot Setup -----------------
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
bot = commands.Bot(command_prefix='/', intents=intents)

DATA_FILE = "dabloon_data.json"

# ----------------- Data Handling -----------------
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

data = load_data()

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

# ----------------- Blackjack Game -----------------
class BlackjackGame:
    def __init__(self, bet):
        self.bet = bet
        self.deck = self.create_deck()
        random.shuffle(self.deck)
        self.player_hand = [self.deck.pop(), self.deck.pop()]
        self.dealer_hand = [self.deck.pop(), self.deck.pop()]
        self.game_over = False

    def create_deck(self):
        suits = ['♠', '♥', '♦', '♣']
        ranks = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
        deck = []
        for suit in suits:
            for rank in ranks:
                value = 11 if rank == 'A' else 10 if rank in ['J','Q','K'] else int(rank)
                deck.append({'rank': rank, 'suit': suit, 'value': value})
        return deck

    def hand_value(self, hand):
        value = sum(card['value'] for card in hand)
        aces = sum(1 for card in hand if card['rank'] == 'A')
        while value > 21 and aces:
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
        player_val = self.hand_value(self.player_hand)
        dealer_val = self.hand_value(self.dealer_hand)
        if dealer_val > 21 or player_val > dealer_val:
            return "win"
        elif player_val < dealer_val:
            return "lose"
        else:
            return "tie"

    def format_hand(self, hand, hide_first=False):
        if hide_first:
            return f"?, {hand[1]['rank']}{hand[1]['suit']}"
        return ", ".join(f"{c['rank']}{c['suit']}" for c in hand)

# ----------------- Blackjack View -----------------
class BlackjackView(View):
    def __init__(self, game, user):
        super().__init__(timeout=60)
        self.game = game
        self.user = user

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.green)
    async def hit_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("This isn't your game!", ephemeral=True)
        result = self.game.hit()
        embed = discord.Embed(
            title="Blackjack",
            description=f"Your hand: {self.game.format_hand(self.game.player_hand)} (Value: {self.game.hand_value(self.game.player_hand)})\n"
                        f"Dealer's hand: {self.game.format_hand(self.game.dealer_hand, hide_first=True)}",
            color=discord.Color.blue()
        )
        if result == "bust":
            embed.description += "\n\n**Bust! You lose!**"
            embed.color = discord.Color.red()
            update_balance(self.user.id, -self.game.bet)
            update_stats(self.user.id, "blackjack", "losses")
            self.stop()
            await interaction.response.edit_message(embed=embed, view=None)
        else:
            await interaction.response.edit_message(embed=embed)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.red)
    async def stand_button(self, interaction: discord.Interaction, button: Button):
        if interaction.user.id != self.user.id:
            return await interaction.response.send_message("This isn't your game!", ephemeral=True)
        result = self.game.stand()
        embed = discord.Embed(
            title="Blackjack",
            description=f"Your hand: {self.game.format_hand(self.game.player_hand)} (Value: {self.game.hand_value(self.game.player_hand)})\n"
                        f"Dealer's hand: {self.game.format_hand(self.game.dealer_hand)} (Value: {self.game.hand_value(self.game.dealer_hand)})",
            color=discord.Color.blue()
        )
        if result == "win":
            embed.description += "\n\n**You win! 🎉**"
            embed.color = discord.Color.green()
            update_balance(self.user.id, self.game.bet)
            update_stats(self.user.id, "blackjack", "wins")
        elif result == "lose":
            embed.description += "\n\n**You lose! 😢**"
            embed.color = discord.Color.red()
            update_balance(self.user.id, -self.game.bet)
            update_stats(self.user.id, "blackjack", "losses")
        else:
            embed.description += "\n\n**It's a tie!**"
            embed.color = discord.Color.orange()
        self.stop()
        await interaction.response.edit_message(embed=embed, view=None)

# ----------------- Commands -----------------
@bot.command()
async def balance(ctx):
    user_data = get_user_data(ctx.author.id)
    await ctx.send(f"{ctx.author.mention}, your balance is {user_data['balance']} dabloons.")

@bot.command()
async def blackjack(ctx, bet: int):
    user_data = get_user_data(ctx.author.id)
    if bet > user_data["balance"]:
        return await ctx.send("You don't have enough dabloons!")
    game = BlackjackGame(bet)
    view = BlackjackView(game, ctx.author)
    embed = discord.Embed(
        title="Blackjack",
        description=f"Your hand: {game.format_hand(game.player_hand)} (Value: {game.hand_value(game.player_hand)})\n"
                    f"Dealer's hand: {game.format_hand(game.dealer_hand, hide_first=True)}",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed, view=view)

# ----------------- Run Bot -----------------
bot.run("YOUR_BOT_TOKEN")
