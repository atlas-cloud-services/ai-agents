import pytest
import datetime
from freezegun import freeze_time

# Use absolute imports from the project root
from agents.incident.models import IncidentReport
from agents.incident.analyzer import _create_llm_prompt

# Sample data for testing
TIMESTAMP_NOW = datetime.datetime(2024, 8, 15, 10, 30, 0)

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