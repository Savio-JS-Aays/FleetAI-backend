import pandas as pd

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app import models
from app.ml.scoring import run_fleet_scoring
from app.ml.correlation import FEATURES, train_part_model
from app.api.rul import calculate_rul_days
from fastapi import HTTPException

router = APIRouter(prefix="/api/predictions", tags=["Predictions"])

@router.post("/score")
def trigger_batch_scoring(db: Session = Depends(get_db)):
    """Runs the ML scoring engine across the whole fleet."""
    processed_count = run_fleet_scoring(db)
    return {"processed_count": processed_count, "status": "success"}

@router.get("/")
def get_ranked_predictions(sort: str = "desc", db: Session = Depends(get_db)):
    """Returns all fleet predictions ranked by failure probability."""

    query = (
        db.query(models.Prediction, models.Vehicle, models.Part)
        .join(
            models.Vehicle,
            models.Prediction.vin == models.Vehicle.vin
        )
        .join(
            models.Part,
            models.Prediction.part_code == models.Part.part_code
        )
    )

    # Sort all VIN + part predictions by probability
    if sort == "desc":
        query = query.order_by(
            models.Prediction.failure_probability_pct.desc(),
            models.Prediction.vin.asc(),
            models.Prediction.part_code.asc(),
        )
    else:
        query = query.order_by(
            models.Prediction.failure_probability_pct.asc(),
            models.Prediction.vin.asc(),
            models.Prediction.part_code.asc(),
        )

    predictions = query.all()

    response = []

    # Return EVERY prediction record.
    # Do NOT collapse multiple parts belonging to the same VIN.
    for p, v, part in predictions:

        # Safely format values coming from the database
        vehicle_name = (
            v.model
            if v.model
            else "Unknown vehicle"
        )

        region = (
            v.region
            if v.region
            else "Unknown region"
        )

        component_name = (
            part.part_name
            if part.part_name
            else p.part_code
        )

        probability = (
            round(float(p.failure_probability_pct), 1)
            if p.failure_probability_pct is not None
            else 0
        )

        rul = (
            p.rul_km
            if p.rul_km is not None
            else 0
        )
        rul_days, _ = calculate_rul_days(p, v)

        risk = (
            p.risk_tier.lower()
            if p.risk_tier
            else "green"
        )

        response.append(
            {
                "vin": v.vin,

                # Vehicle information
                "vehicle": vehicle_name,
                "miles": (
                    f"{v.total_km:,} km"
                    if v.total_km is not None
                    else "—"
                ),
                "fleet": "Fleet Operations",
                "region": region,

                # Prediction information
                "component": component_name,
                "part_code": p.part_code,
                "probability": probability,
                "rul": f"{rul:,} km",
                "predicted_rul_km": rul,
                "predicted_rul_days": rul_days,
                "risk": risk,
                "top_signal": p.top_signal,
            }
        )

    return response

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
        
    selected_signals = [
        r.signal_name for r in active_rules if r.signal_name in FEATURES
    ]
    model = train_part_model(part_code, selected_signals, db)
    if model is None:
        return []
    
    # 2. Get the last 12 weeks of telematics for this VIN, ordered chronologically
    history = db.query(models.Telematics).filter(models.Telematics.vin == vin)\
        .order_by(models.Telematics.week_start_date.desc()).limit(12).all()
        
    history.reverse() # Reverse to go from oldest (12 weeks ago) to newest (today)
    
    # 3. Apply the rule to each week to generate the trend
    trend = []
    for record in history:
        values = pd.DataFrame([{
            signal: getattr(record, signal, 0.0)
            for signal in selected_signals
        }], columns=selected_signals)
        prob_pct = round(
            float(model.predict_proba(values)[0, 1]) * 100,
            2,
        )
        trend.append({
            "week_start_date": record.week_start_date,
            "probability": prob_pct
        })
        
    return trend
@router.get("/{vin}/signal-breakdown")
def get_signal_breakdown(vin: str, part_code: str, db: Session = Depends(get_db)):
    """
    Powers the 'Which signals drive this prediction' bar chart.
    """
    vin = vin.upper()
    part_code = part_code.upper()

    active_rules = db.query(models.RuleConfig).filter(
        models.RuleConfig.part_code == part_code,
        models.RuleConfig.is_included == True
    ).all()
    
    if not active_rules:
        raise HTTPException(status_code=404, detail="No active rules found for this part.")
        
    rule_weights = {r.signal_name: r.correlation_weight for r in active_rules}
    
    # 2. Get the latest week of telematics for this VIN
    latest_telemetry = db.query(models.Telematics).filter(models.Telematics.vin == vin)\
        .order_by(models.Telematics.week_start_date.desc()).first()
        
    if not latest_telemetry:
         raise HTTPException(status_code=404, detail="No telematics found for this VIN.")

    # 3. Calculate each signal's absolute mathematical contribution
    breakdown = []
    total_score = 0.0
    
    # Clean UI labels mapping
    signal_labels = {
        "battery_voltage_sag": "Battery voltage sag",
        "coolant_temp_variance": "Coolant temp variance",
        "oil_pressure_dips": "Oil pressure dips",
        "high_rpm_dwell_time": "High-RPM dwell time",
        "idle_time_pct": "Idle time pct",
        "overload_duty_share": "Overload duty share",
        "harsh_braking_frequency": "Harsh braking frequency",
        "short_trip_ratio": "Short-trip ratio",
        "dtc_recurrence_rate": "DTC recurrence rate"
    }
    
    for signal, weight in rule_weights.items():
        live_value = getattr(latest_telemetry, signal, 0.0)
        contribution = live_value * weight
        total_score += contribution
        
        if contribution > 0:
            breakdown.append({
                "signal_name": signal_labels.get(signal, signal),
                "raw_contribution": contribution
            })
            
    # 4. Normalize the contributions so the bars equal 100% of the prediction
    formatted_breakdown = []
    for item in breakdown:
        pct_share = (item["raw_contribution"] / total_score) * 100 if total_score > 0 else 0
        formatted_breakdown.append({
            "signal_name": item["signal_name"],
            "contribution_pct": round(pct_share, 1)
        })
        
    # Sort highest contribution first
    formatted_breakdown.sort(key=lambda x: x["contribution_pct"], reverse=True)
    
    return formatted_breakdown
