import operator
from typing import Annotated, Dict, List, Optional, Literal, Any

from pydantic import BaseModel, Field
from typing_extensions import TypedDict


# =========================================================
# 🔎 Detective Output
# =========================================================

class Evidence(BaseModel):
    goal: str
    found: bool
    content: Optional[str] = None
    location: str
    rationale: str
    confidence: float = Field(ge=0.0, le=1.0)


# =========================================================
# ⚖️ Judicial Output (Per-criterion)
# =========================================================

JudgeName = Literal["Prosecutor", "Defense", "TechLead"]


class JudicialOpinion(BaseModel):
    judge: JudgeName
    criterion_id: str
    score: int = Field(ge=1, le=5)
    argument: str
    cited_evidence: List[str] = Field(default_factory=list)


# =========================================================
# 👑 Final Report (Chief Justice Output)
# =========================================================

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


# =========================================================
# 🧩 Reducers (to prevent data loss during parallel execution)
# =========================================================

def merge_evidence_dict(
    left: Dict[str, List[Evidence]] | None,
    right: Dict[str, List[Evidence]] | None,
) -> Dict[str, List[Evidence]]:
    """
    Merge dict[str, list[Evidence]] without losing items.
    - preserves existing keys
    - extends lists when the same key exists on both sides
    """
    out: Dict[str, List[Evidence]] = {}
    for src in (left or {}):
        out[src] = list(left[src] or [])

    for src, items in (right or {}).items():
        if src not in out:
            out[src] = list(items or [])
        else:
            out[src].extend(list(items or []))

    return out


def last_write_wins(left: Any, right: Any) -> Any:
    """Reducer for single final values (e.g., final_report)."""
    return right if right is not None else left


# =========================================================
# 🧠 LangGraph State
# =========================================================

class AgentState(TypedDict, total=False):
    repo_url: str
    pdf_path: str

    # Detective & Judge aggregation
    evidences: Annotated[Dict[str, List[Evidence]], merge_evidence_dict]
    opinions: Annotated[List[JudicialOpinion], operator.add]

    # Chief Justice output
    final_report: Annotated[Optional[AuditReport], last_write_wins]

    # Optional flags (help conditional edges + clearer debugging)
    repo_failed: bool
    doc_failed: bool
    vision_failed: bool