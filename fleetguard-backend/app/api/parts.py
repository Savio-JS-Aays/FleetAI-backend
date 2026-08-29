from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date, timedelta
import statistics

from app.database import get_db
from app import models

router = APIRouter(prefix="/api/parts", tags=["Parts & History"])

@router.get("")
def get_all_parts(db: Session = Depends(get_db)):
    """
    Step 1 of Rule Builder: Returns a categorized catalog of all trackable components.
    """
    parts = db.query(models.Part).all()
    
    # Map our specific parts to their UI categories AND human-readable descriptions
    part_mapping = {
        "ALT-001": {"category": "Battery & Charging", "name": "Alternator"},
        "WP-002": {"category": "Cooling System", "name": "Water Pump"},
        "TC-003": {"category": "Powertrain", "name": "Turbocharger"}
    }
    
    response = {}
    for p in parts:
        # Fallback to Uncategorized if a new part is ever added to the DB
        mapping = part_mapping.get(p.part_code, {"category": "Uncategorized", "name": p.part_code})
        cat = mapping["category"]
        
        if cat not in response:
            response[cat] = []
            
        response[cat].append({
            "part_code": p.part_code,
            "description": mapping["name"], # Using the mapped name instead of a DB column
            "design_life_km": p.design_life_km
        })
        
    return response

@router.get("/{part_code}/history")
def get_part_history(part_code: str, db: Session = Depends(get_db)):
    """
    Step 2 of Rule Builder: Returns trailing 12-month failure history and KPIs.
    """
    part_code = part_code.upper()
    
    # 1. Fetch all job cards (failures) for this specific part
    cutoff = date.today() - timedelta(days=365)
    failures = db.query(models.JobCard).filter(
        models.JobCard.part_code == part_code,
        models.JobCard.failure_date >= cutoff,
    ).all()
    
    if not failures:
        raise HTTPException(status_code=404, detail=f"No failure history found for part {part_code}")

    # 2. Calculate KPIs
    total_failures = len(failures)
    
    # Count unique VINs affected
    affected_vins = len(set([f.vin for f in failures]))
    
    # Calculate median mileage at failure
    # We estimate this by using the vehicle's current total_km for our synthetic data
    vins_in_failures = [f.vin for f in failures]
    vehicles = db.query(models.Vehicle).filter(models.Vehicle.vin.in_(vins_in_failures)).all()
    failure_mileage = [f.odometer_at_failure for f in failures if f.odometer_at_failure > 0]
    mileages = failure_mileage or [v.total_km for v in vehicles if v.total_km > 0]
    avg_mileage = int(statistics.median(mileages)) if mileages else 0

    # 3. Build the 12-Month Histogram (Jan - Dec)
    # Initialize all 12 months to 0
    monthly_counts = {month: 0 for month in range(1, 13)} 
    
    for f in failures:
        # Increment the count for the specific month the failure occurred
        month = f.failure_date.month
        monthly_counts[month] += 1

    # Format the histogram data for the frontend chart (e.g., {"month": "Jan", "count": 15})
    month_names = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    histogram = [
        {"month": month_names[i-1], "count": monthly_counts[i]} 
        for i in range(1, 13)
    ]

    return {
        "part_code": part_code,
        "historical_failures_count": total_failures,
        "affected_vins_count": affected_vins,
        "avg_mileage_at_failure_km": avg_mileage,
        "monthly_histogram": histogram
    }