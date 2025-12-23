# Artifact CRIT Value Leaderboard Discord Bot

A Discord bot that allows users to submit and track Genshin Impact artifact stats (CRIT Rate & CRIT DMG), calculate CRIT Value (CV), and maintain a leaderboard. Users can submit stats manually or by scanning screenshots.

---

## Installation

1. **Install Python 3.11**
   EasyOCR requires Python 3.11. Download here:
   [https://www.python.org/downloads/release/python-311/](https://www.python.org/downloads/release/python-311/)

2. **(Optional) Create a virtual environment**

```bash
python -m venv venv
# Windows
venv\Scripts\activate
# macOS/Linux
source venv/bin/activate
```

3. **Install dependencies**

```bash
pip install discord.py aiohttp pillow numpy easyocr
```

* `discord.py` → Discord API & slash commands
* `aiohttp` → Async HTTP requests (avatars, images)
* `pillow` → Image handling & resizing
* `numpy` → Image array processing for OCR
* `easyocr` → OCR for scanning artifact screenshots

4. **Run the bot**

```bash
python bot.py
```

> EasyOCR will work without a GPU, but scans are faster with one.

---

## Commands

**Command syntax:**

* All **base commands** are **slash commands** (e.g., `/submit`).
* Everything in `[ ]` is a **literal**.
* Everything in `< >` is a **non-literal argument**.

---

### `/help`

Displays the list of available commands and their descriptions.

---

### `/name <new_name>`

Sets your display name on the leaderboard.

* If no display name is set, your Discord name is used as a fallback.
* Max name length is **8 characters** for mobile readability.

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

* Supports multiple languages (based on `languages.json`), including English and Simplified Chinese.
* Circlets are automatically rejected.
* If a stat is missing in the screenshot, it is **assumed to be `0`**.
* Negative values or impossible stats are automatically adjusted to `0` for CV calculation.
* **Note:** EasyOCR works faster with a GPU. If no GPU is available, scans may take longer.

Example:

```json
"ch_sim": {
  "crit_rate": ["暴击率"],
  "crit_dmg": ["暴击伤害"],
  "circlet": ["理之冠"]
}
```

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
* Ranks are automatically updated after removal.

---

### `/modify <user_identifier> <artifact_index> <crit_rate> <crit_dmg>`

Modify an existing artifact.

* Updates CRIT Rate, CRIT DMG, and recalculates CRIT Value.
* Negative or CRIT Value > 54.6 are **rejected**.
* Ranks are automatically updated based on the new values.

---

### `/leaderboard`

Displays the top artifacts by CRIT Value.

* Shows **max CRIT Value**, number of artifacts ≥ 45 CRIT Value, and number ≥ 40 CRIT Value.
* Maximum of 25 users displayed.
* Names truncated to **8 characters** for mobile readability.

---

## Artifact Rules

* Only **CRIT Rate** and **CRIT DMG** are considered for CRIT Value.
* Circlets are **not allowed**.
* CRIT Value is automatically calculated for all submissions.
* Negative or CRIT Value > 54.6 are **not allowed**.
* Values are stored persistently in `data.json`.

---

## OCR & Multilingual Support

* Uses **EasyOCR** for artifact screenshot scanning.
* Automatically loads languages from `languages.json`.
* Chinese OCR (`ch_sim` or `ch_tra`) **requires English** to be included.
* New languages can be added dynamically by adding a new key in `languages.json` with the fields:

  * `crit_rate`
  * `crit_dmg`
  * `circlet`
* The bot assumes **0** for any missing or invalid stat in a screenshot.
* **Note:** EasyOCR works faster with a GPU. Without a GPU, scans may take longer.

---

## Example Usage

```plaintext
/name jyov
/submit 14.0 22.5
/scan artifact_screenshot.png
/list
/modify jyov 1 10.9 29.5
/remove jyov 1
/leaderboard
/help
```

---