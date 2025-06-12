# core/strategy_rating.py

import json
from collections import defaultdict
from tabulate import tabulate

LOG_FILE = "strategy_performance.json"

def analyze_strategy_performance():
    try:
        with open(LOG_FILE, "r") as f:
            logs = json.load(f)
    except Exception as e:
        print(f"[⚠️] Could not read {LOG_FILE}: {e}")
        return

    stats = defaultdict(lambda: {"TP_OR_CLOSE": 0, "EMERGENCY": 0, "total": 0, "pnl": 0.0})

    for entry in logs:
        name = entry["strategy"]
        result = entry["result"]
        pnl = float(entry.get("pnl", 0))
        stats[name]["total"] += 1
        stats[name][result] += 1
        stats[name]["pnl"] += pnl

    table = []
    for strategy, data in stats.items():
        total = data["total"]
        win_rate = 100 * data["TP_OR_CLOSE"] / total if total else 0
        avg_pnl = data["pnl"] / total if total else 0
        table.append([
            strategy,
            data["TP_OR_CLOSE"],
            data["EMERGENCY"],
            total,
            f"{win_rate:.1f}%",
            f"{avg_pnl:.2f} USDT"
        ])

    headers = ["Strategy", "Wins (TP)", "Losses (Emergency)", "Total Trades", "Win Rate", "Avg PnL"]
    print("\n📊 Strategy Performance Leaderboard:\n")
    print(tabulate(sorted(table, key=lambda x: float(x[-1].split()[0]), reverse=True), headers=headers, tablefmt="fancy_grid"))

if __name__ == "__main__":
    analyze_strategy_performance()