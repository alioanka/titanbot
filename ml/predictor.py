# ml/predictor.py

import pandas as pd
import numpy as np
import lightgbm as lgb
import os

class PredictMarketDirection:
    def __init__(self, model_path="ml/model_lightgbm.txt"):
        self.model_path = model_path
        self.model = self._load_model()
        self.expected_features = [
            "return", "volatility", "ema_5", "ema_13", "rsi",
            "bb_width", "macd_hist", "atr", "volume_delta"
        ]

    def _load_model(self):
        if os.path.exists(self.model_path):
            model = lgb.LGBMClassifier()
            model._Booster = lgb.Booster(model_file=self.model_path)
            return model
        else:
            print("[!] LightGBM model not found. Using fallback prediction.")
            return None

    def _build_features(self, df: pd.DataFrame):
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

        features = df[self.expected_features].copy()
        return features

    def predict(self, df: pd.DataFrame):
        if self.model is None:
            return {"direction": "NEUTRAL"}

        features = self._build_features(df)
        if features.empty:
            return {"direction": "NEUTRAL"}

        X_latest = features.iloc[[-1]]
        try:
            prob = self.model.predict(X_latest)[0]
            if prob > 0.6:
                return {"direction": "UP"}
            elif prob < 0.4:
                return {"direction": "DOWN"}
            else:
                return {"direction": "NEUTRAL"}
        except Exception as e:
            print(f"[⚠️] Prediction failed: {e}")
            return {"direction": "NEUTRAL"}

        
    def _feature_engineering(self, df: pd.DataFrame):
        df = df.copy()
        df["return"] = df["close"].pct_change()
        df["volatility"] = df["return"].rolling(10).std()
        df["sma_5"] = df["close"].rolling(5).mean()
        df["sma_20"] = df["close"].rolling(20).mean()
        df["rsi"] = self._rsi(df["close"], 14)
        df = df.dropna()
        return df[["return", "volatility", "sma_5", "sma_20", "rsi"]]

    def _rsi(self, series, period=14):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))


    def predict_proba(self, df: pd.DataFrame):
        if self.model is None or df.empty:
            return None, -1.0
        df = self._build_features(df.copy())
        X_latest = df[self.expected_features].dropna().tail(1)
        if X_latest.empty:
            return None, -1.0
        try:
            probs = self.model.predict_proba(X_latest)[0]
            return probs, max(probs)
        except Exception as e:
            print(f"[⚠️] Prediction error: {e}")
            return None, -1.0

    def get_signal_from_probs(self, probs):
        if probs is None:
            return "HOLD"
        class_idx = int(np.argmax(probs))
        return ["SHORT", "HOLD", "LONG"][class_idx]

    def predict(self, df: pd.DataFrame):
        probs, confidence = self.predict_proba(df)
        signal = self.get_signal_from_probs(probs)
        print(f"[🧠] ML Signal: {signal} ({confidence:.2f})")
        return signal, confidence
