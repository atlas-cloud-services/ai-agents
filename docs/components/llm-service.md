# LLM Service

This service provides a foundational API for interacting with a Large Language Model.

## Purpose

*   Abstracts the complexities of loading and running an LLM.
*   Provides a simple HTTP endpoint for text generation.
*   Configured to run efficiently on development environments (e.g., Mac M1 with MPS).

## Implementation Details

*   **Framework:** FastAPI
*   **Core Libraries:** `transformers`, `torch`
*   **Model Loading:**
    *   Uses `AutoTokenizer` and `AutoModelForCausalLM` from Hugging Face `transformers`.
    *   Detects MPS availability (`torch.backends.mps.is_available()`) for Apple Silicon, otherwise defaults to CPU.
    *   Currently configured for `TinyLlama/TinyLlama-1.1B-Chat-v1.0`.
    *   Uses `torch_dtype=torch.float16` and `low_cpu_mem_usage=True` for optimization.
*   **API Endpoints (`api/main.py`):**
    *   `GET /`: Returns a simple status message.
    *   `POST /generate`: Accepts a JSON payload (`GenerateRequest`) with `prompt`, optional `max_length`, and `temperature`. Returns a `GenerateResponse` with the generated `text` (excluding the input prompt) and `processing_time`.
*   **Documentation:** Provides automatic Swagger UI (`/docs`) and ReDoc (`/redoc`) interfaces.

## How to Run

(See [Setup Guide](../setup.md) first)

1.  Activate the virtual environment: `source venv/bin/activate`
2.  Navigate to the service directory: `cd llm-service`
3.  Run the server: `python3 -m uvicorn api.main:app --reload --port 8001`

## Current Status (as of YYYY-MM-DD)

*   Basic functionality implemented and working.
*   Tested on Mac M1.
*   No advanced features like caching, batching, or complex error handling yet. 