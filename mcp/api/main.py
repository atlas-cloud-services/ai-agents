from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import time

# Import the registry
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from orchestration.registry import registry, AgentInfo

app = FastAPI(title="ACS GMAO AI - Master Control Program")

class RegisterAgentRequest(BaseModel):
    name: str
    description: str
    endpoint: str
    capabilities: List[str]

class RegisterAgentResponse(BaseModel):
    agent_id: str
    status: str = "success"

class MessageRequest(BaseModel):
    content: str
    source_agent_id: Optional[str] = None
    target_capability: Optional[str] = None
    metadata: Optional[dict] = None

class MessageResponse(BaseModel):
    message_id: str
    status: str
    responses: Optional[List[dict]] = None

@app.get("/")
def read_root():
    return {"status": "MCP is running", "version": "0.1.0"}

@app.post("/agents/register", response_model=RegisterAgentResponse)
async def register_agent(request: RegisterAgentRequest):
    agent_id = registry.register_agent(
        name=request.name,
        description=request.description,
        endpoint=request.endpoint,
        capabilities=request.capabilities
    )
    return {"agent_id": agent_id, "status": "success"}

@app.get("/agents", response_model=List[AgentInfo])
async def get_all_agents():
    return registry.get_all_agents()

@app.get("/agents/{agent_id}", response_model=AgentInfo)
async def get_agent(agent_id: str):
    agent = registry.get_agent(agent_id)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent with ID {agent_id} not found")
    return agent

@app.post("/message", response_model=MessageResponse)
async def process_message(request: MessageRequest):
    """
    Process a message by routing it to appropriate agents.
    This is a simplified implementation without actual agent communication.
    """
    message_id = f"msg_{int(time.time())}"
    
    # In a real implementation, we would:
    # 1. Find appropriate agents based on target_capability
    # 2. Forward the message to those agents
    # 3. Collect and aggregate responses
    
    # For now, we just acknowledge receipt
    return {
        "message_id": message_id,
        "status": "processed",
        "responses": []
    }