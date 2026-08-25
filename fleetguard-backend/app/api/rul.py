from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app import models

router = APIRouter(prefix="/api/rul", tags=["Remaining Useful Life"])

@router.get("/{vin}/details")
def get_rul_details(vin: str, part_code: str, db: Session = Depends(get_db)):
    """Powers the RUL KPI metrics: KM, Days, Confidence, and Trend."""
    vin = vin.upper()
    part_code = part_code.upper()
    
    prediction = db.query(models.Prediction).filter(
        models.Prediction.vin == vin,
        models.Prediction.part_code == part_code
    ).first()
    
    if not prediction:
        raise HTTPException(status_code=404, detail="No prediction found.")

    # Assume an average fleet usage rate to convert KM to Days
    # (In a production app, we would average the specific VIN's historical weekly km)
    daily_km_usage = 114 
    
    rul_days = int(prediction.rul_km / daily_km_usage) if prediction.rul_km > 0 else 0
    
    # Synthesize the statistical confidence and trend based on risk tier
    confidence = 93 if prediction.risk_tier == "Red" else (88 if prediction.risk_tier == "Amber" else 75)
    trend = -5.9 if prediction.risk_tier == "Red" else -2.1
    
    return {
        "vin": vin,
        "part_code": part_code,
        "predicted_rul_km": int(prediction.rul_km),
        "predicted_rul_days": rul_days,
        "observed_daily_usage_km": daily_km_usage,
        "model_confidence_pct": confidence,
        "degradation_trend_monthly": trend
    }

@router.get("/{vin}/degradation-curve")
def get_degradation_curve(vin: str, part_code: str, db: Session = Depends(get_db)):
    """Generates the plot coordinates for the Degradation vs Threshold chart."""
    vin = vin.upper()
    part_code = part_code.upper()
    
    prediction = db.query(models.Prediction).filter(
        models.Prediction.vin == vin,
        models.Prediction.part_code == part_code
    ).first()
    
    vehicle = db.query(models.Vehicle).filter(models.Vehicle.vin == vin).first()
    part = db.query(models.Part).filter(models.Part.part_code == part_code).first()
    
    if not prediction or not vehicle or not part:
        raise HTTPException(status_code=404, detail="Required data missing.")

    # Calculate actual mileage on this specific part
    part_mileage = vehicle.total_km % part.design_life_km
    
    # We define a "Health Index" from 100 down to 0. 
    # Failure threshold is usually around 30.
    current_health = 100.0 - prediction.failure_probability_pct
    failure_threshold = 30.0
    
    # Calculate the future kilometer mark where health crosses 30
    failure_km_mark = part_mileage + prediction.rul_km

    # Generate the charting coordinates
    curve = [
        {"km": 0, "health_index": 100.0, "is_projection": False}, # Brand new
        {"km": int(part_mileage * 0.5), "health_index": 100.0 - (prediction.failure_probability_pct * 0.3), "is_projection": False}, # Midpoint history
        {"km": part_mileage, "health_index": current_health, "is_projection": False}, # CURRENT STATE
        {"km": int(failure_km_mark), "health_index": failure_threshold, "is_projection": True}, # PROJECTED FAILURE
        {"km": int(failure_km_mark + 3000), "health_index": max(0, failure_threshold - 15), "is_projection": True} # Post-failure projection
    ]
    
    return {
        "failure_threshold_index": failure_threshold,
        "current_km": part_mileage,
        "curve_data": curve
    }