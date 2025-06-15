# auth_agent/main.py

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
import os
import httpx # Useful if this agent needs to call other agents

# Load environment variables from .env file
load_dotenv()

# Initialize the FastAPI application
app = FastAPI(
    title="Auth Agent API",
    description="API for handling user authentication and authorization tasks (registration, login)."
)

# --- Request/Response Models ---
class UserCredentials(BaseModel):
    username: str
    password: str

class UserRegistration(UserCredentials):
    full_name: str
    email: str

class AuthResponse(BaseModel):
    status: str # e.g., "success", "failure"
    message: str
    user_id: str = None
    token: str = None

# --- Placeholder Endpoint: Register User ---
@app.post("/register", response_model=AuthResponse)
async def register_user(user_data: UserRegistration):
    """
    Placeholder endpoint for user registration.
    In a real implementation, this would hash the password and store user details in DB.
    """
    print(f"[Auth Agent] Received registration request for user: {user_data.username}")
    # Basic simulation: Check if user already exists (very simple check for demo)
    if user_data.username == "existing_user":
        return AuthResponse(status="failure", message="User already exists.")

    # Simulate hashing password and storing in DB
    # hashed_password = bcrypt.hashpw(user_data.password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
    # Save user_data (username, hashed_password, full_name, email) to database via DB Agent
    user_id = f"user_{hash(user_data.username)}" # Simple mock ID
    token = "mock_jwt_token_for_auth" # Simulate token generation

    return AuthResponse(
        status="success",
        message=f"User {user_data.username} registered successfully.",
        user_id=user_id,
        token=token
    )

# --- Placeholder Endpoint: Login User ---
@app.post("/login", response_model=AuthResponse)
async def login_user(credentials: UserCredentials):
    """
    Placeholder endpoint for user login.
    In a real implementation, this would verify password and issue a token.
    """
    print(f"[Auth Agent] Received login request for user: {credentials.username}")
    # Basic simulation: Validate credentials (very simple check for demo)
    if credentials.username == "test_user" and credentials.password == "password123":
        user_id = f"user_{hash(credentials.username)}" # Simple mock ID
        token = "mock_jwt_token_for_auth" # Simulate token generation
        return AuthResponse(
            status="success",
            message=f"User {credentials.username} logged in successfully.",
            user_id=user_id,
            token=token
        )
    return AuthResponse(status="failure", message="Invalid username or password.")


# --- Health Check Endpoint ---
@app.get("/health")
async def health_check():
    """
    Health check endpoint for the agent.
    """
    return {"status": f"{app.title} is healthy"}

