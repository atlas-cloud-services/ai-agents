# Incident Analysis Agent

This agent analyzes incident reports to provide structured insights, potential causes, and recommended actions.

## Purpose

*   Automate the initial triage and analysis of incident reports.
*   Leverage LLMs to understand unstructured incident descriptions.
*   Provide structured, actionable outputs with confidence scores to support engineers.
*   Identify patterns and improve efficiency by referencing historical incidents via caching.

## Implementation Details

*   **Location:** `agents/incident/`
*   **Core Files:**
    *   `main.py`: FastAPI application providing the `/analyze` endpoint and handling startup (DB init, MCP registration).
    *   `models.py`: Defines Pydantic models for input (`IncidentReport`), expected LLM output (`LLMStructuredResponse`), actionable steps (`ActionableInsight`), final agent output (`AnalysisResult`), and cache structure (`CacheEntry`).
    *   `analyzer.py`: Contains the core analysis logic (`analyze_incident` function and helpers for caching, LLM interaction, parsing, scoring, insights).
    *   `tests/test_analyzer.py`: Contains unit tests (`pytest`) for the `analyzer.py` functions.
    *   `tests/test_incident_agent_e2e.py`: Contains end-to-end tests (`pytest`) for the `/analyze` API endpoint, mocking external dependencies.
*   **Dependencies:** `fastapi`, `uvicorn`, `pydantic`, `httpx`, `pytest`, `freezegun`, `pytest-httpx`, `pytest-asyncio`.
*   **Data:** `incident_cache.db` (SQLite file created in the working directory on first run if caching is active).

## Analysis Workflow (via `/analyze` endpoint)

1.  **Receive `IncidentReport`**: API receives POST request with incident data.
2.  **Delegate to `analyze_incident`**: The endpoint calls the core analysis function.
3.  **Cache Check**: Generate incident summary hash. Check SQLite cache (`_check_cache`). If hit, return cached `AnalysisResult` (updating timestamp/source).
4.  **Prompt Generation**: If cache miss, format the incident data into a structured prompt.
5.  **LLM Call**: Send the prompt to the LLM Service (`_call_llm_service`).
6.  **Response Parsing**: Receive the raw text response. Extract and validate JSON (`_parse_llm_response`).
7.  **Confidence Scoring**: Evaluate the quality/reliability of the parsed response (`_calculate_confidence`).
8.  **Insight Extraction**: Identify and structure actionable steps (`ActionableInsight`) (`_extract_insights`).
9.  **Caching**: If analysis was successful (not source='error'), add the `AnalysisResult` to the SQLite cache (`_add_to_cache`).
10. **Return `AnalysisResult`**: Send back the final structured analysis (from cache or new analysis) as the API response.

## How to Run/Test

*   **Unit Tests:**
    *   Run from the project root: `pytest tests/test_analyzer.py`
*   **End-to-End Tests (Recommended):**
    *   These test the API endpoint logic by mocking external services (LLM).
    *   Run from the project root: `pytest tests/test_incident_agent_e2e.py`
*   **Running the Service:**
    *   Ensure the LLM Service (and optionally MCP) is running on its configured port (default: 8001).
    *   Activate the virtual environment: `source venv/bin/activate`
    *   From the project root (`ACS-AI-AGENTS`), run: 
        ```bash
        python3 -m uvicorn agents.incident.main:app --reload --port 8003
        ```
    *   Access the API docs at `http://127.0.0.1:8003/docs`.
    *   Send POST requests to `http://127.0.0.1:8003/analyze` with an `IncidentReport` JSON body.

## Current Status (as of YYYY-MM-DD)

*   Core data models defined.
*   FastAPI endpoint (`/analyze`) implemented.
*   Core analysis logic (`analyzer.py`) implemented and unit tested.
    *   Prompt generation.
    *   LLM Service interaction (via `httpx`).
    *   Response parsing (handling markdown, flexible model validation).
    *   Confidence scoring.
    *   Actionable insight extraction.
    *   SQLite-based caching.
*   End-to-end API tests implemented (mocking LLM).
*   Basic MCP registration on startup implemented.
*   Required dependencies added.

## Future Enhancements / TODO

*   Address `DeprecationWarning` for FastAPI `on_event` and `httpx` client usage.
*   Implement more sophisticated insight extraction (e.g., extracting targets).
*   Refine confidence scoring logic.
*   Consider more advanced caching strategies (e.g., semantic similarity, expiry).
*   Improve robustness of MCP registration/communication.
*   Add detailed logging configuration. 