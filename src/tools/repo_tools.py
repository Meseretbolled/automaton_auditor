import ast
import os
import tempfile
import git

def clone_repo_sandboxed(repo_url: str):
    temp_dir = tempfile.TemporaryDirectory()
    try:
        git.Repo.clone_from(repo_url, temp_dir.name)
        return temp_dir.name, temp_dir
    except Exception:
        return None, None

def verify_graph_forensics(repo_path: str):
    graph_path = os.path.join(repo_path, "src/graph.py")
    if not os.path.exists(graph_path):
        return "Missing src/graph.py"

    with open(graph_path, "r") as f:
        try:
            tree = ast.parse(f.read())
            has_stategraph = any(isinstance(n, ast.Call) and getattr(n.func, 'id', None) == 'StateGraph' for n in ast.walk(tree))
            
            # Count edges from START to check for Fan-out
            edge_sources = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and getattr(node.func, 'attr', None) == 'add_edge':
                    if len(node.args) > 0:
                        source = getattr(node.args[0], 'id', getattr(node.args[0], 'value', None))
                        edge_sources.append(source)
            
            is_parallel = edge_sources.count('START') > 1 or len(edge_sources) != len(set(edge_sources))
            
            if has_stategraph and is_parallel:
                return "Verified: Parallel StateGraph Architecture"
            return "Warning: Graph structure may be linear"
        except Exception as e:
            return f"Parsing Error: {str(e)}"