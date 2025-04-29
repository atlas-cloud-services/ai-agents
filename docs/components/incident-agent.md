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
    *   `models.py`: Defines Pydantic models for input (`IncidentReport`), expected LLM output (`LLMStructuredResponse`), actionable steps (`ActionableInsight`), final agent output (`AnalysisResult`), and cache structure (`CacheEntry`).
    *   `analyzer.py`: Contains the core analysis logic.
        *   `_init_cache_db()`: Initializes the SQLite cache database (`incident_cache.db`).
        *   `_get_incident_summary()`: Generates an MD5 hash of the incident description for caching.
        *   `_check_cache()`: Checks the SQLite cache for existing results based on the summary hash.
        *   `_add_to_cache()`: Adds successful analysis results to the SQLite cache.
        *   `_create_llm_prompt()`: Generates a detailed prompt for the LLM Service.
        *   `_call_llm_service()`: Sends the prompt to the LLM Service API.
        *   `_parse_llm_response()`: Extracts, parses, and validates JSON from the raw LLM response.
        *   `_calculate_confidence()`: Calculates a confidence score based on parsing success and field completeness.
        *   `_extract_insights()`: Converts recommended action strings into structured `ActionableInsight` objects.
        *   `analyze_incident()`: Orchestrates the full analysis process (async function), including caching, prompt generation, LLM call, response parsing, confidence scoring, and insight extraction.
    *   `tests/test_analyzer.py`: Contains unit tests (`pytest`) for the analyzer functions, including caching logic tested against an in-memory SQLite DB.
*   **Dependencies:** `pydantic`, `httpx`, `pytest`, `freezegun`, `pytest-httpx`, `pytest-asyncio`.
*   **Data:** `incident_cache.db` (SQLite file created on first run if caching is active).

## Analysis Workflow

1.  **Receive `IncidentReport`**: Agent entry point takes incident data.
2.  **Cache Check**: Generate incident summary hash. Check SQLite cache (`_check_cache`). If hit, return cached `AnalysisResult` (updating timestamp/source).
3.  **Prompt Generation**: If cache miss, format the incident data into a structured prompt.
4.  **LLM Call**: Send the prompt to the LLM Service.
5.  **Response Parsing**: Receive the raw text response. Extract and validate JSON.
6.  **Confidence Scoring**: Evaluate the quality/reliability of the parsed response.
7.  **Insight Extraction**: Identify and structure actionable steps (`ActionableInsight`).
8.  **Caching**: If analysis was successful (not source='error'), add the `AnalysisResult` to the SQLite cache (`_add_to_cache`).
9.  **Return `AnalysisResult`**: Send back the final structured analysis (from cache or new analysis).

## How to Run/Test

*   The agent logic is currently tested via `pytest`.
*   Run tests from the project root: `pytest`
*   (Future) An API endpoint or direct invocation via the **Master Control Program (MCP)** will trigger the agent.

## Current Status (as of YYYY-MM-DD)

*   Core data models defined.
*   Prompt generation logic implemented and unit tested.
*   LLM Service call logic implemented and unit tested (using HTTP mocking).
*   Response parsing logic implemented and unit tested.
*   Confidence scoring logic implemented and unit tested.
*   Basic insight extraction logic implemented and unit tested.
*   SQLite-based caching mechanism implemented and unit tested.
*   Main analysis function includes all steps: caching, prompt gen, LLM call, parsing, scoring, insight extraction, cache update.
*   Required dependencies added. 