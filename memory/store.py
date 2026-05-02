from __future__ import annotations
import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent.parent / "data" / "memory.db"


class MemoryStore:
    """
    SQLite-backed store for:
    - Chunk index (queryable log of what happened)
    - Mandatory context (current state of the world, always 4-5 fields)
    """

    def __init__(self, db_path: Path = DB_PATH):
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._lock, self._conn() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS chunks (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT    NOT NULL,
                    window    TEXT    NOT NULL,
                    summary   TEXT    NOT NULL,
                    tags      TEXT    NOT NULL DEFAULT '[]',
                    source    TEXT    NOT NULL DEFAULT 'agent'
                );

                CREATE TABLE IF NOT EXISTS context (
                    key   TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_chunks_timestamp ON chunks(timestamp);
                CREATE INDEX IF NOT EXISTS idx_chunks_source    ON chunks(source);
            """)

    # ── Index ─────────────────────────────────────────────────────────────────

    def add_chunk(self, window: str, summary: str, tags: list[str], source: str = "agent") -> int:
        ts = datetime.now().isoformat(timespec="seconds")
        with self._lock, self._conn() as conn:
            cur = conn.execute(
                "INSERT INTO chunks (timestamp, window, summary, tags, source) VALUES (?,?,?,?,?)",
                (ts, window, summary, json.dumps(tags), source)
            )
            return cur.lastrowid

    def query_last(self, n: int = 10) -> list[dict]:
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM chunks ORDER BY id DESC LIMIT ?", (n,)
            ).fetchall()
        return [self._row_to_dict(r) for r in reversed(rows)]

    def query_tags(self, tags: list[str]) -> list[dict]:
        """Return chunks that contain ANY of the given tags."""
        with self._lock, self._conn() as conn:
            rows = conn.execute("SELECT * FROM chunks ORDER BY id").fetchall()
        results = []
        for row in rows:
            chunk_tags = json.loads(row["tags"])
            if any(t.lower() in [ct.lower() for ct in chunk_tags] for t in tags):
                results.append(self._row_to_dict(row))
        return results

    def query_since(self, since: str) -> list[dict]:
        """
        since: HH:MM  (today) or ISO datetime prefix
        """
        if len(since) == 5:  # HH:MM
            today = datetime.now().strftime("%Y-%m-%d")
            since = f"{today}T{since}:00"
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM chunks WHERE timestamp >= ? ORDER BY id",
                (since,)
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def query_window(self, window: str) -> list[dict]:
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT * FROM chunks WHERE window LIKE ? ORDER BY id",
                (f"%{window}%",)
            ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def all_chunks(self) -> list[dict]:
        with self._lock, self._conn() as conn:
            rows = conn.execute("SELECT * FROM chunks ORDER BY id").fetchall()
        return [self._row_to_dict(r) for r in rows]

    def chunk_count(self) -> int:
        with self._lock, self._conn() as conn:
            return conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]

    # ── Mandatory context ─────────────────────────────────────────────────────

    def set_context(self, context: dict):
        """Replace entire mandatory context."""
        with self._lock, self._conn() as conn:
            for key, value in context.items():
                conn.execute(
                    "INSERT OR REPLACE INTO context (key, value) VALUES (?,?)",
                    (key, json.dumps(value))
                )

    def get_context(self) -> dict:
        with self._lock, self._conn() as conn:
            rows = conn.execute("SELECT key, value FROM context").fetchall()
        return {r["key"]: json.loads(r["value"]) for r in rows}

    def update_context(self, partial: dict):
        """Update specific fields of mandatory context."""
        current = self.get_context()
        current.update(partial)
        self.set_context(current)

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _row_to_dict(row: sqlite3.Row) -> dict:
        d = dict(row)
        d["tags"] = json.loads(d["tags"])
        return d


# Global store instance
store = MemoryStore()
