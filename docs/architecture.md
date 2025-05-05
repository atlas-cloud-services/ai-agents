# Architecture Overview

This document describes the high-level architecture of the ACS-AI-AGENTS system.

## Diagrams

The following architectural diagrams provide visual representations of different aspects of the system:

1. [System Architecture](architecture/diagrams/system-architecture.md) - High-level overview of the system components
2. [Incident Analysis Sequence](architecture/diagrams/incident-sequence.md) - Flow of an incident analysis request
3. [Incident Agent Components](architecture/diagrams/incident-agent-components.md) - Internal structure of the Incident Analysis Agent
4. [MCP Architecture](architecture/diagrams/mcp-architecture.md) - Master Control Program components
5. [Docker Deployment](architecture/diagrams/docker-deployment.md) - Container deployment architecture
6. [Incident Agent Class Diagram](architecture/diagrams/incident-agent-class-diagram.md) - Class structure of the Incident Analysis Agent
7. [System Integration](architecture/diagrams/system-integration.md) - Integration with external systems

## Components

The system currently consists of the following main components:

1. **LLM Service:** A standalone FastAPI service responsible for loading and exposing a foundational Large Language Model via an API.
2. **Incident Analysis Agent:** An agent designed to receive incident reports, interact with the LLM Service for analysis, process the results, and provide structured insights.
3. **Master Control Program (MCP):** The central orchestration component that acts as a router, manages agent registration and discovery, and coordinates communication between agents.

For component-specific details, see:
- [LLM Service Details](components/llm-service.md)
- [Incident Analysis Agent Details](components/incident-agent.md)
- [Master Control Program (MCP) Details](components/mcp.md)

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