import random
import json

data = {}

for i in range(1, 51):  # 50 example players
    user_id = str(100000000000000000 + i)
    display_name = f"Player{i}"
    artifacts = []
    for _ in range(random.randint(1, 5)):  # each player has 1-5 artifacts
        crit_rate = round(random.uniform(1, 20), 1)
        crit_dmg = round(random.uniform(10, 70), 1)
        cv = crit_rate * 2 + crit_dmg
        artifacts.append({"crit_rate": crit_rate, "crit_dmg": crit_dmg, "cv": cv})
    max_cv = max(a["cv"] for a in artifacts)
    data[user_id] = {"display_name": display_name, "artifacts": artifacts, "max_cv": max_cv}

# Save to JSON
with open("data.json", "w") as f:
    json.dump(data, f, indent=4)
