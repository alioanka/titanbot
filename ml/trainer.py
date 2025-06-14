# ml/trainer.py

import pandas as pd
import numpy as np
import lightgbm as lgb
from data.historical_loader import get_historical_klines
from ml.predictor import PredictMarketDirection

def add_technical_indicators(df):
    df["return"] = df["close"].pct_change()
    df["volatility"] = df["return"].rolling(10).std()

    df["ema_5"] = df["close"].ewm(span=5).mean()
    df["ema_13"] = df["close"].ewm(span=13).mean()

    delta = df["close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    rs = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs))

    df["bb_upper"] = df["close"].rolling(20).mean() + 2 * df["close"].rolling(20).std()
    df["bb_lower"] = df["close"].rolling(20).mean() - 2 * df["close"].rolling(20).std()
    df["bb_width"] = df["bb_upper"] - df["bb_lower"]

    df["macd"] = df["close"].ewm(span=12).mean() - df["close"].ewm(span=26).mean()
    df["macd_signal"] = df["macd"].ewm(span=9).mean()
    df["macd_hist"] = df["macd"] - df["macd_signal"]

    high = df["high"]
    low = df["low"]
    close = df["close"]
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df["atr"] = tr.rolling(14).mean()

    df["volume_delta"] = df["volume"] * df["close"].diff()

    df.dropna(inplace=True)
    return df

def generate_labels(df, horizon=5, threshold=0.002):
    df["future_return"] = df["close"].pct_change(horizon).shift(-horizon)
    df["label"] = 0
    df.loc[df["future_return"] > threshold, "label"] = 1
    df.loc[df["future_return"] < -threshold, "label"] = 0
    df.dropna(subset=["label"], inplace=True)
    return df

def build_features_and_labels(df):
    df = add_technical_indicators(df)
    df = generate_labels(df)

    features = df[[
        "return", "volatility", "ema_5", "ema_13", "rsi",
        "bb_upper", "bb_lower", "bb_width",
        "macd_hist", "atr", "volume_delta"
    ]]
    labels = df["label"]

    # Safety check for NaNs
    mask = ~features.isna().any(axis=1) & ~labels.isna()
    return features[mask], labels[mask]

def generate_multiclass_labels(df, threshold=0.004, horizon=6):
    labels = []
    for i in range(len(df)):
        if i + horizon >= len(df):
            labels.append(1)  # HOLD by default at the end
            continue
        future_return = (df["close"].iloc[i + horizon] - df["close"].iloc[i]) / df["close"].iloc[i]
        if future_return > threshold:
            labels.append(2)  # LONG
        elif future_return < -threshold:
            labels.append(0)  # SHORT
        else:
            labels.append(1)  # HOLD
    df["label_class"] = labels
    return df

#test

def train_model(symbol="BTCUSDT", interval="15m", model_path="ml/model_lightgbm.txt"):
    print(f"[📚] Training LightGBM model for {symbol} on {interval} data")

    df = get_historical_klines(symbol=symbol, interval=interval)
    df = add_technical_indicators(df)
    df = generate_multiclass_labels(df)

    df = df.dropna().reset_index(drop=True)

    features = [
        "return", "volatility", "ema_5", "ema_13", "rsi",
        "bb_upper", "bb_lower", "bb_width", "macd_hist", "atr", "volume_delta"
    ]
    features = [f for f in features if f in df.columns]
    X = df[features]
    y = df["label_class"]

    model = lgb.LGBMClassifier(objective="multiclass", num_class=3, n_estimators=100, max_depth=5)
    model.fit(X, y)

    model.booster_.save_model(model_path)
    print(f"[✅] Model trained and saved to {model_path}")

    # Print feature importances
    importance = pd.Series(model.feature_importances_, index=X.columns).sort_values(ascending=False)
    print("[📊] Top Features:")
    print(importance.head(10))
