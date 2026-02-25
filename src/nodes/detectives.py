from src.state import AgentState, Evidence
from src.tools.repo_tools import clone_repo_sandboxed, verify_graph_forensics
from src.tools.doc_tools import ingest_pdf, search_pdf_concepts

def repo_investigator(state: AgentState):
    path, temp_dir = clone_repo_sandboxed(state["repo_url"])
    result = verify_graph_forensics(path) if path else "Clone Failed"
    evidence = Evidence(goal="AST Parallelism Check", found="Verified" in result, 
                        location="src/graph.py", rationale=result, confidence=1.0)
    if temp_dir: temp_dir.cleanup()
    return {"evidences": {"repo_detective": [evidence]}}

def doc_analyst(state: AgentState):
    content = ingest_pdf(state["pdf_path"])
    analysis = search_pdf_concepts(content, ["LangGraph", "Reducers", "AST"])
    evidence = Evidence(goal="Theory Check", found=analysis["LangGraph"]["found"], 
                        location=state["pdf_path"], rationale=str(analysis), confidence=0.9)
    return {"evidences": {"doc_detective": [evidence]}}