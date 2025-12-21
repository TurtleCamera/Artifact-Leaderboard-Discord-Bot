from PIL import Image
import io
import re
import discord
from discord.ext import commands
from discord import app_commands
import json
import os
import easyocr
import numpy as np

# Initialize EasyOCR once
ocr_reader = easyocr.Reader(['en', 'fr'])  # English + French

# Constants
MAX_NAME_LENGTH = 8  # Max name length on leaderboard (longest possible for mobile)
MAX_LEADERBOARD_PLAYERS = 25  # Max players to display on leaderboard (Discord's limit)
DATA_FILE = "data.json"  # Data file

# Setup intents
intents = discord.Intents.default()
intents.message_content = True  # optional for future features
intents.members = True  # Required to fetch guild members

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

# ----------------- Helper Functions -----------------

# Initialize user if they don't exist
def ensure_user(user_id: str, user: discord.User = None):
    if user_id not in data:
        data[user_id] = {
            "display_name": None,
            "username": user.name if user else None,
            "artifacts": [],
            "max_cv": 0
        }

# Get display name
def get_display_name(user_id: str, fallback_user=None):
    user_data = data.get(str(user_id), {})
    display_name = user_data.get("display_name")
    if display_name:
        return display_name
    if fallback_user:
        return getattr(fallback_user, "display_name", fallback_user.name)
    return "Unknown"

# Count artifacts above a CV threshold
def count_artifacts(artifacts, threshold):
    return sum(1 for arti in artifacts if arti["cv"] >= threshold)

# Calculate CV for an artifact
def calculate_cv(crit_rate: float, crit_dmg: float):
    return crit_rate * 2 + crit_dmg

# Get leaderboard ranks
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

# Resolve user identifier to user_id
async def resolve_user(interaction: discord.Interaction, user_identifier: str = None) -> str:
    if not user_identifier:
        return str(interaction.user.id)

    user_identifier_lower = user_identifier.lower()

    # 1. Check if identifier is a mention <@!id> or <@id>
    match = re.match(r"<@!?(\d+)>", user_identifier)
    if match:
        uid = match.group(1)
        if uid in data:
            return uid

    # 2. Match leaderboard display name (case-insensitive)
    for uid, udata in data.items():
        display_name = udata.get("display_name")
        if display_name and display_name.lower() == user_identifier_lower:
            return uid

    # 3. Match stored Discord username (case-insensitive)
    for uid, udata in data.items():
        username = udata.get("username")
        if username and username.lower() == user_identifier_lower:
            return uid

    # 4. Match plain username in guild (case-insensitive)
    for member in interaction.guild.members:
        if member.name.lower() == user_identifier_lower:
            ensure_user(str(member.id), member)
            return str(member.id)

    return None

# Build rank change message
def build_rank_message(old_rank, new_rank, is_new_user=False):
    if is_new_user:
        return f"Entered leaderboard at rank #{new_rank}"
    if new_rank < old_rank:
        return f"▲ +{old_rank - new_rank} → #{new_rank}"
    if new_rank > old_rank:
        return f"▼ -{new_rank - old_rank} → #{new_rank}"
    return f"▬ Unchanged (#{new_rank})"

# ----------------- Events -----------------

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")

    # Backfill missing usernames in data.json
    data_changed = False
    for uid, udata in data.items():
        # Only backfill if username is missing or empty
        if not udata.get("username"):
            try:
                user = await bot.fetch_user(int(uid))
                if user:
                    udata["username"] = user.name
                    data_changed = True
            except Exception:
                continue

    # Save only if we actually changed something
    if data_changed:
        save_data(data)
        print("Backfilled missing usernames in data.json")

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

# ----------------- Commands -----------------

# /name command
@bot.tree.command(name="name", description="Change your display name on the leaderboard")
@app_commands.describe(new_name="The name you want to display on the leaderboard")
async def name(interaction: discord.Interaction, new_name: str):
    user_id = str(interaction.user.id)
    ensure_user(user_id)
    data[user_id]["display_name"] = new_name
    save_data(data)  # Save after update
    await interaction.response.send_message(
        f"Your leaderboard name is now set to: **{new_name}**",
        ephemeral=True
    )

# /submit command
@bot.tree.command(name="submit", description="Submit an artifact (CRIT Rate & CRIT DMG)")
@app_commands.describe(crit_rate="CRIT Rate of artifact", crit_dmg="CRIT DMG of artifact")
async def submit(interaction: discord.Interaction, crit_rate: float, crit_dmg: float):
    user_id = str(interaction.user.id)
    was_new_user = user_id not in data
    ensure_user(user_id)

    old_rank = get_leaderboard_ranks().get(user_id)

    # Calculate CV and add artifact
    cv = calculate_cv(crit_rate, crit_dmg)
    artifact = {"crit_rate": crit_rate, "crit_dmg": crit_dmg, "cv": cv}
    data[user_id]["artifacts"].append(artifact)
    data[user_id]["max_cv"] = max(data[user_id]["max_cv"], cv)
    save_data(data)  # Save after addition

    # Calculate new rank and build message
    new_rank = get_leaderboard_ranks().get(user_id)
    rank_msg = build_rank_message(old_rank, new_rank, was_new_user)

    # Use temporary webhook to preserve user display
    channel = interaction.channel
    webhook = await channel.create_webhook(name="ArtiBotTempWebhook")
    await webhook.send(
        content=f"Artifact submitted to CRIT Value leaderboard: {cv:.1f} CV\nRank: {rank_msg}",
        username=interaction.user.display_name,
        avatar_url=interaction.user.display_avatar.url
    )
    await webhook.delete()

    await interaction.response.send_message(
        "Your artifact has been submitted!",
        ephemeral=True
    )

# /list command
@bot.tree.command(name="list", description="List all artifacts for a user")
@app_commands.describe(user_identifier="Optional: leaderboard name or Discord username")
async def list_artifacts(interaction: discord.Interaction, user_identifier: str = None):
    target_user_id = await resolve_user(interaction, user_identifier)
    if not target_user_id or target_user_id not in data:
        msg = "You don't have any artifacts on the leaderboard yet." if not user_identifier else f"User '{user_identifier}' not found in the leaderboard."
        await interaction.response.send_message(msg, ephemeral=True)
        return

    user_data = data[target_user_id]
    if not user_data.get("artifacts"):
        await interaction.response.send_message("No artifacts found for this user.", ephemeral=True)
        return

    # Build artifact list table
    lines = [
        "Index | CR   | CD   | CV   ",
        "------+------+------+-----"
    ]
    for idx, arti in enumerate(user_data["artifacts"], start=1):  # 1-based indexing
        lines.append(f"{idx:<5} | {arti['crit_rate']:<4.1f} | {arti['crit_dmg']:<4.1f} | {arti['cv']:<4.1f}")

    artifact_text = "\n".join(lines)
    display_name = get_display_name(target_user_id, interaction.user)
    await interaction.response.send_message(f"Artifacts for **{display_name}**:\n```\n{artifact_text}\n```", ephemeral=True)

# /remove command
@bot.tree.command(name="remove", description="Remove a user or a specific artifact")
@app_commands.describe(
    user_identifier="Leaderboard name or Discord username",
    artifact_index="Optional: index of artifact to remove (1-based). Leave empty to remove the whole user"
)
async def remove(interaction: discord.Interaction, user_identifier: str, artifact_index: int = None):
    target_user_id = await resolve_user(interaction, user_identifier)
    if not target_user_id or target_user_id not in data:
        await interaction.response.send_message(f"User '{user_identifier}' not found in the leaderboard.", ephemeral=True)
        return

    user_data = data[target_user_id]

    if artifact_index is not None:
        artifacts = user_data.get("artifacts", [])
        if artifact_index < 1 or artifact_index > len(artifacts):
            await interaction.response.send_message(
                f"Invalid artifact index. Please provide a number between 1 and {len(artifacts)}.",
                ephemeral=True
            )
            return

        # Remove specified artifact
        removed = artifacts.pop(artifact_index - 1)
        user_data["max_cv"] = max((arti["cv"] for arti in artifacts), default=0)
        save_data(data)  # Save after artifact removal
        await interaction.response.send_message(
            f"Removed artifact #{artifact_index} for **{get_display_name(target_user_id, interaction.user)}**.",
            ephemeral=True
        )
        return

    # Remove entire user
    removed_name = get_display_name(target_user_id, interaction.user)
    data.pop(target_user_id)
    save_data(data)  # Save after user removal
    await interaction.response.send_message(f"Removed **{removed_name}** and all their artifacts from the leaderboard.", ephemeral=True)

# /modify command
@bot.tree.command(name="modify", description="Modify an existing artifact")
@app_commands.describe(
    user_identifier="Leaderboard name or Discord username",
    artifact_index="Index of the artifact to modify (1-based)",
    crit_rate="New CRIT Rate value",
    crit_dmg="New CRIT DMG value"
)
async def modify(interaction: discord.Interaction, user_identifier: str, artifact_index: int, crit_rate: float, crit_dmg: float):
    target_user_id = await resolve_user(interaction, user_identifier)
    if not target_user_id or target_user_id not in data:
        await interaction.response.send_message(f"User '{user_identifier}' not found in the leaderboard.", ephemeral=True)
        return

    artifacts = data[target_user_id]["artifacts"]
    if artifact_index < 1 or artifact_index > len(artifacts):
        await interaction.response.send_message(
            f"Invalid artifact index. Please provide a number between 1 and {len(artifacts)}.",
            ephemeral=True
        )
        return

    artifact = artifacts[artifact_index - 1]
    old_cv, old_cr, old_cd = artifact["cv"], artifact["crit_rate"], artifact["crit_dmg"]

    # Update artifact values
    artifact["crit_rate"], artifact["crit_dmg"], artifact["cv"] = crit_rate, crit_dmg, calculate_cv(crit_rate, crit_dmg)
    data[target_user_id]["max_cv"] = max((arti["cv"] for arti in artifacts), default=0)
    save_data(data)  # Save after modification

    old_rank = get_leaderboard_ranks().get(target_user_id)
    new_rank = get_leaderboard_ranks().get(target_user_id)
    rank_msg = build_rank_message(old_rank, new_rank)

    await interaction.response.send_message(
        f"Modified artifact #{artifact_index} for **{get_display_name(target_user_id, interaction.user)}**:\n"
        f"CRIT Rate: {old_cr:.1f} → {crit_rate:.1f}\n"
        f"CRIT DMG: {old_cd:.1f} → {crit_dmg:.1f}\n"
        f"CV: {old_cv:.1f} → {artifact['cv']:.1f}\n"
        f"Rank: {rank_msg}",
        ephemeral=True
    )

# /scan command
@bot.tree.command(name="scan", description="Scan an artifact screenshot")
@app_commands.describe(image="Upload a screenshot of your artifact")
async def scan(interaction: discord.Interaction, image: discord.Attachment):
    await interaction.response.defer()  # Allow processing time
    user_id = str(interaction.user.id)
    was_new_user = user_id not in data
    ensure_user(user_id)

    try:
        # Download the image and convert to NumPy array
        image_bytes = await image.read()
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img_np = np.array(img)

        # Run OCR
        ocr_results = ocr_reader.readtext(img_np)
        ocr_text = "\n".join([text for _, text, _ in ocr_results])
    except Exception as e:
        await interaction.followup.send(
            f"OCR failed to process the image.\nError: {str(e)}",
            ephemeral=True
        )
        return

    # Detect circlets
    if any(word.lower() in ocr_text.lower() for word in ["circlet", "diadème"]):
        await interaction.followup.send(
            "Circlets are not allowed, sorry!",
            ephemeral=True
        )
        return

    # Extract CRIT Rate and CRIT DMG using regex
    crit_rate = crit_dmg = 0.0  # default to 0
    for line in ocr_text.splitlines():
        line_clean = line.lower().replace("%", "").strip()
        numbers = re.findall(r"\d+[.,]?\d*", line_clean)
        if not numbers:
            continue
        try:
            value = float(numbers[-1].replace(',', '.'))
        except ValueError:
            continue

        if "dgt crit" in line_clean or "crit dmg" in line_clean:
            crit_dmg = value
        elif "taux crit" in line_clean or "crit rate" in line_clean:
            crit_rate = value

    # Now crit_rate and crit_dmg are always numbers (0 if not found)
    cv = calculate_cv(crit_rate, crit_dmg)

    # Permanently add artifact
    artifact = {"crit_rate": crit_rate, "crit_dmg": crit_dmg, "cv": cv}
    data[user_id]["artifacts"].append(artifact)
    data[user_id]["max_cv"] = max(data[user_id]["max_cv"], cv)
    save_data(data)  # Save permanently

    # Calculate leaderboard ranks
    old_rank = get_leaderboard_ranks().get(user_id)
    new_rank = get_leaderboard_ranks().get(user_id)
    rank_msg = build_rank_message(old_rank, new_rank, was_new_user)

    # Send scan result with the uploaded image
    await interaction.followup.send(
        content=(
            f"Scan result:\n"
            f"CRIT Rate: {crit_rate:.1f}\n"
            f"CRIT DMG: {crit_dmg:.1f}\n"
            f"CRIT Value: {cv:.1f}\n"
            f"Rank: {rank_msg}"
        ),
        file=discord.File(fp=io.BytesIO(image_bytes), filename=image.filename),
        ephemeral=False
    )

# /leaderboard command
@bot.tree.command(name="leaderboard", description="Display the CRIT Value leaderboard publicly")
async def leaderboard(interaction: discord.Interaction):
    if not data:
        await interaction.response.send_message("The leaderboard is empty.", ephemeral=True)
        return

    sorted_leaderboard = sorted(
        data.items(),
        key=lambda item: (
            item[1]["max_cv"],
            count_artifacts(item[1]["artifacts"], 45),
            count_artifacts(item[1]["artifacts"], 40)
        ),
        reverse=True
    )

    lines = ["#  | Name     | Max  | 45+ | 40+", "---+----------+------+-----+----"]

    for rank, (user_id, user_data) in enumerate(sorted_leaderboard[:MAX_LEADERBOARD_PLAYERS], start=1):
        # Try to get the member from guild cache first; fetch from API if not cached
        member = interaction.guild.get_member(int(user_id))
        if not member:
            try:
                member = await bot.fetch_user(int(user_id))
            except Exception:
                member = None

        # Use leaderboard display name or Discord username
        name = get_display_name(user_id, fallback_user=member)
        if len(name) > MAX_NAME_LENGTH:
            name = name[:MAX_NAME_LENGTH - 1] + "-"

        lines.append(
            f"{rank:<2} | {name.ljust(MAX_NAME_LENGTH)} | {user_data['max_cv']:<4.1f} | "
            f"{count_artifacts(user_data['artifacts'], 45):<3} | {count_artifacts(user_data['artifacts'], 40):<3}"
        )

    await interaction.response.send_message(f"```\n{chr(10).join(lines)}\n```")

# Run bot
bot.run(TOKEN)
