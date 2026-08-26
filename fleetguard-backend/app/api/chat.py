import os
import requests
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from google import genai
from google.genai import types

load_dotenv()

router = APIRouter(prefix="/api/chat", tags=["AI Assistant"])

# Initialize the Gemini Client explicitly using the loaded key
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

# The local URL where our tools can fetch database info
BASE_URL = "http://127.0.0.1:8000/api"

# --- 1. Define the Agent Tools ---
def get_risk_summary() -> dict:
    """Returns an overall summary of the fleet's risk status."""
    return requests.get(f"{BASE_URL}/fleet/summary").json()

def get_high_risk_vehicles() -> list:
    """Returns a list of VINs that are currently in the Red high-risk tier."""
    return requests.get(f"{BASE_URL}/tools/high-risk").json()

def get_vehicle_details(vin: str) -> dict:
    """Returns the specific probability, risk tier, and top signal for a single vehicle."""
    return requests.get(f"{BASE_URL}/tools/vehicle-details", params={"vin": vin}).json()

def get_telematics_drilldown(vin: str) -> dict:
    """Returns the raw telematics sensor data for a specific vehicle's current week."""
    return requests.get(f"{BASE_URL}/tools/telematics-drilldown", params={"vin": vin}).json()

def get_fleet_risk_trend() -> dict:
    """Returns the 18-day historical trend of the fleet's risk distribution (counts of low, medium, and high risk vehicles over time)."""
    return requests.get(f"{BASE_URL}/fleet/risk-trend").json()

def get_vehicle_probability_trend(vin: str, part_code: str) -> list:
    """Returns the 12-week historical failure probability trend for a specific vehicle and a specific part (e.g., ALT-001)."""
    return requests.get(f"{BASE_URL}/predictions/trend/{vin}", params={"part_code": part_code}).json()

def get_top_precursors_fleet() -> list:
    """Returns a ranked list of the most frequent telematics signals causing failures across the entire fleet."""
    return requests.get(f"{BASE_URL}/engine/top-precursors").json()

# --- 2. Define the Request Schema ---
class Message(BaseModel):
    role: str # 'user' or 'assistant'
    content: str

class ChatRequest(BaseModel):
    message: str
    history: List[Message] = []

# --- 3. The Chat Endpoint ---
@router.post("")
def chat_with_agent(request: ChatRequest):
    """
    Client-facing chat endpoint. Orchestrates the UI prompt, chat history, 
    and Gemini tool calling.
    """
    # Map the frontend's history format to the GenAI SDK format
    formatted_history = []
    for msg in request.history:
        # Gemini expects 'user' or 'model' as roles
        role = "user" if msg.role == "user" else "model"
        formatted_history.append(
            types.Content(role=role, parts=[types.Part.from_text(text=msg.content)])
        )

    # Configure the AI with persona instructions and our backend tools
    config = types.GenerateContentConfig(
        tools=[
            get_risk_summary, 
            get_high_risk_vehicles, 
            get_vehicle_details, 
            get_telematics_drilldown,
            get_fleet_risk_trend,           # NEW TOOL
            get_vehicle_probability_trend,  # NEW TOOL
            get_top_precursors_fleet,
            compare_two_vehicles       
        ],
        system_instruction=(
            "You are FleetGuard AI, an expert predictive maintenance assistant. "
            "You have access to live database tools to check fleet health and specific vehicle telemetry. "
            "Always use your tools to look up real data before answering questions about specific vehicles. "
            "Be concise, professional, and helpful."
        ),
        temperature=0.2,
    )
    
    try:
        # Initialize the stateful chat session with the parsed history
        chat = client.chats.create(
            model="gemini-3.5-flash", 
            config=config, 
            history=formatted_history
        )
        
        # Send the new message. The SDK will automatically pause, execute our local Python 
        # tools if needed, inject the JSON results, and generate the final text answer.
        response = chat.send_message(request.message)
        
        return {"reply": response.text}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def compare_two_vehicles(vin_a: str, vin_b: str) -> dict:
    """
    Fetches and compares the current risk tier, failure probability, and raw telematics for two specific vehicles side-by-side.
    Use this whenever asked to compare two trucks or explain why one is performing better/worse than another.
    """
    vin_a = vin_a.upper()
    vin_b = vin_b.upper()
    
    # Fetch high-level details for both
    details_a = requests.get(f"{BASE_URL}/tools/vehicle-details", params={"vin": vin_a}).json()
    details_b = requests.get(f"{BASE_URL}/tools/vehicle-details", params={"vin": vin_b}).json()
    
    # Fetch raw sensor data for both
    telemetry_a = requests.get(f"{BASE_URL}/tools/telematics-drilldown", params={"vin": vin_a}).json()
    telemetry_b = requests.get(f"{BASE_URL}/tools/telematics-drilldown", params={"vin": vin_b}).json()
    
    # Return a unified side-by-side dictionary
    return {
        vin_a: {"status": details_a, "telemetry": telemetry_a},
        vin_b: {"status": details_b, "telemetry": telemetry_b}
    }