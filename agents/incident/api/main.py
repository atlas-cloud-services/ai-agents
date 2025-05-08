from fastapi import FastAPI
# Removed HTTPException, models
# Removed List, Optional, Dict, Any
import httpx
import json
import os
import logging
from contextlib import asynccontextmanager
from dotenv import load_dotenv # Import load_dotenv

# Import needed parts from local modules
# Adjust paths if main.py is in api/
# Load .env before potentially accessing env vars for imports/config
load_dotenv()

from analyzer import _init_cache_db # Changed to absolute import
from .endpoints import router as api_router # Assuming endpoints is in api/

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Move configuration here
MCP_ENDPOINT = os.getenv("MCP_ENDPOINT", "http://localhost:8002/api") # Add /api prefix
AGENT_ENDPOINT = os.getenv("AGENT_ENDPOINT", "http://localhost:8003/api") # Add /api prefix if agent serves on it
AGENT_NAME = "Incident Analysis Agent"
AGENT_DESCRIPTION = "Analyzes incident reports to identify causes and solutions using LLM and caching"
AGENT_CAPABILITIES = ["incident_analysis", "root_cause_identification", "solution_recommendation", "cached_incident_retrieval"]

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage agent registration and DB initialization."""
    # Initialize DB first
    logger.info("Initializing cache database...")
    try:
        # Assuming _init_cache_db handles its own errors adequately
        _init_cache_db()
        logger.info("Cache database initialization attempt complete.")
    except Exception as db_e:
        logger.error(f"Failed to initialize DB during startup: {db_e}", exc_info=True)
        # Decide if the app should proceed without DB

    # Register with MCP
    registration_data = {
        "name": AGENT_NAME,
        "description": AGENT_DESCRIPTION,
        "endpoint": AGENT_ENDPOINT, # Use configured agent endpoint
        "capabilities": AGENT_CAPABILITIES
    }
    
    logger.info(f"Attempting to register with MCP at {MCP_ENDPOINT}...")
    agent_id = None
    try:
        async with httpx.AsyncClient() as client:
            # Target the correct MCP registration endpoint (assuming /api prefix)
            mcp_register_url = f"{MCP_ENDPOINT.rstrip('/')}/agents/register"
            response = await client.post(mcp_register_url, json=registration_data, timeout=15.0)
        
        # Check specific success code (e.g., 201 Created)
        if response.status_code == 201:
            result = response.json()
            agent_id = result.get("agent_id")
            logger.info(f"Successfully registered with MCP. Agent ID: {agent_id}")
        else:
            logger.error(f"Failed to register with MCP ({response.status_code}): {response.text}")
            # Consider retries or alternative actions
    except httpx.RequestError as e:
         logger.error(f"Error registering with MCP (Request Error): {e}")
    except Exception as e:
        logger.error(f"Unexpected error registering with MCP: {e}", exc_info=True)
    
    # Store agent_id in app state for endpoints to access
    app.state.agent_id = agent_id
    
    yield
    
    # Cleanup on shutdown (e.g., unregister from MCP - optional)
    logger.info("Incident Analysis Agent shutting down.")
    # Add unregistration logic here if needed

app = FastAPI(
    title="ACS GMAO AI - Incident Analysis Agent", 
    lifespan=lifespan
)

# Include the router
app.include_router(api_router, prefix="/api") # Add /api prefix

# Add a root status endpoint
@app.get("/status", summary="Get Agent Root Status")
def read_root_status():
    return {
        "status": "Incident Analysis Agent is running.",
        "detail": "Check /api/ for details and analysis endpoint."
    }

# Allow running with uvicorn
if __name__ == "__main__":
    import uvicorn
    # Point to the app object within this file
    # Adjust module path if structure changes (e.g., "api.main:app")
    uvicorn.run("main:app", host="0.0.0.0", port=8003, reload=True) 