import json
import matplotlib.pyplot as plt
from collections import defaultdict
import os

def load_strategy_logs(path="strategy_performance.json"):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return []

def summarize(logs, ignore_unknown=True):
    stats = defaultdict(lambda: {"tp": 0, "sl": 0, "total": 0, "pnl": 0.0})

    for entry in logs:
        strategy = entry.get("strategy", "Unknown")
        if ignore_unknown and strategy == "Unknown":
            continue

        result = entry.get("result")
        pnl = float(entry.get("pnl", 0))

        stats[strategy]["total"] += 1
        stats[strategy]["pnl"] += pnl

        if result == "TP_OR_CLOSE" and pnl >= 0:
            stats[strategy]["tp"] += 1
        elif result == "EMERGENCY" or pnl < 0:
            stats[strategy]["sl"] += 1

    return stats

def plot_leaderboard(stats):
    strategies = list(stats.keys())
    avg_pnls = [stats[s]["pnl"] / stats[s]["total"] if stats[s]["total"] else 0 for s in strategies]
    win_rates = [100 * stats[s]["tp"] / stats[s]["total"] if stats[s]["total"] else 0 for s in strategies]

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6))
    fig.suptitle("TitanBot Strategy Leaderboard", fontsize=14)

    ax1.bar(strategies, avg_pnls, color="skyblue")
    ax1.set_title("Average PnL (USDT)")
    ax1.set_ylabel("PnL")

    ax2.bar(strategies, win_rates, color="lightgreen")
    ax2.set_title("Win Rate (%)")
    ax2.set_ylabel("Percent")
    ax2.set_ylim(0, 100)

    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig("leaderboard.png")
    print("📤 leaderboard.png saved successfully!")

if __name__ == "__main__":
    logs = load_strategy_logs()
    stats = summarize(logs)
    if stats:
        plot_leaderboard(stats)
    else:
        print("No valid strategy data to plot.")
