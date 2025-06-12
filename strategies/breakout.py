# strategies/breakout.py

from strategies.base import BaseStrategy

class BreakoutStrategy(BaseStrategy):
    def generate_signal(self):
        df = self.data.copy()
        df["high_range"] = df["high"].rolling(window=20).max()
        df["low_range"] = df["low"].rolling(window=20).min()

        last_close = df["close"].iloc[-1]
        high_range = df["high_range"].iloc[-2]  # use previous candle range
        low_range = df["low_range"].iloc[-2]

        if last_close > high_range:
            return "LONG"
        elif last_close < low_range:
            return "SHORT"
        else:
            return "HOLD"

    def name(self):
        return "BreakoutStrategy"
