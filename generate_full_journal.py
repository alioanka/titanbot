# generate_full_journal.py

import json
import pandas as pd

# Load from full strategy performance log
with open("strategy_performance.json", "r") as f:
    full_logs = json.load(f)

# Filter logs with usable entries
valid_logs = []
for entry in full_logs:
    if all(k in entry for k in ["timestamp", "strategy", "pnl"]):
        valid_logs.append({
            "timestamp": entry["timestamp"],
            "strategy": entry["strategy"],
            "pnl": entry["pnl"]
        })

# Convert to DataFrame and save
df = pd.DataFrame(valid_logs)
df["timestamp"] = pd.to_datetime(df["timestamp"])
df = df.sort_values("timestamp")
df.to_csv("journal.csv", index=False)

print(f"✅ Generated journal.csv with {len(df)} rows.")
