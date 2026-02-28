from __future__ import annotations

from typing import Dict, List, Optional
import os

from src.state import AgentState, Evidence
from src.tools.repo_tools import clone_repo_sandboxed, verify_graph_forensics
from src.tools.doc_tools import PDFForensicInterface


# ----------------------------
# Small helpers (judge-friendly)
# ----------------------------

def _clip(text: Optional[str], n: int = 240) -> Optional[str]:
    """Keep snippets short to avoid token bloat."""
    if not text:
        return text
    text = " ".join(text.split())
    return text[:n] + ("..." if len(text) > n else "")


def _best_per_concept(findings: List[Dict]) -> List[Dict]:
    """
    Deduplicate doc findings: keep the highest-confidence item per concept.
    This prevents 'LangGraph found in chunk 3 and chunk 5' looking inconsistent.
    """
    best: Dict[str, Dict] = {}
    for f in findings:
        concept = str(f.get("concept", "")).strip()
        conf = float(f.get("confidence", 0.0))
        if not concept:
            continue
        if concept not in best or conf > float(best[concept].get("confidence", 0.0)):
            best[concept] = f
    return list(best.values())


# ----------------------------
# Detectives
# ----------------------------

def repo_investigator(state: AgentState):
    path, temp_dir = clone_repo_sandboxed(state["repo_url"])

    if not path:
        fail_evidence = Evidence(
            goal="Repository Clone Check",
            found=False,
            content=None,
            location="Remote Repo",
            rationale="Repository cloning failed (authentication issue, invalid URL, or network error).",
            confidence=0.0,
        )
        return {"evidences": {"repo_detective": [fail_evidence]}}

    try:
        results = verify_graph_forensics(path)
        all_evidence: List[Evidence] = []

        # --- 1) Architecture Proof ---
        parallel = bool(results.get("parallel"))
        typed_state = bool(results.get("typed_state"))
        verified = bool(results.get("verified"))
        audited_file = results.get("file_audited", "src/graph.py + src/state.py")
        reason = str(results.get("reason", "N/A"))

        # Optional extra fields (only if your verifier adds them)
        start_fanout = results.get("start_fanout")
        judge_fanout = results.get("judge_fanout")
        reducers = results.get("reducers")

        content_lines = [
            f"verified={verified}",
            f"parallel={parallel}",
            f"typed_state={typed_state}",
        ]
        if isinstance(start_fanout, list) and start_fanout:
            content_lines.append(f"START fan-out -> {', '.join(start_fanout)}")
        if isinstance(judge_fanout, list) and judge_fanout:
            content_lines.append(f"Judges fan-out -> {', '.join(judge_fanout)}")
        if isinstance(reducers, dict) and reducers:
            content_lines.append(f"Reducers -> {reducers}")

        architecture_evidence = Evidence(
            goal="Repo Forensics: LangGraph fan-out/fan-in + Typed State reducers",
            found=verified,
            content=_clip(" | ".join(content_lines), 320),
            location=audited_file,
            rationale=_clip(f"AST verification summary: {reason}", 260) or "AST verification summary produced.",
            confidence=1.0 if verified else 0.65,
        )
        all_evidence.append(architecture_evidence)

        # --- 2) Security Proof (improved wording to avoid false-trigger risks) ---
        unsafe_files = results.get("unsafe_files", []) or []

        if unsafe_files:
            security_evidence = Evidence(
                goal="Security Scan: Unsafe Execution Detected",
                found=True,
                content=_clip("Examples: " + ", ".join(unsafe_files[:3]), 240),
                location=", ".join(unsafe_files[:3]),
                rationale=(
                    f"Detected unsafe execution patterns in {len(unsafe_files)} file(s). "
                    "Replace os.system(...) or subprocess(..., shell=True) with safe subprocess calls."
                ),
                confidence=0.9,
            )
        else:
            security_evidence = Evidence(
                goal="Security Scan: Safe Execution Patterns",
                found=True,
                content="No unsafe execution patterns found (no os.system(...) and no subprocess(..., shell=True)).",
                location="Repository Scan",
                rationale="AST-based scan did not detect unsafe execution patterns in Python files.",
                confidence=0.9,
            )

        all_evidence.append(security_evidence)

        return {"evidences": {"repo_detective": all_evidence}}

    finally:
        if temp_dir:
            temp_dir.cleanup()


def doc_analyst(state: AgentState):
    interface = PDFForensicInterface(state["pdf_path"])
    all_evidence: List[Evidence] = []

    if interface.ingest_and_chunk():
        target_concepts = ["LangGraph", "Parallelism", "Reducers", "AST"]
        findings = interface.targeted_search(target_concepts) or []

        if not findings:
            all_evidence.append(
                Evidence(
                    goal="Documentation Theory Verification",
                    found=False,
                    content=None,
                    location=state["pdf_path"],
                    rationale="PDF ingestion succeeded, but no strong matches were found for key architectural concepts.",
                    confidence=0.7,
                )
            )
        else:
            deduped = _best_per_concept(findings)

            for f in deduped:
                concept = f.get("concept")
                chunk_id = f.get("chunk_id")
                snippet = _clip(f.get("snippet"), 280)

                all_evidence.append(
                    Evidence(
                        goal=f"Doc Proof: {concept}",
                        found=True,
                        content=snippet,
                        location=f"Chunk {chunk_id}",
                        rationale=f"Matched '{concept}' with high-confidence snippet from the report.",
                        confidence=float(f.get("confidence", 0.8)),
                    )
                )
    else:
        all_evidence.append(
            Evidence(
                goal="Documentation Ingestion Check",
                found=False,
                content=None,
                location=state["pdf_path"],
                rationale="PDF ingestion failed — document could not be parsed or loaded.",
                confidence=0.0,
            )
        )

    return {"evidences": {"doc_detective": all_evidence}}


def vision_inspector(state: AgentState):
    """
    VisionInspector:
    - Clones the repo (sandboxed)
    - Searches for common diagram/image files
    - Produces Evidence about what visual artifacts exist
    """
    path, temp_dir = clone_repo_sandboxed(state["repo_url"])

    if not path:
        fail_evidence = Evidence(
            goal="Vision Inspection: Repo Access",
            found=False,
            content=None,
            location="Remote Repo",
            rationale="Could not clone repo, so images/diagrams could not be inspected.",
            confidence=0.0,
        )
        return {"evidences": {"vision_inspector": [fail_evidence]}}

    try:
        image_exts = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
        found_images: List[str] = []

        # Optional: attempt to read image dimensions if Pillow exists
        try:
            from PIL import Image  # type: ignore
            pil_ok = True
        except Exception:
            Image = None  # type: ignore
            pil_ok = False

        for root, _, files in os.walk(path):
            for fname in files:
                ext = os.path.splitext(fname.lower())[1]
                if ext in image_exts:
                    found_images.append(os.path.join(root, fname))

        evidences: List[Evidence] = []

        if not found_images:
            evidences.append(
                Evidence(
                    goal="Vision Inspection: Architecture Diagrams",
                    found=False,
                    content="No image/diagram files found in the repository.",
                    location="Repository Scan",
                    rationale="Searched for .png/.jpg/.jpeg/.webp/.svg inside the cloned repo.",
                    confidence=0.85,
                )
            )
        else:
            sample = found_images[:6]

            for img_path in sample:
                rel = os.path.relpath(img_path, path)
                dims = None

                if pil_ok and Image is not None and not rel.lower().endswith(".svg"):
                    try:
                        with Image.open(img_path) as im:
                            dims = f"{im.size[0]}x{im.size[1]}"
                    except Exception:
                        dims = None

                content = f"Found diagram/image: {rel}"
                if dims:
                    content += f" (size={dims})"

                evidences.append(
                    Evidence(
                        goal="Vision Proof: Diagram/Image Artifact",
                        found=True,
                        content=_clip(content, 280),
                        location=rel,
                        rationale="Repository contains visual artifacts that may document architecture or flows.",
                        confidence=0.9,
                    )
                )

            evidences.append(
                Evidence(
                    goal="Vision Summary: Visual Artifacts Count",
                    found=True,
                    content=f"Total images/diagrams found: {len(found_images)}",
                    location="Repository Scan",
                    rationale="Counted all matching image file extensions in the repo.",
                    confidence=0.9,
                )
            )

        return {"evidences": {"vision_inspector": evidences}}

    finally:
        if temp_dir:
            temp_dir.cleanup()