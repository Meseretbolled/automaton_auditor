from langgraph.graph import StateGraph, START, END
# Ensure you import your nodes and AgentState

def synthesizer_node(state: AgentState):
    """
    Aggregation Node: Consolidates evidence into a JudicialOpinion.
    This fulfills the requirement for a 'judicial layer' attachment point.
    """
    # Logic to calculate risk based on detective findings
    all_ev = state.get("evidences", {})
    count = sum(len(v) for v in all_ev.values())
    
    opinion = JudicialOpinion(
        verdict="Audit Complete",
        risk_score=5 if count > 0 else 0,
        summary=f"Swarm identified {count} evidence points across repo and docs."
    )
    return {"judicial_opinion": opinion}

def create_graph():
    workflow = StateGraph(AgentState)

    # 1. Add Nodes
    workflow.add_node("repo_detective", repo_detective_node)
    workflow.add_node("doc_detective", doc_detective_node)
    workflow.add_node("synthesizer", synthesizer_node) # The new Fan-in node

    # 2. Parallel Fan-out from START
    workflow.add_edge(START, "repo_detective")
    workflow.add_edge(START, "doc_detective")

    # 3. Fan-in to Aggregator (The Synthesis point)
    workflow.add_edge("repo_detective", "synthesizer")
    workflow.add_edge("doc_detective", "synthesizer")

    # 4. Final path
    workflow.add_edge("synthesizer", END)

    return workflow.compile()