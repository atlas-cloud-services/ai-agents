# Master Control Program (MCP) Documentation

## Overview

The Master Control Program (MCP) serves as the central orchestrator for the ACS-GMAO AI Agents system. Its primary responsibilities include:

- **Agent Registration & Discovery:** Maintaining a registry of active AI agents and their capabilities.
- **Message Routing:** Receiving messages and routing them to the appropriate agent(s) based on the required capabilities.
- **Orchestration:** Coordinating tasks that might involve multiple agents.

## Architecture

The MCP is a FastAPI application located in the `mcp/` directory. Key modules include:

- `mcp/api/main.py`: Defines the FastAPI application and its API endpoints.
- `mcp/orchestration/registry.py`: Manages the registration and status of known agents.
- `mcp/orchestration/router.py`: Contains the logic for routing messages to registered agents based on capabilities.
- `mcp/models/`: Contains Pydantic models for agents and messages.

## API Endpoints

The MCP exposes the following RESTful API endpoints (base path typically `/mcp` if deployed behind a gateway, or root `/` if run standalone):

### `GET /`
- **Summary:** Get MCP Status
- **Description:** Returns the current status and version of the MCP.
- **Response:** `{"status": "MCP is running", "version": "0.2.0"}`

### `POST /agents/register`
- **Summary:** Register a New Agent
- **Description:** Registers a new AI agent with the MCP, providing its metadata and capabilities.
- **Request Body:** `RegisterAgentRequest` model (name, description, endpoint, capabilities).
- **Response:** `RegisterAgentResponse` model (agent_id, status).

### `GET /agents`
- **Summary:** List All Registered Agents
- **Description:** Retrieves a list of all agents currently registered with the MCP.
- **Response:** List of `AgentInfo` models.

### `GET /agents/{agent_id}`
- **Summary:** Get Agent Details
- **Description:** Retrieves detailed information about a specific agent by its ID.
- **Response:** `AgentInfo` model.
- **Errors:** 404 if agent not found.

### `PUT /agents/{agent_id}/heartbeat`
- **Summary:** Agent Heartbeat
- **Description:** Allows agents to report their status, updating their `last_heartbeat` time and potentially reactivating them if marked inactive.
- **Request Body:** `HeartbeatRequest` model (optional status).
- **Response:** 204 No Content on success.
- **Errors:** 404 if agent not found.

### `POST /message`
- **Summary:** Route Message to Agents
- **Description:** Receives a message and routes it to all *active* registered agents matching the specified `target_capability`.
- **Request Body:** `MessageRequest` model:
    - `content`: (dict) The actual message payload to be processed.
    - `target_capability`: (string, **required**) The capability required for processing this message.
    - `source_agent_id`: (string, optional) ID of the agent sending the message.
    - `metadata`: (dict, optional) Any additional metadata.
- **Routing Logic:** 
    1. The endpoint receives the `MessageRequest`.
    2. It calls the `route_message_to_agents` function from `mcp/orchestration/router.py`.
    3. The router uses the `registry` to find all registered agents possessing the `target_capability`.
    4. It filters these agents to include only those with `status="active"`.
    5. It asynchronously sends the message payload (`content`, `metadata`, `source_agent_id`) via HTTP POST to the `/process` endpoint of each active, matching agent using `httpx`.
    6. It collects the responses from each agent.
    7. Responses are structured with a `status` ('success' or 'error') and either `data` (the agent's JSON response) or `error`/`details` (if an error occurred during communication or processing).
- **Response:** `MessageResponse` model:
    - `message_id`: (string) Unique ID for this processing request.
    - `status`: (string) Overall status ("processed").
    - `responses`: (list) A list of `AgentResponseData` objects, one for each agent contacted:
        - `agent_id`: (string) ID of the responding agent.
        - `status_code`: (int, optional) HTTP status code from the agent (if available and successful).
        - `response_body`: (any, optional) The actual JSON data returned by the agent on success.
        - `error`: (string, optional) An error message if contacting or processing for this agent failed.
- **Errors:**
    - 422: If `target_capability` is missing in the request.
    - 503: If a fundamental error occurs during the routing process itself.

## Message Routing Implementation (`router.py`)

The `mcp/orchestration/router.py` module contains:

- `route_message_to_agents(capability, message_payload)`: The main asynchronous function that looks up agents via the registry and orchestrates concurrent message sending.
- `send_message_to_agent(client, agent, message_payload)`: An asynchronous helper function that sends the payload to a single agent using `httpx`, handles timeouts and HTTP errors, and returns a structured success/error dictionary.

This allows the MCP to efficiently broadcast messages to relevant agents and gather their responses for further processing or aggregation. 