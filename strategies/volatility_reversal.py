# strategies/volatility_reversal.py

from strategies.base import BaseStrategy

class VolatilityReversalStrategy(BaseStrategy):
    def generate_signal(self):
        df = self.data.copy()
        df["range"] = df["high"] - df["low"]
        df["range_std"] = df["range"].rolling(window=20).std()
        df["range_mean"] = df["range"].rolling(window=20).mean()

        last_range = df["range"].iloc[-1]
        low_vol = df["range"].iloc[-5:-1].mean() < df["range_mean"].iloc[-1] * 0.7

        if low_vol and last_range > df["range_mean"].iloc[-1] * 1.5:
            if df["close"].iloc[-1] > df["open"].iloc[-1]:
                return "LONG"
            elif df["close"].iloc[-1] < df["open"].iloc[-1]:
                return "SHORT"

        return "HOLD"

    def name(self):
        return "VolatilityReversalStrategy"
