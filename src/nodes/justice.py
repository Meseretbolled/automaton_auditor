import json
import os
from typing import Dict, List, Tuple, Any, Optional

from src.state import AgentState, AuditReport, CriterionResult, JudicialOpinion, Evidence


def _load_rubric_file(path: str = "rubric.json") -> Dict[str, Any]:
    if not os.path.exists(path):
        raise FileNotFoundError(f"Missing {path}. Create it in repo root.")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_dimensions(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    dims = data.get("dimensions") or data.get("criteria") or []
    return dims if isinstance(dims, list) else []


def _load_synthesis_rules(data: Dict[str, Any]) -> Dict[str, Any]:
    rules = data.get("synthesis_rules") or {}
    return rules if isinstance(rules, dict) else {}


def _weight_map(dimensions: List[Dict[str, Any]]) -> Dict[str, float]:
    return {d.get("id", ""): float(d.get("weight", 0.0)) for d in dimensions}


def _group_opinions(opinions: List[JudicialOpinion]) -> Dict[str, List[JudicialOpinion]]:
    grouped: Dict[str, List[JudicialOpinion]] = {}
    for op in opinions:
        grouped.setdefault(op.criterion_id, []).append(op)
    return grouped


def _flatten_evidence(evidences: Dict[str, List[Evidence]]) -> List[Tuple[str, Evidence]]:
    flat: List[Tuple[str, Evidence]] = []
    for source, items in evidences.items():
        for i, ev in enumerate(items):
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


def _security_flaw_confirmed(evidences: Dict[str, List[Evidence]]) -> bool:
    """
    Only treat it as a confirmed security flaw if an evidence item explicitly says unsafe calls were found.
    (This prevents false positives where the string 'shell=True' appears only in documentation text.)
    """
    for _, ev in _flatten_evidence(evidences):
        goal = (ev.goal or "").lower()
        txt = (ev.content or "").lower()
        if "security" in goal and "unsafe" in goal and bool(ev.found):
            return True
        # also accept an explicit unsafe-files list style content
        if "unsafe" in goal and bool(ev.found):
            return True
        if "unsafe" in txt and bool(ev.found):
            return True
    return False


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

        # Build strengths/weaknesses
        strengths: List[str] = []
        weaknesses: List[str] = []
        for o in ops:
            txt = (o.argument or "").strip()
            if int(o.score) >= 4:
                strengths.append(f"{o.judge}: {txt[:180]}")
            elif int(o.score) <= 2:
                weaknesses.append(f"{o.judge}: {txt[:180]}")

        dissent: Optional[str] = None
        var = _variance(scores)

        if var >= 2:
            # ✅ satisfy dissent_requirement: explain prosecutor vs defense difference
            p = next((o for o in ops if o.judge == "Prosecutor"), None)
            de = next((o for o in ops if o.judge == "Defense"), None)
            if p and de:
                dissent = (
                    f"Prosecutor scored {p.score}/5 emphasizing: {p.argument[:140]}. "
                    f"Defense scored {de.score}/5 emphasizing: {de.argument[:140]}."
                )
            else:
                dissent = "High disagreement between judges. Review evidence grounding and judge prompts."

            next_steps.append(f"Resolve dissent in {cid}: tighten evidence grounding & judge prompts.")

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
                    "Ensure report claims match repo implementation."
                ],
                dissent=dissent,
            )
        )

    overall = _compute_overall(results, weights)

    # ✅ Apply synthesis_rules.security_override if confirmed
    security_override = str(rules.get("security_override", "")).lower()
    if _security_flaw_confirmed(evidences):
        key_risks.append("Security red flag detected (unsafe system execution).")
        next_steps.append("Fix unsafe system execution: remove os.system / shell=True, use safe subprocess calls.")

        # If rule says "cap total score at 3", do that.
        if "cap" in security_override and "3" in security_override:
            overall = min(overall, 3)
        else:
            # fallback: mild penalty
            overall = max(1, overall - 1)

    # de-dup next_steps while preserving order
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
            "Generate LangSmith trace link for submission proof.",
        ],
    )

    # Write markdown output
    os.makedirs("reports", exist_ok=True)
    out_path = os.path.join("reports", "audit_report.md")

    with open(out_path, "w", encoding="utf-8") as f:
        f.write("# Automaton Auditor — Final Audit Report\n\n")
        f.write(f"**Overall score:** {report.overall_score}/5\n\n")
        f.write("## Executive Summary\n\n")
        f.write(f"{report.executive_summary}\n\n")
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