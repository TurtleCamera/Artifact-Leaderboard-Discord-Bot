import discord
from discord.ext import commands
from discord import app_commands
import json
import os

# Constants
MAX_NAME_LENGTH = 7  # Max name length on leaderboard (longest possible for mobile)
MAX_LEADERBOARD_PLAYERS = 25  # Max players to display on leaderboard (Discord's limit)
DATA_FILE = "data.json"  # Data file

# Setup intents
intents = discord.Intents.default()
intents.message_content = True  # optional for future features

# Create bot
bot = commands.Bot(command_prefix="!", intents=intents)

# Load token
with open("token", "r") as f:
    TOKEN = f.read().strip()

# Data helper functions
def load_data():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    return {}

def save_data(data):
    with open(DATA_FILE, "w") as f:
        json.dump(data, f, indent=4)

data = load_data()

# Helper function to get display name
def get_display_name(user_id: str, fallback_user: discord.Member = None):
    user_data = data.get(str(user_id), {})
    display_name = user_data.get("display_name")
    if display_name:
        return display_name
    # Fallback to Discord username if available
    if fallback_user:
        return fallback_user.display_name
    # Last resort
    return "Unknown"

# Helper function to count artifacts above a CV threshold
def count_artifacts(artifacts, threshold):
    return sum(1 for arti in artifacts if arti["cv"] >= threshold)

# Helper function to get current leaderboard ranking (user_id -> rank)
def get_leaderboard_ranks():
    sorted_leaderboard = sorted(
        data.items(),
        key=lambda item: (
            item[1]["max_cv"],
            count_artifacts(item[1]["artifacts"], 45),
            count_artifacts(item[1]["artifacts"], 40)
        ),
        reverse=True
    )

    return {user_id: rank + 1 for rank, (user_id, _) in enumerate(sorted_leaderboard)}

# Events
# Bot ready
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")

    # Load guild ID
    with open("guild_id", "r") as f:
        GUILD_ID = int(f.read().strip())
    guild = discord.Object(id=GUILD_ID)

    try:
        # Force guild-specific sync
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        print(f"Synced {len(synced)} command(s) to guild {GUILD_ID}")
    except Exception as e:
        print(f"Error syncing commands: {e}")

# Commands
# /name command
@bot.tree.command(name="name", description="Change your display name on the leaderboard")
@app_commands.describe(new_name="The name you want to display on the leaderboard")
async def name(interaction: discord.Interaction, new_name: str):
    user_id = str(interaction.user.id)
    if user_id not in data:
        data[user_id] = {"display_name": None, "artifacts": [], "max_cv": 0}
    data[user_id]["display_name"] = new_name
    save_data(data)
    await interaction.response.send_message(
        f"Your leaderboard name is now set to: **{new_name}**",
        ephemeral=True
    )


# /submit command
@bot.tree.command(name="submit", description="Submit an artifact (CRIT Rate & CRIT DMG)")
@app_commands.describe(crit_rate="CRIT Rate of artifact", crit_dmg="CRIT DMG of artifact")
async def submit(interaction: discord.Interaction, crit_rate: float, crit_dmg: float):
    user_id = str(interaction.user.id)

    # Check if user is new
    was_new_user = user_id not in data

    # Initialize user if not exist
    if was_new_user:
        data[user_id] = {"display_name": None, "artifacts": [], "max_cv": 0}

    # Rank before submission
    ranks_before = get_leaderboard_ranks()
    old_rank = ranks_before.get(user_id)

    # CV calculation
    cv = crit_rate * 2 + crit_dmg

    # Store artifact
    artifact = {"crit_rate": crit_rate, "crit_dmg": crit_dmg, "cv": cv}
    data[user_id]["artifacts"].append(artifact)

    # Update max CV if needed
    if cv > data[user_id]["max_cv"]:
        data[user_id]["max_cv"] = cv

    save_data(data)

    # Rank AFTER submission
    ranks_after = get_leaderboard_ranks()
    new_rank = ranks_after.get(user_id)

    # Build rank change message
    if was_new_user:
        rank_msg = f"Entered leaderboard at rank #{new_rank}"
    elif new_rank < old_rank:
        rank_msg = f"▲ +{old_rank - new_rank} → #{new_rank}"
    elif new_rank > old_rank:
        rank_msg = f"▼ -{new_rank - old_rank} → #{new_rank}"
    else:
        rank_msg = f"▬ Unchanged (#{new_rank})"

    # Send publicly using webhook
    channel = interaction.channel
    webhook = await channel.create_webhook(name="ArtiBotTempWebhook")

    await webhook.send(
        content=(
            f"Artifact submitted to CRIT Value leaderboard: "
            f"{cv:.2f} CV\n"
            f"{rank_msg}"
        ),
        username=interaction.user.display_name,
        avatar_url=interaction.user.display_avatar.url
    )

    await webhook.delete()

    # Confirm to user
    await interaction.response.send_message(
        "Your artifact has been submitted!",
        ephemeral=True
    )

# /list command
@bot.tree.command(name="list", description="List all artifacts for a user")
@app_commands.describe(user_identifier="Optional: leaderboard name, mention, or Discord username")
async def list_artifacts(interaction: discord.Interaction, user_identifier: str = None):
    target_user_id = None

    # Determine which user to show
    if user_identifier:
        # Try to match by /name first
        for uid, udata in data.items():
            if udata.get("display_name") == user_identifier:
                target_user_id = uid
                break

        # Then check for a mention
        if not target_user_id and interaction.guild:
            if len(interaction.message.mentions) > 0:
                target_user_id = str(interaction.message.mentions[0].id)

        # Then check for Discord username#discriminator
        if not target_user_id:
            for member in interaction.guild.members:
                if f"{member.name}#{member.discriminator}" == user_identifier:
                    target_user_id = str(member.id)
                    break

    # Default to invoking user if none found
    if not target_user_id:
        target_user_id = str(interaction.user.id)

    # Check if user has artifacts
    user_data = data.get(target_user_id)
    if not user_data or not user_data.get("artifacts"):
        await interaction.response.send_message("No artifacts found for this user.", ephemeral=True)
        return

    # Build artifact table
    lines = [
        "Index | CR    | CD    | CV    ",
        "------+-------+-------+-------"
    ]
    for idx, arti in enumerate(user_data["artifacts"], start=1):
        lines.append(
            f"{idx:<5} | "
            f"{arti['crit_rate']:<5.1f} | "
            f"{arti['crit_dmg']:<5.1f} | "
            f"{arti['cv']:<5.2f}"
        )

    artifact_text = "\n".join(lines)
    display_name = get_display_name(target_user_id, interaction.user)
    await interaction.response.send_message(
        f"Artifacts for **{display_name}**:\n```\n{artifact_text}\n```",
        ephemeral=True
    )

# /remove command
@bot.tree.command(name="remove", description="Remove a user or a specific artifact")
@app_commands.describe(
    user_identifier="Leaderboard name, mention, or Discord username",
    artifact_index="Optional: index of artifact to remove (1-based). Leave empty to remove the whole user"
)
async def remove(interaction: discord.Interaction, user_identifier: str, artifact_index: int = None):
    target_user_id = None

    # Resolve user_identifier to user_id (same logic as /list)
    # Check /name first
    for uid, udata in data.items():
        if udata.get("display_name") == user_identifier:
            target_user_id = uid
            break

    # Then check for mention
    if not target_user_id and interaction.guild:
        if len(interaction.message.mentions) > 0:
            target_user_id = str(interaction.message.mentions[0].id)

    # Then check for Discord username#discriminator
    if not target_user_id:
        for member in interaction.guild.members:
            if f"{member.name}#{member.discriminator}" == user_identifier:
                target_user_id = str(member.id)
                break

    # If user not found
    if not target_user_id or target_user_id not in data:
        await interaction.response.send_message(
            f"User '{user_identifier}' not found in the leaderboard.",
            ephemeral=True
        )
        return

    # Remove a specific artifact
    if artifact_index is not None:
        artifacts = data[target_user_id].get("artifacts", [])
        if artifact_index < 1 or artifact_index > len(artifacts):
            await interaction.response.send_message(
                f"Invalid artifact index. Please provide a number between 1 and {len(artifacts)}.",
                ephemeral=True
            )
            return

        removed_artifact = artifacts.pop(artifact_index - 1)
        # Update max CV
        if artifacts:
            data[target_user_id]["max_cv"] = max(arti["cv"] for arti in artifacts)
        else:
            data[target_user_id]["max_cv"] = 0

        save_data(data)
        await interaction.response.send_message(
            f"Removed artifact #{artifact_index} for **{get_display_name(target_user_id, interaction.user)}**.",
            ephemeral=True
        )
        return

    # Remove the entire user
    removed_name = get_display_name(target_user_id, interaction.user)
    data.pop(target_user_id)
    save_data(data)
    await interaction.response.send_message(
        f"Removed **{removed_name}** and all their artifacts from the leaderboard.",
        ephemeral=True
    )

# /modify command
@bot.tree.command(name="modify", description="Modify an existing artifact")
@app_commands.describe(
    user_identifier="Leaderboard name, mention, or Discord username",
    artifact_index="Index of the artifact to modify (1-based)",
    crit_rate="New CRIT Rate value",
    crit_dmg="New CRIT DMG value"
)
async def modify(interaction: discord.Interaction, user_identifier: str, artifact_index: int, crit_rate: float, crit_dmg: float):
    target_user_id = None

    # Resolve user_identifier to user_id (same logic as /list)
    for uid, udata in data.items():
        if udata.get("display_name") == user_identifier:
            target_user_id = uid
            break

    # Then check for mention
    if not target_user_id and interaction.guild:
        if len(interaction.message.mentions) > 0:
            target_user_id = str(interaction.message.mentions[0].id)

    # Then check for Discord username#discriminator
    if not target_user_id:
        for member in interaction.guild.members:
            if f"{member.name}#{member.discriminator}" == user_identifier:
                target_user_id = str(member.id)
                break

    # If user not found
    if not target_user_id or target_user_id not in data:
        await interaction.response.send_message(
            f"User '{user_identifier}' not found in the leaderboard.",
            ephemeral=True
        )
        return

    artifacts = data[target_user_id].get("artifacts", [])
    if artifact_index < 1 or artifact_index > len(artifacts):
        await interaction.response.send_message(
            f"Invalid artifact index. Please provide a number between 1 and {len(artifacts)}.",
            ephemeral=True
        )
        return

    artifact = artifacts[artifact_index - 1]
    old_cv = artifact["cv"]
    old_cr = artifact["crit_rate"]
    old_cd = artifact["crit_dmg"]

    # Update artifact
    artifact["crit_rate"] = crit_rate
    artifact["crit_dmg"] = crit_dmg
    artifact["cv"] = crit_rate * 2 + crit_dmg

    # Update max CV
    data[target_user_id]["max_cv"] = max((arti["cv"] for arti in artifacts), default=0)
    save_data(data)

    # Check leaderboard ranks
    ranks_before = get_leaderboard_ranks()
    old_rank = ranks_before.get(target_user_id)
    ranks_after = get_leaderboard_ranks()
    new_rank = ranks_after.get(target_user_id)

    # Build rank change message
    if new_rank < old_rank:
        rank_msg = f"▲ +{old_rank - new_rank} → #{new_rank}"
    elif new_rank > old_rank:
        rank_msg = f"▼ -{new_rank - old_rank} → #{new_rank}"
    else:
        rank_msg = f"▬ Unchanged (#{new_rank})"

    # Send confirmation
    await interaction.response.send_message(
        f"Modified artifact #{artifact_index} for **{get_display_name(target_user_id, interaction.user)}**:\n"
        f"CRIT Rate: {old_cr:.1f} → {crit_rate:.1f}\n"
        f"CRIT DMG: {old_cd:.1f} → {crit_dmg:.1f}\n"
        f"CV: {old_cv:.2f} → {artifact['cv']:.2f}\n"
        f"Leaderboard change: {rank_msg}",
        ephemeral=True
    )

# /leaderboard command (ASCII, mobile-friendly)
@bot.tree.command(name="leaderboard", description="Display the CRIT Value leaderboard publicly")
async def leaderboard(interaction: discord.Interaction):
    if not data:
        await interaction.response.send_message(
            "The leaderboard is empty.",
            ephemeral=True
        )
        return

    # Build sorted leaderboard
    sorted_leaderboard = sorted(
        data.items(),
        key=lambda item: (
            item[1]["max_cv"],
            count_artifacts(item[1]["artifacts"], 45),
            count_artifacts(item[1]["artifacts"], 40)
        ),
        reverse=True
    )

    # Header
    lines = [
        "#  | Name    | Max   | 45+ | 40+",
        "---+---------+-------+-----+----"
    ]

    # Rows
    for rank, (user_id, user_data) in enumerate(
        sorted_leaderboard[:MAX_LEADERBOARD_PLAYERS],
        start=1
    ):
        member = interaction.guild.get_member(int(user_id))  # returns a Member or None
        name = get_display_name(user_id, fallback_user=member)
        if len(name) > MAX_NAME_LENGTH:
            name = name[:MAX_NAME_LENGTH - 1] + "-"

        max_cv = user_data["max_cv"]
        count_45 = count_artifacts(user_data["artifacts"], 45)
        count_40 = count_artifacts(user_data["artifacts"], 40)

        # Left-align numbers
        lines.append(
            f"{rank:<2} | "
            f"{name.ljust(MAX_NAME_LENGTH)} | "
            f"{max_cv:<5.2f} | "
            f"{count_45:<3} | "
            f"{count_40:<3}"
        )

    leaderboard_text = "\n".join(lines)
    await interaction.response.send_message(f"```\n{leaderboard_text}\n```")

# Run bot
bot.run(TOKEN)
