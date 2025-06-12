# emergency/kill_switch.py

from core.state_tracker import StateTracker
import requests
import time
import hmac, hashlib
from urllib.parse import urlencode
from config import BINANCE_API_KEY, BINANCE_API_SECRET, BASE_URL
from utils.telegram import send_telegram

def emergency_exit(client):
    print("[🚨] Emergency kill switch activated!")

    pos = StateTracker.get_open_position("BTCUSDT")
    if not pos:
        print("[✅] No open position to close.")
        return

    side = "SELL" if pos["side"] == "LONG" else "BUY"
    qty = abs(pos["positionAmt"])

    # ✅ GET LATEST PRICE
    try:
        ticker_url = f"{BASE_URL}/fapi/v1/ticker/price?symbol=BTCUSDT"
        price_data = requests.get(ticker_url).json()
        current_price = float(price_data["price"])
    except Exception as e:
        print(f"[⚠️] Failed to fetch market price: {e}")
        current_price = pos["entryPrice"]  # fallback

    entry = pos["entryPrice"]
    size = abs(pos["positionAmt"])
    if pos["side"] == "LONG":
        unreal = (current_price - entry) * size
    else:
        unreal = (entry - current_price) * size

    params = {
        "symbol": "BTCUSDT",
        "side": side,
        "type": "MARKET",
        "quantity": round(qty, 3),
        "timestamp": int(time.time() * 1000)
    }
    query = urlencode(params)
    signature = hmac.new(BINANCE_API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    url = f"{BASE_URL}/fapi/v1/order?{query}&signature={signature}"
    headers = {"X-MBX-APIKEY": BINANCE_API_KEY}
    res = requests.post(url, headers=headers)

    print(f"[🛑] Emergency close response: {res.json()}")

    send_telegram(f"🛑 <b>Position is closed by Emergency Exit</b>\nSymbol: BTCUSDT\nReason: Max drawdown exceeded.")
    # Cancel remaining SL/TP orders after emergency exit
    client.cancel_all_orders("BTCUSDT")  
    from core.performance_logger import log_strategy_result
    log_strategy_result(strategy_name="Unknown", result="EMERGENCY", pnl=round(unreal, 2), timestamp=None)

    StateTracker.clear_state()

