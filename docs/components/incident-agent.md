# Incident Analysis Agent

This agent analyzes incident reports to provide structured insights, potential causes, and recommended actions.

## Purpose

*   Automate the initial triage and analysis of incident reports.
*   Leverage LLMs to understand unstructured incident descriptions.
*   Provide structured, actionable outputs to support engineers.
*   (Future) Identify patterns by referencing historical incidents.

## Implementation Details

*   **Location:** `agents/incident/`
*   **Core Files:**
    *   `models.py`: Defines Pydantic models for input (`IncidentReport`), expected LLM output (`LLMStructuredResponse`), actionable steps (`ActionableInsight`), final agent output (`AnalysisResult`), and cache structure (`CacheEntry`).
    *   `analyzer.py`: Contains the core analysis logic.
        *   `_create_llm_prompt()`: Generates a detailed prompt for the LLM Service, requesting a specific JSON structure.
        *   `_call_llm_service()`: Sends the prompt to the LLM Service API using `httpx` and handles basic errors.
        *   `analyze_incident()`: Orchestrates the analysis process (async function), currently including prompt generation and LLM call.
        *   Placeholder functions for parsing, confidence scoring, insight extraction, and caching.
    *   `tests/test_analyzer.py`: Contains unit tests (`pytest`) for the analyzer functions (`_create_llm_prompt`, `_call_llm_service`). Uses `pytest-asyncio` for async tests and `pytest-httpx` for mocking HTTP calls.
*   **Dependencies:** `pydantic`, `httpx`, `pytest`, `freezegun`, `pytest-httpx`, `pytest-asyncio`.

## Analysis Workflow (Current & Planned)

1.  **Receive `IncidentReport`**: Agent entry point takes incident data (potentially routed from the MCP).
2.  **(TODO) Cache Check**: Look for similar incidents in a local cache.
3.  **Prompt Generation**: Format the incident data into a structured prompt using `_create_llm_prompt`.
4.  **LLM Call**: Send the prompt to the LLM Service (`/generate` endpoint) using `_call_llm_service`.
5.  **(TODO) Response Parsing**: Receive the raw text response and parse the expected JSON structure (`LLMStructuredResponse`). Handle errors gracefully.
6.  **(TODO) Confidence Scoring**: Evaluate the quality/reliability of the parsed response.
7.  **(TODO) Insight Extraction**: Identify actionable steps (`ActionableInsight`) from the recommendations.
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
*   Main analysis function calls prompt generation and LLM service.
*   Placeholders remain for parsing, scoring, insights, and caching.
*   Required dependencies added. 