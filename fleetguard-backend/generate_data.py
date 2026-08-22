import random
import numpy as np
from datetime import date, timedelta
from app.database import SessionLocal, engine
from app import models

# P0 Requirement: Fixed random seed for reproducible datasets
RANDOM_SEED = 42
NUM_VEHICLES = 300

random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)

def generate_parts(db):
    print("Generating Parts...")
    parts = [
        models.Part(part_code="ALT-001", part_name="Alternator", category="Electrical", design_life_km=300000),
        models.Part(part_code="WP-002", part_name="Water Pump", category="Cooling", design_life_km=250000),
        models.Part(part_code="TC-003", part_name="Turbocharger", category="Engine", design_life_km=400000),
    ]
    db.query(models.Part).delete() 
    db.add_all(parts)
    db.commit()
    print(f"-> Created {len(parts)} parts.")
    return parts

def generate_vehicles(db):
    print(f"Generating {NUM_VEHICLES} Vehicles...")
    models_list = ["Long-Haul Tractor", "Rigid Haulage", "Urban Delivery"]
    regions = ["North", "South", "East", "West"]
    db.query(models.Vehicle).delete()
    
    vehicles = []
    for i in range(1, NUM_VEHICLES + 1):
        vin = f"VIN{str(i).zfill(6)}"
        reg_days_ago = random.randint(365, 365 * 5)
        reg_date = date.today() - timedelta(days=reg_days_ago)
        total_km = int((reg_days_ago / 365.0) * random.uniform(80000, 120000))
        
        vehicles.append(models.Vehicle(
            vin=vin, model=random.choice(models_list), region=random.choice(regions),
            registration_date=reg_date, total_km=total_km
        ))
        
    db.add_all(vehicles)
    db.commit()
    print(f"-> Created {len(vehicles)} vehicles.")
    return vehicles

def generate_job_cards(db, vehicles, parts):
    print("Generating Failure History (Job Cards)...")
    db.query(models.JobCard).delete()
    
    job_cards = []
    # Generate ~200 historical failures
    failing_vehicles = random.sample(vehicles, 200)
    
    for i, v in enumerate(failing_vehicles):
        part = random.choice(parts)
        days_ago = random.randint(30, 360)
        fail_date = date.today() - timedelta(days=days_ago)
        
        # P0 Validation: Odometer at failure must be logically lower than current total_km
        odom = int(v.total_km * (1.0 - (days_ago / (5 * 365.0))))
        
        job_cards.append(models.JobCard(
            job_card_id=f"JC{str(i+1).zfill(5)}", vin=v.vin, part_code=part.part_code,
            failure_date=fail_date, odometer_at_failure=odom, replaced=True
        ))
    
    db.add_all(job_cards)
    db.commit()
    print(f"-> Created {len(job_cards)} job cards.")
    return job_cards

def generate_telematics(db, vehicles, job_cards):
    print("Generating 52 Weeks of Telematics with Intentional Signals...")
    db.query(models.Telematics).delete()
    
    # Fast lookup for failures by VIN
    failure_map = {}
    for jc in job_cards:
        if jc.vin not in failure_map:
            failure_map[jc.vin] = []
        failure_map[jc.vin].append(jc)
        
    # Select 15 specific vehicles to experience "Imminent Failures" this week
    imminent_vins = [v.vin for v in vehicles[:15]]
        
    telematics_records = []
    today = date.today()
    
    for v in vehicles:
        v_failures = failure_map.get(v.vin, [])
        is_imminent = v.vin in imminent_vins
        
        for week_offset in range(52):
            week_date = today - timedelta(days=(week_offset * 7))
            
            # 1. Base Normal Signals (Healthy)
            coolant = np.clip(np.random.normal(0.2, 0.05), 0, 1)
            oil_dips = max(0, int(np.random.normal(1, 1)))
            voltage_sag = np.clip(np.random.normal(0.1, 0.05), 0, 1)
            dtc = np.clip(np.random.normal(0.05, 0.02), 0, 1)
            braking = np.clip(np.random.normal(0.15, 0.05), 0, 1)
            overload = np.clip(np.random.normal(0.1, 0.1), 0, 1)
            rpm_dwell = np.clip(np.random.normal(0.2, 0.05), 0, 1)
            short_trip = np.clip(np.random.normal(0.3, 0.1), 0, 1)
            idle = np.clip(np.random.normal(0.15, 0.05), 0, 1)
            
            # 2. Historical Failure Injection (Past)
            for jc in v_failures:
                days_until_failure = (jc.failure_date - week_date).days
                if 14 <= days_until_failure <= 28:
                    if jc.part_code == "ALT-001": 
                        voltage_sag = np.clip(np.random.normal(0.85, 0.1), 0, 1)
                        coolant = np.clip(np.random.normal(0.80, 0.1), 0, 1)
                    elif jc.part_code == "WP-002": 
                        coolant = np.clip(np.random.normal(0.90, 0.05), 0, 1)
                        idle = np.clip(np.random.normal(0.70, 0.1), 0, 1)
                    elif jc.part_code == "TC-003": 
                        rpm_dwell = np.clip(np.random.normal(0.80, 0.1), 0, 1)
                        oil_dips = max(5, int(np.random.normal(15, 3)))
                        
            # 3. Imminent Failure Injection (Current Week)
            # This ensures we have Red-tier vehicles for the dashboard right now
            if is_imminent and week_offset <= 1:
                voltage_sag = np.clip(np.random.normal(0.95, 0.05), 0, 1)
                coolant = np.clip(np.random.normal(0.90, 0.05), 0, 1)
                        
            telematics_records.append(models.Telematics(
                vin=v.vin, week_start_date=week_date, coolant_temp_variance=float(coolant),
                oil_pressure_dips=int(oil_dips), battery_voltage_sag=float(voltage_sag),
                dtc_recurrence_rate=float(dtc), harsh_braking_frequency=float(braking),
                overload_duty_share=float(overload), high_rpm_dwell_time=float(rpm_dwell),
                short_trip_ratio=float(short_trip), idle_time_pct=float(idle)
            ))
            
        if len(telematics_records) > 5000:
            db.add_all(telematics_records)
            db.commit()
            telematics_records = []
            
    if telematics_records:
        db.add_all(telematics_records)
        db.commit()
        
    print("-> Generated 15,600 telematics records successfully.")

def main():
    models.Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        parts = generate_parts(db)
        vehicles = generate_vehicles(db)
        job_cards = generate_job_cards(db, vehicles, parts)
        generate_telematics(db, vehicles, job_cards)
        print("\nSuccess: Fully synthetic dataset injected and ready for ML!")
    finally:
        db.close()

if __name__ == "__main__":
    main()