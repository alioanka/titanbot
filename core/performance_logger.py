# core/performance_logger.py

import json
import os
from datetime import datetime

LOG_FILE = "strategy_performance.json"

def log_strategy_result(strategy_name, result, pnl, timestamp=None):
    if timestamp is None:
        timestamp = datetime.utcnow().isoformat()

    entry = {
        "timestamp": timestamp,
        "strategy": strategy_name,
        "result": result,  # "TP", "SL", "EMERGENCY", "CLOSE"
        "pnl": round(pnl, 2)
    }

    logs = []
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r") as f:
            logs = json.load(f)

    logs.append(entry)

    with open(LOG_FILE, "w") as f:
        json.dump(logs[-200:], f, indent=2)  # keep last 200 entries
