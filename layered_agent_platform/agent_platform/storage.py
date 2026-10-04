"""SQLite access shared by the stateful layers. Each layer owns and creates its own tables."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path

_lock = threading.Lock()


def connect(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        db = sqlite3.connect(path, timeout=30, isolation_level=None, check_same_thread=False)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA busy_timeout=30000")
        db.execute("PRAGMA synchronous=FULL")
    return db
