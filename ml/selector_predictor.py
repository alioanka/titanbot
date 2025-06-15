import pandas as pd
import joblib
import lightgbm as lgb
import warnings
warnings.filterwarnings("ignore", category=FutureWarning, message=".*Downcasting behavior in `replace`.*")


class StrategySelector:
    def __init__(self, model_path="ml/model_strategy_selector.txt", encoder_path="ml/strategy_encoder.pkl"):
        self.model = joblib.load(model_path)
        self.encoder = joblib.load(encoder_path)

    def predict_best_strategy(self, features_df):
        df = features_df.copy()

        # Encode strategy
        df["strategy_encoded"] = self.encoder.transform(df["strategy"])

        # Convert 'zone' to numeric if it's categorical
        if "zone" in df.columns:
            df["zone"] = df["zone"].replace({
                "Sideways": 0,
                "Bullish": 1,
                "Bearish": -1
            }).astype("int64", copy=False)

        # Prepare inputs
        model_features = ["rsi", "atr", "ma_trend", "volume_ratio", "body_ratio", "zone", "strategy_encoded"]
        preds = self.model.predict_proba(df[model_features])
        probs = [p[1] for p in preds]  # Class 1 = expected TP

        best_idx = probs.index(max(probs))
        return df.iloc[best_idx]["strategy"], max(probs)
