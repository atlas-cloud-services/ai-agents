# Use an official Python runtime as a parent image
FROM python:3.11-slim

WORKDIR /app

# Set environment variables (if any specific to MCP)
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

# Install dependencies
# Assuming mcp/requirements.txt exists or will be created
COPY mcp/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Install curl for healthcheck
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Copy the local source code to the container
COPY mcp/api/ /app/api/
COPY mcp/orchestration/ /app/orchestration/
COPY mcp/models/ /app/models/
COPY agents/ /app/agents/
# Add any other necessary files/directories

# Expose the port the app runs on
EXPOSE 8002

# Command to run the application
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8002"]
