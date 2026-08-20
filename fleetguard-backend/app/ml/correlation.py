import pandas as pd
import numpy as np
from sklearn.linear_model import LogisticRegression
from sqlalchemy.orm import Session
from app.models import Telematics, JobCard

def calculate_signal_weights(part_code: str, db: Session) -> list:
    """
    Calculates normalized feature importance weights for a given part 
    using Logistic Regression.
    """
    # 1. Fetch raw data using pandas reading from SQLAlchemy
    # We load all telematics and ONLY the job cards for the requested part
    telematics_query = db.query(Telematics).statement
    df = pd.read_sql(telematics_query, db.bind)
    
    jc_query = db.query(JobCard).filter(JobCard.part_code == part_code).statement
    df_jc = pd.read_sql(jc_query, db.bind)
    
    # 2. Merge Data
    df['week_start_date'] = pd.to_datetime(df['week_start_date'])
    df_jc['failure_date'] = pd.to_datetime(df_jc['failure_date'])
    
    merged_df = df.merge(df_jc[['vin', 'failure_date']], on='vin', how='left')
    
    # 3. Data Leakage Prevention (P0 Requirement)
    # Drop any telematics rows that occur strictly AFTER the failure date.
    valid_rows = (merged_df['failure_date'].isna()) | (merged_df['week_start_date'] <= merged_df['failure_date'])
    clean_df = merged_df[valid_rows].copy()
    
    # 4. Label Generation
    # Label 1 (Pre-failure) if within 28 days (4 weeks) prior to failure. Otherwise 0.
    clean_df['days_to_fail'] = (clean_df['failure_date'] - clean_df['week_start_date']).dt.days
    clean_df['label'] = np.where(
        (clean_df['days_to_fail'] >= 0) & (clean_df['days_to_fail'] <= 28), 1, 0
    )
    
    # 5. Model Training
    features = [
        'coolant_temp_variance', 'oil_pressure_dips', 'battery_voltage_sag',
        'dtc_recurrence_rate', 'harsh_braking_frequency', 'overload_duty_share',
        'high_rpm_dwell_time', 'short_trip_ratio', 'idle_time_pct'
    ]
    
    X = clean_df[features]
    y = clean_df['label']
    
    # Using l2 penalty as required
    model = LogisticRegression(max_iter=1000, random_state=42)
    model.fit(X, y)
    
    # 6. Weight Normalization
    # Extract absolute coefficients (C_i = |w_i|)
    coefs = np.abs(model.coef_[0])
    total_weight = np.sum(coefs)
    
    # Normalize weights so they sum to 1.0 (100%)
    normalized_weights = coefs / total_weight
    
    # 7. Format Response
    results = []
    for feature, weight in zip(features, normalized_weights):
        results.append({
            "signal": feature,
            "weight": float(weight)
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