# db_agent/main.py

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
import os
import asyncpg # For async PostgreSQL interactions
import json # For handling JSON string data if needed for complex types

# Load environment variables from .env file
load_dotenv()

# Initialize the FastAPI application
app = FastAPI(
    title="DB Agent API",
    description="API for handling all PostgreSQL database interactions (CRUD operations)."
)

# Database connection details from .env
DATABASE_URL = os.getenv("DATABASE_URL")

# --- Database Connection Pool (init on startup) ---
# This will hold the connection pool for PostgreSQL
db_pool = None

@app.on_event("startup")
async def startup_db_pool():
    """Create PostgreSQL connection pool on startup."""
    global db_pool
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL environment variable is not set!")
    try:
        db_pool = await asyncpg.create_pool(DATABASE_URL)
        print("[DB Agent] PostgreSQL connection pool created successfully.")
        # Optional: Run initial schema setup if tables don't exist
        await create_tables()
    except Exception as e:
        print(f"[DB Agent] Failed to connect to PostgreSQL: {e}")
        # Depending on desired behavior, you might want to raise here or exit
        raise HTTPException(status_code=500, detail=f"Database connection error: {e}")

@app.on_event("shutdown")
async def shutdown_db_pool():
    """Close PostgreSQL connection pool on shutdown."""
    if db_pool:
        await db_pool.close()
        print("[DB Agent] PostgreSQL connection pool closed.")

async def create_tables():
    """Create necessary database tables if they don't exist."""
    async with db_pool.acquire() as connection:
        await connection.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id VARCHAR(255) PRIMARY KEY,
                username VARCHAR(255) UNIQUE NOT NULL,
                hashed_password VARCHAR(255) NOT NULL,
                full_name VARCHAR(255),
                email VARCHAR(255) UNIQUE
            );
            CREATE TABLE IF NOT EXISTS appointments (
                appointment_id SERIAL PRIMARY KEY,
                user_id VARCHAR(255) REFERENCES users(user_id),
                doctor_name VARCHAR(255) NOT NULL,
                appointment_date DATE NOT NULL,
                appointment_time TIME NOT NULL,
                reason VARCHAR(512),
                status VARCHAR(50) DEFAULT 'scheduled'
            );
        """)
        print("[DB Agent] Checked/created 'users' and 'appointments' tables.")


# --- Request/Response Models ---
class DBQuery(BaseModel):
    table: str
    action: str # e.g., "insert", "select", "update", "delete"
    data: dict = {} # Data for insert/update
    conditions: dict = {} # Conditions for select/update/delete
    columns: list = [] # Columns to select for "select" action

class DBResponse(BaseModel):
    status: str
    message: str
    results: list = []
    row_count: int = 0


# --- Generic Database Endpoint ---
@app.post("/query", response_model=DBResponse)
async def handle_db_query(query: DBQuery):
    """
    Generic endpoint to handle various database operations.
    """
    if not db_pool:
        raise HTTPException(status_code=500, detail="Database connection pool not initialized.")

    async with db_pool.acquire() as connection:
        try:
            if query.action == "insert":
                columns = ', '.join(query.data.keys())
                placeholders = ', '.join([f'${i+1}' for i in range(len(query.data))])
                values = list(query.data.values())
                sql = f"INSERT INTO {query.table} ({columns}) VALUES ({placeholders}) RETURNING *;"
                result = await connection.fetch_row(sql, *values)
                return DBResponse(status="success", message="Record inserted.", results=[dict(result)] if result else [], row_count=1)

            elif query.action == "select":
                columns = ', '.join(query.columns) if query.columns else '*'
                conditions_sql = []
                condition_values = []
                for i, (key, value) in enumerate(query.conditions.items()):
                    conditions_sql.append(f"{key} = ${i+1}")
                    condition_values.append(value)
                where_clause = f" WHERE {' AND '.join(conditions_sql)}" if conditions_sql else ""
                sql = f"SELECT {columns} FROM {query.table}{where_clause};"
                results = await connection.fetch(sql, *condition_values)
                return DBResponse(status="success", message="Records retrieved.", results=[dict(r) for r in results], row_count=len(results))

            elif query.action == "update":
                set_clauses = []
                set_values = []
                param_counter = 1
                for key, value in query.data.items():
                    set_clauses.append(f"{key} = ${param_counter}")
                    set_values.append(value)
                    param_counter += 1

                conditions_sql = []
                for key, value in query.conditions.items():
                    conditions_sql.append(f"{key} = ${param_counter}")
                    set_values.append(value)
                    param_counter += 1
                
                where_clause = f" WHERE {' AND '.join(conditions_sql)}" if conditions_sql else ""
                sql = f"UPDATE {query.table} SET {', '.join(set_clauses)}{where_clause};"
                status = await connection.execute(sql, *set_values)
                row_count = int(status.split()[-1]) # Extract row count from "UPDATE X"
                return DBResponse(status="success", message=f"Records updated. {row_count} rows affected.", row_count=row_count)

            elif query.action == "delete":
                conditions_sql = []
                condition_values = []
                for i, (key, value) in enumerate(query.conditions.items()):
                    conditions_sql.append(f"{key} = ${i+1}")
                    condition_values.append(value)
                where_clause = f" WHERE {' AND '.join(conditions_sql)}" if conditions_sql else ""
                sql = f"DELETE FROM {query.table}{where_clause};"
                status = await connection.execute(sql, *condition_values)
                row_count = int(status.split()[-1]) # Extract row count from "DELETE X"
                return DBResponse(status="success", message=f"Records deleted. {row_count} rows affected.", row_count=row_count)

            else:
                raise HTTPException(status_code=400, detail="Invalid DB action specified.")

        except Exception as e:
            print(f"[DB Agent] Database operation failed: {e}")
            raise HTTPException(status_code=500, detail=f"Database error: {e}")


# --- Health Check Endpoint ---
@app.get("/health")
async def health_check():
    """
    Health check endpoint for the agent.
    """
    return {"status": f"{app.title} is healthy"}

