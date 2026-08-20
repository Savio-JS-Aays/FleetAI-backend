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