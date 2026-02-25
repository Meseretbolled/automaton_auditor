from src.state import AgentState, Evidence
from src.tools.repo_tools import clone_repo_sandboxed, verify_graph_forensics
from src.tools.doc_tools import PDFForensicInterface

def repo_investigator(state: AgentState):
    """
    Upgraded Repo Detective: Performs deep AST auditing.
    """
    path, temp_dir = clone_repo_sandboxed(state["repo_url"])
    
    if not path:
        fail_evidence = Evidence(
            goal="AST Parallelism Check", 
            found=False, 
            location="Remote Repo", 
            rationale="Repository cloning failed (Auth/URL).", 
            confidence=0.0
        )
        return {"evidences": {"repo_detective": [fail_evidence]}}

    results = verify_graph_forensics(path)
    
    evidence = Evidence(
        goal="AST Parallelism Check", 
        found=results.get("verified", False), 
        location=results.get("file_audited", "src/graph.py"), 
        rationale=(
            f"Parallelism: {results.get('parallel')}. "
            f"TypedState: {results.get('typed_state')}. "
            f"Reason: {results.get('reason', 'N/A')}"
        ), 
        confidence=1.0 if results.get("verified") else 0.5
    )

    if temp_dir: 
        temp_dir.cleanup()
        
    return {"evidences": {"repo_detective": [evidence]}}

def doc_analyst(state: AgentState):
    """
    Upgraded Doc Detective: Uses semantic chunks and targeted querying.
    """
    interface = PDFForensicInterface(state["pdf_path"])
    all_evidence = []
    
    if interface.ingest_and_chunk():
        target_concepts = ["LangGraph", "Reducers", "AST"]
        findings = interface.targeted_search(target_concepts)
        
        for f in findings:
            all_evidence.append(Evidence(
                goal=f"Verify {f['concept']} in Documentation", 
                found=True, 
                content=f["snippet"],
                location=f"Chunk {f['chunk_id']}", 
                rationale=f"Targeted match found for {f['concept']}.", 
                confidence=f["confidence"]
            ))
    else:
        all_evidence.append(Evidence(
            goal="Documentation Theory Check",
            found=False,
            location=state["pdf_path"],
            rationale="PDF Ingestion failed.",
            confidence=0.0
        ))

    return {"evidences": {"doc_detective": all_evidence}}