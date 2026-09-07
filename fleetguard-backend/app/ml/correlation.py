import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sqlalchemy.orm import Session
from app import models


FEATURES = (
    "coolant_temp_variance", "oil_pressure_dips", "battery_voltage_sag",
    "dtc_recurrence_rate", "harsh_braking_frequency", "overload_duty_share",
    "high_rpm_dwell_time", "short_trip_ratio", "idle_time_pct",
)


def _load_labeled_history(part_code: str, db: Session) -> pd.DataFrame:
    telematics = pd.read_sql(db.query(models.Telematics).statement, db.bind)
    failures = db.query(models.JobCard).filter(
        models.JobCard.part_code == part_code
    ).all()
    if telematics.empty or not failures:
        return pd.DataFrame()

    telematics["week_start_date"] = pd.to_datetime(telematics["week_start_date"])
    failure_dates = {}
    for failure in failures:
        failure_dates.setdefault(failure.vin, []).append(
            pd.Timestamp(failure.failure_date)
        )

    def next_failure(row):
        future_dates = [
            failure_date for failure_date in failure_dates.get(row.vin, [])
            if failure_date >= row.week_start_date
        ]
        return min(future_dates) if future_dates else pd.NaT

    telematics["failure_date"] = telematics.apply(next_failure, axis=1)
    has_failure_vin = telematics["vin"].isin(failure_dates)
    telematics = telematics[
        telematics["failure_date"].notna() | ~has_failure_vin
    ].copy()
    days_to_fail = (
        telematics["failure_date"] - telematics["week_start_date"]
    ).dt.days
    telematics["label"] = days_to_fail.between(0, 28).astype(int)
    for feature in FEATURES:
        telematics[feature] = pd.to_numeric(telematics[feature], errors="coerce")
    return telematics.dropna(subset=list(FEATURES))


def train_part_model(part_code: str, selected_signals: list[str], db: Session):
    """Train the production model using the same labeled history as backtests."""
    signals = list(dict.fromkeys(selected_signals))
    if not signals or any(signal not in FEATURES for signal in signals):
        return None
    history = _load_labeled_history(part_code.strip().upper(), db)
    if history.empty or history["label"].nunique() < 2:
        return None
    model = make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=2000, random_state=42, C=1.0),
    )
    model.fit(history[signals], history["label"])
    return model

def calculate_signal_weights(part_code: str, db: Session, exclude: list = None) -> list:
    """
    Calculates normalized feature importance weights for a given part 
    using Logistic Regression. Dynamically recalculates if signals are excluded.
    """
    if exclude is None:
        exclude = []
        
    # 1. Filter out the excluded features before passing to the model
    active_features = [f for f in FEATURES if f not in exclude]
    
    # If all features are somehow excluded, return an empty list safely
    if not active_features:
        return []

    # 2. Train the model ONLY on the active features
    model = train_part_model(part_code, active_features, db)
    if model is None:
        return []
        
    coefs = np.abs(model[-1].coef_[0])
    total_weight = np.sum(coefs)
    if total_weight == 0:
        return []

    # Normalize weights so they sum to 1.0 (100%)
    normalized_weights = coefs / total_weight
    
    # 3. Format Response
    results = []
    for feature, weight in zip(active_features, normalized_weights):
        results.append({
            "signal": feature,
            # Rounding to 3 decimal places here (e.g., 0.289). 
            # When your React frontend multiplies it by 100, it becomes a clean 28.9%
            "weight": round(float(weight), 3) 
        })
        
    # Sort descending by weight
    return sorted(results, key=lambda x: x['weight'], reverse=True)

# --- Quick Local Verification Block ---
if __name__ == "__main__":
    from app.database import SessionLocal
    
    db = SessionLocal()
    try:
        print("Testing ML Correlation Engine for Alternator (ALT-001)...")
        results = calculate_signal_weights("ALT-001", db)
        
        print("\nDiscovered Signal Weights:")
        for r in results:
            print(f"- {r['signal']}: {r['weight']:.2%}")
    finally:
        db.close()