import os
from typing import List

import requests
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from google import genai
from google.genai import types


load_dotenv()

router = APIRouter(prefix="/api/chat", tags=["AI Assistant"])


# =========================================================
# GEMINI CLIENT
# =========================================================

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise RuntimeError("GEMINI_API_KEY is not configured.")

client = genai.Client(api_key=GEMINI_API_KEY)


# Backend API used by the AI agent tools
BASE_URL = "http://127.0.0.1:8000/api"


# =========================================================
# HELPER
# =========================================================

def api_get(path: str, params: dict | None = None):
    """
    Safely fetch data from the FleetGuard backend API.

    The AI agent must only use data returned from these
    backend endpoints and must never invent missing data.
    """

    url = f"{BASE_URL}{path}"

    response = requests.get(
        url,
        params=params,
        timeout=10,
    )

    response.raise_for_status()

    return response.json()


# =========================================================
# AI AGENT TOOLS
# =========================================================

def get_risk_summary() -> dict:
    """
    Returns the current overall fleet risk summary.
    """

    return api_get("/fleet/summary")


def get_high_risk_vehicles() -> list:
    """
    Returns vehicles currently classified as high risk.
    """

    return api_get("/tools/high-risk")


def get_vehicle_details(vin: str) -> dict:
    """
    Returns current risk details for a specific vehicle.
    """

    return api_get(
        "/tools/vehicle-details",
        {"vin": vin.upper()},
    )


def get_telematics_drilldown(vin: str) -> dict:
    """
    Returns current telematics data for a specific vehicle.
    """

    return api_get(
        "/tools/telematics-drilldown",
        {"vin": vin.upper()},
    )


def get_fleet_risk_trend() -> dict:
    """
    Returns the historical fleet risk distribution.
    """

    return api_get("/fleet/risk-trend")


def get_vehicle_probability_trend(
    vin: str,
    part_code: str,
) -> list:
    """
    Returns historical failure probability for a vehicle
    and specific component.
    """

    return api_get(
        f"/predictions/trend/{vin.upper()}",
        {"part_code": part_code.upper()},
    )


def get_top_precursors_fleet() -> list:
    """
    Returns the most frequent failure-related telematics
    signals across the fleet.
    """

    return api_get("/engine/top-precursors")


def compare_two_vehicles(
    vin_a: str,
    vin_b: str,
) -> dict:
    """
    Compares two vehicles using real backend data.

    Retrieves current risk details and telematics for both
    vehicles.
    """

    vin_a = vin_a.upper()
    vin_b = vin_b.upper()

    details_a = get_vehicle_details(vin_a)
    details_b = get_vehicle_details(vin_b)

    telemetry_a = get_telematics_drilldown(vin_a)
    telemetry_b = get_telematics_drilldown(vin_b)

    return {
        vin_a: {
            "status": details_a,
            "telemetry": telemetry_a,
        },
        vin_b: {
            "status": details_b,
            "telemetry": telemetry_b,
        },
    }


# =========================================================
# REQUEST SCHEMAS
# =========================================================

class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    history: List[Message] = []


# =========================================================
# AI SYSTEM INSTRUCTIONS
# =========================================================

SYSTEM_INSTRUCTION = """
You are FleetGuard AI, the predictive maintenance assistant
inside the FleetGuard fleet-management application.

Your job is to help fleet operators understand real fleet
risk, vehicle health, component failures, telemetry and
remaining useful life.

============================================================
CRITICAL DATA RULES
============================================================

1. NEVER invent fleet-specific information.

2. NEVER invent:
   - VINs
   - failure probabilities
   - risk tiers
   - regions
   - vehicle models
   - component names
   - RUL values
   - telemetry values
   - trends
   - dates
   - maintenance information

3. When a question requires current FleetGuard data,
   ALWAYS use the appropriate backend tool before answering.

4. Backend tool results are the ONLY source of truth for
   fleet-specific information.

5. If the backend does not contain the requested
   information, clearly say that the information is
   unavailable.

6. Never guess missing values.

7. Never create plausible-looking numbers.

8. If a backend tool returns an error, do not fabricate
   a replacement answer. Explain that the requested fleet
   data could not be retrieved.

9. For a specific VIN, use the vehicle-specific tools.

10. For fleet-wide questions, use fleet-level tools.

11. For comparisons, retrieve information for BOTH vehicles
    before comparing them.

12. Do not claim a vehicle is high risk unless the backend
    data confirms it.

13. Do not claim that a component is causing a failure unless
    the backend data provides evidence for it.

============================================================
ANSWER STYLE
============================================================

Make every answer understandable at FIRST GLANCE.

Do not dump raw JSON.

Do not expose internal API responses.

Do not mention Python functions, backend endpoints,
tool names, or implementation details.

Avoid large unnecessary tables.

Avoid long paragraphs.

Use short sections, bullets and clear labels.

============================================================
VEHICLE RISK QUESTIONS
============================================================

For questions such as:

"Why is VIN000006 high risk?"

First retrieve the actual backend data.

Then answer in a structure similar to:

VIN000006 is currently **High Risk**.

• **Failure probability:** 72.7%
• **Component:** Alternator
• **Region:** West
• **Main signal:** High-RPM dwell time

**Why it matters**
The available fleet data indicates that this vehicle
has an elevated predicted failure probability.

**Recommended action**
Prioritize the vehicle for inspection if the available
backend data supports that recommendation.

Only include fields that actually exist in the backend data.

============================================================
HIGHEST-RISK VEHICLES
============================================================

For questions such as:

"Which vehicles are at highest risk?"

Use the backend high-risk vehicle data.

Present a short ranked list.

Example format:

**Highest-risk vehicles**

1. **VIN000006** — 72.67% — Alternator
2. **VIN000003** — 72.17% — Alternator
3. **VIN000005** — 71.58% — Alternator

Then provide ONE short explanation:

"These vehicles currently have the highest recorded
failure probabilities in the available fleet data."

Do not add vehicles that were not returned by the backend.

============================================================
FLEET HEALTH QUESTIONS
============================================================

For questions such as:

"How is the fleet doing?"

Retrieve the fleet summary first.

Present the most important numbers first.

Example:

**Fleet Health**

• **Vehicles monitored:** X
• **High-risk vehicles:** X
• **Average fleet RUL:** X km

Then give a short plain-English interpretation based
only on the returned data.

============================================================
COMPONENT QUESTIONS
============================================================

If the user asks which component needs attention:

Use the available prediction and fleet data.

Clearly distinguish between:

• Component
• Number of affected vehicles
• Failure probability
• Risk tier

Do not claim causation unless the backend provides
supporting evidence.

============================================================
WHY QUESTIONS
============================================================

For questions such as:

"Why is VIN000006 high risk?"

Retrieve:

1. Vehicle details
2. Telematics data

Explain only signals actually returned by the backend.

Do not invent explanations.

============================================================
TREND QUESTIONS
============================================================

For fleet trend questions:

Use the fleet risk trend tool.

For vehicle/component probability trends:

Use the vehicle probability trend tool.

Clearly distinguish historical data from the current
prediction.

============================================================
COMPARISON QUESTIONS
============================================================

For questions such as:

"Compare VIN000006 and VIN000003"

Retrieve data for BOTH vehicles.

Use this structure:

**VIN000006**
• Risk: ...
• Probability: ...
• Main signal: ...

**VIN000003**
• Risk: ...
• Probability: ...
• Main signal: ...

**Key difference**
Explain the difference using only retrieved data.

Never compare one vehicle using data from another vehicle.

============================================================
MISSING DATA
============================================================

If requested information is unavailable, say:

"I don't have that information in the current FleetGuard
data."

Do not guess.

============================================================
GENERAL BEHAVIOUR
============================================================

Be concise.

Be professional.

Be operationally useful.

Prioritize clarity over technical detail.

Always use real FleetGuard backend data for
fleet-specific questions.
"""


# =========================================================
# CHAT ENDPOINT
# =========================================================

@router.post("")
def chat_with_agent(request: ChatRequest):

    try:

        # -------------------------------------------------
        # Convert frontend history to Gemini format
        # -------------------------------------------------

        formatted_history = []

        for msg in request.history:

            role = "user" if msg.role == "user" else "model"

            formatted_history.append(
                types.Content(
                    role=role,
                    parts=[
                        types.Part.from_text(
                            text=msg.content
                        )
                    ],
                )
            )

        # -------------------------------------------------
        # Configure Gemini
        # -------------------------------------------------

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

            system_instruction=SYSTEM_INSTRUCTION,

            temperature=0.1,
        )

        # -------------------------------------------------
        # Create chat session
        # -------------------------------------------------

        chat = client.chats.create(
            model="gemini-3.5-flash",
            config=config,
            history=formatted_history,
        )

        # -------------------------------------------------
        # Send user message
        # -------------------------------------------------

        response = chat.send_message(
            request.message
        )

        # -------------------------------------------------
        # Validate Gemini response
        # -------------------------------------------------

        if not response:
            raise RuntimeError(
                "Gemini returned an empty response."
            )

        reply = response.text

        if not reply:
            raise RuntimeError(
                "Gemini returned no text response."
            )

        return {
            "reply": reply
        }

    # =====================================================
    # BACKEND TOOL ERROR
    # =====================================================

    except requests.exceptions.RequestException as e:

        print(
            f"[FleetGuard Tool Error] "
            f"{type(e).__name__}: {e}"
        )

        raise HTTPException(
            status_code=502,
            detail=(
                "Fleet data service could not be reached."
            ),
        )

    # =====================================================
    # ALL OTHER ERRORS
    # =====================================================

    except Exception as e:

        print(
            f"[FleetGuard AI Error] "
            f"{type(e).__name__}: {e}"
        )

        error_text = str(e)

        # -------------------------------------------------
        # Gemini quota / rate limit
        # -------------------------------------------------

        if (
            "429" in error_text
            or "RESOURCE_EXHAUSTED" in error_text
        ):

            raise HTTPException(
                status_code=429,
                detail=(
                    "FleetGuard AI has temporarily reached "
                    "the Gemini API request limit. "
                    "Please try again later."
                ),
            )

        # -------------------------------------------------
        # Other AI/backend errors
        # -------------------------------------------------

        raise HTTPException(
            status_code=500,
            detail=(
                "FleetGuard AI could not process "
                "the request."
            )
        )
