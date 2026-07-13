import os
import joblib
import pandas as pd
import numpy as np
from ml.feature_engineering import extract_features

# Cache for the model bundle
_model_bundle = None

def load_models():
    global _model_bundle
    if _model_bundle is None:
        model_path = os.path.join("models", "energy_prediction_model.joblib")
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model file not found at '{model_path}'. Please run training first.")
        print(f"Loading model bundle from '{model_path}'...")
        _model_bundle = joblib.load(model_path)
    return _model_bundle

def predict_future(date_str, time_str, load_id=1):
    """
    Predicts electrical parameters for a future date and time.
    load_id can be 1 (Load-1/System 1) or 2 (Load-2/System 2).
    """
    bundle = load_models()
    models = bundle["models"]
    features = bundle["features"]
    cyclical_features = bundle["cyclical_features"]
    
    # 1. Parse date and time
    dt_str = f"{date_str} {time_str}"
    try:
        dt = pd.to_datetime(dt_str)
    except Exception as e:
        raise ValueError(f"Invalid date/time format: {dt_str}. Error: {e}")
        
    # 2. Create input DataFrame
    input_df = pd.DataFrame({"Date_Time": [dt]})
    input_feat, _ = extract_features(input_df)
    
    # 3. Predict metrics
    prefix = f"Voltage{load_id}"
    if prefix not in models:
        raise ValueError(f"Invalid load_id: {load_id}")
        
    X = input_feat[features]
    X_cyc = input_feat[cyclical_features]
    
    # Predict individual parameters
    voltage = float(models[f"Voltage{load_id}"].predict(X)[0])
    current = float(models[f"Current{load_id}"].predict(X)[0])
    pf = float(models[f"PowerFactor{load_id}"].predict(X)[0])
    frequency = float(models[f"Frequency{load_id}"].predict(X)[0])
    
    # Energy prediction (trend + residual)
    energy_models = models[f"Energy{load_id}"]
    trend_val = float(energy_models["trend"].predict(input_feat[["elapsed_days"]])[0])
    residual_val = float(energy_models["residual"].predict(X_cyc)[0])
    energy = float(trend_val + residual_val)
    
    # 4. Apply physical constraints
    voltage = float(np.clip(voltage, 180.0, 250.0))
    current = float(np.clip(current, 0.0, None))
    pf = float(np.clip(pf, 0.0, 1.0))
    frequency = float(np.clip(frequency, 48.0, 52.0))
    energy = float(np.clip(energy, 0.0, None))
    
    # 5. Compute Power physically: Power = Voltage * Current * PowerFactor
    # We also have an XGBoost model for Power, we can use it or compute it.
    # The physical formula is extremely consistent (MAE ~0.1-0.2W), so we use it.
    power = float(voltage * current * pf)
    
    # Round metrics for presentation
    return {
        "voltage": round(voltage, 1),
        "current": round(current, 2),
        "power": round(power, 1),
        "power_factor": round(pf, 2),
        "frequency": round(frequency, 1),
        "energy": round(energy, 2)
    }

if __name__ == "__main__":
    # Test prediction
    try:
        pred = predict_future("2026-08-20", "18:30:00", load_id=1)
        print("Prediction for Load 1:", pred)
    except Exception as e:
        print("Error during test prediction:", e)
