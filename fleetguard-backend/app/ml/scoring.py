from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date
from app import models

def run_fleet_scoring(db: Session):
    """
    Calculates failure probability and RUL for the entire fleet (P0 Requirement).
    """
    # 1. Fetch active rules
    active_rules = db.query(models.RuleConfig).filter(models.RuleConfig.is_included == True).all()
    rules_by_part = {}
    for r in active_rules:
        if r.part_code not in rules_by_part:
            rules_by_part[r.part_code] = {}
        rules_by_part[r.part_code][r.signal_name] = r.correlation_weight

    if not rules_by_part:
        return 0

    # 2. Fetch reference dictionaries for fast O(1) lookups
    vehicles = {v.vin: v for v in db.query(models.Vehicle).all()}
    parts = {p.part_code: p for p in db.query(models.Part).all()}

    # 3. Get the most recent telematics record for every vehicle
    subq = db.query(
        models.Telematics.vin, 
        func.max(models.Telematics.week_start_date).label('max_date')
    ).group_by(models.Telematics.vin).subquery()

    latest_telematics = db.query(models.Telematics).join(
        subq, 
        (models.Telematics.vin == subq.c.vin) & (models.Telematics.week_start_date == subq.c.max_date)
    ).all()

    # Clear old predictions
    db.query(models.Prediction).delete()
    predictions = []
    
    # 4. Apply Formulas
    for record in latest_telematics:
        for part_code, rule_weights in rules_by_part.items():
            
            # --- Probability Calculation ---
            total_score = 0.0
            signal_contributions = {}
            
            for signal, weight in rule_weights.items():
                live_value = getattr(record, signal, 0.0)
                contribution = live_value * weight
                total_score += contribution
                signal_contributions[signal] = contribution
            
            probability_pct = min(round(total_score * 100, 2), 100.0)
            
            if probability_pct >= 70.0:
                tier = "Red"
            elif probability_pct >= 40.0:
                tier = "Amber"
            else:
                tier = "Green"
                
            top_signal = max(signal_contributions, key=signal_contributions.get) if signal_contributions else "Unknown"

            # --- Remaining Useful Life (RUL) Calculation ---
            v_data = vehicles[record.vin]
            p_data = parts[part_code]
            
            # Extract stress factors to accelerate wear (alpha)
            # Normalizing these to create a multiplier between 1.0 and ~2.5
            stress_factors = (
                getattr(record, 'overload_duty_share', 0.0) +
                getattr(record, 'harsh_braking_frequency', 0.0) +
                getattr(record, 'coolant_temp_variance', 0.0)
            )
            alpha = 1.0 + stress_factors
            
            p_fail = probability_pct / 100.0
            
            # RUL Formula: (Design Life - Current Odometer) / (1 + (alpha * p_fail))
            current_part_km = v_data.total_km % p_data.design_life_km
            base_remaining_km = p_data.design_life_km - current_part_km
            denominator = 1.0 + (alpha * p_fail)
            raw_rul = base_remaining_km / denominator
            
            # Zero-Bound Handling (P0 Requirement): RUL can never be negative
            final_rul = max(0, int(raw_rul))

            predictions.append(models.Prediction(
                vin=record.vin,
                part_code=part_code,
                failure_probability_pct=probability_pct,
                risk_tier=tier,
                top_signal=top_signal,
                rul_km=final_rul,
                computed_date=date.today()
            ))

    db.add_all(predictions)
    db.commit()
    
    return len(predictions)