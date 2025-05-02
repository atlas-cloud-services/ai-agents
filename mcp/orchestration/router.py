import asyncio
import logging
from typing import List, Dict, Any, Tuple

import httpx

from .registry import registry, AgentInfo

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Define a default timeout for agent requests
AGENT_REQUEST_TIMEOUT = 10.0  # seconds

async def send_message_to_agent(client: httpx.AsyncClient, agent: AgentInfo, message_payload: Dict[str, Any]) -> Tuple[str, Dict[str, Any]]:
    """Sends a message payload to a single agent's endpoint.

    Args:
        client: An httpx.AsyncClient instance.
        agent: The AgentInfo object for the target agent.
        message_payload: The dictionary payload to send.

    Returns:
        A tuple containing the agent ID and a dictionary representing the result.
        The result dictionary will have a 'status' ('success' or 'error')
        and either 'data' (on success) or 'error' (on failure).
    """
    target_url = f"{agent.endpoint}/process"  # Assuming agents have a /process endpoint
    logger.info(f"Sending message to agent {agent.name} ({agent.id}) at {target_url}")
    try:
        response = await client.post(
            target_url,
            json=message_payload,
            timeout=AGENT_REQUEST_TIMEOUT
        )
        response.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
        logger.info(f"Received successful response from agent {agent.name} ({agent.id}): {response.status_code}")
        # Return structured success response
        return agent.id, {"status": "success", "data": response.json()}
    except httpx.TimeoutException as exc:
        error_msg = f"Timeout contacting agent {agent.name}"
        logger.error(f"{error_msg} ({agent.id}) at {target_url}")
        # Return structured error response
        return agent.id, {"status": "error", "error": error_msg, "details": str(exc)}
    except httpx.HTTPStatusError as exc: # Catch HTTP errors specifically
        error_msg = f"HTTP error from agent {agent.name}: {exc.response.status_code}"
        logger.error(f"{error_msg} ({agent.id}): {exc}")
        # Try to include response body if available (might contain useful error info)
        try:
            error_details = exc.response.json()
        except Exception:
            error_details = exc.response.text # Fallback to raw text
        # Return structured error response
        return agent.id, {"status": "error", "error": error_msg, "details": error_details}
    except httpx.RequestError as exc:
        error_msg = f"Network error contacting agent {agent.name}"
        logger.error(f"{error_msg} ({agent.id}): {exc}")
        # Return structured error response
        return agent.id, {"status": "error", "error": error_msg, "details": str(exc)}
    except Exception as exc:
        error_msg = f"Unexpected error processing response from agent {agent.name}"
        logger.error(f"{error_msg} ({agent.id}): {exc}", exc_info=True)
        # Return structured error response
        return agent.id, {"status": "error", "error": error_msg, "details": str(exc)}


async def route_message_to_agents(capability: str, message_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Routes a message to all agents with the specified capability.

    Finds agents registered with the given capability and sends the message
    payload to each of them concurrently. Aggregates their responses.

    Args:
        capability: The required capability for processing the message.
        message_payload: The dictionary payload to send to the agents.

    Returns:
        A dictionary where keys are agent IDs and values are dictionaries
        containing the processing status ('success' or 'error') and
        either the response data or error details.
    """
    logger.info(f"Routing message requiring capability: {capability}")
    
    # Find agents with the required capability
    matching_agents = registry.get_agents_by_capability(capability)
    
    active_agents = [agent for agent in matching_agents if agent.status == "active"]
    
    if not active_agents:
        logger.warning(f"No active agents found with capability: {capability}")
        return {}

    logger.info(f"Found {len(active_agents)} active agents for capability '{capability}': {[a.name for a in active_agents]}")

    responses = {}
    async with httpx.AsyncClient() as client:
        tasks = [
            send_message_to_agent(client, agent, message_payload)
            for agent in active_agents # Use the filtered list
        ]
        
        # Execute requests concurrently and gather results
        # return_exceptions=True allows individual tasks to fail without stopping others
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        for result in results:
            if isinstance(result, Exception):
                # This catches errors *within* send_message_to_agent if something unexpected happened
                # OR errors from asyncio.gather itself.
                # Since send_message_to_agent now catches its own errors and returns a dict,
                # this branch is less likely to be hit by agent errors, but good for safety.
                logger.error(f"Error during task execution in gather: {result}", exc_info=True)
                # We don't know which agent this belongs to easily here, so we can't add it to responses dict
            elif isinstance(result, tuple) and len(result) == 2:
                agent_id, response_data = result
                if isinstance(response_data, dict): # Should always be a dict now
                    responses[agent_id] = response_data
                else:
                    # Log unexpected result format from send_message_to_agent
                    logger.error(f"Unexpected non-dict result format from send_message_to_agent task for agent {agent_id}: {response_data}")
                    responses[agent_id] = {"status": "error", "error": "Internal MCP error processing agent response", "details": str(response_data)}
            else:
                # Log unexpected result format from asyncio.gather
                logger.error(f"Unexpected result format from asyncio.gather task: {result}")

    logger.info(f"Finished routing message for capability '{capability}'. Returning {len(responses)} responses.")
    return responses 