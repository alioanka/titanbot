# core/strategy_engine.py

import importlib
import os
import pandas as pd
import json
from collections import defaultdict
from strategies.base import BaseStrategy
from ml.predictor import PredictMarketDirection

STRATEGY_FOLDER = "strategies"

class StrategyEngine:
    def __init__(self, symbol, timeframe, data: pd.DataFrame):
        self.symbol = symbol
        self.timeframe = timeframe
        self.data = data
        self.ml_predictor = PredictMarketDirection()
        self.strategies = self._load_strategies()  # ✅ Add this line

    def _load_strategies(self):
        strategies = []
        for filename in os.listdir(STRATEGY_FOLDER):
            if filename.endswith(".py") and filename not in ("__init__.py", "base.py", "ml_predictive.py"):
                module_name = f"{STRATEGY_FOLDER}.{filename[:-3]}"
                module = importlib.import_module(module_name)
                for attr in dir(module):
                    cls = getattr(module, attr)
                    if isinstance(cls, type) and issubclass(cls, BaseStrategy) and cls is not BaseStrategy:
                        strategies.append(cls(self.symbol, self.timeframe, self.data))
        return strategies

    def select_strategy_and_generate_signal(self):
        best_strategy = self._select_best_strategy()
        signal = best_strategy.generate_signal()
        score = self._score_strategy(signal, self.ml_predictor.predict(self.data))
        print(f"↪️ {best_strategy.name()} → Signal: {signal} → Score: {score}")
        return signal


    def _select_best_strategy(self):
        scores = self._load_strategy_scores()

        # Sort all loaded strategy instances by performance score (fallback to 0)
        sorted_strategies = sorted(
            self.strategies,
            key=lambda s: scores.get(s.name(), 0),
            reverse=True
        )

        return sorted_strategies[0] if sorted_strategies else self.strategies[0]

    def _load_strategy_scores(self):
        try:
            with open("strategy_performance.json", "r") as f:
                logs = json.load(f)
        except:
            return {}

        perf = defaultdict(lambda: {"tp": 0, "emergency": 0, "total": 0, "pnl": 0.0})
        for entry in logs:
            name = entry["strategy"]
            result = entry["result"]
            pnl = float(entry.get("pnl", 0))

            perf[name]["total"] += 1
            perf[name]["pnl"] += pnl
            if result == "TP_OR_CLOSE":
                perf[name]["tp"] += 1
            elif result == "EMERGENCY":
                perf[name]["emergency"] += 1

        # Score = win rate * avg pnl
        scores = {}
        for strategy, stats in perf.items():
            if stats["total"] >= 0:  # MAKE IT 3 LATERavoid low-sample noise
                win_rate = stats["tp"] / stats["total"]
                avg_pnl = stats["pnl"] / stats["total"]
                scores[strategy] = win_rate * avg_pnl

        return scores


    def _score_strategy(self, signal, predictions):
        """
        Basic logic:
        - If strategy signal matches predicted move → high score
        - Else → penalize
        """
        expected = predictions["direction"]
        if signal == "LONG" and expected == "UP":
            return 10
        elif signal == "SHORT" and expected == "DOWN":
            return 10
        elif signal == "HOLD" and expected == "NEUTRAL":
            return 8
        else:
            return -1
