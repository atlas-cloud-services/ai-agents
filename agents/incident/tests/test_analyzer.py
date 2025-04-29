import pytest
import datetime
import httpx
from freezegun import freeze_time
from pytest_httpx import HTTPXMock
import sqlite3
from unittest import mock

# Use absolute imports from the project root
from agents.incident.models import IncidentReport, LLMStructuredResponse, ActionableInsight, AnalysisResult
from agents.incident.analyzer import (
    _create_llm_prompt, 
    _call_llm_service, 
    _parse_llm_response,
    _calculate_confidence,
    _extract_insights,
    _get_incident_summary,
    _check_cache,
    _add_to_cache,
    _init_cache_db,
    LLM_SERVICE_URL,
    CACHE_DB_PATH
)

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
    assert "**REQUIRED JSON OUTPUT SCHEMA:**" in prompt
    assert "**CRITICAL INSTRUCTIONS FOR LLM:**" in prompt
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
    assert "**REQUIRED JSON OUTPUT SCHEMA:**" in prompt
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

# --- Tests for _parse_llm_response --- 

VALID_JSON_STRING = '''
{
  "potential_root_causes": [
    "Cause A",
    "Cause B"
  ],
  "recommended_actions": [
    "Action 1",
    "Action 2"
  ],
  "potential_impact": "High",
  "confidence_explanation": "Based on logs."
}
'''

VALID_JSON_STRING_MINIMAL = '''
{
  "potential_root_causes": [],
  "recommended_actions": []
}
''' # Minimal valid response (optional fields are None)

JSON_WITH_EXTRA_TEXT = '''
Some introductory text from the LLM.
```json
{
  "potential_root_causes": ["Network issue"],
  "recommended_actions": ["Check connectivity"],
  "potential_impact": "Connectivity loss",
  "confidence_explanation": "Likely cause."
}
```
And some trailing text.
'''

INVALID_JSON_SYNTAX = '''
{
  "potential_root_causes": ["Bad syntax"],
  "recommended_actions": ["Fix it"],
  "potential_impact": "Medium"
  "confidence_explanation": "Uncertain" // Missing comma
}
'''

MISSING_REQUIRED_FIELD_JSON = '''
{
  "recommended_actions": ["Action X"],
  "potential_impact": "Low",
  "confidence_explanation": "Guessing."
}
''' # Missing potential_root_causes

WRONG_DATA_TYPE_JSON = '''
{
  "potential_root_causes": "Just one cause", 
  "recommended_actions": ["Action Y"],
  "potential_impact": "Low",
  "confidence_explanation": "Maybe?"
}
''' # potential_root_causes should be a list

def test_parse_llm_response_success():
    """Tests parsing a valid and complete JSON response."""
    errors = []
    result = _parse_llm_response(VALID_JSON_STRING, errors)
    assert isinstance(result, LLMStructuredResponse)
    assert result.potential_root_causes == ["Cause A", "Cause B"]
    assert result.recommended_actions == ["Action 1", "Action 2"]
    assert result.potential_impact == "High"
    assert result.confidence_explanation == "Based on logs."
    assert not errors # No errors should be added

def test_parse_llm_response_minimal_success():
    """Tests parsing a valid JSON with only required fields."""
    errors = []
    result = _parse_llm_response(VALID_JSON_STRING_MINIMAL, errors)
    assert isinstance(result, LLMStructuredResponse)
    assert result.potential_root_causes == []
    assert result.recommended_actions == []
    assert result.potential_impact is None
    assert result.confidence_explanation is None
    assert not errors

def test_parse_llm_response_with_extra_text():
    """Tests parsing valid JSON surrounded by extra text."""
    errors = []
    result = _parse_llm_response(JSON_WITH_EXTRA_TEXT, errors)
    assert isinstance(result, LLMStructuredResponse)
    assert result.potential_root_causes == ["Network issue"]
    assert result.recommended_actions == ["Check connectivity"]
    assert result.potential_impact == "Connectivity loss"
    assert result.confidence_explanation == "Likely cause."
    assert not errors

def test_parse_llm_response_invalid_syntax():
    """Tests parsing a response with invalid JSON syntax."""
    errors = []
    result = _parse_llm_response(INVALID_JSON_SYNTAX, errors)
    assert result is None
    assert len(errors) == 1 # One error should be added
    # Check for the updated error message prefix
    assert "Failed to decode extracted JSON string" in errors[0]

def test_parse_llm_response_missing_required_field():
    """Tests parsing valid JSON missing a field (which is optional in the model)."""
    errors = []
    result = _parse_llm_response(MISSING_REQUIRED_FIELD_JSON, errors)
    assert result is not None # Should return an object as fields are Optional
    assert isinstance(result, LLMStructuredResponse)
    assert result.potential_root_causes is None # The missing field should be None
    assert result.recommended_actions == ["Action X"] # Check other fields parsed
    assert errors == [] # No parsing or validation error should occur

def test_parse_llm_response_wrong_data_type():
    """Tests parsing valid JSON with a field of the wrong data type."""
    errors = []
    result = _parse_llm_response(WRONG_DATA_TYPE_JSON, errors)
    assert result is None # Parsing succeeds, but validation fails, returning None
    assert len(errors) == 1
    assert errors[0].startswith("LLM response JSON failed validation") # Check start of actual error

def test_parse_llm_response_empty_string():
    """Tests parsing an empty string response."""
    errors = []
    result = _parse_llm_response("", errors)
    assert result is None
    assert len(errors) == 1
    assert "LLM response was empty" in errors[0]

def test_parse_llm_response_no_json():
    """Tests parsing a string that does not contain a JSON object."""
    errors = []
    result = _parse_llm_response("This is just plain text.", errors)
    assert result is None
    assert len(errors) == 1
    # Check for the updated error message
    assert "Could not find JSON object structure" in errors[0] 

# --- Tests for _calculate_confidence ---

@pytest.fixture
def full_parsed_data() -> LLMStructuredResponse:
    """Provides a fully populated LLMStructuredResponse fixture."""
    return LLMStructuredResponse(
        potential_root_causes=["Cause A", "Cause B"],
        recommended_actions=["Action 1", "Action 2"],
        potential_impact="High impact scenario.",
        confidence_explanation="Very confident based on data."
    )

@pytest.fixture
def minimal_parsed_data() -> LLMStructuredResponse:
    """Provides an LLMStructuredResponse with only required fields (empty lists)."""
    return LLMStructuredResponse(
        potential_root_causes=[],
        recommended_actions=[]
        # Optional fields are None by default
    )

@pytest.fixture
def partial_parsed_data_whitespace() -> LLMStructuredResponse:
    """Provides data with some fields present but only whitespace."""
    return LLMStructuredResponse(
        potential_root_causes=["Cause C"],
        recommended_actions=["Action 3"],
        potential_impact="   ", # Whitespace only
        confidence_explanation="  "
    )

def test_calculate_confidence_parsing_failed():
    """Tests confidence score when parsing failed (input is None)."""
    score = _calculate_confidence(None, "some raw response")
    assert score == pytest.approx(0.1)

def test_calculate_confidence_full_success(full_parsed_data):
    """Tests confidence score with a complete and valid parsed response."""
    score = _calculate_confidence(full_parsed_data, "some raw response")
    # Base (0.5) + causes (0.1) + actions (0.1) + impact (0.1) + explanation (0.1) = 0.9
    assert score == pytest.approx(0.9)

def test_calculate_confidence_minimal_success(minimal_parsed_data):
    """Tests confidence score with minimal valid data (empty lists, no optional fields)."""
    score = _calculate_confidence(minimal_parsed_data, "some raw response")
    # Base (0.5) + empty causes (0) + empty actions (0) + no impact (0) + no explanation (0) = 0.5
    assert score == pytest.approx(0.5)

def test_calculate_confidence_partial_data_whitespace(partial_parsed_data_whitespace):
    """Tests that fields with only whitespace do not increase score."""
    score = _calculate_confidence(partial_parsed_data_whitespace, "some raw response")
    # Base (0.5) + causes (0.1) + actions (0.1) + whitespace impact (0) + whitespace explanation (0) = 0.7
    assert score == pytest.approx(0.7)

def test_calculate_confidence_partial_data_missing_optional(minimal_parsed_data):
    """Tests score when optional fields are missing (covered by minimal test, but explicit)."""
    # Reuse minimal_parsed_data which has optional fields as None
    minimal_parsed_data.potential_root_causes = ["One Cause"] # Add one required field
    score = _calculate_confidence(minimal_parsed_data, "some raw response")
    # Base (0.5) + causes (0.1) + empty actions (0) + no impact (0) + no explanation (0) = 0.6
    assert score == pytest.approx(0.6)

def test_calculate_confidence_max_score(full_parsed_data: LLMStructuredResponse):
    """Ensures score does not exceed 1.0 (using full_parsed_data)."""
    # This test uses the same data as full_success, just confirms the cap explicitly
    score = _calculate_confidence(full_parsed_data, "some raw response") 
    assert score <= 1.0 

# --- Tests for _extract_insights ---

@pytest.fixture
def parsed_data_for_insights() -> LLMStructuredResponse:
    """Provides parsed data with various actions for insight extraction tests."""
    return LLMStructuredResponse(
        potential_root_causes=["Some cause"],
        recommended_actions=[
            "Please check the logs on server DB01 carefully.",
            "Restart the primary application service.",
            "Review and configure the timeout setting.",
            "Update the internal KB article #456 with resolution steps.",
            "Escalate to the database team if the issue persists.",
            "Monitor system performance closely for the next hour.",
            "Verify that the connection pool is healthy.",
            "Perform a routine system check.", # Should default to investigate
            "notify the network team"
        ],
        potential_impact="High",
        confidence_explanation="Based on analysis."
    )

INCIDENT_ID_FOR_INSIGHTS = "INC-INS-001"

def test_extract_insights_empty_actions():
    """Tests insight extraction when there are no recommended actions."""
    parsed_data = LLMStructuredResponse(potential_root_causes=[], recommended_actions=[])
    insights = _extract_insights(parsed_data, INCIDENT_ID_FOR_INSIGHTS)
    assert insights == []

def test_extract_insights_no_parsed_data():
    """Tests insight extraction when the recommended_actions list is missing or None."""
    # Scenario 1: recommended_actions is explicitly None (should default to empty list in model, but test robustness of function)
    # We need to handle the case where the list *within* a valid object might be empty or None if models change
    # Create a valid object first, then simulate missing actions if possible
    parsed_data_no_actions = LLMStructuredResponse(potential_root_causes=["X"], recommended_actions=[])
    parsed_data_no_actions.recommended_actions = None # Simulate it being None *after* creation if allowed by model flexibility (though current model requires list)
    
    # Test the function's handling if actions is None
    insights_none = _extract_insights(parsed_data_no_actions, INCIDENT_ID_FOR_INSIGHTS)
    assert insights_none == []
    
    # Scenario 2: recommended_actions is an empty list
    parsed_data_empty_actions = LLMStructuredResponse(potential_root_causes=["X"], recommended_actions=[])
    insights_empty = _extract_insights(parsed_data_empty_actions, INCIDENT_ID_FOR_INSIGHTS)
    assert insights_empty == []

def test_extract_insights_classifies_types(parsed_data_for_insights):
    """Tests that different action types are correctly classified."""
    insights = _extract_insights(parsed_data_for_insights, INCIDENT_ID_FOR_INSIGHTS)
    assert len(insights) == 9
    
    # Check classifications based on keywords
    assert insights[0].type == "investigate" # check logs
    assert insights[1].type == "restart"     # Restart
    assert insights[2].type == "configure"   # configure
    assert insights[3].type == "update_doc"  # Update kb
    assert insights[4].type == "escalate"    # Escalate
    assert insights[5].type == "monitor"     # Monitor
    assert insights[6].type == "verify"      # Verify
    assert insights[7].type == "investigate" # Default
    assert insights[8].type == "escalate"    # notify

def test_extract_insights_preserves_description(parsed_data_for_insights):
    """Tests that the original action description is preserved."""
    insights = _extract_insights(parsed_data_for_insights, INCIDENT_ID_FOR_INSIGHTS)
    assert insights[0].description == parsed_data_for_insights.recommended_actions[0]
    assert insights[1].description == parsed_data_for_insights.recommended_actions[1]
    # ... and so on for others

def test_extract_insights_generates_ids(parsed_data_for_insights):
    """Tests that unique insight IDs are generated correctly."""
    insights = _extract_insights(parsed_data_for_insights, INCIDENT_ID_FOR_INSIGHTS)
    assert insights[0].insight_id == f"{INCIDENT_ID_FOR_INSIGHTS}-insight-1"
    assert insights[1].insight_id == f"{INCIDENT_ID_FOR_INSIGHTS}-insight-2"
    assert insights[8].insight_id == f"{INCIDENT_ID_FOR_INSIGHTS}-insight-9"

def test_extract_insights_target_is_none(parsed_data_for_insights):
    """Tests that the target field is currently always None."""
    insights = _extract_insights(parsed_data_for_insights, INCIDENT_ID_FOR_INSIGHTS)
    for insight in insights:
        assert insight.target is None 

# --- Tests for Caching (_check_cache, _add_to_cache) ---

# Use a consistent NAMED path for the mocked in-memory DB during tests
# mode=memory creates an in-memory DB
# cache=shared allows multiple connections in the same process to see it
TEST_DB = "file:test_incident_cache?mode=memory&cache=shared"

@pytest.fixture
def sample_incident_for_cache() -> IncidentReport:
    return IncidentReport(incident_id="INC-CACHE-01", description="Network is down in building A.")

@pytest.fixture
def sample_incident_for_cache_alt() -> IncidentReport:
    # Same description hash as sample_incident_for_cache, different ID
    return IncidentReport(incident_id="INC-CACHE-02", description="Network is down in building A.")

@pytest.fixture
def sample_incident_different() -> IncidentReport:
    return IncidentReport(incident_id="INC-CACHE-03", description="Database server slow.")

@pytest.fixture
def sample_analysis_result(sample_incident_for_cache) -> AnalysisResult:
    return AnalysisResult(
        incident_id=sample_incident_for_cache.incident_id,
        analysis_source="llm",
        confidence_score=0.85,
        parsed_response=LLMStructuredResponse(
            potential_root_causes=["Switch failure"],
            recommended_actions=["Check switch  SWA-01"]
        ),
        actionable_insights=[
            ActionableInsight(insight_id="INC-CACHE-01-insight-1", description="Check switch SWA-01", type="investigate")
        ]
    )

@pytest.fixture
def sample_analysis_result_error(sample_incident_different) -> AnalysisResult:
    return AnalysisResult(
        incident_id=sample_incident_different.incident_id,
        analysis_source="error",
        errors=["LLM call failed"],
        confidence_score=0.1 # Low confidence due to error
    )

@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch):
    """Fixture to ensure tests use an in-memory DB and the table exists."""
    # Patch CACHE_DB_PATH to use in-memory DB for all tests in this module
    monkeypatch.setattr('agents.incident.analyzer.CACHE_DB_PATH', TEST_DB)
    
    # Explicitly initialize the (mocked) database using the patched path
    # This ensures the table is created using the same logic as the main code,
    # but directed to the in-memory DB.
    _init_cache_db() 
    
    # Optional: Could add a cleanup step to delete the in-memory db if needed,
    # but :memory: usually handles this.
    yield # Let the test run
    # Cleanup (optional, as :memory: is volatile)
    try:
        conn = sqlite3.connect(TEST_DB)
        conn.execute("DROP TABLE IF EXISTS incident_analysis_cache")
        conn.commit()
        conn.close()
    except sqlite3.Error:
        pass # Ignore errors during cleanup

def test_get_incident_summary_consistency():
    """Test that the summary function is consistent and handles basic normalization."""
    desc1 = "Network is down in building A."
    desc2 = " network IS down in Building a.  "
    desc3 = "Database server slow."
    assert _get_incident_summary(desc1) == _get_incident_summary(desc2)
    assert _get_incident_summary(desc1) != _get_incident_summary(desc3)

def test_check_cache_miss(sample_incident_different):
    """Test checking cache for an item that doesn't exist."""
    result = _check_cache(sample_incident_different)
    assert result is None

def test_add_to_cache_and_hit(sample_incident_for_cache, sample_analysis_result):
    """Test adding an item to the cache and then retrieving it."""
    # 1. Add to cache
    _add_to_cache(sample_incident_for_cache, sample_analysis_result)
    
    # 2. Check cache
    cached_result = _check_cache(sample_incident_for_cache)
    
    # 3. Assertions
    assert cached_result is not None
    # Compare relevant fields, ignore timestamps potentially
    assert cached_result.incident_id == sample_analysis_result.incident_id
    assert cached_result.analysis_source == sample_analysis_result.analysis_source
    assert cached_result.confidence_score == sample_analysis_result.confidence_score
    assert cached_result.parsed_response == sample_analysis_result.parsed_response
    assert cached_result.actionable_insights == sample_analysis_result.actionable_insights

def test_add_to_cache_update(sample_incident_for_cache, sample_incident_for_cache_alt, sample_analysis_result):
    """Test that adding an item with the same summary updates the existing entry."""
    # 1. Add initial result
    _add_to_cache(sample_incident_for_cache, sample_analysis_result)
    
    # 2. Create a modified result for the *same description hash* but different incident ID
    updated_result_data = sample_analysis_result.model_copy(deep=True)
    updated_result_data.incident_id = sample_incident_for_cache_alt.incident_id
    updated_result_data.confidence_score = 0.99 # Change a field
    
    # 3. Add the updated result (should replace the old one due to summary key)
    _add_to_cache(sample_incident_for_cache_alt, updated_result_data)
    
    # 4. Check cache using the original incident (same summary)
    cached_result = _check_cache(sample_incident_for_cache)
    
    # 5. Assertions - Should retrieve the UPDATED result
    assert cached_result is not None
    assert cached_result.incident_id == sample_incident_for_cache_alt.incident_id # ID should be from the second add
    assert cached_result.confidence_score == 0.99 # Confidence should be updated
    assert cached_result.parsed_response == sample_analysis_result.parsed_response # Other parts remain same

def test_add_to_cache_skips_errors(sample_incident_different, sample_analysis_result_error):
    """Test that results with analysis_source='error' are not cached."""
    # 1. Attempt to add the error result to cache
    _add_to_cache(sample_incident_different, sample_analysis_result_error)
    
    # 2. Check cache - it should be a miss
    cached_result = _check_cache(sample_incident_different)
    
    # 3. Assert
    assert cached_result is None

# Optional: Test DB error scenarios using mocking if needed
# e.g., mock conn.cursor().execute() to raise sqlite3.Error 