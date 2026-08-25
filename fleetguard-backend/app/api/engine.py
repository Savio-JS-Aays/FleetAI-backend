from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app import models

router = APIRouter(prefix="/api/engine", tags=["Predictive Engine"])

@router.get("/overview-kpis")
def get_engine_kpis(db: Session = Depends(get_db)):
    """Powers the 4 KPI cards on the Predictive Failure Engine overview screen."""
    
    # 1. Total VIN/component pairs currently scored
    components_under_watch = db.query(models.Prediction).count()
    
    # 2. Predictions >= 70% threshold
    high_prob_count = db.query(models.Prediction).filter(models.Prediction.failure_probability_pct >= 70.0).count()
    
    # 3. Inside 30-day RUL. 
    # (Assuming a fleet average of ~150km/day, 30 days = 4,500 km)
    inside_30d_rul = db.query(models.Prediction).filter(models.Prediction.rul_km <= 4500).count()
    
    # 4. Validated patterns (We count historical JobCards as validated patterns)
    patterns_validated = db.query(models.JobCard).count()
    
    return {
        "components_under_watch": components_under_watch,
        "high_failure_probability": high_prob_count,
        "components_inside_30_day_rul": inside_30d_rul,
        "precursor_patterns_validated": patterns_validated
    }

@router.get("/top-precursors")
def get_top_precursors(db: Session = Depends(get_db)):
    """Powers the massive bar chart showing the most active signals across the fleet."""
    
    # FIX: Changed Prediction.id to Prediction.vin for the count function
    results = db.query(
        models.Prediction.top_signal, 
        func.count(models.Prediction.vin).label('signal_count') 
    ).filter(models.Prediction.risk_tier == "Red")\
    .group_by(models.Prediction.top_signal)\
    .order_by(func.count(models.Prediction.vin).desc()).all()
    
    # Map raw database column names to clean UI strings
    signal_labels = {
        "battery_voltage_sag": "Battery voltage sag",
        "coolant_temp_variance": "Coolant temp variance",
        "oil_pressure_dips": "Oil pressure dips",
        "high_rpm_dwell_time": "High-RPM dwell time",
        "idle_time_pct": "Idle time pct",
        "overload_duty_share": "Overload duty share",
        "harsh_braking_frequency": "Harsh braking frequency",
        "short_trip_ratio": "Short-trip ratio",
        "dtc_recurrence_rate": "DTC recurrence rate"
    }
    
    formatted_results = []
    for row in results:
        formatted_results.append({
            "signal_name": signal_labels.get(row.top_signal, "Unknown Signal"),
            "value": row.signal_count
        })
        
    return formatted_results