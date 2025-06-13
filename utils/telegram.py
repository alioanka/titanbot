# utils/telegram.py

import requests
import json
import time
import threading
import os
import datetime
import pandas as pd
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from exchange.binance import BinanceFuturesClient
from core.state_tracker import StateTracker
from ml.predictor import PredictMarketDirection

BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
LAST_UPDATE_FILE = "telegram_last_update.json"

def send_telegram(message):
    url = f"{BASE_URL}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    try:
        res = requests.post(url, data=payload)
        if res.status_code != 200:
            print(f"[⚠️] Telegram error: {res.text}")
    except Exception as e:
        print(f"[⚠️] Telegram exception: {e}")

def send_photo(file_path, caption=None):
    url = f"{BASE_URL}/sendPhoto"
    try:
        with open(file_path, "rb") as photo:
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": caption or "Strategy Chart"
            }
            files = {"photo": photo}
            res = requests.post(url, data=payload, files=files)
            if res.status_code != 200:
                print(f"[⚠️] Telegram photo error: {res.text}")
    except Exception as e:
        print(f"[⚠️] Telegram photo exception: {e}")

def get_last_update_id():
    if os.path.exists(LAST_UPDATE_FILE):
        with open(LAST_UPDATE_FILE, "r") as f:
            data = json.load(f)
            return data.get("update_id", 0)
    return 0

def set_last_update_id(update_id):
    with open(LAST_UPDATE_FILE, "w") as f:
        json.dump({"update_id": update_id}, f)

def handle_status():
    try:
        pos = StateTracker.load_position_state()
        if not pos:
            send_telegram("🟢 No open position.")
            return

        symbol = "BTCUSDT"
        side = pos.get("side", "?").upper()
        strategy = pos.get("strategy", "Unknown")
        entry = float(pos.get("entry", 0))
        qty = float(pos.get("qty", 0))
        leverage = int(pos.get("leverage", 0))
        timestamp = pos.get("timestamp", None)

        client = BinanceFuturesClient()
        price = float(client.get_ticker(symbol)["price"])

        df = client.get_klines(symbol, "15m", limit=150)
        df = pd.DataFrame(df, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_asset_volume", "number_of_trades",
            "taker_buy_base_asset_volume", "taker_buy_quote_asset_volume", "ignore"
        ])
        df["close"] = df["close"].astype(float)

        predictor = PredictMarketDirection()
        ml = predictor.predict(df)
        proba = predictor.predict_proba(df)
        confidence = max(proba) * 100 if proba is not None else 0

        pnl = (price - entry) * qty if side == "LONG" else (entry - price) * qty
        pnl_pct = (pnl / (entry * qty)) * 100 if entry and qty else 0

        if timestamp:
            last_signal_time = datetime.datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
        else:
            last_signal_time = "Unknown"

        model_path = "ml/model_lightgbm.txt"
        retrain_hours = 24
        if os.path.exists(model_path):
            mod_time = os.path.getmtime(model_path)
            next_retrain_ts = mod_time + (retrain_hours * 3600)
            next_retrain = datetime.datetime.fromtimestamp(next_retrain_ts).strftime("%Y-%m-%d %H:%M:%S")
        else:
            next_retrain = "Unknown"

        msg = (
            f"📟 <b>TitanBot Status</b>\n\n"
            f"🪙 <b>Symbol:</b> {symbol}\n"
            f"📊 <b>Strategy:</b> {strategy}\n"
            f"💡 <b>Signal:</b> {side}\n"
            f"🧠 <b>ML Prediction:</b> {ml} ({confidence:.1f}%)\n"
            f"📈 <b>Entry Price:</b> {entry:.2f}\n"
            f"📉 <b>Current PnL:</b> {pnl:+.2f} USDT ({pnl_pct:+.2f}%)\n"
            f"📌 <b>Leverage:</b> {leverage}x | <b>Size:</b> {qty:.3f} BTC\n"
            f"🔄 <b>Last Signal:</b> {last_signal_time}\n"
            f"🔁 <b>Next Retrain:</b> {next_retrain}"
        )
        send_telegram(msg)
    except Exception as e:
        send_telegram(f"⚠️ Failed to fetch status: {str(e)}")

def handle_cancel():
    try:
        client = BinanceFuturesClient()
        client.cancel_all_orders("BTCUSDT")
        StateTracker.clear_state()
        send_telegram("🛑 All orders and position state cleared.")
    except Exception as e:
        send_telegram(f"⚠️ Failed to cancel orders: {str(e)}")

def handle_summary():
    try:
        from core.strategy_rating import summarize, load_strategy_logs
        stats = summarize(load_strategy_logs())
        client = BinanceFuturesClient()
        balance = client.get_balance()

        today = datetime.datetime.now().strftime("%Y-%m-%d")
        week = datetime.datetime.now().strftime("%Y-W%U")
        total_pnl_today = 0
        total_pnl_week = 0

        for s, data in stats.items():
            for log in data.get("logs", []):
                ts = log["timestamp"]
                dt = datetime.datetime.fromtimestamp(ts)
                if dt.strftime("%Y-%m-%d") == today:
                    total_pnl_today += log["pnl"]
                if dt.strftime("%Y-W%U") == week:
                    total_pnl_week += log["pnl"]

        msg = (
            f"🗓️ <b>Daily Summary</b>\n\n"
            f"📅 Today: {today}\n"
            f"💰 Total PnL Today: {total_pnl_today:.2f} USDT\n"
            f"📅 Week: {week}\n"
            f"💰 Total PnL This Week: {total_pnl_week:.2f} USDT\n"
            f"💼 Current Balance: {balance:.2f} USDT"
        )
        send_telegram(msg)
    except Exception as e:
        send_telegram(f"⚠️ Failed to generate summary: {str(e)}")

def auto_daily_journal():
    while True:
        try:
            handle_summary()
        except Exception as e:
            print(f"[⚠️] Auto journal error: {e}")
        time.sleep(86400)  # once per 24h

def poll_telegram():
    print("[🔄] Telegram polling started...")
    last_update = get_last_update_id()
    while True:
        try:
            res = requests.get(f"{BASE_URL}/getUpdates", params={"offset": last_update + 1})
            updates = res.json().get("result", [])
            for update in updates:
                last_update = update["update_id"]
                message = update.get("message", {}).get("text", "").strip().lower()

                if message == "/rating":
                    from core.strategy_rating import summarize, load_strategy_logs
                    stats = summarize(load_strategy_logs())
                    if stats:
                        msg = "📊 Strategy Leaderboard\n\n"
                        for s, data in stats.items():
                            win_rate = (data['tp'] / data['total']) * 100 if data['total'] else 0
                            avg_pnl = data['pnl'] / data['total'] if data['total'] else 0
                            msg += f"📌 <b>{s}</b>\n✔️ TP: {data['tp']}  ❌ SL: {data['sl']}  ⚖️ {win_rate:.1f}%  💰 {avg_pnl:.2f} USDT\n\n"
                        send_telegram(msg)
                        send_photo("leaderboard.png", caption="🖼 📈 Leaderboard Chart")
                    else:
                        send_telegram("No strategy data yet.")

                elif message == "/status":
                    handle_status()

                elif message == "/cancel":
                    handle_cancel()

                elif message == "/summary":
                    handle_summary()

            set_last_update_id(last_update)
        except Exception as e:
            print(f"[⚠️] Telegram polling error: {e}")
        time.sleep(5)

# Start auto daily journaling in background
threading.Thread(target=auto_daily_journal, daemon=True).start()
