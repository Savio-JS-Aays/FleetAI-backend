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
    """
    Dynamically calculates fleet-wide aggregate precursor weights by 
    summing up the latest telemetry signals across all 500 vehicles.
    """
    # 1. Find the most recent week of telemetry in the database
    latest_week = db.query(func.max(models.Telematics.week_start_date)).scalar()
    
    if not latest_week:
        return []

    # 2. Dynamically sum the actual database values for ALL 9 tracked signals
    stats = db.query(
        func.sum(models.Telematics.coolant_temp_variance).label("coolant_temp_variance"),
        func.sum(models.Telematics.oil_pressure_dips).label("oil_pressure_dips"),
        func.sum(models.Telematics.battery_voltage_sag).label("battery_voltage_sag"),
        func.sum(models.Telematics.dtc_recurrence_rate).label("dtc_recurrence_rate"),
        func.sum(models.Telematics.harsh_braking_frequency).label("harsh_braking_frequency"),
        func.sum(models.Telematics.overload_duty_share).label("overload_duty_share"),
        func.sum(models.Telematics.high_rpm_dwell_time).label("high_rpm_dwell_time"),
        func.sum(models.Telematics.short_trip_ratio).label("short_trip_ratio"),
        func.sum(models.Telematics.idle_time_pct).label("idle_time_pct")
    ).filter(models.Telematics.week_start_date == latest_week).first()

    if not stats:
        return []

    # 3. Format the response for the frontend UI
    results = [
        {"signal_name": "coolant_temp_variance", "value": int(stats.coolant_temp_variance or 0)},
        {"signal_name": "oil_pressure_dips", "value": int(stats.oil_pressure_dips or 0)},
        {"signal_name": "battery_voltage_sag", "value": int(stats.battery_voltage_sag or 0)},
        {"signal_name": "dtc_recurrence_rate", "value": int(stats.dtc_recurrence_rate or 0)},
        {"signal_name": "harsh_braking_frequency", "value": int(stats.harsh_braking_frequency or 0)},
        {"signal_name": "overload_duty_share", "value": int(stats.overload_duty_share or 0)},
        {"signal_name": "high_rpm_dwell_time", "value": int(stats.high_rpm_dwell_time or 0)},
        {"signal_name": "short_trip_ratio", "value": int(stats.short_trip_ratio or 0)},
        {"signal_name": "idle_time_pct", "value": int(stats.idle_time_pct or 0)}
    ]
    
    # 4. Automatically sort highest to lowest so the UI renders descending bars perfectly
    return sorted(results, key=lambda x: x["value"], reverse=True)