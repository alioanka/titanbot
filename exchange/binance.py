# exchange/binance.py

import time
import hmac
import hashlib
import requests
from urllib.parse import urlencode
from config import BINANCE_API_KEY, BINANCE_API_SECRET, BASE_URL

class BinanceFuturesClient:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"X-MBX-APIKEY": BINANCE_API_KEY})

    def get_klines(self, symbol, interval="5m", limit=150):
        url = f"{BASE_URL}/fapi/v1/klines"
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }
        res = self.session.get(url, params=params)
        data = res.json()
        import pandas as pd
        df = pd.DataFrame(data, columns=[
            "timestamp", "open", "high", "low", "close", "volume",
            "close_time", "quote_volume", "trades", "tb_base", "tb_quote", "ignore"
        ])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        df.set_index("timestamp", inplace=True)
        df = df.astype(float)
        return df[["open", "high", "low", "close", "volume"]]

    def place_order(self, symbol, signal, quantity, sl_price, tp_price, leverage):
        side = "BUY" if signal == "LONG" else "SELL"
        position_side = "LONG" if signal == "LONG" else "SHORT"

        self.set_leverage(symbol, leverage)

        order_params = {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "quantity": self.round_step_size(symbol, quantity),
            "timestamp": int(time.time() * 1000)
        }

        self._signed_post("/fapi/v1/order", order_params)

        # Place SL
        sl_side = "SELL" if side == "BUY" else "BUY"
        sl_params = {
            "symbol": symbol,
            "side": sl_side,
            "type": "STOP_MARKET",
            "stopPrice": round(sl_price, 2),
            "closePosition": True,
            "timestamp": int(time.time() * 1000)
        }
        self._signed_post("/fapi/v1/order", sl_params)

        # Place TP
        tp_params = {
            "symbol": symbol,
            "side": sl_side,
            "type": "TAKE_PROFIT_MARKET",
            "stopPrice": round(tp_price, 2),
            "closePosition": True,
            "timestamp": int(time.time() * 1000)
        }
        self._signed_post("/fapi/v1/order", tp_params)

        print(f"[🟢] Order placed: {side} {quantity} {symbol} @ market | SL: {sl_price}, TP: {tp_price}, Leverage: {leverage}")

    def _signed_post(self, path, params):
        query = urlencode(params)
        signature = hmac.new(BINANCE_API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
        full_url = f"{BASE_URL}{path}?{query}&signature={signature}"
        return self.session.post(full_url)

    def set_leverage(self, symbol, leverage):
        params = {
            "symbol": symbol,
            "leverage": leverage,
            "timestamp": int(time.time() * 1000)
        }
        self._signed_post("/fapi/v1/leverage", params)

    def round_step_size(self, symbol, qty):
        # Naive rounding to 3 decimal places; can be enhanced with exchange rules
        return round(qty, 3)
    
    def cancel_all_orders(self, symbol):
        try:
            params = {
                "symbol": symbol,
                "timestamp": int(time.time() * 1000)
            }
            query = urlencode(params)
            signature = hmac.new(BINANCE_API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
            url = f"{BASE_URL}/fapi/v1/allOpenOrders?{query}&signature={signature}"
            res = self.session.delete(url)
            print(f"[❌] All open orders canceled for {symbol}.")
            return res.json()
        except Exception as e:
            print(f"[⚠️] Failed to cancel open orders: {e}")
            return None
        
    def get_balance(self):
        try:
            params = {
                "timestamp": int(time.time() * 1000)
            }
            query = urlencode(params)
            signature = hmac.new(BINANCE_API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
            url = f"{BASE_URL}/fapi/v2/account?{query}&signature={signature}"
            res = self.session.get(url)
            data = res.json()
            for asset in data.get("assets", []):
                if asset["asset"] == "USDT":
                    return float(asset["walletBalance"])
            return 0.0
        except Exception as e:
            print(f"[⚠️] Failed to fetch balance: {e}")
            return 0.0

    def get_ticker(self, symbol):
        try:
            endpoint = "/fapi/v1/ticker/price"
            params = {"symbol": symbol.upper()}
            response = self._signed_get(endpoint, params=params)
            return float(response["price"])
        except Exception as e:
            print(f"[⚠️] Failed to fetch ticker for {symbol}: {e}")
            return None


