import pytest
import os
import sys

# Ensure src is in the path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.tools.doc_tools import search_pdf_concepts
# Generic import to avoid name errors
import src.tools.repo_tools as repo_tools

def test_search_pdf_concepts_found():
    """Verify that the search logic correctly identifies keywords with aliases."""
    # Test text containing an alias for LangGraph
    sample_text = "The architecture is built on a StateGraph structure."
    keywords = ["LangGraph"]
    
    results = search_pdf_concepts(sample_text, keywords)
    
    # This proves our alias logic works!
    assert results["LangGraph"]["found"] is True
    assert results["LangGraph"]["mentions"] >= 1

def test_search_pdf_concepts_multi():
    """Verify multiple keywords are tracked correctly."""
    sample_text = "Uses AST and Reducers for state management."
    keywords = ["AST", "Reducers"]
    
    results = search_pdf_concepts(sample_text, keywords)
    
    assert results["AST"]["found"] is True
    assert results["Reducers"]["found"] is True

def test_repo_tools_path_exists():
    """Verify the repo tools module is present and loadable."""
    # This verifies your infrastructure is set up correctly
    assert repo_tools is not None
    assert os.path.exists("src/tools/repo_tools.py")