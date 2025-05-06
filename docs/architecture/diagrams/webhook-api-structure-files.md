# Webhook API Structure and Key Files

This diagram outlines a potential project structure for implementing the webhook endpoint within the MCP, highlighting key files and their roles.

```mermaid
flowchart TD
    subgraph API["MCP API Structure"]
        direction TB
        MAIN[FastAPI App]
        ROUTER[API Router]
        
        W_ROUTER[Webhooks Router]
        GMAO_EP[GMAO Incidents Endpoint]
        
        MAIN --> ROUTER
        ROUTER --> W_ROUTER
        W_ROUTER --> GMAO_EP
        
        GMAO_EP -->|POST| HANDLER[handle_gmao_incident]
    end
    
    subgraph FILES["Key Files"]
        direction TB
        ENDPOINTS["mcp/api/endpoints.py<br>- Main API endpoints"]
        
        WEBHOOK["mcp/api/webhooks.py<br>- Webhook-specific endpoints"]
        
        MODELS["mcp/models/webhook.py<br>- Webhook payload models"]
        
        TRANSFORM["mcp/adapters/gmao.py<br>- Transformation logic"]
        
        AUTH["mcp/middleware/auth.py<br>- Authentication middleware"]
    end
    
    GMAO_EP -.-> WEBHOOK
    HANDLER -.-> MODELS
    HANDLER -.-> TRANSFORM
    HANDLER -.-> AUTH
    
    class API fill:#9df,stroke:#333
    class FILES fill:#ad9,stroke:#333
```

**Note:** This diagram suggests a possible refactoring where webhook-specific logic (`mcp/api/webhooks.py`), transformation (`mcp/adapters/gmao.py`), and authentication (`mcp/middleware/auth.py`) are moved to their own modules for better organization as the MCP grows. The current implementation places most of this logic within `mcp/api/endpoints.py`. 