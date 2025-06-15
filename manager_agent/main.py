# manager_agent/main.py

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
import os
import httpx

load_dotenv()

app = FastAPI(
    title="Manager Agent API",
    description="Breaks down tasks and coordinates other agents."
)

# URLs for other agents (use service names for inter-container communication)
INSTRUCTION_DEVELOPER_AGENT_URL = os.getenv("INSTRUCTION_DEVELOPER_AGENT_URL", "http://instruction_developer_agent:8000")
QA_AGENT_URL = os.getenv("QA_AGENT_URL", "http://qa_agent:8000")
SCHEDULER_AGENT_URL = os.getenv("SCHEDULER_AGENT_URL", "http://scheduler_agent:8000")
DB_AGENT_URL = os.getenv("DB_AGENT_URL", "http://db_agent:8000")
AUTH_AGENT_URL = os.getenv("AUTH_AGENT_URL", "http://auth_agent:8000")

# --- Request/Response Models ---
class ManagerInstruction(BaseModel):
    task: str # e.g., "book_appointment", "reschedule_appointment"
    details: dict # Key-value pairs for task specifics

class AgentResponseInternal(BaseModel):
    status: str # "success", "failure", "in_progress"
    message: str
    data: dict = {}
    follow_up_required: bool = False

class DeveloperInstruction(BaseModel):
    task_type: str
    raw_input: str
    extracted_entities: dict = {}

class QAInput(BaseModel):
    proposed_action: str
    action_details: dict

# --- Helper Function for API Calls (common among agents) ---
async def call_agent_api(agent_url: str, endpoint: str, payload: BaseModel):
    """Generic function to call another agent's API."""
    full_url = f"{agent_url}/{endpoint}"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(full_url, json=payload.dict())
            response.raise_for_status()
            return response.json()
        except httpx.HTTPStatusError as e:
            print(f"Error calling agent API {full_url}: {e.response.status_code} - {e.response.text}")
            raise HTTPException(status_code=e.response.status_code, detail=f"Agent API error: {e.response.text}")
        except httpx.RequestError as e:
            print(f"Network error calling agent API {full_url}: {e}")
            raise HTTPException(status_code=503, detail=f"Cannot reach agent service: {e}")

# --- Manager Agent Endpoints ---

@app.post("/process_instruction", response_model=AgentResponseInternal)
async def process_instruction(instruction: ManagerInstruction):
    """
    Receives high-level instructions from the Master Agent and orchestrates
    the workflow by delegating to other agents.
    """
    print(f"Manager Agent received instruction: {instruction.task} with details: {instruction.details}")

    user_id = instruction.details.get("user_id")
    original_message = instruction.details.get("original_message")

    try:
        # Step 1: Use Instruction Developer Agent to flesh out details
        developer_input = DeveloperInstruction(
            task_type=instruction.task,
            raw_input=original_message,
            # In a real scenario, manager would use LLM or rule-based logic to
            # extract initial entities and pass them to developer agent
            extracted_entities={"patient_id": user_id}
        )
        developer_response = await call_agent_api(
            INSTRUCTION_DEVELOPER_AGENT_URL,
            "generate_instruction", # Assuming instruction_developer_agent has this endpoint
            developer_input
        )
        print(f"Developer Agent response: {developer_response}")

        if developer_response.get("status") != "success":
            return AgentResponseInternal(
                status="failure",
                message=f"Instruction Developer failed: {developer_response.get('message', 'Unknown error')}",
                follow_up_required=True
            )

        # Step 2: Use QA Agent to confirm the generated instruction/action
        qa_input = QAInput(
            proposed_action=developer_response.get("proposed_action"),
            action_details=developer_response.get("action_details")
        )
        qa_response = await call_agent_api(
            QA_AGENT_URL,
            "confirm_action", # Assuming qa_agent has this endpoint
            qa_input
        )
        print(f"QA Agent response: {qa_response}")

        if qa_response.get("status") == "rejected":
            # QA agent tried auto-correct, but failed, or requires human intervention
            return AgentResponseInternal(
                status="failure",
                message=f"Action rejected by QA: {qa_response.get('reason', 'Reason unknown')}. Human intervention may be required.",
                follow_up_required=True # Indicate to Master to inform user
            )
        elif qa_response.get("status") == "corrected":
            print(f"QA Agent corrected action: {qa_response.get('corrected_details')}. Proceeding with corrected plan.")
            # Update the action details with QA's corrections
            qa_input.action_details.update(qa_response.get("corrected_details"))

        # Step 3: Based on the task, delegate to the appropriate specialized agent
        final_action_details = qa_input.action_details # Use potentially corrected details

        if instruction.task == "book_appointment" or instruction.task == "reschedule_appointment":
            # Example: Call Scheduler Agent
            scheduler_payload = BaseModel(**final_action_details) # Or a specific model
            scheduler_response = await call_agent_api(
                SCHEDULER_AGENT_URL,
                "handle_booking", # Example endpoint
                scheduler_payload
            )
            return AgentResponseInternal(
                status=scheduler_response.get("status"),
                message=scheduler_response.get("message"),
                data=scheduler_response.get("data", {}),
                follow_up_required=scheduler_response.get("follow_up_required", False)
            )
        elif instruction.task == "register_user" or instruction.task == "login_user":
            # Example: Call Auth Agent
            auth_payload = BaseModel(**final_action_details) # Or a specific model
            auth_response = await call_agent_api(
                AUTH_AGENT_URL,
                "handle_auth", # Example endpoint
                auth_payload
            )
            return AgentResponseInternal(
                status=auth_response.get("status"),
                message=auth_response.get("message"),
                data=auth_response.get("data", {}),
                follow_up_required=auth_response.get("follow_up_required", False)
            )
        # Add more conditions for other tasks (cancel_appointment, etc.)

        return AgentResponseInternal(
            status="failure",
            message=f"Manager Agent doesn't know how to handle task: {instruction.task}",
            follow_up_required=True
        )

    except HTTPException as e:
        return AgentResponseInternal(
            status="failure",
            message=f"An internal error occurred: {e.detail}",
            follow_up_required=True
        )
    except Exception as e:
        print(f"Unexpected error in Manager Agent: {e}")
        return AgentResponseInternal(
            status="failure",
            message="An unexpected error occurred in Manager Agent. Please try again later.",
            follow_up_required=True
        )

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "Manager Agent is healthy"}