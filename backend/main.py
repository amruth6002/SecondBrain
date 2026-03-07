"""SecondBrain — FastAPI Backend

Multi-agent AI system for student knowledge management.
Agents: Planner → Retriever → Executor
"""

import asyncio
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, HTTPException, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from typing import Optional
import os

from config import settings
from models.schemas import ContentInput, ProcessingResult, PipelineStatus, SessionSummary
from agents.orchestrator import run_pipeline, get_current_status
from services.pdf_service import extract_text_from_pdf
from services.youtube_service import extract_transcript
from utils.spaced_repetition import calculate_next_review
from utils.database import (
    init_db, save_session, get_all_sessions, get_session_result_json,
    get_latest_session_result_json, save_flashcard, get_all_flashcards_from_db,
    update_flashcard_sm2, delete_session,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB and restore last session into memory on startup."""
    init_db()
    # Restore all flashcards into in-memory store
    for card in get_all_flashcards_from_db():
        _flashcard_store[card["id"]] = card
    # Restore latest result
    latest_json = get_latest_session_result_json()
    if latest_json:
        try:
            _results_store["latest"] = ProcessingResult.model_validate_json(latest_json)
        except Exception:
            pass
    yield


app = FastAPI(
    title="SecondBrain API",
    description="Multi-agent AI system for student knowledge management",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS — allow React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage for MVP (replaces database)
# Structure: "client_id_latest" -> ProcessingResult, "client_id_flashcard_id" -> dict
_results_store: dict[str, ProcessingResult] = {}
_flashcard_store: dict[str, dict] = {}

# Resolve frontend dist path once (used by root route and SPA catch-all)
_frontend_dist = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "frontend", "dist")


@app.get("/")
async def root():
    # Serve React SPA in production; fall back to JSON health-check in dev
    index_file = os.path.join(_frontend_dist, "index.html")
    if os.path.isfile(index_file):
        return FileResponse(index_file)
    return {
        "app": "SecondBrain",
        "version": "1.0.0",
        "status": "running",
        "model": settings.MODEL_NAME,
    }


@app.get("/health")
@app.get("/api/health")
async def health():
    return {"status": "healthy", "model_configured": bool(settings.AZURE_PHI4_API_KEY)}


# --- Content Processing (fire-and-forget to avoid Azure 230s timeout) ---

async def _run_pipeline_background(text: str, client_id: str):
    """Run pipeline in the background; persist result when done."""
    try:
        result = await run_pipeline(text)
        _results_store[f"{client_id}_latest"] = result
        _persist_result(result, client_id)
    except Exception as e:
        print(f"[BG PIPELINE ERROR] {e}")


@app.post("/api/process/text")
async def process_text(input_data: ContentInput, x_client_id: str = Header("default")):
    """Start text processing pipeline (returns immediately)."""
    if not input_data.text_content:
        raise HTTPException(400, "text_content is required")

    asyncio.create_task(_run_pipeline_background(input_data.text_content, x_client_id))
    return {"status": "processing", "message": "Pipeline started. Follow /api/pipeline/status for updates."}


@app.post("/api/process/pdf")
async def process_pdf(file: UploadFile = File(...), x_client_id: str = Header("default")):
    """Start PDF processing pipeline (returns immediately)."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files are supported")

    contents = await file.read()

    if len(contents) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(400, f"File too large. Max: {settings.MAX_UPLOAD_SIZE_MB}MB")

    text = extract_text_from_pdf(contents)

    if not text.strip():
        raise HTTPException(400, "Could not extract text from PDF. The file may be image-based.")

    asyncio.create_task(_run_pipeline_background(text, x_client_id))
    return {"status": "processing", "message": "Pipeline started. Follow /api/pipeline/status for updates."}


@app.post("/api/process/youtube")
async def process_youtube(input_data: ContentInput, x_client_id: str = Header("default")):
    """Start YouTube processing pipeline (returns immediately)."""
    if not input_data.youtube_url:
        raise HTTPException(400, "youtube_url is required")

    try:
        transcript = extract_transcript(input_data.youtube_url)
    except ValueError as e:
        raise HTTPException(400, str(e))

    asyncio.create_task(_run_pipeline_background(transcript, x_client_id))
    return {"status": "processing", "message": "Pipeline started. Follow /api/pipeline/status for updates."}


# --- Pipeline Status (SSE for real-time updates) ---

@app.get("/api/pipeline/status")
async def pipeline_status():
    """Get current pipeline status as Server-Sent Events for real-time UI."""
    async def event_stream():
        last_stage = ""
        while True:
            status = get_current_status()
            if status.stage != last_stage or status.stage in ("complete", "error"):
                data = json.dumps(status.model_dump())
                yield f"data: {data}\n\n"
                last_stage = status.stage
                if status.stage in ("complete", "error"):
                    break
            await asyncio.sleep(0.5)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# --- Results ---

@app.get("/api/results/latest")
async def get_latest_results(x_client_id: str = Header("default")):
    """Get the most recent processing results."""
    key = f"{x_client_id}_latest"
    if key not in _results_store:
        raise HTTPException(404, "No results yet. Process some content first.")
    return _results_store[key]


# --- Flashcard Review ---

@app.post("/api/flashcards/{card_id}/review")
async def review_flashcard(card_id: str, quality: int = 3, x_client_id: str = Header("default")):
    """Submit a flashcard review and update spaced repetition schedule."""
    mem_key = f"{x_client_id}_{card_id}"
    if mem_key not in _flashcard_store:
        raise HTTPException(404, f"Flashcard {card_id} not found")

    card = _flashcard_store[mem_key]

    updated = calculate_next_review(
        quality=quality,
        easiness_factor=card.get("easiness_factor", 2.5),
        interval=card.get("interval", 1),
        repetitions=card.get("repetitions", 0),
    )

    card.update(updated)
    _flashcard_store[mem_key] = card

    # Persist SM-2 update to SQLite
    update_flashcard_sm2(
        card_id=card_id,
        easiness_factor=updated["easiness_factor"],
        interval=updated["interval"],
        repetitions=updated["repetitions"],
        next_review=updated["next_review"],
        client_id=x_client_id,
    )

    return {"card_id": card_id, **updated}


@app.get("/api/flashcards")
async def get_flashcards(x_client_id: str = Header("default")):
    """Get all flashcards."""
    return [c for k, c in _flashcard_store.items() if k.startswith(f"{x_client_id}_")]


@app.get("/api/flashcards/due")
async def get_due_flashcards(x_client_id: str = Header("default")):
    """Get flashcards due for review."""
    from datetime import datetime
    now = datetime.now().isoformat()
    due = [c for k, c in _flashcard_store.items() if k.startswith(f"{x_client_id}_") and c.get("next_review", "") <= now]
    return due


# --- Dashboard Stats ---

@app.get("/api/dashboard/stats")
async def get_dashboard_stats(x_client_id: str = Header("default")):
    """Get dashboard statistics."""
    result = _results_store.get(f"{x_client_id}_latest")
    from datetime import datetime
    now = datetime.now().isoformat()

    my_cards = [c for k, c in _flashcard_store.items() if k.startswith(f"{x_client_id}_")]
    total_cards = len(my_cards)
    due_cards = len([c for c in my_cards if c.get("next_review", "") <= now])
    mastered = len([c for c in my_cards if c.get("repetitions", 0) >= 3])

    return {
        "total_concepts": len(result.concepts) if result else 0,
        "total_flashcards": total_cards,
        "due_for_review": due_cards,
        "mastered": mastered,
        "graph_nodes": len(result.graph_nodes) if result else 0,
        "graph_edges": len(result.graph_edges) if result else 0,
        "summary": result.summary if result else "",
    }


# --- Sessions History ---

@app.get("/api/sessions", response_model=list[SessionSummary])
async def list_sessions(x_client_id: str = Header("default")):
    """List all past processing sessions (newest first)."""
    return get_all_sessions(client_id=x_client_id)


@app.get("/api/sessions/{session_id}", response_model=ProcessingResult)
async def get_session(session_id: str, x_client_id: str = Header("default")):
    """Load a past session's full result by ID."""
    raw = get_session_result_json(session_id, client_id=x_client_id)
    if not raw:
        raise HTTPException(404, f"Session {session_id} not found")
    return ProcessingResult.model_validate_json(raw)


@app.delete("/api/sessions/{session_id}")
async def delete_session_endpoint(session_id: str, x_client_id: str = Header("default")):
    """Delete a session and all its flashcards from the database."""
    removed = delete_session(session_id, client_id=x_client_id)
    if not removed:
        raise HTTPException(404, f"Session {session_id} not found")
    
    # Also clear from in-memory stores if present
    _results_store.pop(f"{x_client_id}_{session_id}", None)
    
    # Remove associated flashcards for this client from memory
    keys_to_delete = [k for k, c in _flashcard_store.items() if k.startswith(f"{x_client_id}_") and c.get("session_id") == session_id]
    for k in keys_to_delete:
        _flashcard_store.pop(k, None)
        
    return {"deleted": session_id}


# --- Helper ---

def _persist_result(result: ProcessingResult, client_id: str):
    """Save result to SQLite and populate in-memory flashcard store."""
    title = (result.summary[:80] + "...") if len(result.summary) > 80 else result.summary or "Untitled"
    save_session(
        session_id=result.session_id,
        title=title,
        summary=result.summary,
        result_json=result.model_dump_json(),
        client_id=client_id,
    )
    for card in result.flashcards:
        card_dict = card.model_dump()
        card_dict["session_id"] = result.session_id
        _flashcard_store[f"{client_id}_{card.id}"] = card_dict
        save_flashcard(card_dict, session_id=result.session_id, client_id=client_id)


# --- SPA Static File Serving (For Azure Deployment) ---
# This must be at the very bottom so it doesn't override /api routes
if os.path.isdir(_frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(_frontend_dist, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str, request: Request):
        # Allow API routes to pass through (they would have been caught above if they existed,
        # but 404s for /api should return JSON, not the React app)
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="API route not found")

        # For any other route, serve the React index.html
        index_file = os.path.join(_frontend_dist, "index.html")
        if os.path.isfile(index_file):
            return FileResponse(index_file)
        raise HTTPException(status_code=404, detail="Frontend build not found")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
