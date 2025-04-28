import pytest
import datetime
import httpx
from freezegun import freeze_time
from pytest_httpx import HTTPXMock # Import the mocker

# Use absolute imports from the project root
from agents.incident.models import IncidentReport
from agents.incident.analyzer import _create_llm_prompt, _call_llm_service, LLM_SERVICE_URL

# Sample data for testing
TIMESTAMP_NOW = datetime.datetime(2024, 8, 15, 10, 30, 0)
SAMPLE_PROMPT = "Analyze this sample incident."
EXPECTED_LLM_RESPONSE_TEXT = "{\"potential_root_causes\": [\"Disk full\"], \"recommended_actions\": [\"Check disk space\"], \"potential_impact\": \"Service outage\", \"confidence_explanation\": \"High confidence based on keywords.\"}"


@pytest.fixture
def basic_incident() -> IncidentReport:
    """Provides a basic incident report fixture."""
    return IncidentReport(
        incident_id="INC-001",
        timestamp=TIMESTAMP_NOW,
        description="Server XYZ is unresponsive.",
        priority=1,
        affected_systems=["Server XYZ", "Auth Service"],
        reporter="User A"
    )

@pytest.fixture
def minimal_incident() -> IncidentReport:
    """Provides an incident report with only required fields."""
    return IncidentReport(
        incident_id="INC-002",
        timestamp=TIMESTAMP_NOW, # Using the same timestamp for consistency
        description="Database connection errors."
        # Optional fields are None
    )

# --- Tests for _create_llm_prompt --- 

@freeze_time(TIMESTAMP_NOW)
def test_create_llm_prompt_basic(basic_incident: IncidentReport):
    """Tests prompt creation with a fully populated incident report."""
    prompt = _create_llm_prompt(basic_incident)

    # Check if key fields are included and correctly formatted
    assert f"ID: {basic_incident.incident_id}" in prompt
    assert f"Timestamp: {TIMESTAMP_NOW.isoformat()}" in prompt
    assert f"Priority: {basic_incident.priority}" in prompt
    assert f"Affected Systems: {', '.join(basic_incident.affected_systems)}" in prompt
    assert f"Reporter: {basic_incident.reporter}" in prompt
    assert f"Description:\n```\n{basic_incident.description}\n```" in prompt

    # Check for the overall structure
    assert "Analyze the following incident report" in prompt
    assert "Required JSON Output Format:" in prompt
    assert "Instructions for Analysis:" in prompt
    assert "JSON Response:\n```json" in prompt
    assert "potential_root_causes" in prompt
    assert "recommended_actions" in prompt

@freeze_time(TIMESTAMP_NOW)
def test_create_llm_prompt_minimal(minimal_incident: IncidentReport):
    """Tests prompt creation with minimal incident data (optional fields missing)."""
    prompt = _create_llm_prompt(minimal_incident)

    # Check if key fields are included
    assert f"ID: {minimal_incident.incident_id}" in prompt
    assert f"Timestamp: {TIMESTAMP_NOW.isoformat()}" in prompt
    assert f"Description:\n```\n{minimal_incident.description}\n```" in prompt

    # Check how missing optional fields are handled
    assert "Priority: Not specified" in prompt
    assert "Affected Systems: Not specified" in prompt
    assert "Reporter: Not specified" in prompt

    # Check structure remains
    assert "Analyze the following incident report" in prompt
    assert "Required JSON Output Format:" in prompt
    assert "JSON Response:\n```json" in prompt

@freeze_time(TIMESTAMP_NOW)
def test_create_llm_prompt_formatting(basic_incident: IncidentReport):
    """Tests specific formatting aspects of the prompt."""
    prompt = _create_llm_prompt(basic_incident)

    # Ensure description is wrapped in markdown code block
    assert f"Description:\n```\n{basic_incident.description}\n```" in prompt

    # Ensure the final line prompts for JSON
    assert prompt.endswith("JSON Response:\n```json\n")

# --- Tests for _call_llm_service --- 

@pytest.mark.asyncio
async def test_call_llm_service_success(httpx_mock: HTTPXMock):
    """Tests successful call to the LLM service."""
    # Arrange: Mock the response
    httpx_mock.add_response(
        url=LLM_SERVICE_URL,
        method="POST",
        json={"text": EXPECTED_LLM_RESPONSE_TEXT, "processing_time": 1.23},
        status_code=200
    )

    # Act: Call the function
    result = await _call_llm_service(SAMPLE_PROMPT)

    # Assert: Check the result and that the request was made
    assert result == EXPECTED_LLM_RESPONSE_TEXT
    request = httpx_mock.get_request()
    assert request is not None
    assert request.url == LLM_SERVICE_URL
    assert request.method == "POST"
    assert request.read().decode() == f'{{"prompt": "{SAMPLE_PROMPT}"}}'

@pytest.mark.asyncio
async def test_call_llm_service_http_error(httpx_mock: HTTPXMock):
    """Tests handling of HTTP status errors (e.g., 500) from LLM service."""
    # Arrange: Mock an error response
    httpx_mock.add_response(
        url=LLM_SERVICE_URL,
        method="POST",
        text="Internal Server Error",
        status_code=500
    )

    # Act: Call the function
    result = await _call_llm_service(SAMPLE_PROMPT)

    # Assert: Check that None is returned (indicating an error)
    assert result is None

@pytest.mark.asyncio
async def test_call_llm_service_request_error(httpx_mock: HTTPXMock):
    """Tests handling of network request errors (e.g., timeout, connection refused)."""
    # Arrange: Mock a network error
    httpx_mock.add_exception(httpx.RequestError("Connection refused"))

    # Act: Call the function
    result = await _call_llm_service(SAMPLE_PROMPT)

    # Assert: Check that None is returned
    assert result is None

@pytest.mark.asyncio
async def test_call_llm_service_missing_text_field(httpx_mock: HTTPXMock):
    """Tests handling of a successful response missing the 'text' field."""
    # Arrange: Mock a response without the 'text' field
    httpx_mock.add_response(
        url=LLM_SERVICE_URL,
        method="POST",
        json={"processing_time": 1.23}, # Missing 'text'
        status_code=200
    )

    # Act: Call the function
    result = await _call_llm_service(SAMPLE_PROMPT)

    # Assert: Check that None is returned
    assert result is None

@pytest.mark.asyncio
async def test_call_llm_service_invalid_json_response(httpx_mock: HTTPXMock):
    """Tests handling of a response that is not valid JSON."""
    # Arrange: Mock a non-JSON response
    httpx_mock.add_response(
        url=LLM_SERVICE_URL,
        method="POST",
        text="<htm>This is not JSON</html>",
        status_code=200
    )

    # Act: Call the function
    result = await _call_llm_service(SAMPLE_PROMPT)

    # Assert: Check that None is returned
    assert result is None 