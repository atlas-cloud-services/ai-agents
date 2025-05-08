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
4. **GMAO Webhook Integration (within MCP):** A specific API endpoint (`/api/v1/webhooks/gmao/incidents`) within the MCP designed to receive incident data from an external GMAO system. It handles authentication, data mapping, and asynchronous forwarding of incidents to the Incident Analysis Agent.

For component-specific details, see:
- [LLM Service Details](components/llm-service.md)
- [Incident Analysis Agent Details](components/incident-agent.md)
- [Master Control Program (MCP) Details](components/mcp.md)
- [GMAO Webhook Integration Details](components/webhook-integration.md)

## Interaction Flow (Example: Incident Analysis via GMAO Webhook)

1.  An external **GMAO System** sends an incident report via a `POST` request to the `/api/v1/webhooks/gmao/incidents` endpoint on the **Master Control Program (MCP)**. The request includes an `X-GMAO-Token` for authentication.
2.  The MCP authenticates the request. If successful, it maps the incoming `GmaoWebhookPayload` to an internal `IncidentReport` format.
3.  The MCP schedules a background task (`forward_incident_to_agent`) to send this `IncidentReport` to the **Incident Analysis Agent** and immediately returns a `202 Accepted` response to the GMAO system with a `tracking_id`.
4.  The background task in the MCP attempts to `POST` the `IncidentReport` to the Incident Analysis Agent, with built-in retry logic for transient errors.
5.  The Incident Analysis Agent receives the `IncidentReport` data.
6.  It checks a local cache for similar past incidents.
7.  If no suitable cache hit, it constructs a detailed prompt based on the incident details.
8.  It sends a request containing the prompt to the `/generate` endpoint of the **LLM Service**.
9.  The LLM Service processes the prompt using the loaded language model and returns the generated text.
10. The Incident Analysis Agent receives the raw LLM response.
11. It parses the response, attempting to extract structured data (causes, actions, impact).
12. It calculates a confidence score for the analysis.
13. It extracts actionable insights from the recommendations.
14. It stores the analysis result in the cache.
15. It returns the final `AnalysisResult` object back to the MCP's background task.
16. The MCP background task logs the outcome of the forwarding attempt.

*(Diagrams could be added here later to illustrate the flow)* 