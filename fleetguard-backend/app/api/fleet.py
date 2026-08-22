from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app import models

router = APIRouter(prefix="/api/fleet", tags=["Fleet Overview"])

@router.get("/summary")
def get_fleet_summary(db: Session = Depends(get_db)):
    """
    Returns aggregate KPIs for the Executive Overview dashboard (P0 Requirement).
    """
    # 1. Total Vehicles Monitored
    total_vehicles = db.query(models.Vehicle).count()
    
    # 2. Critical Red Alerts (Count of predictions where tier is Red)
    red_alerts = db.query(models.Prediction).filter(models.Prediction.risk_tier == "Red").count()
    
    # 3. Average Fleet RUL
    avg_rul_result = db.query(func.avg(models.Prediction.rul_km)).scalar()
    avg_rul = int(avg_rul_result) if avg_rul_result else 0
    
    return {
        "total_vehicles": total_vehicles,
        "red_alerts": red_alerts,
        "avg_rul": avg_rul
    }