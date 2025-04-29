from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import time
import logging
import uuid

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Import the registry
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from orchestration.registry import registry, AgentInfo
from orchestration.router import route_message_to_agents, AGENT_REQUEST_TIMEOUT

app = FastAPI(
    title="ACS GMAO AI - Master Control Program (MCP)",
    description="The Master Control Program orchestrates communication and tasks among various AI agents.",
    version="0.2.0"
)

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

@app.get("/", summary="Get MCP Status")
def read_root():
    """Returns the current status and version of the MCP."""
    return {"status": "MCP is running", "version": app.version}

@app.post("/agents/register", 
            response_model=RegisterAgentResponse, 
            status_code=status.HTTP_201_CREATED,
            summary="Register a New Agent",
            description="Registers a new AI agent with the MCP, providing its metadata and capabilities.")
async def register_agent(request: RegisterAgentRequest):
    """Registers a new agent with the central registry."""
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

@app.get("/agents", 
         response_model=List[AgentInfo],
         summary="List All Registered Agents",
         description="Retrieves a list of all agents currently registered with the MCP.")
async def get_all_agents():
    """Returns a list of all agents in the registry."""
    return registry.get_all_agents()

@app.get("/agents/{agent_id}", 
         response_model=AgentInfo,
         summary="Get Agent Details",
         description="Retrieves detailed information about a specific agent by its ID.",
         responses={404: {"description": "Agent not found"}})
async def get_agent(agent_id: str):
    """Returns details for a specific agent ID."""
    agent = registry.get_agent(agent_id)
    if not agent:
        logger.warning(f"Attempted to access non-existent agent ID: {agent_id}")
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Agent with ID {agent_id} not found")
    return agent

@app.post("/message", 
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

    # Prepare the payload to send to agents
    # We might want to refine what exactly gets forwarded
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
        # Catch potential errors in the routing initiation itself
        logger.error(f"Failed to initiate routing for message {message_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, 
                            detail="Failed to route message to agents")

    # Format the responses according to the AgentResponseData model
    formatted_responses: List[AgentResponseData] = []
    for agent_id, response_data in agent_responses_dict.items():
        if isinstance(response_data, Exception):
            # Handle specific httpx errors or general exceptions
            error_msg = f"{type(response_data).__name__}: {str(response_data)}"
            logger.warning(f"Error response from agent {agent_id} for message {message_id}: {error_msg}")
            formatted_responses.append(AgentResponseData(agent_id=agent_id, error=error_msg))
        elif isinstance(response_data, dict): # Assuming successful response is a dict
            # We might want to add status code if the agent includes it
            logger.debug(f"Successful response from agent {agent_id} for message {message_id}")
            formatted_responses.append(AgentResponseData(agent_id=agent_id, response_body=response_data))
        else:
             # Handle unexpected response types
            error_msg = f"Unexpected response type from agent: {type(response_data).__name__}"
            logger.error(f"Unexpected response from agent {agent_id} for message {message_id}: {response_data}")
            formatted_responses.append(AgentResponseData(agent_id=agent_id, error=error_msg))

    logger.info(f"Processed message {message_id}. Returning {len(formatted_responses)} responses.")
    return {
        "message_id": message_id,
        "status": "processed",
        "responses": formatted_responses
    }

# Add an endpoint for agent health checks / heartbeat (Optional but good practice)
class HeartbeatRequest(BaseModel):
    status: str = "ok"

@app.put("/agents/{agent_id}/heartbeat", status_code=status.HTTP_204_NO_CONTENT)
async def agent_heartbeat(agent_id: str, request: HeartbeatRequest):
    """Allows agents to report their status (heartbeat)."""
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

# --- Helper for Running (if main script) ---
# (Consider using a separate run script or docker compose)
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)