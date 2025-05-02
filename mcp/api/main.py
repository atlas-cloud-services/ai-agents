from fastapi import FastAPI, HTTPException, status
import logging
from dotenv import load_dotenv

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables BEFORE accessing them for imports if needed
load_dotenv()

# Import the registry
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from orchestration.registry import registry, AgentInfo

# Import the API router
from .endpoints import router as api_router

app = FastAPI(
    title="ACS GMAO AI - Master Control Program (MCP)",
    description="The Master Control Program orchestrates communication and tasks among various AI agents.",
    version="0.2.0"
)

# Include the API router
app.include_router(api_router, prefix="/api")

# Add a root status endpoint for the main app
@app.get("/status", summary="Get MCP Root Status")
def read_root_status():
    """Returns the root status and version of the MCP."""
    return {"status": "MCP is running", "version": app.version, "detail": "Check /api/ for detailed endpoints."}

# --- Helper for Running (if main script) ---
# (Consider using a separate run script or docker compose)
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8002, reload=True)