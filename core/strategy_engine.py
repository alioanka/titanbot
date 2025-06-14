# core/strategy_engine.py

import importlib
import random
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
        # Step 1: Use ML to get directional signal and confidence
        ml_signal, confidence = self.ml_predictor.predict(self.data)
        print(f"[ML] Predicted signal: {ml_signal} with confidence {confidence:.2f}")

        if confidence >= 0.75 and ml_signal in ["LONG", "SHORT"]:
            print(f"[🧠] ML signal selected: {ml_signal}")
            return ml_signal

        # Step 2: Use Phase 12 ML strategy selector if available
        try:
            from ml.selector_predictor import StrategySelector
            selector = StrategySelector(
                model_path="ml/model_strategy_selector.txt",
                encoder_path="ml/strategy_encoder.pkl"
            )

            # Build feature snapshot for each strategy
            required = ["rsi", "atr", "close", "open", "high", "low", "volume"]
            if not all(col in self.data.columns for col in required):
                raise ValueError(f"Missing required indicators in data: {self.data.columns.tolist()}")

            rows = []
            for s in self.strategies:
                row = {
                    "rsi": self.data["rsi"].iloc[-1],
                    "atr": self.data["atr"].iloc[-1],
                    "ma_trend": (self.data["close"].iloc[-1] - self.data["close"].iloc[-10]) / self.data["close"].iloc[-10],
                    "volume_ratio": self.data["volume"].iloc[-1] / self.data["volume"].rolling(10).mean().iloc[-1],
                    "body_ratio": abs(self.data["close"].iloc[-1] - self.data["open"].iloc[-1]) / (self.data["high"].iloc[-1] - self.data["low"].iloc[-1] + 1e-9),
                    "strategy": s.name()
                }
                rows.append(row)

            df = pd.DataFrame(rows)

            # Load encoder
            import joblib
            encoder = joblib.load("ml/strategy_encoder.pkl")
            df["strategy_encoded"] = encoder.transform(df["strategy"])

            best_strategy_name, prob = selector.predict_best_strategy(df)
            best_strategy = next((s for s in self.strategies if s.name() == best_strategy_name), None)
            if best_strategy:
                signal = best_strategy.generate_signal()
                print(f"[🤖] Selector picked: {best_strategy.name()} → Signal: {signal} (Prob: {prob:.2f})")
                return signal
        except Exception as e:
            print(f"[⚠️] Phase 12 strategy selector failed: {e}")

        # Step 3: Fallback to best performing strategy
        best_strategy = self._select_best_strategy()
        if best_strategy:
            signal = best_strategy.generate_signal()
            print(f"↪️ {best_strategy.name()} → Signal: {signal}")
            return signal
        else:
            return "HOLD"



    def _select_best_strategy(self):
        scores = self._load_strategy_scores()

        # Sort all loaded strategy instances by performance score (fallback to 0)
        sorted_strategies = sorted(
            self.strategies,
            key=lambda s: scores.get(s.name(), 0),
            reverse=True
        )

#        return random.choice(self.strategies)

        if len(scores) < 10:
            print("[🧪] Strategy sample size small — using random strategy.")
            return random.choice(self.strategies)
        else:
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

        print("[DEBUG] Strategy scores:", scores) #remove later

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
