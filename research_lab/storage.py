from __future__ import annotations
import json, sqlite3
from pathlib import Path
from datetime import datetime, timezone


def connect(path: str | Path = "data/research.sqlite") -> sqlite3.Connection:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("CREATE TABLE IF NOT EXISTS research_runs (id INTEGER PRIMARY KEY, created_at TEXT NOT NULL, question TEXT NOT NULL, report_json TEXT NOT NULL)")
    conn.commit()
    return conn


def save_report(report: dict, path: str | Path = "data/research.sqlite") -> int:
    with connect(path) as conn:
        cur = conn.execute("INSERT INTO research_runs(created_at, question, report_json) VALUES (?, ?, ?)",
                           (datetime.now(timezone.utc).isoformat(), report["question"], json.dumps(report, ensure_ascii=False)))
        return int(cur.lastrowid)


def recent_runs(path: str | Path = "data/research.sqlite", limit: int = 30) -> list[dict]:
    with connect(path) as conn:
        rows = conn.execute("SELECT id, created_at, question FROM research_runs ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return [{"id": r[0], "created_at": r[1], "question": r[2]} for r in rows]


def get_report(run_id: int, path: str | Path = "data/research.sqlite") -> dict | None:
    with connect(path) as conn:
        row = conn.execute("SELECT report_json FROM research_runs WHERE id=?", (run_id,)).fetchone()
    return json.loads(row[0]) if row else None
