# Artifact CRIT Value Leaderboard Discord Bot

A Discord bot that allows users to submit and track Genshin Impact artifact stats (CRIT Rate & CRIT DMG), calculate CRIT Value (CV), and maintain a leaderboard. Users can submit stats manually or by scanning screenshots.

---

## Installation

1. **Install Python**
   Download the latest version here:
   [https://www.python.org/downloads/](https://www.python.org/downloads/)

2. **Install dependencies**

```bash
pip install discord.py aiohttp pillow numpy easyocr
```

* `discord.py` → Discord API & slash commands
* `aiohttp` → Async HTTP requests (avatars, images, OCR API)
* `pillow` → Image handling & resizing
* `numpy` → Image array processing for OCR
* `easyocr` → OCR backend (via EasyOCR API)

3. **Run the bot**

```bash
python cv_bot.py
```

> The bot uses the **EasyOCR online API**.
> A GPU is not required locally, but OCR speed depends on the API response time.

---

## Commands

**Command syntax:**

* All **base commands** are **slash commands** (e.g., `/submit`).
* Everything in `[ ]` is a **literal**.
* Everything in `< >` is a **non-literal argument**.

---

### `/name <new_name>`

Sets your display name on the leaderboard.

* If no display name is set, your Discord name is used as a fallback.
* Names are truncated on the leaderboard for mobile readability.

---

### `/submit <crit_rate> <crit_dmg>`

Manually submit an artifact.

* `crit_rate` and `crit_dmg` are **percent values** (e.g., 31.1).
* CRIT Value (CV) is automatically calculated:

```
CV = CRIT Rate * 2 + CRIT DMG
```

* Circlets **cannot** be submitted.
* Negative values or CRIT Value > 54.6 are **rejected**.

---

### `/scan <image>`

Scan an artifact screenshot and automatically extract CRIT Rate & CRIT DMG using OCR.

* Uses the **EasyOCR online API**.
* Supports multiple languages loaded from `languages.json`.
* Each user can select their OCR language via `/language`.
* Circlets are automatically rejected.
* If a stat is missing in the screenshot, it is **assumed to be `0`**.
* Negative values or impossible stats are clamped to `0`.

Example `languages.json` entry:

```json
"ch_sim": {
  "crit_rate": ["暴击率"],
  "crit_dmg": ["暴击伤害"],
  "circlet": ["理之冠"]
}
```

---

### `/language <language_code>`

Sets your personal OCR language.

* The list of valid codes is loaded dynamically from `languages.json`.
* The first language in `languages.json` is used as the default.
* If a user's language becomes invalid, it is automatically set to the default.

---

### `/list <user_identifier>`

Lists all artifacts for a user.

* If no user is specified, lists your artifacts.
* Displays **CRIT Rate, CRIT DMG, CRIT Value**, and artifact index.

---

### `/remove <user_identifier> <artifact_index>`

Remove a user or a specific artifact.

* If `artifact_index` is omitted, removes all artifacts and the user from the leaderboard.
* Otherwise, removes the specified artifact.

---

### `/modify <user_identifier> <artifact_index> <crit_rate> <crit_dmg>`

Modify an existing artifact.

* Updates CRIT Rate, CRIT DMG, and recalculates CRIT Value.
* Negative or CRIT Value > 54.6 are **rejected**.

---

### `/leaderboard`

Displays the CRIT Value leaderboard.

* Ranking is based on:

  1. **Max CRIT Value**
  2. **Number of artifacts ≥ 45 CV**
  3. **Number of artifacts ≥ 40 CV**
* Shows **max CRIT Value**, **45+ count**, and **40+ count**.
* Displays up to **99 players**.
* Names are truncated for mobile readability.
* The #1 player’s avatar is shown at the bottom of the embed.

---

## Artifact Rules

* Only **CRIT Rate** and **CRIT DMG** are used for CRIT Value.
* Circlets are **not allowed**.
* CRIT Value is computed as **(2 × CRIT Rate) + CRIT DMG**.
* Negative or CRIT Value > 54.6 are **not allowed**.
* Data is stored persistently in `data.json`.

---

## OCR & Multilingual Support

* OCR languages are loaded dynamically from `languages.json`.
* Each language entry defines:
  * `crit_rate`
  * `crit_dmg`
  * `circlet`
* Each user selects their OCR language with `/language`.
* Missing or invalid OCR values are treated as **0**.

---

## Example Usage

```plaintext
/name jyov
/language ch_sim
/submit 14.0 22.5
/scan artifact_screenshot.png
/list
/modify jyov 1 10.9 29.5
/remove jyov 1
/leaderboard
```

---