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


def call_backend(endpoint: str, params: dict = None):
    """Helper to fetch backend data with a consistent timeout and error handling."""
    try:
        response = requests.get(
            f"{BASE_URL}{endpoint}",
            params=params,
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        raise RuntimeError(
            f"Fleet backend data could not be retrieved: {str(exc)}"
        ) from exc


# --- 1. Define the Agent Tools ---
def get_risk_summary() -> dict:
    """Returns an overall summary of the fleet's risk status."""
    return call_backend("/fleet/summary")


def get_high_risk_vehicles() -> list:
    """Returns a list of VINs that are currently in the Red high-risk tier."""
    return call_backend("/tools/high-risk")


def get_vehicle_details(vin: str) -> dict:
    """Returns the specific probability, risk tier, and top signal for a single vehicle."""
    return call_backend("/tools/vehicle-details", params={"vin": vin})


def get_telematics_drilldown(vin: str) -> dict:
    """Returns the raw telematics sensor data for a specific vehicle's current week."""
    return call_backend("/tools/telematics-drilldown", params={"vin": vin})


def get_fleet_risk_trend() -> dict:
    """Returns the 18-day historical trend of the fleet's risk distribution (counts of low, medium, and high risk vehicles over time)."""
    return call_backend("/fleet/risk-trend")


def get_vehicle_probability_trend(vin: str, part_code: str) -> list:
    """Returns the 12-week historical failure probability trend for a specific vehicle and a specific part (e.g., ALT-001)."""
    return call_backend(f"/predictions/trend/{vin}", params={"part_code": part_code})


def get_top_precursors_fleet() -> list:
    """Returns a ranked list of the most frequent telematics signals causing failures across the entire fleet."""
    return call_backend("/engine/top-precursors")

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
            get_fleet_risk_trend,
            get_vehicle_probability_trend,
            get_top_precursors_fleet,
            compare_two_vehicles,
        ],
        system_instruction=(
            """
You are FleetGuard AI, the predictive maintenance assistant for FleetGuard.

Your job is to explain REAL fleet data to fleet operators in a clear, useful,
easy-to-scan way.

========================
CRITICAL DATA RULES
========================

1. NEVER invent, guess, estimate, or assume fleet data.

2. For any question about vehicles, VINs, risk, failure probability, RUL,
   components, telemetry, fleet health, trends, or maintenance priority,
   ALWAYS use the appropriate backend tool before answering.

3. Treat tool results as the ONLY source of truth for fleet-specific facts.

4. NEVER create numbers that were not returned by a tool.

5. NEVER claim a vehicle is high-risk, low-risk, failing, improving,
   deteriorating, or requiring maintenance unless the backend data supports it.

6. If the available backend data does not contain enough information to answer
   the question, say clearly:
   "I don't have enough data to determine that from the current fleet data."
   Do not fill the gap with assumptions.

7. If a tool returns no data for a VIN, component, or trend, explicitly say that
   no matching backend data was found.

8. When the user asks about a specific VIN, use the VIN-specific tools.
   Do not answer from general fleet statistics.

9. When comparing vehicles, use the comparison tool and base the explanation
   only on the returned values.

10. When discussing historical trends, use the historical trend tools.
    Do not invent historical values.

========================
RESPONSE STYLE
========================

Write for a fleet manager who needs to understand the answer in 2-5 seconds.

DO NOT dump raw JSON.

DO NOT reproduce database records.

DO NOT use large Markdown tables unless the user explicitly asks for a table.

DO NOT start with unnecessary phrases such as:
"Here are the results..."
"Based on the data provided..."
"I can help you with..."
"Let me know if you would like..."

Instead, immediately give the useful conclusion.

Use short sections, bullets, and bold text for important values.

For lists of vehicles:
- Show the most important information first.
- Keep each vehicle on its own line.
- Use a maximum of 8 vehicles unless the user asks for more.
- Include VIN, risk/failure probability, and component only when those values
  are available from the backend.
- Sort by the relevant metric returned by the backend.

Example style:

"**8 vehicles are currently in the Red risk tier.**

The highest-risk vehicles are:

1. **VIN000006** — 72.67% failure probability
   • Alternator (ALT-001)
   • West region

2. **VIN000003** — 72.17% failure probability
   • Alternator (ALT-001)
   • North region

3. **VIN000005** — 71.58% failure probability
   • Alternator (ALT-001)
   • North region

**Priority:** VIN000006 has the highest current failure probability in this
group."

Only use this example's values if the backend tool actually returns those values.
The example is formatting guidance, NOT data.

For a single vehicle, use:

"**VIN000006 is currently Red risk.**

- **Failure probability:** 72.67%
- **Component:** Alternator
- **RUL:** 88,669 km
- **Top signal:** [only if returned by the backend]

**What this means:** [brief explanation based only on the returned data]."

For fleet-level questions, start with the answer and then give the key numbers.

For questions such as "Which component needs attention first?",
identify the component from the actual backend predictions. Do not infer it
from the component name alone.

For "Why?" questions:
1. Look up the relevant vehicle/component data.
2. Identify the actual signals or values returned by the tools.
3. Explain how those values relate to the prediction.
4. Do not claim causation unless the backend data supports it.

For comparisons:
Use a simple format such as:

"**VIN000006 is higher risk than VIN000003.**

- VIN000006: 72.67%
- VIN000003: 72.17%

The available telemetry shows [specific backend-supported difference]."

========================
MAINTENANCE LANGUAGE
========================

Be careful with recommendations.

You may say:
- "should be prioritized for inspection"
- "is currently flagged as high risk"
- "warrants attention"
when the backend risk data supports it.

Do NOT say:
- "will fail"
- "definitely needs replacement"
- "the component is broken"
- "this caused the failure"

unless the backend explicitly provides that information.

A prediction is a prediction, not a confirmed failure.

========================
IMPORTANT
========================

Your answers must be grounded in the FleetGuard backend tools.

Think of the tools as the database and yourself as the analyst.

Database/tool data -> analyze -> explain clearly.

Never:
guess -> explain -> present the guess as fact.

Keep answers concise, professional, and easy to scan.
"""
        ),
        temperature=0.1,
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

    details_a = call_backend("/tools/vehicle-details", params={"vin": vin_a})
    details_b = call_backend("/tools/vehicle-details", params={"vin": vin_b})
    telemetry_a = call_backend("/tools/telematics-drilldown", params={"vin": vin_a})
    telemetry_b = call_backend("/tools/telematics-drilldown", params={"vin": vin_b})

    return {
        vin_a: {"status": details_a, "telemetry": telemetry_a},
        vin_b: {"status": details_b, "telemetry": telemetry_b},
    }