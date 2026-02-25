from langgraph.graph import StateGraph, START, END
from src.state import AgentState, JudicialOpinion
from src.nodes.detectives import repo_investigator, doc_analyst

def synthesizer_node(state: AgentState):
    """
    The 'Judicial Layer' Aggregator.
    Consolidates parallel findings into a final JudicialOpinion.
    """
    all_evidences = state.get("evidences", {})
    
    # Simple logic: If we have findings, complete the audit
    total_findings = sum(len(evs) for evs in all_evidences.values())
    
    # Determine risk score based on 'found' flags
    risk = 2 # Default safe
    for source in all_evidences.values():
        if any(not e.found for e in source):
            risk += 3
            
    opinion = JudicialOpinion(
        verdict="Audit Complete" if total_findings > 0 else "Incomplete Evidence",
        summary=f"Swarm processed {total_findings} pieces of evidence.",
        risk_score=min(risk, 10)
    )
    
    return {"judicial_opinion": opinion}

builder = StateGraph(AgentState)

# 1. Add all nodes
builder.add_node("repo_detective", repo_investigator)
builder.add_node("doc_detective", doc_analyst)
builder.add_node("synthesizer", synthesizer_node) # The missing piece!

# 2. Parallel Fan-out from START
builder.add_edge(START, "repo_detective")
builder.add_edge(START, "doc_detective")

# 3. Fan-in (Collect results into the aggregator)
# Instead of going to END, they meet at the synthesizer
builder.add_edge("repo_detective", "synthesizer")
builder.add_edge("doc_detective", "synthesizer")

# 4. Finish the workflow
builder.add_edge("synthesizer", END)

graph = builder.compile()