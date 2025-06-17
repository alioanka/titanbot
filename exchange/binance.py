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
        sl_side = "SELL" if side == "BUY" else "BUY"

        self.set_leverage(symbol, leverage)

        # 1. Place Market Order
        order_params = {
            "symbol": symbol,
            "side": side,
            "type": "MARKET",
            "quantity": self.round_step_size(symbol, quantity),
            "timestamp": int(time.time() * 1000)
        }
        order_response = self._signed_post("/fapi/v1/order", order_params)

        # 2. Place SL
        sl_params = {
            "symbol": symbol,
            "side": sl_side,
            "type": "STOP_MARKET",
            "stopPrice": round(sl_price, 2),
            "closePosition": True,
            "workingType": "MARK_PRICE",
            "timestamp": int(time.time() * 1000)
        }
        sl_response = self._signed_post("/fapi/v1/order", sl_params)

        # 3. Place TP
        tp_params = {
            "symbol": symbol,
            "side": sl_side,
            "type": "TAKE_PROFIT_MARKET",
            "stopPrice": round(tp_price, 2),
            "closePosition": True,
            "workingType": "MARK_PRICE",
            "timestamp": int(time.time() * 1000)
        }
        tp_response = self._signed_post("/fapi/v1/order", tp_params)

        # 4. Log and Alert if SL or TP fails
        if '"orderId"' not in sl_response.text:
            print(f"[❌] SL order FAILED for {symbol}: {sl_response.text}")
            from utils.telegram import send_telegram
            send_telegram(f"❌ <b>SL Order FAILED</b> for {symbol}\n<code>{sl_response.text}</code>")

        if '"orderId"' not in tp_response.text:
            print(f"[❌] TP order FAILED for {symbol}: {tp_response.text}")
            from utils.telegram import send_telegram
            send_telegram(f"❌ <b>TP Order FAILED</b> for {symbol}\n<code>{tp_response.text}</code>")

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
            url = f"{BASE_URL}/fapi/v1/ticker/price"
            params = {"symbol": symbol.upper()}
            response = requests.get(url, params=params).json()
            return float(response["price"])
        except Exception as e:
            print(f"[⚠️] Failed to fetch ticker for {symbol}: {e}")
            return 0.0
        
    def get_current_price(self, symbol: str) -> float:
        """
        Fetch the current price for the given symbol from Binance Futures.
        """
        url = f"{BASE_URL}/fapi/v1/ticker/price?symbol={symbol}"
        response = self.session.get(url)
        response.raise_for_status()
        return float(response.json()["price"])
    
    def verify_open_orders(self, symbol):
        url = f"{BASE_URL}/fapi/v1/openOrders"
        params = {
            "symbol": symbol,
            "timestamp": int(time.time() * 1000)
        }
        query = urlencode(params)
        signature = hmac.new(BINANCE_API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
        full_url = f"{url}?{query}&signature={signature}"
        response = self.session.get(full_url)

        sl_found, tp_found = False, False
        if response.status_code == 200:
            orders = response.json()
            for o in orders:
                if o.get("type") == "STOP_MARKET" and o.get("closePosition"):
                    sl_found = True
                if o.get("type") == "TAKE_PROFIT_MARKET" and o.get("closePosition"):
                    tp_found = True
        return sl_found, tp_found
    
    def safe_place_order(self, symbol, signal, qty, sl, tp, leverage):
        self.cancel_all_orders(symbol)  # Just in case
        self.place_order(symbol, signal, qty, sl, tp, leverage)

        # Wait briefly to ensure Binance processes orders
        time.sleep(2)

        sl_ok, tp_ok = self.verify_open_orders(symbol)
        if not sl_ok or not tp_ok:
            print(f"[⚠️] SL or TP order missing for {symbol}, retrying once...")
            print(f"[DEBUG] Missing SL: {not sl_ok}, Missing TP: {not tp_ok}")

            self.place_order(symbol, signal, qty, sl, tp, leverage)
            time.sleep(2)
            sl_ok, tp_ok = self.verify_open_orders(symbol)

            if not sl_ok or not tp_ok:
                from utils.telegram import send_telegram
                send_telegram(f"❌ <b>Failed to verify SL/TP</b> for {symbol} after retry. Manual check recommended.")
            else:
                print(f"[✅] SL/TP verified after retry for {symbol}")









