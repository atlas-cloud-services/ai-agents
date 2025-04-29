import pytest
import pytest_asyncio
import httpx
from unittest.mock import patch, MagicMock
import json

from mcp.orchestration.registry import AgentInfo
from mcp.orchestration.router import route_message_to_agents

# Mock agents for testing
@pytest.fixture
def mock_agents():
    return [
        AgentInfo(
            id="agent1",
            name="Test Agent 1",
            description="Test agent with capability1",
            endpoint="http://localhost:8003",
            capabilities=["capability1", "capability2"],
            status="active"
        ),
        AgentInfo(
            id="agent2",
            name="Test Agent 2",
            description="Test agent with capability2",
            endpoint="http://localhost:8004",
            capabilities=["capability2"],
            status="active"
        ),
        AgentInfo(
            id="agent3",
            name="Test Agent 3 (inactive)",
            description="Inactive test agent",
            endpoint="http://localhost:8005",
            capabilities=["capability1"],
            status="inactive"
        )
    ]

@pytest_asyncio.fixture
async def mock_registry(mock_agents):
    with patch("mcp.orchestration.router.registry") as mock_registry:
        # Setup the registry to return our mock agents based on capability
        def get_agents_by_capability(capability):
            return [agent for agent in mock_agents if capability in agent.capabilities]
            
        mock_registry.get_agents_by_capability.side_effect = get_agents_by_capability
        yield mock_registry

@pytest.mark.asyncio
async def test_route_message_success(mock_registry, httpx_mock):
    """Test successful routing to multiple agents"""
    # Setup mock responses
    httpx_mock.add_response(
        url="http://localhost:8003/process",
        method="POST",
        json={"result": "success from agent1"},
        status_code=200
    )
    httpx_mock.add_response(
        url="http://localhost:8004/process",
        method="POST",
        json={"result": "success from agent2"},
        status_code=200
    )
    
    # Call the function
    message_content = {"data": "test message"}
    result = await route_message_to_agents("capability2", message_content)
    
    # Verify results
    assert len(result) == 2
    assert "agent1" in result
    assert "agent2" in result
    assert result["agent1"]["status"] == "success"
    assert result["agent2"]["status"] == "success"
    assert result["agent1"]["data"]["result"] == "success from agent1"
    assert result["agent2"]["data"]["result"] == "success from agent2"

@pytest.mark.asyncio
async def test_route_message_agent_error(mock_registry, httpx_mock):
    """Test handling of agent errors"""
    # Setup mock responses - one success, one error
    httpx_mock.add_response(
        url="http://localhost:8003/process",
        method="POST",
        json={"result": "success from agent1"},
        status_code=200
    )
    httpx_mock.add_response(
        url="http://localhost:8004/process",
        method="POST",
        json={"error": "Something went wrong"},
        status_code=500
    )
    
    # Call the function
    message_content = {"data": "test message"}
    result = await route_message_to_agents("capability2", message_content)
    
    # Verify results
    assert len(result) == 2
    assert result["agent1"]["status"] == "success"
    assert result["agent2"]["status"] == "error"
    assert "error" in result["agent2"]

@pytest.mark.asyncio
async def test_no_agents_for_capability(mock_registry):
    """Test behavior when no agents have the requested capability"""
    # Call the function with a capability no agent has
    result = await route_message_to_agents("nonexistent_capability", {"data": "test"})
    
    # Verify empty result
    assert result == {}

@pytest.mark.asyncio
async def test_inactive_agents_skipped(mock_registry, httpx_mock):
    """Test that inactive agents are skipped"""
    # Setup mock response for the active agent
    httpx_mock.add_response(
        url="http://localhost:8003/process",
        method="POST",
        json={"result": "success from agent1"},
        status_code=200
    )
    
    # Call the function - both agent1 and agent3 have capability1,
    # but agent3 is inactive and should be skipped
    result = await route_message_to_agents("capability1", {"data": "test"})
    
    # Verify only agent1 got a response
    assert len(result) == 1
    assert "agent1" in result
    assert "agent3" not in result