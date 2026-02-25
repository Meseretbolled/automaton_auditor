import operator
from typing import Annotated, Dict, List, Optional
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

class Evidence(BaseModel):
    """Structured evidence with bounded confidence scores."""
    goal: str
    found: bool
    content: Optional[str] = None
    location: str
    rationale: str
    # Enforces 0.0 to 1.0 range as requested by the rubric
    confidence: float = Field(ge=0.0, le=1.0)

class JudicialOpinion(BaseModel):
    """Explicit model for the final verdict."""
    verdict: str = Field(description="Final compliance decision")
    risk_score: int = Field(ge=0, le=10, description="Risk level 0-10")
    summary: str

class AgentState(TypedDict):
    repo_url: str
    pdf_path: str
    # Reducer: operator.ior for Dicts ensures parallel detective findings merge
    evidences: Annotated[Dict[str, List[Evidence]], operator.ior]
    # New explicit field for judicial layer
    judicial_opinion: Optional[JudicialOpinion]