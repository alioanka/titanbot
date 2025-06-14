
import pandas as pd
from ml.selector_predictor import StrategySelector
import joblib

# Load encoder and extract known strategies
encoder = joblib.load("ml/strategy_encoder.pkl")
strategies = list(encoder.classes_)

# Create dummy feature data (same length as strategies list)
data = []
for i in range(len(strategies)):
    data.append({
        "rsi": 50 + i,
        "atr": 10 + i * 0.5,
        "ma_trend": 0.002 * i,
        "volume_ratio": 1.1 + i * 0.1,
        "body_ratio": 0.4 + i * 0.05
    })

# Build DataFrame
df = pd.DataFrame(data)
df["strategy"] = strategies
df["strategy_encoded"] = encoder.transform(strategies)

# Run selector
selector = StrategySelector(
    model_path="ml/model_strategy_selector.txt",
    encoder_path="ml/strategy_encoder.pkl"
)

best_strategy, confidence = selector.predict_best_strategy(df)
print(f"🧠 ML Selector Picked: {best_strategy} (Confidence: {confidence:.2f})")
