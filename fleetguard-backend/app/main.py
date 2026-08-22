from fastapi import FastAPI
from app.database import engine
from app import models
from app.api import rules, predictions, fleet, tools  # Import tools router

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="FleetGuard AI API")

app.include_router(rules.router)
app.include_router(predictions.router)
app.include_router(fleet.router)
app.include_router(tools.router) # Register the agent tools

@app.get("/api/health")
def health_check():
    return {"status": "ok"}