import json
import os
import time
from typing import Dict, List, Tuple, Any

from pydantic import ValidationError

from src.state import AgentState, Evidence, JudicialOpinion, JudgeName


def _load_rubric(path: str = "rubric.json") -> List[Dict[str, Any]]:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Missing {path}. Create it in the repo root (same level as src/)."
        )
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # ✅ support both formats
    dims = data.get("dimensions") or data.get("criteria") or []
    if not isinstance(dims, list):
        return []
    return dims


def _flatten_evidence(evidences: Dict[str, List[Evidence]]) -> List[Tuple[str, Evidence]]:
    flat: List[Tuple[str, Evidence]] = []
    for source, items in evidences.items():
        for i, ev in enumerate(items):
            flat.append((f"{source}:{i}", ev))
    return flat


def _evidence_brief(evidences: Dict[str, List[Evidence]], max_items: int = 10) -> str:
    flat = _flatten_evidence(evidences)[:max_items]
    lines: List[str] = []
    for ev_id, ev in flat:
        status = "FOUND" if ev.found else "FAIL"
        conf = float(ev.confidence or 0.0)
        lines.append(f"- {ev_id} | {status} | {ev.goal} | {ev.location} | {conf:.2f}")
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


def _llm_available() -> bool:
    if os.getenv("LLM_MODE", "").lower().strip() == "fallback":
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

    # doc rubric uses forensic_instruction and judicial_logic
    instr = criterion.get("forensic_instruction") or criterion.get("description") or ""
    logic = (criterion.get("judicial_logic") or {})
    judge_logic = logic.get(judge.lower()) or logic.get(judge) or ""

    persona = {
        "Prosecutor": (
            "You are the Prosecutor. Be skeptical and strict. "
            "Assume corners were cut unless evidence proves otherwise. "
            "Penalize missing requirements, security issues, and vague claims."
        ),
        "Defense": (
            "You are the Defense. Be fair and generous. "
            "Give credit for partial implementations and clear intent. "
            "If evidence is incomplete, suggest what would complete it."
        ),
        "TechLead": (
            "You are the Tech Lead. Be practical and engineering-focused. "
            "Prioritize correctness, maintainability, and system design. "
            "Reward clean architecture and strong evidence."
        ),
    }[judge]

    scoring_rules = (
        "Score from 1 to 5:\n"
        "1 = fails/no evidence\n"
        "2 = weak / major gaps\n"
        "3 = acceptable / partial\n"
        "4 = strong\n"
        "5 = excellent / exemplary\n\n"
        "Rules:\n"
        "- Use ONLY the evidence provided.\n"
        "- Do NOT invent files or facts.\n"
        "- cited_evidence must be IDs like repo_detective:0 or doc_detective:2\n"
        "- Provide a short argument (2–5 sentences).\n"
    )

    return f"""
{persona}

Criterion:
- id: {cid}
- name: {cname}

Forensic instruction:
{instr}

Judge-specific logic to apply:
{judge_logic}

Evidence (subset):
{evidence_text}

{scoring_rules}

Return a JudicialOpinion with:
- judge = "{judge}"
- criterion_id = "{cid}"
- score = integer 1..5
- argument = your reasoning grounded in evidence
- cited_evidence = list of evidence IDs (e.g. ["repo_detective:0"])
""".strip()


def _deterministic_fallback_for_one(
    judge: JudgeName,
    criterion_id: str,
    evidences: Dict[str, List[Evidence]],
    reason: str,
) -> JudicialOpinion:
    total = sum(len(v) for v in evidences.values())
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
    time.sleep(float(os.getenv("JUDGE_PER_CRITERION_DELAY", "1.5")))

    evidences = state.get("evidences", {}) or {}
    criteria = _load_rubric()

    if not criteria:
        raise ValueError("rubric.json loaded but contains no dimensions/criteria.")

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
        evidences, max_items=int(os.getenv("MAX_EVIDENCE_FOR_JUDGES", "5"))
    )

    try:
        from groq import RateLimitError, BadRequestError  # type: ignore
    except Exception:
        RateLimitError = Exception  # type: ignore
        BadRequestError = Exception  # type: ignore

    opinions: List[JudicialOpinion] = []

    for c in criteria:
        cid = c.get("id", "unknown")
        prompt = _judge_prompt(judge, c, evidence_text)

        try:
            opinion = structured_llm.invoke(prompt)
            opinion.judge = judge
            opinion.criterion_id = cid

        except RateLimitError:
            time.sleep(float(os.getenv("JUDGE_BACKOFF_SECONDS", "6")))
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
    return _run_judge("TechLead", state)