
from fastapi import Query, APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
import pandas as pd
from app.ml.backtest import calculate_backtest
from app.ml.correlation import calculate_signal_weights
from app.ml.correlation import FEATURES, train_part_model
from app import models, schemas
from pydantic import BaseModel
from typing import List
from datetime import datetime

class BacktestRequest(BaseModel):
    part_code: str
    selected_signals: List[str]

router = APIRouter(prefix="/api/ml", tags=["ML & Rules"])

def run_prediction_engine_for_part(part_code: str, db: Session):
    """Calculates predictions for the entire fleet when a new rule is saved."""
    print(f"--- TRIGGERING PREDICTION ENGINE FOR {part_code} ---")
    
    # 1. Get the active rules for this part
    active_rules = db.query(models.RuleConfig).filter(
        models.RuleConfig.part_code == part_code,
        models.RuleConfig.is_included == True
    ).all()

    if not active_rules:
        print(" -> No active rules found. Skipping engine.")
        return

    # 2. Clear old predictions for this part
    db.query(models.Prediction).filter(models.Prediction.part_code == part_code).delete()

    # 3. Fetch latest telemetry and calculate
    vehicles = db.query(models.Vehicle).all()
    predictions_to_add = []

    for v in vehicles:
        latest_tel = db.query(models.Telematics).filter(
            models.Telematics.vin == v.vin
        ).order_by(models.Telematics.week_start_date.desc()).first()

        if not latest_tel:
            continue

        prob = 0.0
        top_sig = ""
        max_contrib = 0.0

        for rule in active_rules:
            val = getattr(latest_tel, rule.signal_name, 0.0)
            normalized_val = (val / 15.0) if rule.signal_name == "oil_pressure_dips" else val
            
            contribution = normalized_val * rule.correlation_weight
            prob += contribution

            if contribution > max_contrib:
                max_contrib = contribution
                top_sig = rule.signal_name

        prob = min(prob * 100, 99.9)

        if prob > 15.0:
            tier = "Red" if prob >= 70 else ("Amber" if prob >= 40 else "Green")
            rul = max(100, int((100 - prob) * 120))
            
            predictions_to_add.append(models.Prediction(
                vin=v.vin, part_code=part_code, failure_probability_pct=round(prob, 1),
                risk_tier=tier, rul_km=rul, top_signal=top_sig, computed_date=datetime.now()
            ))

    # 4. Save the new predictions
    db.add_all(predictions_to_add)
    db.commit()
    print(f"--- ENGINE COMPLETE: Generated {len(predictions_to_add)} live predictions! ---\n")


@router.get("/correlations")
def get_correlations(
    part_code: str, 
    exclude: str = Query(default=""), 
    db: Session = Depends(get_db)
):
    """
    Dynamically calculates and returns signal correlations for a part.
    Accepts a comma-separated list of signals to exclude from the calculation.
    """
    # 1. Convert the comma-separated string from the URL into a Python list
    # e.g., "battery_voltage_sag,short_trip_ratio" -> ["battery_voltage_sag", "short_trip_ratio"]
    excluded_list = [s.strip() for s in exclude.split(",") if s.strip()] if exclude else []
    
    # 2. Pass the parsed list to your updated calculation function
    return calculate_signal_weights(part_code, db, exclude=excluded_list)

@router.post("/rules")
def save_rule(rule: schemas.RuleCreate, db: Session = Depends(get_db)):
    """Persists a configured rule to the database and fires the prediction engine."""
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
    
    # 3. NOW FIRE THE ENGINE!
    run_prediction_engine_for_part(rule.part_code, db)
    
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

    selected_signals = [
        rule.signal_name for rule in active_rules
        if rule.signal_name in FEATURES
    ]
    model = train_part_model(part_code, selected_signals, db)
    if model is None:
        return []
    rows = db.query(models.Telematics).order_by(
        models.Telematics.week_start_date.desc()
    ).all()
    weekly_scores = {}
    for row in rows:
        values = pd.DataFrame([{
            signal: getattr(row, signal, 0.0)
            for signal in selected_signals
        }], columns=selected_signals)
        probability = float(model.predict_proba(values)[0, 1]) * 100
        weekly_scores.setdefault(row.week_start_date, []).append(probability)

    return [
        {
            "week_start_date": week,
            "probability": round(sum(scores) / len(scores), 2),
        }
        for week, scores in sorted(weekly_scores.items())[-10:]
    ]

@router.post("/backtest")
def backtest_rule(payload: BacktestRequest, db: Session = Depends(get_db)):
    """
    Step 4 of Rule Builder: Backtests the proposed formula against historical data.
    """
    # Route the request directly into your genuine Machine Learning pipeline
    return calculate_backtest(
        part_code=payload.part_code,
        selected_signals=payload.selected_signals,
        db=db
    )