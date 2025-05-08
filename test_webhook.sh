#!/bin/bash

# Basic script to test the GMAO webhook endpoint on the MCP.

MCP_HOST="localhost"
MCP_PORT="8002" # Port where MCP is exposed from docker-compose.yml
WEBHOOK_URL="http://${MCP_HOST}:${MCP_PORT}/api/v1/webhooks/gmao/incidents"

# IMPORTANT: Replace with your actual API key or load from .env
# For local testing, you can source your .env file if it exports the variable,
# or manually set it here.
API_KEY="your_gmao_webhook_api_key_here" # Replace this placeholder

PAYLOAD_FILE="test_payload.json"

if [ ! -f "$PAYLOAD_FILE" ]; then
    echo "Error: Payload file ($PAYLOAD_FILE) not found."
    echo "Please create it with a valid JSON payload based on GmaoWebhookPayload model."
    exit 1
fi

if [ "$API_KEY" == "your_gmao_webhook_api_key_here" ]; then
    echo "Warning: API_KEY is set to the placeholder value."
    echo "Please edit this script and replace it with your actual GMAO_WEBHOOK_API_KEY."
    # Optionally, try to source from .env if it exists
    if [ -f .env ]; then
        echo "Attempting to source API key from .env file..."
        set -a # automatically export all variables
        source .env
        set +a
        API_KEY=$GMAO_WEBHOOK_API_KEY
        if [ "$API_KEY" == "your_gmao_webhook_api_key_here" ] || [ -z "$API_KEY" ]; then 
             echo "Failed to load API_KEY from .env or it was still the placeholder. Exiting."
             exit 1
        else 
            echo "Successfully loaded API_KEY from .env"
        fi 
    else 
        echo "No .env file found to source API_KEY from. Exiting."
        exit 1
    fi
fi

echo "Sending test payload to: $WEBHOOK_URL"
echo "Using API Key (first 5 chars): ${API_KEY:0:5}..."

curl -X POST \
  "$WEBHOOK_URL" \
  -H "Content-Type: application/json" \
  -H "X-GMAO-Token: $API_KEY" \
  -d @"$PAYLOAD_FILE" \
  --verbose

echo "\nDone." 