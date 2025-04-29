import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
import uuid

# Import the FastAPI app instance
# We need to adjust sys.path or use a better project structure/packaging
# For now, let's assume tests are run from the root ACS-AI-AGENTS directory
# or that PYTHONPATH is set up correctly.
# A more robust solution involves proper packaging.
import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..')))

from mcp.api.main import app 

# --- Test Fixtures ---

@pytest.fixture(scope="module")
def test_client():
    """Provides a FastAPI TestClient instance."""
    client = TestClient(app)
    yield client

@pytest.fixture
def mock_route_message():
    """Fixture to mock the route_message_to_agents function."""
    # Note the path to mock: it's where the function is *imported* into, not where it's defined
    with patch('mcp.api.main.route_message_to_agents', new_callable=AsyncMock) as mock_router:
        yield mock_router

# --- Test Cases ---

def test_process_message_success(test_client, mock_route_message):
    """Test the /message endpoint successfully routing and returning responses."""
    # Arrange
    request_payload = {
        "content": {"data": "sample task"},
        "target_capability": "process_data",
        "source_agent_id": "initiator-123"
    }
    
    mock_agent_response = {
        "agent-abc": {"status": "completed", "result": "data processed"},
        "agent-xyz": {"status": "completed", "result": "validation passed"}
    }
    mock_route_message.return_value = mock_agent_response

    # Act
    response = test_client.post("/message", json=request_payload)

    # Assert
    assert response.status_code == 200
    mock_route_message.assert_awaited_once_with(
        capability="process_data",
        message_payload={
            "content": {"data": "sample task"},
            "metadata": None, # Metadata was None in request
            "source_agent_id": "initiator-123"
        }
    )
    
    response_json = response.json()
    assert response_json["status"] == "processed"
    assert "message_id" in response_json
    assert len(response_json["responses"]) == 2
    
    # Check formatted responses (order might vary, so check contents)
    agent_ids_in_response = {r["agent_id"] for r in response_json["responses"]}
    assert agent_ids_in_response == {"agent-abc", "agent-xyz"}
    
    for resp_item in response_json["responses"]:
        agent_id = resp_item["agent_id"]
        assert resp_item["error"] is None
        assert resp_item["response_body"] == mock_agent_response[agent_id]

def test_process_message_routing_error(test_client, mock_route_message):
    """Test the /message endpoint when the router function raises an exception."""
    # Arrange
    request_payload = {
        "content": {"data": "another task"},
        "target_capability": "analyze_image"
    }
    
    mock_route_message.side_effect = Exception("Routing failed internally")

    # Act
    response = test_client.post("/message", json=request_payload)

    # Assert
    assert response.status_code == 503 # Service Unavailable
    mock_route_message.assert_awaited_once() # Ensure it was called
    
    response_json = response.json()
    assert response_json["detail"] == "Failed to route message to agents"

def test_process_message_agent_error_response(test_client, mock_route_message):
    """Test the /message endpoint when one agent returns an error."""
    # Arrange
    request_payload = {
        "content": {"data": "error task"},
        "target_capability": "process_error"
    }
    
    mock_agent_response = {
        "agent-ok": {"status": "completed"},
        "agent-fail": TimeoutError("Agent did not respond in time") # Example error
    }
    mock_route_message.return_value = mock_agent_response

    # Act
    response = test_client.post("/message", json=request_payload)

    # Assert
    assert response.status_code == 200
    mock_route_message.assert_awaited_once()
    
    response_json = response.json()
    assert response_json["status"] == "processed"
    assert len(response_json["responses"]) == 2
    
    # Find the responses for each agent
    ok_response = next((r for r in response_json["responses"] if r["agent_id"] == "agent-ok"), None)
    fail_response = next((r for r in response_json["responses"] if r["agent_id"] == "agent-fail"), None)
    
    assert ok_response is not None
    assert ok_response["error"] is None
    assert ok_response["response_body"] == {"status": "completed"}
    
    assert fail_response is not None
    assert fail_response["response_body"] is None
    assert "TimeoutError: Agent did not respond in time" in fail_response["error"]

# We don't explicitly test for missing 'target_capability' here because
# FastAPI/Pydantic handles the 422 Unprocessable Entity response automatically.
# Testing validation is possible but often redundant for basic cases.

# TODO: Add tests for other endpoints like /agents/register, /agents, etc. later. 