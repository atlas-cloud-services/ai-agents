from pydantic import BaseModel, Field
from typing import List, Optional
import datetime
import uuid # Added for insight IDs

class IncidentReport(BaseModel):
    """Represents the input incident data."""
    incident_id: str = Field(..., description="Unique identifier for the incident.")
    timestamp: datetime.datetime = Field(default_factory=datetime.datetime.now, description="Time the incident was reported.")
    description: str = Field(..., description="Detailed description of the incident symptoms and observations.")
    priority: Optional[int] = Field(None, description="Priority level (e.g., 1-5).")
    affected_systems: Optional[List[str]] = Field(None, description="List of systems/services affected.")
    reporter: Optional[str] = Field(None, description="Who reported the incident.")

# --- Enhanced Data Structures ---

class RootCause(BaseModel):
    """Structured representation of a potential root cause."""
    cause: str = Field(..., description="Description of the potential root cause.")
    likelihood: str = Field(..., description="Estimated likelihood (e.g., High, Medium, Low).")
    explanation: str = Field(..., description="Brief explanation supporting this root cause.")

class RecommendedAction(BaseModel):
    """Structured representation of a recommended action."""
    action: str = Field(..., description="Detailed description of the action to be taken.")
    type: str = Field(..., description="Category of action (e.g., Investigate, Remediate, Configure, Escalate, Document).")
    target: Optional[str] = Field(None, description="Specific system, component, or resource the action applies to.")
    priority: Optional[int] = Field(None, description="Suggested priority for the action (e.g., 1-5).")
    estimated_time_minutes: Optional[int] = Field(None, description="Estimated time required for the action in minutes.")
    required_skills: List[str] = Field([], description="Technical skills needed to perform the action.")

class LLMStructuredResponse(BaseModel):
    """Defines the *enhanced* expected structured output from the LLM analysis."""
    potential_root_causes: List[RootCause] = Field([], description="List of likely root causes identified by the LLM.")
    recommended_actions: List[RecommendedAction] = Field([], description="List of suggested steps to resolve the incident.")
    incident_category: Optional[str] = Field(None, description="Categorization of the incident (e.g., Hardware, Software, Network, Security, User Error).")
    estimated_resolution_time_hours: Optional[float] = Field(None, description="Overall estimated time to resolve the incident in hours.")
    similar_known_issues: List[str] = Field([], description="References to potentially similar past incidents or known issues (e.g., IDs, KB articles).")
    recommended_documentation: List[str] = Field([], description="Links or references to relevant documentation.")
    confidence_explanation: Optional[str] = Field(None, description="LLM's explanation for its analysis confidence.")

# --- Original Structures (ActionableInsight used in final result) ---

class ActionableInsight(BaseModel):
    """Represents a specific, actionable task derived from the analysis.
       Now derived from the enhanced RecommendedAction.
    """
    insight_id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique ID for the insight.")
    description: str = Field(..., description="Description of the actionable step (from RecommendedAction.action).")
    target: Optional[str] = Field(None, description="Specific target related to the action (from RecommendedAction.target).")
    type: str = Field(..., description="Type of action (from RecommendedAction.type).")
    priority: Optional[int] = Field(None, description="Action priority (from RecommendedAction.priority).")
    estimated_time_minutes: Optional[int] = Field(None, description="Estimated time (from RecommendedAction.estimated_time_minutes).")
    required_skills: List[str] = Field([], description="Required skills (from RecommendedAction.required_skills).")

class AnalysisResult(BaseModel):
    """Represents the final structured analysis output from the agent."""
    incident_id: str
    analysis_timestamp: datetime.datetime = Field(default_factory=datetime.datetime.now)
    llm_raw_response: Optional[str] = Field(None, description="The raw text response from the LLM.")
    # Uses the *enhanced* LLMStructuredResponse model
    parsed_response: Optional[LLMStructuredResponse] = Field(None, description="The parsed *enhanced* structured data from the LLM response.")
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Confidence score (0.0 to 1.0) of the analysis quality.")
    actionable_insights: List[ActionableInsight] = Field([], description="List of specific actionable steps derived from recommended actions.")
    errors: List[str] = Field([], description="List of errors encountered during analysis.")
    analysis_source: str = Field(..., description="Source of the analysis ('llm', 'cache', 'error').")
    processing_time_seconds: Optional[float] = Field(None, description="Time taken for the analysis.")
    # similar_incident_ids field is removed as this info is now within LLMStructuredResponse
    # similar_incident_ids: List[str] = Field([], description="IDs of similar past incidents found in cache.") # Removed

class CacheEntry(BaseModel):
    """Schema for storing analysis results in the cache."""
    incident_summary: str # A concise summary or hash of the incident description
    result: AnalysisResult # Stores the enhanced AnalysisResult
    timestamp: datetime.datetime
