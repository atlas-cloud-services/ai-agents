# Use an official Python runtime as a parent image
FROM python:3.11-slim

WORKDIR /app

# Set environment variables
ENV MCP_ENDPOINT="http://mcp:8002/api" 
ENV AGENT_ENDPOINT="http://incident-agent:8003/api" 
ENV LLM_SERVICE_URL="http://llm-service:8001/api/generate"
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Install dependencies
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Install curl for healthcheck
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Copy the local source code to the container
# Copy relevant modules needed by api/main.py and api/endpoints.py
COPY api/ /app/api/
COPY models.py /app/
COPY analyzer.py /app/
COPY __init__.py /app/
# Ensure the directory structure allows relative imports (e.g., from ..models)

# Create data directory for SQLite DB
RUN mkdir /app/data

# Expose the port the app runs on
EXPOSE 8003

# Command to run the application
# The entry point should be the main FastAPI app file
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8003"]
