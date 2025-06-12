# data/historical_loader.py

import requests
import pandas as pd
import time

def get_historical_klines(symbol="BTCUSDT", interval="5m", lookback_days=180):
    base_url = "https://fapi.binance.com/fapi/v1/klines"
    end_time = int(time.time() * 1000)
    limit = 1500  # max per request
    all_data = []

    ms_per_candle = {
        "1m": 60_000,
        "3m": 180_000,
        "5m": 300_000,
        "15m": 900_000,
        "1h": 3_600_000,
        "4h": 14_400_000
    }[interval]

    total_candles = int((lookback_days * 24 * 60 * 60 * 1000) / ms_per_candle)
    start_time = end_time - total_candles * ms_per_candle

    while start_time < end_time:
        params = {
            "symbol": symbol,
            "interval": interval,
            "startTime": start_time,
            "limit": limit
        }
        try:
            response = requests.get(base_url, params=params)
            data = response.json()
            if not data:
                break
            all_data.extend(data)
            start_time = data[-1][0] + ms_per_candle
            time.sleep(0.5)  # avoid rate limits
        except Exception as e:
            print(f"[!] Error fetching data: {e}")
            time.sleep(2)

    df = pd.DataFrame(all_data, columns=[
        "timestamp", "open", "high", "low", "close", "volume",
        "close_time", "quote_asset_volume", "num_trades",
        "taker_buy_base_vol", "taker_buy_quote_vol", "ignore"
    ])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    df.set_index("timestamp", inplace=True)
    df = df.astype(float)
    return df[["open", "high", "low", "close", "volume"]]
