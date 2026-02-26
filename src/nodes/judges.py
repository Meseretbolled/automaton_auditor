import json
import os
import re
import time
from typing import Dict, List, Tuple

from pydantic import ValidationError

from src.state import AgentState, Evidence, JudicialOpinion, JudgeName


# ----------------------------
# Helpers
# ----------------------------

def _load_rubric(path: str = "rubric.json") -> List[Dict]:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Missing {path}. Create it in the repo root (same level as src/)."
        )
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("criteria", [])


def _flatten_evidence(evidences: Dict[str, List[Evidence]]) -> List[Tuple[str, Evidence]]:
    """Return list of (evidence_id, Evidence) where evidence_id is like 'repo_detective:0'."""
    flat: List[Tuple[str, Evidence]] = []
    for source, items in evidences.items():
        for i, ev in enumerate(items):
            flat.append((f"{source}:{i}", ev))
    return flat


def _evidence_brief(evidences: Dict[str, List[Evidence]], max_items: int = 10) -> str:
    """Create a compact text summary of evidence for the judge prompt."""
    flat = _flatten_evidence(evidences)[:max_items]

    lines: List[str] = []
    for ev_id, ev in flat:
        status = "FOUND" if ev.found else "FAIL"
        # Keep it short to reduce token usage
        lines.append(f"- {ev_id} | {status} | {ev.goal} | {ev.location} | {ev.confidence:.2f}")

    return "\n".join(lines) if lines else "No evidence provided."


def _choose_citations(evidences: Dict[str, List[Evidence]], limit: int = 3) -> List[str]:
    """
    Choose evidence IDs to cite. Prefer negative evidence (found=False), then highest confidence.
    Returns IDs like repo_detective:0 (no brackets).
    """
    flat = _flatten_evidence(evidences)

    negatives = [(eid, ev) for eid, ev in flat if not ev.found]
    positives = [(eid, ev) for eid, ev in flat if ev.found]

    negatives.sort(key=lambda x: x[1].confidence, reverse=True)
    positives.sort(key=lambda x: x[1].confidence, reverse=True)

    chosen = [eid for eid, _ in negatives[:limit]]
    if len(chosen) < limit:
        chosen += [eid for eid, _ in positives[: (limit - len(chosen))]]

    return chosen


def _extract_json(text: str) -> str:
    """
    Extract the first JSON object from text.
    Robust against extra words before/after JSON.
    """
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model output.")
    return text[start:end + 1]


def _llm_available() -> bool:
    return bool(os.getenv("GROQ_API_KEY", "").strip())


def _get_llm():
    from langchain_groq import ChatGroq  # type: ignore

    model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    temperature = float(os.getenv("JUDGE_TEMPERATURE", "0.2"))

    return ChatGroq(model=model, temperature=temperature)


def _judge_prompt(judge: JudgeName, criterion: Dict, evidence_text: str) -> str:
    """Different personas: Prosecutor (strict), Defense (generous), TechLead (practical)."""
    cid = criterion["id"]
    cname = criterion.get("name", cid)
    cdesc = criterion.get("description", "")

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
        "- cited_evidence must be IDs like repo_detective:0 or doc_detective:2 (NO brackets).\n"
        "- Return ONLY JSON. No markdown, no code fences, no extra text."
    )

    # IMPORTANT: keep JSON braces as plain text, only insert values with {judge} and {cid}
    return f"""
{persona}

Criterion:
- id: {cid}
- name: {cname}
- description: {cdesc}

Evidence (subset):
{evidence_text}

{scoring_rules}

Return ONLY a valid JSON object (no extra text):
{{"judge":"{judge}","criterion_id":"{cid}","score":1,"argument":"...","cited_evidence":["repo_detective:0"]}}
""".strip()


def _deterministic_fallback(
    judge: JudgeName,
    criteria: List[Dict],
    evidences: Dict[str, List[Evidence]],
) -> List[JudicialOpinion]:
    """If no API key, still return structured opinions so the pipeline runs."""
    total = sum(len(v) for v in evidences.values())
    has_fail = any((not ev.found) for _, ev in _flatten_evidence(evidences))

    base = 3
    if total == 0:
        base = 1
    elif has_fail and judge == "Prosecutor":
        base = 2
    elif not has_fail and judge == "Defense":
        base = 4

    cites = _choose_citations(evidences, limit=3)

    opinions: List[JudicialOpinion] = []
    for c in criteria:
        opinions.append(
            JudicialOpinion(
                judge=judge,
                criterion_id=c["id"],
                score=base,
                argument=(
                    f"(Fallback) Evidence_count={total}, has_failures={has_fail}. "
                    "Replace with LLM judging for final submission."
                ),
                cited_evidence=cites,
            )
        )
    return opinions


def _run_judge(judge: JudgeName, state: AgentState) -> Dict:
    evidences = state.get("evidences", {})
    criteria = _load_rubric()

    if not criteria:
        raise ValueError("rubric.json loaded but contains no 'criteria'.")

    if not _llm_available():
        opinions = _deterministic_fallback(judge, criteria, evidences)
        return {"opinions": opinions}

    llm = _get_llm()

    evidence_text = _evidence_brief(
        evidences,
        max_items=int(os.getenv("MAX_EVIDENCE_FOR_JUDGES", "6")),
    )

    retries = int(os.getenv("GROQ_RETRIES", "3"))
    retry_sleep = float(os.getenv("GROQ_RETRY_SLEEP", "6"))

    opinions: List[JudicialOpinion] = []

    for criterion in criteria:
        prompt = _judge_prompt(judge, criterion, evidence_text)

        # Retry on rate limit
        raw = None
        last_err = None

        for _ in range(retries):
            try:
                raw = llm.invoke(prompt)
                last_err = None
                break
            except Exception as e:
                last_err = e
                msg = str(e).lower()
                if "rate limit" in msg or "429" in msg:
                    time.sleep(retry_sleep)
                    continue
                break

        # Still failed -> safe fallback per-criterion (NO CRASH)
        if raw is None:
            opinions.append(
                JudicialOpinion(
                    judge=judge,
                    criterion_id=criterion["id"],
                    score=2,
                    argument=f"Groq call failed (likely rate limit). Used safe fallback. Error={type(last_err).__name__}",
                    cited_evidence=_choose_citations(evidences, limit=3),
                )
            )
            continue

        text = getattr(raw, "content", str(raw))

        try:
            json_str = _extract_json(text)
            data = json.loads(json_str)

            # Normalize citations: remove accidental brackets
            cited: List[str] = []
            for item in data.get("cited_evidence", []):
                s = str(item).strip()
                s = s.replace("[", "").replace("]", "")
                cited.append(s)

            data["cited_evidence"] = cited

            opinion = JudicialOpinion(**data)

        except (json.JSONDecodeError, ValidationError, ValueError) as e:
            opinion = JudicialOpinion(
                judge=judge,
                criterion_id=criterion["id"],
                score=2,
                argument=f"Judge output parsing failed; used safe fallback. Error={type(e).__name__}",
                cited_evidence=_choose_citations(evidences, limit=3),
            )

        if not opinion.cited_evidence:
            opinion.cited_evidence = _choose_citations(evidences, limit=3)

        opinions.append(opinion)

    return {"opinions": opinions}


# ----------------------------
# LangGraph Nodes
# ----------------------------

def prosecutor_judge(state: AgentState):
    return _run_judge("Prosecutor", state)


def defense_judge(state: AgentState):
    return _run_judge("Defense", state)


def techlead_judge(state: AgentState):
    return _run_judge("TechLead", state)