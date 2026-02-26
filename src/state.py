import operator
from typing import Annotated, Dict, List, Optional, Literal

from pydantic import BaseModel, Field
from typing_extensions import TypedDict


class Evidence(BaseModel):
    goal: str
    found: bool
    content: Optional[str] = None
    location: str
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0)


JudgeName = Literal["Prosecutor", "Defense", "TechLead"]


class JudicialOpinion(BaseModel):
    judge: JudgeName
    criterion_id: str
    score: int = Field(ge=1, le=5)
    argument: str
    cited_evidence: List[str] = Field(default_factory=list)


class CriterionResult(BaseModel):
    criterion_id: str
    final_score: int = Field(ge=1, le=5)
    summary: str
    strengths: List[str] = Field(default_factory=list)
    weaknesses: List[str] = Field(default_factory=list)
    remediation: List[str] = Field(default_factory=list)
    dissent: Optional[str] = None


class AuditReport(BaseModel):
    overall_score: int = Field(ge=1, le=5)
    executive_summary: str
    criteria: List[CriterionResult] = Field(default_factory=list)
    key_risks: List[str] = Field(default_factory=list)
    next_steps: List[str] = Field(default_factory=list)


class AgentState(TypedDict):
    repo_url: str
    pdf_path: str

    evidences: Annotated[Dict[str, List[Evidence]], operator.ior]
    opinions: Annotated[List[JudicialOpinion], operator.add]
    final_report: Optional[AuditReport]