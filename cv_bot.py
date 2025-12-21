import discord
from discord.ext import commands

# Read bot token from file
with open("token", "r") as f:
    TOKEN = f.read().strip()  # .strip() removes newlines

intents = discord.Intents.default()
intents.message_content = True  # optional for later

bot = commands.Bot(command_prefix="!", intents=intents)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")

bot.run(TOKEN)
