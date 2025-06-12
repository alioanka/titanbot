# strategies/trend_following.py

from strategies.base import BaseStrategy

class TrendFollowingStrategy(BaseStrategy):
    def generate_signal(self):
        df = self.data.copy()
        df["ema20"] = df["close"].ewm(span=20).mean()
        df["ema50"] = df["close"].ewm(span=50).mean()

        if df["ema20"].iloc[-1] > df["ema50"].iloc[-1] and df["ema20"].iloc[-2] <= df["ema50"].iloc[-2]:
            return "LONG"
        elif df["ema20"].iloc[-1] < df["ema50"].iloc[-1] and df["ema20"].iloc[-2] >= df["ema50"].iloc[-2]:
            return "SHORT"
        else:
            return "HOLD"

    def name(self):
        return "TrendFollowingStrategy"
