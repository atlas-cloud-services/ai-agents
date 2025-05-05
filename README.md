# ACS-AI-AGENTS

This repository hosts the AI Agents developed for Atlas Cloud Services (ACS) GMAO project. It features a multi-agent architecture orchestrated by a Master Control Program (MCP).

## Architecture Overview

The system consists of several independent services that communicate via APIs:

1.  **LLM Service (`llm-service/`)**: Provides access to Large Language Models (LLMs) with caching capabilities.
2.  **Master Control Program (`mcp/`)**: Registers agents and routes messages between them based on capabilities.
3.  **Incident Analysis Agent (`agents/incident/`)**: Analyzes incident reports using the LLM Service, providing insights, root cause analysis, and recommended actions. It registers itself with the MCP.
4.  **Redis (`redis`)**: Used by the LLM Service for caching responses.

Each Python-based service follows a standard structure using FastAPI, with API endpoint logic separated from the main application setup:

*   `api/main.py`: FastAPI application setup, configuration loading, lifespan management (startup/shutdown events like DB init or MCP registration).
*   `api/endpoints.py`: Contains the `APIRouter` and endpoint function definitions.
*   `models.py` (or similar): Pydantic models for API requests/responses and internal data structures.
*   `requirements.txt`: Python dependencies.
*   `Dockerfile`: Container build instructions.

## Setup & Running (Docker Recommended)

The recommended way to run the services is using Docker and Docker Compose.

**Prerequisites:**

*   Docker ([Install Docker](https://docs.docker.com/get-docker/))
*   Docker Compose ([Usually included with Docker Desktop](https://docs.docker.com/compose/install/))

**Running with Docker Compose:**

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/atlas-cloud-services/ACS-AI-AGENTS.git
    cd ACS-AI-AGENTS
    ```
2.  **(Optional) Create `.env` files:** For local overrides, create `.env` files within each service directory (`llm-service`, `mcp`, `agents/incident`) based on the `.env.example` files (if provided) or the environment variables defined in the respective `Dockerfile` and `docker-compose.yml`.
3.  **Build and start the services:**
    ```bash
    docker-compose up --build -d
    ```
    *   `--build`: Forces Docker to build the images before starting.
    *   `-d`: Runs the containers in detached mode (in the background).

4.  **Accessing the Services:**
    *   **LLM Service:** `http://localhost:8001/status` (API endpoints under `/api/` e.g., `http://localhost:8001/api/generate`)
    *   **MCP:** `http://localhost:8002/status` (API endpoints under `/api/` e.g., `http://localhost:8002/api/agents`)
    *   **Incident Agent:** `http://localhost:8003/status` (API endpoints under `/api/` e.g., `http://localhost:8003/api/analyze`)
    *   Each service also provides Swagger UI docs at `/api/docs` (e.g., `http://localhost:8001/api/docs`).

5.  **Viewing Logs:**
    ```bash
    docker-compose logs -f # Stream logs from all services
    docker-compose logs -f llm-service # Stream logs for a specific service
    ```

6.  **Stopping the Services:**
    ```bash
    docker-compose down
    ```
    *   Add `-v` to remove volumes (like Redis data and incident cache) if desired: `docker-compose down -v`

## Running Services Individually (Local Development without Docker)

If you prefer to run services directly on your host machine (e.g., for easier debugging):

1.  **Clone the repository.**
2.  **Set up Python environments:** Create and activate a separate virtual environment for *each* service (`llm-service`, `mcp`, `agents/incident`).
    ```bash
    # Example for llm-service
    cd llm-service
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    cd ..
    # Repeat for mcp and agents/incident
    ```
3.  **Set Environment Variables:** Ensure required environment variables are set (e.g., `MCP_ENDPOINT`, `LLM_SERVICE_URL`, `REDIS_HOST`). You can use `.env` files (create them in each service directory) as `python-dotenv` is included.
4.  **Start Redis:** You'll need a Redis instance running locally (e.g., `redis-server` or via Docker: `docker run -d -p 6379:6379 redis:alpine`).
5.  **Run each service:** Open separate terminals for each service, activate its respective environment, and run using `uvicorn`:
    ```bash
    # Terminal 1: LLM Service
    cd llm-service
    source venv/bin/activate
    python -m uvicorn api.main:app --reload --port 8001

    # Terminal 2: MCP
    cd mcp
    source venv/bin/activate
    python -m uvicorn api.main:app --reload --port 8002

    # Terminal 3: Incident Agent
    cd agents/incident
    source venv/bin/activate
    python -m uvicorn api.main:app --reload --port 8003
    ```

## Git Branches

*   **`main`**: Production-ready code. (Will be created later)
*   **`dev`**: Development branch where features are integrated.
*   **`feature/*`**: Branches for developing new features.
*   **`hotfix/*`**: Branches for critical production bug fixes.

## Architecture Documentation

The system architecture is documented with Mermaid diagrams to provide clear visual representations of components and interactions. View the [Architecture Overview](docs/architecture.md) for more details.

Key diagrams include:
- System architecture overview
- Component interactions
- Sequence flows
- Deployment architecture
