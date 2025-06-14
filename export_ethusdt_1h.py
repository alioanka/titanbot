from binance.client import Client
import pandas as pd

api_key = "3496a2c3b8ece53a6d26088af05471aed61c0bf506bade185c235bc2fdd56d91"
api_secret = "180dbaeac5bf6b5e7dc04369dc160b872a6ed7f34720813c767c2421455e410d"
client = Client(api_key, api_secret)

raw = client.futures_klines(symbol="ETHUSDT", interval="1h", limit=1000)

columns = [
    "timestamp", "open", "high", "low", "close", "volume",
    "close_time", "quote_asset_volume", "num_trades",
    "taker_buy_base", "taker_buy_quote", "ignore"
]
df = pd.DataFrame(raw, columns=columns)
df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
df = df[["timestamp", "open", "high", "low", "close", "volume"]]
df.to_csv("ETHUSDT_1h.csv", index=False)

print("✅ ETHUSDT_1h.csv exported with timestamp.")
