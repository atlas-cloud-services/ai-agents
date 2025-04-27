from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import requests
import json
import os

app = FastAPI(title="ACS GMAO AI - Incident Analysis Agent")

MCP_ENDPOINT = os.getenv("MCP_ENDPOINT", "http://localhost:8002")
LLM_ENDPOINT = os.getenv("LLM_ENDPOINT", "http://localhost:8001")

# Agent details
AGENT_NAME = "Incident Analysis Agent"
AGENT_DESCRIPTION = "Analyzes incident reports to identify causes and solutions"
AGENT_CAPABILITIES = ["incident_analysis", "root_cause_identification", "solution_recommendation"]

# Track our registration with MCP
agent_id = None

class IncidentReport(BaseModel):
    id: str
    title: str
    description: str
    created_at: str
    equipment_id: Optional[str] = None
    severity: Optional[str] = None
    status: str
    reported_by: str
    tags: Optional[List[str]] = None

class AnalysisRequest(BaseModel):
    incident: IncidentReport

class AnalysisResponse(BaseModel):
    incident_id: str
    likely_causes: List[str]
    recommended_actions: List[str]
    similar_incidents: List[Dict[str, Any]]
    confidence: float

@app.on_event("startup")
async def startup_event():
    """Register with MCP on startup"""
    global agent_id
    
    registration_data = {
        "name": AGENT_NAME,
        "description": AGENT_DESCRIPTION,
        "endpoint": os.getenv("AGENT_ENDPOINT", "http://localhost:8003"),
        "capabilities": AGENT_CAPABILITIES
    }
    
    try:
        response = requests.post(
            f"{MCP_ENDPOINT}/agents/register",
            json=registration_data
        )
        
        if response.status_code == 200:
            result = response.json()
            agent_id = result.get("agent_id")
            print(f"Successfully registered with MCP. Agent ID: {agent_id}")
        else:
            print(f"Failed to register with MCP: {response.text}")
    except Exception as e:
        print(f"Error registering with MCP: {e}")

@app.get("/")
def read_root():
    return {
        "status": "Incident Analysis Agent is running",
        "registered": agent_id is not None,
        "agent_id": agent_id
    }

@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_incident(request: AnalysisRequest):
    """Analyze an incident report"""
    # This is a placeholder implementation
    # In a real implementation, we would:
    # 1. Extract key information from the incident report
    # 2. Query the LLM for analysis
    # 3. Process and structure the LLM response
    
    # Simple LLM query for demonstration
    try:
        # Create a prompt for the LLM
        prompt = f"""
        Analyze this datacenter incident:
        Title: {request.incident.title}
        Description: {request.incident.description}
        Equipment ID: {request.incident.equipment_id}
        Severity: {request.incident.severity}
        
        Please provide:
        1. Three most likely causes
        2. Three recommended actions
        """
        
        # Query the LLM
        llm_response = requests.post(
            f"{LLM_ENDPOINT}/generate",
            json={"prompt": prompt, "max_length": 512}
        )
        
        if llm_response.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to get response from LLM service")
        
        # Process LLM response (simplified)
        llm_text = llm_response.json().get("text", "")
        
        # Very simple parsing (in reality, you'd want more sophisticated extraction)
        lines = llm_text.split("\n")
        causes = [line for line in lines if "cause" in line.lower()][:3]
        actions = [line for line in lines if "action" in line.lower() or "recommend" in line.lower()][:3]
        
        return {
            "incident_id": request.incident.id,
            "likely_causes": causes if causes else ["Unknown cause"],
            "recommended_actions": actions if actions else ["Investigate further"],
            "similar_incidents": [],  # Placeholder for similar incidents
            "confidence": 0.7  # Placeholder confidence score
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing incident: {str(e)}")