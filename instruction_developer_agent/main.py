# instruction_developer_agent/main.py

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
import os
import httpx

# Load environment variables from .env file
load_dotenv()

app = FastAPI(
    title="Instruction Developer Agent API",
    description="Generates detailed, executable instructions based on high-level plans."
)

# --- Request/Response Models ---
class DeveloperInstruction(BaseModel):
    task_type: str # e.g., "book_appointment", "register_user"
    raw_input: str # Original user message
    extracted_entities: dict = {} # Entities potentially pre-extracted by Manager

class DevelopedInstruction(BaseModel):
    status: str # "success", "failure"
    message: str
    proposed_action: str # e.g., "book_appointment_with_details"
    action_details: dict # Detailed parameters for the action


# --- Endpoint to Generate Instructions ---
@app.post("/generate_instruction", response_model=DevelopedInstruction)
async def generate_instruction(instruction: DeveloperInstruction):
    """
    Takes a high-level task and raw input to develop detailed, executable instructions.
    This will involve an LLM call to gemini-1.5-flash for complex parsing and generation.
    """
    print(f"[Instruction Developer] Developing instruction for task: {instruction.task_type}")
    print(f"Original input: '{instruction.raw_input}'")
    print(f"Pre-extracted entities: {instruction.extracted_entities}")

    # Placeholder for LLM call to gemini-1.5-flash
    # You would typically craft a prompt here to instruct the LLM to parse the
    # raw_input and extracted_entities to generate structured action_details.

    # Example prompt structure for LLM:
    # prompt = f"""
    # You are an Instruction Developer AI. Your task is to generate a precise JSON object
    # representing an action and its details based on a user's request.
    # User's request: "{instruction.raw_input}"
    # Detected task type: "{instruction.task_type}"
    # Known entities (if any): {json.dumps(instruction.extracted_entities)}

    # Based on the above, create a JSON object with two keys:
    # 1. "proposed_action": A string describing the specific action to take (e.g., "book_appointment", "register_user", "cancel_appointment").
    # 2. "action_details": A dictionary containing all necessary parameters for that action.
    #    For "book_appointment", include "patient_name", "doctor_name", "date", "time", "reason".
    #    For "register_user", include "username", "password", "full_name", "email".
    #    If any information is missing, set relevant fields to null or clearly state "missing".

    # Example for booking:
    # {{
    #     "proposed_action": "book_appointment",
    #     "action_details": {{
    #         "patient_name": "John Doe",
    #         "doctor_name": "Dr. Smith",
    #         "date": "2025-07-15",
    #         "time": "14:00",
    #         "reason": "General check-up"
    #     }}
    # }}

    # Example for registration:
    # {{
    #     "proposed_action": "register_user",
    #     "action_details": {{
    #         "username": "johndoe",
    #         "password": "securepassword123",
    #         "full_name": "John Doe",
    #         "email": "john.doe@example.com"
    #     }}
    # }}
    # Ensure the output is valid JSON.
    # """

    # Here, we'll simulate the LLM response with hardcoded logic for demonstration.
    proposed_action = instruction.task_type
    action_details = {"user_id": instruction.extracted_entities.get("user_id")} # Start with known user_id

    if instruction.task_type == "book_appointment":
        # Simple entity extraction for demo purposes, LLM would do this robustly
        action_details.update({
            "patient_name": instruction.raw_input.split("for")[-1].strip().split("with")[0].strip() if "for" in instruction.raw_input else "Unknown Patient",
            "doctor_name": instruction.raw_input.split("with")[-1].strip().split("on")[0].strip() if "with" in instruction.raw_input else "Any Doctor",
            "appointment_date": "2025-06-15" if "tomorrow" in instruction.raw_input else "2025-06-XX", # Placeholder
            "appointment_time": "10:00" if "morning" in instruction.raw_input else "Any Time", # Placeholder
            "reason": "General check-up"
        })
        message = "Appointment details developed."
    elif instruction.task_type == "register_user":
        action_details.update({
            "username": "new_user_" + str(hash(instruction.raw_input))[:5], # Mock username
            "password": "StrongPassword!1", # Mock password
            "full_name": "New Clinic User",
            "email": "new_user@example.com"
        })
        message = "User registration details developed."
    elif instruction.task_type == "login_user":
        action_details.update({
            "username": "test_user", # Mock username
            "password": "password123" # Mock password
        })
        message = "User login details developed."
    else:
        message = f"Instruction development not fully implemented for: {instruction.task_type}"
        return DevelopedInstruction(status="failure", message=message, proposed_action="unknown", action_details={})


    return DevelopedInstruction(
        status="success",
        message=message,
        proposed_action=proposed_action,
        action_details=action_details
    )


# --- Health Check Endpoint ---
@app.get("/health")
async def health_check():
    """
    Health check endpoint for the agent.
    """
    return {"status": f"{app.title} is healthy"}
