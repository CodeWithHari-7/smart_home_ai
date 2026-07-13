import os
import joblib
import numpy as np
import pandas as pd
from sqlalchemy import create_engine
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
import xgboost as xgb

from ml.preprocessing import load_data_from_db, clean_data
from ml.feature_engineering import extract_features

def train_and_evaluate():
    # 1. Connect to DB and load data
    engine = create_engine("postgresql://postgres:@localhost:5432/smart_home")
    df_raw = load_data_from_db(engine)
    df_cleaned = clean_data(df_raw)
    
    # 2. Extract features
    df_feat, features = extract_features(df_cleaned)
    print(f"Extracted features: {features}")
    
    # 3. Chronological split (80% Train, 10% Val, 10% Test)
    n = len(df_feat)
    train_idx = int(n * 0.8)
    val_idx = int(n * 0.9)
    
    train_df = df_feat.iloc[:train_idx]
    val_df = df_feat.iloc[train_idx:val_idx]
    test_df = df_feat.iloc[val_idx:]
    
    print(f"Split sizes - Train: {len(train_df)}, Val: {len(val_df)}, Test: {len(test_df)}")
    
    # Features for standard targets
    X_train = train_df[features]
    X_val = val_df[features]
    X_test = test_df[features]
    
    # Cyclical features for Energy residual modeling (exclude elapsed_days)
    cyclical_features = [f for f in features if f != "elapsed_days"]
    X_train_cyc = train_df[cyclical_features]
    X_val_cyc = val_df[cyclical_features]
    X_test_cyc = test_df[cyclical_features]
    
    # List of targets for both systems
    targets = {
        "Voltage1": "standard", "Current1": "standard", "Power1": "standard", "Frequency1": "standard", "PowerFactor1": "standard", "Energy1": "cumulative",
        "Voltage2": "standard", "Current2": "standard", "Power2": "standard", "Frequency2": "standard", "PowerFactor2": "standard", "Energy2": "cumulative"
    }
    
    models = {}
    metrics = {}
    
    os.makedirs("models", exist_ok=True)
    
    for target, target_type in targets.items():
        print(f"\nTraining model for {target}...")
        y_train = train_df[target]
        y_val = val_df[target]
        y_test = test_df[target]
        
        if target_type == "standard":
            # Train XGBoost
            model = xgb.XGBRegressor(n_estimators=100, learning_rate=0.1, max_depth=6, random_state=42)
            model.fit(
                X_train, y_train,
                eval_set=[(X_val, y_val)],
                verbose=False
            )
            
            # Predict
            preds = model.predict(X_test)
            models[target] = model
            
        elif target_type == "cumulative":
            # 1. Fit linear trend on elapsed_days
            trend_model = LinearRegression()
            trend_model.fit(train_df[["elapsed_days"]], y_train)
            
            # 2. Get residuals
            train_trend = trend_model.predict(train_df[["elapsed_days"]])
            val_trend = trend_model.predict(val_df[["elapsed_days"]])
            test_trend = trend_model.predict(test_df[["elapsed_days"]])
            
            y_train_res = y_train - train_trend
            y_val_res = y_val - val_trend
            
            # 3. Fit XGBoost on residuals using cyclical features
            res_model = xgb.XGBRegressor(n_estimators=100, learning_rate=0.1, max_depth=6, random_state=42)
            res_model.fit(
                X_train_cyc, y_train_res,
                eval_set=[(X_val_cyc, y_val_res)],
                verbose=False
            )
            
            # Predict
            test_res_preds = res_model.predict(X_test_cyc)
            preds = test_trend + test_res_preds
            
            # Save both models
            models[target] = {
                "trend": trend_model,
                "residual": res_model
            }
            
        # Physical constraints post-processing
        if "Voltage" in target:
            preds = np.clip(preds, 180.0, 250.0)
        elif "Current" in target:
            preds = np.clip(preds, 0.0, None)
        elif "PowerFactor" in target:
            preds = np.clip(preds, 0.0, 1.0)
        elif "Frequency" in target:
            preds = np.clip(preds, 45.0, 55.0)
            
        # Calculate metrics
        mae = mean_absolute_error(y_test, preds)
        rmse = np.sqrt(mean_squared_error(y_test, preds))
        r2 = r2_score(y_test, preds)
        
        # Calculate MAPE (where target is not 0)
        mask = y_test > 0.01
        if mask.sum() > 0:
            mape = np.mean(np.abs((y_test[mask] - preds[mask]) / y_test[mask])) * 100
        else:
            mape = 0.0
            
        metrics[target] = {
            "MAE": float(mae),
            "RMSE": float(rmse),
            "R2": float(r2),
            "MAPE": float(mape)
        }
        
        print(f"{target} Test Metrics - MAE: {mae:.4f}, RMSE: {rmse:.4f}, R2: {r2:.4f}, MAPE: {mape:.2f}%")
        
    # Save all models & metadata
    save_package = {
        "models": models,
        "features": features,
        "cyclical_features": cyclical_features,
        "metrics": metrics,
        "data_start": train_df["Date_Time"].min().isoformat(),
        "data_end": test_df["Date_Time"].max().isoformat()
    }
    
    model_path = os.path.join("models", "energy_prediction_model.joblib")
    joblib.dump(save_package, model_path)
    print(f"\nAll models saved successfully to '{model_path}'")
    
    # Save training metrics to a text file for documentation
    metrics_df = pd.DataFrame(metrics).T
    metrics_df.to_csv(os.path.join("models", "training_metrics.csv"))
    print("Training metrics saved to models/training_metrics.csv")

if __name__ == "__main__":
    train_and_evaluate()
