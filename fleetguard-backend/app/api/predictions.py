from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from app.ml.scoring import run_fleet_scoring

router = APIRouter(prefix="/api/predictions", tags=["Predictions"])

@router.post("/score")
def trigger_batch_scoring(db: Session = Depends(get_db)):
    """Runs the ML scoring engine across the whole fleet."""
    processed_count = run_fleet_scoring(db)
    return {"processed_count": processed_count, "status": "success"}

@router.get("/")
def get_ranked_predictions(sort: str = "desc", db: Session = Depends(get_db)):
    """Returns the fleet ranked by failure probability (P0 Requirement)."""
    query = db.query(models.Prediction)
    
    if sort == "desc":
        query = query.order_by(models.Prediction.failure_probability_pct.desc())
        
    predictions = query.all()
    
    # Format the response for the frontend
    results = []
    for p in predictions:
        results.append({
            "vin": p.vin,
            "part_code": p.part_code,
            "probability": p.failure_probability_pct,
            "tier": p.risk_tier,
            "top_signal": p.top_signal,
            "rul": p.rul_km
        })
    return results

@router.get("/trend/{vin}")
def get_probability_trend(vin: str, part_code: str, db: Session = Depends(get_db)):
    """Calculates the 12-week probability trend for a specific vehicle (Requirement 4.3)."""
    vin = vin.upper()
    
    # 1. Get the active rule for this part
    active_rules = db.query(models.RuleConfig).filter(
        models.RuleConfig.part_code == part_code, 
        models.RuleConfig.is_included == True
    ).all()
    
    if not active_rules:
        return []
        
    rule_weights = {r.signal_name: r.correlation_weight for r in active_rules}
    
    # 2. Get the last 12 weeks of telematics for this VIN, ordered chronologically
    history = db.query(models.Telematics).filter(models.Telematics.vin == vin)\
        .order_by(models.Telematics.week_start_date.desc()).limit(12).all()
        
    history.reverse() # Reverse to go from oldest (12 weeks ago) to newest (today)
    
    # 3. Apply the rule to each week to generate the trend
    trend = []
    for record in history:
        total_score = 0.0
        for signal, weight in rule_weights.items():
            live_value = getattr(record, signal, 0.0)
            total_score += (live_value * weight)
            
        prob_pct = min(round(total_score * 100, 2), 100.0)
        trend.append({
            "week_start_date": record.week_start_date,
            "probability": prob_pct
        })
        
    return trend