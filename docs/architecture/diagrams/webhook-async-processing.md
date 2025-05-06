# Asynchronous Processing with Background Tasks

This sequence diagram illustrates how FastAPI's background tasks can be used for asynchronous processing of webhook data after the initial acknowledgment.

```mermaid
sequenceDiagram
    title Asynchronous Processing with Background Tasks
    
    participant GMAO as GMAO System
    participant FastAPI as FastAPI Endpoint
    participant Task as Background Task
    participant IAA as Incident Analysis Agent
    
    GMAO->>+FastAPI: POST webhook payload
    
    FastAPI->>FastAPI: Validate & authenticate
    FastAPI->>FastAPI: Create background_task
    
    FastAPI-->>-GMAO: 202 Accepted (immediate response)
    
    activate Task
    Task->>Task: Transform payload
    Task->>+IAA: POST transformed data
    IAA-->>-Task: Analysis results
    Task->>Task: Store results
    deactivate Task
    
    GMAO->>FastAPI: GET status endpoint
    FastAPI-->>GMAO: Processing status / results
``` 