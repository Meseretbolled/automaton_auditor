import json
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional

from src.state import AgentState, AuditReport, CriterionResult, JudicialOpinion, Evidence


def _repo_root() -> Path:
    # repo root = same level as src/
    return Path(__file__).resolve().parents[2]


def _load_rubric_file(path: str = "rubric.json") -> Dict[str, Any]:
    rubric_path = _repo_root() / path
    if not rubric_path.exists():
        raise FileNotFoundError(f"Missing {rubric_path}. Create rubric.json in repo root.")
    with open(rubric_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_dimensions(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    dims = data.get("dimensions") or data.get("criteria") or []
    return dims if isinstance(dims, list) else []


def _load_synthesis_rules(data: Dict[str, Any]) -> Dict[str, Any]:
    rules = data.get("synthesis_rules") or {}
    return rules if isinstance(rules, dict) else {}


def _weight_map(dimensions: List[Dict[str, Any]]) -> Dict[str, float]:
    # rubric.json may not contain weights -> fallback to average in _compute_overall
    return {d.get("id", ""): float(d.get("weight", 0.0) or 0.0) for d in dimensions}


def _group_opinions(opinions: List[JudicialOpinion]) -> Dict[str, List[JudicialOpinion]]:
    grouped: Dict[str, List[JudicialOpinion]] = {}
    for op in opinions or []:
        grouped.setdefault(op.criterion_id, []).append(op)
    return grouped


def _flatten_evidence(evidences: Dict[str, List[Evidence]]) -> List[Tuple[str, Evidence]]:
    flat: List[Tuple[str, Evidence]] = []
    for source, items in (evidences or {}).items():
        for i, ev in enumerate(items or []):
            flat.append((f"{source}:{i}", ev))
    return flat


def _variance(scores: List[int]) -> int:
    return max(scores) - min(scores) if scores else 0


def _final_score_from_opinions(ops: List[JudicialOpinion]) -> Tuple[int, str]:
    scores = [int(o.score) for o in ops if o.score is not None]
    if not scores:
        return 1, "avg=0.00, var=0"

    avg = sum(scores) / len(scores)
    base = int(round(avg))
    var = _variance(scores)

    # mild skepticism boost if big disagreement and prosecutor very low
    judges = {o.judge: o for o in ops}
    prosecutor = judges.get("Prosecutor")
    if prosecutor and int(prosecutor.score) <= 2 and var >= 2:
        base = max(1, base - 1)

    return max(1, min(5, base)), f"avg={avg:.2f}, var={var}"


def _compute_overall(results: List[CriterionResult], weights: Dict[str, float]) -> int:
    if not results:
        return 1

    usable = [(r.final_score, float(weights.get(r.criterion_id, 0.0))) for r in results]
    usable = [(s, w) for (s, w) in usable if w > 0]

    if usable:
        weighted_sum = sum(s * w for s, w in usable)
        wsum = sum(w for _, w in usable)
        overall = int(round(weighted_sum / wsum))
    else:
        overall = int(round(sum(r.final_score for r in results) / len(results)))

    return max(1, min(5, overall))


# ----------------------------
# FIXED: strict security confirmation
# ----------------------------

def _security_flaw_confirmed(evidences: Dict[str, List[Evidence]]) -> bool:
    """
    Confirm ONLY when repo evidence explicitly says unsafe execution was DETECTED in code.
    Avoid triggering on documentation strings like 'no shell=True'.
    """
    for _, ev in _flatten_evidence(evidences):
        goal = (ev.goal or "").lower()
        if ev.found and "security scan" in goal and "unsafe execution detected" in goal:
            return True
    return False


def _fact_supremacy_penalty(criterion_id: str, evidences: Dict[str, List[Evidence]]) -> Optional[str]:
    """
    Implements 'fact_supremacy': if evidence FACTS show failure, override generous opinions.
    Returns a short penalty reason if applicable.
    """
    flat = _flatten_evidence(evidences)

    # Confirm unsafe only if the dedicated "unsafe execution detected" evidence exists
    if criterion_id in ("security_sandboxing", "forensic_accuracy_code"):
        for _, ev in flat:
            if ev.found and "unsafe execution detected" in (ev.goal or "").lower():
                return "Fact supremacy: unsafe execution evidence confirmed."

    # If graph/state evidence explicitly failed, cap the criterion
    if criterion_id in ("langgraph_architecture", "forensic_accuracy_code"):
        for _, ev in flat:
            g = (ev.goal or "").lower()
            if ("graph" in g or "state" in g) and (not ev.found):
                return "Fact supremacy: required graph/state evidence missing."

    return None


def chief_justice(state: AgentState):
    evidences: Dict[str, List[Evidence]] = state.get("evidences", {}) or {}
    opinions: List[JudicialOpinion] = state.get("opinions", []) or []

    rubric = _load_rubric_file()
    dimensions = _load_dimensions(rubric)
    rules = _load_synthesis_rules(rubric)
    weights = _weight_map(dimensions)

    grouped = _group_opinions(opinions)

    results: List[CriterionResult] = []
    key_risks: List[str] = []
    next_steps: List[str] = []

    for d in dimensions:
        cid = d.get("id", "unknown")
        ops = grouped.get(cid, [])

        if not ops:
            results.append(
                CriterionResult(
                    criterion_id=cid,
                    final_score=1,
                    summary="No judge opinions produced for this criterion.",
                    strengths=[],
                    weaknesses=["Missing judge evaluation output."],
                    remediation=["Ensure each judge produces an opinion for every rubric criterion."],
                    dissent=None,
                )
            )
            key_risks.append(f"Missing judge output for {cid}.")
            continue

        final_score, meta = _final_score_from_opinions(ops)
        scores = [int(o.score) for o in ops if o.score is not None]

        strengths: List[str] = []
        weaknesses: List[str] = []
        for o in ops:
            txt = (o.argument or "").strip()
            if int(o.score) >= 4:
                strengths.append(f"{o.judge}: {txt[:180]}")
            elif int(o.score) <= 2:
                weaknesses.append(f"{o.judge}: {txt[:180]}")

        dissent: Optional[str] = None
        if _variance(scores) >= 2:
            # satisfy dissent_requirement (prosecutor vs defense)
            p = next((o for o in ops if o.judge == "Prosecutor"), None)
            de = next((o for o in ops if o.judge == "Defense"), None)
            if p and de:
                dissent = (
                    f"Prosecutor scored {p.score}/5 emphasizing: {p.argument[:140]}. "
                    f"Defense scored {de.score}/5 emphasizing: {de.argument[:140]}."
                )
            else:
                dissent = "High disagreement between judges. Review evidence grounding."
            next_steps.append(f"Resolve dissent in {cid}: tighten evidence grounding & judge prompts.")

        # Fact supremacy override (facts > opinions)
        if str(rules.get("fact_supremacy", "")).strip():
            penalty_reason = _fact_supremacy_penalty(cid, evidences)
            if penalty_reason:
                final_score = max(1, min(final_score, 2))
                weaknesses.append(penalty_reason)

        if final_score <= 3:
            next_steps.append(f"Improve {cid}: add stronger citations + clearer cross-references (repo <-> report).")

        results.append(
            CriterionResult(
                criterion_id=cid,
                final_score=final_score,
                summary=f"Chief Justice synthesis ({meta}).",
                strengths=strengths[:3],
                weaknesses=weaknesses[:3],
                remediation=[
                    "Address judge weaknesses and add stronger evidence citations.",
                    "Ensure report claims match repo implementation.",
                ],
                dissent=dissent,
            )
        )

    overall = _compute_overall(results, weights)

    # Apply security override if confirmed (STRICT now)
    security_override = str(rules.get("security_override", "")).lower()
    if _security_flaw_confirmed(evidences):
        key_risks.append("Security red flag detected (unsafe system execution).")
        next_steps.append("Fix unsafe execution: remove os.system / shell=True, use safe subprocess calls.")
        if "cap" in security_override and "3" in security_override:
            overall = min(overall, 3)
        else:
            overall = max(1, overall - 1)

    # de-dup next steps while preserving order
    seen = set()
    next_steps_unique: List[str] = []
    for s in next_steps:
        if s not in seen:
            seen.add(s)
            next_steps_unique.append(s)

    exec_summary = (
        f"Final audit complete. Overall score={overall}/5. "
        f"Criteria evaluated={len(results)}. "
        f"Judicial opinions received={len(opinions)}."
    )

    report = AuditReport(
        overall_score=overall,
        executive_summary=exec_summary,
        criteria=results,
        key_risks=key_risks[:8],
        next_steps=next_steps_unique[:8] if next_steps_unique else [
            "Review dissent areas (if any) and tighten evidence grounding.",
            "Add missing rubric coverage if any criterion has score=1.",
        ],
    )

    return {"final_report": report}