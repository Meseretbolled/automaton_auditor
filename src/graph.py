from langgraph.graph import StateGraph, START, END

from src.state import AgentState
from src.nodes.detectives import repo_investigator, doc_analyst
from src.nodes.judges import prosecutor_judge, defense_judge, techlead_judge
from src.nodes.justice import chief_justice


def evidence_aggregator(state: AgentState):
    """
    Optional explicit fan-in node.
    Reducers already merge evidences, so this node just passes through.
    It exists to make the graph structure (fan-in) visible in LangSmith.
    """
    return {}


def opinion_aggregator(state: AgentState):
    """
    Optional explicit fan-in node for judge opinions.
    Reducers already merge opinions, so this node just passes through.
    """
    return {}


builder = StateGraph(AgentState)

# -----------------------------
# Detectives
# -----------------------------
builder.add_node("repo_detective", repo_investigator)
builder.add_node("doc_detective", doc_analyst)
builder.add_node("evidence_aggregator", evidence_aggregator)

# Fan-out
builder.add_edge(START, "repo_detective")
builder.add_edge(START, "doc_detective")

# Fan-in
builder.add_edge("repo_detective", "evidence_aggregator")
builder.add_edge("doc_detective", "evidence_aggregator")

# -----------------------------
# Judges
# -----------------------------
builder.add_node("prosecutor", prosecutor_judge)
builder.add_node("defense", defense_judge)
builder.add_node("techlead", techlead_judge)
builder.add_node("opinion_aggregator", opinion_aggregator)

# Fan-out (Judges parallel)
builder.add_edge("evidence_aggregator", "prosecutor")
builder.add_edge("evidence_aggregator", "defense")
builder.add_edge("evidence_aggregator", "techlead")

# Fan-in (Opinions merge)
builder.add_edge("prosecutor", "opinion_aggregator")
builder.add_edge("defense", "opinion_aggregator")
builder.add_edge("techlead", "opinion_aggregator")

# -----------------------------
# Chief Justice
# -----------------------------
builder.add_node("chief_justice", chief_justice)
builder.add_edge("opinion_aggregator", "chief_justice")
builder.add_edge("chief_justice", END)

graph = builder.compile()