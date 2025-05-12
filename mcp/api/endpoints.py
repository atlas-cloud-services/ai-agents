from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import time
import logging
import uuid
import os
import httpx
from fastapi import Header, BackgroundTasks
import datetime
import asyncio

# Assuming registry and route_message_to_agents are accessible
# This might require adjustments based on actual project structure
# If they are in the parent dir, relative imports might work or sys.path manipulation needed
try:
    from orchestration.registry import registry, AgentInfo, AGENT_REQUEST_TIMEOUT
    from orchestration.router import route_message_to_agents
except ImportError:
    # Fallback or raise error if running endpoints standalone isn't intended
    # For now, let's assume they are available via the app context if needed
    # Or define dummy placeholders if needed for linting/type checking
    class AgentInfoPlaceholder(BaseModel):
        id: str
        name: str
    registry = None # Placeholder
    async def route_message_to_agents(capability: str, message_payload: Dict): return {} # Placeholder
    AGENT_REQUEST_TIMEOUT = 15 # Placeholder for timeout value, align with actual if defined
    AgentInfo = AgentInfoPlaceholder # Use placeholder if import fails

logger = logging.getLogger(__name__)
router = APIRouter()

# --- API Models (Moved from main.py) ---
class RegisterAgentRequest(BaseModel):
    name: str
    description: str
    endpoint: str
    capabilities: List[str]

class RegisterAgentResponse(BaseModel):
    agent_id: str
    status: str = "success"

class MessageRequest(BaseModel):
    content: Dict[str, Any] # Changed to Dict for more flexible message content
    target_capability: str  # Made mandatory for routing
    source_agent_id: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None

class AgentResponseData(BaseModel):
    """Structure for reporting individual agent responses or errors."""
    agent_id: str
    status_code: Optional[int] = None
    response_body: Optional[Any] = None
    error: Optional[str] = None

class MessageResponse(BaseModel):
    message_id: str
    status: str
    responses: List[AgentResponseData] = [] # Use the new structure

# Endpoint for agent health checks / heartbeat (Moved from main.py)
class HeartbeatRequest(BaseModel):
    status: str = "ok"

# --- Endpoints ---
@router.get("/", summary="Get MCP Status")
def read_root():
    """Returns the current status of the MCP (from endpoints)."""
    # Access app version if needed via Request injection or keep simple
    return {"status": "MCP is running (endpoint check)"}

@router.post("/agents/register", 
            response_model=RegisterAgentResponse, 
            status_code=status.HTTP_201_CREATED,
            summary="Register a New Agent",
            description="Registers a new AI agent with the MCP, providing its metadata and capabilities.")
async def register_agent(request: RegisterAgentRequest):
    """Registers a new agent with the central registry."""
    if not registry: raise HTTPException(503, "Registry not initialized")
    try:
        agent_id = registry.register_agent(
            name=request.name,
            description=request.description,
            endpoint=request.endpoint,
            capabilities=request.capabilities
        )
        logger.info(f"Registered new agent: {request.name} (ID: {agent_id})")
        return {"agent_id": agent_id, "status": "registered"}
    except Exception as e:
        logger.error(f"Failed to register agent {request.name}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to register agent")

@router.get("/agents", 
         response_model=List[AgentInfo],
         summary="List All Registered Agents",
         description="Retrieves a list of all agents currently registered with the MCP.")
async def get_all_agents():
    """Returns a list of all agents in the registry."""
    if not registry: raise HTTPException(503, "Registry not initialized")
    return registry.get_all_agents()

@router.get("/agents/{agent_id}", 
         response_model=AgentInfo,
         summary="Get Agent Details",
         description="Retrieves detailed information about a specific agent by its ID.",
         responses={404: {"description": "Agent not found"}})
async def get_agent(agent_id: str):
    """Returns details for a specific agent ID."""
    if not registry: raise HTTPException(503, "Registry not initialized")
    agent = registry.get_agent(agent_id)
    if not agent:
        logger.warning(f"Attempted to access non-existent agent ID: {agent_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent with ID {agent_id} not found")
    return agent

@router.post("/message", 
          response_model=MessageResponse,
          summary="Route Message to Agents",
          description="Receives a message and routes it to all registered agents matching the target capability.",
          responses={
              400: {"description": "Missing target capability"},
              503: {"description": "Error during agent communication"}
          })
async def process_message(request: MessageRequest):
    """Processes and routes a message to agents based on capability."""
    message_id = f"msg_{uuid.uuid4()}" # Use UUID for better uniqueness
    logger.info(f"Received message {message_id} for capability: {request.target_capability}")

    payload_to_forward = {
        "content": request.content,
        "metadata": request.metadata,
        "source_agent_id": request.source_agent_id
    }

    try:
        agent_responses_dict = await route_message_to_agents(
            capability=request.target_capability,
            message_payload=payload_to_forward
        )
    except Exception as e:
        logger.error(f"Failed to initiate routing for message {message_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, 
                            detail="Failed to route message to agents")

    formatted_responses: List[AgentResponseData] = []
    for agent_id, response_data in agent_responses_dict.items():
        if isinstance(response_data, Exception):
            error_msg = f"{type(response_data).__name__}: {str(response_data)}"
            logger.warning(f"Error response from agent {agent_id} for message {message_id}: {error_msg}")
            formatted_responses.append(AgentResponseData(agent_id=agent_id, error=error_msg))
        elif isinstance(response_data, dict):
            logger.debug(f"Successful response from agent {agent_id} for message {message_id}")
            formatted_responses.append(AgentResponseData(agent_id=agent_id, response_body=response_data))
        else:
             error_msg = f"Unexpected response type from agent: {type(response_data).__name__}"
             logger.error(f"Unexpected response from agent {agent_id} for message {message_id}: {response_data}")
             formatted_responses.append(AgentResponseData(agent_id=agent_id, error=error_msg))

    logger.info(f"Processed message {message_id}. Returning {len(formatted_responses)} responses.")
    return {
        "message_id": message_id,
        "status": "processed",
        "responses": formatted_responses
    }

@router.put("/agents/{agent_id}/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
async def agent_heartbeat(agent_id: str, request: HeartbeatRequest):
    """Allows agents to report their status (heartbeat)."""
    if not registry: raise HTTPException(503, "Registry not initialized")
    agent = registry.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent {agent_id} not registered")
    
    # Update last heartbeat time and potentially status
    registry.agents[agent_id].last_heartbeat = time.time()
    if agent.status != "active": # Reactivate if it was inactive
         registry.update_agent_status(agent_id, "active")
         logger.info(f"Agent {agent.name} ({agent_id}) reactivated via heartbeat.")
    # No response body needed for 204
    return

# --- Webhook Endpoint for GMAO Incidents ---

# TODO: Move these to a proper config module or load from environment variables securely
# Example: GMAO_WEBHOOK_API_KEY = os.getenv("GMAO_WEBHOOK_API_KEY")
# Example: INCIDENT_AGENT_URL = os.getenv("INCIDENT_AGENT_URL", "http://incident-agent/api/analyze")

# Import Pydantic models
from pydantic import BaseModel, Field

# Import registry and other MCP components (adjust paths as needed)
from orchestration.registry import registry
from agents.incident.models import IncidentReport, AnalysisResult, LLMStructuredResponse, ActionableInsight

# Import webhook models (adjust path if models are in a different location within mcp)
from models.webhook import GmaoWebhookPayload, WebhookResponse

GMAO_WEBHOOK_API_KEY = os.getenv("GMAO_WEBHOOK_API_KEY", "your-secret-gmao-api-key") # Replace with secure retrieval
INCIDENT_AGENT_URL = os.getenv("INCIDENT_AGENT_URL", "http://localhost:8003/api/analyze") # Agent's /analyze endpoint

# Configuration for GMAO Callback
GMAO_CALLBACK_URL = os.getenv("GMAO_CALLBACK_URL")
GMAO_CALLBACK_API_KEY = os.getenv("GMAO_CALLBACK_API_KEY")
CALLBACK_MAX_ATTEMPTS = int(os.getenv("GMAO_CALLBACK_MAX_ATTEMPTS", "3"))
CALLBACK_RETRY_DELAYS_SECONDS_STR = os.getenv("GMAO_CALLBACK_RETRY_DELAYS_SECONDS", "5,10")
CALLBACK_RETRY_DELAYS_SECONDS = [int(d.strip()) for d in CALLBACK_RETRY_DELAYS_SECONDS_STR.split(',')]
CALLBACK_TIMEOUT_SECONDS = float(os.getenv("GMAO_CALLBACK_TIMEOUT_SECONDS", "60.0"))

MAX_FORWARD_ATTEMPTS = 3
RETRY_DELAYS_SECONDS = [5, 10] # Delay after 1st, 2nd failed attempt respectively

# --- Add new environment variable for MCP to Agent timeout ---
# Default to 630 seconds (10.5 minutes), slightly longer than agent's default LLM timeout
MCP_TO_AGENT_TIMEOUT = float(os.getenv("MCP_TO_AGENT_TIMEOUT", "630.0"))

async def verify_api_key(x_gmao_token: str = Header(None)):
    """Dependency to verify the API key from the header."""
    if not x_gmao_token:
        logger.warning("Missing X-GMAO-Token header for webhook.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing API Key",
            headers={"WWW-Authenticate": "Header X-GMAO-Token"},
        )
    if x_gmao_token != GMAO_WEBHOOK_API_KEY:
        logger.warning("Invalid API Key received for webhook.")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid API Key",
            headers={"WWW-Authenticate": "Header X-GMAO-Token"},
        )
    return x_gmao_token # Or just True, value not typically used

def map_gmao_to_incident_report(gmao_payload: GmaoWebhookPayload) -> IncidentReport:
    """Maps the GMAO webhook payload (based on Django Incident model) to the IncidentReport format."""
    logger.debug(f"Mapping GMAO payload for external ID: {gmao_payload.external_incident_id}")
    
    # Priority mapping (GMAO text to internal integer)
    priority_map = {
        "low": 3,    # Adjust numbers as per your internal system's definition
        "medium": 2,
        "high": 1,
        # Add other GMAO priority text values if they exist, e.g., "critical"
    }
    internal_priority = None
    if gmao_payload.priority:
        internal_priority = priority_map.get(gmao_payload.priority.lower())
        if internal_priority is None:
            logger.warning(f"Unknown GMAO priority '{gmao_payload.priority}' for incident {gmao_payload.external_incident_id}. Setting to None.")

    # Construct a detailed description for the internal report
    # Include title, original description, status, image_url, and gmao_link if present
    description_parts = [gmao_payload.title, "\n\n" + gmao_payload.description]
    description_parts.append(f"\n\nGMAO Status: {gmao_payload.status}")
    if gmao_payload.image_url:
        description_parts.append(f"\nGMAO Image: {gmao_payload.image_url}")
    if gmao_payload.gmao_link:
        description_parts.append(f"\nGMAO Link: {gmao_payload.gmao_link}")
    if gmao_payload.additional_data:
        description_parts.append(f"\n\nAdditional GMAO Data: {str(gmao_payload.additional_data)}")
    
    full_description = "".join(description_parts)

    report = IncidentReport(
        incident_id=gmao_payload.external_incident_id, # Using GMAO's incident ID
        timestamp=gmao_payload.incident_created_at,    # Using when incident was created in GMAO
        description=full_description,
        priority=internal_priority,
        affected_systems=gmao_payload.affected_services, # Direct mapping if field names match
        reporter=gmao_payload.reported_by_gmao_user_id   # Using GMAO user ID as reporter
    )
    logger.info(f"Successfully mapped GMAO incident {gmao_payload.external_incident_id} (Title: {gmao_payload.title}) to internal format.")
    return report

async def forward_incident_to_agent(incident_report: IncidentReport, tracking_id: str, original_external_incident_id: str):
    # Ensure tracking_id is used consistently in logging
    logger.info(f"[{tracking_id}] Forwarding incident {incident_report.incident_id} (external: {original_external_incident_id}) to agent at {INCIDENT_AGENT_URL}")

    if not INCIDENT_AGENT_URL:
        logger.error(f"[{tracking_id}] INCIDENT_AGENT_URL is not configured. Cannot forward incident {incident_report.incident_id}.")
        # Send error callback to GMAO if agent URL is missing
        error_payload = GMAOCallbackPayload(
            external_incident_id=original_external_incident_id,
            analysis_summary="MCP configuration error: Incident Analysis Agent URL not set.",
            status="error_mcp_config",
            recommended_actions=[],
            confidence_score=None,
            mcp_tracking_id=tracking_id
        )
        await send_analysis_to_gmao(error_payload, tracking_id)
        return

    agent_analysis_result: Optional[AnalysisResult] = None

    for attempt in range(1, MAX_FORWARD_ATTEMPTS + 1):
        try:
            # Use the new MCP_TO_AGENT_TIMEOUT for the client call to the incident agent
            async with httpx.AsyncClient(timeout=MCP_TO_AGENT_TIMEOUT) as client:
                logger.debug(f"[{tracking_id}] Forwarding attempt {attempt}/{MAX_FORWARD_ATTEMPTS} for incident {incident_report.incident_id} to agent. MCP Timeout: {MCP_TO_AGENT_TIMEOUT}s")
                response = await client.post(INCIDENT_AGENT_URL, json=incident_report.model_dump(mode="json"))
                logger.debug(f"[{tracking_id}] Agent responded with status: {response.status_code}") # DEBUG: Log agent status code
                response.raise_for_status()
                logger.info(f"[{tracking_id}] Successfully forwarded incident {incident_report.incident_id} to agent on attempt {attempt}. Response status: {response.status_code}") # Ensure tracking_id used
                
                # --- START ENHANCED LOGGING ---
                logger.info(f"[{tracking_id}] Agent responded successfully. Attempting to parse response for incident {incident_report.incident_id}.")
                try:
                    agent_response_json = response.json()
                    # DEBUG: Log the raw JSON received from the agent
                    logger.debug(f"[{tracking_id}] Agent raw response JSON: {agent_response_json}")
                    # Use model_validate for Pydantic v2+
                    agent_analysis_result = AnalysisResult.model_validate(agent_response_json)
                    logger.info(f"[{tracking_id}] Successfully parsed AnalysisResult for {incident_report.incident_id}. Source: {agent_analysis_result.analysis_source if agent_analysis_result else 'N/A'}")
                except Exception as parse_exc:
                    logger.error(f"[{tracking_id}] FAILED to parse AnalysisResult from agent for incident {incident_report.incident_id}: {parse_exc}", exc_info=True)
                    # Assign error result but continue to callback logic below if desired
                    agent_analysis_result = AnalysisResult(
                        incident_id=incident_report.incident_id, # Use the internal ID here
                        errors=[f"MCP: Failed to parse agent response: {str(parse_exc)}"],
                        analysis_source="error_parsing_mcp",
                        actionable_insights=[], # Ensure list is initialized
                        parsed_response=None   # Ensure optional fields are None if not available
                    )
                    # Decide if we should break here or attempt callback with the error status
                    logger.warning(f"[{tracking_id}] Proceeding to callback despite agent response parsing error.")
                # --- END ENHANCED LOGGING ---
                break # Exit retry loop on successful agent communication (even if parsing failed, we might want to report that)
        except httpx.RequestError as e:
            logger.warning(f"[{tracking_id}] Request error on attempt {attempt}/{MAX_FORWARD_ATTEMPTS} forwarding incident {incident_report.incident_id} to agent: {e}")
            if attempt == MAX_FORWARD_ATTEMPTS:
                logger.error(f"[{tracking_id}] Final attempt failed. Request error forwarding incident {incident_report.incident_id} to agent: {e}", exc_info=True)
        except httpx.HTTPStatusError as e:
            logger.warning(f"[{tracking_id}] HTTP error {e.response.status_code} on attempt {attempt}/{MAX_FORWARD_ATTEMPTS} forwarding incident {incident_report.incident_id} to agent: {e.response.text[:200]}")
            # For agent communication, typically don't retry 4xx errors as they indicate a problem with the request itself or agent-side rejection
            if e.response.status_code < 500 and e.response.status_code not in [408, 429]: # 408 Request Timeout, 429 Too Many Requests
                logger.error(f"[{tracking_id}] Non-retryable HTTP error {e.response.status_code} from agent for incident {incident_report.incident_id}. Aborting forward.", exc_info=True)
                agent_analysis_result = AnalysisResult(
                    incident_id=incident_report.incident_id,
                    errors=[f"MCP: Agent returned non-retryable HTTP error {e.response.status_code}: {e.response.text[:100]}"],
                    analysis_source="error_agent_response",
                    actionable_insights=[],
                    parsed_response=None
                )
                break # Stop retrying for client-side errors from agent
                if attempt == MAX_FORWARD_ATTEMPTS:
                    logger.error(f"[{tracking_id}] Final attempt failed. HTTP error forwarding incident {incident_report.incident_id} to agent: {e.response.status_code}", exc_info=True)
        except Exception as e: # Catch-all for other unexpected errors during agent communication
            logger.error(f"[{tracking_id}] Unexpected error on attempt {attempt}/{MAX_FORWARD_ATTEMPTS} forwarding incident {incident_report.incident_id} to agent: {e}", exc_info=True)
            if attempt == MAX_FORWARD_ATTEMPTS:
                logger.error(f"[{tracking_id}] Final attempt failed with unexpected error forwarding incident {incident_report.incident_id} to agent.", exc_info=True)

        if attempt < MAX_FORWARD_ATTEMPTS:
            # Use existing RETRY_DELAYS_SECONDS for agent forwarding
            delay_index = min(attempt - 1, len(RETRY_DELAYS_SECONDS) - 1)
            delay = RETRY_DELAYS_SECONDS[delay_index]
            logger.info(f"[{tracking_id}] Retrying agent forward in {delay}s...")
            await asyncio.sleep(delay)

    # --- START ENHANCED LOGGING ---
    logger.info(f"[{tracking_id}] Finished agent communication attempts. Result received: {'Yes' if agent_analysis_result else 'No'}")
    # --- END ENHANCED LOGGING ---

    # After attempting to contact the agent (or if it was skipped):
    if agent_analysis_result:
        # --- START ENHANCED LOGGING ---
        logger.info(f"[{tracking_id}] AnalysisResult is available. Preparing to send analysis results back to GMAO for external incident ID: {original_external_incident_id}")
        try:
            gmao_payload = transform_to_gmao_format(agent_analysis_result, original_external_incident_id, tracking_id)
            logger.info(f"[{tracking_id}] Payload transformed successfully for GMAO callback.")
            # DEBUG: Log the payload going to GMAO (might be verbose)
            logger.debug(f"[{tracking_id}] GMAO Callback Payload: {gmao_payload.model_dump_json(indent=2)}")
            logger.info(f"[{tracking_id}] Initiating call to send_analysis_to_gmao.")
            callback_success = await send_analysis_to_gmao(gmao_payload, tracking_id)
            if callback_success:
                logger.info(f"[{tracking_id}] Successfully initiated and completed callback sequence to GMAO for {original_external_incident_id}.")
            else:
                logger.error(f"[{tracking_id}] Callback sequence to GMAO for {original_external_incident_id} failed (send_analysis_to_gmao returned False).")
        except Exception as transform_send_exc:
             logger.error(f"[{tracking_id}] Error during transformation or sending callback for {original_external_incident_id}: {transform_send_exc}", exc_info=True)
        # --- END ENHANCED LOGGING ---
    elif INCIDENT_AGENT_URL: # Only if URL was configured and we didn't get a result
         # --- START ENHANCED LOGGING ---
         logger.error(f"[{tracking_id}] No AnalysisResult object available after agent communication for incident {incident_report.incident_id}. Attempting error callback to GMAO.")
         # --- END ENHANCED LOGGING ---
         error_payload = GMAOCallbackPayload(
             external_incident_id=original_external_incident_id,
             analysis_summary="Failed to obtain a valid analysis from the incident agent after multiple attempts.",
             status="error_agent_unavailable_or_invalid_response",
             recommended_actions=[],
             confidence_score=None,
             mcp_tracking_id=tracking_id
         )
         # --- START ENHANCED LOGGING ---
         logger.info(f"[{tracking_id}] Initiating ERROR call to send_analysis_to_gmao.")
         # --- END ENHANCED LOGGING ---
         await send_analysis_to_gmao(error_payload, tracking_id)
    else:
        # Log if INCIDENT_AGENT_URL wasn't set (already handled earlier, but good for clarity)
        logger.info(f"[{tracking_id}] INCIDENT_AGENT_URL was not configured, skipping agent communication and callback attempts.")

# --- Pydantic Model for GMAO Callback ---
class GMAOCallbackPayload(BaseModel):
    external_incident_id: str = Field(..., description="Original Incident ID from GMAO.")
    analysis_summary: str = Field(..., description="Summary of the analysis performed.")
    confidence_score: Optional[float] = Field(None, description="Confidence score of the analysis (0.0 to 1.0).")
    recommended_actions: List[str] = Field(default_factory=list, description="List of recommended actions.")
    status: str = Field(..., description="Status of the analysis (e.g., 'analyzed', 'error_in_analysis', 'error_in_callback').")
    analysis_timestamp: Optional[datetime.datetime] = None
    mcp_tracking_id: Optional[str] = Field(None, description="MCP's internal tracking ID for this incident process.")

# --- Helper function to transform AnalysisResult to GMAO format ---
def transform_to_gmao_format(
    analysis_result: AnalysisResult,
    original_external_incident_id: str,
    mcp_tracking_id: str
) -> GMAOCallbackPayload:
    logger.debug(f"[{mcp_tracking_id}] Transforming AnalysisResult for incident {original_external_incident_id} to GMAO format.")
    
    summary_parts = []
    actionable_insights = analysis_result.actionable_insights or []
    parsed_response = analysis_result.parsed_response

    if parsed_response and parsed_response.potential_root_causes:
        causes_text = ", ".join([
            rc.cause for rc in parsed_response.potential_root_causes if rc.cause and hasattr(rc, 'cause')
        ])
        if causes_text:
            summary_parts.append(f"Potential Causes: {causes_text}")

    if actionable_insights:
        insights_summary = "; ".join([insight.description for insight in actionable_insights[:2] if hasattr(insight, 'description')])
        if insights_summary:
             summary_parts.append(f"Key Insights: {insights_summary}")
    
    analysis_summary = ". ".join(summary_parts)
    if not analysis_summary and analysis_result.llm_raw_response:
        analysis_summary = (analysis_result.llm_raw_response[:250] + "...") if len(analysis_result.llm_raw_response) > 250 else analysis_result.llm_raw_response
    elif not analysis_summary:
        analysis_summary = "Analysis complete. No specific summary points extracted."

    recommended_actions_str = []
    if actionable_insights:
        for insight in actionable_insights:
            action_detail = insight.description if hasattr(insight, 'description') else "N/A"
            target_detail = insight.target if hasattr(insight, 'target') and insight.target else "N/A"
            type_detail = insight.type if hasattr(insight, 'type') and insight.type else "N/A"
            recommended_actions_str.append(
                f"{action_detail} (Target: {target_detail}, Type: {type_detail})"
            )
    elif parsed_response and parsed_response.recommended_actions:
        recommended_actions_str = [
            action.action for action in parsed_response.recommended_actions if hasattr(action, 'action') and action.action
        ]

    current_status = "analyzed"
    if analysis_result.errors:
        current_status = "error_in_analysis"
        error_details = '; '.join(analysis_result.errors)
        analysis_summary = f"Errors during analysis: {error_details}. {analysis_summary}"[:1000] # Keep summary reasonable

    return GMAOCallbackPayload(
        external_incident_id=original_external_incident_id,
        analysis_summary=analysis_summary,
        confidence_score=analysis_result.confidence_score,
        recommended_actions=recommended_actions_str,
        status=current_status,
        analysis_timestamp=analysis_result.analysis_timestamp,
        mcp_tracking_id=mcp_tracking_id
    )

# --- Helper function to send analysis results back to GMAO ---
async def send_analysis_to_gmao(payload: GMAOCallbackPayload, tracking_id: str):
    logger.info(f"[{tracking_id}] Preparing to send analysis results to GMAO for incident {payload.external_incident_id}.")

    if not GMAO_CALLBACK_URL:
        logger.error(f"[{tracking_id}] GMAO_CALLBACK_URL is not configured. Cannot send analysis for {payload.external_incident_id}.")
        # Optionally, raise an error or handle as per your application's requirements
        return

    # Ensure GMAO_CALLBACK_URL has a trailing slash
    callback_url = GMAO_CALLBACK_URL
    if not callback_url.endswith('/'):
        logger.debug(f"[{tracking_id}] Appending trailing slash to GMAO_CALLBACK_URL.")
        callback_url += '/'

    headers = {
        "Content-Type": "application/json",
    }
    if GMAO_CALLBACK_API_KEY:
        headers["X-API-Key"] = GMAO_CALLBACK_API_KEY # Changed from X-Callback-Auth-Token to X-API-Key
    
    logger.info(f"[{tracking_id}] Attempting to send analysis results for {payload.external_incident_id} to GMAO at {callback_url}")

    for attempt in range(1, CALLBACK_MAX_ATTEMPTS + 1):
        try:
            logger.info(f"[{tracking_id}] Attempt {attempt}/{CALLBACK_MAX_ATTEMPTS} sending analysis to GMAO at {callback_url} for {payload.external_incident_id}.") # Use callback_url
            async with httpx.AsyncClient(timeout=CALLBACK_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    callback_url, # Use the modified callback_url
                    json=payload.model_dump(mode="json"),
                    headers=headers
                )
                response.raise_for_status()
                logger.info(f"[{tracking_id}] Successfully sent analysis to GMAO for incident {payload.external_incident_id} on attempt {attempt}. Response: {response.status_code} {response.text[:100]}")
                return True
        except httpx.RequestError as e:
            logger.warning(f"[{tracking_id}] Request error on attempt {attempt}/{CALLBACK_MAX_ATTEMPTS} sending analysis to GMAO for {payload.external_incident_id}: {e}")
            if attempt == CALLBACK_MAX_ATTEMPTS:
                logger.error(f"[{tracking_id}] Final attempt failed. Request error sending analysis to GMAO for {payload.external_incident_id}: {e}", exc_info=True)
        except httpx.HTTPStatusError as e:
            logger.warning(f"[{tracking_id}] HTTP status error {e.response.status_code} on attempt {attempt}/{CALLBACK_MAX_ATTEMPTS} sending analysis to GMAO for {payload.external_incident_id}: {e.response.text[:200]}") # Log part of response
            # Don't retry client errors (4xx) unless it's 429 (Too Many Requests) or specific retryable 4xx codes.
            # For simplicity, we retry all 4xx here along with 5xx, but this could be refined.
            if e.response.status_code < 500 and e.response.status_code not in [408, 429]: # Example: Don't retry 400, 401, 403, 404 etc.
                 logger.error(f"[{tracking_id}] Non-retryable HTTP error {e.response.status_code} sending analysis to GMAO. Aborting.")
                 break # Exit retry loop for these errors
            if attempt == CALLBACK_MAX_ATTEMPTS:
                logger.error(f"[{tracking_id}] Final attempt failed. HTTP error sending analysis to GMAO for {payload.external_incident_id}: {e.response.status_code}", exc_info=True)
        except Exception as e:
            logger.error(f"[{tracking_id}] Unexpected error on attempt {attempt}/{CALLBACK_MAX_ATTEMPTS} sending analysis to GMAO for {payload.external_incident_id}: {e}", exc_info=True)
        
        if attempt < CALLBACK_MAX_ATTEMPTS:
            delay_index = min(attempt - 1, len(CALLBACK_RETRY_DELAYS_SECONDS) - 1)
            delay = CALLBACK_RETRY_DELAYS_SECONDS[delay_index]
            logger.info(f"[{tracking_id}] Retrying GMAO callback in {delay}s...")
            await asyncio.sleep(delay)

    logger.error(f"[{tracking_id}] Failed to send analysis to GMAO for incident {payload.external_incident_id} after {CALLBACK_MAX_ATTEMPTS} attempts.")
    return False

@router.post("/v1/webhooks/gmao/incidents", 
            response_model=WebhookResponse,
            status_code=status.HTTP_202_ACCEPTED,
            summary="Receive Incident from GMAO System",
            description="Webhook endpoint to receive incident data from the GMAO system, authenticate, map, and queue for processing by the Incident Analysis Agent.",
            dependencies=[Depends(verify_api_key)]) # Apply authentication dependency
async def receive_gmao_incident(
    payload: GmaoWebhookPayload, 
    background_tasks: BackgroundTasks,
    # api_key: str = Depends(verify_api_key) # Alternative if you need the key value
):
    """
    Handles incoming incident data from the GMAO system.
    Authenticates the request, maps the payload, and schedules asynchronous processing.
    Responds quickly with a 202 Accepted.
    """
    tracking_id = f"mcp-wh-{uuid.uuid4()}"
    logger.info(f"[{tracking_id}] Received webhook for external incident: {payload.external_incident_id}")

    # 1. Map data to internal format
    try:
        incident_report_data = map_gmao_to_incident_report(payload)
        logger.info(f"[{tracking_id}] Payload mapped successfully for: {incident_report_data.incident_id}")
    except Exception as e:
        logger.error(f"[{tracking_id}] Error mapping GMAO payload {payload.external_incident_id}: {e}", exc_info=True)
        # For critical mapping errors, you might choose to respond with an error immediately
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Error processing webhook payload: {str(e)}"
        )

    # 2. Schedule background task for forwarding to Incident Analysis Agent
    # Pass the original_external_incident_id to the background task
    background_tasks.add_task(forward_incident_to_agent, incident_report_data, tracking_id, payload.external_incident_id)
    logger.info(f"[{tracking_id}] Incident {incident_report_data.incident_id} (external: {payload.external_incident_id}) queued for forwarding to agent and GMAO callback.")

    return WebhookResponse(
        status="success", 
        message="Incident received and queued for processing.",
        tracking_id=tracking_id
    )
