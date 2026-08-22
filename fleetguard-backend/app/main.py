from fastapi import FastAPI
from app.database import engine
from app import models
from app.api import rules, predictions, fleet  # Import the fleet router

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="FleetGuard AI API")

app.include_router(rules.router)
app.include_router(predictions.router)
app.include_router(fleet.router) # Register the fleet endpoints

@app.get("/api/health")
def health_check():
    """Verify system status (P0 Requirement)"""
    return {"status": "ok"}