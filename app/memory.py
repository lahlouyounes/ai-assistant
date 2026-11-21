"""Mémoire conversationnelle (SQLite), isolée par identifiant de session + actions en attente."""
import json
import time
import uuid
from contextlib import contextmanager

from .config import settings
from .database import execute, open_connection


@contextmanager
def _db():
    con = open_connection(settings.memory_db)
    if settings.database_url:
        statements = [
            """CREATE TABLE IF NOT EXISTS messages(
                id BIGSERIAL PRIMARY KEY, session_id TEXT NOT NULL,
                role TEXT NOT NULL, content TEXT NOT NULL, ts DOUBLE PRECISION NOT NULL)""",
            "CREATE INDEX IF NOT EXISTS idx_msg_session ON messages(session_id, id)",
            """CREATE TABLE IF NOT EXISTS pending(
                id TEXT PRIMARY KEY, session_id TEXT NOT NULL, tool TEXT NOT NULL,
                args TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', ts DOUBLE PRECISION NOT NULL)""",
            """CREATE TABLE IF NOT EXISTS documents(
                id TEXT PRIMARY KEY, session_id TEXT NOT NULL, filename TEXT NOT NULL,
                content TEXT NOT NULL, pages INTEGER NOT NULL, ts DOUBLE PRECISION NOT NULL)""",
            "CREATE INDEX IF NOT EXISTS idx_doc_session ON documents(session_id, ts)",
        ]
        for statement in statements:
            con.execute(statement)
    else:
        con.executescript("""
        CREATE TABLE IF NOT EXISTS messages(
            id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
            role TEXT NOT NULL, content TEXT NOT NULL, ts REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_msg_session ON messages(session_id, id);
        CREATE TABLE IF NOT EXISTS pending(
            id TEXT PRIMARY KEY, session_id TEXT NOT NULL, tool TEXT NOT NULL,
            args TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', ts REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS documents(
            id TEXT PRIMARY KEY, session_id TEXT NOT NULL, filename TEXT NOT NULL,
            content TEXT NOT NULL, pages INTEGER NOT NULL, ts REAL NOT NULL);
        CREATE INDEX IF NOT EXISTS idx_doc_session ON documents(session_id, ts);
        """)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def save_message(session_id: str, role: str, content: str) -> None:
    with _db() as con:
        execute(con, "INSERT INTO messages(session_id, role, content, ts) VALUES (?,?,?,?)",
                    (session_id, role, content, time.time()))


def load_history(session_id: str) -> list[dict]:
    with _db() as con:
        rows = execute(con, "SELECT role, content FROM messages WHERE session_id=? ORDER BY id DESC LIMIT ?",
                           (session_id, settings.max_history)).fetchall()
    msgs = [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]
    while msgs and msgs[0]["role"] != "user":  # l'API exige de commencer par un message user
        msgs.pop(0)
    return msgs


def clear_session(session_id: str) -> None:
    with _db() as con:
        execute(con, "DELETE FROM messages WHERE session_id=?", (session_id,))
        execute(con, "DELETE FROM documents WHERE session_id=?", (session_id,))
        execute(con, "DELETE FROM pending WHERE session_id=?", (session_id,))


def add_document(session_id: str, filename: str, content: str, pages: int) -> dict:
    document = {"id": uuid.uuid4().hex, "filename": filename, "pages": pages, "ts": time.time()}
    with _db() as con:
        execute(con, "INSERT INTO documents(id, session_id, filename, content, pages, ts) VALUES (?,?,?,?,?,?)",
                    (document["id"], session_id, filename, content, pages, document["ts"]))
    return document


def list_documents(session_id: str) -> list[dict]:
    with _db() as con:
        rows = execute(con, "SELECT id, filename, pages, ts FROM documents WHERE session_id=? ORDER BY ts",
                           (session_id,)).fetchall()
    return [dict(row) for row in rows]


def load_documents_context(session_id: str, max_chars: int = 30000) -> str:
    with _db() as con:
        rows = execute(con, "SELECT filename, content FROM documents WHERE session_id=? ORDER BY ts",
                           (session_id,)).fetchall()
    sections = []
    used = 0
    for row in rows:
        section = f"\n--- PDF : {row['filename']} ---\n{row['content']}\n"
        remaining = max_chars - used
        if remaining <= 0:
            break
        sections.append(section[:remaining])
        used += min(len(section), remaining)
    return "".join(sections)


def delete_document(session_id: str, document_id: str) -> bool:
    with _db() as con:
        cursor = execute(con, "DELETE FROM documents WHERE id=? AND session_id=?", (document_id, session_id))
    return cursor.rowcount > 0


def add_pending(session_id: str, tool: str, args: dict) -> str:
    pid = uuid.uuid4().hex[:12]
    with _db() as con:
        execute(con, "INSERT INTO pending(id, session_id, tool, args, ts) VALUES (?,?,?,?,?)",
                    (pid, session_id, tool, json.dumps(args, ensure_ascii=False), time.time()))
    return pid


def get_pending(pid: str, session_id: str) -> dict | None:
    with _db() as con:
        r = execute(con, "SELECT * FROM pending WHERE id=? AND session_id=?", (pid, session_id)).fetchone()
    return dict(r) if r else None


def set_pending_status(pid: str, status: str) -> None:
    with _db() as con:
        execute(con, "UPDATE pending SET status=? WHERE id=?", (status, pid))
