from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import time
import logging
import uuid
import os
import httpx
from fastapi import Header, BackgroundTasks
import datetime

# Assuming registry and route_message_to_agents are accessible
# This might require adjustments based on actual project structure
# If they are in the parent dir, relative imports might work or sys.path manipulation needed
try:
    from orchestration.registry import registry, AgentInfo
    from orchestration.router import route_message_to_agents, AGENT_REQUEST_TIMEOUT
except ImportError:
    # Fallback or raise error if running endpoints standalone isn't intended
    # For now, let's assume they are available via the app context if needed
    # Or define dummy placeholders if needed for linting/type checking
    class AgentInfo(BaseModel):
        id: str
        name: str
    registry = None # Placeholder
    async def route_message_to_agents(capability: str, message_payload: Dict): return {} # Placeholder

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

# Placeholder for IncidentReport if not directly accessible by MCP
class InternalIncidentReport(BaseModel):
    incident_id: str
    timestamp: datetime.datetime
    description: str
    priority: Optional[int] = None
    affected_systems: Optional[List[str]] = None
    reporter: Optional[str] = None
    # Add any other fields expected by the Incident Analysis Agent

# Import webhook models (adjust path if models are in a different location within mcp)
try:
    from ..models.webhook import GmaoWebhookPayload, WebhookResponse
except ImportError:
    # Fallback for local testing if models are in the same dir or mcp/models/
    from mcp.models.webhook import GmaoWebhookPayload, WebhookResponse

GMAO_WEBHOOK_API_KEY = os.getenv("GMAO_WEBHOOK_API_KEY", "your-secret-gmao-api-key") # Replace with secure retrieval
INCIDENT_AGENT_URL = os.getenv("INCIDENT_AGENT_URL", "http://localhost:8003/api/analyze") # Agent's /analyze endpoint

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

def map_gmao_to_internal_incident(gmao_payload: GmaoWebhookPayload) -> InternalIncidentReport:
    """Maps the GMAO webhook payload (based on Django Incident model) to the internal IncidentReport format."""
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

    internal_report = InternalIncidentReport(
        incident_id=gmao_payload.external_incident_id, # Using GMAO's incident ID
        timestamp=gmao_payload.incident_created_at,    # Using when incident was created in GMAO
        description=full_description,
        priority=internal_priority,
        affected_systems=gmao_payload.affected_services, # Direct mapping if field names match
        reporter=gmao_payload.reported_by_gmao_user_id   # Using GMAO user ID as reporter
    )
    logger.info(f"Successfully mapped GMAO incident {gmao_payload.external_incident_id} (Title: {gmao_payload.title}) to internal format.")
    return internal_report

async def forward_incident_to_agent(incident_report: InternalIncidentReport):
    """Asynchronously forwards the mapped incident to the Incident Analysis Agent."""
    logger.info(f"Forwarding incident {incident_report.incident_id} to Incident Analysis Agent at {INCIDENT_AGENT_URL}")
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(INCIDENT_AGENT_URL, json=incident_report.model_dump(mode="json")) # Use model_dump for Pydantic v2
            response.raise_for_status() # Raises an HTTPError if the HTTP request returned an unsuccessful status code
            logger.info(f"Incident {incident_report.incident_id} successfully forwarded. Agent response: {response.status_code}")
    except httpx.RequestError as e:
        logger.error(f"Error sending incident {incident_report.incident_id} to agent: {e}", exc_info=True)
        # TODO: Implement retry logic or dead-letter queue for failed forwards
    except httpx.HTTPStatusError as e:
        logger.error(f"Incident Analysis Agent returned an error for {incident_report.incident_id}: {e.response.status_code} - {e.response.text}", exc_info=True)
        # TODO: Handle specific agent error responses

@router.post("/api/v1/webhooks/gmao/incidents", 
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
        internal_incident_report = map_gmao_to_internal_incident(payload)
        logger.info(f"[{tracking_id}] Payload mapped successfully for: {internal_incident_report.incident_id}")
    except Exception as e:
        logger.error(f"[{tracking_id}] Error mapping GMAO payload {payload.external_incident_id}: {e}", exc_info=True)
        # For critical mapping errors, you might choose to respond with an error immediately
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Error processing webhook payload: {str(e)}"
        )

    # 2. Schedule background task for forwarding to Incident Analysis Agent
    background_tasks.add_task(forward_incident_to_agent, internal_incident_report)
    logger.info(f"[{tracking_id}] Incident {internal_incident_report.incident_id} queued for forwarding to agent.")

    return WebhookResponse(
        status="success", 
        message="Incident received and queued for processing.",
        tracking_id=tracking_id
    )
