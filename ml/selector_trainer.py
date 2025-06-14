
import pandas as pd
import numpy as np
import lightgbm as lgb
import ta
from sklearn.preprocessing import LabelEncoder
from sklearn.model_selection import train_test_split
import joblib

# Load ETH candle data
eth_df = pd.read_csv("ETHUSDT_1h.csv")
eth_df["timestamp"] = pd.to_datetime(eth_df["timestamp"])
eth_df.set_index("timestamp", inplace=True)

# Compute features
eth_df["rsi"] = ta.momentum.RSIIndicator(eth_df["close"]).rsi()
eth_df["atr"] = ta.volatility.AverageTrueRange(eth_df["high"], eth_df["low"], eth_df["close"]).average_true_range()
eth_df["ma14"] = eth_df["close"].rolling(14).mean()
eth_df["ma_trend"] = eth_df["ma14"].pct_change(periods=5)
eth_df["volume_ratio"] = eth_df["volume"] / eth_df["volume"].rolling(14).mean()
eth_df["body_ratio"] = abs(eth_df["close"] - eth_df["open"]) / (eth_df["high"] - eth_df["low"] + 1e-6)
eth_df.dropna(inplace=True)
eth_df.reset_index(inplace=True)

# Load trade journal
journal = pd.read_csv("journal.csv")
journal["timestamp"] = pd.to_datetime(journal["timestamp"])
journal["timestamp_rounded"] = journal["timestamp"].dt.floor("H")
journal["target"] = (journal["pnl"] > 0).astype(int)

# Merge candles with journal
merged = pd.merge(
    journal,
    eth_df,
    how="inner",
    left_on="timestamp_rounded",
    right_on="timestamp"
)

# Encode strategy
le = LabelEncoder()
merged["strategy_encoded"] = le.fit_transform(merged["strategy"])

# Prepare training data
features = ["rsi", "atr", "ma_trend", "volume_ratio", "body_ratio", "strategy_encoded"]
X = merged[features]
y = merged["target"]

# Train/test split
X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)

# Train LightGBM
model = lgb.LGBMClassifier()
model.fit(X_train, y_train)

# Save model and encoder
joblib.dump(model, "model_strategy_selector.txt")
joblib.dump(le, "strategy_encoder.pkl")
print("✅ Model and encoder saved.")
