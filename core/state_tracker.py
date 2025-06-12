# core/state_tracker.py

import requests
import time
import json
import os
from config import BINANCE_API_KEY, BINANCE_API_SECRET, BASE_URL
import hmac, hashlib
from urllib.parse import urlencode

class StateTracker:
    STATE_FILE = "position_state.json"

    @staticmethod
    def _signed_request(path, params={}, method="GET"):
        timestamp = int(time.time() * 1000)
        params["timestamp"] = timestamp
        query = urlencode(params)
        signature = hmac.new(BINANCE_API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
        url = f"{BASE_URL}{path}?{query}&signature={signature}"

        headers = {"X-MBX-APIKEY": BINANCE_API_KEY}
        if method == "GET":
            res = requests.get(url, headers=headers)
        else:
            res = requests.post(url, headers=headers)
        return res.json()

    @staticmethod
    def get_open_position(symbol):
        try:
            data = StateTracker._signed_request("/fapi/v2/positionRisk")
            for pos in data:
                if pos["symbol"] == symbol:
                    amt = float(pos["positionAmt"])
                    if abs(amt) > 0:
                        print(f"[📍] Found live position: {amt} {symbol}")
                        return {
                            "symbol": symbol,
                            "positionAmt": amt,
                            "entryPrice": float(pos.get("entryPrice", 0)),
                            "unrealizedProfit": float(pos.get("unrealizedProfit", 0)),
                            "side": "LONG" if amt > 0 else "SHORT"
                        }
            return None
        except Exception as e:
            print(f"[⚠️] Error fetching position: {e}")
            return None


    @staticmethod
    def detect_unusual_drawdown(symbol="BTCUSDT", max_loss_pct=0.03):
        pos = StateTracker.get_open_position(symbol)
        if not pos:
            return False

        # ✅ GET LATEST PRICE
        try:
            ticker_url = f"{BASE_URL}/fapi/v1/ticker/price?symbol={symbol}"
            price_data = requests.get(ticker_url).json()
            current_price = float(price_data["price"])
        except Exception as e:
            print(f"[⚠️] Failed to fetch market price: {e}")
            return False

        entry = pos["entryPrice"]
        size = abs(pos["positionAmt"])
        value = entry * size

        # ✅ Calculate PnL manually
        if pos["side"] == "LONG":
            unreal = (current_price - entry) * size
        else:
            unreal = (entry - current_price) * size

        unreal_pct = unreal / value if value > 0 else 0

        print(f"[📉] Live PnL: {unreal:.2f} USDT ({unreal_pct:.2%})")

        if unreal_pct < -max_loss_pct:
            print("[🚨] Max drawdown exceeded!")
            return True
        return False


    @staticmethod
    def save_position_state(position_data):
        with open(StateTracker.STATE_FILE, "w") as f:
            json.dump(position_data, f)

    @staticmethod
    def load_position_state():
        if os.path.exists(StateTracker.STATE_FILE):
            with open(StateTracker.STATE_FILE, "r") as f:
                return json.load(f)
        return None

    @staticmethod
    def clear_state():
        if os.path.exists(StateTracker.STATE_FILE):
            os.remove(StateTracker.STATE_FILE)
