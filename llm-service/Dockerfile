# Stage 1: Download Model
FROM python:3.11-slim as model_downloader

# Install necessary libraries for downloading
RUN pip install --no-cache-dir transformers torch

# Set environment variable to specify cache directory inside the image
ENV TRANSFORMERS_CACHE=/app/models
ENV HUGGINGFACE_HUB_CACHE=/app/models

# Define model ID as an argument or variable
ARG MODEL_ID="TinyLlama/TinyLlama-1.1B-Chat-v1.0"

# Create cache directory and download the model
RUN mkdir -p /app/models && \
    python -c "from transformers import AutoModelForCausalLM, AutoTokenizer; AutoTokenizer.from_pretrained('$MODEL_ID', cache_dir='/app/models'); AutoModelForCausalLM.from_pretrained('$MODEL_ID', cache_dir='/app/models')"

# Stage 2: Build Application Image
FROM python:3.11-slim

WORKDIR /app

# Set environment variables for Redis and caching
ENV REDIS_HOST="redis"
ENV REDIS_PORT=6379
ENV REDIS_DB=0
ENV REDIS_LLM_TTL_SECONDS=86400 
ENV PYTHONUNBUFFERED=1

# Set Transformers cache directory (where the model will be copied to)
ENV TRANSFORMERS_CACHE=/app/models
ENV HUGGINGFACE_HUB_CACHE=/app/models

# Install runtime dependencies
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Install curl for healthcheck
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Copy the application code
COPY api/ /app/api/

# Copy the downloaded model from the first stage
COPY --from=model_downloader /app/models /app/models

# Expose the port the app runs on
EXPOSE 8001

# Command to run the application using uvicorn
# Note: The host is 0.0.0.0 to accept connections from outside the container
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8001"] 