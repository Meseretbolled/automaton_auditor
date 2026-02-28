# 🕵️ Automaton Auditor  
### A Deterministic Multi-Agent Forensic Swarm for Auditing Autonomous Systems

---

## 📌 Overview

**Automaton Auditor** is a structured multi-agent forensic system built using **LangGraph**.  
It performs deep architectural audits of autonomous repositories by combining:

- 🔎 AST-based static code verification  
- 📄 Multimodal PDF forensic analysis (OCR + semantic chunking)  
- ⚖ Structured judicial LLM debate  
- 🧠 Deterministic score synthesis  

The system follows a **Fan-Out / Fan-In Swarm Architecture** with typed reducers to ensure safe parallel execution and deterministic evidence merging.

---

## 🎯 Project Purpose

This project was designed to satisfy a **Robust Swarm Architecture Rubric**, requiring:

- True parallel orchestration
- Typed state with reducers
- Evidence-grounded reasoning
- Structured judicial outputs
- Deterministic synthesis
- Separation of fact verification from LLM reasoning

Unlike simple LLM-based audit tools, Automaton Auditor verifies *real structural implementation* using Python AST inspection.

---

# 🏗 System Architecture

## 🔁 High-Level Execution Flow

![High Level Flow](assets/architecture-flow.png)

**Execution Model:**

1. Detectives run in parallel  
2. Evidence streams merge via typed reducer  
3. Three judicial personas evaluate independently  
4. Chief Justice synthesizes deterministically  
5. Final structured audit report is generated  

This fan-out / fan-in architecture guarantees concurrency safety and deterministic results.

---

## 🧠 Layered Architecture

![Layered Architecture](assets/layered-architecture.png)

### 🟢 Layer 1 — Forensic Detectives (Parallel)

#### 🔍 RepoInvestigator
- Sandboxed repository cloning
- AST graph verification
- Reducer detection
- Git progression analysis
- Security scan (`os.system`, `shell=True` detection)

#### 📄 DocAnalyst
- RapidOCR ingestion
- Semantic chunk search
- Rubric concept verification
- File-path cross-reference (hallucination detection)

#### 🖼 VisionInspector
- Embedded PDF diagram detection
- Repository image scanning
- Optional dimension extraction (Pillow)

---

### 🔵 Layer 2 — Typed Swarm State

- `AgentState` defined via Pydantic
- Evidence stored as structured `Evidence` objects
- `operator.ior` reducer ensures safe merging
- Prevents evidence overwrite and race conditions

---

### 🟠 Layer 3 — Judicial Evaluation

Three independent personas evaluate each criterion:

| Judge        | Personality |
|--------------|-------------|
| **Prosecutor** | Strict, skeptical, penalizes missing proof |
| **Defense**    | Balanced, credits partial implementations |
| **TechLead**   | Engineering-focused, values architecture correctness |

Each judge:
- Uses Groq (Llama 3.1-8b-instant)
- Returns structured JSON
- Is validated via Pydantic
- Falls back safely if LLM parsing fails

---

### 🔴 Layer 4 — Chief Justice Synthesis Engine

The Chief Justice:

- Computes average score
- Detects disagreement variance
- Applies fact-supremacy penalties
- Generates remediation guidance
- Produces deterministic final JSON report

This prevents LLM hallucination from overriding factual verification.

---

## 🔄 Evidence Reducer Mechanism

![Reducer Mechanism](assets/reducer-diagram.png)

Parallel evidence is merged using `operator.ior` to prevent:

- State overwrite  
- Evidence loss  
- Concurrency race conditions  

This guarantees deterministic fan-in behavior.

---

# 🛠 Technology Stack

| Layer | Technology |
|-------|------------|
| Orchestration | LangGraph (StateGraph) |
| LLM | Groq (Llama 3.1-8b-instant) |
| Static Analysis | Python `ast` module |
| OCR | RapidOCR |
| State Modeling | Pydantic |
| Image Processing | PyMuPDF + Pillow (optional) |
| Environment | uv (Python 3.13 isolated environment) |
| Observability | LangSmith |

---

# 🛡 Security & Forensic Protocols

## 🔒 Sandboxed Repository Analysis

All repository inspection runs inside temporary directories to prevent:

- Code injection
- Local environment pollution
- Unsafe execution

The system avoids:
- `os.system`
- `shell=True`
- Unsanitized subprocess calls

---

## 🧬 AST-Based Verification

The RepoInvestigator:

- Ignores comments and strings
- Inspects real code structure
- Verifies actual `StateGraph` instantiation
- Detects reducer usage
- Identifies unsafe execution patterns

---

## 🧠 Fact Supremacy Protocol

If:
- Graph structure is missing
- Reducers are absent
- Evidence contradicts claims  

The Chief Justice penalizes the score regardless of LLM reasoning.

This ensures structural validation remains authoritative.

---

# 🚀 Installation & Usage

## 1️⃣ Install Dependencies


```uv sync```
```source .venv/bin/activate ```
----

## 2️⃣ Configure Environment

## Create a .env file in the project root:
```GROQ_API_KEY=your_groq_key```
```GROQ_MODEL=llama-3.1-8b-instant```

```LANGCHAIN_TRACING_V2=true```
```LANGCHAIN_API_KEY=your_langsmith_key```
```LANGCHAIN_PROJECT=automaton-auditor-week2```

### 3️⃣ Run the Auditor
- Self Audit
```python -m src.main \```
```--repo https://github.com/your/repo.git \```
```--pdf path/to/report.pdf \```
```  --mode self```

- Peer Audit

```python -m src.main \```
```--repo https://github.com/peer/repo.git \```
```--pdf path/to/peer_report.pdf \```
```--mode peer```

## 📊 Example Output
```json
{
  "overall_score": 3,
  "executive_summary": "Final audit complete.",
  "criteria": [
    {
      "criterion_id": "langgraph_architecture",
      "final_score": 3,
      "summary": "Chief Justice synthesis.",
      "remediation": [
        "Tighten reducer verification evidence."
      ]
    }
  ]
}
```

## Reports are saved to:

```audit/report_onself_generated/```
### 📈 Current Capabilities

✅ Parallel LangGraph execution

✅ Typed AgentState with reducers

✅ AST-based graph verification

✅ Git forensic analysis

✅ Security scanning

✅ Multimodal PDF chunk inspection

✅ Hallucination detection

✅ Structured judicial layer

✅ Deterministic score synthesis

✅ LangSmith observability

## 📊 Observability

- All executions are traceable in LangSmith, including:

- Node-level timing

- Token usage

- Judge outputs

- Reducer merges

- Failure paths

## 🧠 Design Philosophy

- Automaton Auditor strictly separates:

- Fact Layer (AST + OCR + repository scanning)

- Reasoning Layer (LLM judges)

- Deterministic Layer (Chief Justice scoring)

- This architecture prevents hallucination from contaminating structural verification.

### 📜 License

## MIT License

## 👩‍💻 Author

## Meseret Bolled
Software Engineering Student
Focused on AI-native system architecture & multi-agent design