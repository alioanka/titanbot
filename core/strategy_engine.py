# core/strategy_engine.py

import importlib
import os
import pandas as pd
from strategies.base import BaseStrategy
from ml.predictor import PredictMarketDirection

STRATEGY_FOLDER = "strategies"

class StrategyEngine:
    def __init__(self, symbol, timeframe, data: pd.DataFrame):
        self.symbol = symbol
        self.timeframe = timeframe
        self.data = data
        self.ml_predictor = PredictMarketDirection()

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
        strategies = self._load_strategies()
        predictions = self.ml_predictor.predict(self.data)

        best_score = -999
        best_signal = "HOLD"
        best_strategy = "None"

        for strategy in strategies:
            try:
                signal = strategy.generate_signal()
                score = self._score_strategy(signal, predictions)
                print(f"↪️ {strategy.name()} → Signal: {signal} → Score: {score}")
                if score > best_score:
                    best_score = score
                    best_signal = signal
                    best_strategy = strategy.name()
            except Exception as e:
                print(f"[!] Error in {strategy.name()}: {e}")
                continue

        print(f"[✓] Selected Strategy: {best_strategy} → Signal: {best_signal}")
        return best_signal

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
