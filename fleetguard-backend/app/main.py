from fastapi import FastAPI
from app.database import engine
from app import models

# Create all tables in the database automatically on startup
models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="FleetGuard AI API")

@app.get("/api/health")
def health_check():
    """Verify system status (P0 Requirement)"""
    return {"status": "ok"}