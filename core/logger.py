from __future__ import annotations
import json
import logging
import sqlite3
import threading
from datetime import datetime
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "logs.db"


class DBHandler(logging.Handler):
    """Logging handler que escribe a SQLite."""

    def __init__(self, db_path: Path = DB_PATH):
        super().__init__()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._path = db_path
        self._lock = threading.Lock()
        self._init_db()

    def _init_db(self):
        with self._lock, sqlite3.connect(self._path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS logs (
                    id        INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT    NOT NULL,
                    level     TEXT    NOT NULL,
                    module    TEXT    NOT NULL,
                    message   TEXT    NOT NULL,
                    extra     TEXT
                )
            """)

    def emit(self, record: logging.LogRecord):
        try:
            extra = None
            if hasattr(record, "extra"):
                extra = json.dumps(record.extra, ensure_ascii=False)

            with self._lock, sqlite3.connect(self._path) as conn:
                conn.execute(
                    "INSERT INTO logs (timestamp, level, module, message, extra) VALUES (?,?,?,?,?)",
                    (
                        datetime.now().isoformat(timespec="seconds"),
                        record.levelname,
                        record.module,
                        record.getMessage(),
                        extra,
                    )
                )
        except Exception:
            pass  # logging nunca debe romper el programa


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        # Consola — solo WARNING y arriba
        ch = logging.StreamHandler()
        ch.setLevel(logging.WARNING)
        ch.setFormatter(logging.Formatter("[%(module)s] %(levelname)s: %(message)s"))
        logger.addHandler(ch)
        # SQLite — todo
        logger.addHandler(DBHandler())
    return logger