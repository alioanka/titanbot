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
        self.last_ml_confidence = None
        self.last_market_zone = None


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
            self.last_ml_confidence = confidence
            # Set market zone here
            try:
                trend = (self.data["close"].iloc[-1] - self.data["close"].iloc[-20]) / self.data["close"].iloc[-20]
                if trend > 0.015:
                    self.last_market_zone = "Bullish"
                elif trend < -0.015:
                    self.last_market_zone = "Bearish"
                else:
                    self.last_market_zone = "Sideways"
                print(f"[🌐] Market zone (ML path): {self.last_market_zone}")
            except Exception as e:
                print(f"[⚠️] ML zone detection failed: {e}")
                self.last_market_zone = "Unknown"
            
            return ml_signal

        # Step 2: Use Phase 12 ML strategy selector if available
        try:
            # Defensive patch for indicator columns (rsi, atr, etc.)
            if "rsi" not in self.data.columns or self.data["rsi"].isna().all():
                self.data["return"] = self.data["close"].pct_change()
                self.data["volatility"] = self.data["return"].rolling(10).std()
                self.data["ema_5"] = self.data["close"].ewm(span=5).mean()
                self.data["ema_13"] = self.data["close"].ewm(span=13).mean()

                delta = self.data["close"].diff()
                gain = delta.where(delta > 0, 0).rolling(14).mean()
                loss = -delta.where(delta < 0, 0).rolling(14).mean()
                rs = gain / loss
                self.data["rsi"] = 100 - (100 / (1 + rs))

                self.data["macd"] = self.data["close"].ewm(span=12).mean() - self.data["close"].ewm(span=26).mean()
                self.data["macd_signal"] = self.data["macd"].ewm(span=9).mean()
                self.data["macd_hist"] = self.data["macd"] - self.data["macd_signal"]

                tr1 = self.data["high"] - self.data["low"]
                tr2 = abs(self.data["high"] - self.data["close"].shift())
                tr3 = abs(self.data["low"] - self.data["close"].shift())
                tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
                self.data["atr"] = tr.rolling(14).mean()

                self.data["volume_delta"] = self.data["volume"] * self.data["close"].diff()

            # Phase 13: Determine market context zone (Bullish, Bearish, Sideways)
            zone = "Sideways"
            try:
                trend = (self.data["close"].iloc[-1] - self.data["close"].iloc[-20]) / self.data["close"].iloc[-20]
                if trend > 0.015:
                    zone = "Bullish"
                elif trend < -0.015:
                    zone = "Bearish"
                print(f"[🌐] Market zone: {zone}")
                self.last_market_zone = zone  # ✅ Phase 14 support
            except Exception as e:
                print(f"[⚠️] Trend zone detection failed: {e}")
                self.last_market_zone = None

            # Load Phase 12 ML model
            from ml.selector_predictor import StrategySelector
            selector = StrategySelector(
                model_path="ml/model_strategy_selector.txt",
                encoder_path="ml/strategy_encoder.pkl"
            )

            # Defensive check — patch missing raw OHLCV columns
            ohlc_keys = ["open", "high", "low", "close", "volume"]
            if not all(k in self.data.columns for k in ohlc_keys):
                try:
                    from exchange.binance import BinanceFuturesClient
                    client = BinanceFuturesClient()
                    klines = client.fetch_ohlcv(self.symbol, self.timeframe, limit=20)
                    ohlcv_df = pd.DataFrame(klines, columns=["timestamp", "open", "high", "low", "close", "volume"])
                    for col in ohlc_keys:
                        self.data[col] = ohlcv_df[col].astype(float)
                except Exception as err:
                    raise ValueError(f"Missing required indicators in data: {self.data.columns.tolist()}")

            rows = []
            for s in self.strategies:
                row = {
                    "rsi": self.data["rsi"].iloc[-1],
                    "atr": self.data["atr"].iloc[-1],
                    "ma_trend": (self.data["close"].iloc[-1] - self.data["close"].iloc[-10]) / self.data["close"].iloc[-10],
                    "volume_ratio": self.data["volume"].iloc[-1] / self.data["volume"].rolling(10).mean().iloc[-1],
                    "body_ratio": abs(self.data["close"].iloc[-1] - self.data["open"].iloc[-1]) / (self.data["high"].iloc[-1] - self.data["low"].iloc[-1] + 1e-9),
                    "strategy": s.name(),
                    "zone": zone  # ⬅️ NEW FEATURE for Phase 13
                }
                rows.append(row)

            df = pd.DataFrame(rows)

            import joblib
            encoder = joblib.load("ml/strategy_encoder.pkl")
            df["strategy_encoded"] = encoder.transform(df["strategy"])

            best_strategy_name, prob = selector.predict_best_strategy(df)
            best_strategy = next((s for s in self.strategies if s.name() == best_strategy_name), None)
            if best_strategy:
                signal = best_strategy.generate_signal()
                print(f"[🤖] Selector picked: {best_strategy.name()} → Signal: {signal} (Prob: {prob:.2f})")
                self.last_ml_confidence = self.last_ml_confidence if hasattr(self, 'last_ml_confidence') else None
                self.last_market_zone = self.last_market_zone if hasattr(self, 'last_market_zone') else "Unknown"
                print(f"[PHASE 14 DEBUG] Final strategy signal: {signal}")
                print(f"[PHASE 14 DEBUG] Last ML confidence set to: {self.last_ml_confidence}")
                print(f"[PHASE 14 DEBUG] Last market zone set to: {self.last_market_zone}")
             
                return signal
        except Exception as e:
            print(f"[⚠️] Phase 12/13 strategy selector failed: {e}")

        # Step 3: Fallback to best performing strategy
        best_strategy = self._select_best_strategy()
        if best_strategy:
            signal = best_strategy.generate_signal()
            print(f"↪️ {best_strategy.name()} → Signal: {signal}")
            self.last_ml_confidence = self.last_ml_confidence if hasattr(self, 'last_ml_confidence') else None
            self.last_market_zone = self.last_market_zone if hasattr(self, 'last_market_zone') else "Unknown"
            print(f"[PHASE 14 DEBUG] Final strategy signal: {signal}")
            print(f"[PHASE 14 DEBUG] Last ML confidence set to: {self.last_ml_confidence}")
            print(f"[PHASE 14 DEBUG] Last market zone set to: {self.last_market_zone}")
                
            return signal
        else:
            return "HOLD"
        
        print(f"[PHASE 14 DEBUG] Final strategy signal: {signal}")
        print(f"[PHASE 14 DEBUG] Last ML confidence set to: {self.last_ml_confidence}")
        print(f"[PHASE 14 DEBUG] Last market zone set to: {self.last_market_zone}")





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
