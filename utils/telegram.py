# utils/telegram.py

import requests
import json
import time
import threading
import os
from config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID

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

def poll_telegram():
    print("[🔄] Telegram polling started...")
    last_update = get_last_update_id()
    while True:
        try:
            res = requests.get(f"{BASE_URL}/getUpdates", params={"offset": last_update + 1})
            updates = res.json().get("result", [])
            for update in updates:
                last_update = update["update_id"]
                message = update.get("message", {}).get("text", "")
                if message.strip() == "/rating":
                    from core.strategy_rating import summarize, load_strategy_logs
                    stats = summarize(load_strategy_logs())
                    if stats:
                        msg = "📊 Strategy Leaderboard\n\n"
                        for s, data in stats.items():
                            win_rate = (data['tp'] / data['total']) * 100 if data['total'] else 0
                            avg_pnl = data['pnl'] / data['total'] if data['total'] else 0
                            msg += f"📌 <b>{s}</b>\n✔️ TP: {data['tp']}  ❌ SL: {data['sl']}  ⚖️ {win_rate:.1f}%  💰 {avg_pnl:.2f} USDT\n\n"
                        send_telegram(msg)
                        send_photo("leaderboard.png", caption="📈 Leaderboard Chart")
                    else:
                        send_telegram("No strategy data yet.")

                elif message.strip().lower() == "/status":
                    from core.state_tracker import load_position_state
                    from core.strategy_engine import StrategyEngine
                    from ml.predictor import PredictMarketDirection
                    import pandas as pd
                    import os

                    try:
                        pos = load_position_state()
                        if not pos:
                            send_telegram("🟢 No open position.")
                        else:
                            df = pd.read_csv("data/BTCUSDT_15m.csv")  # or wherever your main dataset is
                            predictor = PredictMarketDirection()
                            strategy = pos.get("strategy", "Unknown")
                            signal = pos.get("side", "?").upper()
                            ml = predictor.predict(df)

                            entry = float(pos.get("entry", 0))
                            last_price = float(df["close"].iloc[-1])
                            side = signal
                            qty = float(pos.get("qty", 0))
                            leverage = int(pos.get("leverage", 0))
                            pnl = (last_price - entry) * qty if side == "LONG" else (entry - last_price) * qty
                            pnl_pct = (pnl / (entry * qty)) * 100 if entry and qty else 0

                            msg = (
                                f"📟 <b>TitanBot Status</b>\n\n"
                                f"🪙 <b>Symbol:</b> BTCUSDT\n"
                                f"📊 <b>Strategy:</b> {strategy}\n"
                                f"💡 <b>Signal:</b> {side}\n"
                                f"🧠 <b>ML Prediction:</b> {ml}\n"
                                f"📈 <b>Entry Price:</b> {entry:.2f}\n"
                                f"📉 <b>Current PnL:</b> {pnl:+.2f} USDT ({pnl_pct:+.2f}%)\n"
                                f"📌 <b>Leverage:</b> {leverage}x | <b>Size:</b> {qty:.3f} BTC"
                            )
                            send_telegram(msg)
                    except Exception as e:
                        send_telegram(f"⚠️ Failed to fetch status: {str(e)}")


            set_last_update_id(last_update)
        except Exception as e:
            print(f"[⚠️] Telegram polling error: {e}")
        time.sleep(5)
