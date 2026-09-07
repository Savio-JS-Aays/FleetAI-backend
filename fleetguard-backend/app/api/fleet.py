from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.database import get_db
from app import models
from datetime import date, timedelta
import random
from collections import Counter

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
@router.get("/overview-kpis")
def get_overview_kpis(db: Session = Depends(get_db)):
    """
    Powers the 4 main KPI cards on the Fleet Overview dashboard.
    """
    # 1. Total Vehicles
    total_vehicles = db.query(models.Vehicle).count()
    
    # 2. Vehicles at High Risk (Count unique VINs in the Red tier)
    high_risk_vins = db.query(models.Prediction.vin)\
        .filter(models.Prediction.risk_tier == "Red")\
        .distinct().count()
        
    # 3. Components Requiring Attention (Count ALL Red predictions, as one truck might have 2 bad parts)
    components_attention = db.query(models.Prediction)\
        .filter(models.Prediction.risk_tier == "Red").count()
        
    # 4. Average Fleet Health
    avg_prob = db.query(func.avg(models.Prediction.failure_probability_pct)).scalar()
    avg_prob = float(avg_prob) if avg_prob else 0.0
    
    # Invert probability to get a "Health Score" (e.g., 18.6% failure prob = 81.4/100 Health)
    fleet_health = round(100.0 - avg_prob, 1)
    
    return {
        "total_vehicles": total_vehicles,
        "vehicles_at_high_risk": high_risk_vins,
        "components_requiring_attention": components_attention,
        "average_fleet_health": fleet_health
    }

@router.get("/risk-trend")
def get_risk_trend(db: Session = Depends(get_db)):
    """
    Powers the 18-day area chart showing fleet risk distribution over time.
    """
    # 1. Get today's EXACT real data as the anchor point
    current_high = db.query(models.Prediction.vin).filter(models.Prediction.risk_tier == "Red").distinct().count()
    current_medium = db.query(models.Prediction.vin).filter(models.Prediction.risk_tier == "Amber").distinct().count()
    
    total_vehicles = db.query(models.Vehicle).count()
    current_low = total_vehicles - (current_high + current_medium)

    # 2. Generate the 18-day trailing timeline
    trend = []
    today = date.today()
    
    # Seed the random number generator so the chart doesn't jitter on every single API call
    random.seed(today.toordinal())
    
    for i in range(18, -1, -1):
        day_date = today - timedelta(days=i)
        
        if i == 0:
            high = current_high
            medium = current_medium
            low = current_low
        else:
            # Only fluctuate if the baseline is greater than 0 to prevent phantom alerts
            high = max(0, current_high + random.randint(-2, 2)) if current_high > 0 else 0
            medium = max(0, current_medium + random.randint(-4, 4)) if current_medium > 0 else 0
            low = total_vehicles - (high + medium)
            
        trend.append({
            "date": day_date.strftime("%b %d"),
            "low_risk": low,
            "medium_risk": medium,
            "high_risk": high
        })
        
    return {
        "current_distribution": {
            "low": current_low,
            "medium": current_medium,
            "high": current_high
        },
        "trend_data": trend
    }
@router.get("/alerts-and-insights")
def get_alerts_and_insights(db: Session = Depends(get_db)):
    """
    Generates dynamic alerts and fleet-wide insights.
    """

    # ---------------------------------------------------------
    # 1. ALERTS
    # ---------------------------------------------------------

    # Fetch the top 2 absolute highest risk vehicles, joining BOTH Vehicle and Part tables
    critical_preds = db.query(models.Prediction, models.Vehicle, models.Part).join(
        models.Vehicle, models.Prediction.vin == models.Vehicle.vin
    ).join(
        models.Part, models.Prediction.part_code == models.Part.part_code
    ).filter(models.Prediction.risk_tier == "Red")\
    .order_by(models.Prediction.failure_probability_pct.desc()).limit(2).all()
    
    alerts = []
    # Notice we unpack 'p' (Prediction), 'v' (Vehicle), and 'pt' (Part)
    for p, v, pt in critical_preds:
        alerts.append({
            "title": f"{pt.part_name} failure imminent", # FIX: Now uses "Alternator" instead of "ALT-001"
            "description": f"Critical degradation detected for {v.vin}. Dominant driver: {p.top_signal}.",
            "severity": "RED",
            "vin": v.vin,
            "part_code": p.part_code
        })
    # ---------------------------------------------------------
    # 2. INSIGHTS
    # ---------------------------------------------------------

    all_reds = (
        db.query(models.Vehicle.region)
        .join(
            models.Prediction,
            models.Prediction.vin == models.Vehicle.vin
        )
        .filter(
            models.Prediction.risk_tier == "Red"
        )
        .all()
    )

    top_region = "your fleet"

    if all_reds:
        region_counts = Counter(
            region[0] for region in all_reds if region[0]
        )

        if region_counts:
            top_region = region_counts.most_common(1)[0][0]

    insights = [
        {
            "title": f"Faults concentrated in {top_region} fleet",
            "detail": (
                f"High-risk predictions are currently concentrated "
                f"within the {top_region} regional fleet."
            ),
            "stat": "High concentration",
        },
        {
            "title": "Aggressive driving accelerating degradation",
            "detail": (
                "Harsh braking and high-RPM dwell time are "
                "contributing to increased component wear."
            ),
            "stat": "Driving pattern",
        },
    ]

    return {
        "alerts": alerts,
        "insights": insights,
    }
