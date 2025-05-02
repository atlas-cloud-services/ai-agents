from fastapi import APIRouter, HTTPException, Request
from typing import Dict, Any
import logging

# Use relative imports assuming endpoints.py is in the same dir as models.py and analyzer.py
# Adjust if the structure is different (e.g., api/endpoints.py, needs ..models)
# Assuming structure agents/incident/{main.py, models.py, analyzer.py}
# Needs update if using agents/incident/api/{main.py, endpoints.py}
from models import IncidentReport, AnalysisResult # Changed to absolute import
from analyzer import analyze_incident # Changed to absolute import

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/", summary="Get Agent Status")
async def read_root(request: Request):
    """Returns the running status and registration info of the agent."""
    # Access agent_id from app state if stored there
    agent_id = getattr(request.app.state, 'agent_id', None)
    return {
        "status": "Incident Analysis Agent is running (endpoint check)",
        "registered": agent_id is not None,
        "agent_id": agent_id
    }

@router.post("/analyze", 
          response_model=AnalysisResult,
          summary="Analyze Incident Report",
          description="Receives an incident report, performs analysis using LLM and caching, and returns structured results including causes, actions, confidence, and insights.",
          responses={
              200: {"description": "Analysis successful"},
              500: {"description": "Internal server error during analysis"}
          }
         )
async def analyze_incident_endpoint(report: IncidentReport) -> AnalysisResult:
    """API Endpoint to analyze an incident report."""
    logger.info(f"Received analysis request via API endpoint for incident ID: {report.incident_id}")
    try:
        # Call the core analysis function from analyzer.py
        analysis_result = await analyze_incident(report)
        logger.info(f"Analysis complete for {report.incident_id}. Source: {analysis_result.analysis_source}")
        return analysis_result
    except Exception as e:
        logger.error(f"Unexpected error in /analyze endpoint for incident {report.incident_id}: {e}", exc_info=True)
        # Return a structured error consistent with AnalysisResult
        return AnalysisResult(
            incident_id=report.incident_id,
            analysis_source="error",
            errors=[f"Unexpected server error in endpoint: {e}"]
        ) 