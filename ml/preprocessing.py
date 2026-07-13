import pandas as pd
import numpy as np

def load_data_from_db(engine):
    """
    Loads raw sensor data from the PostgreSQL database.
    """
    query = "SELECT * FROM sensor_data ORDER BY \"Date_Time\" ASC"
    print("Loading data from PostgreSQL...")
    df = pd.read_sql(query, engine)
    print(f"Loaded {len(df)} rows from database.")
    return df

def clean_data(df):
    """
    Cleans the raw data.
    - Sorts chronologically
    - Drops exact duplicates
    - Imputes anomalies (like frequency or voltage dropping to 0 when power is ON)
    """
    df = df.copy()
    
    # 1. Sort by Date_Time
    df = df.sort_values("Date_Time").reset_index(drop=True)
    
    # 2. Remove exact duplicate rows
    initial_len = len(df)
    df = df.drop_duplicates(subset=["Date_Time"], keep="first").reset_index(drop=True)
    if len(df) < initial_len:
        print(f"Removed {initial_len - len(df)} duplicate rows based on timestamp.")
        
    # 3. Handle anomalies
    # In electrical grids, frequency should be ~50Hz. A value of 0.0 is an outage/sensor issue.
    # If Voltage = 0 and Current = 0, it's a legitimate blackout.
    # Let's clean Frequency columns: replace 0 with 50.0 or forward fill when current > 0
    for i in [1, 2]:
        freq_col = f"Frequency{i}"
        curr_col = f"Current{i}"
        
        # If Current > 0 but Frequency == 0, replace with 50.0 (sensor error)
        mask = (df[curr_col] > 0.01) & (df[freq_col] < 40.0)
        df.loc[mask, freq_col] = 50.0
        
        # If Frequency is completely 0 and current is 0, keep it or set to 0.
        # Ensure voltage is non-negative, current is non-negative
        df[f"Voltage{i}"] = df[f"Voltage{i}"].clip(lower=0.0)
        df[f"Current{i}"] = df[f"Current{i}"].clip(lower=0.0)
        df[f"Power{i}"] = df[f"Power{i}"].clip(lower=0.0)
        df[f"PowerFactor{i}"] = df[f"PowerFactor{i}"].clip(lower=0.0, upper=1.0)
        df[f"Frequency{i}"] = df[f"Frequency{i}"].clip(lower=0.0)
        df[f"Energy{i}"] = df[f"Energy{i}"].clip(lower=0.0)
        
    return df

if __name__ == "__main__":
    from sqlalchemy import create_engine
    engine = create_engine("postgresql://postgres:@localhost:5432/smart_home")
    df = load_data_from_db(engine)
    df_clean = clean_data(df)
    print("Cleaned data shape:", df_clean.shape)
