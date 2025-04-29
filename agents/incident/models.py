from pydantic import BaseModel, Field
from typing import List, Optional
import datetime

class IncidentReport(BaseModel):
    """Represents the input incident data."""
    incident_id: str = Field(..., description="Unique identifier for the incident.")
    timestamp: datetime.datetime = Field(default_factory=datetime.datetime.now, description="Time the incident was reported.")
    description: str = Field(..., description="Detailed description of the incident symptoms and observations.")
    priority: Optional[int] = Field(None, description="Priority level (e.g., 1-5).")
    affected_systems: Optional[List[str]] = Field(None, description="List of systems/services affected.")
    reporter: Optional[str] = Field(None, description="Who reported the incident.")

class LLMStructuredResponse(BaseModel):
    """Defines the expected structured output from the LLM analysis."""
    potential_root_causes: List[str] = Field(..., description="List of likely root causes identified by the LLM.")
    recommended_actions: List[str] = Field(..., description="List of suggested steps to resolve the incident.")
    potential_impact: Optional[str] = Field(None, description="Potential business or technical impact if not resolved.")
    confidence_explanation: Optional[str] = Field(None, description="LLM's explanation for its confidence level (if provided).")

class ActionableInsight(BaseModel):
    """Represents a specific, actionable task derived from the analysis."""
    insight_id: str = Field(..., description="Unique ID for the insight.")
    description: str = Field(..., description="Description of the actionable step.")
    target: Optional[str] = Field(None, description="Specific system, component, or KB article related to the action.")
    type: str = Field(..., description="Type of action (e.g., 'investigate', 'configure', 'update_doc', 'escalate').")

class AnalysisResult(BaseModel):
    """Represents the final structured analysis output from the agent."""
    incident_id: str
    analysis_timestamp: datetime.datetime = Field(default_factory=datetime.datetime.now)
    llm_raw_response: Optional[str] = Field(None, description="The raw text response from the LLM.")
    parsed_response: Optional[LLMStructuredResponse] = Field(None, description="The parsed structured data from the LLM response.")
    confidence_score: Optional[float] = Field(None, ge=0.0, le=1.0, description="Confidence score (0.0 to 1.0) of the analysis quality.")
    actionable_insights: List[ActionableInsight] = Field([], description="List of specific actionable steps.")
    errors: List[str] = Field([], description="List of errors encountered during analysis.")
    analysis_source: str = Field(..., description="Source of the analysis ('llm', 'cache', 'error').")
    processing_time_seconds: Optional[float] = Field(None, description="Time taken for the analysis.")
    similar_incident_ids: List[str] = Field([], description="IDs of similar past incidents found in cache.")

class CacheEntry(BaseModel):
    """Schema for storing analysis results in the cache."""
    incident_summary: str # A concise summary or hash of the incident description
    result: AnalysisResult
    timestamp: datetime.datetime
