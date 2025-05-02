from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import time
import logging
import uuid

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
