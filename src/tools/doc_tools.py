import os
from docling.document_converter import DocumentConverter

def ingest_pdf(path: str) -> str:
    if not os.path.exists(path): 
        print(f"DEBUG: File NOT found at {path}")
        return ""
    
    print(f"DEBUG: Starting PDF ingestion for {path}...")
    
    try:
        # Use the default converter - it is the most stable across versions
        converter = DocumentConverter()
        
        # This performs the conversion
        result = converter.convert(path)
        content = result.document.export_to_markdown()
        
        print(f"DEBUG: Successfully extracted {len(content)} characters.")
        return content
        
    except Exception as e:
        print(f"DEBUG: Ingestion error: {e}")
        return ""

def search_pdf_concepts(content: str, keywords: list) -> dict:
    results = {}
    if not content:
        return {word: {"found": False, "mentions": 0} for word in keywords}

    lower_content = content.lower()

    # Alias map to handle variations in naming or OCR artifacts
    # This ensures "LangGraph" is found if "StateGraph" exists in the text.
    aliases = {
        "LangGraph": ["langgraph", "stategraph", "langchain", "workflow"],
        "Reducers": ["reducer", "operator.ior", "aggregate", "state management"],
        "AST": ["ast", "abstract syntax tree", "parsing", "static analysis"]
    }

    for word in keywords:
        # Get aliases for the keyword, defaulting to the word itself if not in map
        search_terms = aliases.get(word, [word.lower()])
        
        # Sum up mentions of all related terms
        count = sum(lower_content.count(term.lower()) for term in search_terms)
        
        results[word] = {"found": count > 0, "mentions": count}
        
    return results