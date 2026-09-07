import random
import numpy as np
from datetime import date, timedelta
from app.database import SessionLocal, engine
from app import models
import math

# Fixed random seed for reproducible datasets
RANDOM_SEED = 42
NUM_VEHICLES = 500

random.seed(RANDOM_SEED)
np.random.seed(RANDOM_SEED)

# 1. Real-world mechanical failure profiles mapped strictly to your 9 DB columns
FAILURE_PROFILES = {
    "ALT-001": { # Alternator
        "root": ["short_trip_ratio"], 
        "early": ["high_rpm_dwell_time"], 
        "critical": ["battery_voltage_sag"]
    },
    "WP-002": { # Water Pump
        "root": ["idle_time_pct"], 
        "early": ["coolant_temp_variance"], 
        "critical": ["dtc_recurrence_rate"]
    },
    "TC-003": { # Turbocharger
        "root": ["overload_duty_share"], 
        "early": ["high_rpm_dwell_time"], 
        "critical": ["oil_pressure_dips"]
    },
    "BP-004": { # Brake Pads
        "root": ["short_trip_ratio"], 
        "early": ["harsh_braking_frequency"], 
        "critical": ["dtc_recurrence_rate"]
    },
    "GB-005": { # Gearbox
        "root": ["overload_duty_share"], 
        "early": ["harsh_braking_frequency", "idle_time_pct"], 
        "critical": ["dtc_recurrence_rate"]
    }
}

def generate_parts(db):
    print("Generating Parts...")
    parts = [
        models.Part(part_code="ALT-001", part_name="Alternator", category="Electrical", design_life_km=300000),
        models.Part(part_code="WP-002", part_name="Water Pump", category="Cooling", design_life_km=250000),
        models.Part(part_code="TC-003", part_name="Turbocharger", category="Engine", design_life_km=400000),
        models.Part(part_code="BP-004", part_name="Brake Pads", category="Braking", design_life_km=100000),
        models.Part(part_code="GB-005", part_name="Gearbox", category="Transmission", design_life_km=500000),
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
    # Generate ~250 historical failures
    failing_vehicles = random.sample(vehicles, 250)
    
    for i, v in enumerate(failing_vehicles):
        part = random.choice(parts)
        days_ago = random.randint(30, 360)
        fail_date = date.today() - timedelta(days=days_ago)
        
        # Odometer at failure must be logically lower than current total_km
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
    print("Generating 52 Weeks of Telematics with Tiered Degradation...")
    db.query(models.Telematics).delete()
    
    failure_map = {}
    for jc in job_cards:
        if jc.vin not in failure_map:
            failure_map[jc.vin] = []
        failure_map[jc.vin].append(jc)
        
    # Assign ~50 vehicles to have an active, ongoing degradation right now
    imminent_vins = {v.vin: random.choice(["ALT-001", "WP-002", "TC-003", "BP-004", "GB-005"]) for v in vehicles[:50]}
        
    telematics_records = []
    today = date.today()
    
    for v in vehicles:
        v_failures = failure_map.get(v.vin, [])
        active_failing_part = imminent_vins.get(v.vin)
        
        for week_offset in range(52):
            week_date = today - timedelta(days=(week_offset * 7))
            
            # Base Normal Signals (Healthy Dictionary)
            signals = {
                "coolant_temp_variance": float(np.clip(np.random.normal(0.2, 0.05), 0, 1)),
                "oil_pressure_dips": max(0, int(np.random.normal(1, 1))),
                "battery_voltage_sag": float(np.clip(np.random.normal(0.1, 0.05), 0, 1)),
                "dtc_recurrence_rate": float(np.clip(np.random.normal(0.05, 0.02), 0, 1)),
                "harsh_braking_frequency": float(np.clip(np.random.normal(0.15, 0.05), 0, 1)),
                "overload_duty_share": float(np.clip(np.random.normal(0.1, 0.1), 0, 1)),
                "high_rpm_dwell_time": float(np.clip(np.random.normal(0.2, 0.05), 0, 1)),
                "short_trip_ratio": float(np.clip(np.random.normal(0.3, 0.1), 0, 1)),
                "idle_time_pct": float(np.clip(np.random.normal(0.15, 0.05), 0, 1))
            }
            
            # Helper to mathematically compound signals based on distance to failure
            def apply_tiered_degradation(part_code, weeks_until_failure):
                profile = FAILURE_PROFILES.get(part_code, {})
                
                # Tier 1: Root Causes (Chronically 30-50% higher across all 52 weeks)
                for sig in profile.get("root", []):
                    if isinstance(signals[sig], int):
                        signals[sig] += int(signals[sig] * random.uniform(0.3, 0.5))
                    else:
                        signals[sig] = min(1.0, signals[sig] * random.uniform(1.3, 1.5))
                        
                # Tier 2: Early Warnings (Gradual linear climb starting 15 weeks out)
                if weeks_until_failure <= 15:
                    multiplier = 1 + ((15 - weeks_until_failure) * 0.05)
                    for sig in profile.get("early", []):
                        if isinstance(signals[sig], int):
                            signals[sig] = int(signals[sig] * multiplier)
                        else:
                            signals[sig] = min(1.0, signals[sig] * multiplier)
                            
                # Tier 3: Critical Symptoms (Exponential spike in the final 4 weeks)
                if weeks_until_failure <= 4:
                    spike_factor = math.exp(5 - weeks_until_failure) 
                    for sig in profile.get("critical", []):
                        if sig == "oil_pressure_dips":
                            signals[sig] += int(spike_factor) # Add integer dips
                        else:
                            signals[sig] = min(1.0, signals[sig] + (spike_factor * 0.005))

            # Inject Historical Failure Spikes (Iterate past job cards)
            for jc in v_failures:
                days_until_failure = (jc.failure_date - week_date).days
                if 0 <= days_until_failure <= 365:
                    weeks_until = days_until_failure // 7
                    apply_tiered_degradation(jc.part_code, weeks_until)
                        
            # Inject Active Imminent Failure Spikes
            if active_failing_part:
                # week_offset acts exactly as weeks_until_failure (0 = failing this week)
                apply_tiered_degradation(active_failing_part, week_offset)
                        
            telematics_records.append(models.Telematics(
                vin=v.vin, 
                week_start_date=week_date, 
                **signals
            ))
            
        if len(telematics_records) > 10000:
            db.add_all(telematics_records)
            db.commit()
            telematics_records = []
            
    if telematics_records:
        db.add_all(telematics_records)
        db.commit()
        
    print(f"-> Generated {NUM_VEHICLES * 52} tiered telematics records successfully.")


def main():
    models.Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        parts = generate_parts(db)
        vehicles = generate_vehicles(db)
        job_cards = generate_job_cards(db, vehicles, parts)
        generate_telematics(db, vehicles, job_cards)
        print("\nSuccess: Fully synthetic tiered 500-vehicle dataset injected and ready for ML Analysis!")
    finally:
        db.close()

if __name__ == "__main__":
    main()