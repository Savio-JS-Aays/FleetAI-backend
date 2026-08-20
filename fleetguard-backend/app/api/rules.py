from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.ml.correlation import calculate_signal_weights
from app import models, schemas

router = APIRouter(prefix="/api/ml", tags=["ML & Rules"])

@router.get("/correlations")
def get_correlations(part_code: str, db: Session = Depends(get_db)):
    """Dynamically calculates and returns signal correlations for a part."""
    # This executes the ML logic we just tested
    return calculate_signal_weights(part_code, db)

@router.post("/rules")
def save_rule(rule: schemas.RuleCreate, db: Session = Depends(get_db)):
    """Persists a configured rule to the database (P0 Requirement)."""
    # 1. Delete any existing rule for this part to overwrite it
    db.query(models.RuleConfig).filter(models.RuleConfig.part_code == rule.part_code).delete()
    
    # 2. Insert the new configuration
    configs = []
    for sig in rule.signals:
        configs.append(models.RuleConfig(
            part_code=rule.part_code,
            signal_name=sig.signal,
            correlation_weight=sig.weight,
            is_included=sig.is_included
        ))
    
    db.add_all(configs)
    db.commit()
    
    return {"status": "saved"}

@router.get("/rules")
def get_saved_rule(part_code: str, db: Session = Depends(get_db)):
    """Retrieves the currently active rule for a part."""
    rules = db.query(models.RuleConfig).filter(models.RuleConfig.part_code == part_code).all()
    return rules