from typing import Dict, List, Optional
from pydantic import BaseModel
import uuid

class AgentInfo(BaseModel):
    """Model for storing information about registered agents"""
    id: str
    name: str
    description: str
    endpoint: str
    capabilities: List[str]
    status: str = "active"
    last_heartbeat: Optional[float] = None

class AgentRegistry:
    """Registry for keeping track of all available agents"""
    
    def __init__(self):
        self.agents: Dict[str, AgentInfo] = {}
    
    def register_agent(self, name: str, description: str, endpoint: str, capabilities: List[str]) -> str:
        """Register a new agent and return its ID"""
        agent_id = str(uuid.uuid4())
        
        agent = AgentInfo(
            id=agent_id,
            name=name,
            description=description,
            endpoint=endpoint,
            capabilities=capabilities
        )
        
        self.agents[agent_id] = agent
        return agent_id
    
    def get_agent(self, agent_id: str) -> Optional[AgentInfo]:
        """Get agent info by ID"""
        return self.agents.get(agent_id)
    
    def get_all_agents(self) -> List[AgentInfo]:
        """Get all registered agents"""
        return list(self.agents.values())
    
    def get_agents_by_capability(self, capability: str) -> List[AgentInfo]:
        """Get all agents with a specific capability"""
        return [
            agent for agent in self.agents.values()
            if capability in agent.capabilities
        ]
    
    def update_agent_status(self, agent_id: str, status: str) -> bool:
        """Update the status of an agent"""
        if agent_id in self.agents:
            self.agents[agent_id].status = status
            return True
        return False
    
    def deregister_agent(self, agent_id: str) -> bool:
        """Remove an agent from the registry"""
        if agent_id in self.agents:
            del self.agents[agent_id]
            return True
        return False

# Create a singleton instance
registry = AgentRegistry()