# scheduler_agent/main.py

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
import os
import httpx
from datetime import date, time, datetime, timedelta

# Load environment variables from .env file
load_dotenv()

app = FastAPI(
    title="Scheduler Agent API",
    description="Manages appointment scheduling logic, conflicts, and availability."
)

# URL for the DB Agent
DB_AGENT_URL = os.getenv("DB_AGENT_URL", "http://db_agent:8000")

# --- Request/Response Models ---
class AppointmentDetails(BaseModel):
    user_id: str
    patient_name: str
    doctor_name: str
    appointment_date: str # YYYY-MM-DD
    appointment_time: str # HH:MM
    reason: str

class BookingResponse(BaseModel):
    status: str # "success", "failure"
    message: str
    appointment_id: int = None
    confirmation_details: dict = {}

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


# --- Endpoint to Handle Booking ---
@app.post("/handle_booking", response_model=BookingResponse)
async def handle_booking(details: AppointmentDetails):
    """
    Handles booking a new appointment or rescheduling an existing one.
    This will interact with the DB Agent.
    """
    print(f"[Scheduler Agent] Attempting to book/reschedule appointment for {details.patient_name} with {details.doctor_name}")

    try:
        # Step 1: Check for existing appointments/availability using DB Agent
        # In a real scenario, this would be more sophisticated, checking doctor's schedule, etc.
        db_query_payload = {
            "table": "appointments",
            "action": "select",
            "conditions": {
                "doctor_name": details.doctor_name,
                "appointment_date": details.appointment_date,
                "appointment_time": details.appointment_time
            },
            "columns": ["appointment_id"]
        }
        db_response = await call_agent_api(DB_AGENT_URL, "query", BaseModel(**db_query_payload))

        if db_response.get("status") == "success" and db_response.get("row_count", 0) > 0:
            return BookingResponse(status="failure", message="This time slot is already booked for this doctor.")

        # Step 2: Proceed with booking (insert into DB)
        appointment_data = {
            "user_id": details.user_id,
            "doctor_name": details.doctor_name,
            "appointment_date": details.appointment_date,
            "appointment_time": details.appointment_time,
            "reason": details.reason,
            "status": "scheduled"
        }
        db_insert_payload = {
            "table": "appointments",
            "action": "insert",
            "data": appointment_data
        }
        db_response = await call_agent_api(DB_AGENT_URL, "query", BaseModel(**db_insert_payload))

        if db_response.get("status") == "success" and db_response.get("row_count", 0) > 0:
            new_appointment_id = db_response.get("results", [{}])[0].get("appointment_id")
            return BookingResponse(
                status="success",
                message=f"Appointment booked successfully for {details.patient_name} with {details.doctor_name} on {details.appointment_date} at {details.appointment_time}.",
                appointment_id=new_appointment_id,
                confirmation_details={
                    "patient_name": details.patient_name,
                    "doctor_name": details.doctor_name,
                    "date": details.appointment_date,
                    "time": details.appointment_time,
                    "reason": details.reason,
                    "appointment_id": new_appointment_id
                }
            )
        else:
            return BookingResponse(status="failure", message="Failed to book appointment in database.")

    except HTTPException as e:
        return BookingResponse(status="failure", message=f"Error in Scheduler Agent: {e.detail}")
    except Exception as e:
        print(f"[Scheduler Agent] Unexpected error: {e}")
        return BookingResponse(status="failure", message="An unexpected error occurred during scheduling.")


# --- Endpoint to Handle Cancellation ---
@app.post("/handle_cancellation", response_model=BookingResponse)
async def handle_cancellation(appointment_id: int):
    """
    Handles canceling an existing appointment.
    """
    print(f"[Scheduler Agent] Attempting to cancel appointment ID: {appointment_id}")

    try:
        # Step 1: Check if appointment exists
        db_select_payload = {
            "table": "appointments",
            "action": "select",
            "conditions": {"appointment_id": appointment_id},
            "columns": ["status"]
        }
        db_response = await call_agent_api(DB_AGENT_URL, "query", BaseModel(**db_select_payload))

        if db_response.get("status") == "success" and db_response.get("row_count", 0) == 0:
            return BookingResponse(status="failure", message=f"Appointment with ID {appointment_id} not found.")
        
        current_status = db_response.get("results", [{}])[0].get("status")
        if current_status == "cancelled":
            return BookingResponse(status="failure", message=f"Appointment with ID {appointment_id} is already cancelled.")


        # Step 2: Update appointment status to cancelled
        db_update_payload = {
            "table": "appointments",
            "action": "update",
            "data": {"status": "cancelled"},
            "conditions": {"appointment_id": appointment_id}
        }
        db_response = await call_agent_api(DB_AGENT_URL, "query", BaseModel(**db_update_payload))

        if db_response.get("status") == "success" and db_response.get("row_count", 0) > 0:
            return BookingResponse(
                status="success",
                message=f"Appointment ID {appointment_id} cancelled successfully.",
                appointment_id=appointment_id
            )
        else:
            return BookingResponse(status="failure", message="Failed to cancel appointment in database.")

    except HTTPException as e:
        return BookingResponse(status="failure", message=f"Error in Scheduler Agent: {e.detail}")
    except Exception as e:
        print(f"[Scheduler Agent] Unexpected error during cancellation: {e}")
        return BookingResponse(status="failure", message="An unexpected error occurred during cancellation.")


# --- Health Check Endpoint ---
@app.get("/health")
async def health_check():
    """
    Health check endpoint for the agent.
    """
    return {"status": f"{app.title} is healthy"}

