import os
import requests
from dotenv import load_dotenv
from google import genai
from google.genai import types

# Load API key from .env file
load_dotenv()
api_key = os.getenv("LLM_API_KEY")

if not api_key or api_key == "your_gemini_api_key_here":
    print("CRITICAL ERROR: Please set a valid LLM_API_KEY in your .env file.")
    exit(1)

# Initialize the new SDK Client
client = genai.Client(api_key=api_key)

BASE_URL = "http://127.0.0.1:8000/api"

# --- 1. Define the Tools mapping to our FastAPI endpoints ---
def get_risk_summary():
    """Returns aggregate fleet risk counts, total vehicles, and average RUL."""
    response = requests.get(f"{BASE_URL}/fleet/summary")
    return response.json()

def get_high_risk_vehicles(part_code: str = None, region: str = None):
    """Returns a list of specific Red-tier high-risk vehicles. Use this to find which vehicles are likely to fail."""
    params = {}
    if part_code: params["part_code"] = part_code
    if region: params["region"] = region
    
    response = requests.get(f"{BASE_URL}/tools/high-risk", params=params)
    return response.json()

def get_vehicle_details(vin: str):
    """Returns specific probability, risk tier, and Remaining Useful Life (RUL) for a given VIN."""
    response = requests.get(f"{BASE_URL}/tools/vehicle-details", params={"vin": vin})
    
    # Handle the missing data constraint cleanly (P0 Requirement)
    if response.status_code == 404:
        return {"error": f"Vehicle {vin} not found in the database."}
    return response.json()

# --- 2. Configure the Gemini Model ---
# The new SDK uses a strict config object to pass instructions and tools
config = types.GenerateContentConfig(
    system_instruction=(
        "You are FleetGuard AI. You must ONLY use the provided tools to answer data questions. "
        "Do not invent VINs, probabilities, or metrics. If a tool returns an error, state that "
        "the information is unavailable."
    ),
    tools=[get_risk_summary, get_high_risk_vehicles, get_vehicle_details],
    temperature=0.1, # Keep it low so it focuses strictly on data, not creative writing
)

# --- 3. Execute the Benchmark Test ---
def run_benchmark():
    print("Initializing Insight Agent (Using New google-genai SDK)...")
    
    # Start a chat session with the config applied
    chat = client.chats.create(model="gemini-3.5-flash", config=config)
    
    benchmark_question = "Can you give me a summary of the fleet risk, and list 3 specific vehicles that are in the red tier?"
    print(f"\nUser: {benchmark_question}")
    print('\n[LLM is "thinking" and executing backend tools...]\n')
    
    # Send the message. The SDK will automatically handle calling our Python functions!
    response = chat.send_message(benchmark_question)
    
    print("FleetGuard AI:")
    print(response.text)

if __name__ == "__main__":
    run_benchmark()