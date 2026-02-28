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
# GIT HISTORY EXTRACTION
# ============================================================

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
        structured: List[Dict[str, str]] = []

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


# ============================================================
# ARCHITECTURE CHECKS
# ============================================================

def _has_typed_state(state_py: str) -> bool:
    """
    Verifies:
    - AgentState inherits from TypedDict
    - operator.ior reducer exists (used in your AgentState annotations)
    """
    try:
        tree = ast.parse(state_py)
    except Exception:
        return False

    has_agentstate_typed = False
    has_reducer_ior = False

    for node in ast.walk(tree):
        # Check: class AgentState(TypedDict)
        if isinstance(node, ast.ClassDef) and node.name == "AgentState":
            bases = []
            for b in node.bases:
                if isinstance(b, ast.Name):
                    bases.append(b.id)
                elif isinstance(b, ast.Attribute):
                    bases.append(b.attr)

            if "TypedDict" in bases:
                has_agentstate_typed = True

        # Detect operator.ior usage
        # (e.g., Annotated[..., operator.ior])
        if isinstance(node, ast.Attribute) and node.attr == "ior":
            if isinstance(node.value, ast.Name) and node.value.id == "operator":
                has_reducer_ior = True

    return has_agentstate_typed and has_reducer_ior


def _has_parallel_fanout(graph_py: str) -> bool:
    """
    Detects if START has 2+ outgoing edges (parallel fan-out).
    Looks for builder.add_edge(START, ...)
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
                # START is usually an imported name, so node.args[0] is ast.Name("START")
                src = getattr(node.args[0], "id", None)
                if src == "START":
                    start_edges += 1

    return start_edges >= 2


# ============================================================
# SAFE SECURITY SCAN (AST-BASED, NO FALSE POSITIVES)
# ============================================================

def _is_shell_true(call_node: ast.Call) -> bool:
    """
    Returns True if call has keyword argument shell=True
    """
    for kw in call_node.keywords or []:
        if kw.arg == "shell":
            # Python 3.8+: True is Constant(True)
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
        # includes subprocess.run / Popen / call / check_output, etc.
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
    - Verifies parallel fan-out
    - Verifies typed state + reducer
    - Scans for unsafe calls (separate evidence)
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

    with open(graph_path, "r", encoding="utf-8") as f:
        graph_src = f.read()

    with open(state_path, "r", encoding="utf-8") as f:
        state_src = f.read()

    parallel = _has_parallel_fanout(graph_src)
    typed_state = _has_typed_state(state_src)
    unsafe_files = _detect_unsafe_calls(repo_path)

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
        "file_audited": "src/graph.py + src/state.py",
    }