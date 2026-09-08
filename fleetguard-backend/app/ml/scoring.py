from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date
import pandas as pd
from app import models
from app.ml.correlation import FEATURES, train_part_model


def run_fleet_scoring(db: Session):
    """
    Calculates failure probability and RUL for the entire fleet (P0 Requirement).
    """

    # 1. Fetch active rules
    active_rules = (
        db.query(models.RuleConfig)
        .filter(models.RuleConfig.is_included == True)
        .all()
    )

    rules_by_part = {}

    for r in active_rules:
        if r.part_code not in rules_by_part:
            rules_by_part[r.part_code] = {}

        rules_by_part[r.part_code][r.signal_name] = r.correlation_weight

    # DEBUG: Show which parts and how many rules are being used
    print("\n=== SCORING RULES BY PART ===")
    for part_code, rules in rules_by_part.items():
        print(f"{part_code}: {len(rules)} rules")

    if not rules_by_part:
        return 0

    models_by_part = {
        part_code: train_part_model(
            part_code,
            [signal for signal in rule_weights if signal in FEATURES],
            db,
        )
        for part_code, rule_weights in rules_by_part.items()
    }

    # 2. Fetch reference dictionaries for fast O(1) lookups
    vehicles = {
        v.vin: v
        for v in db.query(models.Vehicle).all()
    }

    parts = {
        p.part_code: p
        for p in db.query(models.Part).all()
    }

    # 3. Get the most recent telematics record for every vehicle
    subq = (
        db.query(
            models.Telematics.vin,
            func.max(models.Telematics.week_start_date).label("max_date")
        )
        .group_by(models.Telematics.vin)
        .subquery()
    )

    latest_telematics = (
        db.query(models.Telematics)
        .join(
            subq,
            (models.Telematics.vin == subq.c.vin)
            & (
                models.Telematics.week_start_date
                == subq.c.max_date
            )
        )
        .all()
    )

    # Clear old predictions
    db.query(models.Prediction).delete()

    predictions = []

    # DEBUG: Count how many predictions are being generated per part
    part_prediction_counts = {}

    # 4. Apply formulas
    for record in latest_telematics:

        for part_code, rule_weights in rules_by_part.items():

            # DEBUG: Count this VIN + part combination
            part_prediction_counts[part_code] = (
                part_prediction_counts.get(part_code, 0) + 1
            )

            # --- Probability Calculation ---
            selected_signals = [
                signal for signal in rule_weights if signal in FEATURES
            ]
            model = models_by_part[part_code]
            signal_contributions = {}

            if model is None:
                probability_pct = 0.0
            else:
                values = {
                    signal: getattr(record, signal, 0.0)
                    for signal in selected_signals
                }
                feature_frame = pd.DataFrame(
                    [values],
                    columns=selected_signals,
                )
                probability_pct = round(
                    float(model.predict_proba(feature_frame)[0, 1]) * 100,
                    2,
                )
                scaled_values = model[0].transform(feature_frame)[0]
                coefficients = model[-1].coef_[0]
                signal_contributions = {
                    signal: float(value * coefficient)
                    for signal, value, coefficient in zip(
                        selected_signals, scaled_values, coefficients
                    )
                }

            # --- Risk Tier ---
            if probability_pct >= 70.0:
                tier = "Red"
            elif probability_pct >= 40.0:
                tier = "Amber"
            else:
                tier = "Green"

            # --- Top Signal ---
            top_signal = (
                max(
                    signal_contributions,
                    key=signal_contributions.get
                )
                if signal_contributions
                else "Unknown"
            )

            # --- Remaining Useful Life (RUL) Calculation ---
            v_data = vehicles[record.vin]
            p_data = parts[part_code]

            # Extract stress factors to accelerate wear
            stress_factors = (
                getattr(
                    record,
                    "overload_duty_share",
                    0.0
                )
                +
                getattr(
                    record,
                    "harsh_braking_frequency",
                    0.0
                )
                +
                getattr(
                    record,
                    "coolant_temp_variance",
                    0.0
                )
            )

            alpha = 1.0 + stress_factors

            p_fail = probability_pct / 100.0
            current_part_km = v_data.total_km % p_data.design_life_km
            base_remaining_km = p_data.design_life_km - current_part_km
            # RUL Formula:
            # (Design Life - Current Odometer)
            # / (1 + (alpha * p_fail))

            # ✨ THE FIX: removed the duplicate, unconditional
            # `final_rul = max(0, int(raw_rul))` that used to sit here.
            # It ran on every iteration regardless of branch, so a
            # Red-tier part (probability_pct >= 70.0) that correctly
            # got final_rul = 0 above was then immediately overwritten
            # with whatever `raw_rul` happened to be left over from a
            # *previous* VIN/part in this loop (Python for-loops don't
            # reset local variables between iterations) — producing
            # exactly the "100% failure probability but a long RUL"
            # symptom, non-deterministically, depending on iteration
            # order. Each branch now fully owns its own final_rul with
            # no code after the if/else able to clobber it.
            if probability_pct >= 70.0:
                final_rul = 0
            else:
                raw_rul = (base_remaining_km * (1.0 - p_fail)) / alpha
                final_rul = max(0, int(raw_rul))

            # --- Create Prediction ---
            predictions.append(
                models.Prediction(
                    vin=record.vin,
                    part_code=part_code,
                    failure_probability_pct=probability_pct,
                    risk_tier=tier,
                    top_signal=top_signal,
                    rul_km=final_rul,
                    computed_date=date.today()
                )
            )

    # Save predictions
    db.add_all(predictions)
    db.commit()

    # DEBUG: Show final prediction counts
    print("\n=== PREDICTIONS GENERATED ===")

    for part_code, count in sorted(
        part_prediction_counts.items()
    ):
        print(
            f"{part_code}: {count} predictions"
        )

    print(
        f"\nTOTAL PREDICTIONS: {len(predictions)}"
    )

    return len(predictions)