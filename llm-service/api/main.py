import os
import time
import json
import logging
import redis.asyncio as redis
from contextlib import asynccontextmanager
from dotenv import load_dotenv # Import load_dotenv

from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

# Import the router
from .endpoints import router as api_router 

# Load environment variables from .env file
load_dotenv()

# --- Logging Setup ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Configuration ---
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
# Default TTL set to 24 hours (in seconds), configurable via env var
REDIS_LLM_TTL_SECONDS = int(os.getenv("REDIS_LLM_TTL_SECONDS", 24 * 60 * 60))
CACHE_KEY_PREFIX = "llm_cache:"

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage Redis connection pool and model loading/unloading lifecycle."""
    logger.info(f"Connecting to Redis at {REDIS_HOST}:{REDIS_PORT}, DB {REDIS_DB}")
    try:
        pool = redis.ConnectionPool(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
        app.state.redis_client = redis.Redis(connection_pool=pool)
        await app.state.redis_client.ping()
        logger.info("Successfully connected to Redis.")
        app.state.cache_hits = 0
        app.state.cache_misses = 0
        app.state.REDIS_LLM_TTL_SECONDS = REDIS_LLM_TTL_SECONDS # Pass TTL to state
    except redis.RedisError as e:
        logger.error(f"Failed to connect to Redis: {e}", exc_info=True)
        app.state.redis_client = None
        app.state.cache_hits = 0
        app.state.cache_misses = 0
        app.state.REDIS_LLM_TTL_SECONDS = REDIS_LLM_TTL_SECONDS # Still set default TTL maybe?
    
    # Load Model and Tokenizer, store in app.state
    logger.info("Loading model and tokenizer...")
    try:
        app.state.device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
        logger.info(f"Using device: {app.state.device}")
        MODEL_ID = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"
        app.state.tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
        app.state.model = AutoModelForCausalLM.from_pretrained(
            MODEL_ID,
            torch_dtype=torch.float16,
            low_cpu_mem_usage=True
        ).to(app.state.device)
        logger.info("Model and tokenizer loaded successfully and stored in app state.")
    except Exception as e:
        logger.error(f"Error loading model: {e}", exc_info=True)
        app.state.model = None
        app.state.tokenizer = None
        app.state.device = 'cpu'

    yield
    
    # Clean up Redis connection
    if hasattr(app.state, 'redis_client') and app.state.redis_client:
        logger.info("Closing Redis connection...")
        await app.state.redis_client.close()
        # Assuming pool was stored if redis_client was created
        if 'pool' in locals(): 
             await pool.disconnect()
        logger.info("Redis connection closed.")
    # Optional: Clean up model/tokenizer from memory if needed
    logger.info("Shutting down application.")

app = FastAPI(title="ACS GMAO AI - LLM Service", lifespan=lifespan)

# Remove model loading from global scope - moved to lifespan

# Remove Helper Functions - moved to endpoints

# Remove API Models - moved/duplicated in endpoints (consider centralizing later)

# Include the API router
app.include_router(api_router, prefix="/api") # Add a prefix for clarity

# Keep the root endpoint here for basic health check?
@app.get("/status", summary="Get Service Root Status")
def read_root_status():
    # Basic check, more detailed status is now in /api/
    return {"status": "LLM Service is running. Check /api/ for details."}


# Remove endpoint definitions - moved to endpoints.py

# Allow running with uvicorn for local testing (optional)
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run("main:app", host="0.0.0.0", port=8001, reload=True) # Ensure reload points to main:app