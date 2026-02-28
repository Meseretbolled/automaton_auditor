import json
import os
import time
from pathlib import Path
from typing import Dict, List, Tuple, Any

from pydantic import ValidationError

from src.state import AgentState, Evidence, JudicialOpinion, JudgeName


def _repo_root() -> Path:
    # rubric.json expected at repo root (same level as src/)
    # This works even if you run from another directory.
    return Path(__file__).resolve().parents[2]


def _load_rubric(path: str = "rubric.json") -> List[Dict[str, Any]]:
    rubric_path = _repo_root() / path
    if not rubric_path.exists():
        raise FileNotFoundError(
            f"Missing {rubric_path}. Create rubric.json in the repo root (same level as src/)."
        )

    with open(rubric_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # ✅ support both formats
    dims = data.get("dimensions") or data.get("criteria") or []
    return dims if isinstance(dims, list) else []


def _flatten_evidence(evidences: Dict[str, List[Evidence]]) -> List[Tuple[str, Evidence]]:
    flat: List[Tuple[str, Evidence]] = []
    for source, items in (evidences or {}).items():
        for i, ev in enumerate(items or []):
            flat.append((f"{source}:{i}", ev))
    return flat


def _evidence_brief(evidences: Dict[str, List[Evidence]], max_items: int = 10) -> str:
    flat = _flatten_evidence(evidences)[:max_items]
    lines: List[str] = []
    for ev_id, ev in flat:
        status = "FOUND" if ev.found else "FAIL"
        conf = float(ev.confidence or 0.0)
        goal = (ev.goal or "")[:80]
        loc = (ev.location or "")[:80]
        lines.append(f"- {ev_id} | {status} | {goal} | {loc} | {conf:.2f}")
    return "\n".join(lines) if lines else "No evidence provided."


def _choose_citations(evidences: Dict[str, List[Evidence]], limit: int = 3) -> List[str]:
    flat = _flatten_evidence(evidences)

    negatives = [(eid, ev) for eid, ev in flat if not ev.found]
    positives = [(eid, ev) for eid, ev in flat if ev.found]

    negatives.sort(key=lambda x: float(x[1].confidence or 0.0), reverse=True)
    positives.sort(key=lambda x: float(x[1].confidence or 0.0), reverse=True)

    chosen = [eid for eid, _ in negatives[:limit]]
    if len(chosen) < limit:
        chosen += [eid for eid, _ in positives[: (limit - len(chosen))]]

    return chosen


# ----------------------------
# AUTO LLM + AUTO FALLBACK
# ----------------------------

def _llm_available() -> bool:
    """
    Auto-mode:
    - If GROQ_API_KEY exists -> use LLM.
    - If user explicitly sets LLM_MODE=fallback -> force fallback.
    """
    mode = os.getenv("LLM_MODE", "").lower().strip()
    if mode == "fallback":
        return False
    return bool(os.getenv("GROQ_API_KEY", "").strip())


def _get_llm():
    from langchain_groq import ChatGroq  # type: ignore

    model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    temperature = float(os.getenv("JUDGE_TEMPERATURE", "0.2"))
    return ChatGroq(model=model, temperature=temperature)


def _judge_prompt(judge: JudgeName, criterion: Dict[str, Any], evidence_text: str) -> str:
    cid = criterion.get("id", "unknown")
    cname = criterion.get("name", cid)

    instr = criterion.get("forensic_instruction") or criterion.get("description") or ""
    logic = criterion.get("judicial_logic") or {}
    judge_logic = logic.get(judge.lower()) or logic.get(judge) or ""

    persona = {
        "Prosecutor": (
            "You are the Prosecutor. Be skeptical and strict. "
            "Penalize missing requirements, security issues, vague or unverified claims."
        ),
        "Defense": (
            "You are the Defense. Be fair and generous. "
            "Give credit for partial implementations and strong intent. "
            "If something is missing, explain exactly what to add."
        ),
        "TechLead": (
            "You are the Tech Lead. Be practical and engineering-focused. "
            "Prioritize correctness, maintainability, safety, and reproducibility."
        ),
    }[judge]

    rules = (
        "Scoring: integer 1..5\n"
        "1 = fails/no evidence\n"
        "2 = weak / major gaps\n"
        "3 = acceptable / partial\n"
        "4 = strong\n"
        "5 = excellent\n\n"
        "Hard rules:\n"
        "- Use ONLY evidence provided.\n"
        "- Do NOT invent files, APIs, or features.\n"
        "- cited_evidence must be IDs like repo_detective:0 or doc_detective:2\n"
        "- argument must be short (2–5 sentences) and grounded.\n"
    )

    return f"""
{persona}

Criterion:
- id: {cid}
- name: {cname}

Forensic instruction:
{instr}

Judge-specific logic:
{judge_logic}

Evidence (subset):
{evidence_text}

{rules}

Return a JudicialOpinion JSON with:
judge="{judge}"
criterion_id="{cid}"
score=1..5
argument="..."
cited_evidence=[...]
""".strip()


def _deterministic_fallback_for_one(
    judge: JudgeName,
    criterion_id: str,
    evidences: Dict[str, List[Evidence]],
    reason: str,
) -> JudicialOpinion:
    total = sum(len(v or []) for v in (evidences or {}).values())
    has_fail = any((not ev.found) for _, ev in _flatten_evidence(evidences))

    score = 3
    if total == 0:
        score = 1
    elif has_fail and judge == "Prosecutor":
        score = 2
    elif not has_fail and judge == "Defense":
        score = 4

    return JudicialOpinion(
        judge=judge,
        criterion_id=criterion_id,
        score=score,
        argument=reason,
        cited_evidence=_choose_citations(evidences, limit=3),
    )


def _run_judge(judge: JudgeName, state: AgentState) -> Dict[str, Any]:
    time.sleep(float(os.getenv("JUDGE_PER_CRITERION_DELAY", "1.0")))

    evidences = state.get("evidences", {}) or {}
    criteria = _load_rubric()

    if not criteria:
        raise ValueError("rubric.json loaded but contains no dimensions/criteria.")

    # If LLM is not available (no key or forced fallback), deterministic mode
    if not _llm_available():
        opinions: List[JudicialOpinion] = []
        for c in criteria:
            opinions.append(
                _deterministic_fallback_for_one(
                    judge=judge,
                    criterion_id=c.get("id", "unknown"),
                    evidences=evidences,
                    reason="LLM disabled/unavailable. Used deterministic fallback.",
                )
            )
        return {"opinions": opinions}

    base_llm = _get_llm()
    structured_llm = base_llm.with_structured_output(JudicialOpinion)

    evidence_text = _evidence_brief(
        evidences, max_items=int(os.getenv("MAX_EVIDENCE_FOR_JUDGES", "6"))
    )

    try:
        from groq import RateLimitError, BadRequestError  # type: ignore
    except Exception:
        RateLimitError = Exception  # type: ignore
        BadRequestError = Exception  # type: ignore

    opinions: List[JudicialOpinion] = []

    # ✅ Auto-fallback if rate limiting keeps happening
    rate_limit_count = 0
    rate_limit_max = int(os.getenv("RATE_LIMIT_MAX", "2"))

    for c in criteria:
        cid = c.get("id", "unknown")

        # If we already hit too many rate limits, fallback for remaining criteria
        if rate_limit_count >= rate_limit_max:
            opinions.append(
                _deterministic_fallback_for_one(
                    judge=judge,
                    criterion_id=cid,
                    evidences=evidences,
                    reason="Too many rate limits. Auto-fallback for remaining criteria.",
                )
            )
            continue

        prompt = _judge_prompt(judge, c, evidence_text)

        try:
            opinion = structured_llm.invoke(prompt)
            opinion.judge = judge
            opinion.criterion_id = cid

        except RateLimitError:
            rate_limit_count += 1
            time.sleep(float(os.getenv("JUDGE_BACKOFF_SECONDS", "12")))
            opinion = _deterministic_fallback_for_one(
                judge=judge,
                criterion_id=cid,
                evidences=evidences,
                reason="Rate limit hit. Used deterministic fallback for this criterion.",
            )

        except (BadRequestError, ValidationError, ValueError, Exception) as e:
            opinion = _deterministic_fallback_for_one(
                judge=judge,
                criterion_id=cid,
                evidences=evidences,
                reason=f"Judge output failed ({type(e).__name__}). Used deterministic fallback.",
            )

        if not opinion.cited_evidence:
            opinion.cited_evidence = _choose_citations(evidences, limit=3)

        opinions.append(opinion)

    return {"opinions": opinions}


def prosecutor_judge(state: AgentState):
    return _run_judge("Prosecutor", state)


def defense_judge(state: AgentState):
    return _run_judge("Defense", state)


def techlead_judge(state: AgentState):
    # ✅ FIX: no trailing comma (no tuple!)
    return _run_judge("TechLead", state)