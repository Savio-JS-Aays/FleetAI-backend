from fastapi import FastAPI
from app.database import engine
from app import models
from app.api import rules  # Import the new router

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="FleetGuard AI API")

# Register the ML/Rules endpoints
app.include_router(rules.router)

@app.get("/api/health")
def health_check():
    """Verify system status (P0 Requirement)"""
    return {"status": "ok"}