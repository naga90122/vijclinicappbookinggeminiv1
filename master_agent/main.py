# master_agent/main.py

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
import os
import httpx # For making API calls to other agents

# Load environment variables from .env file
load_dotenv()

app = FastAPI(
    title="Master Agent API",
    description="Orchestrates clinic appointment booking workflows."
)

# Configuration for other agents (replace with actual service names/ports if different in docker-compose)
MANAGER_AGENT_URL = os.getenv("MANAGER_AGENT_URL", "http://manager_agent:8000") # Use service name for inter-container comms
VOICE_INTERFACE_URL = os.getenv("VOICE_INTERFACE_URL", "http://voice_interface:8000")

# --- Request/Response Models ---
class UserMessage(BaseModel):
    user_id: str
    message: str # The transcribed text from the user
    is_voice: bool = True # Flag to indicate if original input was voice

class AgentResponse(BaseModel):
    response_text: str # Text response to the user
    action_status: str = "pending" # e.g., "success", "failure", "in_progress"
    follow_up_required: bool = False # Does master need to ask further questions?

class ManagerInstruction(BaseModel):
    task: str # e.g., "book_appointment", "reschedule_appointment"
    details: dict # Key-value pairs for task specifics

# --- Helper Function for API Calls (common among agents) ---
async def call_agent_api(agent_url: str, endpoint: str, payload: BaseModel):
    """Generic function to call another agent's API."""
    full_url = f"{agent_url}/{endpoint}"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(full_url, json=payload.dict())
            response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
            return response.json()
        except httpx.HTTPStatusError as e:
            print(f"Error calling agent API {full_url}: {e.response.status_code} - {e.response.text}")
            raise HTTPException(status_code=e.response.status_code, detail=f"Agent API error: {e.response.text}")
        except httpx.RequestError as e:
            print(f"Network error calling agent API {full_url}: {e}")
            raise HTTPException(status_code=503, detail=f"Cannot reach agent service: {e}")

# --- Master Agent Endpoints ---

@app.post("/process_user_input", response_model=AgentResponse)
async def process_user_input(user_input: UserMessage):
    """
    Main endpoint for receiving user input (transcribed voice or text).
    Delegates to the Manager Agent for processing.
    """
    print(f"Master Agent received input from {user_input.user_id}: '{user_input.message}' (Voice: {user_input.is_voice})")

    # Step 1: Analyze user intent (Placeholder for NLU)
    # In a real scenario, this would use an LLM call to gemini-1.5-flash
    # to extract intent (book, reschedule, cancel, register, login) and entities.
    # For now, let's assume a simple intent detection.
    # Example:
    intent = "unknown"
    if "book appointment" in user_input.message.lower() or "schedule an appointment" in user_input.message.lower():
        intent = "book_appointment"
    elif "reschedule" in user_input.message.lower():
        intent = "reschedule_appointment"
    elif "cancel" in user_input.message.lower():
        intent = "cancel_appointment"
    elif "register" in user_input.message.lower() or "sign up" in user_input.message.lower():
        intent = "register_user"
    elif "login" in user_input.message.lower() or "sign in" in user_input.message.lower():
        intent = "login_user"

    if intent == "unknown":
        return AgentResponse(
            response_text="I'm sorry, I didn't understand that. Could you please rephrase your request?",
            action_status="failure",
            follow_up_required=True
        )

    # Step 2: Delegate to Manager Agent
    manager_instruction = ManagerInstruction(
        task=intent,
        details={"user_id": user_input.user_id, "original_message": user_input.message}
    )

    try:
        # Call the Manager Agent's API to initiate the workflow
        manager_response = await call_agent_api(
            MANAGER_AGENT_URL,
            "process_instruction", # Assuming manager_agent has this endpoint
            manager_instruction
        )
        print(f"Manager Agent response: {manager_response}")

        # The Master Agent interprets the Manager's response to formulate a user-facing reply.
        # This part will become more sophisticated as agents are built out.
        if manager_response.get("status") == "success":
            user_facing_response = manager_response.get("message", "Request sent to Manager for processing.")
            return AgentResponse(
                response_text=user_facing_response,
                action_status="in_progress", # Master initiates, other agents work
                follow_up_required=manager_response.get("follow_up_required", False)
            )
        else:
            return AgentResponse(
                response_text=manager_response.get("message", "There was an issue processing your request."),
                action_status="failure",
                follow_up_required=True # Ask for clarification
            )
    except HTTPException as e:
        return AgentResponse(
            response_text=f"An error occurred internally: {e.detail}",
            action_status="failure",
            follow_up_required=True
        )
    except Exception as e:
        print(f"Unexpected error in Master Agent: {e}")
        return AgentResponse(
            response_text="An unexpected error occurred. Please try again later.",
            action_status="failure",
            follow_up_required=True
        )

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "Master Agent is healthy"}

