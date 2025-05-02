import time
import json
import logging
import torch
import redis.asyncio as redis
from fastapi import APIRouter, HTTPException, Depends, Query, Request
from pydantic import BaseModel
from typing import Optional

# Assuming these are defined and accessible via Request state or dependency injection later
# from ..main import model, tokenizer, device, _generate_cache_key, logger, REDIS_LLM_TTL_SECONDS
# For now, define placeholders or access via request.app.state

logger = logging.getLogger(__name__)

# --- API Models ---
# Duplicating models here for now, ideally they'd be in a separate models.py
class GenerateRequest(BaseModel):
    prompt: str
    max_length: Optional[int] = 2048
    temperature: Optional[float] = 0.7

class GenerateResponse(BaseModel):
    text: str
    processing_time: float
    cache_status: Optional[str] = None

class StatsResponse(BaseModel):
    cache_hits: int
    cache_misses: int

router = APIRouter()

# --- Helper Functions ---
# Moved _generate_cache_key here, assuming CACHE_KEY_PREFIX is accessible or defined
# Ideally, configuration like CACHE_KEY_PREFIX should be managed centrally
CACHE_KEY_PREFIX = "llm_cache:" # Placeholder, get from config/app state ideally

def _generate_cache_key(request_data: GenerateRequest) -> str:
    """Generates a consistent cache key based on prompt and parameters."""
    import hashlib # Moved import here as it's only used in this func now
    params = {
        "prompt": request_data.prompt,
        "max_length": request_data.max_length,
        "temperature": request_data.temperature
    }
    payload_string = json.dumps(params, sort_keys=True)
    hash_object = hashlib.sha256(payload_string.encode('utf-8'))
    key = f"{CACHE_KEY_PREFIX}{hash_object.hexdigest()}"
    logger.debug(f"Generated cache key: {key} for params: {params}")
    return key


@router.get("/", summary="Get Service Status")
async def read_root(request: Request):
    """Returns the running status of the LLM Service."""
    # Access app state via request
    app_state = request.app.state
    redis_status = "connected" if hasattr(app_state, 'redis_client') and app_state.redis_client else "disconnected"
    # Access model/tokenizer status (assuming they are loaded into app state or globally accessible)
    # This might need adjustment based on how main.py manages model loading
    model_status = "loaded" if hasattr(app_state, 'model') and app_state.model and hasattr(app_state, 'tokenizer') and app_state.tokenizer else "not loaded"
    return {"status": "LLM Service is running", "model_status": model_status, "redis_status": redis_status}

@router.post("/generate",
          response_model=GenerateResponse,
          summary="Generate Text with Caching",
          description="Generates text based on a prompt using the loaded LLM. Results are cached in Redis based on prompt and parameters.")
async def generate_text(
    request: Request, # Inject Request to access app state
    gen_request: GenerateRequest, # Keep the original request model
    force_refresh: bool = Query(False, description="Set to true to bypass the cache and force regeneration.")
):
    """Generates text from a prompt, using Redis cache if available."""
    # Access shared resources via request.app.state
    app_state = request.app.state
    model = getattr(app_state, 'model', None)
    tokenizer = getattr(app_state, 'tokenizer', None)
    device = getattr(app_state, 'device', 'cpu') # Default to CPU if not found
    redis_client = getattr(app_state, 'redis_client', None)
    REDIS_LLM_TTL_SECONDS = getattr(app_state, 'REDIS_LLM_TTL_SECONDS', 24 * 60 * 60) # Default TTL

    if model is None or tokenizer is None:
        raise HTTPException(status_code=503, detail="Model not loaded or accessible")

    cache_key = _generate_cache_key(gen_request)
    cache_status = "disabled"

    # 1. Check Cache
    if redis_client and not force_refresh:
        try:
            cached_data = await redis_client.get(cache_key)
            if cached_data:
                logger.info(f"Cache HIT for key: {cache_key}")
                app_state.cache_hits = getattr(app_state, 'cache_hits', 0) + 1
                response_data = json.loads(cached_data)
                response_data["cache_status"] = "hit"
                return response_data
            else:
                logger.info(f"Cache MISS for key: {cache_key}")
                app_state.cache_misses = getattr(app_state, 'cache_misses', 0) + 1
                cache_status = "miss"
        except redis.RedisError as e:
            logger.warning(f"Redis GET error for key {cache_key}: {e}. Proceeding without cache.", exc_info=True)
            cache_status = "error"
        except json.JSONDecodeError as e:
            logger.warning(f"Error decoding cached JSON for key {cache_key}: {e}. Ignoring cache.", exc_info=True)
            app_state.cache_misses = getattr(app_state, 'cache_misses', 0) + 1
            cache_status = "miss"

    if not force_refresh and cache_status == "disabled":
        logger.warning("Redis client not available, skipping cache check.")
        app_state.cache_misses = getattr(app_state, 'cache_misses', 0) + 1

    if force_refresh:
        logger.info(f"Cache bypass requested for key: {cache_key}")
        app_state.cache_misses = getattr(app_state, 'cache_misses', 0) + 1
        cache_status = "bypass"

    start_time = time.time()

    try:
        # Create input tokens
        inputs = tokenizer(gen_request.prompt, return_tensors="pt").to(device)

        # Generate text
        with torch.no_grad():
            outputs = model.generate(
                inputs["input_ids"],
                max_length=gen_request.max_length,
                temperature=gen_request.temperature,
                do_sample=True,
                pad_token_id=tokenizer.eos_token_id
            )

        # Decode the generated text
        generated_text = tokenizer.decode(outputs[0], skip_special_tokens=True)
        response_text = generated_text[len(gen_request.prompt):].strip() if generated_text.startswith(gen_request.prompt) else generated_text.strip()

        processing_time = time.time() - start_time
        logger.info(f"LLM generation took {processing_time:.2f} seconds.")

        # Prepare response data
        response_data = {"text": response_text, "processing_time": processing_time, "cache_status": cache_status}

        # 2. Store in Cache
        if redis_client and cache_status != "error":
            try:
                cache_value = json.dumps(response_data)
                await redis_client.setex(cache_key, REDIS_LLM_TTL_SECONDS, cache_value)
                logger.info(f"Stored response in cache for key: {cache_key} with TTL: {REDIS_LLM_TTL_SECONDS}s")
            except redis.RedisError as e:
                logger.warning(f"Redis SETEX error for key {cache_key}: {e}. Response not cached.", exc_info=True)

        return response_data

    except Exception as e:
        logger.error(f"Error during LLM generation: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error during text generation: {e}")

@router.get("/stats",
         response_model=StatsResponse,
         summary="Get Cache Statistics",
         description="Returns the number of cache hits and misses since the service started.")
async def get_stats(request: Request):
    """Returns the current cache hit/miss statistics."""
    app_state = request.app.state
    return {
        "cache_hits": getattr(app_state, 'cache_hits', 0),
        "cache_misses": getattr(app_state, 'cache_misses', 0)
    } 