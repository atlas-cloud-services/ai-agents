import os
import time
import json
import hashlib
import logging
import redis.asyncio as redis
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import List, Optional

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

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
    """Manage Redis connection pool lifecycle."""
    logger.info(f"Connecting to Redis at {REDIS_HOST}:{REDIS_PORT}, DB {REDIS_DB}")
    try:
        pool = redis.ConnectionPool(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True)
        app.state.redis_client = redis.Redis(connection_pool=pool)
        # Test connection
        await app.state.redis_client.ping()
        logger.info("Successfully connected to Redis.")
        # Initialize simple cache stats
        app.state.cache_hits = 0
        app.state.cache_misses = 0
    except redis.RedisError as e:
        logger.error(f"Failed to connect to Redis: {e}", exc_info=True)
        app.state.redis_client = None # Ensure it's None if connection fails
        app.state.cache_hits = 0
        app.state.cache_misses = 0
    
    yield
    
    # Clean up Redis connection
    if app.state.redis_client:
        logger.info("Closing Redis connection...")
        await app.state.redis_client.close()
        await pool.disconnect()
        logger.info("Redis connection closed.")

app = FastAPI(title="ACS GMAO AI - LLM Service", lifespan=lifespan)

# Configure for Mac M1
device = torch.device("mps" if torch.backends.mps.is_available() else "cpu")
print(f"Using device: {device}")

# Load a small model suitable for Mac M1
MODEL_ID = "TinyLlama/TinyLlama-1.1B-Chat-v1.0"  # Small model that works on Mac M1

try:
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL_ID,
        torch_dtype=torch.float16,
        low_cpu_mem_usage=True
    ).to(device)
    print("Model loaded successfully")
except Exception as e:
    print(f"Error loading model: {e}")
    model = None
    tokenizer = None

# --- Helper Functions ---

def _generate_cache_key(request: 'GenerateRequest') -> str:
    """Generates a consistent cache key based on prompt and parameters.

    Args:
        request: The GenerateRequest object.

    Returns:
        A SHA256 hash string prefixed for the cache key.
    """
    # Include all parameters that affect the output
    params = {
        "prompt": request.prompt,
        "max_length": request.max_length,
        "temperature": request.temperature
    }
    # Sort keys for consistency and convert to JSON string
    payload_string = json.dumps(params, sort_keys=True)
    # Hash the string
    hash_object = hashlib.sha256(payload_string.encode('utf-8'))
    key = f"{CACHE_KEY_PREFIX}{hash_object.hexdigest()}"
    logger.debug(f"Generated cache key: {key} for params: {params}")
    return key

# --- API Models ---

class GenerateRequest(BaseModel):
    prompt: str
    max_length: Optional[int] = 2048
    temperature: Optional[float] = 0.7

class GenerateResponse(BaseModel):
    text: str
    processing_time: float
    cache_status: Optional[str] = None # Add cache status to response

class StatsResponse(BaseModel):
    cache_hits: int
    cache_misses: int

@app.get("/", summary="Get Service Status")
def read_root():
    """Returns the running status of the LLM Service."""
    redis_status = "connected" if hasattr(app.state, 'redis_client') and app.state.redis_client else "disconnected"
    model_status = "loaded" if model and tokenizer else "not loaded"
    return {"status": "LLM Service is running", "model_status": model_status, "redis_status": redis_status}

@app.post("/generate", 
          response_model=GenerateResponse,
          summary="Generate Text with Caching",
          description="Generates text based on a prompt using the loaded LLM. Results are cached in Redis based on prompt and parameters.")
async def generate_text(
    request: GenerateRequest,
    force_refresh: bool = Query(False, description="Set to true to bypass the cache and force regeneration.")
):
    """Generates text from a prompt, using Redis cache if available.
    
    Args:
        request: The generation request details.
        force_refresh: If true, ignores any cached result.
    
    Returns:
        The generated text, processing time, and cache status.
    """
    if model is None or tokenizer is None:
        raise HTTPException(status_code=503, detail="Model not loaded")
    
    redis_client = app.state.redis_client if hasattr(app.state, 'redis_client') else None
    cache_key = _generate_cache_key(request)
    cache_status = "disabled" # Default if Redis is not available
    
    # 1. Check Cache (if enabled and not force_refresh)
    if redis_client and not force_refresh:
        try:
            cached_data = await redis_client.get(cache_key)
            if cached_data:
                logger.info(f"Cache HIT for key: {cache_key}")
                app.state.cache_hits += 1
                # Deserialize cached JSON string
                response_data = json.loads(cached_data)
                response_data["cache_status"] = "hit"
                return response_data
            else:
                logger.info(f"Cache MISS for key: {cache_key}")
                app.state.cache_misses += 1
                cache_status = "miss" # Will be generated and cached now
        except redis.RedisError as e:
            logger.warning(f"Redis GET error for key {cache_key}: {e}. Proceeding without cache.", exc_info=True)
            cache_status = "error"
        except json.JSONDecodeError as e:
            logger.warning(f"Error decoding cached JSON for key {cache_key}: {e}. Ignoring cache.", exc_info=True)
            app.state.cache_misses += 1 # Treat as miss if cache data is corrupted
            cache_status = "miss"

    # If cache miss, force_refresh, or Redis error, generate text
    if not force_refresh and cache_status == "disabled":
        logger.warning("Redis client not available, skipping cache check.")
        app.state.cache_misses += 1 # Count as miss if Redis isn't working

    if force_refresh:
        logger.info(f"Cache bypass requested for key: {cache_key}")
        app.state.cache_misses += 1 # Force refresh counts as a miss for stats
        cache_status = "bypass"

    start_time = time.time()
    
    try:
    # Create input tokens
    inputs = tokenizer(request.prompt, return_tensors="pt").to(device)
    
    # Generate text
    with torch.no_grad():
        outputs = model.generate(
            inputs["input_ids"],
            max_length=request.max_length,
            temperature=request.temperature,
            do_sample=True,
                pad_token_id=tokenizer.eos_token_id # Suppress warning for padding
        )
    
    # Decode the generated text
    generated_text = tokenizer.decode(outputs[0], skip_special_tokens=True)
    
        # Remove the prompt from the generated text (simple approach)
        response_text = generated_text[len(request.prompt):].strip() if generated_text.startswith(request.prompt) else generated_text.strip()
    
    processing_time = time.time() - start_time
        logger.info(f"LLM generation took {processing_time:.2f} seconds.")

        # Prepare response data
        response_data = {"text": response_text, "processing_time": processing_time, "cache_status": cache_status}

        # 2. Store in Cache (if Redis is available)
        if redis_client and cache_status != "error": # Don't cache if there was a Redis GET error
            try:
                # Serialize the response dictionary to JSON for caching
                cache_value = json.dumps(response_data)
                await redis_client.setex(cache_key, REDIS_LLM_TTL_SECONDS, cache_value)
                logger.info(f"Stored response in cache for key: {cache_key} with TTL: {REDIS_LLM_TTL_SECONDS}s")
            except redis.RedisError as e:
                logger.warning(f"Redis SETEX error for key {cache_key}: {e}. Response not cached.", exc_info=True)
        
        return response_data

    except Exception as e:
        logger.error(f"Error during LLM generation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error during text generation: {e}")

@app.get("/stats", 
         response_model=StatsResponse,
         summary="Get Cache Statistics",
         description="Returns the number of cache hits and misses since the service started.")
async def get_stats():
    """Returns the current cache hit/miss statistics."""
    return {
        "cache_hits": app.state.cache_hits if hasattr(app.state, 'cache_hits') else 0,
        "cache_misses": app.state.cache_misses if hasattr(app.state, 'cache_misses') else 0
    }

# Allow running with uvicorn for local testing (optional)
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run(app, host="0.0.0.0", port=8001)