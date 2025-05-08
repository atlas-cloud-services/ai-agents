import os

# Set the test API key in the environment BEFORE other imports that might read it at module level
TEST_GMAO_API_KEY = "test-secret-gmao-api-key-for-pytest"
os.environ["GMAO_WEBHOOK_API_KEY"] = TEST_GMAO_API_KEY

import pytest
from fastapi.testclient import TestClient
import datetime # Added for timestamp comparisons
from pytest_mock import MockerFixture # For mocking
from fastapi import BackgroundTasks # To inspect/mock its methods

# Adjust the import path according to your project structure
# This assumes that 'mcp' is a package and PYTHONPATH is set up correctly
# or that tests are run from a location where 'mcp' is discoverable.
from mcp.api.main import app # The FastAPI app instance
from mcp.models.webhook import GmaoWebhookPayload # For creating test payloads
from mcp.api.endpoints import map_gmao_to_incident_report, forward_incident_to_agent, INCIDENT_AGENT_URL # The function and model to test
from agents.incident.models import IncidentReport # ADDED: Import IncidentReport

# Define the webhook endpoint path
GMAO_WEBHOOK_ENDPOINT = "/api/v1/webhooks/gmao/incidents" # Updated to the simplified path

# Import httpx for mocking its exceptions and for spec in mocks
import httpx

@pytest.fixture(scope="module")
def client():
    """
    Test client fixture that uses the FastAPI app.
    """
    with TestClient(app) as c:
        yield c

# --- Test Cases ---

# 1. API Key Authentication Tests
def test_webhook_missing_api_key(client: TestClient):
    """Test webhook access without providing an API key."""
    response = client.post(GMAO_WEBHOOK_ENDPOINT, json={})
    assert response.status_code == 401 # Unauthorized
    assert "Missing API Key" in response.json().get("detail", "")

def test_webhook_invalid_api_key(client: TestClient):
    """Test webhook access with an invalid API key."""
    headers = {"X-GMAO-Token": "this-is-a-wrong-key"}
    response = client.post(GMAO_WEBHOOK_ENDPOINT, headers=headers, json={})
    assert response.status_code == 403 # Forbidden
    assert "Invalid API Key" in response.json().get("detail", "")

def test_webhook_valid_api_key_empty_payload(client: TestClient, mocker: MockerFixture):
    """
    Test webhook access with a valid API key but an empty/invalid payload.
    This primarily tests authentication; payload validation is a separate concern.
    FastAPI will return 422 if payload doesn't match GmaoWebhookPayload.
    """
    mocker.patch("mcp.api.endpoints.GMAO_WEBHOOK_API_KEY", TEST_GMAO_API_KEY)
    headers = {"X-GMAO-Token": TEST_GMAO_API_KEY}
    response = client.post(GMAO_WEBHOOK_ENDPOINT, headers=headers, json={})
    # Expect 422 Unprocessable Entity due to Pydantic validation of GmaoWebhookPayload
    assert response.status_code == 422 

# Placeholder for a valid minimal payload for further tests
# You should define this based on your GmaoWebhookPayload model requirements
# Ensure all non-optional fields are present.
VALID_MINIMAL_PAYLOAD = {
    "external_incident_id": "test-incident-001",
    "title": "Test Incident Title",
    "description": "Detailed description of the test incident.",
    "status": "OPEN", # Or any valid status string
    "priority": "MEDIUM", # Or any valid priority string
    "incident_created_at": "2023-10-28T10:00:00Z" # ISO 8601 datetime string
    # Add other required fields from GmaoWebhookPayload here
    # e.g., "affected_services": [], "reported_by_gmao_user_id": "test_user"
}

def test_webhook_successful_auth_and_reception(client: TestClient, mocker: MockerFixture):
    """
    Test successful authentication and basic reception (202 Accepted).
    This uses a minimal valid payload.
    """
    mocker.patch("mcp.api.endpoints.GMAO_WEBHOOK_API_KEY", TEST_GMAO_API_KEY)
    headers = {"X-GMAO-Token": TEST_GMAO_API_KEY}
    
    # If we want to ensure the background task is not actually run,
    # we can mock it here, but test_webhook_schedules_forward_incident_task covers its call.
    # For this test, we primarily care about the 202.
    # However, if the actual call to httpx within the background task (unmocked) would fail
    # in the test environment (e.g. network issues), it might be safer to mock add_task.
    # For now, assuming the live log's error [Errno 8] was specific to that run or unmocked BG task.
    # Let's ensure add_task is at least spied on to prevent unintended side effects in this test too.
    mocker.patch("fastapi.BackgroundTasks.add_task")

    response = client.post(GMAO_WEBHOOK_ENDPOINT, headers=headers, json=VALID_MINIMAL_PAYLOAD)
    assert response.status_code == 202 # Accepted
    response_data = response.json()
    assert response_data.get("status") == "success"
    assert "Incident received and queued for processing" in response_data.get("message", "")
    assert "tracking_id" in response_data

# 2. Data Transformation Tests (map_gmao_to_incident_report)

def test_map_gmao_basic_payload():
    """Test mapping with a basic, valid GmaoWebhookPayload."""
    payload = GmaoWebhookPayload(**VALID_MINIMAL_PAYLOAD) # Use our defined minimal payload
    
    report = map_gmao_to_incident_report(payload) # MODIFIED: function name and variable name

    assert isinstance(report, IncidentReport) # MODIFIED: class name and variable name
    assert report.incident_id == VALID_MINIMAL_PAYLOAD["external_incident_id"] # MODIFIED: variable name
    # Pydantic v1 might store datetime as is, v2 might ensure UTC. Assuming it matches GmaoWebhookPayload's parsed datetime.
    assert report.timestamp == payload.incident_created_at # MODIFIED: variable name
        
    expected_description_part_title = VALID_MINIMAL_PAYLOAD["title"]
    expected_description_part_desc = VALID_MINIMAL_PAYLOAD["description"]
    assert expected_description_part_title in report.description # MODIFIED: variable name
    assert expected_description_part_desc in report.description # MODIFIED: variable name
    assert f"GMAO Status: {VALID_MINIMAL_PAYLOAD['status']}" in report.description # MODIFIED: variable name

    # Based on the priority_map in endpoints.py: {"low": 3, "medium": 2, "high": 1}
    assert report.priority == 2 # "MEDIUM" maps to 2 # MODIFIED: variable name

    # Assuming GmaoWebhookPayload has these as optional with default_factory=list
    assert report.affected_systems == [] # MODIFIED: variable name
    assert report.reporter == None # Optional field, not in VALID_MINIMAL_PAYLOAD # MODIFIED: variable name

def test_map_gmao_with_optional_fields():
    """Test mapping with all optional fields provided in GmaoWebhookPayload."""
    payload_data = {
        **VALID_MINIMAL_PAYLOAD, # Start with the minimal valid data
        "image_url": "http://example.com/image.png",
        "affected_services": ["service1", "service2"],
        "reported_by_gmao_user_id": "test_reporter_id",
        "gmao_link": "http://gmao.example.com/123",
        "additional_data": {"key1": "value1", "custom_field": "custom_value"}
    }
    payload = GmaoWebhookPayload(**payload_data)
    report = map_gmao_to_incident_report(payload) # MODIFIED: function name and variable name

    assert report.affected_systems == payload_data["affected_services"] # MODIFIED: variable name
    assert report.reporter == payload_data["reported_by_gmao_user_id"] # MODIFIED: variable name
    
    assert payload_data["image_url"] in report.description # MODIFIED: variable name
    assert payload_data["gmao_link"] in report.description # MODIFIED: variable name
    assert str(payload_data["additional_data"]) in report.description # MODIFIED: variable name

def test_map_gmao_priority_variations():
    """Test different priority mappings based on endpoints.py logic."""
    # Current map: {"low": 3, "medium": 2, "high": 1}
    priorities_to_test = {
        "LOW": 3,
        "low": 3,
        "MEDIUM": 2,
        "medium": 2,
        "HIGH": 1,
        "high": 1,
        "CRITICAL": None, # Assuming CRITICAL is not in the map, should result in None
        "UnknownValue": None # Unknown priorities should result in None
    }
    for gmao_prio, expected_internal_prio in priorities_to_test.items():
        # Create a full payload dict first for GmaoWebhookPayload model validation
        current_payload_data = {
            "external_incident_id": f"prio-test-{gmao_prio}",
            "title": "Priority Test",
            "description": "Testing priority mapping",
            "status": "OPEN",
            "priority": gmao_prio,
            "incident_created_at": "2023-01-01T12:00:00Z"
        }
        payload = GmaoWebhookPayload(**current_payload_data)
        report = map_gmao_to_incident_report(payload) # MODIFIED: function name and variable name
        assert report.priority == expected_internal_prio, f"Failed for GMAO priority: '{gmao_prio}'" # MODIFIED: variable name

# 3. Asynchronous Processing Tests

def test_webhook_schedules_forward_incident_task(client: TestClient, mocker: MockerFixture):
    """Test that a successful webhook call schedules the forward_incident_to_agent task."""
    mocker.patch("mcp.api.endpoints.GMAO_WEBHOOK_API_KEY", TEST_GMAO_API_KEY)
    headers = {"X-GMAO-Token": TEST_GMAO_API_KEY}
    mock_add_task = mocker.patch("fastapi.BackgroundTasks.add_task")
    response = client.post(GMAO_WEBHOOK_ENDPOINT, headers=headers, json=VALID_MINIMAL_PAYLOAD)
    assert response.status_code == 202
    mock_add_task.assert_called_once()
    args, _ = mock_add_task.call_args
    assert args[0] == forward_incident_to_agent
    report_argument = args[1]
    assert isinstance(report_argument, IncidentReport) # MODIFIED: class name
    assert report_argument.incident_id == VALID_MINIMAL_PAYLOAD["external_incident_id"]

# Unit tests for forward_incident_to_agent function
@pytest.mark.asyncio
async def test_forward_incident_successful(mocker: MockerFixture):
    """Test forward_incident_to_agent successfully posts data."""
    sample_report_data = {
        "incident_id": "fwd-test-001", 
        "timestamp": datetime.datetime.now(datetime.timezone.utc),
        "description": "Forward test successful", 
        "priority": 1
        # Add other fields required by IncidentReport if any # MODIFIED: class name
    }
    incident_report = IncidentReport(**sample_report_data) # MODIFIED: class name

    mock_response = mocker.MagicMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json = mocker.Mock(return_value={"agent_status": "incident_processed"}) # Regular mock for .json()
    mock_response.raise_for_status = mocker.Mock() # Does nothing on success

    # Patch httpx.AsyncClient class
    mock_async_client_constructor = mocker.patch("httpx.AsyncClient", autospec=True)
    # Configure the instance that AsyncClient() will produce
    mock_client_instance = mock_async_client_constructor.return_value
    mock_client_instance.__aenter__.return_value = mock_client_instance # Make __aenter__ return the instance
    mock_client_instance.__aexit__ = mocker.AsyncMock(return_value=None)      # Mock __aexit__
    # Configure the 'post' method of this instance to be an AsyncMock
    mock_client_instance.post = mocker.AsyncMock(return_value=mock_response)

    mock_logger_info = mocker.patch("mcp.api.endpoints.logger.info")

    await forward_incident_to_agent(incident_report)

    mock_client_instance.post.assert_called_once_with(
        INCIDENT_AGENT_URL, 
        json=incident_report.model_dump(mode="json")
    )
    # Check for successful log message
    # This assertion needs to be specific to what you log on success
    successful_log_found = any(
        f"Successfully forwarded incident {incident_report.incident_id}" in call_args[0][0]
        for call_args in mock_logger_info.call_args_list
    )
    assert successful_log_found, "Successful forwarding log message not found"

@pytest.mark.asyncio
async def test_forward_incident_http_status_error(mocker: MockerFixture):
    """Test forward_incident_to_agent handles HTTPStatusError."""
    sample_report_data = {"incident_id": "fwd-test-002", "timestamp": datetime.datetime.now(datetime.timezone.utc), "description": "Forward HTTP error"}
    incident_report = IncidentReport(**sample_report_data) # MODIFIED: class name

    mock_response = mocker.MagicMock(spec=httpx.Response)
    mock_response.status_code = 500
    mock_response.text = "Internal Server Error from Agent"
    mock_response.json = mocker.Mock(return_value={"detail": "Error"}) # If .json() might be called
    mock_response.raise_for_status = mocker.Mock(
        side_effect=httpx.HTTPStatusError("Error from agent", request=mocker.MagicMock(), response=mock_response)
    )

    mock_async_client_constructor = mocker.patch("httpx.AsyncClient", autospec=True)
    mock_client_instance = mock_async_client_constructor.return_value
    mock_client_instance.__aenter__.return_value = mock_client_instance
    mock_client_instance.__aexit__ = mocker.AsyncMock(return_value=None) 
    mock_client_instance.post = mocker.AsyncMock(return_value=mock_response)

    mock_logger_error = mocker.patch("mcp.api.endpoints.logger.error")

    await forward_incident_to_agent(incident_report)

    mock_client_instance.post.assert_called_once()
    error_log_found = any(
        f"HTTP error forwarding incident {incident_report.incident_id}" in call_args[0][0]
        for call_args in mock_logger_error.call_args_list
    )
    assert error_log_found, "HTTPStatusError log message not found"

@pytest.mark.asyncio
async def test_forward_incident_request_error(mocker: MockerFixture):
    """Test forward_incident_to_agent handles RequestError."""
    sample_report_data = {"incident_id": "fwd-test-003", "timestamp": datetime.datetime.now(datetime.timezone.utc), "description": "Forward Request error"}
    incident_report = IncidentReport(**sample_report_data) # MODIFIED: class name

    mock_async_client_constructor = mocker.patch("httpx.AsyncClient", autospec=True)
    mock_client_instance = mock_async_client_constructor.return_value
    mock_client_instance.__aenter__.return_value = mock_client_instance
    mock_client_instance.__aexit__ = mocker.AsyncMock(return_value=None) 
    mock_client_instance.post = mocker.AsyncMock(
        side_effect=httpx.RequestError("Connection failed", request=mocker.MagicMock())
    )

    mock_logger_error = mocker.patch("mcp.api.endpoints.logger.error")

    await forward_incident_to_agent(incident_report)

    mock_client_instance.post.assert_called_once()
    error_log_found = any(
        f"Request error forwarding incident {incident_report.incident_id}" in call_args[0][0]
        for call_args in mock_logger_error.call_args_list
    )
    assert error_log_found, "RequestError log message not found"

# More tests to be added for:
# - Error handling within the endpoint (e.g., if mapping fails critically before background task) 