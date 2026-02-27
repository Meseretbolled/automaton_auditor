import os
import ast
import tempfile
import subprocess
from typing import Dict, Any, List


def clone_repo_sandboxed(repo_url: str):
    """
    Clones a repository into a temporary directory sandbox.
    Returns (repo_path, temp_dir_object).
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
        temp_dir.cleanup()
        print(f"[ERROR] Git clone failed: {e.stderr}")
        return None, None


def extract_git_history(repo_path: str) -> List[Dict[str, str]]:
    """
    Extracts commit history to check development progression.
    """
    try:
        result = subprocess.run(
            ["git", "-C", repo_path, "log", "--oneline", "--reverse"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        commits = result.stdout.strip().split("\n")
        structured = []

        for line in commits:
            if not line.strip():
                continue

            parts = line.split(" ", 1)
            if len(parts) == 2:
                structured.append({"hash": parts[0], "message": parts[1]})

        return structured

    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Git log failed: {e.stderr}")
        return []


def _has_typed_state(state_py: str) -> bool:
    """
    Verifies:
    - AgentState inherits from TypedDict
    - operator.ior reducer exists
    """
    try:
        tree = ast.parse(state_py)
    except Exception:
        return False

    has_agentstate_typed = False
    has_reducer_ior = False

    for node in ast.walk(tree):
        # Check for: class AgentState(TypedDict)
        if isinstance(node, ast.ClassDef) and node.name == "AgentState":
            bases = []
            for b in node.bases:
                if isinstance(b, ast.Name):
                    bases.append(b.id)
                elif isinstance(b, ast.Attribute):
                    bases.append(b.attr)

            if "TypedDict" in bases:
                has_agentstate_typed = True

        # Detect operator.ior usage (for evidence reducer)
        if isinstance(node, ast.Attribute) and node.attr == "ior":
            if isinstance(node.value, ast.Name) and node.value.id == "operator":
                has_reducer_ior = True

    return has_agentstate_typed and has_reducer_ior


def _has_parallel_fanout(graph_py: str) -> bool:
    """
    Detects if START has 2+ outgoing edges (parallel fan-out).
    """
    try:
        tree = ast.parse(graph_py)
    except Exception:
        return False

    start_edges = 0

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = getattr(node.func, "attr", getattr(node.func, "id", None))

            if func_name == "add_edge" and len(node.args) >= 2:
                src = getattr(node.args[0], "id", getattr(node.args[0], "value", None))
                if src == "START":
                    start_edges += 1

    return start_edges >= 2


def _detect_unsafe_calls(repo_path: str) -> List[str]:
    """
    Basic security scan:
    Detects usage of os.system (unsafe execution).
    """
    flagged_files = []

    for root, _, files in os.walk(repo_path):
        for file in files:
            if file.endswith(".py"):
                full_path = os.path.join(root, file)
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        if "os.system(" in f.read():
                            flagged_files.append(full_path)
                except Exception:
                    continue

    return flagged_files

def verify_graph_forensics(repo_path: str) -> Dict[str, Any]:
    """
    Main forensic check:
    - Ensures src/graph.py exists
    - Ensures src/state.py exists
    - Verifies parallel fan-out
    - Verifies typed state + reducer
    - Scans for unsafe calls (returned separately)
    """

    graph_path = os.path.join(repo_path, "src", "graph.py")
    state_path = os.path.join(repo_path, "src", "state.py")

    if not os.path.exists(graph_path):
        return {"verified": False, "reason": "src/graph.py not found", "file_audited": "src/graph.py"}

    if not os.path.exists(state_path):
        return {"verified": False, "reason": "src/state.py not found", "file_audited": "src/state.py"}

    with open(graph_path, "r", encoding="utf-8") as f:
        graph_src = f.read()

    with open(state_path, "r", encoding="utf-8") as f:
        state_src = f.read()

    parallel = _has_parallel_fanout(graph_src)
    typed_state = _has_typed_state(state_src)
    unsafe_files = _detect_unsafe_calls(repo_path)

    # ✅ UPDATED: verified means architecture is valid (security is separate evidence)
    verified = parallel and typed_state

    reason = (
        f"parallel={parallel}, "
        f"typed_state={typed_state}, "
        f"unsafe_calls_detected={len(unsafe_files)}"
    )

    return {
        "verified": verified,
        "parallel": parallel,
        "typed_state": typed_state,
        "unsafe_files": unsafe_files,
        "reason": reason,
        "file_audited": "src/graph.py + src/state.py"
    }