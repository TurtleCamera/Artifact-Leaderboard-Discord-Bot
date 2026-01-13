from PIL import Image
import io
from io import BytesIO
import unicodedata
import re
import discord
from discord.ext import commands
from discord import app_commands, Embed
import json
import os
import aiohttp
import traceback

# Constants
MAX_CV = 54.6  # Maximum allowed CRIT Value
MAX_NAME_LENGTH = 13  # Max name length on leaderboard (longest possible for mobile)
MAX_LEADERBOARD_PLAYERS = 99  # Max players to display on leaderboard
MAX_AVATAR_FETCH_SIZE = 200 # Max bytes to fetch at once
AVATAR_DISPLAY_SIZE = 64    # Resize avatar
DATA_FILE = "data.json"  # Data file
LANG_FILE = "languages.json"  # Multilingual mapping
EASYOCR_API_URL = "https://api.easyocr.org/ocr"

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

# Load language mappings
def load_languages():
    if os.path.exists(LANG_FILE):
        with open(LANG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    # Default languages if file missing
    return {
        "en": {
            "crit_rate": ["crit rate"],
            "crit_dmg": ["crit dmg"],
            "circlet": ["circlet"]
        },
        "ch_sim": {
            "crit_rate": ["暴击率"],
            "crit_dmg": ["暴击伤害"],
            "circlet": ["理之冠"]
        }
    }

# Load language mappings
languages = load_languages()  # your JSON loader

# Build OCR language list directly from JSON keys
ocr_languages = list(languages.keys())

# EasyOCR requires English whenever Chinese is included
chinese_keys = {"ch_sim", "ch_tra"}
if any(l in chinese_keys for l in ocr_languages) and "en" not in ocr_languages:
    ocr_languages.append("en")  # always include English

# ----------------- Helper Functions -----------------

# Initialize user if they don't exist
def ensure_user(user_id: str, user: discord.User = None):
    if user_id not in data:
        data[user_id] = {
            "display_name": None,
            "username": user.name if user else None,
            "artifacts": [],
            "max_cv": 0,
            "language": "en"  # default language
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

# Validate CRIT Rate and CRIT DMG. Returns sanitized values and an error message if invalid.
def validate_artifact_stats(crit_rate: float, crit_dmg: float) -> (float, float, str):
    # Negative values are invalid
    if crit_rate < 0 or crit_dmg < 0:
        return 0, 0, "CRIT Rate and CRIT DMG cannot be negative."

    cv = calculate_cv(crit_rate, crit_dmg)
    if cv > MAX_CV:
        return 0, 0, f"CRIT Value cannot exceed {MAX_CV:.1f}. Submitted CV = {cv:.1f}."

    return crit_rate, crit_dmg, None

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

    # 1. Match leaderboard display name (case-insensitive)
    for uid, udata in data.items():
        display_name = udata.get("display_name")
        if display_name and display_name.lower() == user_identifier_lower:
            return uid

    # 2. Match guild member display name (nickname or username fallback)
    for member in interaction.guild.members:
        if member.display_name.lower() == user_identifier_lower:
            return str(member.id)

    # 3. Match plain Discord username (case-insensitive)
    for member in interaction.guild.members:
        if member.name.lower() == user_identifier_lower:
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

# Normalize text (usually used for circlet detection)
def normalize_text(text: str) -> str:
    """
    Lowercase and remove accents/diacritics for consistent matching.
    """
    text = text.lower()
    text = unicodedata.normalize('NFD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    return text

# Parse artifact text for all languages in languages.json
def parse_artifact_text(ocr_text: str):
    crit_rate = crit_dmg = 0.0

    # Split OCR text into lines and normalize
    lines = [normalize_text(line.replace("%", "").strip()) for line in ocr_text.splitlines()]

    # Prepare normalized circlet keywords once
    circlet_keywords_all = set()
    crit_rate_keywords_all = set()
    crit_dmg_keywords_all = set()
    for lang_map in languages.values():
        circlet_keywords_all.update(normalize_text(k) for k in lang_map.get("circlet", []))
        crit_rate_keywords_all.update(normalize_text(k) for k in lang_map.get("crit_rate", []))
        crit_dmg_keywords_all.update(normalize_text(k) for k in lang_map.get("crit_dmg", []))

    for line_clean in lines:
        # First, check if this line is a circlet
        if any(word in line_clean for word in circlet_keywords_all):
            return None, None, True  # Circlet detected, stop immediately

        # Extract numeric values if not circlet
        numbers = re.findall(r"\d+[.,]?\d*", line_clean)
        if not numbers:
            continue
        try:
            value = float(numbers[-1].replace(",", "."))
        except ValueError:
            continue

        # Check for CRIT DMG
        if any(word in line_clean for word in crit_dmg_keywords_all):
            crit_dmg = value
        # Check for CRIT Rate
        if any(word in line_clean for word in crit_rate_keywords_all):
            crit_rate = value

    return crit_rate, crit_dmg, False

# Send image to EasyOCR online and return the recognized text as a string.
async def online_easyocr(image_bytes: bytes, languages: list = None):
    languages = languages or ["en"]
    lang_str = ",".join(languages)

    data = aiohttp.FormData()
    data.add_field("file", image_bytes, filename="image.png", content_type="image/png")
    data.add_field("lang", lang_str)

    async with aiohttp.ClientSession() as session:
        async with session.post(EASYOCR_API_URL, data=data) as resp:
            if resp.status != 200:
                text = await resp.text()
                raise Exception(f"OCR API failed: {resp.status}, {text}")
            result_json = await resp.json()

    # Convert JSON 'words' array into plain text lines
    words = result_json.get("words", [])
    text_lines = [word["text"] for word in words]
    return "\n".join(text_lines)

# Download profile pictures
async def fetch_avatar_bytes(url: str) -> BytesIO:
    async with aiohttp.ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                return None
            data = await resp.read()
            return BytesIO(data)

# ----------------- Events -----------------

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")
    print("------")

    # Backfill missing usernames in data.json
    data_changed = False
    for uid, udata in data.items():
        if not udata.get("username"):
            try:
                user = await bot.fetch_user(int(uid))
                if user:
                    udata["username"] = user.name
                    data_changed = True
            except Exception:
                continue
    if data_changed:
        save_data(data)
        print("Backfilled missing usernames in data.json")

    # Try to load guild ID and sync commands, but don't crash if invalid
    try:
        with open("guild_id", "r") as f:
            guild_id_str = f.read().strip()
            GUILD_ID = int(guild_id_str)
        guild = discord.Object(id=GUILD_ID)

        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        print(f"Synced {len(synced)} command(s) to guild {GUILD_ID}")
    except FileNotFoundError:
        print("No guild_id file found. Running bot without guild-specific command syncing.")
    except ValueError:
        print(f"Invalid guild_id value: '{guild_id_str}'. Running bot without guild-specific command syncing.")
    except discord.HTTPException as e:
        print(f"Guild ID {guild_id_str} does not link to a valid server or failed to sync: {e}")
    except Exception as e:
        print(f"Unexpected error during guild sync: {e}")

# ----------------- Commands -----------------

# /name
@bot.tree.command(name="name", description="Change your display name on the leaderboard")
@app_commands.describe(new_name="The name you want to display on the leaderboard")
async def name(interaction: discord.Interaction, new_name: str):
    user_id = str(interaction.user.id)
    ensure_user(user_id)
    data[user_id]["display_name"] = new_name
    save_data(data)
    embed = Embed(
        title="Leaderboard Name Updated",
        description=f"Your leaderboard name is now set to **{new_name}**",
        color=0x1abc9c
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

# /submit
@bot.tree.command(name="submit", description="Submit an artifact (CRIT Rate & CRIT DMG)")
@app_commands.describe(crit_rate="CRIT Rate of artifact", crit_dmg="CRIT DMG of artifact")
async def submit(interaction: discord.Interaction, crit_rate: float, crit_dmg: float):
    user_id = str(interaction.user.id)
    was_new_user = user_id not in data
    ensure_user(user_id)

    # Validate stats
    crit_rate, crit_dmg, error = validate_artifact_stats(crit_rate, crit_dmg)
    if error:
        embed = Embed(
            title="Invalid Artifact Stats",
            description=error,
            color=0xe74c3c
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    old_rank = get_leaderboard_ranks().get(user_id)
    cv = calculate_cv(crit_rate, crit_dmg)

    artifact = {"crit_rate": crit_rate, "crit_dmg": crit_dmg, "cv": cv}
    data[user_id]["artifacts"].append(artifact)
    data[user_id]["max_cv"] = max(data[user_id]["max_cv"], cv)
    save_data(data)

    new_rank = get_leaderboard_ranks().get(user_id)
    rank_msg = build_rank_message(old_rank, new_rank, was_new_user)

    embed = Embed(title="Artifact Submitted", color=0x1abc9c)
    embed.add_field(
        name="",  # invisible field name
        value=(
            f"CRIT Rate: {crit_rate:.1f}%\n"
            f"CRIT DMG: {crit_dmg:.1f}%\n"
            f"**CRIT Value: {cv:.1f}**"
        ),
        inline=False
    )
    embed.add_field(
        name=f"**Rank:** {rank_msg}",
        value=(""),
        inline=False
    )
    embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)

    await interaction.response.send_message(embed=embed)

# /list
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

    lines = ["Index | CR   | CD   | CV   ", "------+------+------+-----"]
    for idx, arti in enumerate(user_data["artifacts"], start=1):
        lines.append(f"{idx:<5} | {arti['crit_rate']:<4.1f} | {arti['crit_dmg']:<4.1f} | {arti['cv']:<4.1f}")

    artifact_text = "\n".join(lines)
    target_member = interaction.guild.get_member(int(target_user_id))
    display_name = get_display_name(target_user_id, fallback_user=target_member)
    embed = Embed(
        title=f"Artifacts for {display_name}",
        description=f"```\n{artifact_text}\n```",
        color=0x3498db
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

# /remove
@bot.tree.command(name="remove", description="Remove a user or a specific artifact")
@app_commands.describe(
    user_identifier="Leaderboard name or Discord username",
    artifact_index="Optional: index of artifact to remove (1-based). Leave empty to remove the whole user"
)
async def remove(interaction: discord.Interaction, user_identifier: str, artifact_index: int = None):
    target_user_id = await resolve_user(interaction, user_identifier)
    if not target_user_id or target_user_id not in data:
        embed = Embed(
            title="User Not Found",
            description=f"User '{user_identifier}' not found in the leaderboard.",
            color=0xe74c3c
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    user_data = data[target_user_id]

    if artifact_index is not None:
        artifacts = user_data.get("artifacts", [])
        if artifact_index < 1 or artifact_index > len(artifacts):
            embed = Embed(
                title="Invalid Artifact Index",
                description=f"Please provide a number between 1 and {len(artifacts)}.",
                color=0xe74c3c
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

        old_rank = get_leaderboard_ranks().get(target_user_id)

        removed = artifacts.pop(artifact_index - 1)
        user_data["max_cv"] = max((arti["cv"] for arti in artifacts), default=0)
        save_data(data)

        new_rank = get_leaderboard_ranks().get(target_user_id)
        rank_msg = build_rank_message(old_rank, new_rank)

        target_member = interaction.guild.get_member(int(target_user_id))
        display_name = get_display_name(target_user_id, fallback_user=target_member)

        embed = discord.Embed(title="Artifact Removed", color=0xe74c3c)
        embed.description = f"Removed artifact #{artifact_index} for **{display_name}**."
        embed.add_field(name="Rank", value=rank_msg, inline=False)

        await interaction.response.send_message(embed=embed)
        return

    old_rank = get_leaderboard_ranks().get(target_user_id)
    removed_name = get_display_name(target_user_id, fallback_user=interaction.guild.get_member(int(target_user_id)))
    data.pop(target_user_id)
    save_data(data)

    embed = discord.Embed(title="User Removed", color=0xe74c3c)
    embed.description = f"Removed **{removed_name}** and all of their artifacts from the leaderboard."
    embed.add_field(name="Previous Rank", value=f"#{old_rank}", inline=False)

    await interaction.response.send_message(embed=embed)

# /modify
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
        embed = Embed(
            title="User Not Found",
            description=f"User '{user_identifier}' not found in the leaderboard.",
            color=0xe74c3c
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    artifacts = data[target_user_id]["artifacts"]
    if artifact_index < 1 or artifact_index > len(artifacts):
        embed = Embed(
            title="Invalid Artifact Index",
            description=f"Please provide a number between 1 and {len(artifacts)}.",
            color=0xe74c3c
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    # Validate new stats
    crit_rate, crit_dmg, error = validate_artifact_stats(crit_rate, crit_dmg)
    if error:
        embed = Embed(
            title="Invalid Artifact Stats",
            description=f"Cannot modify artifact: {error}",
            color=0xe74c3c
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    old_rank = get_leaderboard_ranks().get(target_user_id)
    artifact = artifacts[artifact_index - 1]
    old_cv, old_cr, old_cd = artifact["cv"], artifact["crit_rate"], artifact["crit_dmg"]

    artifact["crit_rate"], artifact["crit_dmg"], artifact["cv"] = crit_rate, crit_dmg, calculate_cv(crit_rate, crit_dmg)
    data[target_user_id]["max_cv"] = max((arti["cv"] for arti in artifacts), default=0)
    save_data(data)

    new_rank = get_leaderboard_ranks().get(target_user_id)
    rank_msg = build_rank_message(old_rank, new_rank)
    target_member = interaction.guild.get_member(int(target_user_id))
    display_name = get_display_name(target_user_id, fallback_user=target_member)

    embed = discord.Embed(title=f"Artifact #{artifact_index} Modified", color=0xf1c40f)
    embed.set_author(name=display_name)
    embed.add_field(
        name="",  # invisible field name
        value=(
            f"CRIT Rate: {old_cr:.1f}% → {crit_rate:.1f}%\n"
            f"CRIT DMG: {old_cd:.1f}% → {crit_dmg:.1f}%\n"
            f"**CRIT Value: {old_cv:.1f} → {artifact['cv']:.1f}**"
        ),
        inline=False
    )
    embed.add_field(
        name=f"**Rank:** {rank_msg}",
        value=(""),
        inline=False
    )

    await interaction.response.send_message(embed=embed)

# /scan command
async def handle_scan(interaction: discord.Interaction, image: discord.Attachment):
    user_id = str(interaction.user.id)
    was_new_user = user_id not in data
    ensure_user(user_id)

    user_lang = data[user_id].get("language", "en")
    ocr_langs_to_use = [user_lang]

    # Always include English for fallback
    if "en" not in ocr_langs_to_use:
        ocr_langs_to_use.append("en")

    # Send a "processing" embed
    processing_embed = Embed(
        title="Scanning Artifact...",
        description=f"OCR is running using languages: {', '.join(ocr_langs_to_use)}",
        color=0x3498db
    )
    await interaction.response.send_message(embed=processing_embed)

    try:
        image_bytes = await image.read()
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        output_bytes = BytesIO()
        img.save(output_bytes, format="PNG")
        output_bytes.seek(0)

        ocr_text = await online_easyocr(output_bytes.getvalue(), languages=ocr_langs_to_use)

    except Exception as e:
        error_embed = Embed(
            title="OCR Failed",
            description=f"OCR failed to process the image.",
            color=0xe74c3c
        )
        await interaction.edit_original_response(embed=error_embed)
        return

    crit_rate, crit_dmg, circlet_detected = parse_artifact_text(ocr_text)

    # Circlets aren't allowed
    if circlet_detected:
        circlet_embed = Embed(
            title="Invalid Artifact",
            description="Circlets are not allowed, sorry!",
            color=0xe74c3c
        )
        await interaction.edit_original_response(embed=circlet_embed)
        return

    # Validate artifact
    crit_rate = crit_rate or 0.0
    crit_dmg = crit_dmg or 0.0
    crit_rate, crit_dmg, error = validate_artifact_stats(crit_rate, crit_dmg)
    if error:
        crit_rate = crit_dmg = 0.0

    # Calcualte CV and store artifact
    cv = calculate_cv(crit_rate, crit_dmg)
    artifact = {"crit_rate": crit_rate, "crit_dmg": crit_dmg, "cv": cv}
    data[user_id]["artifacts"].append(artifact)
    data[user_id]["max_cv"] = max(data[user_id]["max_cv"], cv)
    save_data(data)

    # Update user's rank
    old_rank = get_leaderboard_ranks().get(user_id)
    new_rank = get_leaderboard_ranks().get(user_id)
    rank_msg = build_rank_message(old_rank, new_rank, was_new_user)

    result_embed = Embed(title="Artifact Scan Result", color=0x1abc9c)
    result_embed.add_field(
        name="", value=(
            f"CRIT Rate: {crit_rate:.1f}%\n"
            f"CRIT DMG: {crit_dmg:.1f}%\n"
            f"**CRIT Value: {cv:.1f}**"
        ), inline=False
    )
    result_embed.add_field(name=f"**Rank:** {rank_msg}", value="", inline=False)
    result_embed.set_thumbnail(url="attachment://" + image.filename)

    try:
        await interaction.edit_original_response(
            embed=result_embed,
            attachments=[discord.File(io.BytesIO(image_bytes), filename=image.filename)]
        )
    except Exception as e:
        # Fallback if the screenshot failed to send
        result_embed.set_footer(text="Screenshot could not be attached because it took too long to send to Discord.")
        await interaction.edit_original_response(
            embed=result_embed
        )

@bot.tree.command(name="scan", description="Scan an artifact screenshot")
@app_commands.describe(image="Upload a screenshot of your artifact")
async def scan(interaction: discord.Interaction, image: discord.Attachment):
    await handle_scan(interaction, image)

@bot.tree.command(name="sc", description="Shortcut for /scan")
@app_commands.describe(image="Upload a screenshot of your artifact")
async def scan_short(interaction: discord.Interaction, image: discord.Attachment):
    await handle_scan(interaction, image)

# /language
language_codes = ", ".join(languages.keys()) # Build dynamic description for the /language command
@bot.tree.command(name="language", description="Set your OCR language for artifact scanning")
@app_commands.describe(language=f"Available options: {language_codes}")
async def language(interaction: discord.Interaction, language: str):
    user_id = str(interaction.user.id)
    ensure_user(user_id)
    
    language = language.lower()
    if language not in languages:
        embed = Embed(
            title="Invalid Language",
            description=f"Available language codes: {language_codes}",
            color=0xe74c3c
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    data[user_id]["language"] = language
    save_data(data)

    embed = Embed(
        title="OCR Language Updated",
        description=f"Your artifact OCR language has been set to **{language}** ✅",
        color=0x1abc9c
    )
    await interaction.response.send_message(embed=embed, ephemeral=True)

# /leaderboard
@bot.tree.command(name="leaderboard", description="Display the CRIT Value leaderboard publicly")
async def leaderboard(interaction: discord.Interaction):
    if not data:
        embed = Embed(
            title="Leaderboard Empty",
            description="No artifacts have been submitted yet.",
            color=0xe74c3c
        )
        await interaction.response.send_message(embed=embed)
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

    lines = [
        "# |Name         |Max |45+|40+",
        "--+-------------+----+---+---"
    ]

    top_user_member = None

    for rank, (user_id, user_data) in enumerate(
        sorted_leaderboard[:MAX_LEADERBOARD_PLAYERS], start=1
    ):
        member = interaction.guild.get_member(int(user_id))
        if not member:
            try:
                member = await bot.fetch_user(int(user_id))
            except Exception:
                member = None

        # Save #1 player's member object
        if rank == 1 and member:
            top_user_member = member

        name = get_display_name(user_id, fallback_user=member)
        if len(name) > MAX_NAME_LENGTH:
            name = name[:MAX_NAME_LENGTH - 1] + "-"

        lines.append(
            f"{rank:<2}|{name.ljust(MAX_NAME_LENGTH)}|"
            f"{user_data['max_cv']:<2.1f}|"
            f"{count_artifacts(user_data['artifacts'], 45):<3}|"
            f"{count_artifacts(user_data['artifacts'], 40):<3}"
        )

    # Build embed with leaderboard text
    description_text = f"```\n{chr(10).join(lines)}\n```"
    embed = Embed(
        title="CRIT Value Leaderboard",
        description=description_text,
        color=0x3498db
    )

    # If top player exists, attach their avatar at the bottom with a label
    if top_user_member:
        avatar_url = top_user_member.display_avatar.url
        async with aiohttp.ClientSession() as session:
            async with session.get(avatar_url) as resp:
                if resp.status == 200:
                    avatar_bytes = await resp.read()

                    # Open image and resize with high-quality resampling
                    img = Image.open(BytesIO(avatar_bytes)).convert("RGBA")
                    img = img.resize((AVATAR_DISPLAY_SIZE, AVATAR_DISPLAY_SIZE), resample=Image.LANCZOS)

                    # Save to BytesIO for Discord upload
                    output = BytesIO()
                    img.save(output, format="PNG")
                    output.seek(0)

                    # Prepare file and embed
                    file = discord.File(output, filename="top_avatar.png")
                    top_name = get_display_name(top_user_member.id, fallback_user=top_user_member)
                    embed.add_field(name=f"I'm sick of {top_name}.", value="", inline=True)
                    embed.set_image(url="attachment://top_avatar.png")

                    await interaction.response.send_message(embed=embed, file=file)
                    return

    # Fallback: send embed without image
    await interaction.response.send_message(embed=embed)

# Run bot
bot.run(TOKEN)
