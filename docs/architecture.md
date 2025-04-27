# Architecture Overview

This document describes the high-level architecture of the ACS-AI-AGENTS system.

## Components

The system currently consists of the following main components:

1.  **LLM Service:** A standalone FastAPI service responsible for loading and exposing a foundational Large Language Model via an API. It handles model loading (optimized for target hardware like M1 Macs) and text generation requests.
    *   See [LLM Service Details](components/llm-service.md)
2.  **Incident Analysis Agent:** An agent designed to receive incident reports, interact with the LLM Service for analysis, process the results, and provide structured insights.
    *   See [Incident Analysis Agent Details](components/incident-agent.md)
3.  **Master Control Program (MCP):** (Planned) The central orchestration component. It will act as a central router, manage agent registration and discovery, receive incoming requests (e.g., new incidents), identify the appropriate agent(s) to handle them based on capabilities, route the requests, and potentially aggregate responses.
    *   See [Master Control Program (MCP) Details](components/mcp.md)

## Interaction Flow (Example: Incident Analysis)

1.  An external system (e.g., monitoring tool, ticketing system) sends an incident report to the **Master Control Program (MCP)** (once implemented).
2.  The MCP identifies the Incident Analysis Agent as capable of handling the report and routes the `IncidentReport` data to it.
3.  *Currently:* The Incident Analysis Agent is invoked directly.
4.  The Incident Analysis Agent receives the `IncidentReport` data.
5.  It checks a local cache for similar past incidents.
6.  If no suitable cache hit, it constructs a detailed prompt based on the incident details.
7.  It sends a request containing the prompt to the `/generate` endpoint of the **LLM Service**.
8.  The LLM Service processes the prompt using the loaded language model and returns the generated text.
9.  The Incident Analysis Agent receives the raw LLM response.
10. It parses the response, attempting to extract structured data (causes, actions, impact).
11. It calculates a confidence score for the analysis.
12. It extracts actionable insights from the recommendations.
13. It stores the analysis result in the cache.
14. It returns the final `AnalysisResult` object (potentially back to the MCP or the original caller).

*(Diagrams could be added here later to illustrate the flow)* 