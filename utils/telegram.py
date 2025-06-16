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
        price = client.get_ticker(symbol)


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
        print(f"[DEBUG] predict_proba returned: {proba}")

        #confidence = max(proba) * 100 if proba is not None else 0
        try:
            confidence = max(proba) * 100
        except:
            confidence = proba * 100 if isinstance(proba, (int, float)) else 0

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
                if not ts:
                    continue
                try:
                    # ✅ Handle ISO string timestamps properly
                    dt = datetime.datetime.fromisoformat(ts)
                except:
                    continue
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

def handle_weekly():
    from core.strategy_rating import summarize, load_strategy_logs
    stats = summarize(load_strategy_logs())
    week = datetime.datetime.now().strftime("%Y-W%U")
    total = 0.0
    msg = f"📅 <b>Weekly Strategy Report ({week})</b>\n\n"
    for strategy, data in stats.items():
        win_rate = (data["tp"] / data["total"]) * 100 if data["total"] else 0
        msg += (
            f"📌 <b>{strategy}</b>\n"
            f"✔️ TP: {data['tp']} | ❌ SL: {data['sl']} | ⚖️ {win_rate:.1f}% | 💰 {data['pnl']:.2f} USDT\n\n"
        )
        for log in data.get("logs", []):
            try:
                dt = datetime.datetime.fromisoformat(log["timestamp"])
                if dt.strftime("%Y-W%U") == week:
                    total += log["pnl"]
            except:
                continue
    msg += f"📈 Total Weekly PnL: {total:.2f} USDT"
    send_telegram(msg)

def handle_journal():
    from core.strategy_rating import load_strategy_logs
    import datetime
    import pandas as pd

    try:
        raw_data = load_strategy_logs()
        today = datetime.datetime.now().strftime("%Y-%m-%d")
        filtered_logs = []

        msg = f"📔 <b>Trade Journal ({today})</b>\n\n"

        # ✅ Handle both list and dict structures
        if isinstance(raw_data, dict):
            strategy_logs = raw_data.items()
        elif isinstance(raw_data, list):
            # Normalize to: {strategy: [logs]} format
            from collections import defaultdict
            strategy_dict = defaultdict(list)
            for log in raw_data:
                strategy = log.get("strategy", "Unknown")
                strategy_dict[strategy].append(log)
            strategy_logs = strategy_dict.items()
        else:
            raise ValueError("Unsupported format from load_strategy_logs")

        for strategy, logs in strategy_logs:
            for log in logs:
                try:
                    dt = datetime.datetime.fromisoformat(log["timestamp"])
                    if dt.strftime("%Y-%m-%d") == today:
                        log["strategy"] = strategy
                        filtered_logs.append(log)
                except Exception:
                    continue

        # ✅ Sort all logs chronologically before printing
        filtered_logs.sort(key=lambda x: x["timestamp"])
        for log in filtered_logs:
            pnl = log.get("pnl", 0)
            strategy = log.get("strategy", "Unknown")
            result = "✅ TP" if pnl >= 0 else "❌ SL"
            msg += f"{result} | {strategy} | {pnl:+.2f} USDT\n"


        if not filtered_logs:
            msg += "No trades today."

        send_telegram(msg)

        if filtered_logs:
            df = pd.DataFrame(filtered_logs)
            df.to_csv("journal.csv", index=False)
            send_document("journal.csv", caption="📎 Today's Journal")

    except Exception as e:
        send_telegram(f"⚠️ Error in journal: {str(e)}")



def handle_monthly():
    from core.strategy_rating import load_strategy_logs
    logs = load_strategy_logs()
    now = datetime.datetime.now()
    current_month = now.strftime("%Y-%m")
    pnl = 0.0
    count = 0
    for log in logs:
        try:
            dt = datetime.datetime.fromisoformat(log["timestamp"])
            if dt.strftime("%Y-%m") == current_month:
                pnl += log["pnl"]
                count += 1
        except:
            continue
    msg = (
        f"📆 <b>Monthly Summary ({current_month})</b>\n\n"
        f"🧾 Trades: {count}\n"
        f"💰 Total PnL: {pnl:.2f} USDT"
    )
    send_telegram(msg)

def handle_lifetime():
    from core.strategy_rating import load_strategy_logs
    logs = load_strategy_logs()
    pnl = sum(log.get("pnl", 0) for log in logs)
    count = len(logs)
    msg = (
        f"🌍 <b>Lifetime Stats</b>\n\n"
        f"🧾 Trades: {count}\n"
        f"💰 Total PnL: {pnl:.2f} USDT"
    )
    send_telegram(msg)

def send_command_list():
    send_telegram(
        "🤖 <b>TitanBotv2 Online</b>\n\n"
        "Available commands:\n"
        "/status – View current trade status\n"
        "/rating – Strategy leaderboard\n"
        "/summary – Daily/weekly PnL + balance\n"
        "/weekly – Weekly performance per strategy\n"
        "/journal – Today's trade log (CSV)\n"
        "/monthly – This month's total PnL\n"
        "/lifetime – All-time performance\n"
        "/cancel – Emergency order cancel"
    )

def send_document(file_path, caption=None):
    url = f"{BASE_URL}/sendDocument"
    try:
        with open(file_path, "rb") as doc:
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "caption": caption or "Document"
            }
            files = {"document": doc}
            res = requests.post(url, data=payload, files=files)
            if res.status_code != 200:
                print(f"[⚠️] Telegram file error: {res.text}")
    except Exception as e:
        print(f"[⚠️] Telegram file exception: {e}")


def poll_telegram():
    print("[🔄] Telegram polling started...")
    last_update = get_last_update_id()

    # Send full command list on bot startup
    send_command_list()

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
                elif message == "/weekly":
                    handle_weekly()
                elif message == "/journal":
                    handle_journal()
                elif message == "/monthly":
                    handle_monthly()
                elif message == "/lifetime":
                    handle_lifetime()
                elif message == "/help":
                    send_command_list()

            set_last_update_id(last_update)
        except Exception as e:
            print(f"[⚠️] Telegram polling error: {e}")
        time.sleep(5)


# Start auto daily journaling in background
threading.Thread(target=auto_daily_journal, daemon=True).start()
