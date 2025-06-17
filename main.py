# main.py

import os
import time
import traceback
import datetime
from exchange.binance import BinanceFuturesClient
import requests  # ✅ FIXED
from config import BASE_URL  # ✅ FIXED
from core.strategy_engine import StrategyEngine
from core.risk_manager import RiskManager
from core.state_tracker import StateTracker
from emergency.kill_switch import emergency_exit
from ml.trainer import train_model
from utils.telegram import send_telegram
from utils.telegram import poll_telegram
import threading

MODEL_PATH = "ml/model_lightgbm.txt"
RETRAIN_INTERVAL_HOURS = 24

SYMBOL = "BTCUSDT"
TIMEFRAME = "15m"

last_trade_close_time = 0
last_trade_result = None
cooldown_tp = 3 * 60   # 3 minutes
cooldown_sl = 6 * 60   # 6 minutes

# NEW: Adaptive SL/TP multipliers
zone_sl_tp_multipliers = {
    "Bullish": (0.9, 1.2),     # (SL, TP)
    "Bearish": (1.1, 1.1),
    "Sideways": (0.8, 0.8)
}
confidence_sl_tp_multipliers = [
    (0.99, (1.0, 1.0)),
    (0.95, (0.9, 0.9)),
    (0.90, (0.85, 0.85)),
    (0.80, (0.75, 0.75)),
]


def auto_retrain_loop(symbol, interval):
    while True:
        if os.path.exists(MODEL_PATH):
            mod_time = os.path.getmtime(MODEL_PATH)
            age_hours = (time.time() - mod_time) / 3600
            if age_hours > RETRAIN_INTERVAL_HOURS:
                print(f"[🔄] Last trained {age_hours:.2f}h ago. Retraining...")
                train_model(symbol, interval)
            else:
                print(f"[🧠] Model is fresh ({age_hours:.2f}h ago). Skipping retrain.")
        else:
            print("[⚠️] No model found. Training from scratch...")
            train_model(symbol, interval)

        time.sleep(3600)  # Check once every hour

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
                global last_trade_close_time, last_trade_result
                last_trade_close_time = time.time()
                last_trade_result = "SL" if result_type == "STOP LOSS" else "TP"

                send_telegram(f"✅ <b>Trade Closed ({result_type})</b>\nSymbol: {SYMBOL}")
#                log_strategy_result(strategy_name="Unknown", result="TP_OR_CLOSE", pnl=round(pnl, 2))
                log_strategy_result(
                    strategy_name=previous_state.get("strategy", "Unknown"),
                    result="TP_OR_CLOSE",
                    pnl=round(pnl, 2)
                )
                StateTracker.clear_state()

            # ✅ Place new order only if no position exists
            if current_position:
                print("[⏳] Open position already exists, skipping new order.")

                # ✅ Phase 15: Trailing Stop Check for open position
                try:
                    from core.risk_manager import trailing_stop_check

                    # Extract required values from saved state
                    previous_state = StateTracker.load_position_state()
                    if previous_state:
                        entry_price = float(previous_state.get("entry"))
                        sl_price = float(previous_state.get("sl"))
                        tp_price = float(previous_state.get("tp"))
                        final_signal = previous_state.get("side")

                        TRAILING_STOP = {
                            "activation_pct": 0.005,
                            "trail_pct": 0.003
                        }

                        trailing_stop_check(
                            client=client,
                            symbol=SYMBOL,
                            position=current_position,
                            entry_price=entry_price,
                            signal=final_signal,
                            sl_price=sl_price,
                            tp_price=tp_price,
                            trailing_config=TRAILING_STOP
                        )

                except Exception as e:
                    print(f"[⚠️] Error in Trailing SL check: {e}")


            else:
                #signal = "LONG"  # or engine.select_strategy_and_generate_signal()
                signal = engine.select_strategy_and_generate_signal()


                if last_trade_result == "TP" and (time.time() - last_trade_close_time) < cooldown_tp:
                    print("⏳ TP cooldown active. Skipping entry.")
                    continue

                if last_trade_result == "SL" and (time.time() - last_trade_close_time) < cooldown_sl:
                    print("⏳ SL cooldown active. Skipping entry.")
                    continue


                if signal in ["LONG", "SHORT"]:
                    # 🧠 Get ML confidence and zone from engine (if available)
                    ml_conf = getattr(engine, "last_ml_confidence", None)
                    zone = getattr(engine, "last_market_zone", None)

                    # ✅ Log values to verify
                    print(f"[DEBUG] Using ML Confidence: {ml_conf}")
                    print(f"[DEBUG] Using Market Zone: {zone}")

                    # Ensure defaults are set if missing
                    conf_for_risk = ml_conf if ml_conf is not None else 1.0
                    zone_for_risk = zone if zone is not None else "Unknown"

                    qty, leverage, sl, tp = RiskManager.calculate_position(
                        signal, df, balance=1000, zone=zone_for_risk, confidence=conf_for_risk
                    )
                    # ✅ Final confirmation logging

                    print(f"[✅] Final SL/TP values after Phase 14 logic:")
                    print(f"     ➤ Signal: {signal}")
                    print(f"     ➤ ML Confidence: {ml_conf if ml_conf is not None else 'N/A'}")
                    print(f"     ➤ Market Zone: {zone if zone is not None else 'N/A'}")
                    print(f"     ➤ SL: {sl:.2f} | TP: {tp:.2f}")




                    client.place_order(SYMBOL, signal, qty, sl, tp, leverage)
                    StateTracker.save_position_state({
                        "symbol": SYMBOL,
                        "side": signal,
                        "qty": qty,
                        "sl": sl,
                        "tp": tp,
                        "leverage": leverage,
                        "entry": df["close"].iloc[-1],  # or use live entry price
                        "strategy": engine._select_best_strategy().name()  # ✅ add this line
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

def refresh_chart_every_12h():
    import subprocess
    while True:
        try:
            subprocess.run(["python3", "scripts/strategy_chart.py"])
        except:
            print("[⚠️] Failed to update leaderboard chart.")
        time.sleep(43200)  # 12h



if __name__ == "__main__":

    # Start background threads BEFORE the bot loop
    threading.Thread(target=poll_telegram, daemon=True).start()
    threading.Thread(target=auto_retrain_loop, args=(SYMBOL, TIMEFRAME), daemon=True).start()
    threading.Thread(target=refresh_chart_every_12h, daemon=True).start()
    run_bot()
