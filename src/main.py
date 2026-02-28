import os
import json
import argparse
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv

from src.graph import graph


def _ensure_dirs() -> None:
    Path("audit/report_onself_generated").mkdir(parents=True, exist_ok=True)
    Path("audit/report_onpeer_generated").mkdir(parents=True, exist_ok=True)
    Path("audit/report_bypeer_received").mkdir(parents=True, exist_ok=True)


def _report_dir_for_mode(mode: str) -> Path:
    return Path("audit/report_onpeer_generated") if mode == "peer" else Path("audit/report_onself_generated")


def _safe_dump(obj: Any) -> Dict[str, Any]:
    if hasattr(obj, "model_dump"):
        return obj.model_dump()
    if isinstance(obj, dict):
        return obj
    return {"value": str(obj)}


def _to_markdown(report_dict: Dict[str, Any]) -> str:
    overall = report_dict.get("overall_score", "N/A")
    summary = report_dict.get("executive_summary", "")
    key_risks = report_dict.get("key_risks", []) or []
    next_steps = report_dict.get("next_steps", []) or []
    criteria = report_dict.get("criteria", []) or []

    lines = []
    lines.append("# Automaton Auditor — Audit Report\n\n")
    lines.append(f"**Overall Score:** {overall}/5\n\n")

    if summary:
        lines.append("## Executive Summary\n\n")
        lines.append(f"{summary}\n\n")

    lines.append("## Criteria Results\n\n")
    if not criteria:
        lines.append("- No criteria results found.\n")
    else:
        for c in criteria:
            cid = c.get("criterion_id", "unknown")
            score = c.get("final_score", "N/A")
            csum = c.get("summary", "")
            strengths = c.get("strengths", []) or []
            weaknesses = c.get("weaknesses", []) or []
            remediation = c.get("remediation", []) or []
            dissent = c.get("dissent")

            lines.append(f"### {cid}\n\n")
            lines.append(f"- **Score:** {score}/5\n")
            if csum:
                lines.append(f"- **Summary:** {csum}\n")

            if strengths:
                lines.append("\n**Strengths**\n")
                for s in strengths[:8]:
                    lines.append(f"- {s}\n")

            if weaknesses:
                lines.append("\n**Weaknesses**\n")
                for w in weaknesses[:8]:
                    lines.append(f"- {w}\n")

            if remediation:
                lines.append("\n**Remediation**\n")
                for r in remediation[:8]:
                    lines.append(f"- {r}\n")

            if dissent:
                lines.append(f"\n**Dissent:** {dissent}\n")

            lines.append("\n")

    lines.append("## Key Risks\n\n")
    if key_risks:
        for r in key_risks[:10]:
            lines.append(f"- {r}\n")
    else:
        lines.append("- None reported.\n")

    lines.append("\n## Next Steps\n\n")
    if next_steps:
        for n in next_steps[:10]:
            lines.append(f"- {n}\n")
    else:
        lines.append("- None reported.\n")

    return "".join(lines)


def write_audit_outputs(final_report_obj: Any, mode: str) -> Path:
    _ensure_dirs()
    out_dir = _report_dir_for_mode(mode)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"audit_report_{ts}"

    report_dict = _safe_dump(final_report_obj)

    json_path = out_dir / f"{base}.json"
    md_path = out_dir / f"{base}.md"

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report_dict, f, indent=2, ensure_ascii=False)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(_to_markdown(report_dict))

    return out_dir


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(description="Automaton Auditor - TRP1 Week 2")
    parser.add_argument("--repo", help="Repository URL to audit (overrides REPO_URL env)")
    parser.add_argument("--pdf", help="PDF path to audit (overrides PDF_PATH env)")
    parser.add_argument(
        "--mode",
        choices=["self", "peer"],
        default="self",
        help="Where to save outputs: self -> audit/report_onself_generated, peer -> audit/report_onpeer_generated",
    )
    args = parser.parse_args()

    repo_url = (args.repo or os.getenv("REPO_URL", "")).strip()
    pdf_path = (args.pdf or os.getenv("PDF_PATH", "")).strip()

    if not repo_url:
        raise ValueError("Missing repo URL. Provide --repo or set REPO_URL in your .env")
    if not pdf_path:
        raise ValueError("Missing PDF path. Provide --pdf or set PDF_PATH in your .env")

    initial_state = {
        "repo_url": repo_url,
        "pdf_path": pdf_path,
        "evidences": {},
        "opinions": [],
        "final_report": None,
    }

    result = graph.invoke(initial_state)
    final_report = result.get("final_report")

    if not final_report:
        print("\n No final_report produced. Check graph wiring.\n")
        return

    print("\n✅ FINAL REPORT\n")
    if hasattr(final_report, "model_dump_json"):
        print(final_report.model_dump_json(indent=2))
    else:
        print(json.dumps(_safe_dump(final_report), indent=2, ensure_ascii=False))

    out_dir = write_audit_outputs(final_report, mode=args.mode)
    print(f"\n Saved audit outputs to: {out_dir}\n")


if __name__ == "__main__":
    main()