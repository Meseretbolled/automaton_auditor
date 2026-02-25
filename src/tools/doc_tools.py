from docling.document_converter import DocumentConverter
import os

def ingest_pdf(path: str) -> str:
    if not os.path.exists(path): return ""
    converter = DocumentConverter()
    return converter.convert(path).document.export_to_markdown()

def search_pdf_concepts(content: str, keywords: list) -> dict:
    results = {}
    for word in keywords:
        count = content.lower().count(word.lower())
        results[word] = {"found": count > 0, "mentions": count}
    return results