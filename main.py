# main.py

import os
import time
import traceback
from exchange.binance import BinanceFuturesClient
import requests  # ✅ FIXED
from config import BASE_URL  # ✅ FIXED
from core.strategy_engine import StrategyEngine
from core.risk_manager import RiskManager
from core.state_tracker import StateTracker
from emergency.kill_switch import emergency_exit
from ml.trainer import train_model
from utils.telegram import send_telegram

MODEL_PATH = "ml/model_lightgbm.txt"

SYMBOL = "BTCUSDT"
TIMEFRAME = "15m"

def auto_retrain_model(symbol="BTCUSDT", interval="5m"):
    retrain_interval_hours = 24
    now = time.time()

    if not os.path.exists(MODEL_PATH):
        print("[⚠️] No existing model found. Training from scratch.")
        train_model(symbol, interval)
        return

    last_modified = os.path.getmtime(MODEL_PATH)
    hours_since_last_train = (now - last_modified) / 3600

    if hours_since_last_train > retrain_interval_hours:
        print(f"[🔄] Last trained {hours_since_last_train:.2f}h ago. Retraining...")
        train_model(symbol, interval)
    else:
        print(f"[🧠] Model is fresh ({hours_since_last_train:.2f}h ago). Skipping retrain.")

#adding run_bot
#   engine = StrategyEngine(symbol=SYMBOL, timeframe=TIMEFRAME, data=df)
#   signal = engine.select_strategy_and_generate_signal()

def run_bot():
    print("🚀 TitanBot AI starting...")

    auto_retrain_model(symbol=SYMBOL, interval=TIMEFRAME)
    client = BinanceFuturesClient()
    

    while True:
        try:
            df = client.get_klines(SYMBOL, TIMEFRAME)
            engine = StrategyEngine(symbol=SYMBOL, timeframe=TIMEFRAME, data=df)

            # ✅ LOAD previous position (to compare against current)
            previous_state = StateTracker.load_position_state()
            current_position = StateTracker.get_open_position(SYMBOL)
            print("[DEBUG] Position info:", current_position)

            # ✅ If previous existed and current is gone = trade closed
            if previous_state and not current_position:
                from core.performance_logger import log_strategy_result
                # NEW: Cancel all open orders for this symbol
                client.cancel_all_orders(SYMBOL)

                # Get current price as exit reference
                try:
                    price_data = requests.get(f"{BASE_URL}/fapi/v1/ticker/price?symbol={SYMBOL}").json()
                    current_price = float(price_data["price"])
                except:
                    current_price = None

                pnl = "Unknown"
                try:
                    entry = float(previous_state["entry"])
                    size = float(previous_state["qty"])
                    side = previous_state["side"]

                    if current_price:
                        pnl = (current_price - entry) * size if side == "LONG" else (entry - current_price) * size
                except:
                    pass

                # If PnL is negative, assume SL
                result_type = "STOP LOSS" if pnl != "Unknown" and pnl < 0 else "TP or Manual"
                send_telegram(f"✅ <b>Trade Closed ({result_type})</b>\nSymbol: {SYMBOL}")
                log_strategy_result(strategy_name="Unknown", result="TP_OR_CLOSE", pnl=round(pnl, 2))
                StateTracker.clear_state()

            # ✅ Place new order only if no position exists
            if current_position:
                print("[⏳] Open position already exists, skipping new order.")
            else:
                #signal = "LONG"  # or engine.select_strategy_and_generate_signal()
                signal = engine.select_strategy_and_generate_signal()
                if signal in ["LONG", "SHORT"]:
                    qty, leverage, sl, tp = RiskManager.calculate_position(signal, df, balance=1000)
                    client.place_order(SYMBOL, signal, qty, sl, tp, leverage)
                    StateTracker.save_position_state({
                        "symbol": SYMBOL,
                        "side": signal,
                        "qty": qty,
                        "sl": sl,
                        "tp": tp,
                        "leverage": leverage,
                        "entry": df["close"].iloc[-1]  # or use live entry price
                    })
                    send_telegram(f"🚀 <b>New {signal} Position Opened</b>\n"
                                  f"Symbol: {SYMBOL}\nQty: {qty:.4f} @ Leverage {leverage}x\n"
                                  f"SL: {sl:.2f} | TP: {tp:.2f}")

            # ✅ Emergency SL kill switch
            if StateTracker.detect_unusual_drawdown(symbol=SYMBOL, max_loss_pct=0.03):
                emergency_exit(client)
                send_telegram(f"🛑 <b>Emergency Exit Triggered</b>\nSymbol: {SYMBOL}\nReason: Max drawdown exceeded.")

        except Exception as e:
            print("[❌] Critical error in bot loop:")
            traceback.print_exc()
            send_telegram(f"❌ <b>Error in TitanBot</b>\n{str(e)}")

        print("[⏳] Sleeping for 60 seconds...\n")
        time.sleep(60)


if __name__ == "__main__":
    run_bot()
