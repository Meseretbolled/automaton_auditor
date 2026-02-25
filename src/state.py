import operator
from typing import Annotated, Dict, List, Optional
from pydantic import BaseModel, Field
from typing_extensions import TypedDict

class Evidence(BaseModel):
    goal: str
    found: bool
    content: Optional[str] = None
    location: str
    rationale: str
    confidence: float

class AgentState(TypedDict):
    repo_url: str
    pdf_path: str
    # Reducer ensures parallel detectives merge results instead of overwriting
    evidences: Annotated[Dict[str, List[Evidence]], operator.ior]
    opinions: Annotated[List[dict], operator.add]