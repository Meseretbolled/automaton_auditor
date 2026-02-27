from __future__ import annotations

from typing import Dict, List, Optional

from src.state import AgentState, Evidence
from src.tools.repo_tools import clone_repo_sandboxed, verify_graph_forensics
from src.tools.doc_tools import PDFForensicInterface


# ----------------------------
# Small helpers (judge-friendly)
# ----------------------------

def _clip(text: Optional[str], n: int = 240) -> Optional[str]:
    """Keep snippets short to avoid token bloat."""
    if not text:
        return text
    text = " ".join(text.split())
    return text[:n] + ("..." if len(text) > n else "")


def _best_per_concept(findings: List[Dict]) -> List[Dict]:
    """
    Deduplicate doc findings: keep the highest-confidence item per concept.
    This prevents 'LangGraph found in chunk 3 and chunk 5' looking inconsistent.
    """
    best: Dict[str, Dict] = {}
    for f in findings:
        concept = str(f.get("concept", "")).strip()
        conf = float(f.get("confidence", 0.0))
        if not concept:
            continue
        if concept not in best or conf > float(best[concept].get("confidence", 0.0)):
            best[concept] = f
    return list(best.values())


# ----------------------------
# Detectives
# ----------------------------

def repo_investigator(state: AgentState):
    path, temp_dir = clone_repo_sandboxed(state["repo_url"])

    if not path:
        fail_evidence = Evidence(
            goal="Repository Clone Check",
            found=False,
            content=None,
            location="Remote Repo",
            rationale="Repository cloning failed (authentication issue, invalid URL, or network error).",
            confidence=0.0,
        )
        return {"evidences": {"repo_detective": [fail_evidence]}}

    results = verify_graph_forensics(path)
    all_evidence: List[Evidence] = []

    # --- 1) Architecture Proof (give judges a compact, explicit summary) ---
    parallel = bool(results.get("parallel"))
    typed_state = bool(results.get("typed_state"))
    verified = bool(results.get("verified"))
    audited_file = results.get("file_audited", "src/graph.py + src/state.py")
    reason = str(results.get("reason", "N/A"))

    # If your verifier provides extra details, include them if available.
    # (Safe get: won't break if keys are missing.)
    start_fanout = results.get("start_fanout")  # e.g. ["repo_detective", "doc_detective"]
    judge_fanout = results.get("judge_fanout")  # e.g. ["prosecutor", "defense", "techlead"]
    reducers = results.get("reducers")          # e.g. {"evidences":"operator.ior", "opinions":"operator.add"}

    content_lines = [
        f"verified={verified}",
        f"parallel={parallel}",
        f"typed_state={typed_state}",
    ]
    if isinstance(start_fanout, list) and start_fanout:
        content_lines.append(f"START fan-out -> {', '.join(start_fanout)}")
    if isinstance(judge_fanout, list) and judge_fanout:
        content_lines.append(f"Judges fan-out -> {', '.join(judge_fanout)}")
    if isinstance(reducers, dict) and reducers:
        content_lines.append(f"Reducers -> {reducers}")

    architecture_evidence = Evidence(
        goal="Repo Forensics: LangGraph fan-out/fan-in + Typed State reducers",
        found=verified,
        content=_clip(" | ".join(content_lines), 320),
        location=audited_file,
        rationale=_clip(f"AST verification summary: {reason}", 260) or "AST verification summary produced.",
        confidence=1.0 if verified else 0.65,
    )
    all_evidence.append(architecture_evidence)

    # --- 2) Security Proof (keep it crisp and actionable) ---
    unsafe_files = results.get("unsafe_files", []) or []
    if unsafe_files:
        security_evidence = Evidence(
            goal="Security Scan: Unsafe System Calls",
            found=True,
            content=_clip("Examples: " + ", ".join(unsafe_files[:3]), 240),
            location=", ".join(unsafe_files[:3]),
            rationale=f"Detected unsafe call patterns in {len(unsafe_files)} file(s). Replace os.system/subprocess(shell=True) with safe APIs.",
            confidence=0.9,
        )
    else:
        security_evidence = Evidence(
            goal="Security Scan: Unsafe System Calls",
            found=False,
            content="No unsafe execution patterns found (os.system / shell=True).",
            location="Repository Scan",
            rationale="Static scan did not detect unsafe execution patterns in Python files.",
            confidence=0.9,
        )
    all_evidence.append(security_evidence)

    if temp_dir:
        temp_dir.cleanup()

    return {"evidences": {"repo_detective": all_evidence}}


def doc_analyst(state: AgentState):
    interface = PDFForensicInterface(state["pdf_path"])
    all_evidence: List[Evidence] = []

    if interface.ingest_and_chunk():
        target_concepts = ["LangGraph", "Parallelism", "Reducers", "AST"]
        findings = interface.targeted_search(target_concepts) or []

        if not findings:
            all_evidence.append(
                Evidence(
                    goal="Documentation Theory Verification",
                    found=False,
                    content=None,
                    location=state["pdf_path"],
                    rationale="PDF ingestion succeeded, but no strong matches were found for key architectural concepts.",
                    confidence=0.7,
                )
            )
        else:
            # ✅ Keep only the best evidence per concept to avoid 'inconsistency' complaints.
            deduped = _best_per_concept(findings)

            for f in deduped:
                concept = f.get("concept")
                chunk_id = f.get("chunk_id")
                snippet = _clip(f.get("snippet"), 280)

                all_evidence.append(
                    Evidence(
                        goal=f"Doc Proof: {concept}",
                        found=True,
                        content=snippet,
                        location=f"Chunk {chunk_id}",
                        rationale=f"Matched '{concept}' with high-confidence snippet from the report.",
                        confidence=float(f.get("confidence", 0.8)),
                    )
                )
    else:
        all_evidence.append(
            Evidence(
                goal="Documentation Ingestion Check",
                found=False,
                content=None,
                location=state["pdf_path"],
                rationale="PDF ingestion failed — document could not be parsed or loaded.",
                confidence=0.0,
            )
        )

    return {"evidences": {"doc_detective": all_evidence}}