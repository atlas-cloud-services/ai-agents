# Incident Analysis Agent

This agent analyzes incident reports to provide structured insights, potential causes, and recommended actions.

## Purpose

*   Automate the initial triage and analysis of incident reports.
*   Leverage LLMs to understand unstructured incident descriptions.
*   Provide structured, actionable outputs with confidence scores to support engineers.
*   (Future) Identify patterns by referencing historical incidents.

## Implementation Details

*   **Location:** `agents/incident/`
*   **Core Files:**
    *   `models.py`: Defines Pydantic models for input (`IncidentReport`), expected LLM output (`LLMStructuredResponse`), actionable steps (`ActionableInsight`), final agent output (`AnalysisResult`), and cache structure (`CacheEntry`).
    *   `analyzer.py`: Contains the core analysis logic.
        *   `_create_llm_prompt()`: Generates a detailed prompt for the LLM Service.
        *   `_call_llm_service()`: Sends the prompt to the LLM Service API.
        *   `_parse_llm_response()`: Extracts, parses, and validates JSON from the raw LLM response.
        *   `_calculate_confidence()`: Calculates a confidence score based on parsing success and field completeness.
        *   `_extract_insights()`: Converts recommended action strings into structured `ActionableInsight` objects with basic type classification.
        *   `analyze_incident()`: Orchestrates the analysis process (async function), including prompt generation, LLM call, response parsing, confidence scoring, and insight extraction.
        *   Placeholder functions for caching.
    *   `tests/test_analyzer.py`: Contains unit tests (`pytest`) for the analyzer functions (`_create_llm_prompt`, `_call_llm_service`, `_parse_llm_response`, `_calculate_confidence`, `_extract_insights`). Uses `pytest-asyncio` and `pytest-httpx`.
*   **Dependencies:** `pydantic`, `httpx`, `pytest`, `freezegun`, `pytest-httpx`, `pytest-asyncio`.

## Analysis Workflow (Current & Planned)

1.  **Receive `IncidentReport`**: Agent entry point takes incident data (potentially routed from the MCP).
2.  **(TODO) Cache Check**: Look for similar incidents in a local cache.
3.  **Prompt Generation**: Format the incident data into a structured prompt.
4.  **LLM Call**: Send the prompt to the LLM Service.
5.  **Response Parsing**: Receive the raw text response. Extract and validate JSON.
6.  **Confidence Scoring**: Evaluate the quality/reliability of the parsed response.
7.  **Insight Extraction**: Identify and structure actionable steps (`ActionableInsight`) from the recommendations using `_extract_insights`.
8.  **(TODO) Caching**: Store the `AnalysisResult` in the cache.
9.  **Return `AnalysisResult`**: Send back the final structured analysis (potentially to the MCP).

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
*   Main analysis function includes prompt gen, LLM call, parsing, scoring, and insight extraction.
*   Placeholder remains for caching.
*   Required dependencies added. 