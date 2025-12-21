# Artifact CRIT Value Leaderboard Discord Bot

A Discord bot that allows users to submit and track Genshin Impact artifact stats (CRIT Rate & CRIT DMG), calculate CRIT Value (CV), and maintain a leaderboard. Users can submit stats manually or by scanning screenshots.

---

## Commands

> **Command syntax:**
>
> * All **base commands** are **slash commands** (e.g., `/submit`).
> * Everything in `[ ]` is a **literal**.
> * Everything in `< >` is a **non-literal argument** (something you provide, like a number or image).

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
* CV is automatically calculated:

  ```
  CV = CRIT Rate * 2 + CRIT DMG
  ```
* Circlets **cannot** be submitted.

---

### `/scan <image>`

Scan an artifact screenshot and automatically extract CRIT Rate & CRIT DMG using OCR.

* Supports multiple languages (based on `languages.json`), including English, French, and Simplified Chinese.
* Circlets are automatically rejected.
* Fails gracefully if no valid stats are detected.

---

### `/list [user_identifier]`

Lists all artifacts for a user.

* If no user is specified, lists your artifacts.
* Displays **CRIT Rate, CRIT DMG, CV**, and artifact index.

---

### `/remove <user_identifier> [artifact_index]`

Remove a user or a specific artifact.

* If `artifact_index` is omitted, removes all artifacts and the user from the leaderboard.
* Otherwise, removes the specified artifact.

---

### `/modify <user_identifier> <artifact_index> <crit_rate> <crit_dmg>`

Modify an existing artifact.

* Updates CRIT Rate, CRIT DMG, and recalculates CV.
* Can adjust rank automatically based on the new values.

---

### `/leaderboard`

Displays the top artifacts by CRIT Value.

* Shows **max CV**, number of artifacts ≥ 45 CV, and number ≥ 40 CV.
* Maximum of 25 users displayed.
* Names truncated to **8 characters** for mobile readability.

---

## Artifact Rules

* Only **CRIT Rate** and **CRIT DMG** are considered for CV.
* Circlets are **not allowed**.
* CV is automatically calculated for all submissions.
* Values are stored persistently in `data.json`.

---

## OCR & Multilingual Support

* Uses **EasyOCR** for artifact screenshot scanning.
* Automatically loads languages from `languages.json`.
* Chinese OCR (`ch_sim` or `ch_tra`) **requires English** to be included.
* New languages can be added by adding a new key in `languages.json` with the following fields:

  * `crit_rate`
  * `crit_dmg`
  * `circlet`

Example:

```json
"jp": {
    "crit_rate": ["会心率"],
    "crit_dmg": ["会心ダメージ"],
    "circlet": ["冠"]
}
```

---

## Example Usage

```plaintext
/name Diluc
/submit 31.1 62.2
/scan artifact_screenshot.png
/list
/modify Diluc 1 33.0 65.0
/remove Diluc 1
/leaderboard
/help
```

---