# config.py

BINANCE_API_KEY = "3496a2c3b8ece53a6d26088af05471aed61c0bf506bade185c235bc2fdd56d91"
BINANCE_API_SECRET = "180dbaeac5bf6b5e7dc04369dc160b872a6ed7f34720813c767c2421455e410d"

# Use Binance Futures Testnet for safety
BASE_URL = "https://testnet.binancefuture.com"

TELEGRAM_BOT_TOKEN = "7502687086:AAE0yi66l9zj87wCWO5ZMfn18_5ZJo8SuKo"
TELEGRAM_CHAT_ID = "462007586"

TRAILING_STOP = {
    "enabled": True,
    "activation_pct": 0.005,  # +0.5% profit to activate trailing
    "trail_pct": 0.003        # trails by 0.3%
}
