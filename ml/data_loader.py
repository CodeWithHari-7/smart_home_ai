import pandas as pd
from sqlalchemy import create_engine
import psycopg2

def load_data():
    db_url = "postgresql://postgres:@localhost:5432/smart_home"
    print("Connecting to PostgreSQL database 'smart_home'...")
    engine = create_engine(db_url)
    
    excel_path = "energy_data.xlsx"
    print(f"Reading Excel file '{excel_path}' (this might take 10-15 seconds)...")
    df = pd.read_excel(excel_path)
    print(f"Excel loaded. Total rows: {len(df)}")
    
    # Preprocess date and time columns
    print("Formatting Date and Time...")
    df["Date_str"] = df["Date"].dt.strftime("%Y-%m-%d")
    df["Time_str"] = df["Time"].astype(str)
    df["Date_Time"] = pd.to_datetime(df["Date_str"] + " " + df["Time_str"])
    
    # Drop intermediate columns
    df = df.drop(columns=["Date", "Time", "Date_str", "Time_str"])
    
    # Reorder columns to make Date_Time prominent
    cols = ["S_No", "Date_Time"] + [c for c in df.columns if c not in ["S_No", "Date_Time"]]
    df = df[cols]
    
    print("Bulk inserting data into table 'sensor_data' in PostgreSQL...")
    # bulk insert using pandas
    df.to_sql("sensor_data", engine, if_exists="replace", index=False)
    print("Data loaded successfully.")
    
    # Create index on Date_Time and S_No for performance
    print("Creating indexes on sensor_data...")
    conn = psycopg2.connect(
        dbname="smart_home",
        user="postgres",
        password="",
        host="localhost",
        port=5432
    )
    cur = conn.cursor()
    cur.execute("ALTER TABLE sensor_data ADD PRIMARY KEY (\"S_No\");")
    cur.execute("CREATE INDEX idx_sensor_datetime ON sensor_data (\"Date_Time\");")
    conn.commit()
    cur.close()
    conn.close()
    print("Indexes created. Database setup complete!")

if __name__ == "__main__":
    load_data()
