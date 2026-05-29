from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS stage_state (
    source_id   TEXT NOT NULL,
    language    TEXT NOT NULL DEFAULT '',
    stage       TEXT NOT NULL,
    status      TEXT NOT NULL,
    artifact    TEXT,
    updated_at  TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (source_id, language, stage)
);

CREATE TABLE IF NOT EXISTS publish_log (
    youtube_id   TEXT PRIMARY KEY,
    source_id    TEXT NOT NULL,
    language     TEXT NOT NULL,
    fmt          TEXT NOT NULL,
    scheduled_at TEXT NOT NULL
);
"""


@contextmanager
def connect(db_path: str | Path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        yield conn
        conn.commit()
    finally:
        conn.close()


def set_status(conn, source_id, language, stage, status, artifact=None):
    conn.execute(
        """INSERT INTO stage_state (source_id, language, stage, status, artifact)
           VALUES (?, ?, ?, ?, ?)
           ON CONFLICT(source_id, language, stage)
           DO UPDATE SET status=excluded.status,
                         artifact=excluded.artifact,
                         updated_at=datetime('now')""",
        (source_id, language or "", stage, status, str(artifact) if artifact else None),
    )


def get_status(conn, source_id, language, stage):
    row = conn.execute(
        "SELECT status, artifact FROM stage_state WHERE source_id=? AND language=? AND stage=?",
        (source_id, language or "", stage),
    ).fetchone()
    return (row["status"], row["artifact"]) if row else (None, None)


def is_done(conn, source_id, language, stage) -> bool:
    status, _ = get_status(conn, source_id, language, stage)
    return status == "done"
