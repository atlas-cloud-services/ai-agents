# ACS-AI-AGENTS

This repository hosts the AI Agents developed for Atlas Cloud Services (ACS) GMAO project.

## Current Components

### 1. LLM Service (`llm-service/`)

Provides a basic API endpoint to interact with a Large Language Model (LLM).

**Features:**

*   Loads a specified LLM (currently configured for `TinyLlama/TinyLlama-1.1B-Chat-v1.0` suitable for M1 Macs).
*   Uses `torch` with MPS backend detection for Apple Silicon.
*   Exposes a `/generate` endpoint via FastAPI.
*   Includes interactive API documentation via Swagger UI (`/docs`) and ReDoc (`/redoc`).

## Setup

1.  **Clone the repository:**
    ```bash
    git clone https://github.com/atlas-cloud-services/ACS-AI-AGENTS.git
    cd ACS-AI-AGENTS
    ```
2.  **Create and activate a virtual environment:**
    *   Ensure you have Python 3.10 or higher installed.
    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```
    *(On Windows, use `venv\Scripts\activate`)*
3.  **Install dependencies:**
    ```bash
    pip install -r requirements.txt
    ```

## Running the LLM Service

1.  **Activate the virtual environment:**
    ```bash
    source venv/bin/activate
    ```
2.  **Navigate to the service directory:**
    ```bash
    cd llm-service
    ```
3.  **Run the Uvicorn server:**
    ```bash
    python3 -m uvicorn api.main:app --reload --port 8001
    ```
4.  **Access the API:**
    *   **Root:** `http://127.0.0.1:8001/`
    *   **Swagger UI:** `http://127.0.0.1:8001/docs`
    *   **ReDoc:** `http://127.0.0.1:8001/redoc`
    *   **Generate Endpoint (POST):** `http://127.0.0.1:8001/generate`

## Git Branches

*   **`main`**: Production-ready code. (Will be created later)
*   **`dev`**: Development branch where features are integrated.
*   **`feature/*`**: Branches for developing new features.
*   **`hotfix/*`**: Branches for critical production bug fixes.
