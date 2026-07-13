import pandas as pd
import numpy as np

# Reference date for calculating elapsed days
# Let's fix this reference date as the starting date of the training dataset
REFERENCE_DATETIME = pd.to_datetime("2024-06-17 19:42:24")

def extract_features(df, is_inference=False):
    """
    Extracts time-series features from the Date_Time column.
    If is_inference is True, df can be a DataFrame containing a single row or multiple rows.
    """
    df = df.copy()
    
    # Ensure Datetime format
    dt = pd.to_datetime(df["Date_Time"])
    
    # 1. Base time components
    df["hour"] = dt.dt.hour
    df["minute"] = dt.dt.minute
    df["day_of_week"] = dt.dt.dayofweek
    df["month"] = dt.dt.month
    
    # 2. Cyclical encoding for Hour (24-hour cycle)
    df["hour_sin"] = np.sin(2 * np.pi * df["hour"] / 24.0)
    df["hour_cos"] = np.cos(2 * np.pi * df["hour"] / 24.0)
    
    # 3. Cyclical encoding for Minute (60-minute cycle)
    df["minute_sin"] = np.sin(2 * np.pi * df["minute"] / 60.0)
    df["minute_cos"] = np.cos(2 * np.pi * df["minute"] / 60.0)
    
    # 4. Cyclical encoding for Day of Week (7-day cycle)
    df["day_of_week_sin"] = np.sin(2 * np.pi * df["day_of_week"] / 7.0)
    df["day_of_week_cos"] = np.cos(2 * np.pi * df["day_of_week"] / 7.0)
    
    # 5. Elapsed time feature (in fractional days) for modeling cumulative trends (like Energy)
    elapsed_timedelta = dt - REFERENCE_DATETIME
    df["elapsed_days"] = elapsed_timedelta.dt.total_seconds() / (24 * 3600)
    
    # Drop raw intermediate features that might overfit (like hour/minute/day_of_week directly)
    # We will use cyclical features, month, and elapsed_days for modeling
    features = [
        "hour_sin", "hour_cos", 
        "minute_sin", "minute_cos", 
        "day_of_week_sin", "day_of_week_cos",
        "month", "elapsed_days"
    ]
    
    return df, features

if __name__ == "__main__":
    test_df = pd.DataFrame({"Date_Time": [pd.to_datetime("2026-08-20 18:30:00")]})
    df_feat, features = extract_features(test_df)
    print("Extracted features list:", features)
    print("Features values for 2026-08-20 18:30:00:")
    print(df_feat[features].to_string())
