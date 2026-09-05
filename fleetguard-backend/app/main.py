from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.database import engine
from app import models
from app.api import rules, predictions, fleet, tools, parts, engine as engine_api, rul, chat  # Import tools router

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="FleetGuard AI API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(rules.router)
app.include_router(predictions.router)
app.include_router(fleet.router)
app.include_router(tools.router)
app.include_router(parts.router)
app.include_router(engine_api.router)
app.include_router(rul.router)
app.include_router(chat.router)


@app.get("/api/health")
def health_check():
    return {"status": "ok"}