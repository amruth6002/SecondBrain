"""SQLite persistence layer for SecondBrain.

All results, sessions, and flashcard SM-2 state survive backend restarts.
Database file: secondbrain.db (in backend root, gitignored).
"""

import json
import sqlite3
import uuid
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent.parent / "secondbrain.db"


def get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Create tables if they don't exist and run simple migrations."""
    conn = get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS sessions (
            id          TEXT PRIMARY KEY,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            title       TEXT NOT NULL DEFAULT 'Untitled Session',
            summary     TEXT DEFAULT '',
            result_json TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS flashcards (
            id              TEXT PRIMARY KEY,
            session_id      TEXT NOT NULL,
            question        TEXT DEFAULT '',
            answer          TEXT DEFAULT '',
            concept_id      TEXT DEFAULT '',
            bloom_level     TEXT DEFAULT 'understand',
            source_excerpt  TEXT DEFAULT '',
            easiness_factor REAL    DEFAULT 2.5,
            interval        INTEGER DEFAULT 1,
            repetitions     INTEGER DEFAULT 0,
            next_review     TEXT,
            FOREIGN KEY (session_id) REFERENCES sessions(id)
        );

        CREATE INDEX IF NOT EXISTS idx_fc_session  ON flashcards(session_id);
        CREATE INDEX IF NOT EXISTS idx_fc_review   ON flashcards(next_review);

        /* ── Notebook-based knowledge management ── */

        CREATE TABLE IF NOT EXISTS notebooks (
            id          TEXT PRIMARY KEY,
            name        TEXT NOT NULL DEFAULT 'Untitled Notebook',
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
            client_id   TEXT NOT NULL DEFAULT 'default'
        );

        CREATE TABLE IF NOT EXISTS blocks (
            id          TEXT PRIMARY KEY,
            notebook_id TEXT NOT NULL,
            block_type  TEXT NOT NULL DEFAULT 'text',
            title       TEXT DEFAULT '',
            content     TEXT DEFAULT '',
            position    INTEGER DEFAULT 0,
            created_at  TEXT NOT NULL DEFAULT (datetime('now')),
            FOREIGN KEY (notebook_id) REFERENCES notebooks(id) ON DELETE CASCADE
        );

        CREATE TABLE IF NOT EXISTS concepts (
            id              TEXT PRIMARY KEY,
            notebook_id     TEXT,
            name            TEXT NOT NULL,
            definition      TEXT DEFAULT '',
            category        TEXT DEFAULT '',
            importance      TEXT DEFAULT 'medium',
            related_concepts TEXT DEFAULT '[]',
            source_context  TEXT DEFAULT '',
            created_at      TEXT NOT NULL DEFAULT (datetime('now')),
            client_id       TEXT NOT NULL DEFAULT 'default',
            FOREIGN KEY (notebook_id) REFERENCES notebooks(id) ON DELETE SET NULL
        );

        CREATE TABLE IF NOT EXISTS graph_edges (
            id                  TEXT PRIMARY KEY,
            source_concept_id   TEXT NOT NULL,
            target_concept_id   TEXT NOT NULL,
            relationship        TEXT DEFAULT '',
            strength            REAL DEFAULT 0.5,
            notebook_id         TEXT,
            client_id           TEXT NOT NULL DEFAULT 'default',
            FOREIGN KEY (notebook_id) REFERENCES notebooks(id) ON DELETE SET NULL
        );

        CREATE INDEX IF NOT EXISTS idx_notebooks_client ON notebooks(client_id);
        CREATE INDEX IF NOT EXISTS idx_blocks_notebook ON blocks(notebook_id);
        CREATE INDEX IF NOT EXISTS idx_concepts_client ON concepts(client_id);
        CREATE INDEX IF NOT EXISTS idx_concepts_notebook ON concepts(notebook_id);
        CREATE INDEX IF NOT EXISTS idx_concepts_name ON concepts(name);
        CREATE INDEX IF NOT EXISTS idx_edges_client ON graph_edges(client_id);
    """)
    
    # Graceful Migration: Add client_id if it doesn't exist
    try:
        conn.execute("ALTER TABLE sessions ADD COLUMN client_id TEXT DEFAULT 'default'")
    except sqlite3.OperationalError:
        pass  # Column already exists
    
    try:
        conn.execute("ALTER TABLE flashcards ADD COLUMN client_id TEXT DEFAULT 'default'")
    except sqlite3.OperationalError:
        pass

    try:
        conn.execute("CREATE INDEX idx_sessions_client ON sessions(client_id)")
        conn.execute("CREATE INDEX idx_flashcards_client ON flashcards(client_id)")
    except sqlite3.OperationalError:
        pass

    try:
        conn.execute("ALTER TABLE flashcards ADD COLUMN notebook_id TEXT DEFAULT NULL")
    except sqlite3.OperationalError:
        pass

    conn.commit()
    conn.close()


# ---- Sessions ----------------------------------------------------------------

def save_session(session_id: str, title: str, summary: str, result_json: str, client_id: str = "default"):
    conn = get_conn()
    conn.execute(
        """INSERT OR REPLACE INTO sessions (id, created_at, title, summary, result_json, client_id)
           VALUES (?, datetime('now'), ?, ?, ?, ?)""",
        (session_id, title[:120], summary, result_json, client_id),
    )
    conn.commit()
    conn.close()


def get_all_sessions(client_id: str = "default") -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT id, created_at, title, summary FROM sessions WHERE client_id = ? ORDER BY created_at DESC LIMIT 20",
        (client_id,)
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_session_result_json(session_id: str, client_id: str = "default") -> Optional[str]:
    conn = get_conn()
    row = conn.execute(
        "SELECT result_json FROM sessions WHERE id = ? AND client_id = ?", (session_id, client_id)
    ).fetchone()
    conn.close()
    return row["result_json"] if row else None


def get_latest_session_result_json(client_id: str = "default") -> Optional[str]:
    conn = get_conn()
    row = conn.execute(
        "SELECT result_json FROM sessions WHERE client_id = ? ORDER BY created_at DESC LIMIT 1",
        (client_id,)
    ).fetchone()
    conn.close()
    return row["result_json"] if row else None


def delete_session(session_id: str, client_id: str = "default") -> bool:
    """Delete a session and its flashcards for a specific client. Returns True if a row was deleted."""
    conn = get_conn()
    conn.execute("DELETE FROM flashcards WHERE session_id = ? AND client_id = ?", (session_id, client_id))
    cur = conn.execute("DELETE FROM sessions WHERE id = ? AND client_id = ?", (session_id, client_id))
    conn.commit()
    deleted = cur.rowcount > 0
    conn.close()
    return deleted


# ---- Flashcards --------------------------------------------------------------

def save_flashcard(card: dict, session_id: str, client_id: str = "default"):
    conn = get_conn()
    conn.execute(
        """INSERT OR REPLACE INTO flashcards
           (id, session_id, client_id, question, answer, concept_id, bloom_level, source_excerpt,
            easiness_factor, interval, repetitions, next_review)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            card["id"], session_id, client_id,
            card.get("question", ""), card.get("answer", ""),
            card.get("concept_id", ""), card.get("bloom_level", "understand"),
            card.get("source_excerpt", ""),
            card.get("easiness_factor", 2.5), card.get("interval", 1),
            card.get("repetitions", 0), card.get("next_review"),
        ),
    )
    conn.commit()
    conn.close()


def get_all_flashcards_from_db(client_id: str = "default") -> list[dict]:
    conn = get_conn()
    rows = conn.execute("SELECT * FROM flashcards WHERE client_id = ?", (client_id,)).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def update_flashcard_sm2(
    card_id: str,
    easiness_factor: float,
    interval: int,
    repetitions: int,
    next_review: str,
    client_id: str = "default"
):
    conn = get_conn()
    conn.execute(
        """UPDATE flashcards
           SET easiness_factor=?, interval=?, repetitions=?, next_review=?
           WHERE id=? AND client_id=?""",
        (easiness_factor, interval, repetitions, next_review, card_id, client_id),
    )
    conn.commit()
    conn.close()


# ── Notebooks ─────────────────────────────────────────────────────────────────

def create_notebook(notebook_id: str, name: str, client_id: str = "default") -> dict:
    conn = get_conn()
    conn.execute(
        "INSERT INTO notebooks (id, name, client_id) VALUES (?, ?, ?)",
        (notebook_id, name, client_id),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM notebooks WHERE id = ?", (notebook_id,)).fetchone()
    conn.close()
    return dict(row) if row else {}


def get_all_notebooks(client_id: str = "default") -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        """SELECT n.*, COUNT(b.id) as block_count
           FROM notebooks n LEFT JOIN blocks b ON b.notebook_id = n.id
           WHERE n.client_id = ?
           GROUP BY n.id
           ORDER BY n.updated_at DESC""",
        (client_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_notebook(notebook_id: str, client_id: str = "default") -> Optional[dict]:
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM notebooks WHERE id = ? AND client_id = ?",
        (notebook_id, client_id),
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def rename_notebook(notebook_id: str, name: str, client_id: str = "default") -> bool:
    conn = get_conn()
    cur = conn.execute(
        "UPDATE notebooks SET name = ?, updated_at = datetime('now') WHERE id = ? AND client_id = ?",
        (name, notebook_id, client_id),
    )
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok


def delete_notebook(notebook_id: str, client_id: str = "default") -> bool:
    conn = get_conn()
    conn.execute("DELETE FROM blocks WHERE notebook_id = ?", (notebook_id,))
    conn.execute("DELETE FROM concepts WHERE notebook_id = ? AND client_id = ?", (notebook_id, client_id))
    conn.execute("DELETE FROM graph_edges WHERE notebook_id = ? AND client_id = ?", (notebook_id, client_id))
    conn.execute("DELETE FROM flashcards WHERE notebook_id = ? AND client_id = ?", (notebook_id, client_id))
    cur = conn.execute("DELETE FROM notebooks WHERE id = ? AND client_id = ?", (notebook_id, client_id))
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok


# ── Blocks ────────────────────────────────────────────────────────────────────

def add_block(block_id: str, notebook_id: str, block_type: str, title: str, content: str, position: int = 0):
    conn = get_conn()
    if position == 0:
        row = conn.execute(
            "SELECT COALESCE(MAX(position), 0) + 1 as next_pos FROM blocks WHERE notebook_id = ?",
            (notebook_id,),
        ).fetchone()
        position = row["next_pos"]
    conn.execute(
        "INSERT INTO blocks (id, notebook_id, block_type, title, content, position) VALUES (?, ?, ?, ?, ?, ?)",
        (block_id, notebook_id, block_type, title, content, position),
    )
    conn.execute("UPDATE notebooks SET updated_at = datetime('now') WHERE id = ?", (notebook_id,))
    conn.commit()
    conn.close()


def get_blocks(notebook_id: str) -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM blocks WHERE notebook_id = ? ORDER BY position",
        (notebook_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def delete_block(block_id: str) -> bool:
    conn = get_conn()
    row = conn.execute("SELECT notebook_id FROM blocks WHERE id = ?", (block_id,)).fetchone()
    cur = conn.execute("DELETE FROM blocks WHERE id = ?", (block_id,))
    if row:
        conn.execute("UPDATE notebooks SET updated_at = datetime('now') WHERE id = ?", (row["notebook_id"],))
    conn.commit()
    ok = cur.rowcount > 0
    conn.close()
    return ok


# ── Persistent Concepts ───────────────────────────────────────────────────────

def save_concepts_for_notebook(concepts: list[dict], notebook_id: str, client_id: str = "default"):
    """Save extracted concepts, replacing any previous ones for this notebook."""
    conn = get_conn()
    conn.execute("DELETE FROM concepts WHERE notebook_id = ? AND client_id = ?", (notebook_id, client_id))
    for c in concepts:
        related = json.dumps(c.get("related_concepts", []))
        conn.execute(
            """INSERT INTO concepts (id, notebook_id, name, definition, category, importance,
               related_concepts, source_context, client_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (c.get("id", str(uuid.uuid4())[:8]), notebook_id, c["name"],
             c.get("definition", ""), c.get("category", ""),
             c.get("importance", "medium"), related,
             c.get("source_context", ""), client_id),
        )
    conn.commit()
    conn.close()


def get_all_concepts(client_id: str = "default") -> list[dict]:
    """Get all concepts across all notebooks for a client."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM concepts WHERE client_id = ? ORDER BY created_at DESC",
        (client_id,),
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["related_concepts"] = json.loads(d.get("related_concepts", "[]"))
        except Exception:
            d["related_concepts"] = []
        result.append(d)
    return result


def get_concepts_for_notebook(notebook_id: str, client_id: str = "default") -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM concepts WHERE notebook_id = ? AND client_id = ?",
        (notebook_id, client_id),
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["related_concepts"] = json.loads(d.get("related_concepts", "[]"))
        except Exception:
            d["related_concepts"] = []
        result.append(d)
    return result


def search_concepts(query: str, client_id: str = "default") -> list[dict]:
    """Search concepts by name or definition (case-insensitive)."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM concepts WHERE client_id = ? AND (name LIKE ? OR definition LIKE ?) ORDER BY importance DESC",
        (client_id, f"%{query}%", f"%{query}%"),
    ).fetchall()
    conn.close()
    result = []
    for r in rows:
        d = dict(r)
        try:
            d["related_concepts"] = json.loads(d.get("related_concepts", "[]"))
        except Exception:
            d["related_concepts"] = []
        result.append(d)
    return result


# ── Persistent Graph Edges ────────────────────────────────────────────────────

def save_graph_edges_for_notebook(edges: list[dict], notebook_id: str, client_id: str = "default"):
    """Save graph edges, replacing any previous ones for this notebook."""
    conn = get_conn()
    conn.execute("DELETE FROM graph_edges WHERE notebook_id = ? AND client_id = ?", (notebook_id, client_id))
    for e in edges:
        conn.execute(
            """INSERT INTO graph_edges (id, source_concept_id, target_concept_id,
               relationship, strength, notebook_id, client_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (str(uuid.uuid4())[:8], e.get("source", ""), e.get("target", ""),
             e.get("relationship", e.get("label", "")),
             e.get("strength", 0.5), notebook_id, client_id),
        )
    conn.commit()
    conn.close()


def get_all_graph_edges(client_id: str = "default") -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM graph_edges WHERE client_id = ? ORDER BY strength DESC",
        (client_id,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_graph_edges_for_notebook(notebook_id: str, client_id: str = "default") -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM graph_edges WHERE notebook_id = ? AND client_id = ?",
        (notebook_id, client_id),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Notebook-aware Flashcards ─────────────────────────────────────────────────

def save_flashcards_for_notebook(cards: list[dict], notebook_id: str, session_id: str, client_id: str = "default"):
    """Save flashcards for a notebook, replacing any previous ones."""
    conn = get_conn()
    conn.execute("DELETE FROM flashcards WHERE notebook_id = ? AND client_id = ?", (notebook_id, client_id))
    for card in cards:
        conn.execute(
            """INSERT OR REPLACE INTO flashcards
               (id, session_id, notebook_id, client_id, question, answer, concept_id,
                bloom_level, source_excerpt, easiness_factor, interval, repetitions, next_review)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (card.get("id", str(uuid.uuid4())[:8]), session_id, notebook_id, client_id,
             card.get("question", ""), card.get("answer", ""),
             card.get("concept_id", ""), card.get("bloom_level", "understand"),
             card.get("source_excerpt", ""),
             card.get("easiness_factor", 2.5), card.get("interval", 1),
             card.get("repetitions", 0), card.get("next_review")),
        )
    conn.commit()
    conn.close()


def get_flashcards_for_notebook(notebook_id: str, client_id: str = "default") -> list[dict]:
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM flashcards WHERE notebook_id = ? AND client_id = ?",
        (notebook_id, client_id),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
