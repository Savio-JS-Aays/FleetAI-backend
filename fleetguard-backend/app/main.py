from fastapi import FastAPI
from app.database import engine
from app import models
from app.api import rules, predictions # Import predictions

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="FleetGuard AI API")

app.include_router(rules.router)
app.include_router(predictions.router) # Register predictions

@app.get("/api/health")
def health_check():
    return {"status": "ok"}