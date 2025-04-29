import datetime
import logging
from typing import Dict, Any, Optional, List
import json
import httpx # Added for making HTTP requests
import re # Added for regular expression matching
import sqlite3 # Added for SQLite database
import hashlib # Added for creating incident summary hash
from pydantic import ValidationError # Added for specific error catching

from .models import IncidentReport, AnalysisResult, LLMStructuredResponse, ActionableInsight, CacheEntry # Added CacheEntry

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
# --- Force DEBUG level for this specific module --- 
logger.setLevel(logging.DEBUG)

# Configuration for the LLM Service
LLM_SERVICE_URL = "http://127.0.0.1:8001/generate"
LLM_REQUEST_TIMEOUT = 120.0 # Increased from 60.0

# Configuration for Cache
CACHE_DB_PATH = "incident_cache.db"

PROMPT_TEMPLATE = """
Analyze the following incident report and provide ONLY a valid, structured JSON response adhering strictly to the schema below.

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

**REQUIRED JSON OUTPUT SCHEMA:**
```json
{{
  "potential_root_causes": [
    "String describing cause 1...",
    "String describing cause 2..."
  ],
  "recommended_actions": [
    "String describing action 1...",
    "String describing action 2..."
  ],
  "potential_impact": "String describing potential impact...",
  "confidence_explanation": "String explaining analysis confidence..."
}}
```

**CRITICAL INSTRUCTIONS FOR LLM:**
1. Identify the most likely root causes based *only* on the provided description. List them as **simple strings** in the `potential_root_causes` array.
2. Suggest concrete, actionable steps. List them as **simple strings** in the `recommended_actions` array.
3. Briefly describe the potential impact as a **single string**.
4. Explain your confidence reasoning as a **single string**.
5. **DO NOT** nest JSON objects within the `potential_root_causes` or `recommended_actions` arrays.
6. **DO NOT** include any text, comments, or markdown outside the single ```json ... ``` block.
7. **DO NOT** add duplicate keys.
8. Ensure the final output is **syntactically valid JSON** parsable by standard libraries.

JSON Response:
```json
"""

# --- Database Initialization --- 

def _init_cache_db():
    """Initializes the SQLite database and creates the cache table if it doesn't exist."""
    try:
        with sqlite3.connect(CACHE_DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS incident_analysis_cache (
                incident_summary TEXT PRIMARY KEY, -- Hash of the description
                analysis_result_json TEXT NOT NULL, -- JSON string of AnalysisResult
                timestamp DATETIME NOT NULL
            )
            """)
            conn.commit()
            logger.info(f"Cache database initialized at {CACHE_DB_PATH}")
    except sqlite3.Error as e:
        logger.error(f"Error initializing cache database: {e}", exc_info=True)
        # Agent might continue without caching if DB init fails

# Call initialization once when the module loads
# _init_cache_db() # <<< Commented out to rely on explicit initialization or fixture call

# --- Helper Functions --- 

def _get_incident_summary(description: str) -> str:
    """Creates a short MD5 hash of the incident description to use as a cache key.

    Args:
        description: The incident description string.

    Returns:
        A hexadecimal MD5 hash string.
    """
    # Normalize whitespace and case for potentially better matching, though hash is sensitive
    normalized_desc = ' '.join(description.lower().split())
    return hashlib.md5(normalized_desc.encode()).hexdigest()

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
    """Analyzes an incident report using an LLM, with caching.

    Orchestrates cache check, prompt creation, LLM call, parsing, scoring, 
    insight extraction, and cache update.

    Args:
        incident: The incident report data.

    Returns:
        An AnalysisResult object containing the analysis details or errors.
    """
    start_time = datetime.datetime.now()
    logger.info(f"Starting analysis for incident ID: {incident.incident_id}")

    # --- Step 1: Cache Check --- 
    cached_result = _check_cache(incident)
    if cached_result:
        # Update timestamp and source for the cached result
        cached_result.analysis_timestamp = datetime.datetime.now()
        cached_result.analysis_source = "cache"
        cached_result.processing_time_seconds = (datetime.datetime.now() - start_time).total_seconds()
        logger.info(f"Analysis complete for incident ID: {incident.incident_id} from cache in {cached_result.processing_time_seconds:.2f}s")
        return cached_result

    # --- If Cache Miss, Proceed with LLM Analysis --- 
    analysis_result = AnalysisResult(
        incident_id=incident.incident_id,
        analysis_source="pending",
        errors=[]
    )

    # --- Step 2: Generate Prompt ---
    try:
        prompt = _create_llm_prompt(incident)
        logger.debug(f"Generated prompt:\n{prompt[:300]}...")
    except Exception as e:
        error_msg = f"Error creating LLM prompt: {e}"
        logger.error(error_msg, exc_info=True)
        analysis_result.errors.append(error_msg)
        analysis_result.analysis_source = "error"
        analysis_result.processing_time_seconds = (datetime.datetime.now() - start_time).total_seconds()
        return analysis_result

    # --- Step 3: Call LLM Service --- 
    llm_raw_response = await _call_llm_service(prompt)
    
    if llm_raw_response is None:
        error_msg = "Failed to get response from LLM service."
        analysis_result.errors.append(error_msg)
        analysis_result.analysis_source = "error"
        analysis_result.processing_time_seconds = (datetime.datetime.now() - start_time).total_seconds()
        return analysis_result

    analysis_result.llm_raw_response = llm_raw_response

    # --- Step 4: Parse LLM Response --- 
    parsed_data = _parse_llm_response(llm_raw_response, analysis_result.errors)
    
    if parsed_data:
        analysis_result.parsed_response = parsed_data
        analysis_result.analysis_source = "llm" # Source is LLM if parsing ok
    else:
        analysis_result.analysis_source = "error"

    # --- Step 5: Calculate Confidence Score --- 
    analysis_result.confidence_score = _calculate_confidence(
        parsed_data, 
        llm_raw_response
    )

    # --- Step 6: Extract Actionable Insights --- 
    if analysis_result.parsed_response:
        analysis_result.actionable_insights = _extract_insights(
            analysis_result.parsed_response, 
            incident.incident_id
        )

    # --- Step 7: Add to Cache --- 
    # Add the result to cache only if the source wasn't an error
    if analysis_result.analysis_source != "error":
       _add_to_cache(incident, analysis_result)

    # --- Finalize ---
    end_time = datetime.datetime.now()
    analysis_result.processing_time_seconds = (end_time - start_time).total_seconds()
    if analysis_result.analysis_source != "error":
        logger.info(f"Analysis complete for incident ID: {incident.incident_id} via LLM in {analysis_result.processing_time_seconds:.2f}s (Confidence: {analysis_result.confidence_score:.2f})")
    else:
         logger.warning(f"Analysis for incident ID: {incident.incident_id} completed with errors in {analysis_result.processing_time_seconds:.2f}s (Confidence: {analysis_result.confidence_score:.2f})")

    return analysis_result

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
    # --- DEBUG LOGGING START ---
    logger.debug(f"_parse_llm_response received raw response (len={len(response)}):\n---START RAW---\n{response}\n---END RAW---")
    # --- DEBUG LOGGING END ---
    if not response:
        error_msg = "LLM response was empty."
        logger.warning(error_msg)
        errors_list.append(error_msg)
        return None

    json_str = None
    try:
        # Priority 1: Look for ```json ... ``` block and extract content within {}
        json_markdown_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response, re.DOTALL | re.IGNORECASE)
        if json_markdown_match:
            json_str = json_markdown_match.group(1)
            logger.debug("Regex Priority 1 (Markdown Block) MATCHED.")
        else:
            logger.debug("Regex Priority 1 (Markdown Block) DID NOT MATCH.")
            # Priority 2: Look for the first { ... } block (non-greedy)
            first_json_match = re.search(r'(\{.*?\})', response, re.DOTALL)
            if first_json_match:
                json_str = first_json_match.group(1)
                logger.debug("Regex Priority 2 (First Block) MATCHED.")
            else:
                logger.debug("Regex Priority 2 (First Block) DID NOT MATCH.")

        # --- DEBUG LOGGING START ---
        logger.debug(f"Value of json_str BEFORE validation: {'None' if json_str is None else json_str[:500] + '...'}")
        # --- DEBUG LOGGING END ---

        if json_str:
            logger.debug(f"Extracted JSON string: {json_str[:200]}...")
            
            # Parse the extracted JSON string
            data = json.loads(json_str)
            
            # Validate the parsed data against the Pydantic model
            parsed_obj = LLMStructuredResponse(**data)
            logger.info("Successfully parsed and validated LLM response against flexible model.")
            return parsed_obj
        else:
            error_msg = "Could not find JSON object structure in LLM response."
            logger.warning(f"{error_msg} Raw response snippet: {response[:500]}...") # Log snippet here too
            errors_list.append(error_msg)
            return None
            
    except json.JSONDecodeError as e:
        error_msg = f"Failed to decode extracted JSON string [len={len(json_str) if json_str else 0}]: {e}"
        logger.error(f"{error_msg} - Extracted string: {json_str[:500]}...", exc_info=True)
        errors_list.append(error_msg)
        return None
    except ValidationError as e:
        error_msg = f"LLM response JSON failed validation against flexible model: {e}"
        logger.error(error_msg, exc_info=True)
        errors_list.append(error_msg)
        # Return None even if validation fails, as per previous logic. We might try partial parsing later.
        return None
    except Exception as e:
        error_msg = f"Unexpected error during LLM response processing: {e}"
        logger.error(error_msg, exc_info=True)
        errors_list.append(error_msg)
        return None

def _calculate_confidence(parsed_data: Optional[LLMStructuredResponse], raw_response: str) -> float:
    """Calculates a confidence score (0.0 - 1.0) based on parsing success
    and completeness of the structured response (handles flexible types).

    Args:
        parsed_data: The parsed LLMStructuredResponse object, or None if parsing failed.
        raw_response: The raw response string from the LLM (can be used for future checks).

    Returns:
        A float between 0.0 and 1.0 representing the confidence score.
    """
    logger.info("Calculating confidence score...")
    
    if parsed_data is None:
        logger.warning("Confidence score is low due to parsing/validation failure.")
        return 0.1 # Low confidence if parsing or validation failed
    
    # Start with a base score assuming parsing/validation was successful
    score = 0.5 
    
    # Increase score based on presence and basic validity of fields
    # Check if list exists and is not empty
    if parsed_data.potential_root_causes and isinstance(parsed_data.potential_root_causes, list) and len(parsed_data.potential_root_causes) > 0:
        score += 0.1
    # Check if list exists and is not empty
    if parsed_data.recommended_actions and isinstance(parsed_data.recommended_actions, list) and len(parsed_data.recommended_actions) > 0:
        score += 0.1
    # Check if field exists, is a string, and not empty/whitespace
    if parsed_data.potential_impact and isinstance(parsed_data.potential_impact, str) and parsed_data.potential_impact.strip():
        score += 0.1
    # Check if field exists, is a string, and not empty/whitespace
    if parsed_data.confidence_explanation and isinstance(parsed_data.confidence_explanation, str) and parsed_data.confidence_explanation.strip():
        score += 0.1
        
    # --- Future Enhancements --- 
    # - Check for specific keywords in explanation (e.g., "uncertain", "low confidence")
    # - Analyze length/detail of causes and actions
    # - Use raw_response length or structure as a factor
    
    final_score = min(score, 1.0) # Ensure score doesn't exceed 1.0
    logger.info(f"Calculated confidence score: {final_score:.2f}")
    return final_score

def _extract_insights(parsed_data: LLMStructuredResponse, incident_id: str) -> List[ActionableInsight]:
    """Extracts actionable insights from the LLM's recommended actions.
    
    Performs basic keyword matching to categorize actions.
    Safely handles cases where recommended_actions might contain non-string elements.

    Args:
        parsed_data: The validated structured response from the LLM.
        incident_id: The ID of the incident for linking insights.

    Returns:
        A list of ActionableInsight objects.
    """
    logger.info("Extracting actionable insights...")
    insights = []
    # Check if parsed_data and recommended_actions exist and if recommended_actions is a list
    if not parsed_data or not parsed_data.recommended_actions or not isinstance(parsed_data.recommended_actions, list):
        logger.warning("No valid recommended actions list found to extract insights from.")
        return []
        
    action_index = 0
    for action in parsed_data.recommended_actions:
        # Ensure the action is a string before processing
        if not isinstance(action, str):
            logger.warning(f"Skipping non-string item in recommended_actions: {action}")
            continue

        action_index += 1 # Increment index only for valid string actions
        insight_type = "investigate" # Default type
        target = None # Placeholder for target extraction (future enhancement)
        action_lower = action.lower()
        
        # Basic keyword-based classification (same as before)
        if "check logs" in action_lower or "review logs" in action_lower or "examine logs" in action_lower:
            insight_type = "investigate"
        elif "update" in action_lower and ("kb" in action_lower or "doc" in action_lower or "knowledge base" in action_lower):
            insight_type = "update_doc"
        elif "configure" in action_lower or "change setting" in action_lower or "adjust parameter" in action_lower:
            insight_type = "configure"
        elif "restart" in action_lower or "reboot" in action_lower or "recycle" in action_lower:
             insight_type = "restart"
        elif "escalate" in action_lower or "notify" in action_lower:
            insight_type = "escalate"
        elif "monitor" in action_lower or "observe" in action_lower:
            insight_type = "monitor"
        elif "verify" in action_lower or "confirm" in action_lower or "check status" in action_lower:
             insight_type = "verify"
             
        insight = ActionableInsight(
            # Use the incremented action_index
            insight_id=f"{incident_id}-insight-{action_index}", 
            description=action, # Use the original string action
            type=insight_type,
            target=target # Currently None
        )
        insights.append(insight)
        logger.debug(f"Extracted insight: Type='{insight.type}', Description='{insight.description[:50]}...'")

    logger.info(f"Extracted {len(insights)} actionable insights from string actions.")
    return insights

# --- Cache Functions --- 

def _check_cache(incident: IncidentReport) -> Optional[AnalysisResult]:
    """Checks the cache for a previous analysis of a similar incident.

    Args:
        incident: The incoming incident report.

    Returns:
        A cached AnalysisResult if found, otherwise None.
    """
    summary = _get_incident_summary(incident.description)
    logger.info(f"Checking cache for incident summary: {summary}")
    conn = None # Initialize connection variable
    try:
        conn = sqlite3.connect(CACHE_DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT analysis_result_json FROM incident_analysis_cache WHERE incident_summary = ?",
            (summary,)
        )
        row = cursor.fetchone()
        if row:
            logger.info(f"Cache hit for incident summary: {summary}")
            analysis_result = AnalysisResult.model_validate_json(row[0])
            return analysis_result
        else:
            logger.info(f"Cache miss for incident summary: {summary}")
            return None
    except sqlite3.Error as e:
        logger.error(f"SQLite error checking cache (summary: {summary}): {e}", exc_info=True)
        return None
    except ValidationError as e:
        logger.error(f"Failed to validate cached data (summary: {summary}): {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error deserializing cached result (summary: {summary}): {e}", exc_info=True)
        return None
    finally:
        if conn: # Ensure connection is closed even if errors occurred
            conn.close()

def _add_to_cache(incident: IncidentReport, result: AnalysisResult):
    """Adds or updates an analysis result in the cache.
    
    Only adds results that did not encounter errors during processing.

    Args:
        incident: The incident report used for the analysis.
        result: The successful AnalysisResult to cache.
    """
    if result.analysis_source == 'error':
        logger.warning("Skipping caching for result with errors.")
        return
        
    summary = _get_incident_summary(incident.description)
    conn = None # Initialize connection variable
    try:
        result_json = result.model_dump_json(exclude_none=True)
        
        conn = sqlite3.connect(CACHE_DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
        INSERT OR REPLACE INTO incident_analysis_cache 
        (incident_summary, analysis_result_json, timestamp)
        VALUES (?, ?, ?)
        """, (summary, result_json, datetime.datetime.now()))
        conn.commit()
        logger.info(f"Added/Updated analysis result in cache for summary: {summary}")
    except sqlite3.Error as e:
        logger.error(f"SQLite error adding/updating cache (summary: {summary}): {e}", exc_info=True)
    except Exception as e:
        logger.error(f"Unexpected error serializing result for caching (summary: {summary}): {e}", exc_info=True)
    finally:
        if conn: # Ensure connection is closed even if errors occurred
            conn.close()


