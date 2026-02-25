import ast
import os
import tempfile
import git
from typing import Tuple, Optional, Dict, Any

def clone_repo_sandboxed(repo_url: str) -> Tuple[Optional[str], Optional[tempfile.TemporaryDirectory]]:
    """Clones with rich error feedback for auth or missing repos."""
    temp_dir = tempfile.TemporaryDirectory()
    try:
        git.Repo.clone_from(repo_url, temp_dir.name, depth=1)
        return temp_dir.name, temp_dir
    except git.GitCommandError as e:
        err = str(e).lower()
        if "authentication" in err:
            print(f"🔒 Auth Failure: Private repo or bad token for {repo_url}")
        elif "not found" in err:
            print(f"🚫 Not Found: Invalid URL {repo_url}")
        return None, None

def verify_graph_forensics(repo_path: str) -> Dict[str, Any]:
    """Deep AST analysis: Checks inheritance, decorators, and parallel patterns."""
    graph_path = os.path.join(repo_path, "src/graph.py")
    if not os.path.exists(graph_path):
        return {"status": "Missing", "reason": "src/graph.py not found"}

    with open(graph_path, "r") as f:
        try:
            tree = ast.parse(f.read())
            
            # 1. Deep Check: Inheritance (e.g., class State(TypedDict))
            has_typed_state = False
            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
                    if any(x in bases for x in ["TypedDict", "BaseModel"]):
                        has_typed_state = True
            
            # 2. Parallelism Check
            edge_sources = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    # Catch .add_edge or just add_edge
                    func_name = getattr(node.func, 'attr', getattr(node.func, 'id', None))
                    if func_name == 'add_edge' and node.args:
                        # Extract node name from START or "START"
                        source = getattr(node.args[0], 'id', getattr(node.args[0], 'value', None))
                        edge_sources.append(source)
            
            is_parallel = edge_sources.count('START') > 1
            
            return {
                "verified": is_parallel and has_typed_state,
                "parallel": is_parallel,
                "typed_state": has_typed_state
            }
        except Exception as e:
            return {"status": "Error", "reason": str(e)}