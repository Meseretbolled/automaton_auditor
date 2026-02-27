🕵️ The Automaton Auditor — Week 2 Forensic Swarm
📌 Project Overview

The Automaton Auditor is a multi-agent forensic auditing system built with LangGraph.
It evaluates autonomous agent repositories using structured evidence, static analysis (AST), document analysis (OCR + semantic chunking), and a multi-judge reasoning layer.

Instead of simple keyword matching, the system performs:

📂 Static Code Verification (AST-based)

📄 Multimodal PDF Analysis (OCR + semantic chunking)

⚖️ Multi-Persona Judicial Evaluation

🧠 Deterministic Final Synthesis

The result is a structured, explainable audit report grounded in real repository and documentation evidence.


🧠 System Architecture

The Automaton Auditor follows a Fan-Out / Fan-In Swarm Pattern with typed state merging and structured judicial evaluation.

🔁 High-Level Swarm Flow

## 🔁 High-Level Execution Flow

```mermaid
flowchart TD

    START([START]) --> R[RepoInvestigator 🔎]
    START --> D[DocAnalyst 📘]

    R --> AGG[Evidence Aggregator<br/>Reducer: operator.ior]
    D --> AGG

    AGG --> P[Prosecutor ⚖️]
    P --> DEF[Defense 🛡️]
    DEF --> T[TechLead 👨‍💻]

    T --> CJ[Chief Justice 👑]
    CJ --> REPORT[Final Audit Report 📊]

    🧩 Layered Architecture View


---

# 📌 2️⃣ Layered Architecture View

Paste this under a new section:

```markdown
## 🧠 Layered Architecture View

```mermaid
flowchart LR

subgraph Layer 1: Forensic Detectives (Parallel)
    R[RepoInvestigator<br/>• AST Analysis<br/>• Graph Verification<br/>• Reducer Detection]
    D[DocAnalyst<br/>• OCR Processing<br/>• Semantic Chunking<br/>• Concept Verification]
end

subgraph Layer 2: Typed Swarm State
    S[AgentState<br/>evidences: Dict[str, List[Evidence]]<br/>Reducer: operator.ior]
end

subgraph Layer 3: Judicial Evaluation
    P[Prosecutor]
    DEF[Defense]
    T[TechLead]
end

subgraph Layer 4: Deterministic Synthesis
    CJ[Chief Justice<br/>Score Aggregation<br/>Variance Detection<br/>Remediation]
    FR[AuditReport Output]
end

R --> S
D --> S

S --> P
P --> DEF
DEF --> T

T --> CJ
CJ --> FR

🔄 Reducer-Based Evidence Merge (Core Concept)


This shows evaluators your architecture thinking level 🔥

---

# 📌 3️⃣ Evidence Reducer Mechanism Diagram

Paste this too:

```markdown
## 🔄 Evidence Reducer Mechanism

```mermaid
flowchart TD

    E1[Repo Evidence Stream]
    E2[Doc Evidence Stream]

    E1 --> RED[operator.ior Reducer]
    E2 --> RED

    RED --> MERGED[Merged Evidence Dictionary]


    
    Why this matters:

Prevents overwriting during parallel execution

Guarantees deterministic fan-in

Preserves evidence provenance

Ensures structured state integrity

🔎 Forensic Layer (Parallel Detectives)
🔹 RepoInvestigator

Uses Python ast module for structural analysis

Verifies:

StateGraph instantiation

builder.add_edge() wiring

Parallel structure

Reducer usage (operator.ior)

Ignores comments and string literals

Outputs structured Evidence objects

🔹 DocAnalyst

Uses RapidOCR + semantic chunking

Audits PDF reports (including scanned content)

Detects theoretical alignment:

LangGraph

Parallelism

Reducers

Swarm architecture

Assigns confidence scores

Outputs structured evidence

Both detectives execute in parallel and merge their outputs via typed reducers.

⚖️ Judicial Layer (Multi-Agent Reasoning)

After evidence collection, three independent judges evaluate rubric criteria.

⚖️ Prosecutor

Strict and skeptical

Penalizes missing requirements

Flags inconsistencies

🛡️ Defense

Fair and balanced

Rewards partial implementations

Recognizes architectural intent

👨‍💻 TechLead

Engineering-focused

Evaluates correctness and maintainability

Checks architectural soundness

Each judge:

Uses Groq (Llama 3.1)

Produces structured JudicialOpinion

Must cite real evidence IDs (e.g., repo_detective:0)

Includes rate-limit safe retry logic

Falls back safely if JSON parsing fails

👑 Chief Justice (Deterministic Synthesis)

The Chief Justice:

Aggregates all judicial opinions

Computes final per-criterion score

Detects disagreement (variance)

Produces:

Final score

Strengths

Weaknesses

Remediation recommendations

Dissent flag (if judges disagree)

Final output is a structured AuditReport.

## 🛠️ Tech Stack

| Layer | Technology |
|-------|------------|
| Orchestration | LangGraph (StateGraph) |
| LLM | Groq (Llama 3.1-8b-instant) |
| Static Analysis | Python `ast` module |
| Document Processing | RapidOCR (via Docling) |
| State Modeling | Pydantic (Typed AgentState + Reducers) |
| Observability | LangSmith |
| Environment | uv (Isolated Python 3.13) |

🚀 Getting Started
1️⃣ Installation

```uv sync```

2️⃣ Environment Configuration

Create a .env file in the root directory:

GROQ_API_KEY=your_groq_key
GROQ_MODEL=llama-3.1-8b-instant

LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=your_langsmith_key
LANGCHAIN_PROJECT=automaton-auditor-week2

3️⃣ Running the Audit

uv run python -m src.main

The system will:

Ingest and chunk the PDF

Analyze repository structure via AST

Execute three judicial personas

Synthesize final audit report

Output structured scoring

🛡️ Forensic Protocols
🔐 Sandboxed Repository Inspection

Cloning and inspection occur in isolated temporary directories.

🧩 AST over Regex

Structural verification is performed using Python’s ast, ensuring real execution logic is analyzed.

📄 Multimodal PDF Analysis

RapidOCR allows analysis of scanned or non-searchable PDFs.

⚖️ Evidence-Grounded Judging

Judges are explicitly instructed to:

Use only provided evidence

Avoid hallucination

Cite valid evidence IDs

🧠 Deterministic Final Aggregation

Final scoring logic is reproducible and transparent.

📊 Current Swarm Status

✅ Functional parallel forensic layer
✅ Typed state with reducer-based merging (operator.ior)
✅ AST-based graph verification
✅ OCR-based document analysis
✅ Three-judge reasoning layer
✅ Deterministic chief justice synthesis
✅ Groq integration with rate-limit safety
✅ Structured final audit report generation

🎯 Rubric Alignment

This implementation demonstrates:

Fan-Out/Fan-In architecture

Parallel execution proof

Reducer-based state merging

Structured evidence handling

Multi-agent reasoning

Deterministic final synthesis

🧭 Project Phase

Swarm Level: Full Judicial Stack Active

Detectives + Judges + Chief Justice operational.
Next phase focuses on strengthening evidence grounding and improving scoring robustness