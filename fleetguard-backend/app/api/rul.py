from datetime import date

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app import models
from app.ml.correlation import FEATURES, train_part_model

router = APIRouter(prefix="/api/rul", tags=["Remaining Useful Life"])


def calculate_rul_days(prediction, vehicle) -> tuple[int, float]:
    elapsed_days = max(
        (date.today() - vehicle.registration_date).days,
        1,
    )
    daily_km_usage = max(
        vehicle.total_km / elapsed_days,
        1.0,
    )
    rul_days = (
        int(prediction.rul_km / daily_km_usage)
        if prediction.rul_km > 0
        else 0
    )
    return rul_days, daily_km_usage


def _get_model_confidence_pct(probability_pct: float) -> float:
    """
    Confidence is how far the model's probability sits from the 50/50
    decision boundary, scaled to 0-100. A prediction of 2% or 98% is a
    confident call either way; a prediction near 50% is genuinely
    uncertain. This replaces the old constants (93/88/75, keyed only
    off risk_tier), which ignored the prediction's actual probability
    and were identical for every "Red" part regardless of its data.
    """
    return round(min(100.0, abs(probability_pct - 50.0) * 2), 1)


def _get_degradation_trend_monthly(vin: str, selected_signals: list[str], model, db: Session):
    """
    Computes the actual monthly rate of change in this part's failure
    probability, using the same weekly telematics history and trained
    model as the probability-trend chart (/api/predictions/trend/{vin}).
    Replaces the old constant (-5.9 for Red, -2.1 otherwise), which was
    identical for every part in a risk tier regardless of how that
    specific part was actually trending.

    Returns None (not a fabricated number) if there isn't enough
    telematics history to compute a real slope.
    """
    history = (
        db.query(models.Telematics)
        .filter(models.Telematics.vin == vin)
        .order_by(models.Telematics.week_start_date.desc())
        .limit(12)
        .all()
    )

    if len(history) < 2:
        return None

    history.reverse()  # oldest -> newest

    weekly_probs = []
    for record in history:
        values = pd.DataFrame(
            [{signal: getattr(record, signal, 0.0) for signal in selected_signals}],
            columns=selected_signals,
        )
        prob_pct = float(model.predict_proba(values)[0, 1]) * 100
        weekly_probs.append(prob_pct)

    weeks_elapsed = len(weekly_probs) - 1
    if weeks_elapsed == 0:
        return None

    weekly_rate = (weekly_probs[-1] - weekly_probs[0]) / weeks_elapsed
    monthly_rate = weekly_rate * (365.25 / 12 / 7)  # weeks -> months

    return round(monthly_rate, 2)


@router.get("/fleet")
def get_fleet_rul(db: Session = Depends(get_db)):
    """Return the most urgent predicted RUL and days for every VIN."""

    # Dedupe to each VIN+part's newest prediction *before* picking the
    # most urgent row per VIN. Without this, a VIN's most-urgent row
    # could come from a stale prediction run (a "zombie" record) rather
    # than the latest scoring batch, since the old query scanned every
    # historical Prediction row ever written for that VIN.
    latest_predictions_subq = (
        db.query(func.max(models.Prediction.prediction_id).label("latest_id"))
        .group_by(models.Prediction.vin, models.Prediction.part_code)
        .subquery()
    )

    rows = (
        db.query(models.Prediction, models.Vehicle, models.Part)
        .join(models.Vehicle, models.Prediction.vin == models.Vehicle.vin)
        .join(models.Part, models.Prediction.part_code == models.Part.part_code)
        .join(
            latest_predictions_subq,
            models.Prediction.prediction_id == latest_predictions_subq.c.latest_id,
        )
        .order_by(
            models.Prediction.vin.asc(),
            models.Prediction.rul_km.asc(),
        )
        .all()
    )

    fleet = {}
    for prediction, vehicle, part in rows:
        if vehicle.vin in fleet:
            continue

        rul_days, daily_km_usage = calculate_rul_days(prediction, vehicle)
        fleet[vehicle.vin] = {
            "vin": vehicle.vin,
            "vehicle": vehicle.model,
            "region": vehicle.region,
            "part_code": prediction.part_code,
            "component": part.part_name,
            "predicted_rul_km": int(prediction.rul_km),
            "predicted_rul_days": rul_days,
            "observed_daily_usage_km": round(daily_km_usage, 2),
            "failure_probability_pct": round(
                float(prediction.failure_probability_pct),
                2,
            ),
            "risk_tier": prediction.risk_tier,
        }

    return list(fleet.values())


@router.get("/{vin}/details")
def get_rul_details(vin: str, part_code: str, db: Session = Depends(get_db)):
    """Powers the RUL KPI metrics: KM, Days, Confidence, and Trend."""
    vin = vin.upper()
    part_code = part_code.upper()

    prediction = (
        db.query(models.Prediction)
        .filter(
            models.Prediction.vin == vin,
            models.Prediction.part_code == part_code,
        )
        .order_by(models.Prediction.prediction_id.desc())
        .first()
    )

    if not prediction:
        raise HTTPException(status_code=404, detail="No prediction found.")

    vehicle = db.query(models.Vehicle).filter(
        models.Vehicle.vin == vin
    ).first()
    if not vehicle:
        raise HTTPException(status_code=404, detail="Vehicle not found.")

    rul_days, daily_km_usage = calculate_rul_days(prediction, vehicle)

    probability_pct = float(prediction.failure_probability_pct)
    confidence = _get_model_confidence_pct(probability_pct)

    # Compute a real trend from this part's active rules + telematics
    # history. If either is missing, return None rather than a
    # tier-based placeholder number.
    trend = None
    active_rules = (
        db.query(models.RuleConfig)
        .filter(
            models.RuleConfig.part_code == part_code,
            models.RuleConfig.is_included == True,
        )
        .all()
    )
    selected_signals = [r.signal_name for r in active_rules if r.signal_name in FEATURES]

    if selected_signals:
        model = train_part_model(part_code, selected_signals, db)
        if model is not None:
            trend = _get_degradation_trend_monthly(vin, selected_signals, model, db)

    return {
        "vin": vin,
        "part_code": part_code,
        "predicted_rul_km": int(prediction.rul_km),
        "predicted_rul_days": rul_days,
        "observed_daily_usage_km": daily_km_usage,
        "model_confidence_pct": confidence,
        "degradation_trend_monthly": trend,
    }


@router.get("/{vin}/degradation-curve")
def get_degradation_curve(vin: str, part_code: str, db: Session = Depends(get_db)):
    """Generates the plot coordinates for the Degradation vs Threshold chart."""
    vin = vin.upper()
    part_code = part_code.upper()

    prediction = db.query(models.Prediction).filter(
        models.Prediction.vin == vin,
        models.Prediction.part_code == part_code
    ).order_by(models.Prediction.prediction_id.desc()).first()

    vehicle = db.query(models.Vehicle).filter(models.Vehicle.vin == vin).first()
    part = db.query(models.Part).filter(models.Part.part_code == part_code).first()

    if not prediction or not vehicle or not part:
        raise HTTPException(status_code=404, detail="Required data missing.")

    # Calculate actual mileage on this specific part
    part_mileage = vehicle.total_km % part.design_life_km

    current_health = 100.0 - prediction.failure_probability_pct
    failure_threshold = 30.0

    # Calculate the future kilometer mark where health crosses 30
    failure_km_mark = part_mileage + prediction.rul_km

    # Prevent the part from "healing" by capping the future health
    projected_health = min(current_health, failure_threshold)
    post_failure_health = max(0.0, projected_health - 15.0)

    # Generate the charting coordinates
    curve = []

    # 1. Simulate Historical Wear (10 data points for a smooth swoop)
    history_steps = 10
    step_size = part_mileage / history_steps

    for i in range(history_steps + 1):
        km = int(i * step_size)
        ratio = km / max(1, part_mileage)

        point_health = 100.0 - ((100.0 - current_health) * (ratio ** 3))
        curve.append({
            "km": km,
            "health_index": round(point_health, 2),
            "is_projection": False
        })

    # 2. Simulate Future Projection (5 data points for a smooth dashed drop)
    if failure_km_mark > part_mileage:
        future_distance = failure_km_mark - part_mileage
        future_steps = 5
        future_step_size = future_distance / future_steps

        for i in range(1, future_steps + 1):
            km = int(part_mileage + (i * future_step_size))
            ratio = i / future_steps

            drop_amount = current_health - projected_health
            point_health = current_health - (drop_amount * (ratio ** 1.5))

            curve.append({
                "km": km,
                "health_index": round(point_health, 2),
                "is_projection": True
            })

    # 3. Add the final post-failure resting point
    curve.append({
        "km": int(failure_km_mark + 3000),
        "health_index": round(post_failure_health, 2),
        "is_projection": True
    })

    return {
        "failure_threshold_index": failure_threshold,
        "current_km": part_mileage,
        "curve_data": curve
    }