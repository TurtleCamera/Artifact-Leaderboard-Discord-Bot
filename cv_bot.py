import discord
from discord.ext import commands
from discord import app_commands
import json
import os

# Setup intents
intents = discord.Intents.default()
intents.message_content = True  # optional for future features

# Create bot
bot = commands.Bot(command_prefix="!", intents=intents)

# Load token
with open("token", "r") as f:
    TOKEN = f.read().strip()

# Data file
DATA_FILE = "data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

data = load_data()

# Helper: get display name
def get_display_name(user_id, discord_name):
    user_data = data.get(str(user_id), {})
    return user_data.get("display_name") or discord_name

# Event: bot ready
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")
    try:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"Error syncing commands: {e}")

# /name command
@bot.tree.command(name="name", description="Change your display name on the leaderboard")
@app_commands.describe(new_name="The name you want to display on the leaderboard")
async def name(interaction: discord.Interaction, new_name: str):
    user_id = str(interaction.user.id)
    if user_id not in data:
        data[user_id] = {"display_name": None, "artifacts": [], "max_cv": 0}
    data[user_id]["display_name"] = new_name
    save_data(data)
    await interaction.response.send_message(f"Your leaderboard name is now set to: **{new_name}**", ephemeral=True)

# /submit command
@bot.tree.command(name="submit", description="Submit an artifact (crit rate & crit dmg)")
@app_commands.describe(crit_rate="Crit Rate of artifact", crit_dmg="Crit Damage of artifact")
async def submit(interaction: discord.Interaction, crit_rate: float, crit_dmg: float):
    user_id = str(interaction.user.id)
    user_name = interaction.user.display_name

    # Initialize user if not exist
    if user_id not in data:
        data[user_id] = {"display_name": None, "artifacts": [], "max_cv": 0}

    # CV calculation
    cv = crit_rate * 2 + crit_dmg

    # Store artifact
    artifact = {"crit_rate": crit_rate, "crit_dmg": crit_dmg, "cv": cv}
    data[user_id]["artifacts"].append(artifact)

    # Update max CV if needed
    if cv > data[user_id]["max_cv"]:
        data[user_id]["max_cv"] = cv
        rank_msg = "New highest CRIT value!"
    else:
        rank_msg = "Submitted"

    save_data(data)
    display_name = get_display_name(user_id, user_name)

    # Send publicly using webhook
    channel = interaction.channel  # channel where command was used

    # Create temporary webhook
    webhook = await channel.create_webhook(name="ArtiBotTempWebhook")

    # Send message through webhook using user's name & avatar
    await webhook.send(
        content=f"Artifact submitted to CRIT Value Leaderboard: {cv:.2f} CV. {rank_msg}",
        username=interaction.user.display_name,
        avatar_url=interaction.user.display_avatar.url
    )

    # Delete webhook to clean up
    await webhook.delete()

    # Respond ephemerally to user to confirm submission
    await interaction.response.send_message("Your artifact has been submitted publicly!", ephemeral=True)

# Run bot
bot.run(TOKEN)
