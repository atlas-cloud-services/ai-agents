from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import httpx
import json
import os
import logging

# Import our defined models and analysis function
from .models import IncidentReport, AnalysisResult
from .analyzer import analyze_incident, _init_cache_db

app = FastAPI(title="ACS GMAO AI - Incident Analysis Agent")

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

MCP_ENDPOINT = os.getenv("MCP_ENDPOINT", "http://localhost:8002")
# LLM_ENDPOINT is configured within analyzer.py now

# Agent details
AGENT_NAME = "Incident Analysis Agent"
AGENT_DESCRIPTION = "Analyzes incident reports to identify causes and solutions using LLM and caching"
AGENT_CAPABILITIES = ["incident_analysis", "root_cause_identification", "solution_recommendation", "cached_incident_retrieval"]

# Track our registration with MCP
agent_id = None

@app.on_event("startup")
async def startup_event():
    """Initialize DB and register with MCP on startup"""
    global agent_id
    
    # Initialize the cache database first
    logger.info("Initializing cache database...")
    _init_cache_db()
    logger.info("Cache database initialization attempt complete.")
    
    # Proceed with MCP registration
    agent_endpoint = os.getenv("AGENT_ENDPOINT", "http://localhost:8003")
    registration_data = {
        "name": AGENT_NAME,
        "description": AGENT_DESCRIPTION,
        "endpoint": agent_endpoint,
        "capabilities": AGENT_CAPABILITIES
    }
    
    logger.info(f"Attempting to register with MCP at {MCP_ENDPOINT}...")
    try:
        # Use httpx for potential async compatibility later
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{MCP_ENDPOINT}/agents/register",
                json=registration_data,
                timeout=10.0 # Add a timeout
            )
        
        if response.status_code == 200:
            result = response.json()
            agent_id = result.get("agent_id")
            logger.info(f"Successfully registered with MCP. Agent ID: {agent_id}")
        else:
            logger.error(f"Failed to register with MCP ({response.status_code}): {response.text}")
    except httpx.RequestError as e:
         logger.error(f"Error registering with MCP (Request Error): {e}")
    except Exception as e:
        logger.error(f"Unexpected error registering with MCP: {e}", exc_info=True)

@app.get("/")
def read_root():
    return {
        "status": "Incident Analysis Agent is running",
        "registered": agent_id is not None,
        "agent_id": agent_id
    }

@app.post("/analyze", 
          response_model=AnalysisResult,
          summary="Analyze Incident Report",
          description="Receives an incident report, performs analysis using LLM and caching, and returns structured results including causes, actions, confidence, and insights.",
          responses={
              200: {"description": "Analysis successful"},
              500: {"description": "Internal server error during analysis"}
              # We might add 422 if input validation fails, handled by FastAPI
          }
         )
async def analyze_incident_endpoint(report: IncidentReport) -> AnalysisResult:
    """API Endpoint to analyze an incident report."""
    logger.info(f"Received analysis request for incident ID: {report.incident_id}")
    try:
        # Call the core analysis function from analyzer.py
        analysis_result = await analyze_incident(report)
        logger.info(f"Analysis complete for {report.incident_id}. Source: {analysis_result.analysis_source}")
        # No need to raise HTTPException here usually, as errors are captured in AnalysisResult
        # However, if analyze_incident itself could raise an unhandled exception, a broader try/except might be needed.
        return analysis_result
    except Exception as e:
        # Catch any unexpected errors not handled within analyze_incident
        logger.error(f"Unexpected error in /analyze endpoint for incident {report.incident_id}: {e}", exc_info=True)
        # Return a generic error response or re-raise as HTTPException
        # Creating an AnalysisResult with error is more consistent with the function's design
        return AnalysisResult(
            incident_id=report.incident_id,
            analysis_source="error",
            errors=[f"Unexpected server error: {e}"]
            # Other fields default or are None
        )