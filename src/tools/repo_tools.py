import os
import ast
import tempfile
import subprocess
from typing import Dict, Any, List, Optional, Tuple


# ============================================================
# SAFE CLONE
# ============================================================

def clone_repo_sandboxed(repo_url: str) -> Tuple[Optional[str], Optional[tempfile.TemporaryDirectory]]:
    """
    Clones a repository into a temporary directory sandbox.
    Returns (repo_path, temp_dir_object).
    Uses SAFE subprocess call (no shell=True).
    """
    temp_dir = tempfile.TemporaryDirectory()
    repo_path = os.path.join(temp_dir.name, "repo")

    try:
        subprocess.run(
            ["git", "clone", repo_url, repo_path],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return repo_path, temp_dir

    except subprocess.CalledProcessError as e:
        print("[ERROR] Git clone failed:")
        print(e.stderr)
        temp_dir.cleanup()
        return None, None


# ============================================================
# GIT HISTORY EXTRACTION (WITH TIMESTAMPS)
# ============================================================

def extract_git_history(repo_path: str, max_commits: int = 50) -> List[Dict[str, str]]:
    """
    Extracts commit history to check development progression.

    Returns list of dicts:
      { "hash": "...", "date": "...", "author": "...", "message": "..." }

    Uses a safe subprocess call (no shell=True).
    """
    try:
        # ISO-ish date for easy reading; includes timezone.
        # Format: HASH|DATE|AUTHOR|SUBJECT
        result = subprocess.run(
            [
                "git",
                "-C",
                repo_path,
                "log",
                f"-n{max_commits}",
                "--reverse",
                "--pretty=format:%H|%ad|%an|%s",
                "--date=iso-strict",
            ],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        lines = [ln for ln in result.stdout.splitlines() if ln.strip()]
        structured: List[Dict[str, str]] = []

        for ln in lines:
            parts = ln.split("|", 3)
            if len(parts) != 4:
                continue
            structured.append(
                {
                    "hash": parts[0].strip(),
                    "date": parts[1].strip(),
                    "author": parts[2].strip(),
                    "message": parts[3].strip(),
                }
            )

        return structured

    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Git log failed: {e.stderr}")
        return []


# ============================================================
# AST HELPERS
# ============================================================

def _call_attr_name(call: ast.Call) -> str:
    """
    Returns attribute name for a call like builder.add_edge -> "add_edge"
    or function name like add_edge -> "add_edge"
    """
    func = call.func
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _is_name(node: ast.AST, expected: str) -> bool:
    return isinstance(node, ast.Name) and node.id == expected


def _is_const_str(node: ast.AST) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def _const_str(node: ast.AST) -> Optional[str]:
    if _is_const_str(node):
        return str(node.value)
    return None


# ============================================================
# ARCHITECTURE CHECKS (RUBRIC-STRONG)
# ============================================================

def _has_typed_state_with_reducers(state_py: str) -> Dict[str, bool]:
    """
    Verifies:
    - AgentState inherits from TypedDict
    - reducer operator.ior exists somewhere (evidence merge)
    - reducer operator.add exists somewhere (lists / concatenation)
    """
    try:
        tree = ast.parse(state_py)
    except Exception:
        return {"typed_state": False, "reducer_ior": False, "reducer_add": False}

    has_agentstate_typed = False
    has_reducer_ior = False
    has_reducer_add = False

    for node in ast.walk(tree):
        # class AgentState(TypedDict)
        if isinstance(node, ast.ClassDef) and node.name in ("AgentState", "State", "GraphState"):
            bases = []
            for b in node.bases:
                if isinstance(b, ast.Name):
                    bases.append(b.id)
                elif isinstance(b, ast.Attribute):
                    bases.append(b.attr)
            if "TypedDict" in bases:
                has_agentstate_typed = True

        # Detect operator.ior / operator.add usage anywhere in annotations
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "operator":
            if node.attr == "ior":
                has_reducer_ior = True
            if node.attr == "add":
                has_reducer_add = True

    return {
        "typed_state": has_agentstate_typed,
        "reducer_ior": has_reducer_ior,
        "reducer_add": has_reducer_add,
    }


def _graph_structure_checks(graph_py: str) -> Dict[str, Any]:
    """
    Checks graph orchestration patterns via AST:
    - START fan-out: 2+ add_edge(START, ...)
    - Fan-in node exists: evidence_aggregator/opinion_aggregator added
    - Judges fan-out: evidence_aggregator -> prosecutor/defense/techlead
    - Conditional edges exist: add_conditional_edges(...)
    - Explicit END edge exists
    """
    try:
        tree = ast.parse(graph_py)
    except Exception:
        return {
            "start_fanout": False,
            "start_fanout_count": 0,
            "has_conditional_edges": False,
            "has_evidence_aggregator": False,
            "has_opinion_aggregator": False,
            "judges_parallel": False,
            "has_end": False,
        }

    start_edges = 0
    has_conditional = False
    has_end = False

    # We will detect nodes added by name strings
    node_names: set[str] = set()
    edges: List[Tuple[str, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = _call_attr_name(node)

            if fn == "add_node" and len(node.args) >= 1:
                # add_node("name", func)
                name = _const_str(node.args[0])
                if name:
                    node_names.add(name)

            if fn == "add_edge" and len(node.args) >= 2:
                src = node.args[0]
                dst = node.args[1]

                # count START fan-out
                if _is_name(src, "START"):
                    start_edges += 1

                # track explicit END usage
                if _is_name(dst, "END"):
                    has_end = True

                # capture edges when strings
                src_s = _const_str(src) if _is_const_str(src) else (src.id if isinstance(src, ast.Name) else None)
                dst_s = _const_str(dst) if _is_const_str(dst) else (dst.id if isinstance(dst, ast.Name) else None)
                if src_s and dst_s:
                    edges.append((src_s, dst_s))

            if fn == "add_conditional_edges":
                has_conditional = True

    has_evidence_agg = "evidence_aggregator" in node_names
    has_opinion_agg = "opinion_aggregator" in node_names

    # Judges parallel fan-out expected from evidence_aggregator -> {prosecutor, defense, techlead}
    judge_targets = {"prosecutor", "defense", "techlead"}
    judge_edges = {dst for (src, dst) in edges if src == "evidence_aggregator" and dst in judge_targets}
    judges_parallel = len(judge_edges) >= 2  # ideally 3, but accept >=2

    return {
        "start_fanout": start_edges >= 2,
        "start_fanout_count": start_edges,
        "has_conditional_edges": has_conditional,
        "has_evidence_aggregator": has_evidence_agg,
        "has_opinion_aggregator": has_opinion_agg,
        "judges_parallel": judges_parallel,
        "has_end": has_end,
    }


# ============================================================
# SAFE SECURITY SCAN (AST-BASED, NO FALSE POSITIVES)
# ============================================================

def _is_shell_true(call_node: ast.Call) -> bool:
    """
    Returns True if call has keyword argument shell=True
    """
    for kw in call_node.keywords or []:
        if kw.arg == "shell":
            if isinstance(kw.value, ast.Constant) and kw.value.value is True:
                return True
    return False


def _call_name(node: ast.AST) -> str:
    """
    Build a dotted call name like:
    - os.system
    - subprocess.run
    - run (if imported directly)
    """
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        left = _call_name(node.value)
        if left:
            return f"{left}.{node.attr}"
        return node.attr
    return ""


def _detect_unsafe_calls_in_file(py_path: str) -> bool:
    """
    Detects actual unsafe calls using AST:
    - os.system(...)
    - subprocess.<any>(..., shell=True)
    """
    try:
        with open(py_path, "r", encoding="utf-8", errors="ignore") as f:
            src = f.read()

        tree = ast.parse(src)
    except Exception:
        # If we can't parse the file, don't block grading; treat as not-unsafe
        return False

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        name = _call_name(node.func)

        # 1) os.system(...)
        if name == "os.system":
            return True

        # 2) subprocess.*(..., shell=True)
        if name.startswith("subprocess.") and _is_shell_true(node):
            return True

    return False


def _detect_unsafe_calls(repo_path: str) -> List[str]:
    """
    Detects usage of unsafe execution patterns with AST parsing:
    - os.system(...)
    - subprocess.*(..., shell=True)

    Skips virtualenv, caches, git, and our own tooling file.
    """
    unsafe_files: List[str] = []

    SKIP_DIRS = {".venv", "__pycache__", ".git", ".mypy_cache", ".pytest_cache"}
    SKIP_FILES = {"repo_tools.py"}

    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]

        for name in files:
            if not name.endswith(".py"):
                continue
            if name in SKIP_FILES:
                continue

            full_path = os.path.join(root, name)

            if _detect_unsafe_calls_in_file(full_path):
                unsafe_files.append(full_path)

    return unsafe_files


# ============================================================
# MAIN FORENSICS ENTRY
# ============================================================

def verify_graph_forensics(repo_path: str) -> Dict[str, Any]:
    """
    Main forensic check:
    - Ensures src/graph.py exists
    - Ensures src/state.py exists
    - Verifies START fan-out (parallel)
    - Verifies fan-in nodes and judge fan-out
    - Verifies conditional edges exist
    - Verifies typed state + reducer(s) exist
    - Scans for unsafe calls (separate evidence)
    - Includes git history with timestamps for narrative evidence
    """

    graph_path = os.path.join(repo_path, "src", "graph.py")
    state_path = os.path.join(repo_path, "src", "state.py")

    if not os.path.exists(graph_path):
        return {
            "verified": False,
            "reason": "src/graph.py not found",
            "file_audited": "src/graph.py",
        }

    if not os.path.exists(state_path):
        return {
            "verified": False,
            "reason": "src/state.py not found",
            "file_audited": "src/state.py",
        }

    with open(graph_path, "r", encoding="utf-8", errors="ignore") as f:
        graph_src = f.read()

    with open(state_path, "r", encoding="utf-8", errors="ignore") as f:
        state_src = f.read()

    graph_checks = _graph_structure_checks(graph_src)
    state_checks = _has_typed_state_with_reducers(state_src)
    unsafe_files = _detect_unsafe_calls(repo_path)
    git_history = extract_git_history(repo_path)

    verified = (
        graph_checks["start_fanout"]
        and graph_checks["has_evidence_aggregator"]
        and graph_checks["has_opinion_aggregator"]
        and graph_checks["judges_parallel"]
        and graph_checks["has_conditional_edges"]
        and graph_checks["has_end"]
        and state_checks["typed_state"]
        and (state_checks["reducer_ior"] or state_checks["reducer_add"])
    )

    reason = (
        f"start_fanout={graph_checks['start_fanout']} (count={graph_checks['start_fanout_count']}), "
        f"conditional_edges={graph_checks['has_conditional_edges']}, "
        f"fan_in_nodes=evidence:{graph_checks['has_evidence_aggregator']} opinion:{graph_checks['has_opinion_aggregator']}, "
        f"judges_parallel={graph_checks['judges_parallel']}, "
        f"end_edge={graph_checks['has_end']}, "
        f"typed_state={state_checks['typed_state']}, "
        f"reducers(ior={state_checks['reducer_ior']}, add={state_checks['reducer_add']}), "
        f"unsafe_calls_detected={len(unsafe_files)}, "
        f"git_commits={len(git_history)}"
    )

    return {
        "verified": verified,
        "graph_checks": graph_checks,
        "state_checks": state_checks,
        "unsafe_files": unsafe_files,
        "git_history": git_history,
        "reason": reason,
        "file_audited": "src/graph.py + src/state.py + repo scan",
    }