from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import date
from app import models

def run_fleet_scoring(db: Session):
    """
    Calculates the failure probability for the entire fleet based on active rules (P0 Requirement).
    """
    # 1. Get all unique parts that have an active rule configured
    active_rules = db.query(models.RuleConfig).filter(models.RuleConfig.is_included == True).all()
    
    # Group rules by part_code
    rules_by_part = {}
    for r in active_rules:
        if r.part_code not in rules_by_part:
            rules_by_part[r.part_code] = {}
        rules_by_part[r.part_code][r.signal_name] = r.correlation_weight

    if not rules_by_part:
        return 0 # No rules saved yet

    # 2. Get the most recent telematics record for every vehicle
    # Subquery to find the max date per VIN
    subq = db.query(
        models.Telematics.vin, 
        func.max(models.Telematics.week_start_date).label('max_date')
    ).group_by(models.Telematics.vin).subquery()

    latest_telematics = db.query(models.Telematics).join(
        subq, 
        (models.Telematics.vin == subq.c.vin) & (models.Telematics.week_start_date == subq.c.max_date)
    ).all()

    # Clear old predictions to calculate fresh ones
    db.query(models.Prediction).delete()

    predictions = []
    
    # 3. Apply the formula to every vehicle
    for record in latest_telematics:
        for part_code, rule_weights in rules_by_part.items():
            
            total_score = 0.0
            signal_contributions = {}
            
            # Multiply live data by the saved weights
            for signal, weight in rule_weights.items():
                # Get the value dynamically using getattr
                live_value = getattr(record, signal, 0.0)
                contribution = live_value * weight
                
                total_score += contribution
                signal_contributions[signal] = contribution
            
            # Convert to a clean percentage (0 to 100)
            probability_pct = min(round(total_score * 100, 2), 100.0)
            
            # Assign Risk Tier
            if probability_pct >= 70.0:
                tier = "Red"
            elif probability_pct >= 40.0:
                tier = "Amber"
            else:
                tier = "Green"
                
            # Find the top contributing signal (the one with the highest math contribution)
            top_signal = max(signal_contributions, key=signal_contributions.get) if signal_contributions else "Unknown"

            # Create the prediction record
            predictions.append(models.Prediction(
                vin=record.vin,
                part_code=part_code,
                failure_probability_pct=probability_pct,
                risk_tier=tier,
                top_signal=top_signal, # Added this!
                rul_km=0, 
                computed_date=date.today()
            ))

    # 4. Save to the database
    db.add_all(predictions)
    db.commit()
    
    return len(predictions)