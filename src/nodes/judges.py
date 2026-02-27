import json
import os
import time
from typing import Dict, List, Tuple

from pydantic import ValidationError

from src.state import AgentState, Evidence, JudicialOpinion, JudgeName


def _load_rubric(path: str = "rubric.json") -> List[Dict]:
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"Missing {path}. Create it in the repo root (same level as src/)."
        )
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("criteria", [])


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
        lines.append(f"- {ev_id} | {status} | {ev.goal} | {ev.location} | {ev.confidence:.2f}")

    return "\n".join(lines) if lines else "No evidence provided."


def _choose_citations(evidences: Dict[str, List[Evidence]], limit: int = 3) -> List[str]:
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
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in model output.")
    return text[start : end + 1]


def _llm_available() -> bool:
    if os.getenv("LLM_MODE", "").lower().strip() == "fallback":
        return False
    return bool(os.getenv("GROQ_API_KEY", "").strip())


def _get_llm():
    from langchain_groq import ChatGroq  # type: ignore

    model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    temperature = float(os.getenv("JUDGE_TEMPERATURE", "0.2"))
    return ChatGroq(model=model, temperature=temperature)


def _judge_prompt(judge: JudgeName, criterion: Dict, evidence_text: str) -> str:
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


def _run_judge(judge: JudgeName, state: AgentState) -> Dict:
    evidences = state.get("evidences", {})
    criteria = _load_rubric()

    if not criteria:
        raise ValueError("rubric.json loaded but contains no 'criteria'.")

    if not _llm_available():
        opinions: List[JudicialOpinion] = []
        for c in criteria:
            opinions.append(
                _deterministic_fallback_for_one(
                    judge=judge,
                    criterion_id=c["id"],
                    evidences=evidences,
                    reason="LLM disabled/unavailable. Used deterministic fallback.",
                )
            )
        return {"opinions": opinions}

    llm = _get_llm()
    evidence_text = _evidence_brief(evidences, max_items=int(os.getenv("MAX_EVIDENCE_FOR_JUDGES", "8")))

    try:
        from groq import RateLimitError, BadRequestError  # type: ignore
    except Exception:
        RateLimitError = Exception  # type: ignore
        BadRequestError = Exception  # type: ignore

    opinions: List[JudicialOpinion] = []

    for c in criteria:
        cid = c["id"]
        prompt = _judge_prompt(judge, c, evidence_text)

        try:
            raw = llm.invoke(prompt)
            text = getattr(raw, "content", str(raw))

            json_str = _extract_json(text)
            data = json.loads(json_str)

            cited_clean: List[str] = []
            for item in data.get("cited_evidence", []):
                s = str(item).strip().replace("[", "").replace("]", "")
                cited_clean.append(s)
            data["cited_evidence"] = cited_clean

            opinion = JudicialOpinion(**data)

        except RateLimitError:
            time.sleep(float(os.getenv("JUDGE_BACKOFF_SECONDS", "6")))
            opinion = _deterministic_fallback_for_one(
                judge=judge,
                criterion_id=cid,
                evidences=evidences,
                reason="Rate limit hit. Used deterministic fallback for this criterion.",
            )

        except (BadRequestError, json.JSONDecodeError, ValidationError, ValueError, Exception) as e:
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
