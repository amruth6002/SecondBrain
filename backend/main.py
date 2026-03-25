"""SecondBrain — FastAPI Backend

Multi-agent AI system for student knowledge management.
Agents: Planner → Retriever → Executor
"""

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, HTTPException, Header, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from typing import Optional
import os

from config import settings
from models.schemas import ContentInput, ProcessingResult, PipelineStatus, SessionSummary, ChatRequest
from agents.orchestrator import run_pipeline, get_current_status
from services.pdf_service import extract_text_from_pdf
from services.youtube_service import extract_transcript
from utils.spaced_repetition import calculate_next_review
from utils.database import (
    init_db, save_session, get_all_sessions, get_session_result_json,
    get_latest_session_result_json, save_flashcard, get_all_flashcards_from_db,
    get_flashcard, update_flashcard_sm2, delete_session,
    create_notebook, get_all_notebooks, get_notebook as db_get_notebook,
    rename_notebook, delete_notebook,
    add_block as db_add_block, get_blocks, delete_block as db_delete_block,
    save_concepts_for_notebook, get_all_concepts, get_concepts_for_notebook,
    search_concepts, save_graph_edges_for_notebook, get_all_graph_edges,
    get_graph_edges_for_notebook, save_flashcards_for_notebook,
    get_flashcards_for_notebook,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize DB and restore last session into memory on startup."""
    init_db()
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
_processing_notebooks: dict[str, str] = {}  # notebook_id -> stage ("planner"|"retriever"|"executor")

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
        result = await run_pipeline(text, client_id=client_id)
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
            else:
                yield ": keepalive\n\n"
            await asyncio.sleep(1.0)

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
    card = get_flashcard(card_id, client_id=x_client_id)
    if not card:
        raise HTTPException(404, f"Flashcard {card_id} not found")

    updated = calculate_next_review(
        quality=quality,
        easiness_factor=card.get("easiness_factor", 2.5),
        interval=card.get("interval", 1),
        repetitions=card.get("repetitions", 0),
    )

    card.update(updated)

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
    return get_all_flashcards_from_db(client_id=x_client_id)


@app.get("/api/flashcards/due")
async def get_due_flashcards(x_client_id: str = Header("default")):
    """Get flashcards due for review."""
    from datetime import datetime
    now = datetime.now().isoformat()
    all_cards = get_all_flashcards_from_db(client_id=x_client_id)
    due = [c for c in all_cards if c.get("next_review", "") <= now]
    return due


# --- Dashboard Stats ---

@app.get("/api/dashboard/stats")
async def get_dashboard_stats(x_client_id: str = Header("default")):
    """Get dashboard statistics."""
    from datetime import datetime
    now = datetime.now().isoformat()

    # Get aggregate stats from DB
    all_concepts = get_all_concepts(client_id=x_client_id)
    all_edges = get_all_graph_edges(client_id=x_client_id)

    my_cards = get_all_flashcards_from_db(client_id=x_client_id)
    total_cards = len(my_cards)
    due_cards = len([c for c in my_cards if c.get("next_review", "") <= now])
    mastered = len([c for c in my_cards if c.get("repetitions", 0) >= 3])

    # Get recent sessions for a better summary
    recent_sessions = get_all_sessions(client_id=x_client_id)
    summary_text = "Your knowledge base is empty. Create a notebook and process some content to build your SecondBrain!"
    if recent_sessions:
        summary_text = "### Recent Extractions\n\n" + "\n\n---\n\n".join([f"**{s.title}**\n{s.summary}" for s in recent_sessions[:3]])

    return {
        "total_concepts": len(all_concepts),
        "total_flashcards": total_cards,
        "due_for_review": due_cards,
        "mastered": mastered,
        "graph_nodes": len(all_concepts),
        "graph_edges": len(all_edges),
        "summary": summary_text,
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


# --- Notebooks ----------------------------------------------------------------

@app.post("/api/notebooks")
async def create_notebook_endpoint(body: dict, x_client_id: str = Header("default")):
    nb_id = str(uuid.uuid4())[:8]
    name = body.get("name", "Untitled Notebook")
    nb = create_notebook(nb_id, name, x_client_id)
    return nb


@app.get("/api/notebooks")
async def list_notebooks(x_client_id: str = Header("default")):
    return get_all_notebooks(client_id=x_client_id)


@app.get("/api/notebooks/{notebook_id}")
async def get_notebook_detail(notebook_id: str, x_client_id: str = Header("default")):
    nb = db_get_notebook(notebook_id, x_client_id)
    if not nb:
        raise HTTPException(404, "Notebook not found")
    blocks = get_blocks(notebook_id)
    concepts_rows = get_concepts_for_notebook(notebook_id, x_client_id)
    flashcards = get_flashcards_for_notebook(notebook_id, x_client_id)
    edges = get_graph_edges_for_notebook(notebook_id, x_client_id)
    graph_nodes = [
        {"id": c["id"], "label": c["name"], "category": c.get("category", ""),
         "importance": c.get("importance", "medium"), "definition": c.get("definition", "")}
        for c in concepts_rows
    ]
    graph_edges = [
        {"source": e["source_concept_id"], "target": e["target_concept_id"],
         "label": e.get("relationship", ""), "strength": e.get("strength", 0.5)}
        for e in edges
    ]
    return {
        "id": nb["id"], "name": nb["name"],
        "created_at": nb.get("created_at", ""),
        "updated_at": nb.get("updated_at", ""),
        "blocks": blocks,
        "concepts": concepts_rows,
        "flashcards": flashcards,
        "graph_nodes": graph_nodes,
        "graph_edges": graph_edges,
    }


@app.put("/api/notebooks/{notebook_id}")
async def rename_notebook_endpoint(notebook_id: str, body: dict, x_client_id: str = Header("default")):
    name = body.get("name", "")
    if not name.strip():
        raise HTTPException(400, "Name is required")
    ok = rename_notebook(notebook_id, name, x_client_id)
    if not ok:
        raise HTTPException(404, "Notebook not found")
    return {"id": notebook_id, "name": name}


@app.delete("/api/notebooks/{notebook_id}")
async def delete_notebook_endpoint(notebook_id: str, x_client_id: str = Header("default")):
    ok = delete_notebook(notebook_id, x_client_id)
    if not ok:
        raise HTTPException(404, "Notebook not found")
    return {"deleted": notebook_id}


# --- Blocks -------------------------------------------------------------------

@app.post("/api/notebooks/{notebook_id}/blocks")
async def add_text_block(notebook_id: str, body: dict, x_client_id: str = Header("default")):
    nb = db_get_notebook(notebook_id, x_client_id)
    if not nb:
        raise HTTPException(404, "Notebook not found")
    title = body.get("title", "Text notes")
    content = body.get("content", "")
    if not content.strip():
        raise HTTPException(400, "Content is required")
    block_id = str(uuid.uuid4())[:8]
    db_add_block(block_id, notebook_id, "text", title, content)
    return {"id": block_id, "block_type": "text", "title": title}


@app.post("/api/notebooks/{notebook_id}/blocks/pdf")
async def add_pdf_block(notebook_id: str, file: UploadFile = File(...), x_client_id: str = Header("default")):
    nb = db_get_notebook(notebook_id, x_client_id)
    if not nb:
        raise HTTPException(404, "Notebook not found")
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(400, "Only PDF files")
    contents = await file.read()
    if len(contents) > settings.MAX_UPLOAD_SIZE_MB * 1024 * 1024:
        raise HTTPException(400, f"File too large. Max: {settings.MAX_UPLOAD_SIZE_MB}MB")
    text = extract_text_from_pdf(contents)
    if not text.strip():
        raise HTTPException(400, "Could not extract text from PDF.")
    block_id = str(uuid.uuid4())[:8]
    db_add_block(block_id, notebook_id, "pdf", file.filename or "PDF", text)
    return {"id": block_id, "block_type": "pdf", "title": file.filename}


@app.post("/api/notebooks/{notebook_id}/blocks/youtube")
async def add_youtube_block(notebook_id: str, body: dict, x_client_id: str = Header("default")):
    nb = db_get_notebook(notebook_id, x_client_id)
    if not nb:
        raise HTTPException(404, "Notebook not found")
    url = body.get("youtube_url", "")
    if not url:
        raise HTTPException(400, "youtube_url is required")
    try:
        transcript = extract_transcript(url)
    except ValueError as e:
        raise HTTPException(400, str(e))
    block_id = str(uuid.uuid4())[:8]
    title = f"YouTube: {url[:60]}"
    db_add_block(block_id, notebook_id, "youtube", title, transcript)
    return {"id": block_id, "block_type": "youtube", "title": title}


@app.delete("/api/blocks/{block_id}")
async def delete_block_endpoint(block_id: str):
    ok = db_delete_block(block_id)
    if not ok:
        raise HTTPException(404, "Block not found")
    return {"deleted": block_id}


# --- Process Notebook ---------------------------------------------------------

async def _run_notebook_pipeline_background(notebook_id: str, client_id: str):
    """Process all blocks in a notebook in the background."""
    _processing_notebooks[notebook_id] = "planner"
    try:
        blocks = get_blocks(notebook_id)
        combined = "\n\n---\n\n".join(
            f"[{b['block_type'].upper()}: {b['title']}]\n{b['content']}"
            for b in blocks if b.get("content")
        )
        if not combined.strip():
            return

        result = await run_pipeline(combined, notebook_id=notebook_id, client_id=client_id)

        if result.success:
            concepts_dicts = [c.model_dump() for c in result.concepts]
            save_concepts_for_notebook(concepts_dicts, notebook_id, client_id)

            edges_dicts = [e.model_dump() for e in result.graph_edges]
            save_graph_edges_for_notebook(edges_dicts, notebook_id, client_id)

            flashcard_dicts = [f.model_dump() for f in result.flashcards]
            save_flashcards_for_notebook(flashcard_dicts, notebook_id, result.session_id, client_id)

            _results_store[f"{client_id}_latest"] = result
            for card in result.flashcards:
                cd = card.model_dump()
                cd["session_id"] = result.session_id
                cd["notebook_id"] = notebook_id
                _flashcard_store[f"{client_id}_{card.id}"] = cd
    except Exception as e:
        print(f"[NOTEBOOK PIPELINE ERROR] {e}")
    finally:
        _processing_notebooks.pop(notebook_id, None)


@app.post("/api/notebooks/{notebook_id}/process")
async def process_notebook_endpoint(notebook_id: str, x_client_id: str = Header("default")):
    nb = db_get_notebook(notebook_id, x_client_id)
    if not nb:
        raise HTTPException(404, "Notebook not found")
    if notebook_id in _processing_notebooks:
        return {"status": "processing", "message": "Already processing."}
    blocks = get_blocks(notebook_id)
    if not blocks:
        raise HTTPException(400, "Notebook has no content blocks. Add some content first.")
    asyncio.create_task(_run_notebook_pipeline_background(notebook_id, x_client_id))
    return {"status": "processing", "message": "Pipeline started for notebook."}


@app.get("/api/notebooks/{notebook_id}/processing-status")
async def notebook_processing_status(notebook_id: str):
    """Check whether a notebook is currently being processed."""
    if notebook_id in _processing_notebooks:
        status = get_current_status()
        return {
            "processing": True,
            "stage": status.stage,
            "progress": status.progress,
            "message": status.message,
        }
    return {"processing": False}


# --- Knowledge (Cross-notebook) -----------------------------------------------

@app.get("/api/knowledge/concepts")
async def list_all_concepts(x_client_id: str = Header("default")):
    return get_all_concepts(client_id=x_client_id)


@app.get("/api/knowledge/graph")
async def get_full_knowledge_graph(x_client_id: str = Header("default")):
    concepts = get_all_concepts(client_id=x_client_id)
    edges = get_all_graph_edges(client_id=x_client_id)
    nodes = [
        {"id": c["id"], "label": c["name"], "category": c.get("category", ""),
         "importance": c.get("importance", "medium"), "definition": c.get("definition", "")}
        for c in concepts
    ]
    graph_edges = [
        {"source": e["source_concept_id"], "target": e["target_concept_id"],
         "label": e.get("relationship", ""), "strength": e.get("strength", 0.5)}
        for e in edges
    ]
    return {"nodes": nodes, "edges": graph_edges}


@app.get("/api/knowledge/search")
async def search_knowledge(q: str = Query(""), x_client_id: str = Header("default")):
    if not q.strip():
        return []
    return search_concepts(q, client_id=x_client_id)


# --- RAG Chat (Ask SecondBrain) -----------------------------------------------

@app.post("/api/chat")
async def rag_chat(req: ChatRequest, x_client_id: str = Header("default")):
    """Ask your SecondBrain a question using vector search across all notebooks."""
    if not req.query.strip():
        raise HTTPException(400, "Query cannot be empty")
        
    try:
        from utils.llm_client import get_embedding, call_llm_text
        from utils.database import search_concepts_by_embedding, get_edges_for_concept_ids, get_all_notebooks
        
        # 1. Embed user query
        query_embedding = await get_embedding(req.query)
        
        # 2. Search Cosmos DB for relevant concepts
        similar_concepts = search_concepts_by_embedding(
            query_embedding, 
            limit=5, 
            client_id=x_client_id, 
            notebook_id=req.notebook_id
        )
            
        # 3. Fetch all notebooks for naming context
        notebooks = get_all_notebooks(client_id=x_client_id)
        nb_dict = {nb["id"]: nb["name"] for nb in notebooks}
        
        # 4. Fetch related graph edges
        concept_ids = [c["id"] for c in similar_concepts if "id" in c]
        edges = get_edges_for_concept_ids(concept_ids, client_id=x_client_id) if concept_ids else []
        
        # 5. Build context
        context_str = "No relevant concepts found in the knowledge base."
        if similar_concepts:
            concept_strs = []
            for c in similar_concepts:
                nb_name = nb_dict.get(c.get("notebook_id"), "Unknown Notebook")
                concept_strs.append(f"Concept: {c['name']} (from notebook: '{nb_name}')\nDefinition: {c['definition']}\nSource Context: {c.get('source_context', '')}")
            
            edge_strs = []
            for e in edges:
                source_name = next((c["name"] for c in similar_concepts if c.get("id") == e["source_concept_id"]), "Unknown")
                target_name = next((c["name"] for c in similar_concepts if c.get("id") == e["target_concept_id"]), "Unknown")
                if source_name != "Unknown" and target_name != "Unknown":
                    edge_strs.append(f"- {source_name} --[{e.get('relationship', 'is related to')}]--> {target_name} (Strength: {e.get('strength', 0)})")
            
            context_str = "CONCEPTS:\n" + "\n\n".join(concept_strs)
            if edge_strs:
                context_str += "\n\nRELATIONSHIPS (Graph Edges):\n" + "\n".join(edge_strs)
            
        system_prompt = f"""You are SecondBrain, an AI learning assistant answering a student's question.
Use the provided knowledge base context to answer exactly and thoroughly. The context comes from various 'notebooks' created by the user. If the user asks about a specific 'notebook', refer to the concepts that came from that notebook name.

CRITICAL INSTRUCTIONS:
- You must synthesize an answer based on the concepts, definitions, and relationships provided.
- If the knowledge base context DOES NOT contain enough relevant information to answer (even partially), reply EXACTLY with: "I don't have enough extracted information in your SecondBrain to confidentally answer that." 
- Do NOT use outside knowledge if it's not in the context.

KNOWLEDGE BASE CONTEXT:
{context_str}
"""
        
        # 4. Generate Answer
        answer = await call_llm_text(system_prompt, req.query, temperature=0.3)
        
        return {
            "answer": answer,
            "sources": [{"name": c["name"], "similarity": c.get("similarity_score", 0)} for c in similar_concepts]
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Chat error: {str(e)}")


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
