from __future__ import annotations
import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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
                               
                CREATE TABLE IF NOT EXISTS user_data (
                category TEXT NOT NULL,
                key      TEXT NOT NULL,
                value    TEXT NOT NULL,
                PRIMARY KEY (category, key)
                );                  
                CREATE TABLE IF NOT EXISTS credentials (
                service  TEXT NOT NULL,
                key      TEXT NOT NULL,
                value    TEXT NOT NULL,
                PRIMARY KEY (service, key)
                );
                
                CREATE TABLE IF NOT EXISTS screen_entities (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    entity_id    TEXT NOT NULL UNIQUE,
                    name         TEXT NOT NULL,
                    llm_name     TEXT NOT NULL,
                    window_title TEXT NOT NULL,
                    window_class TEXT DEFAULT '',
                    bounds       TEXT NOT NULL,
                    source       TEXT NOT NULL DEFAULT 'locate_anything',
                    confidence   REAL DEFAULT 1.0,
                    created_at   TEXT NOT NULL,
                    last_seen    TEXT NOT NULL,
                    hit_count    INTEGER DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_entities_llm_window ON screen_entities(llm_name, window_title);
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

    def set_user_data(self, category: str, key: str, value: str):
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO user_data (category, key, value) VALUES (?,?,?)",
                (category, key, value)
            )

    def get_user_data(self, category: str, key: str) -> str | None:
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM user_data WHERE category=? AND key=?",
                (category, key)
            ).fetchone()
        return row["value"] if row else None

    def get_user_category(self, category: str) -> dict:
        with self._lock, self._conn() as conn:
            rows = conn.execute(
                "SELECT key, value FROM user_data WHERE category=?",
                (category,)
            ).fetchall()
        return {r["key"]: r["value"] for r in rows}

    def get_all_user_data(self, category: str | None = None) -> dict:
        with self._lock, self._conn() as conn:
            if category:
                rows = conn.execute(
                    "SELECT category, key, value FROM user_data WHERE category=?",
                    (category,)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT category, key, value FROM user_data"
                ).fetchall()

        result: dict = {}
        for r in rows:
            if r["category"] not in result:
                result[r["category"]] = {}
            result[r["category"]][r["key"]] = r["value"]
        return result

    def delete_user_data(self, category: str, key: str | None = None):
        with self._lock, self._conn() as conn:
            if key:
                conn.execute(
                    "DELETE FROM user_data WHERE category=? AND key=?",
                    (category, key)
                )
            else:
                conn.execute(
                    "DELETE FROM user_data WHERE category=?",
                    (category,)
                )

    # ── Credentials ────────────────────────────────────────────────────────────

    def set_credential(self, service: str, key: str, value: str):
        from core.crypto import encrypt
        encrypted = encrypt(value)
        with self._lock, self._conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO credentials (service, key, value) VALUES (?,?,?)",
                (service.lower(), key.lower(), encrypted)
            )

    def get_credential(self, service: str, key: str) -> str | None:
        from core.crypto import decrypt
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM credentials WHERE service=? AND key=?",
                (service.lower(), key.lower())
            ).fetchone()
        if not row:
            return None
        return decrypt(row["value"])

    def list_credentials(self, service: str | None = None) -> dict:
        with self._lock, self._conn() as conn:
            if service:
                rows = conn.execute(
                    "SELECT service, key FROM credentials WHERE service=?",
                    (service.lower(),)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT service, key FROM credentials"
                ).fetchall()
        result: dict = {}
        for r in rows:
            if r["service"] not in result:
                result[r["service"]] = []
            result[r["service"]].append(r["key"])
        return result

    def delete_credential(self, service: str, key: str | None = None):
        with self._lock, self._conn() as conn:
            if key:
                conn.execute(
                    "DELETE FROM credentials WHERE service=? AND key=?",
                    (service.lower(), key.lower())
                )
            else:
                conn.execute(
                    "DELETE FROM credentials WHERE service=?",
                    (service.lower(),)
                )

    # ── Screen entities ───────────────────────────────────────────────────────

    def register_screen_entity(
        self, entity_id: str, name: str, llm_name: str,
        window_title: str, window_class: str, bounds: dict,
        source: str, confidence: float
    ) -> int:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock, self._conn() as conn:
            cur = conn.execute(
                """INSERT OR REPLACE INTO screen_entities
                   (entity_id, name, llm_name, window_title, window_class,
                    bounds, source, confidence, created_at, last_seen, hit_count)
                   VALUES (?,?,?,?,?,?,?,?,?,?,1)""",
                (entity_id, name, llm_name, window_title, window_class,
                 json.dumps(bounds), source, confidence, now, now)
            )
            return cur.lastrowid

    def get_screen_entity(self, llm_name: str, window_title: str) -> dict | None:
        with self._lock, self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM screen_entities WHERE llm_name=? AND window_title=?",
                (llm_name, window_title)
            ).fetchone()
        if not row:
            return None
        return self._screen_entity_row(row)

    def find_screen_entities(
        self, llm_name: str, window_title: str | None = None
    ) -> list[dict]:
        with self._lock, self._conn() as conn:
            if window_title:
                rows = conn.execute(
                    "SELECT * FROM screen_entities WHERE llm_name LIKE ? AND window_title=?",
                    (f"%{llm_name}%", window_title)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM screen_entities WHERE llm_name LIKE ?",
                    (f"%{llm_name}%",)
                ).fetchall()
        return [self._screen_entity_row(r) for r in rows]

    def list_screen_entities(self, window_title: str | None = None) -> list[dict]:
        with self._lock, self._conn() as conn:
            if window_title:
                rows = conn.execute(
                    "SELECT * FROM screen_entities WHERE window_title LIKE ? ORDER BY last_seen DESC",
                    (f"%{window_title}%",)
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM screen_entities ORDER BY last_seen DESC"
                ).fetchall()
        return [self._screen_entity_row(r) for r in rows]

    def update_screen_entity_hit(self, entity_id: str):
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE screen_entities SET hit_count = hit_count + 1, last_seen=? WHERE entity_id=?",
                (now, entity_id)
            )

    def update_screen_entity_bounds(self, entity_id: str, bounds: dict):
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE screen_entities SET bounds=?, last_seen=? WHERE entity_id=?",
                (json.dumps(bounds), now, entity_id)
            )

    def update_screen_entity_llm_name(self, entity_id: str, llm_name: str):
        with self._lock, self._conn() as conn:
            conn.execute(
                "UPDATE screen_entities SET llm_name=? WHERE entity_id=?",
                (llm_name, entity_id)
            )

    def delete_screen_entity(self, entity_id: str):
        with self._lock, self._conn() as conn:
            conn.execute(
                "DELETE FROM screen_entities WHERE entity_id=?",
                (entity_id,)
            )

    @staticmethod
    def _screen_entity_row(row: sqlite3.Row) -> dict:
        d = dict(row)
        d["bounds"] = json.loads(d["bounds"])
        return d

store = MemoryStore()