# core/risk_manager.py

import pandas as pd
import numpy as np

class RiskManager:
    MAX_RISK_PCT = 0.02   # 2% risk per trade
    DEFAULT_LEVERAGE = 10
    MAX_LEVERAGE = 20
    SL_ATR_MULTIPLIER = 0.8 #1.5
    TP_ATR_MULTIPLIER = 1.2 #2.5
    FALLBACK_SL_PCT = 0.003 #0.01
    FALLBACK_TP_PCT = 0.006 #0.02

    @staticmethod
    def calculate_position(signal: str, df: pd.DataFrame, balance: float = 1000, zone: str = None, confidence: float = 1.0):
        close_price = df["close"].iloc[-1]
        atr = RiskManager._calculate_atr(df)

        # Default multipliers
        sl_mult = RiskManager.SL_ATR_MULTIPLIER
        tp_mult = RiskManager.TP_ATR_MULTIPLIER

        # 📉 Adjust based on zone if available (Phase 13)
        if zone:
            print(f"[🌍] Adjusting SL/TP for market zone: {zone}")
            if zone == "Bullish":
                sl_mult *= 0.9
                tp_mult *= 1.2
            elif zone == "Bearish":
                sl_mult *= 1.2
                tp_mult *= 0.9
            elif zone == "Sideways":
                sl_mult *= 0.8
                tp_mult *= 0.8
            print(f"[⚙️] Zone-based multipliers applied: SL x{sl_mult:.2f}, TP x{tp_mult:.2f}")

        # 📐 Adjust further if ML confidence is weak (Phase 14)
        if confidence < 0.99:
            if confidence >= 0.95:
                sl_mult *= 0.9
                tp_mult *= 0.9
            elif confidence >= 0.90:
                sl_mult *= 0.85
                tp_mult *= 0.85
            elif confidence >= 0.80:
                sl_mult *= 0.75
                tp_mult *= 0.75
            print(f"[📐] Confidence-based multipliers applied: SL x{sl_mult:.2f}, TP x{tp_mult:.2f} for conf {confidence:.2f}")


        if atr is None or np.isnan(atr):
            sl_pct = RiskManager.FALLBACK_SL_PCT
            tp_pct = RiskManager.FALLBACK_TP_PCT
            sl_price = close_price * (1 - sl_pct) if signal == "LONG" else close_price * (1 + sl_pct)
            tp_price = close_price * (1 + tp_pct) if signal == "LONG" else close_price * (1 - tp_pct)
        else:
            sl_price = close_price - atr * sl_mult if signal == "LONG" else close_price + atr * sl_mult
            tp_price = close_price + atr * tp_mult if signal == "LONG" else close_price - atr * tp_mult

        stop_loss_distance = abs(close_price - sl_price)
        risk_amount = balance * RiskManager.MAX_RISK_PCT
        qty = risk_amount / stop_loss_distance

        # ⚙️ Leverage adjustment based on volatility
        volatility = df["close"].pct_change().rolling(10).std().iloc[-1]
        leverage = min(RiskManager.MAX_LEVERAGE, max(1, int(RiskManager.DEFAULT_LEVERAGE / (volatility * 100 + 1))))

        print(f"[💡] RiskManager decision → Qty: {qty:.4f}, Leverage: {leverage}, SL: {sl_price:.2f}, TP: {tp_price:.2f}")
        return qty, leverage, sl_price, tp_price


    @staticmethod
    def _calculate_atr(df: pd.DataFrame, period: int = 14):
        high = df["high"]
        low = df["low"]
        close = df["close"]

        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)

        atr = tr.rolling(period).mean()
        return atr.iloc[-1] if len(atr) >= period else None
