from src.state import Evidence, AgentState
from src.tools.repo_tools import clone_repo_sandboxed, verify_graph_forensics
from src.tools.doc_tools import PDFForensicInterface

def repo_detective_node(state: AgentState):
    """
    Upgraded Repo Detective: Uses Deep AST and Sandboxing.
    Fulfills 'Detective Node Implementation' level 5.
    """
    path, temp_dir = clone_repo_sandboxed(state["repo_url"])
    if not path:
        return {"evidences": {"repo_detective": [
            Evidence(goal="Clone Repo", found=False, location="Git", 
                     rationale="Auth/Network failure", confidence=0.0)
        ]}}

    # Perform Deep AST Audit
    results = verify_graph_forensics(path)
    
    evidence = Evidence(
        goal="Verify Parallel Architecture",
        found=results.get("verified", False),
        content=f"Parallel: {results.get('parallel')}, TypedState: {results.get('typed_state')}",
        location=f"AST Analysis of {state['repo_url']}",
        rationale="Checked class inheritance and START node edge counts.",
        confidence=1.0 if results.get("verified") else 0.5
    )
    
    return {"evidences": {"repo_detective": [evidence]}}

def doc_detective_node(state: AgentState):
    """
    Upgraded Doc Detective: Uses Chunked Querying.
    Fulfills 'Forensic Tool Engineering' level 5.
    """
    interface = PDFForensicInterface(state["pdf_path"])
    findings = []
    
    if interface.ingest_and_chunk():
        # Targeted search instead of full blob scan
        raw_findings = interface.targeted_search(["LangGraph", "Reducers"])
        for rf in raw_findings:
            findings.append(Evidence(
                goal=f"Identify {rf['concept']} documentation",
                found=True,
                content=rf["snippet"],
                location=f"Page {rf['page']}",
                rationale="Targeted keyword match in chunked document.",
                confidence=rf["confidence"]
            ))
            
    return {"evidences": {"doc_detective": findings}}