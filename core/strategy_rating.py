import json
from collections import defaultdict
from tabulate import tabulate

def load_strategy_logs(path="strategy_performance.json"):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except:
        return []

def summarize(logs, ignore_unknown=True):
    stats = defaultdict(lambda: {"tp": 0, "sl": 0, "total": 0, "pnl": 0.0, "logs": []})

    for entry in logs:
        strategy = entry.get("strategy", "Unknown")
        if ignore_unknown and strategy == "Unknown":
            continue

        result = entry.get("result")
        pnl = float(entry.get("pnl", 0))

        stats[strategy]["total"] += 1
        stats[strategy]["pnl"] += pnl
        stats[strategy]["logs"].append(entry)  # ✅ Append full log entry for summary

        if result == "TP_OR_CLOSE" and pnl >= 0:
            stats[strategy]["tp"] += 1
        elif result == "EMERGENCY" or pnl < 0:
            stats[strategy]["sl"] += 1

    return stats


def show_summary(stats):
    table = []
    for strategy, data in stats.items():
        win_rate = (data["tp"] / data["total"]) * 100 if data["total"] else 0
        avg_pnl = data["pnl"] / data["total"] if data["total"] else 0
        table.append([
            strategy,
            data["tp"],
            data["sl"],
            data["total"],
            f"{win_rate:.1f}%",
            f"{avg_pnl:.2f} USDT"
        ])

    table.sort(key=lambda row: float(row[4].replace('%', '')), reverse=True)

    print("\n📊 Strategy Performance Leaderboard:\n")
    print(tabulate(
        table,
        headers=["Strategy", "Wins (TP)", "Losses (SL)", "Total Trades", "Win Rate", "Avg PnL"],
        tablefmt="fancy_grid"
    ))

if __name__ == "__main__":
    logs = load_strategy_logs()
    summary = summarize(logs)
    show_summary(summary)
