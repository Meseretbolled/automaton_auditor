from __future__ import annotations

from typing import Dict, List, Optional
import os

from src.state import AgentState, Evidence
from src.tools.repo_tools import clone_repo_sandboxed, verify_graph_forensics
from src.tools.doc_tools import PDFForensicInterface

def _clip(text: Optional[str], n: int = 240) -> Optional[str]:
    """Keep snippets short to avoid token bloat."""
    if not text:
        return text
    text = " ".join(str(text).split())
    return text[:n] + ("..." if len(text) > n else "")


def _best_per_concept(findings: List[Dict]) -> List[Dict]:
    """Keep highest-confidence item per concept."""
    best: Dict[str, Dict] = {}
    for f in findings:
        concept = str(f.get("concept", "")).strip()
        conf = float(f.get("confidence", 0.0))
        if not concept:
            continue
        if concept not in best or conf > float(best[concept].get("confidence", 0.0)):
            best[concept] = f
    return list(best.values())


def repo_investigator(state: AgentState):
    path, temp_dir = clone_repo_sandboxed(state["repo_url"])

    if not path:
        fail_evidence = Evidence(
            goal="Repository Clone Check",
            found=False,
            content=None,
            location="Remote Repo",
            rationale="Repository cloning failed (invalid URL, auth, or network).",
            confidence=0.0,
        )
        return {
            "evidences": {"repo_detective": [fail_evidence]},
            "repo_failed": True,
        }

    try:
        all_evidence: List[Evidence] = []

        # If verify_graph_forensics crashes, THAT is a failure
        try:
            results = verify_graph_forensics(path)
        except Exception as e:
            crash_evidence = Evidence(
                goal="Repo Forensics: Verifier crashed",
                found=False,
                content=_clip(str(e), 300),
                location="verify_graph_forensics",
                rationale="Repo was cloned, but verification tool crashed.",
                confidence=0.0,
            )
            return {
                "evidences": {"repo_detective": [crash_evidence]},
                "repo_failed": True,
            }

        # --- 1) Architecture Proof ---
        graph_checks = results.get("graph_checks") or {}
        state_checks = results.get("state_checks") or {}

        # Backwards-compat (if older verifier output)
        parallel = bool(results.get("parallel")) if "parallel" in results else bool(graph_checks.get("start_fanout"))
        typed_state = bool(results.get("typed_state")) if "typed_state" in results else bool(state_checks.get("typed_state"))
        verified = bool(results.get("verified"))
        audited_file = results.get("file_audited", "src/graph.py + src/state.py")
        reason = str(results.get("reason", "N/A"))

        content_lines = [
            f"verified={verified}",
            f"parallel/fanout_ok={parallel}",
            f"typed_state_ok={typed_state}",
        ]

        # include richer checks if present
        if graph_checks:
            content_lines.append(f"graph_checks={graph_checks}")
        if state_checks:
            content_lines.append(f"state_checks={state_checks}")

        architecture_evidence = Evidence(
            goal="Repo Forensics: LangGraph fan-out/fan-in + Typed State reducers",
            found=verified,  # ✅ this can be False, that's OK (not a node failure)
            content=_clip(" | ".join(content_lines), 380),
            location=audited_file,
            rationale=_clip(f"AST verification summary: {reason}", 260) or "AST verification summary produced.",
            confidence=1.0 if verified else 0.65,
        )
        all_evidence.append(architecture_evidence)

        # --- 2) Git progression evidence (if available) ---
        git_history = results.get("git_history") or []
        if git_history:
            sample = git_history[:5]
            sample_text = "; ".join([f"{c.get('date','')} {c.get('message','')}" for c in sample])
            all_evidence.append(
                Evidence(
                    goal="Git Forensics: Development progression",
                    found=True,
                    content=_clip(f"Commits={len(git_history)} | sample: {sample_text}", 360),
                    location="git log --reverse",
                    rationale="Commit history supports a plausible development story when messages show progression.",
                    confidence=0.85,
                )
            )
        else:
            all_evidence.append(
                Evidence(
                    goal="Git Forensics: Development progression",
                    found=False,
                    content="No git history extracted (repo may be shallow, missing .git, or log failed).",
                    location="git log --reverse",
                    rationale="Unable to extract commit narrative; this can reduce forensic confidence.",
                    confidence=0.5,
                )
            )

        # --- 3) Security Proof (AST-based) ---
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

        return {
            "evidences": {"repo_detective": all_evidence},
            "repo_failed": False,
        }

    finally:
        if temp_dir:
            temp_dir.cleanup()


def doc_analyst(state: AgentState):
    """
    DocAnalyst:
    - Chunk PDF (Docling)
    - Search for rubric concepts
    - Extract file-path claims and cross-reference against repo files
    """
    interface = PDFForensicInterface(state["pdf_path"])
    all_evidence: List[Evidence] = []

    repo_path, repo_tmp = clone_repo_sandboxed(state["repo_url"])

    try:
        ok = interface.ingest_and_chunk()
        if not ok:
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
            return {"evidences": {"doc_detective": all_evidence}, "doc_failed": True}

        target_concepts = [
            "LangGraph",
            "Parallelism",
            "Reducers",
            "ConditionalEdges",
            "StateSync",
            "DialecticalSynthesis",
            "Metacognition",
            "Swarm",
            "Forensics",
            "AST",
        ]
        findings = interface.targeted_search(target_concepts) or []
        deduped = _best_per_concept(findings)

        if not deduped:
            all_evidence.append(
                Evidence(
                    goal="Documentation Theory Verification",
                    found=False,
                    content="PDF ingested, but key rubric concepts were not detected with high confidence.",
                    location=state["pdf_path"],
                    rationale="Missing theory keywords can weaken the forensic linkage between report and implementation.",
                    confidence=0.7,
                )
            )
        else:
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
                        rationale=f"Matched '{concept}' with snippet from the report.",
                        confidence=float(f.get("confidence", 0.8)),
                    )
                )

        # Path claims cross-reference (hallucination check)
        try:
            path_claims = interface.cross_reference_paths(repo_path)
        except Exception:
            path_claims = []

        if path_claims:
            verified = [p for p in path_claims if p.get("status") == "VERIFIED"]
            halluc = [p for p in path_claims if p.get("status") == "HALLUCINATED"]

            all_evidence.append(
                Evidence(
                    goal="Doc Forensics: Path claims cross-reference",
                    found=True,
                    content=_clip(
                        f"Verified={len(verified)} | Hallucinated={len(halluc)} | "
                        f"examples_verified={', '.join([v['path'] for v in verified[:3]])} | "
                        f"examples_hallucinated={', '.join([h['path'] for h in halluc[:3]])}",
                        380,
                    ),
                    location="PDF report vs cloned repo",
                    rationale="Cross-referencing file-path claims prevents report hallucination and supports forensic accuracy.",
                    confidence=0.85,
                )
            )

            if halluc:
                all_evidence.append(
                    Evidence(
                        goal="Doc Forensics: Potential hallucinated file references",
                        found=True,
                        content=_clip("Hallucinated examples: " + ", ".join([h["path"] for h in halluc[:6]]), 360),
                        location="PDF report",
                        rationale="The report references file paths that do not exist in the repository.",
                        confidence=0.9,
                    )
                )
        else:
            all_evidence.append(
                Evidence(
                    goal="Doc Forensics: Path claims cross-reference",
                    found=False,
                    content="No file-path claims detected in PDF text (or extraction unavailable).",
                    location=state["pdf_path"],
                    rationale="Path-claim extraction is optional but strengthens forensic accuracy when present.",
                    confidence=0.5,
                )
            )

        return {"evidences": {"doc_detective": all_evidence}, "doc_failed": False}

    finally:
        if repo_tmp:
            repo_tmp.cleanup()


def vision_inspector(state: AgentState):
    """
    VisionInspector:
    - Attempts to count embedded images/diagrams in the PDF
    - Clones the repo and searches for diagram/image files
    """
    evidences: List[Evidence] = []

    # 1) PDF embedded images (best effort)
    try:
        import fitz  # PyMuPDF  # type: ignore

        doc = fitz.open(state["pdf_path"])
        count = 0
        for page in doc:
            imgs = page.get_images(full=True)
            count += len(imgs)

        evidences.append(
            Evidence(
                goal="Vision Inspection: PDF embedded images/diagrams",
                found=True,
                content=f"Detected embedded images in PDF: {count}",
                location=state["pdf_path"],
                rationale="Counted embedded images via PyMuPDF.",
                confidence=0.85,
            )
        )
    except Exception:
        evidences.append(
            Evidence(
                goal="Vision Inspection: PDF embedded images/diagrams",
                found=False,
                content="PyMuPDF not available or PDF could not be scanned for embedded images.",
                location=state["pdf_path"],
                rationale="Best-effort feature; dependency may be missing.",
                confidence=0.5,
            )
        )

    # 2) Repo images scan
    path, temp_dir = clone_repo_sandboxed(state["repo_url"])
    if not path:
        evidences.append(
            Evidence(
                goal="Vision Inspection: Repo Access",
                found=False,
                content=None,
                location="Remote Repo",
                rationale="Could not clone repo, so repo images/diagrams could not be inspected.",
                confidence=0.0,
            )
        )
        return {"evidences": {"vision_inspector": evidences}, "vision_failed": True}

    try:
        image_exts = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
        found_images: List[str] = []

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

        if not found_images:
            evidences.append(
                Evidence(
                    goal="Vision Inspection: Repo diagrams/images",
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
                        content=_clip(content, 300),
                        location=rel,
                        rationale="Repository contains visual artifacts that may document architecture or flows.",
                        confidence=0.9,
                    )
                )

            evidences.append(
                Evidence(
                    goal="Vision Summary: Repo visual artifacts count",
                    found=True,
                    content=f"Total images/diagrams found in repo: {len(found_images)}",
                    location="Repository Scan",
                    rationale="Counted image file extensions in the repo.",
                    confidence=0.9,
                )
            )

        return {"evidences": {"vision_inspector": evidences}, "vision_failed": False}

    finally:
        if temp_dir:
            temp_dir.cleanup()