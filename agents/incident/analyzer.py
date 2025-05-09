import datetime
import logging
from typing import Dict, Any, Optional, List
import json
import httpx # Added for making HTTP requests
import re # Added for regular expression matching
import sqlite3 # Added for SQLite database
import hashlib # Added for creating incident summary hash
import os # <-- ADDED import
from pydantic import ValidationError # Added for specific error catching

from models import IncidentReport, AnalysisResult, LLMStructuredResponse, ActionableInsight, CacheEntry # Changed to direct import

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)
# --- Force DEBUG level for this specific module --- 
logger.setLevel(logging.DEBUG)

# Configuration for the LLM Service
# MODIFIED: Read from environment variables, falling back to defaults
LLM_SERVICE_URL = os.getenv("LLM_SERVICE_URL", "http://llm-service:8001/api/generate") 
LLM_REQUEST_TIMEOUT = float(os.getenv("LLM_REQUEST_TIMEOUT", 120.0))

# Configuration for Cache
CACHE_DB_PATH = "/app/data/incident_cache.db"

PROMPT_TEMPLATE = """
Analyze the following incident report and provide ONLY a valid, structured JSON response adhering strictly to the enhanced schema below.

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

**REQUIRED ENHANCED JSON OUTPUT SCHEMA:**
```json
{{
  "potential_root_causes": [
    {{
      "cause": "Example: Unstable network switch",
      "likelihood": "High",
      "explanation": "Example: Logs show repeated flapping on the core switch port."
    }},
    {{
      "cause": "Example: Database overload",
      "likelihood": "Medium",
      "explanation": "Example: Monitoring indicates high CPU and memory on DB server during the incident timeframe."
    }}
  ],
  "recommended_actions": [
    {{
      "action": "Example: Check switch S12 logs for errors.",
      "type": "Investigate",
      "target": "Switch S12",
      "priority": 1,
      "estimated_time_minutes": 30,
      "required_skills": ["Network Analysis", "Switch CLI"]
    }},
    {{
      "action": "Example: Restart application server App-01.",
      "type": "Remediate",
      "target": "App-01",
      "priority": 2,
      "estimated_time_minutes": 15,
      "required_skills": ["Application Support"]
    }}
  ],
  "incident_category": "Network",
  "estimated_resolution_time_hours": 2.5,
  "similar_known_issues": [
    "INC-12345",
    "KB-9876"
  ],
  "recommended_documentation": [
    "Internal Wiki: Switch Troubleshooting Guide",
    "Vendor Manual: Model XYZ Switch, Page 55"
  ],
  "confidence_explanation": "Example: Analysis based on symptom keywords and reported affected systems. High confidence in network issue, medium on specific component."
}}
```

**CRITICAL INSTRUCTIONS FOR LLM:**
1. Analyze the incident based *only* on the provided description.
2. Populate the `potential_root_causes` array with objects, each containing `cause`, `likelihood`, and `explanation`.
3. Populate the `recommended_actions` array with objects, each containing `action`, `type`, `target`, `priority`, `estimated_time_minutes`, and `required_skills`.
4. Provide an overall `incident_category` and `estimated_resolution_time_hours`.
5. List any `similar_known_issues` or `recommended_documentation` references as strings.
6. Explain your confidence reasoning in `confidence_explanation`.
7. **DO NOT** include any text, comments, or markdown outside the single ```json ... ``` block.
8. Ensure the final output is **syntactically valid JSON** parsable by standard libraries, paying close attention to commas, braces, brackets, and quotes.
9. Use `null` for optional fields if no value is applicable.

JSON Response:
```json
"""

# --- Database Initialization --- 

def _init_cache_db(conn: Optional[sqlite3.Connection] = None):
    """Initializes the SQLite database and creates the cache table if it doesn't exist.

    Args:
        conn: An optional existing sqlite3 connection to use (primarily for testing).
              If None, a new connection to CACHE_DB_PATH will be created.
    """
    close_conn = False
    if conn is None:
        try:
            conn = sqlite3.connect(CACHE_DB_PATH)
            close_conn = True
        except sqlite3.Error as e:
            logger.error(f"Error connecting to cache database {CACHE_DB_PATH}: {e}", exc_info=True)
            return # Cannot proceed without a connection

    try:
        cursor = conn.cursor()
        cursor.execute("""
        CREATE TABLE IF NOT EXISTS incident_analysis_cache (
            incident_summary TEXT PRIMARY KEY, -- Hash of the description
            analysis_result_json TEXT NOT NULL, -- JSON string of AnalysisResult
            timestamp DATETIME NOT NULL
        )
        """)
        conn.commit()
        db_path = CACHE_DB_PATH if close_conn else "(provided connection)"
        logger.info(f"Cache table verified/created in {db_path}")
    except sqlite3.Error as e:
        logger.error(f"Error initializing cache table: {e}", exc_info=True)
    finally:
        if close_conn and conn:
            conn.close()

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

    # --- Enhanced Logging ---
    logger.debug(f"LLM Prompt being sent:\\n{prompt}") # Log the full prompt
    try:
        # Attempt to serialize payload to string to get its size
        payload_json_str = json.dumps(payload)
        logger.info(f"Size of payload to LLM service: {len(payload_json_str)} bytes.")
    except TypeError as e: # Catch specific error if payload is not serializable
        logger.warning(f"Could not serialize payload to determine size for LLM service: {e}")
    except Exception as e: # Catch any other unexpected error during size calculation
        logger.warning(f"Could not determine payload size for LLM service due to an unexpected error: {e}")
    # --- End Enhanced Logging ---

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
    """Parses the raw JSON string from the LLM response into the enhanced LLMStructuredResponse model.

    Args:
        response: The raw string response from the LLM, expected to be a JSON block.
        errors_list: A list to append parsing/validation error messages to.

    Returns:
        An LLMStructuredResponse object if parsing and validation succeed, otherwise None.
    """
    logger.debug(f"Attempting to parse LLM response JSON...")
    
    # --- Attempt to extract JSON block --- 
    # Basic extraction assuming the response starts/ends with ```json ... ```
    # More robust regex might be needed if LLM output varies significantly.
    json_match = re.search(r"```json\s*({.*?})\s*```", response, re.DOTALL | re.IGNORECASE)
    
    if json_match:
        json_str_to_parse = json_match.group(1).strip()
        logger.debug("Found JSON content within ```json ... ``` delimiters.")
    else:
        logger.warning("Could not find ```json delimiters. Attempting to extract JSON object directly.")
        # Try to find the first '{' and last '}'
        try:
            start_index = response.index('{')
            end_index = response.rindex('}') + 1
            json_str_to_parse = response[start_index:end_index].strip()
            logger.debug(f"Extracted potential JSON string from first '{{' to last '}}': {json_str_to_parse[:100]}...")
        except ValueError:
            # This means '{' or '}' was not found, which is problematic
            logger.error("Could not find starting '{' or ending '}' in the LLM response.")
            json_str_to_parse = response.strip() # Fallback to old behavior, likely to fail validation next

    if not json_str_to_parse: # Should not happen if response is not None/empty
        error_msg = "LLM response is empty or invalid."
        logger.error(error_msg)
        errors_list.append(error_msg)
        return None

    # --- Attempt to parse JSON string --- 
    try:
        parsed_json = json.loads(json_str_to_parse)
        logger.debug(f"Successfully parsed JSON string: {parsed_json}")
    except json.JSONDecodeError as e:
        error_msg = f"Failed to decode JSON from LLM response: {e}"
        logger.error(error_msg, exc_info=True)
        logger.debug(f"Extracted JSON string was: {json_str_to_parse}")
        errors_list.append(error_msg)
        return None
    except Exception as e:
        error_msg = f"Unexpected error parsing JSON: {e}"
        logger.error(error_msg, exc_info=True)
        logger.debug(f"Extracted JSON string was: {json_str_to_parse}")
        errors_list.append(error_msg)
        return None

    # --- Attempt to validate against Pydantic model --- 
    try:
        validated_data = LLMStructuredResponse(**parsed_json)
        logger.info("Successfully validated LLM response against enhanced Pydantic model.")
        return validated_data
    except ValidationError as e:
        error_msg = f"LLM response JSON does not match expected schema: {e}"
        logger.error(error_msg, exc_info=False) # Don't need full traceback for validation error
        logger.debug(f"Parsed JSON was: {parsed_json}")
        errors_list.append(error_msg)
        return None
    except Exception as e:
        error_msg = f"Unexpected error validating parsed JSON: {e}"
        logger.error(error_msg, exc_info=True)
        logger.debug(f"Parsed JSON was: {parsed_json}")
        errors_list.append(error_msg)
        return None

def _calculate_confidence(parsed_data: Optional[LLMStructuredResponse], raw_response: str) -> float:
    """Calculates a heuristic confidence score based on the *enhanced* parsed LLM response.

    Assigns points based on the presence and basic validity of key fields in the 
    structured response. Penalizes for missing data or parsing failures.

    Args:
        parsed_data: The validated LLMStructuredResponse object, or None if parsing failed.
        raw_response: The raw string response from the LLM.

    Returns:
        A confidence score between 0.0 and 1.0.
    """
    if parsed_data is None:
        logger.warning("Cannot calculate confidence score: LLM response parsing failed.")
        return 0.1 # Very low confidence if parsing completely failed

    score = 0.0
    max_score = 100.0
    
    logger.debug("Calculating confidence score...")

    # --- Presence of Core Components --- 
    if parsed_data.potential_root_causes:
        score += 20
        logger.debug("+20 points: Potential root causes present.")
    else:
        logger.debug("  0 points: Potential root causes missing.")

    if parsed_data.recommended_actions:
        score += 20
        logger.debug("+20 points: Recommended actions present.")
    else:
        logger.debug("  0 points: Recommended actions missing.")

    # --- Presence of Enhanced Fields --- 
    if parsed_data.incident_category:
        score += 10
        logger.debug("+10 points: Incident category present.")
    else:
        logger.debug("  0 points: Incident category missing.")
        
    if parsed_data.estimated_resolution_time_hours is not None:
        score += 10
        logger.debug("+10 points: Estimated resolution time present.")
    else:
        logger.debug("  0 points: Estimated resolution time missing.")

    if parsed_data.similar_known_issues:
        score += 5
        logger.debug("+5 points: Similar known issues present.")
    else:
        logger.debug("  0 points: Similar known issues missing.")
        
    if parsed_data.recommended_documentation:
        score += 5
        logger.debug("+5 points: Recommended documentation present.")
    else:
        logger.debug("  0 points: Recommended documentation missing.")

    # --- Detail within Causes and Actions --- 
    cause_details_score = 0
    if parsed_data.potential_root_causes:
        num_causes = len(parsed_data.potential_root_causes)
        has_likelihood = any(c.likelihood for c in parsed_data.potential_root_causes)
        has_explanation = any(c.explanation for c in parsed_data.potential_root_causes)
        if num_causes > 0: cause_details_score += 2
        if has_likelihood: cause_details_score += 4
        if has_explanation: cause_details_score += 4
        score += cause_details_score
        logger.debug(f"+{cause_details_score} points: Root cause details (count={num_causes}, likelihood={has_likelihood}, explanation={has_explanation}).")
    else:
        logger.debug("  0 points: Root cause details (no causes).")

    action_details_score = 0
    if parsed_data.recommended_actions:
        num_actions = len(parsed_data.recommended_actions)
        has_type = any(a.type for a in parsed_data.recommended_actions)
        has_priority = any(a.priority is not None for a in parsed_data.recommended_actions)
        has_time = any(a.estimated_time_minutes is not None for a in parsed_data.recommended_actions)
        has_skills = any(a.required_skills for a in parsed_data.recommended_actions)
        if num_actions > 0: action_details_score += 2
        if has_type: action_details_score += 2
        if has_priority: action_details_score += 2
        if has_time: action_details_score += 2
        if has_skills: action_details_score += 2
        score += action_details_score
        logger.debug(f"+{action_details_score} points: Action details (count={num_actions}, type={has_type}, prio={has_priority}, time={has_time}, skills={has_skills}).")
    else:
        logger.debug("  0 points: Action details (no actions).")
        
    # --- Confidence Explanation --- 
    if parsed_data.confidence_explanation:
        score += 10 
        logger.debug("+10 points: Confidence explanation present.")
    else:
        logger.debug("  0 points: Confidence explanation missing.")

    # Normalize score to 0.0 - 1.0
    final_score = max(0.0, min(1.0, score / max_score))
    logger.info(f"Calculated confidence score: {final_score:.2f} (raw score: {score}/{max_score})")
    return final_score

def _extract_insights(parsed_data: LLMStructuredResponse, incident_id: str) -> List[ActionableInsight]:
    """Extracts actionable insights from the *enhanced* parsed LLM response.

    Iterates through the recommended_actions in the parsed data and creates
    ActionableInsight objects, mapping fields appropriately.

    Args:
        parsed_data: The validated LLMStructuredResponse object.
        incident_id: The ID of the incident (currently unused, but kept for context).

    Returns:
        A list of ActionableInsight objects.
    """
    insights: List[ActionableInsight] = []
    if not parsed_data or not parsed_data.recommended_actions:
        logger.warning("No recommended actions found in parsed LLM response to extract insights from.")
        return insights

    logger.info(f"Extracting actionable insights from {len(parsed_data.recommended_actions)} recommended actions.")
    for i, action in enumerate(parsed_data.recommended_actions):
        try:
            # Create insight using data from the RecommendedAction object
            insight = ActionableInsight(
                description=action.action,  # Use the main action description
                type=action.type,          # Use the action type
                target=action.target,
                priority=action.priority,
                estimated_time_minutes=action.estimated_time_minutes,
                required_skills=action.required_skills
                # insight_id is generated automatically by default_factory
            )
            insights.append(insight)
        except Exception as e:
            logger.error(f"Error creating ActionableInsight for action #{i}: {action} - Error: {e}", exc_info=True)
            # Continue to next action if one fails

    logger.info(f"Successfully extracted {len(insights)} actionable insights.")
    return insights

# --- Cache Functions --- 

def _check_cache(incident: IncidentReport, conn: Optional[sqlite3.Connection] = None) -> Optional[AnalysisResult]:
    """Checks the cache for a previous analysis of a similar incident.

    Args:
        incident: The incoming incident report.
        conn: Optional existing DB connection for testing.

    Returns:
        A cached AnalysisResult if found, otherwise None.
    """
    summary = _get_incident_summary(incident.description)
    logger.info(f"Checking cache for incident summary: {summary}")
    # conn = None # Initialize connection variable - Removed
    close_conn = False
    if conn is None:
        try:
            conn = sqlite3.connect(CACHE_DB_PATH)
            close_conn = True
        except sqlite3.Error as e:
            logger.error(f"Error connecting to cache database {CACHE_DB_PATH} for read: {e}", exc_info=True)
            return None # Cannot check cache without DB connection

    try:
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
        # Consider deleting the invalid cache entry here?
        return None
    except Exception as e:
        logger.error(f"Unexpected error deserializing cached result (summary: {summary}): {e}", exc_info=True)
        return None
    finally:
        if close_conn and conn: # Ensure connection is closed only if created within the function
            conn.close()

def _add_to_cache(incident: IncidentReport, result: AnalysisResult, conn: Optional[sqlite3.Connection] = None):
    """Adds or updates an analysis result in the cache.
    
    Only adds results that did not encounter errors during processing.

    Args:
        incident: The incident report used for the analysis.
        result: The successful AnalysisResult to cache.
        conn: Optional existing DB connection for testing.
    """
    if result.analysis_source == 'error':
        logger.warning("Skipping caching for result with errors.")
        return
        
    summary = _get_incident_summary(incident.description)
    # conn = None # Initialize connection variable - Removed
    close_conn = False
    if conn is None:
        try:
            conn = sqlite3.connect(CACHE_DB_PATH)
            close_conn = True
        except sqlite3.Error as e:
            logger.error(f"Error connecting to cache database {CACHE_DB_PATH} for write: {e}", exc_info=True)
            return # Cannot cache without DB connection
            
    try:
        result_json = result.model_dump_json(exclude_none=True)
        
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
        if close_conn and conn: # Ensure connection is closed only if created within the function
            conn.close()


