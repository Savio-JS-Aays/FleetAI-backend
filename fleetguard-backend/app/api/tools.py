from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app import models

router = APIRouter(prefix="/api/tools", tags=["Agent Tools"])

@router.get("/high-risk")
def get_high_risk_vehicles(part_code: str = None, region: str = None, db: Session = Depends(get_db)):
    """Tool: Returns a list of Red-tier vehicles for the Insight Agent (P0)."""
    query = db.query(models.Prediction, models.Vehicle).join(
        models.Vehicle, models.Prediction.vin == models.Vehicle.vin
    ).filter(models.Prediction.risk_tier == "Red")
    
    if part_code:
        query = query.filter(models.Prediction.part_code == part_code)
    if region:
        query = query.filter(models.Vehicle.region == region)
        
    results = query.all()
    
    # Return a condensed payload optimized for the LLM context window
    return [
        {
            "vin": p.vin, 
            "region": v.region, 
            "part": p.part_code,
            "probability_pct": p.failure_probability_pct
        } 
        for p, v in results
    ]

@router.get("/vehicle-details")
def get_vehicle_details(vin: str, db: Session = Depends(get_db)):
    """Tool: Returns specific RUL and probability for a single VIN (P0)."""
    # Force uppercase to handle user typos in the chat
    vin = vin.upper() 
    
    pred = db.query(models.Prediction).filter(models.Prediction.vin == vin).first()
    
    # P0 Missing Data Handling
    if not pred:
        raise HTTPException(status_code=404, detail=f"Prediction data not found for VIN: {vin}")
        
    return {
        "vin": pred.vin,
        "part_code": pred.part_code,
        "probability_pct": pred.failure_probability_pct,
        "risk_tier": pred.risk_tier,
        "rul_km": pred.rul_km,
        "top_contributing_signal": pred.top_signal
    }

@router.get("/telematics-drilldown")
def get_vehicle_telematics_drilldown(vin: str, db: Session = Depends(get_db)):
    """Tool: Returns the latest telematics signals for a VIN to explain the risk (P0)."""
    vin = vin.upper()
    
    latest = db.query(models.Telematics).filter(models.Telematics.vin == vin)\
        .order_by(models.Telematics.week_start_date.desc()).first()
        
    if not latest:
        raise HTTPException(status_code=404, detail=f"Telematics data not found for VIN: {vin}")
        
    return {
        "vin": latest.vin,
        "week_start": latest.week_start_date,
        "signals": {
            "coolant_temp_variance": latest.coolant_temp_variance,
            "battery_voltage_sag": latest.battery_voltage_sag,
            "oil_pressure_dips": latest.oil_pressure_dips,
            "high_rpm_dwell_time": latest.high_rpm_dwell_time,
            "harsh_braking_frequency": latest.harsh_braking_frequency,
            "idle_time_pct": latest.idle_time_pct
        }
    }