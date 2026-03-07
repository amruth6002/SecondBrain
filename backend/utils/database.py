"""SQLite persistence layer for SecondBrain.

All results, sessions, and flashcard SM-2 state survive backend restarts.
Database file: secondbrain.db (in backend root, gitignored).
"""

import sqlite3
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
