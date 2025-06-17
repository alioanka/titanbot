# core/risk_manager.py

import pandas as pd
import numpy as np
from config import TRAILING_STOP
from core.state_tracker import StateTracker
from exchange.binance import BinanceFuturesClient
from utils.telegram import send_telegram

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


        if atr is None or np.isnan(atr) or atr == 0:
            print(f"[⚠️] Invalid ATR ({atr}). Using fallback SL/TP percentages.")
            sl_pct = RiskManager.FALLBACK_SL_PCT
            tp_pct = RiskManager.FALLBACK_TP_PCT
            sl_price = close_price * (1 - sl_pct) if signal == "LONG" else close_price * (1 + sl_pct)
            tp_price = close_price * (1 + tp_pct) if signal == "LONG" else close_price * (1 - tp_pct)
        else:
            sl_price = close_price - atr * sl_mult if signal == "LONG" else close_price + atr * sl_mult
            tp_price = close_price + atr * tp_mult if signal == "LONG" else close_price - atr * tp_mult

        stop_loss_distance = abs(close_price - sl_price)

        if stop_loss_distance == 0:
            print(f"[❌] SL distance is zero! Possible bug. SL = {sl_price}, Close = {close_price}, ATR = {atr}, SL Mult = {sl_mult}")
            print("[⚠️] Using fallback SL/TP values...")
            sl_pct = RiskManager.FALLBACK_SL_PCT
            tp_pct = RiskManager.FALLBACK_TP_PCT
            sl_price = close_price * (1 - sl_pct) if signal == "LONG" else close_price * (1 + sl_pct)
            tp_price = close_price * (1 + tp_pct) if signal == "LONG" else close_price * (1 - tp_pct)
            stop_loss_distance = abs(close_price - sl_price)

        risk_amount = balance * RiskManager.MAX_RISK_PCT
        qty = risk_amount / stop_loss_distance

        if not np.isfinite(qty) or qty == 0:
            print(f"[❌] Invalid qty calculated: {qty}. Skipping this trade.")
            return 0, 1, sl_price, tp_price

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
    


def trailing_stop_check(client, symbol, position, entry_price, signal, sl_price, tp_price, trailing_config):
    current_price = client.get_current_price(symbol)
    if current_price is None:
        print(f"[⚠️] Skipping trailing check — current price not available for {symbol}")
        return

    activation_pct = trailing_config["activation_pct"]
    trail_pct = trailing_config["trail_pct"]
    position_side = position.get("positionSide", "BOTH")

    activation_price = None
    new_sl = None

    print(f"\n[🔍] Trailing SL Check for {symbol}")
    print(f"     ➤ Signal: {signal}")
    print(f"     ➤ Entry Price: {entry_price:.2f}")
    print(f"     ➤ Current Price: {current_price:.2f}")
    print(f"     ➤ TP: {tp_price:.2f} | SL: {sl_price:.2f}")
    print(f"     ➤ Trailing Config → Activation: {activation_pct*100:.2f}%, Trail: {trail_pct*100:.2f}%")

    if signal == "LONG":
        activation_price = entry_price * (1 + activation_pct)
        new_sl = current_price * (1 - trail_pct)

        if activation_price > tp_price:
            print(f"[⛔] Skipping trailing — activation ({activation_price:.2f}) > TP ({tp_price:.2f})")
            return

        print(f"     ➤ Activation Price (LONG): {activation_price:.2f} | New SL: {new_sl:.2f}")

        if current_price >= activation_price:
            if new_sl > sl_price:
                print(f"[🚨] Triggering Trailing SL (LONG) — New SL: {new_sl:.2f} > Old SL: {sl_price:.2f}")
                try:
                    client.cancel_stop_loss_order(symbol)
                    client.set_stop_loss(symbol, new_sl, position_side=position_side)
                    send_telegram(
                        f"📉 <b>Trailing SL Updated (LONG)</b>\n"
                        f"Symbol: {symbol}\nNew SL: {new_sl:.2f}\nEntry: {entry_price:.2f}\nPrice: {current_price:.2f}"
                    )
                except Exception as e:
                    print(f"[⚠️] Failed to update trailing SL: {e}")
            else:
                print(f"[ℹ️] Skipped update — New SL not better than current.")
        else:
            print(f"[🕒] Waiting — current price below activation ({activation_price:.2f})")

    elif signal == "SHORT":
        activation_price = entry_price * (1 - activation_pct)
        new_sl = current_price * (1 + trail_pct)

        if activation_price < tp_price:
            print(f"[⛔] Skipping trailing — activation ({activation_price:.2f}) < TP ({tp_price:.2f})")
            return

        print(f"     ➤ Activation Price (SHORT): {activation_price:.2f} | New SL: {new_sl:.2f}")

        if current_price <= activation_price:
            if new_sl < sl_price:
                print(f"[🚨] Triggering Trailing SL (SHORT) — New SL: {new_sl:.2f} < Old SL: {sl_price:.2f}")
                try:
                    client.cancel_stop_loss_order(symbol)
                    client.set_stop_loss(symbol, new_sl, position_side=position_side)
                    send_telegram(
                        f"📉 <b>Trailing SL Updated (SHORT)</b>\n"
                        f"Symbol: {symbol}\nNew SL: {new_sl:.2f}\nEntry: {entry_price:.2f}\nPrice: {current_price:.2f}"
                    )
                except Exception as e:
                    print(f"[⚠️] Failed to update trailing SL: {e}")
            else:
                print(f"[ℹ️] Skipped update — New SL not better than current.")
        else:
            print(f"[🕒] Waiting — current price above activation ({activation_price:.2f})")

    else:
        print(f"[⚠️] Unknown signal type: {signal}")
