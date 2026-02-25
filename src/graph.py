from langgraph.graph import StateGraph, START, END
from src.state import AgentState
from src.nodes.detectives import repo_investigator, doc_analyst

builder = StateGraph(AgentState)
builder.add_node("repo_detective", repo_investigator)
builder.add_node("doc_detective", doc_analyst)

# Parallel Fan-out
builder.add_edge(START, "repo_detective")
builder.add_edge(START, "doc_detective")

builder.add_edge("repo_detective", END)
builder.add_edge("doc_detective", END)

graph = builder.compile()