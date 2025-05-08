# MCP (Master Control Program)

This service acts as the central orchestrator for the AI-AGENTS system.

## Features

- Agent Registration and Discovery
- Message Routing based on Capabilities
- GMAO Incident Webhook Integration (see detailed documentation [here](../../docs/components/webhook-integration.md))

## GMAO Incident Webhook Endpoint

The MCP exposes a webhook endpoint to receive incident data from an external GMAO (Gestion de Maintenance Assistée par Ordinateur) system.

- **URL Path:** `/api/v1/webhooks/gmao/incidents`
- **HTTP Method:** `POST`
- **Authentication:** API Key
  - Requires an `X-GMAO-Token` header containing the pre-configured API key.

- **Expected Payload Format:**
  The endpoint expects a JSON payload matching the structure of the `GmaoWebhookPayload` Pydantic model (defined in `mcp.models.webhook`). Key fields include:
  ```json
  {
    "external_incident_id": "string (GMAO's incident ID)",
    "title": "string",
    "description": "string",
    "status": "string (e.g., OPEN, IN_PROGRESS)",
    "priority": "string (e.g., LOW, MEDIUM, HIGH)",
    "incident_created_at": "datetime (ISO 8601 format, e.g., 2023-10-27T10:00:00Z)",
    "image_url": "string (optional)",
    "affected_services": "array of strings (optional)",
    "reported_by_gmao_user_id": "string (optional)",
    "gmao_link": "string (optional)",
    "additional_data": "object (optional, key-value pairs)"
  }
  ```
  (Refer to `mcp/models/webhook.py` for the full `GmaoWebhookPayload` model definition and example.)

- **Response Codes & Format:**
  - **`202 ACCEPTED`**: Successfully received and queued for processing.
    Response Body (`WebhookResponse` model):
    ```json
    {
      "status": "success",
      "message": "Incident received and queued for processing.",
      "tracking_id": "string (e.g., mcp-wh-uuid)"
    }
    ```
  - **`401 UNAUTHORIZED`**: Missing or incorrect `X-GMAO-Token` header.
  - **`403 FORBIDDEN`**: Invalid API Key in `X-GMAO-Token`.
  - **`422 UNPROCESSABLE ENTITY`**: Payload validation error (doesn't match `GmaoWebhookPayload`) or critical error during initial mapping.
  - **`500 INTERNAL SERVER ERROR`**: Unexpected server error during webhook processing (less common for the initial synchronous part).

- **Required Environment Variables for MCP:**
  - `GMAO_WEBHOOK_API_KEY`: The secret API key that the GMAO system must send in the `X-GMAO-Token` header.
  - `INCIDENT_AGENT_URL`: The full URL (including `/api/analyze`) where the mapped incident data should be POSTed to the Incident Analysis Agent (e.g., `http://incident-agent:8003/api/analyze`).
  - `MCP_PORT` (Optional, if you want to configure the port MCP listens on, otherwise defaults based on your `Dockerfile` or `uvicorn` command).

For details on the implementation, including data transformation, asynchronous processing, and the retry mechanism for agent communication, refer to `mcp/api/endpoints.py` (`receive_gmao_incident` function and helpers) and the comprehensive [GMAO Webhook Integration documentation](../../docs/components/webhook-integration.md). 