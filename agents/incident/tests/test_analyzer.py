import pytest
import datetime
import httpx
import json # Added for complex JSON manipulation
from freezegun import freeze_time
from pytest_httpx import HTTPXMock
import sqlite3
from unittest import mock
import uuid # Added for testing UUIDs
import allure # Added for Allure reporting

# Use absolute imports from the project root
from agents.incident.models import (
    IncidentReport,
    LLMStructuredResponse,
    ActionableInsight,
    AnalysisResult,
    RootCause,         # Added
    RecommendedAction  # Added
)
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
    analyze_incident, # Added for e2e test
    LLM_SERVICE_URL,
    CACHE_DB_PATH
)

# --- Allure Feature/Story Grouping ---
FEATURE = "Incident Analysis Agent"
STORY_PROMPT = "Prompt Generation"
STORY_PARSING = "LLM Response Parsing"
STORY_CONFIDENCE = "Confidence Scoring"
STORY_INSIGHTS = "Insight Extraction"
STORY_CACHE = "Caching Logic"
STORY_E2E = "End-to-End Analysis Flow"
STORY_UTILS = "Utility Functions"

# Sample data for testing
TIMESTAMP_NOW = datetime.datetime(2024, 8, 15, 10, 30, 0)
SAMPLE_PROMPT = "Analyze this sample incident."
# OLD Response Text (for older tests if needed, or remove if updating all)
# EXPECTED_LLM_RESPONSE_TEXT = "{\"potential_root_causes\": [\"Disk full\"], \"recommended_actions\": [\"Check disk space\"], \"potential_impact\": \"Service outage\", \"confidence_explanation\": \"High confidence based on keywords.\"}"

# --- Test Fixtures ---

@pytest.fixture
def basic_incident() -> IncidentReport:
    """Provides a basic incident report fixture."""
    return IncidentReport(
        incident_id="INC-001",
        timestamp=TIMESTAMP_NOW,
        description="Server XYZ is unresponsive after package upgrade. Errors in /var/log/syslog mention 'dependency conflict'.",
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

# --- Enhanced Data Fixtures ---

@pytest.fixture
def sample_enhanced_llm_json_str() -> str:
    """Provides a sample JSON string matching the *enhanced* schema."""
    data = {
        "potential_root_causes": [
            {"cause": "Incompatible package version after upgrade", "likelihood": "High", "explanation": "Timing coincides with upgrade, error mentions dependency conflict."},
            {"cause": "Underlying disk I/O issue", "likelihood": "Low", "explanation": "Less likely given the error message, but possible."}
        ],
        "recommended_actions": [
            {"action": "Rollback package upgrade on Server XYZ", "type": "Remediate", "target": "Server XYZ", "priority": 1, "estimated_time_minutes": 60, "required_skills": ["Linux Admin", "Package Management"]},
            {"action": "Investigate dependency conflict mentioned in logs", "type": "Investigate", "target": "/var/log/syslog", "priority": 2, "estimated_time_minutes": 30, "required_skills": ["Troubleshooting"]},
            {"action": "Update system documentation with conflict details", "type": "Document", "target": "KB Article 123", "priority": 4, "estimated_time_minutes": 15, "required_skills": ["Technical Writing"]}
        ],
        "incident_category": "Software",
        "estimated_resolution_time_hours": 2.5,
        "similar_known_issues": ["INC-PREV-456", "KB Article 789"],
        "recommended_documentation": ["Package XYZ v2.0 Release Notes", "Internal Rollback Procedure Guide"],
        "confidence_explanation": "High confidence due to direct error message correlation with recent change."
    }
    return json.dumps(data, indent=2) # Return as JSON string

@pytest.fixture
def sample_enhanced_llm_response_obj(sample_enhanced_llm_json_str) -> LLMStructuredResponse:
    """Provides a parsed LLMStructuredResponse object from the enhanced JSON."""
    return LLMStructuredResponse(**json.loads(sample_enhanced_llm_json_str))

@pytest.fixture
def sample_sparse_enhanced_llm_response_obj() -> LLMStructuredResponse:
    """Provides a sparse but valid LLMStructuredResponse object."""
    return LLMStructuredResponse(
        potential_root_causes=[{"cause": "Unknown", "likelihood": "Unknown", "explanation": "Insufficient data"}],
        recommended_actions=[], # Empty list is valid
        incident_category=None, # Optional fields can be None
        estimated_resolution_time_hours=None,
        similar_known_issues=[],
        recommended_documentation=[],
        confidence_explanation="Low confidence due to lack of details."
    )

# --- Tests for _create_llm_prompt (Including Enhancement Check) ---

# Existing tests test_create_llm_prompt_basic, test_create_llm_prompt_minimal, test_create_llm_prompt_formatting remain relevant for basic structure

# NEW Test for Enhanced Prompt Content
@pytest.mark.unit
@allure.feature(FEATURE)
@allure.story(STORY_PROMPT)
@allure.severity(allure.severity_level.NORMAL)
@freeze_time(TIMESTAMP_NOW)
def test_enhanced_prompt_creation(basic_incident: IncidentReport):
    """Tests that the enhanced prompt template includes the new structural elements."""
    prompt = _create_llm_prompt(basic_incident)

    # Check for new fields/structure in the schema description within the prompt
    assert '"potential_root_causes": [' in prompt
    assert '"cause":' in prompt
    assert '"likelihood":' in prompt
    assert '"explanation":' in prompt

    assert '"recommended_actions": [' in prompt
    assert '"action":' in prompt
    assert '"type":' in prompt
    assert '"target":' in prompt
    assert '"priority":' in prompt
    assert '"estimated_time_minutes":' in prompt
    assert '"required_skills":' in prompt

    assert '"incident_category":' in prompt
    assert '"estimated_resolution_time_hours":' in prompt
    assert '"similar_known_issues":' in prompt
    assert '"recommended_documentation":' in prompt
    assert '"confidence_explanation":' in prompt

    # Check critical instructions reflect new schema
    assert "Populate the `potential_root_causes` array with objects" in prompt
    assert "Populate the `recommended_actions` array with objects" in prompt

# --- Tests for _call_llm_service (No change needed, depends on URL/payload format) ---
# Existing tests test_call_llm_service_* remain valid

# --- Tests for _parse_llm_response (Including Enhanced Parsing) ---

# Adapting previous tests to use the new structure and new validation logic

@pytest.mark.unit
@allure.feature(FEATURE)
@allure.story(STORY_PARSING)
@allure.severity(allure.severity_level.CRITICAL) # Parsing is critical
def test_parse_enhanced_llm_response_success(sample_enhanced_llm_json_str):
    """Tests parsing a valid, complex JSON string matching the enhanced schema."""
    response_str = f"```json\n{sample_enhanced_llm_json_str}\n```"
    errors = []
    result = _parse_llm_response(response_str, errors)

    assert not errors
    assert result is not None
    assert isinstance(result, LLMStructuredResponse)
    assert len(result.potential_root_causes) == 2
    assert isinstance(result.potential_root_causes[0], RootCause)
    assert result.potential_root_causes[0].cause == "Incompatible package version after upgrade"
    assert result.potential_root_causes[0].likelihood == "High"
    assert len(result.recommended_actions) == 3
    assert isinstance(result.recommended_actions[0], RecommendedAction)
    assert result.recommended_actions[0].action == "Rollback package upgrade on Server XYZ"
    assert result.recommended_actions[0].type == "Remediate"
    assert result.recommended_actions[0].priority == 1
    assert result.recommended_actions[0].estimated_time_minutes == 60
    assert result.recommended_actions[0].required_skills == ["Linux Admin", "Package Management"]
    assert result.incident_category == "Software"
    assert result.estimated_resolution_time_hours == 2.5
    assert result.similar_known_issues == ["INC-PREV-456", "KB Article 789"]
    assert result.recommended_documentation == ["Package XYZ v2.0 Release Notes", "Internal Rollback Procedure Guide"]
    assert result.confidence_explanation is not None

@pytest.mark.unit
@allure.feature(FEATURE)
@allure.story(STORY_PARSING)
@allure.severity(allure.severity_level.NORMAL)
def test_parse_enhanced_llm_response_minimal_success(sample_sparse_enhanced_llm_response_obj):
    """Tests parsing a minimal but valid enhanced JSON structure."""
    # Re-serialize the sparse object to test parsing
    json_str = sample_sparse_enhanced_llm_response_obj.model_dump_json(exclude_none=True)
    response_str = f"```json\n{json_str}\n```"
    errors = []
    result = _parse_llm_response(response_str, errors)

    assert not errors
    assert result is not None
    assert isinstance(result, LLMStructuredResponse)
    assert len(result.potential_root_causes) == 1
    assert result.potential_root_causes[0].cause == "Unknown"
    assert len(result.recommended_actions) == 0 # Empty list is valid
    assert result.incident_category is None
    assert result.estimated_resolution_time_hours is None
    assert len(result.similar_known_issues) == 0
    assert len(result.recommended_documentation) == 0
    assert result.confidence_explanation == "Low confidence due to lack of details."

@pytest.mark.unit
@allure.feature(FEATURE)
@allure.story(STORY_PARSING)
@allure.severity(allure.severity_level.NORMAL)
def test_parse_enhanced_llm_response_with_extra_text(sample_enhanced_llm_json_str):
    """Tests parsing enhanced JSON when wrapped in markdown and extra text."""
    response_str = f"Here is the analysis:\n```json\n{sample_enhanced_llm_json_str}\n```\nLet me know if you need more help."
    errors = []
    result = _parse_llm_response(response_str, errors)
    assert not errors
    assert result is not None
    assert result.incident_category == "Software" # Check one field for success

@pytest.mark.unit
@allure.feature(FEATURE)
@allure.story(STORY_PARSING)
@allure.severity(allure.severity_level.NORMAL)
def test_parse_enhanced_llm_response_invalid_syntax():
    """Tests parsing enhanced JSON with a syntax error."""
    invalid_json = '{"potential_root_causes": [{"cause":"Bad","likelihood":"High","explanation":"Test"}], "recommended_actions": [] // Missing comma }'
    response_str = f"```json\n{invalid_json}\n```"
    errors = []
    result = _parse_llm_response(response_str, errors)
    assert errors # Expect an error
    assert "Failed to decode JSON" in errors[0]
    assert result is None

@pytest.mark.unit
@allure.feature(FEATURE)
@allure.story(STORY_PARSING)
@allure.severity(allure.severity_level.NORMAL)
def test_parse_enhanced_llm_response_schema_mismatch():
    """Tests parsing JSON that is valid syntax but doesn't match the enhanced schema."""
    # Missing 'likelihood' in root cause
    mismatch_json = '{"potential_root_causes": [{"cause":"Bad","explanation":"Test"}], "recommended_actions": []}'
    response_str = f"```json\n{mismatch_json}\n```"
    errors = []
    result = _parse_llm_response(response_str, errors)
    assert errors # Expect an error
    assert "LLM response JSON does not match expected schema" in errors[0]
    assert "potential_root_causes.0.likelihood" in errors[0] # Check pydantic error detail
    assert result is None

@pytest.mark.unit
@allure.feature(FEATURE)
@allure.story(STORY_PARSING)
@allure.severity(allure.severity_level.NORMAL)
def test_parse_enhanced_llm_response_empty_string():
    """Tests parsing an empty string."""
    errors = []
    result = _parse_llm_response("", errors)
    assert errors
    assert "LLM response is not enclosed" in errors[0] # Updated error check
    assert result is None

@pytest.mark.unit
@allure.feature(FEATURE)
@allure.story(STORY_PARSING)
@allure.severity(allure.severity_level.NORMAL)
def test_parse_enhanced_llm_response_no_json():
    """Tests parsing a string with no JSON content."""
    response_str = "This is just plain text, no JSON here."
    errors = []
    result = _parse_llm_response(response_str, errors)
    assert errors
    assert "LLM response is not enclosed" in errors[0] # Updated error check
    assert result is None

# --- Tests for _calculate_confidence (Enhanced) ---

@pytest.mark.unit
@allure.feature(FEATURE)
@allure.story(STORY_CONFIDENCE)
@allure.severity(allure.severity_level.NORMAL)
def test_calculate_confidence_enhanced_parsing_failed():
    """Tests confidence when parsing completely fails (returns None)."""
    # raw_response doesn't matter much here as parsed_data is None
    confidence = _calculate_confidence(None, "some raw response")
    assert confidence == pytest.approx(0.1) # Should be very low

@pytest.mark.unit
@allure.feature(FEATURE)
@allure.story(STORY_CONFIDENCE)
@allure.severity(allure.severity_level.NORMAL)
def test_calculate_confidence_enhanced_full_success(sample_enhanced_llm_response_obj):
    """Tests confidence with a fully populated enhanced response."""
    confidence = _calculate_confidence(sample_enhanced_llm_response_obj, "dummy raw response")
    # Expect high confidence due to presence of all major fields and details
    # Score breakdown: 20(causes)+20(actions)+10(cat)+10(time)+5(issues)+5(docs)+10(cause_detail)+10(action_detail)+10(conf_expl) = 100
    assert confidence == pytest.approx(1.0)

@pytest.mark.unit
@allure.feature(FEATURE)
@allure.story(STORY_CONFIDENCE)
@allure.severity(allure.severity_level.NORMAL)
def test_calculate_confidence_enhanced_sparse_success(sample_sparse_enhanced_llm_response_obj):
    """Tests confidence with a sparse but valid enhanced response."""
    confidence = _calculate_confidence(sample_sparse_enhanced_llm_response_obj, "dummy raw response")
    # Expect lower score due to missing optional fields and minimal lists
    # Score breakdown: 20(causes)+0(actions)+0(cat)+0(time)+0(issues)+0(docs)+10(cause_detail)+0(action_detail)+10(conf_expl) = 40
    expected_score = 40.0 / 100.0
    assert confidence == pytest.approx(expected_score)

@pytest.mark.unit
@allure.feature(FEATURE)
@allure.story(STORY_CONFIDENCE)
@allure.severity(allure.severity_level.NORMAL)
def test_calculate_confidence_enhanced_missing_core():
    """Tests confidence when core lists (causes/actions) are missing."""
    data = LLMStructuredResponse(
        potential_root_causes=[], # Missing
        recommended_actions=[],   # Missing
        incident_category="Software",
        estimated_resolution_time_hours=1.0,
        similar_known_issues=[],
        recommended_documentation=[],
        confidence_explanation="Present"
    )
    confidence = _calculate_confidence(data, "dummy")
    # Score breakdown: 0(causes)+0(actions)+10(cat)+10(time)+0(issues)+0(docs)+0(cause_detail)+0(action_detail)+10(conf_expl) = 30
    expected_score = 30.0 / 100.0
    assert confidence == pytest.approx(expected_score)

# --- Tests for _extract_insights (Enhanced) ---

@pytest.fixture
def enhanced_parsed_data_for_insights(sample_enhanced_llm_response_obj) -> LLMStructuredResponse:
    """Uses the full enhanced response object fixture."""
    return sample_enhanced_llm_response_obj

@pytest.mark.unit
@allure.feature(FEATURE)
@allure.story(STORY_INSIGHTS)
@allure.severity(allure.severity_level.NORMAL)
def test_extract_insights_from_enhanced_response_structure(enhanced_parsed_data_for_insights):
    """Verifies the structure and content of insights extracted from enhanced actions."""
    incident_id = "INC-TEST-123"
    insights = _extract_insights(enhanced_parsed_data_for_insights, incident_id)

    assert len(insights) == 3 # Matches number of recommended actions

    # Check first insight maps correctly
    insight1 = insights[0]
    action1 = enhanced_parsed_data_for_insights.recommended_actions[0]
    assert isinstance(insight1, ActionableInsight)
    assert isinstance(insight1.insight_id, str) and len(insight1.insight_id) > 0 # Check UUID is generated
    assert insight1.description == action1.action
    assert insight1.type == action1.type
    assert insight1.target == action1.target
    assert insight1.priority == action1.priority
    assert insight1.estimated_time_minutes == action1.estimated_time_minutes
    assert insight1.required_skills == action1.required_skills

    # Check second insight
    insight2 = insights[1]
    action2 = enhanced_parsed_data_for_insights.recommended_actions[1]
    assert insight2.description == action2.action
    assert insight2.type == action2.type
    assert insight2.priority == action2.priority

    # Check third insight
    insight3 = insights[2]
    action3 = enhanced_parsed_data_for_insights.recommended_actions[2]
    assert insight3.description == action3.action
    assert insight3.type == action3.type
    assert insight3.priority == action3.priority

@pytest.mark.unit
@allure.feature(FEATURE)
@allure.story(STORY_INSIGHTS)
@allure.severity(allure.severity_level.NORMAL)
def test_extract_insights_enhanced_empty_actions():
    """Tests extraction when the recommended_actions list is empty."""
    data = LLMStructuredResponse(recommended_actions=[]) # Other fields don't matter here
    insights = _extract_insights(data, "INC-EMPTY")
    assert len(insights) == 0

@pytest.mark.unit
@allure.feature(FEATURE)
@allure.story(STORY_INSIGHTS)
@allure.severity(allure.severity_level.NORMAL)
def test_extract_insights_enhanced_no_parsed_data():
    """Tests extraction when parsed_data itself is None."""
    # Pass None directly, which shouldn't happen if confidence check is done first, but good to test
    insights = _extract_insights(None, "INC-NONE") # type: ignore
    assert len(insights) == 0

# --- Tests for Caching (_get_incident_summary, _check_cache, _add_to_cache) ---
# Existing tests should still work, but we need to ensure AnalysisResult with the
# *new* structure can be cached and retrieved.

@pytest.fixture
def sample_incident_different() -> IncidentReport:
    """Provides an incident with a different description for cache miss testing."""
    return IncidentReport(incident_id="INC-CACHE-03", description="Database server slow.")

@pytest.fixture(autouse=True)
def setup_test_db(monkeypatch):
    """Fixture to set up an in-memory SQLite database connection for each test
       where the connection is explicitly passed to the cache functions.
    """
    # Use monkeypatch to temporarily change the CACHE_DB_PATH
    # This ensures that even if a function *doesn't* get the connection passed,
    # it still uses an in-memory db (though it might be a different one).
    monkeypatch.setattr('agents.incident.analyzer.CACHE_DB_PATH', ':memory:')
    
    # Create a single in-memory connection for the test
    conn = None
    try:
        # Use a URI for shared in-memory cache visible across connections in the same thread
        # This might be more reliable than simple :memory:
        conn_uri = "file:memdb_test?mode=memory&cache=shared"
        conn = sqlite3.connect(conn_uri, uri=True)
        _init_cache_db(conn) # Initialize the table using this specific connection
        yield conn # Provide the connection to the test function
    finally:
        if conn:
            conn.close() # Ensure the connection is closed after the test

@pytest.mark.unit
@allure.feature(FEATURE)
@allure.story(STORY_UTILS)
@allure.severity(allure.severity_level.MINOR)
def test_get_incident_summary_consistency():
    """Test that the summary function is consistent and handles basic normalization."""
    desc1 = "Network is down in building A."
    desc2 = " network IS down in Building a.  "
    desc3 = "Database server slow."
    assert _get_incident_summary(desc1) == _get_incident_summary(desc2)
    assert _get_incident_summary(desc1) != _get_incident_summary(desc3)

@pytest.mark.unit
@allure.feature(FEATURE)
@allure.story(STORY_CACHE)
@allure.severity(allure.severity_level.NORMAL)
def test_check_cache_enhanced_miss(sample_incident_different, setup_test_db):
    """Verify cache miss works the same way."""
    conn = setup_test_db # Get the connection from the fixture
    result = _check_cache(sample_incident_different, conn=conn)
    assert result is None

@pytest.mark.unit
@allure.feature(FEATURE)
@allure.story(STORY_CACHE)
@allure.severity(allure.severity_level.CRITICAL) # Caching is critical
def test_add_to_cache_and_hit_enhanced(basic_incident, sample_enhanced_llm_response_obj, setup_test_db):
    """Test adding and retrieving an enhanced AnalysisResult."""
    conn = setup_test_db # Get the connection from the fixture
    # Create a full AnalysisResult using the enhanced response object
    full_result = AnalysisResult(
        incident_id=basic_incident.incident_id,
        parsed_response=sample_enhanced_llm_response_obj,
        actionable_insights=_extract_insights(sample_enhanced_llm_response_obj, basic_incident.incident_id),
        confidence_score=_calculate_confidence(sample_enhanced_llm_response_obj, "dummy"),
        analysis_source="llm",
        llm_raw_response="dummy raw response"
    )

    # Add to cache using the connection
    _add_to_cache(basic_incident, full_result, conn=conn)
    
    # Check cache using the connection
    cached_result = _check_cache(basic_incident, conn=conn)

    assert cached_result is not None
    assert cached_result.incident_id == basic_incident.incident_id
    assert cached_result.analysis_source == "llm" # Source should be original source, not 'cache' yet
    assert cached_result.parsed_response is not None
    # Verify nested structure was preserved through serialization/deserialization
    assert cached_result.parsed_response.incident_category == "Software"
    assert len(cached_result.parsed_response.potential_root_causes) == 2
    assert cached_result.parsed_response.potential_root_causes[0].likelihood == "High"
    assert len(cached_result.parsed_response.recommended_actions) == 3
    assert cached_result.parsed_response.recommended_actions[0].priority == 1
    assert len(cached_result.actionable_insights) == 3
    assert cached_result.actionable_insights[0].priority == 1

# Existing test_add_to_cache_update can likely remain similar, just ensure the updated result is also enhanced.
# Existing test_add_to_cache_skips_errors remains valid.

# --- End-to-End Test for analyze_incident (Enhanced) ---

@pytest.mark.unit # Still unit as it mocks external deps
@allure.feature(FEATURE)
@allure.story(STORY_E2E)
@allure.severity(allure.severity_level.BLOCKER) # E2E flow is critical
@pytest.mark.asyncio
@mock.patch('agents.incident.analyzer._add_to_cache') # Mock adding to cache
@mock.patch('agents.incident.analyzer._check_cache') # Mock checking cache
async def test_analyze_incident_e2e_enhanced(
    mock_check_cache: mock.MagicMock,
    mock_add_to_cache: mock.MagicMock,
    basic_incident: IncidentReport,
    sample_enhanced_llm_json_str: str,
    httpx_mock: HTTPXMock,
    setup_test_db: sqlite3.Connection # Keep setup_test_db only if other tests need it implicitly
):
    """Tests the full analyze_incident flow with mocked cache and enhanced LLM response."""
    # conn = setup_test_db # No longer need connection directly if mocking cache funcs

    # Arrange: Mock cache to simulate a miss
    mock_check_cache.return_value = None

    # Arrange: Mock the LLM service response
    httpx_mock.add_response(
        url=LLM_SERVICE_URL,
        method="POST",
        json={"text": f"```json\n{sample_enhanced_llm_json_str}\n```"}, # Simulate LLM wrapping in markdown
        status_code=200
    )

    # Act: Run the main analysis function
    result = await analyze_incident(basic_incident)

    # Assert: Check the final AnalysisResult
    assert result is not None
    assert result.incident_id == basic_incident.incident_id
    assert result.analysis_source == "llm"
    assert not result.errors # Expect no errors in this flow
    assert result.llm_raw_response is not None
    assert sample_enhanced_llm_json_str in result.llm_raw_response # Check raw response was stored

    # Assert Parsed Response (check key fields)
    assert result.parsed_response is not None
    assert result.parsed_response.incident_category == "Software"
    assert len(result.parsed_response.potential_root_causes) == 2
    assert result.parsed_response.potential_root_causes[0].cause == "Incompatible package version after upgrade"
    assert len(result.parsed_response.recommended_actions) == 3
    assert result.parsed_response.recommended_actions[0].action == "Rollback package upgrade on Server XYZ"

    # Assert Actionable Insights
    assert len(result.actionable_insights) == 3
    insight1 = result.actionable_insights[0]
    assert insight1.description == "Rollback package upgrade on Server XYZ"
    assert insight1.type == "Remediate"
    assert insight1.priority == 1
    assert insight1.estimated_time_minutes == 60
    assert insight1.required_skills == ["Linux Admin", "Package Management"]

    # Assert Confidence Score (should be high)
    assert result.confidence_score is not None
    assert result.confidence_score > 0.8 # Expect high confidence for this detailed response

    # Assert Processing Time
    assert result.processing_time_seconds is not None and result.processing_time_seconds > 0

    # Assert Cache function calls
    mock_check_cache.assert_called_once_with(basic_incident)
    mock_add_to_cache.assert_called_once_with(basic_incident, result)

# --- Keep Old Tests (Optional, or remove/update if fully replaced) ---
# If you want to maintain backward compatibility tests using the old simple string format,
# you might need separate fixtures and potentially conditional logic or separate test files.
# For now, assuming the goal is to fully transition to the enhanced format.

# ==================================================================
# Example of how you *might* keep an old test structure (if needed)
# ==================================================================
# @pytest.fixture
# def sample_old_llm_json_str() -> str:
#     data = {
#         "potential_root_causes": ["Old Cause 1", "Old Cause 2"],
#         "recommended_actions": ["Old Action 1", "Old Action 2"],
#         "potential_impact": "Old Impact",
#         "confidence_explanation": "Old Explanation"
#     }
#     return json.dumps(data)
    
# def test_parse_old_response_format(sample_old_llm_json_str):
#     # This test would FAIL with the new _parse_llm_response because the
#     # structure doesn't match LLMStructuredResponse anymore.
#     # You would need a different parsing/validation logic or model if you
#     # need to support both formats simultaneously.
#     pass
# ================================================================== 