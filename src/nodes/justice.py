import json
import os
from typing import Dict, List, Tuple

from src.state import AgentState, AuditReport, CriterionResult, JudicialOpinion, Evidence


def _load_rubric(path: str = "rubric.json") -> List[Dict]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Missing {path}. Create it in repo root.")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data.get("criteria", [])


def _weight_map(criteria: List[Dict]) -> Dict[str, float]:
    return {c["id"]: float(c.get("weight", 0.0)) for c in criteria}


def _group_opinions(opinions: List[JudicialOpinion]) -> Dict[str, List[JudicialOpinion]]:
    grouped: Dict[str, List[JudicialOpinion]] = {}
    for op in opinions:
        grouped.setdefault(op.criterion_id, []).append(op)
    return grouped


def _flatten_evidence(evidences: Dict[str, List[Evidence]]) -> List[Tuple[str, Evidence]]:
    flat = []
    for source, items in evidences.items():
        for i, ev in enumerate(items):
            flat.append((f"{source}:{i}", ev))
    return flat


def _detect_security_red_flag(evidences: Dict[str, List[Evidence]]) -> bool:
    """
    Simple deterministic override:
    if any evidence goal mentions unsafe/system call and found=True => security red flag.
    """
    for _, ev in _flatten_evidence(evidences):
        goal = (ev.goal or "").lower()
        if "security" in goal and "unsafe" in goal and ev.found:
            return True
    return False


def _variance(scores: List[int]) -> int:
    if not scores:
        return 0
    return max(scores) - min(scores)


def _final_score_from_opinions(ops: List[JudicialOpinion]) -> Tuple[int, str]:
    """
    Deterministic synthesis:
    - Base score: rounded average
    - If Prosecutor exists and gave <=2 and variance high, lean conservative.
    """
    scores = [o.score for o in ops]
    avg = sum(scores) / len(scores)
    base = int(round(avg))

    var = _variance(scores)

    judges = {o.judge: o for o in ops}
    prosecutor = judges.get("Prosecutor")
    if prosecutor and prosecutor.score <= 2 and var >= 2:
        base = max(1, base - 1)

    return max(1, min(5, base)), f"avg={avg:.2f}, var={var}"


def chief_justice(state: AgentState):
    """
    Chief Justice (Deterministic):
    - Groups opinions per criterion
    - Produces CriterionResult list
    - Applies simple override rules (security red flag lowers overall)
    - Writes a markdown report to reports/audit_report.md
    """

    evidences = state.get("evidences", {})
    opinions = state.get("opinions", [])

    criteria = _load_rubric()
    weights = _weight_map(criteria)

    grouped = _group_opinions(opinions)

    results: List[CriterionResult] = []
    key_risks: List[str] = []
    next_steps: List[str] = []

    for c in criteria:
        cid = c["id"]
        ops = grouped.get(cid, [])

        if not ops:
            # If no judge opinions exist for this criterion, mark as weak
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

        # Dissent if high variance between judges
        scores = [o.score for o in ops]
        dissent = None
        if _variance(scores) >= 2:
            dissent = "High disagreement between judges. Review evidence grounding and judge prompts."

        # Summarize strengths/weaknesses from arguments (lightweight)
        strengths = []
        weaknesses = []
        for o in ops:
            txt = o.argument.strip()
            if o.score >= 4:
                strengths.append(f"{o.judge}: {txt[:120]}")
            elif o.score <= 2:
                weaknesses.append(f"{o.judge}: {txt[:120]}")

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

    # Weighted overall score
    if results:
        weighted = 0.0
        weight_sum = 0.0
        for r in results:
            w = float(weights.get(r.criterion_id, 0.0))
            weighted += r.final_score * w
            weight_sum += w
        overall = int(round(weighted / weight_sum)) if weight_sum > 0 else int(round(sum(r.final_score for r in results) / len(results)))
    else:
        overall = 1

    # Security override (deterministic)
    if _detect_security_red_flag(evidences):
        overall = min(overall, 2)
        key_risks.append("Security red flag detected (unsafe system execution).")

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
        next_steps=next_steps[:8] if next_steps else [
            "Review dissent areas (if any) and tighten evidence grounding.",
            "Add missing rubric coverage if any criterion has score=1.",
            "Generate LangSmith trace link for submission proof."
        ],
    )

    # Write markdown output
    os.makedirs("reports", exist_ok=True)
    out_path = os.path.join("reports", "audit_report.md")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"# Automaton Auditor — Final Audit Report\n\n")
        f.write(f"**Overall score:** {report.overall_score}/5\n\n")
        f.write(f"## Executive Summary\n\n{report.executive_summary}\n\n")
        f.write("## Criteria Results\n\n")
        for cr in report.criteria:
            f.write(f"### {cr.criterion_id} — {cr.final_score}/5\n\n")
            f.write(f"{cr.summary}\n\n")
            if cr.strengths:
                f.write("**Strengths**\n")
                for s in cr.strengths:
                    f.write(f"- {s}\n")
                f.write("\n")
            if cr.weaknesses:
                f.write("**Weaknesses**\n")
                for w in cr.weaknesses:
                    f.write(f"- {w}\n")
                f.write("\n")
            if cr.remediation:
                f.write("**Remediation**\n")
                for r in cr.remediation:
                    f.write(f"- {r}\n")
                f.write("\n")
            if cr.dissent:
                f.write(f"**Dissent:** {cr.dissent}\n\n")

        if report.key_risks:
            f.write("## Key Risks\n")
            for k in report.key_risks:
                f.write(f"- {k}\n")
            f.write("\n")

        if report.next_steps:
            f.write("## Next Steps\n")
            for n in report.next_steps:
                f.write(f"- {n}\n")
            f.write("\n")

    return {"final_report": report}