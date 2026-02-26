from src.state import AgentState, Evidence
from src.tools.repo_tools import (
    clone_repo_sandboxed,
    verify_graph_forensics,
)
from src.tools.doc_tools import PDFForensicInterface


def repo_investigator(state: AgentState):
    path, temp_dir = clone_repo_sandboxed(state["repo_url"])

    if not path:
        fail_evidence = Evidence(
            goal="Repository Clone Check",
            found=False,
            location="Remote Repo",
            rationale="Repository cloning failed (authentication issue, invalid URL, or network error).",
            confidence=0.0
        )
        return {"evidences": {"repo_detective": [fail_evidence]}}

    results = verify_graph_forensics(path)
    all_evidence = []

    architecture_evidence = Evidence(
        goal="AST Structural Verification (Parallelism + Typed State)",
        found=results.get("verified", False),
        location=results.get("file_audited", "src/graph.py + src/state.py"),
        rationale=(
            f"Parallelism detected: {results.get('parallel')}. "
            f"Typed state with reducer detected: {results.get('typed_state')}. "
            f"Details: {results.get('reason', 'N/A')}"
        ),
        confidence=1.0 if results.get("verified") else 0.6
    )
    all_evidence.append(architecture_evidence)

    unsafe_files = results.get("unsafe_files", [])
    if unsafe_files:
        security_evidence = Evidence(
            goal="Security Scan: Unsafe System Calls",
            found=True,
            location=", ".join(unsafe_files[:3]),
            rationale=f"Detected unsafe call patterns (e.g., os.system) in {len(unsafe_files)} file(s).",
            confidence=0.9
        )
    else:
        security_evidence = Evidence(
            goal="Security Scan: Unsafe System Calls",
            found=False,
            location="Repository Scan",
            rationale="No unsafe execution patterns (e.g., os.system) detected in Python files.",
            confidence=0.9
        )
    all_evidence.append(security_evidence)

    if temp_dir:
        temp_dir.cleanup()

    return {"evidences": {"repo_detective": all_evidence}}


def doc_analyst(state: AgentState):
    interface = PDFForensicInterface(state["pdf_path"])
    all_evidence = []

    if interface.ingest_and_chunk():
        target_concepts = ["LangGraph", "Parallelism", "Reducers", "AST"]
        findings = interface.targeted_search(target_concepts)

        if not findings:
            all_evidence.append(Evidence(
                goal="Documentation Theory Verification",
                found=False,
                location=state["pdf_path"],
                rationale="PDF ingestion succeeded, but no strong matches were found for key architectural concepts.",
                confidence=0.7
            ))
        else:
            for f in findings:
                all_evidence.append(Evidence(
                    goal=f"Verify {f.get('concept')} in Documentation",
                    found=True,
                    content=f.get("snippet"),
                    location=f"Chunk {f.get('chunk_id')}",
                    rationale=f"Targeted conceptual match found for {f.get('concept')}.",
                    confidence=f.get("confidence", 0.8)
                ))
    else:
        all_evidence.append(Evidence(
            goal="Documentation Ingestion Check",
            found=False,
            location=state["pdf_path"],
            rationale="PDF ingestion failed — document could not be parsed or loaded.",
            confidence=0.0
        ))

    return {"evidences": {"doc_detective": all_evidence}}