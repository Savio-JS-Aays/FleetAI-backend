import random
from datetime import date, timedelta
from app.database import SessionLocal, engine
from app import models

# P0 Requirement: Fixed random seed for reproducible datasets
RANDOM_SEED = 42
NUM_VEHICLES = 300

random.seed(RANDOM_SEED)

def generate_parts(db):
    print("Generating Parts...")
    parts = [
        models.Part(part_code="ALT-001", part_name="Alternator", category="Electrical", design_life_km=300000),
        models.Part(part_code="WP-002", part_name="Water Pump", category="Cooling", design_life_km=250000),
        models.Part(part_code="TC-003", part_name="Turbocharger", category="Engine", design_life_km=400000),
    ]
    
    # Clear existing parts to prevent primary key collisions on re-runs
    db.query(models.Part).delete() 
    db.add_all(parts)
    db.commit()
    print(f"-> Created {len(parts)} parts.")

def generate_vehicles(db):
    print(f"Generating {NUM_VEHICLES} Vehicles...")
    models_list = ["Long-Haul Tractor", "Rigid Haulage", "Urban Delivery"]
    regions = ["North", "South", "East", "West"]
    
    # Clear existing vehicles
    db.query(models.Vehicle).delete()
    
    vehicles = []
    for i in range(1, NUM_VEHICLES + 1):
        vin = f"VIN{str(i).zfill(6)}"
        v_model = random.choice(models_list)
        region = random.choice(regions)
        
        # Registration between 1 to 5 years ago
        reg_days_ago = random.randint(365, 365 * 5)
        # Using a fixed end-date (today) for the simulation
        reg_date = date.today() - timedelta(days=reg_days_ago)
        
        # Assume an average of 80,000 to 120,000 km driven per year
        total_km = int((reg_days_ago / 365.0) * random.uniform(80000, 120000))
        
        vehicle = models.Vehicle(
            vin=vin,
            model=v_model,
            region=region,
            registration_date=reg_date,
            total_km=total_km
        )
        vehicles.append(vehicle)
        
    db.add_all(vehicles)
    db.commit()
    print(f"-> Created {len(vehicles)} vehicles.")

def main():
    # Ensure tables exist
    models.Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()
    try:
        generate_parts(db)
        generate_vehicles(db)
        print("\nSuccess: Base dimensional data generated!")
    finally:
        db.close()

if __name__ == "__main__":
    main()