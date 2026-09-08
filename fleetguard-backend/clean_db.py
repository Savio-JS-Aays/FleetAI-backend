from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Prediction

def flush_predictions():
    db = SessionLocal()
    try:
        # 1. Delete all poisoned historical data
        deleted_count = db.query(Prediction).delete()
        db.commit()
        print(f"Success! Deleted {deleted_count} old, mathematically flawed predictions.")
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    flush_predictions()