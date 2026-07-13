import os
import sys
from datetime import datetime, timedelta
import io
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import create_engine

# Add the project root to sys.path so we can import from ml
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from ml.inference import predict_future, load_models

app = FastAPI(title="Smart Home Predictive Energy System")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Connect to database
DB_URL = "postgresql://postgres:@localhost:5432/smart_home"
engine = create_engine(DB_URL)

# Mount frontend directory for static assets (js, css, images)
# Note: we will serve index.html directly from "/"
os.makedirs("frontend", exist_ok=True)
app.mount("/frontend", StaticFiles(directory="frontend"), name="frontend")

class PredictionRequest(BaseModel):
    date: str  # YYYY-MM-DD
    time: str  # HH:MM or HH:MM:SS
    load_id: int = 1  # 1 or 2

def get_time_shift():
    """
    Calculates the timedelta to shift the dataset's max timestamp
    to the current real-world local time. This makes the data appear 'live'.
    """
    dataset_max_time = datetime(2024, 6, 30, 23, 59, 55)
    now = datetime.now()
    return now - dataset_max_time

@app.get("/")
def read_root():
    html_path = os.path.join("frontend", "index.html")
    if os.path.exists(html_path):
        return FileResponse(html_path)
    return HTMLResponse("Frontend files not created yet. Please wait.", status_code=404)

@app.get("/api/history")
def get_history(
    load_id: int = Query(1, ge=1, le=2),
    limit: int = Query(100, ge=1, le=2000),
    from_date: str = Query(None),
    to_date: str = Query(None)
):
    try:
        # Load recent data from database
        query = f"""
            SELECT "S_No", "Date_Time", 
                   "Voltage{load_id}" AS "Voltage", 
                   "Current{load_id}" AS "Current", 
                   "Power{load_id}" AS "Power", 
                   "Frequency{load_id}" AS "Frequency", 
                   "PowerFactor{load_id}" AS "PowerFactor", 
                   "Energy{load_id}" AS "Energy"
            FROM sensor_data
            ORDER BY "Date_Time" DESC
            LIMIT {limit}
        """
        df = pd.read_sql(query, engine)
        if df.empty:
            return []
            
        # Reverse to chronological order for charts
        df = df.iloc[::-1].reset_index(drop=True)
        
        # Apply time shift so timestamps appear current
        shift = get_time_shift()
        df["Date_Time"] = df["Date_Time"] + shift
        
        # Filter by shifted datetime if requested
        if from_date:
            try:
                from_dt = pd.to_datetime(from_date)
                df = df[df["Date_Time"] >= from_dt]
            except Exception:
                pass
        if to_date:
            try:
                to_dt = pd.to_datetime(to_date)
                df = df[df["Date_Time"] <= to_dt]
            except Exception:
                pass
                
        # Format Date_Time as string
        df["Date_Time"] = df["Date_Time"].dt.strftime("%Y-%m-%d %H:%M:%S")
        
        return df.to_dict(orient="records")
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/export")
def export_data(
    load_id: int = Query(1, ge=1, le=2),
    from_date: str = Query(None),
    to_date: str = Query(None)
):
    try:
        # Load all history or filtered history
        query = f"""
            SELECT "S_No", "Date_Time", 
                   "Voltage{load_id}" AS "Voltage", 
                   "Current{load_id}" AS "Current", 
                   "Power{load_id}" AS "Power", 
                   "Frequency{load_id}" AS "Frequency", 
                   "PowerFactor{load_id}" AS "PowerFactor", 
                   "Energy{load_id}" AS "Energy"
            FROM sensor_data
            ORDER BY "Date_Time" ASC
        """
        df = pd.read_sql(query, engine)
        if df.empty:
            raise HTTPException(status_code=404, detail="No data available to export")
            
        # Apply time shift so timestamps appear current
        shift = get_time_shift()
        df["Date_Time"] = df["Date_Time"] + shift
        
        # Filter by shifted datetime if requested
        if from_date:
            try:
                from_dt = pd.to_datetime(from_date)
                df = df[df["Date_Time"] >= from_dt]
            except Exception:
                pass
        if to_date:
            try:
                to_dt = pd.to_datetime(to_date)
                df = df[df["Date_Time"] <= to_dt]
            except Exception:
                pass
                
        # Format Date_Time as string
        df["Date_Time"] = df["Date_Time"].dt.strftime("%Y-%m-%d %H:%M:%S")
        
        # Convert to CSV
        stream = io.StringIO()
        df.to_csv(stream, index=False)
        response = StreamingResponse(
            iter([stream.getvalue()]),
            media_type="text/csv"
        )
        response.headers["Content-Disposition"] = f"attachment; filename=sensor_data_load{load_id}.csv"
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/predict-energy")
def predict_energy(req: PredictionRequest):
    try:
        # Validate load_id
        if req.load_id not in [1, 2]:
            raise HTTPException(status_code=400, detail="Invalid load_id. Must be 1 or 2.")
            
        # Parse inputs to validate date/time format
        try:
            target_dt = pd.to_datetime(f"{req.date} {req.time}")
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid date or time format. Use YYYY-MM-DD and HH:MM.")
            
        # Physical date boundary checks
        # Dataset starts in 2024-06-17. The shifted dataset starts roughly 13 days ago and ends now.
        # Ensure we only predict future dates relative to current local time.
        now = datetime.now()
        if target_dt < now:
            # Check if it's within the dataset time range
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "error": f"The requested date/time ({target_dt}) is in the past. Predictions can only be made for future datetimes (after {now.strftime('%Y-%m-%d %H:%M:%S')})."
                }
            )
            
        # Since our ML model was trained on the raw 2024 dates, we need to map the user's
        # requested future datetime (e.g. in 2026) BACK to the raw training date coordinate!
        # Specifically, we subtract the shift!
        shift = get_time_shift()
        raw_target_dt = target_dt - shift
        
        raw_date_str = raw_target_dt.strftime("%Y-%m-%d")
        raw_time_str = raw_target_dt.strftime("%H:%M:%S")
        
        # Run inference using the raw coordinate
        predictions = predict_future(raw_date_str, raw_time_str, load_id=req.load_id)
        
        # Model metadata
        bundle = load_models()
        metrics = bundle["metrics"]
        
        # Extract evaluation metrics for this load to display transparency
        load_metrics = {
            k.replace(str(req.load_id), ""): v 
            for k, v in metrics.items() if str(req.load_id) in k
        }
        
        # Calculate forecast horizon in days
        horizon_days = (target_dt - now).total_seconds() / (24 * 3600)
        
        return {
            "success": True,
            "prediction_datetime": target_dt.strftime("%Y-%m-%dT%H:%M:%S"),
            "predictions": predictions,
            "model_information": {
                "model_name": "XGBoost + Linear Residual Energy Forecaster",
                "forecast_horizon": f"{horizon_days:.2f} days",
                "evaluation_metrics": load_metrics
            }
        }
        
    except HTTPException as he:
        raise he
    except FileNotFoundError as fnf:
        raise HTTPException(status_code=503, detail=str(fnf))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/model-info")
def get_model_info():
    try:
        bundle = load_models()
        return {
            "model_name": "XGBoost Regressor + Linear Trend Accumulator",
            "features": bundle["features"],
            "metrics": bundle["metrics"],
            "training_period": {
                "start": bundle["data_start"],
                "end": bundle["data_end"]
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
