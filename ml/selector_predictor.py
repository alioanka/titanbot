
import pandas as pd
import joblib
import lightgbm as lgb

class StrategySelector:
    def __init__(self, model_path="ml/model_strategy_selector.txt", encoder_path="ml/strategy_encoder.pkl"):
        self.model = joblib.load(model_path)
        self.encoder = joblib.load(encoder_path)

    def predict_best_strategy(self, features_df):
        preds = self.model.predict_proba(features_df.drop(columns=["strategy"]))
        probs = [p[1] for p in preds]  # Class 1 = expected TP
        best_idx = probs.index(max(probs))
        return features_df.iloc[best_idx]["strategy"], max(probs)
