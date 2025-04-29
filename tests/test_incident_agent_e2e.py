import pytest
import pytest_asyncio # Use pytest_asyncio for async fixtures
import httpx
import os
import json
import datetime
from unittest.mock import patch
from pytest_httpx import HTTPXMock # Import mocker

# Import the FastAPI app and models from the incident agent
from agents.incident.main import app # Import the FastAPI app instance
from agents.incident.models import IncidentReport, AnalysisResult, LLMStructuredResponse
from agents.incident.analyzer import CACHE_DB_PATH as ANALYZER_CACHE_PATH # Path used by analyzer
from agents.incident.analyzer import LLM_SERVICE_URL # URL the analyzer tries to call

# --- Test Data ---

@pytest.fixture
def sample_incident_data() -> dict:
    """Provides raw data for a sample incident report."""
    return {
      "incident_id": "E2E-TEST-001",
      "timestamp": datetime.datetime.now().isoformat(), # Use current time
      "description": "End-to-end test: Service API is returning intermittent 503 errors.",
      "priority": 1,
      "affected_systems": ["api-gateway", "user-service"],
      "reporter": "e2e-tester"
    }

@pytest.fixture
def sample_llm_valid_response_json() -> str:
    """Provides a valid JSON string as expected from the LLM."""
    return json.dumps({
      "potential_root_causes": [
        "Underlying user-service instance crashing.",
        "Load balancer misconfiguration."
      ],
      "recommended_actions": [
        "Check user-service logs for errors.",
        "Verify load balancer health checks and configuration.",
        "Monitor resource utilization on user-service hosts."
      ],
      "potential_impact": "API unavailability leading to user-facing errors.",
      "confidence_explanation": "High confidence based on common patterns for 503 errors."
    })

@pytest.fixture
def sample_llm_malformed_response_text() -> str:
    """Provides a malformed/non-JSON string."""
    return "Sorry, I encountered an error generating the JSON. Root cause might be network."

# --- Fixtures for Test Setup ---

@pytest.fixture(scope="function") # Ensure clean state for each test function
def temporary_cache(tmp_path, monkeypatch):
    """Creates a temporary directory for the cache DB and patches the path."""
    temp_db_path = tmp_path / "test_incident_cache.db"
    print(f"\nUsing temporary cache DB: {temp_db_path}")
    
    # Patch the CACHE_DB_PATH used by the analyzer module
    monkeypatch.setattr('agents.incident.analyzer.CACHE_DB_PATH', str(temp_db_path))
    
    # Explicitly initialize the DB using the patched path *before* the app starts
    # This guarantees the table exists before the test runs.
    from agents.incident.analyzer import _init_cache_db
    _init_cache_db()
    
    yield str(temp_db_path)
    # tmp_path fixture handles cleanup of the directory and file

# Async fixture for the HTTP client
@pytest_asyncio.fixture(scope="function")
async def test_client(temporary_cache): # Depends on temporary_cache to ensure path is patched first
    """Provides an httpx AsyncClient configured to test the agent's FastAPI app."""
    # The app's startup event will run here, initializing the temp cache DB
    async with httpx.AsyncClient(app=app, base_url="http://testserver") as client:
        yield client

# --- Basic E2E Test --- 
# (We'll add more tests later)

@pytest.mark.asyncio
async def test_health_check(test_client: httpx.AsyncClient):
    """Tests the basic health check endpoint."""
    response = await test_client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "Incident Analysis Agent is running"
    # We won't assert registration status here as MCP isn't part of this test setup

# --- E2E Analysis Tests ---

@pytest.mark.asyncio
async def test_analyze_success_cache_miss(
    test_client: httpx.AsyncClient,
    httpx_mock: HTTPXMock,
    sample_incident_data: dict,
    sample_llm_valid_response_json: str
):
    """Tests successful analysis via LLM (cache miss)."""
    # Arrange: Mock the LLM service call
    httpx_mock.add_response(
        url=LLM_SERVICE_URL,
        method="POST",
        json={"text": sample_llm_valid_response_json, "processing_time": 1.5}, # Simulate LLM response structure
        status_code=200
    )
    
    # Act: Send request to the agent's /analyze endpoint
    response = await test_client.post("/analyze", json=sample_incident_data)
    
    # Assert: Check response status and AnalysisResult content
    assert response.status_code == 200
    result = response.json() # Parse the JSON response body
    
    # Validate the AnalysisResult structure and key fields
    assert result["incident_id"] == sample_incident_data["incident_id"]
    assert result["analysis_source"] == "llm"
    assert not result["errors"] # Errors list should be empty
    assert result["llm_raw_response"] is not None # Raw response should be stored
    assert result["parsed_response"] is not None # Parsed response should exist
    assert result["confidence_score"] > 0.5 # Expect reasonably high confidence
    assert len(result["actionable_insights"]) > 0 # Should extract some insights
    
    # Optionally, check specific parsed fields
    parsed = result["parsed_response"]
    expected_parsed = json.loads(sample_llm_valid_response_json)
    assert parsed["potential_root_causes"] == expected_parsed["potential_root_causes"]
    assert parsed["recommended_actions"] == expected_parsed["recommended_actions"]

@pytest.mark.asyncio
async def test_analyze_success_cache_hit(
    test_client: httpx.AsyncClient,
    httpx_mock: HTTPXMock,
    sample_incident_data: dict,
    sample_llm_valid_response_json: str
):
    """Tests that a second identical request results in a cache hit."""
    
    # --- First Call (Cache Miss - same as previous test) ---
    # Arrange: Mock the LLM service call for the first request
    httpx_mock.add_response(
        url=LLM_SERVICE_URL,
        method="POST",
        json={"text": sample_llm_valid_response_json, "processing_time": 1.5},
        status_code=200
    )
    
    # Act 1: Send the first request to populate the cache
    print("\nSending first request (expect cache miss)...")
    response1 = await test_client.post("/analyze", json=sample_incident_data)
    
    # Assert 1: Check first response
    assert response1.status_code == 200
    result1 = response1.json()
    assert result1["analysis_source"] == "llm"
    assert not result1["errors"]
    print("First request successful (LLM source).")

    # --- Second Call (Cache Hit) ---
    # Arrange: Remove the LLM mock. If caching works, it shouldn't be called.
    httpx_mock.reset(True)
    # Optional: Add a fallback route that would raise an error if called
    # httpx_mock.add_callback(lambda request: pytest.fail("LLM service was called unexpectedly!"))

    # Act 2: Send the *exact same* request again
    print("Sending second request (expect cache hit)...")
    response2 = await test_client.post("/analyze", json=sample_incident_data)

    # Assert 2: Check second response
    assert response2.status_code == 200
    result2 = response2.json()

    assert result2["incident_id"] == sample_incident_data["incident_id"]
    assert result2["analysis_source"] == "cache" # <<< Key assertion: Source is cache
    assert not result2["errors"]
    assert result2["parsed_response"] is not None # Parsed response should exist from cache
    assert result2["confidence_score"] == result1["confidence_score"] # Should match first result
    assert result2["actionable_insights"] == result1["actionable_insights"] # Should match
    print("Second request successful (Cache source).")

@pytest.mark.asyncio
async def test_analyze_llm_malformed_response(
    test_client: httpx.AsyncClient,
    httpx_mock: HTTPXMock,
    sample_incident_data: dict,
    sample_llm_malformed_response_text: str # Use the malformed text fixture
):
    """Tests handling of malformed/non-JSON response from LLM service."""
    # Arrange: Mock the LLM service call to return malformed text
    httpx_mock.add_response(
        url=LLM_SERVICE_URL,
        method="POST",
        json={"text": sample_llm_malformed_response_text, "processing_time": 0.5},
        status_code=200
    )
    
    # Act: Send request to the agent's /analyze endpoint
    response = await test_client.post("/analyze", json=sample_incident_data)
    
    # Assert: Check response status and AnalysisResult content
    assert response.status_code == 200 # Endpoint should still return 200 OK
    result = response.json()
    
    assert result["incident_id"] == sample_incident_data["incident_id"]
    assert result["analysis_source"] == "error" # Source should be error
    assert len(result["errors"]) > 0 # Errors list should not be empty
    # Check for expected error message (might depend on parsing logic)
    assert any("Could not find JSON" in e or "Failed to decode" in e for e in result["errors"])
    assert result["llm_raw_response"] == sample_llm_malformed_response_text # Raw response should be stored
    assert result["parsed_response"] is None # Parsing failed
    assert result["confidence_score"] < 0.2 # Expect low confidence
    assert not result["actionable_insights"] # No insights extracted

@pytest.mark.asyncio
async def test_analyze_llm_http_error(
    test_client: httpx.AsyncClient,
    httpx_mock: HTTPXMock,
    sample_incident_data: dict
):
    """Tests handling of HTTP error (e.g., 500) from LLM service."""
    # Arrange: Mock the LLM service call to return status 500
    httpx_mock.add_response(
        url=LLM_SERVICE_URL,
        method="POST",
        text="Internal Server Error",
        status_code=500
    )
    
    # Act: Send request to the agent's /analyze endpoint
    response = await test_client.post("/analyze", json=sample_incident_data)
    
    # Assert: Check response status and AnalysisResult content
    assert response.status_code == 200 # Endpoint itself should still be OK
    result = response.json()
    
    assert result["incident_id"] == sample_incident_data["incident_id"]
    assert result["analysis_source"] == "error"
    assert len(result["errors"]) > 0
    # Check for the specific error added when _call_llm_service returns None
    assert "Failed to get response from LLM service." in result["errors"]
    assert result["llm_raw_response"] is None # No raw response received
    assert result["parsed_response"] is None
    assert result["confidence_score"] is None # Or potentially 0.1 depending on calculation logic if raw_response is None
    assert not result["actionable_insights"]

@pytest.mark.asyncio
async def test_analyze_llm_network_error(
    test_client: httpx.AsyncClient,
    httpx_mock: HTTPXMock,
    sample_incident_data: dict
):
    """Tests handling of network error when calling LLM service."""
    # Arrange: Mock the LLM service call to raise a network error
    httpx_mock.add_exception(httpx.RequestError("Connection refused"))
    
    # Act: Send request to the agent's /analyze endpoint
    response = await test_client.post("/analyze", json=sample_incident_data)
    
    # Assert: Check response status and AnalysisResult content
    assert response.status_code == 200 # Endpoint itself should still be OK
    result = response.json()
    
    assert result["incident_id"] == sample_incident_data["incident_id"]
    assert result["analysis_source"] == "error"
    assert len(result["errors"]) > 0
    # Check for the specific error added when _call_llm_service returns None
    assert "Failed to get response from LLM service." in result["errors"]
    assert result["llm_raw_response"] is None # No raw response received
    assert result["parsed_response"] is None
    assert result["confidence_score"] is None # Or 0.1
    assert not result["actionable_insights"]

# More tests to come... 