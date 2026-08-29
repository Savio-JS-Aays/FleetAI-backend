from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.ml.backtest import calculate_backtest
from app.ml.correlation import calculate_signal_weights
from app import models, schemas
from pydantic import BaseModel
from typing import List

class BacktestRequest(BaseModel):
    part_code: str
    selected_signals: List[str]


router = APIRouter(prefix="/api/ml", tags=["ML & Rules"])

@router.get("/correlations")
def get_correlations(part_code: str, db: Session = Depends(get_db)):
    """Dynamically calculates and returns signal correlations for a part."""
    # This executes the ML logic we just tested
    return calculate_signal_weights(part_code, db)

@router.post("/rules")
def save_rule(rule: schemas.RuleCreate, db: Session = Depends(get_db)):
    """Persists a configured rule to the database (P0 Requirement)."""
    # 1. Delete any existing rule for this part to overwrite it
    db.query(models.RuleConfig).filter(models.RuleConfig.part_code == rule.part_code).delete()
    
    # 2. Insert the new configuration
    configs = []
    for sig in rule.signals:
        configs.append(models.RuleConfig(
            part_code=rule.part_code,
            signal_name=sig.signal,
            correlation_weight=sig.weight,
            is_included=sig.is_included
        ))
    
    db.add_all(configs)
    db.commit()
    
    return {"status": "saved"}

@router.get("/rules")
def get_saved_rule(part_code: str, db: Session = Depends(get_db)):
    """Retrieves the currently active rule for a part."""
    rules = db.query(models.RuleConfig).filter(models.RuleConfig.part_code == part_code).all()
    return rules

@router.get("/rule-trend")
def get_rule_trend(part_code: str, db: Session = Depends(get_db)):
    """Return the last ten fleet-average scores for the active part rule."""
    active_rules = db.query(models.RuleConfig).filter(
        models.RuleConfig.part_code == part_code.upper(),
        models.RuleConfig.is_included == True,
    ).all()
    if not active_rules:
        return []

    weights = {rule.signal_name: rule.correlation_weight for rule in active_rules}
    rows = db.query(models.Telematics).order_by(
        models.Telematics.week_start_date.desc()
    ).all()
    weekly_scores = {}
    for row in rows:
        score = sum(getattr(row, signal, 0.0) * weight for signal, weight in weights.items())
        weekly_scores.setdefault(row.week_start_date, []).append(min(score * 100, 100.0))

    return [
        {
            "week_start_date": week,
            "probability": round(sum(scores) / len(scores), 2),
        }
        for week, scores in sorted(weekly_scores.items())[-10:]
    ]

@router.post("/backtest")
def backtest_rule(payload: BacktestRequest, db: Session = Depends(get_db)):
    """Evaluate a selected-signal rule against historical fleet outcomes."""
    return calculate_backtest(payload.part_code, payload.selected_signals, db)