import datetime
import logging
from typing import Dict, Any, Optional
import json
import httpx # Added for making HTTP requests
import re # Added for regular expression matching

from .models import IncidentReport, AnalysisResult, LLMStructuredResponse, ActionableInsight

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configuration for the LLM Service
LLM_SERVICE_URL = "http://127.0.0.1:8001/generate"
LLM_REQUEST_TIMEOUT = 60.0 # Timeout in seconds for the LLM call

PROMPT_TEMPLATE = """
Analyze the following incident report and provide a structured JSON response.

Incident Details:
ID: {incident_id}
Timestamp: {timestamp}
Priority: {priority}
Affected Systems: {affected_systems}
Reporter: {reporter}
Description:
```
{description}
```

Required JSON Output Format:
```json
{{
  "potential_root_causes": [
    "Cause 1 description...",
    "Cause 2 description..."
  ],
  "recommended_actions": [
    "Action 1 description...",
    "Action 2 description..."
  ],
  "potential_impact": "Description of potential impact...",
  "confidence_explanation": "Explanation of why the analysis is confident/uncertain..."
}}
```

Instructions for Analysis:
1. Identify the most likely root causes based *only* on the provided description.
2. Suggest concrete, actionable steps to investigate and resolve the issue.
3. Briefly describe the potential impact if the incident is not addressed.
4. Explain the reasoning behind your confidence in this analysis. Be specific about ambiguities or assumptions.
5. Ensure the output strictly adheres to the JSON format specified above. Do not include any text outside the JSON structure.

JSON Response:
```json
"""

def _create_llm_prompt(incident: IncidentReport) -> str:
    """Creates a structured prompt for the LLM based on the incident report.

    Args:
        incident: The incident report data.

    Returns:
        A formatted string containing the prompt for the LLM.
    """
    logger.info(f"Creating LLM prompt for incident ID: {incident.incident_id}")
    prompt = PROMPT_TEMPLATE.format(
        incident_id=incident.incident_id,
        timestamp=incident.timestamp.isoformat(),
        priority=incident.priority if incident.priority is not None else "Not specified",
        affected_systems=", ".join(incident.affected_systems) if incident.affected_systems else "Not specified",
        reporter=incident.reporter if incident.reporter else "Not specified",
        description=incident.description
    )
    return prompt

async def _call_llm_service(prompt: str) -> Optional[str]:
    """Calls the external LLM service to get an analysis for the prompt.

    Args:
        prompt: The formatted prompt string to send to the LLM.

    Returns:
        The raw text response from the LLM service, or None if an error occurs.
    """
    logger.info("Calling LLM service...")
    payload = {"prompt": prompt}
    try:
        async with httpx.AsyncClient(timeout=LLM_REQUEST_TIMEOUT) as client:
            response = await client.post(LLM_SERVICE_URL, json=payload)

            # Raise an exception for bad status codes (4xx or 5xx)
            response.raise_for_status()

            # Parse the JSON response from the LLM service
            response_data = response.json()
            llm_text = response_data.get("text")
            if llm_text:
                logger.info("Successfully received response from LLM service.")
                logger.debug(f"LLM Raw Response: {llm_text[:200]}...") # Log beginning of response
                return llm_text
            else:
                logger.error("LLM service response did not contain 'text' field.")
                return None

    except httpx.RequestError as e:
        # Handles connection errors, timeouts, etc.
        logger.error(f"Error calling LLM service: {e.__class__.__name__} - {e}", exc_info=True)
        return None
    except httpx.HTTPStatusError as e:
        # Handles non-2xx status codes
        logger.error(f"LLM service returned error status {e.response.status_code}: {e.response.text}", exc_info=True)
        return None
    except Exception as e:
        # Catch any other unexpected errors during the call or parsing response.json()
        logger.error(f"Unexpected error during LLM service call: {e}", exc_info=True)
        return None

async def analyze_incident(incident: IncidentReport) -> AnalysisResult:
    """Analyzes an incident report using an LLM.

    Orchestrates prompt creation, LLM call, and (soon) response processing.

    Args:
        incident: The incident report data.

    Returns:
        An AnalysisResult object containing the analysis details or errors.
    """
    start_time = datetime.datetime.now()
    logger.info(f"Starting analysis for incident ID: {incident.incident_id}")

    analysis_result = AnalysisResult(
        incident_id=incident.incident_id,
        analysis_source="pending",
        errors=[]
    )

    # --- TODO: Step 5: Implement Historical Cache Check --- 
    # Check cache first
    # cached_result = _check_cache(incident)
    # if cached_result:
    #     logger.info(f"Found cached result for incident ID: {incident.incident_id}")
    #     cached_result.analysis_timestamp = datetime.datetime.now()
    #     cached_result.analysis_source = "cache"
    #     return cached_result

    # --- Step 2: Generate Prompt ---
    try:
        prompt = _create_llm_prompt(incident)
        logger.debug(f"Generated prompt:\n{prompt[:300]}...") # Log beginning of prompt
    except Exception as e:
        error_msg = f"Error creating LLM prompt: {e}"
        logger.error(error_msg, exc_info=True)
        analysis_result.errors.append(error_msg)
        analysis_result.analysis_source = "error"
        analysis_result.processing_time_seconds = (datetime.datetime.now() - start_time).total_seconds()
        return analysis_result # Return early on prompt error

    # --- Step 3: Call LLM Service --- 
    llm_raw_response = await _call_llm_service(prompt)
    
    if llm_raw_response is None:
        # Error occurred during the LLM call, details already logged by _call_llm_service
        error_msg = "Failed to get response from LLM service."
        analysis_result.errors.append(error_msg)
        analysis_result.analysis_source = "error"
        analysis_result.processing_time_seconds = (datetime.datetime.now() - start_time).total_seconds()
        return analysis_result # Return early on LLM call error

    # Store the raw response if successful
    analysis_result.llm_raw_response = llm_raw_response

    # --- Step 4: Parse LLM Response --- 
    parsed_data = _parse_llm_response(llm_raw_response, analysis_result.errors)
    
    if parsed_data:
        analysis_result.parsed_response = parsed_data
        # We tentatively set source to 'llm' if the call succeeded,
        # parsing success confirms it.
        analysis_result.analysis_source = "llm"
    else:
        # Error details were already added to analysis_result.errors by _parse_llm_response
        analysis_result.analysis_source = "error"
        # We might still want to proceed to calculate a low confidence score even if parsing fails

    # --- TODO: Step 5: Calculate Confidence Score --- 
    # analysis_result.confidence_score = _calculate_confidence(analysis_result.parsed_response, llm_raw_response)

    # --- TODO: Step 6: Extract Actionable Insights --- 
    # if analysis_result.parsed_response:
    #     analysis_result.actionable_insights = _extract_insights(analysis_result.parsed_response, incident.incident_id)

    # --- TODO: Step 7: Add to Cache ---
    # if analysis_result.analysis_source != "error": # Don't cache errors
    #    _add_to_cache(incident, analysis_result)

    # --- Finalize ---
    # Analysis source is now set based on parsing success/failure
    end_time = datetime.datetime.now()
    analysis_result.processing_time_seconds = (end_time - start_time).total_seconds()
    if analysis_result.analysis_source != "error":
        logger.info(f"Analysis complete for incident ID: {incident.incident_id} in {analysis_result.processing_time_seconds:.2f}s")
    else:
         logger.warning(f"Analysis for incident ID: {incident.incident_id} completed with errors in {analysis_result.processing_time_seconds:.2f}s")

    return analysis_result

# --- Placeholder/TODO functions --- 

def _parse_llm_response(response: str, errors_list: list) -> Optional[LLMStructuredResponse]:
    """Parses the raw LLM response string to extract the structured JSON data.

    Attempts to find a JSON object within the response, parse it, and
    validate it against the LLMStructuredResponse model.
    Handles JSON potentially wrapped in markdown code fences.

    Args:
        response: The raw text response from the LLM service.
        errors_list: A list to append error messages to if parsing fails.

    Returns:
        An LLMStructuredResponse object if parsing and validation are successful,
        otherwise None.
    """
    logger.info("Attempting to parse LLM response...")
    if not response:
        error_msg = "LLM response was empty."
        logger.warning(error_msg)
        errors_list.append(error_msg)
        return None

    json_str = None
    try:
        # Priority 1: Look for ```json ... ``` block
        json_markdown_match = re.search(r'```json\s*(\{.*?\})\s*```', response, re.DOTALL | re.IGNORECASE)
        if json_markdown_match:
            json_str = json_markdown_match.group(1) # Extract content within the braces
            logger.debug("Extracted JSON from markdown block.")
        else:
            # Priority 2: Look for the first { ... } block (non-greedy)
            # This is less reliable if multiple JSON objects exist in the response
            first_json_match = re.search(r'(\{.*?\})', response, re.DOTALL)
            if first_json_match:
                json_str = first_json_match.group(1)
                logger.debug("Extracted first JSON block found (non-greedy).")

        if json_str:
            logger.debug(f"Extracted JSON string: {json_str[:200]}...")
            
            # Parse the extracted JSON string
            data = json.loads(json_str)
            
            # Validate the parsed data against the Pydantic model
            parsed_obj = LLMStructuredResponse(**data)
            logger.info("Successfully parsed and validated LLM response.")
            return parsed_obj
        else:
            error_msg = "Could not find JSON object structure in LLM response."
            logger.warning(f"{error_msg} Raw response: {response[:500]}...")
            errors_list.append(error_msg)
            return None
            
    except json.JSONDecodeError as e:
        error_msg = f"Failed to decode extracted JSON string [len={len(json_str) if json_str else 0}]: {e}"
        logger.error(f"{error_msg} - Extracted string: {json_str[:500]}...", exc_info=True)
        errors_list.append(error_msg)
        return None
    except Exception as e:
        # Catches Pydantic's ValidationError and other unexpected errors
        error_msg = f"Error validating parsed LLM response data: {e}"
        logger.error(error_msg, exc_info=True)
        errors_list.append(error_msg)
        return None

# def _calculate_confidence(parsed_data: Optional[LLMStructuredResponse], raw_response: str) -> Optional[float]:
#     # Implementation to calculate confidence score (0.0 - 1.0)
#     # Factors: was parsing successful? fields populated? keywords? response length?
#     logger.info("Calculating confidence score...")
#     if parsed_data is None:
#         return 0.1 # Low confidence if parsing failed
    
#     score = 0.5 # Base score
#     if parsed_data.potential_root_causes: score += 0.1
#     if parsed_data.recommended_actions: score += 0.1
#     if parsed_data.potential_impact: score += 0.1
#     if parsed_data.confidence_explanation: score += 0.1
    
#     # Add more sophisticated checks (e.g., keyword analysis, length, check explanation)
    
#     return min(score, 1.0) # Cap at 1.0

# def _extract_insights(parsed_data: LLMStructuredResponse) -> List[ActionableInsight]:
#     # Implementation to identify actionable steps from recommended_actions
#     logger.info("Extracting actionable insights...")
#     insights = []
#     if not parsed_data or not parsed_data.recommended_actions:
#         return []
        
#     for i, action in enumerate(parsed_data.recommended_actions):
#         # Basic example: Treat every recommended action as an insight
#         # More sophisticated logic could involve pattern matching (e.g., "Check logs on server X", "Update KB article Y")
#         insight_type = "investigate" # Default type
#         target = None
#         # Example pattern matching (very basic)
#         action_lower = action.lower()
#         if "check logs" in action_lower or "review logs" in action_lower:
#             insight_type = "investigate"
#             # Try to extract target (e.g., server name)
#         elif "update" in action_lower and ("kb" in action_lower or "doc" in action_lower):
#             insight_type = "update_doc"
#         elif "configure" in action_lower or "change setting" in action_lower:
#             insight_type = "configure"
#         elif "restart" in action_lower or "reboot" in action_lower:
#              insight_type = "restart"
#         elif "escalate" in action_lower:
#             insight_type = "escalate"
            
#         insights.append(ActionableInsight(
#             insight_id=f"{parsed_data.incident_id}-insight-{i+1}", # Link insight to incident
#             description=action,
#             type=insight_type,
#             target=target # Placeholder for extracted target
#         ))
#     return insights

# --- Cache Functions (Example using simple dict, recommend SQLite/TinyDB for persistence) --- 
# incident_cache: Dict[str, CacheEntry] = {}
# def _get_incident_summary(incident: IncidentReport) -> str:
#     # Create a simple hash or summary of the description for cache key
#     # Be mindful of collisions if using basic hashing
#     import hashlib
#     return hashlib.md5(incident.description.encode()).hexdigest()[:16]

# def _check_cache(incident: IncidentReport) -> Optional[AnalysisResult]:
#     summary = _get_incident_summary(incident)
#     entry = incident_cache.get(summary)
#     if entry:
#         # Optional: Add logic for cache expiry
#         logger.info(f"Cache hit for incident summary: {summary}")
#         # Return a copy to avoid modifying the cached object directly
#         return entry.result.copy(deep=True)
#     logger.info(f"Cache miss for incident summary: {summary}")
#     return None

# def _add_to_cache(incident: IncidentReport, result: AnalysisResult):
#     # Requires incident_id on ActionableInsight to be set correctly before caching
#     if result.analysis_source == 'error': # Don't cache errors
#         return
#     summary = _get_incident_summary(incident)
#     entry = CacheEntry(
#         incident_summary=summary,
#         result=result.copy(deep=True), # Store a copy
#         timestamp=datetime.datetime.now()
#     )
#     incident_cache[summary] = entry
#     logger.info(f"Added analysis result to cache for summary: {summary}")


