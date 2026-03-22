"""MongoDB persistence layer for SecondBrain using Azure Cosmos DB vCore.

All results, sessions, and flashcard SM-2 state survive backend restarts.
"""

import json
import uuid
from typing import Optional
from pymongo import MongoClient

from config import settings

_CLIENT = None
_DB = None

def get_db():
    global _CLIENT, _DB
    if _CLIENT is None:
        if not settings.MONGODB_URI:
            raise ValueError("MONGODB_URI environment variable is not set")
        # Ensure we connect quickly to fail fast if configured incorrectly
        _CLIENT = MongoClient(settings.MONGODB_URI, serverSelectionTimeoutMS=5000)
        _DB = _CLIENT["secondbrain"]
    return _DB


def init_db():
    """Create collections and vector indexes."""
    db = get_db()
    
    # We create collections explicitly if they don't exist
    collections = db.list_collection_names()
    for coll in ["sessions", "flashcards", "notebooks", "blocks", "concepts", "graph_edges"]:
        if coll not in collections:
            db.create_collection(coll)
            
    # Create required indexes
    db.sessions.create_index("client_id")
    db.flashcards.create_index("client_id")
    db.flashcards.create_index("session_id")
    db.flashcards.create_index("next_review")
    db.notebooks.create_index("client_id")
    db.blocks.create_index("notebook_id")
    db.concepts.create_index("client_id")
    db.concepts.create_index("notebook_id")
    db.concepts.create_index("name")
    db.graph_edges.create_index("client_id")

    # Note: Cosmos DB MongoDB vCore vector index creation requires a specific command.
    # It must be created before inserting vectors or on an empty collection.
    # We will try to create it, ignoring errors if it already exists.
    try:
        db.command({
            "createIndexes": "concepts",
            "indexes": [{
                "name": "vectorSearchIndex",
                "key": { "embedding": "cosmosSearch" },
                "cosmosSearchOptions": {
                    "kind": "vector-ivf",
                    "numLists": 1,
                    "similarity": "COS",
                    "dimensions": 1536
                }
            }]
        })
        print("Vector search index configured successfully.")
    except Exception as e:
        # Ignore if index already exists
        pass


# ---- Helper for converting ObjectId/formatting back to dict
def _doc_to_dict(doc: dict) -> dict:
    if not doc:
        return doc
    d = dict(doc)
    d.pop("_id", None)
    return d


# ---- Sessions ----------------------------------------------------------------

def save_session(session_id: str, title: str, summary: str, result_json: str, client_id: str = "default"):
    db = get_db()
    from datetime import datetime
    doc = {
        "id": session_id,
        "created_at": datetime.utcnow().isoformat() + "Z",
        "title": title[:120],
        "summary": summary,
        "result_json": result_json,
        "client_id": client_id
    }
    db.sessions.update_one({"id": session_id, "client_id": client_id}, {"$set": doc}, upsert=True)

def get_all_sessions(client_id: str = "default") -> list[dict]:
    db = get_db()
    cursor = db.sessions.find({"client_id": client_id}, {"_id": 0, "id": 1, "created_at": 1, "title": 1, "summary": 1}).sort("created_at", -1).limit(20)
    return list(cursor)

def get_session_result_json(session_id: str, client_id: str = "default") -> Optional[str]:
    db = get_db()
    doc = db.sessions.find_one({"id": session_id, "client_id": client_id}, {"result_json": 1})
    return doc.get("result_json") if doc else None

def get_latest_session_result_json(client_id: str = "default") -> Optional[str]:
    db = get_db()
    doc = db.sessions.find_one({"client_id": client_id}, {"result_json": 1}, sort=[("created_at", -1)])
    return doc.get("result_json") if doc else None

def delete_session(session_id: str, client_id: str = "default") -> bool:
    db = get_db()
    db.flashcards.delete_many({"session_id": session_id, "client_id": client_id})
    res = db.sessions.delete_one({"id": session_id, "client_id": client_id})
    return res.deleted_count > 0


# ---- Flashcards --------------------------------------------------------------

def save_flashcard(card: dict, session_id: str, client_id: str = "default"):
    db = get_db()
    doc = {
        "id": card["id"],
        "session_id": session_id,
        "client_id": client_id,
        "question": card.get("question", ""),
        "answer": card.get("answer", ""),
        "concept_id": card.get("concept_id", ""),
        "bloom_level": card.get("bloom_level", "understand"),
        "source_excerpt": card.get("source_excerpt", ""),
        "easiness_factor": card.get("easiness_factor", 2.5),
        "interval": card.get("interval", 1),
        "repetitions": card.get("repetitions", 0),
        "next_review": card.get("next_review")
    }
    db.flashcards.update_one({"id": card["id"], "client_id": client_id}, {"$set": doc}, upsert=True)

def get_all_flashcards_from_db(client_id: str = "default") -> list[dict]:
    db = get_db()
    return [_doc_to_dict(d) for d in db.flashcards.find({"client_id": client_id})]

def update_flashcard_sm2(
    card_id: str,
    easiness_factor: float,
    interval: int,
    repetitions: int,
    next_review: str,
    client_id: str = "default"
):
    db = get_db()
    db.flashcards.update_one(
        {"id": card_id, "client_id": client_id},
        {"$set": {
            "easiness_factor": easiness_factor,
            "interval": interval,
            "repetitions": repetitions,
            "next_review": next_review
        }}
    )


# ── Notebooks ─────────────────────────────────────────────────────────────────

def create_notebook(notebook_id: str, name: str, client_id: str = "default") -> dict:
    db = get_db()
    from datetime import datetime
    now = datetime.utcnow().isoformat() + "Z"
    doc = {
        "id": notebook_id,
        "name": name,
        "created_at": now,
        "updated_at": now,
        "client_id": client_id
    }
    db.notebooks.insert_one(doc)
    return _doc_to_dict(doc)

def get_all_notebooks(client_id: str = "default") -> list[dict]:
    db = get_db()
    pipeline = [
        {"$match": {"client_id": client_id}},
        {"$lookup": {
            "from": "blocks",
            "localField": "id",
            "foreignField": "notebook_id",
            "as": "blocks_arr"
        }},
        {"$addFields": {
            "block_count": {"$size": "$blocks_arr"}
        }},
        {"$project": {
            "_id": 0, "blocks_arr": 0
        }},
        {"$sort": {"updated_at": -1}}
    ]
    return list(db.notebooks.aggregate(pipeline))

def get_notebook(notebook_id: str, client_id: str = "default") -> Optional[dict]:
    db = get_db()
    doc = db.notebooks.find_one({"id": notebook_id, "client_id": client_id})
    return _doc_to_dict(doc)

def rename_notebook(notebook_id: str, name: str, client_id: str = "default") -> bool:
    db = get_db()
    from datetime import datetime
    res = db.notebooks.update_one(
        {"id": notebook_id, "client_id": client_id},
        {"$set": {"name": name, "updated_at": datetime.utcnow().isoformat() + "Z"}}
    )
    return res.modified_count > 0

def delete_notebook(notebook_id: str, client_id: str = "default") -> bool:
    db = get_db()
    db.blocks.delete_many({"notebook_id": notebook_id})
    db.concepts.delete_many({"notebook_id": notebook_id, "client_id": client_id})
    db.graph_edges.delete_many({"notebook_id": notebook_id, "client_id": client_id})
    db.flashcards.delete_many({"notebook_id": notebook_id, "client_id": client_id})
    res = db.notebooks.delete_one({"id": notebook_id, "client_id": client_id})
    return res.deleted_count > 0


# ── Blocks ────────────────────────────────────────────────────────────────────

def add_block(block_id: str, notebook_id: str, block_type: str, title: str, content: str, position: int = 0):
    db = get_db()
    from datetime import datetime
    now = datetime.utcnow().isoformat() + "Z"
    
    if position == 0:
        doc = db.blocks.find_one({"notebook_id": notebook_id}, sort=[("position", -1)])
        position = (doc["position"] + 1) if doc else 1

    doc = {
        "id": block_id,
        "notebook_id": notebook_id,
        "block_type": block_type,
        "title": title,
        "content": content,
        "position": position,
        "created_at": now
    }
    db.blocks.insert_one(doc)
    db.notebooks.update_one({"id": notebook_id}, {"$set": {"updated_at": now}})

def get_blocks(notebook_id: str) -> list[dict]:
    db = get_db()
    cursor = db.blocks.find({"notebook_id": notebook_id}).sort("position", 1)
    return [_doc_to_dict(d) for d in cursor]

def delete_block(block_id: str) -> bool:
    db = get_db()
    from datetime import datetime
    doc = db.blocks.find_one({"id": block_id})
    if not doc:
        return False
        
    res = db.blocks.delete_one({"id": block_id})
    if res.deleted_count > 0:
        db.notebooks.update_one({"id": doc["notebook_id"]}, {"$set": {"updated_at": datetime.utcnow().isoformat() + "Z"}})
        return True
    return False


# ── Persistent Concepts ───────────────────────────────────────────────────────

def save_concepts_for_notebook(concepts: list[dict], notebook_id: str, client_id: str = "default"):
    db = get_db()
    from datetime import datetime
    now = datetime.utcnow().isoformat() + "Z"
    
    db.concepts.delete_many({"notebook_id": notebook_id, "client_id": client_id})
    
    docs = []
    for c in concepts:
        related = json.dumps(c.get("related_concepts", [])) if isinstance(c.get("related_concepts"), list) else c.get("related_concepts", "[]")
        doc = {
            "id": c.get("id", str(uuid.uuid4())[:8]),
            "notebook_id": notebook_id,
            "name": c["name"],
            "definition": c.get("definition", ""),
            "category": c.get("category", ""),
            "importance": c.get("importance", "medium"),
            "related_concepts": related,
            "source_context": c.get("source_context", ""),
            "embedding": c.get("embedding", []),  # New field!
            "created_at": now,
            "client_id": client_id
        }
        docs.append(doc)
        
    if docs:
        db.concepts.insert_many(docs)

def get_all_concepts(client_id: str = "default") -> list[dict]:
    db = get_db()
    cursor = db.concepts.find({"client_id": client_id}).sort("created_at", -1)
    result = []
    for d in cursor:
        d = _doc_to_dict(d)
        d.pop("embedding", None)  # Don't send embeddings to UI
        try:
            d["related_concepts"] = json.loads(d.get("related_concepts", "[]"))
        except Exception:
            d["related_concepts"] = []
        result.append(d)
    return result

def get_concepts_for_notebook(notebook_id: str, client_id: str = "default") -> list[dict]:
    db = get_db()
    cursor = db.concepts.find({"notebook_id": notebook_id, "client_id": client_id})
    result = []
    for d in cursor:
        d = _doc_to_dict(d)
        d.pop("embedding", None)
        try:
            d["related_concepts"] = json.loads(d.get("related_concepts", "[]"))
        except Exception:
            d["related_concepts"] = []
        result.append(d)
    return result

def search_concepts(query: str, client_id: str = "default") -> list[dict]:
    db = get_db()
    import re
    regex = re.compile(f".*{re.escape(query)}.*", re.IGNORECASE)
    cursor = db.concepts.find({
        "client_id": client_id,
        "$or": [{"name": regex}, {"definition": regex}]
    })
    result = []
    for d in cursor:
        d = _doc_to_dict(d)
        d.pop("embedding", None)
        try:
            d["related_concepts"] = json.loads(d.get("related_concepts", "[]"))
        except Exception:
            d["related_concepts"] = []
        result.append(d)
    return result

def search_concepts_by_embedding(embedding: list[float], limit: int = 5, client_id: str = "default", notebook_id: Optional[str] = None) -> list[dict]:
    """Perform a vector search using Cosmos DB MongoDB vCore $search."""
    db = get_db()
    match_stage = {"client_id": client_id}
    if notebook_id:
        match_stage["notebook_id"] = notebook_id
        
    pipeline = [
        {
            "$search": {
                "cosmosSearch": {
                    "vector": embedding,
                    "path": "embedding",
                    "k": limit,
                    "efSearch": 40
                },
                "returnStoredSource": True
            }
        },
        {
            "$match": match_stage
        },
        {
            "$project": {
                "similarityScore": { "$meta": "searchScore" },
                "document": "$$ROOT"
            }
        }
    ]
    cursor = db.concepts.aggregate(pipeline)
    result = []
    for doc_wrapper in cursor:
        doc = _doc_to_dict(doc_wrapper.get("document", {}))
        doc.pop("embedding", None)
        doc["similarity_score"] = doc_wrapper.get("similarityScore", 0)
        try:
            doc["related_concepts"] = json.loads(doc.get("related_concepts", "[]"))
        except Exception:
            doc["related_concepts"] = []
        result.append(doc)
    return result

# ── Persistent Graph Edges ────────────────────────────────────────────────────

def save_graph_edges_for_notebook(edges: list[dict], notebook_id: str, client_id: str = "default"):
    db = get_db()
    db.graph_edges.delete_many({"notebook_id": notebook_id, "client_id": client_id})
    
    docs = []
    for e in edges:
        doc = {
            "id": str(uuid.uuid4())[:8],
            "source_concept_id": e.get("source", ""),
            "target_concept_id": e.get("target", ""),
            "relationship": e.get("relationship", e.get("label", "")),
            "strength": e.get("strength", 0.5),
            "notebook_id": notebook_id,
            "client_id": client_id
        }
        docs.append(doc)
        
    if docs:
        db.graph_edges.insert_many(docs)

def get_all_graph_edges(client_id: str = "default") -> list[dict]:
    db = get_db()
    cursor = db.graph_edges.find({"client_id": client_id}).sort("strength", -1)
    return [_doc_to_dict(d) for d in cursor]

def get_graph_edges_for_notebook(notebook_id: str, client_id: str = "default") -> list[dict]:
    db = get_db()
    cursor = db.graph_edges.find({"notebook_id": notebook_id, "client_id": client_id})
    return [_doc_to_dict(d) for d in cursor]

def get_edges_for_concept_ids(concept_ids: list[str], client_id: str = "default") -> list[dict]:
    db = get_db()
    cursor = db.graph_edges.find({
        "client_id": client_id,
        "$or": [
            {"source_concept_id": {"$in": concept_ids}},
            {"target_concept_id": {"$in": concept_ids}}
        ]
    })
    return [_doc_to_dict(d) for d in cursor]


# ── Notebook-aware Flashcards ─────────────────────────────────────────────────

def save_flashcards_for_notebook(cards: list[dict], notebook_id: str, session_id: str, client_id: str = "default"):
    db = get_db()
    db.flashcards.delete_many({"notebook_id": notebook_id, "client_id": client_id})
    
    for card in cards:
        doc = {
            "id": card.get("id", str(uuid.uuid4())[:8]),
            "session_id": session_id,
            "notebook_id": notebook_id,
            "client_id": client_id,
            "question": card.get("question", ""),
            "answer": card.get("answer", ""),
            "concept_id": card.get("concept_id", ""),
            "bloom_level": card.get("bloom_level", "understand"),
            "source_excerpt": card.get("source_excerpt", ""),
            "easiness_factor": card.get("easiness_factor", 2.5),
            "interval": card.get("interval", 1),
            "repetitions": card.get("repetitions", 0),
            "next_review": card.get("next_review")
        }
        db.flashcards.update_one({"id": doc["id"], "client_id": client_id}, {"$set": doc}, upsert=True)

def get_flashcards_for_notebook(notebook_id: str, client_id: str = "default") -> list[dict]:
    db = get_db()
    cursor = db.flashcards.find({"notebook_id": notebook_id, "client_id": client_id})
    return [_doc_to_dict(d) for d in cursor]
