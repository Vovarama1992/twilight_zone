from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional


SCHEMA_VERSION = 1


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS interests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    description TEXT NOT NULL DEFAULT '',
    weight REAL NOT NULL DEFAULT 0.5,
    status TEXT NOT NULL DEFAULT 'active',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS interest_edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_interest_id INTEGER NOT NULL REFERENCES interests(id) ON DELETE CASCADE,
    target_interest_id INTEGER NOT NULL REFERENCES interests(id) ON DELETE CASCADE,
    relation TEXT NOT NULL,
    weight REAL NOT NULL DEFAULT 0.5,
    evidence TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(source_interest_id, target_interest_id, relation)
);

CREATE TABLE IF NOT EXISTS day_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    energy TEXT NOT NULL DEFAULT 'normal',
    overload INTEGER NOT NULL DEFAULT 0,
    mode TEXT NOT NULL DEFAULT 'balanced',
    notes TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS analysis_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    summary TEXT NOT NULL,
    strategy_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS search_strategies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    status TEXT NOT NULL DEFAULT 'active',
    queries_json TEXT NOT NULL,
    rationale TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS candidate_materials (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    url TEXT NOT NULL UNIQUE,
    source TEXT NOT NULL DEFAULT '',
    snippet TEXT NOT NULL DEFAULT '',
    language TEXT NOT NULL DEFAULT 'unknown',
    score REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'new',
    evaluation_json TEXT NOT NULL DEFAULT '{}',
    discovered_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    material_id INTEGER REFERENCES candidate_materials(id) ON DELETE SET NULL,
    channel TEXT NOT NULL DEFAULT 'telegram',
    message TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    sent_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS reactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery_id INTEGER REFERENCES deliveries(id) ON DELETE SET NULL,
    reaction TEXT NOT NULL,
    raw_payload TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    body TEXT NOT NULL,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS kv_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_candidate_status_score
    ON candidate_materials(status, score DESC);

CREATE INDEX IF NOT EXISTS idx_deliveries_status
    ON deliveries(status, created_at);
"""


SEED_INTERESTS = [
    ("AI agents", "Agentic systems, LLM tooling, automation of intellectual work.", 0.9),
    ("Modern mathematics", "Category theory, algebraic geometry, HoTT, toposes, p-adic geometry.", 0.85),
    ("Engineering bridges", "Formal verification, DSLs, cryptography, ZK, math software.", 0.8),
    ("Startups", "Small strong teams, experimental products, research-to-product paths.", 0.75),
    ("Twilight Zone", "Unusual rigorous thinkers and ideas with a long aftertaste.", 0.7),
    ("Experimental music", "Drone, ambient, psychoacoustic and dark electronic landscapes.", 0.5),
]


class Database:
    def __init__(self, path: Path):
        self.path = path

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.executescript(SCHEMA_SQL)
            conn.execute("PRAGMA user_version = %d" % SCHEMA_VERSION)
            conn.execute(
                "INSERT OR IGNORE INTO day_state (id, energy, overload, mode) VALUES (1, 'normal', 0, 'balanced')"
            )
            conn.executemany(
                "INSERT OR IGNORE INTO interests (name, description, weight) VALUES (?, ?, ?)",
                SEED_INTERESTS,
            )
            self._seed_edges(conn)

    def _seed_edges(self, conn: sqlite3.Connection) -> None:
        ids = {
            row["name"]: row["id"]
            for row in conn.execute("SELECT id, name FROM interests").fetchall()
        }
        edges = [
            ("Modern mathematics", "Engineering bridges", "bridge", 0.8, "User values paths from deep math to tools."),
            ("AI agents", "Startups", "product", 0.7, "Research agent systems can become products."),
            ("AI agents", "Engineering bridges", "architecture", 0.75, "LLM systems need modular engineering."),
            ("Twilight Zone", "Modern mathematics", "aesthetic", 0.55, "Strange rigorous ideas often live near foundations."),
        ]
        for source, target, relation, weight, evidence in edges:
            if source in ids and target in ids:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO interest_edges
                        (source_interest_id, target_interest_id, relation, weight, evidence)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (ids[source], ids[target], relation, weight, evidence),
                )


class Repository:
    def __init__(self, db: Database):
        self.db = db

    def interests_snapshot(self) -> List[Dict[str, Any]]:
        with self.db.connect() as conn:
            rows = conn.execute(
                "SELECT name, description, weight, status FROM interests ORDER BY weight DESC, name"
            ).fetchall()
            return [dict(row) for row in rows]

    def day_state(self) -> Dict[str, Any]:
        with self.db.connect() as conn:
            row = conn.execute("SELECT energy, overload, mode, notes, updated_at FROM day_state WHERE id = 1").fetchone()
            return dict(row)

    def update_day_state(
        self,
        energy: Optional[str] = None,
        overload: Optional[bool] = None,
        mode: Optional[str] = None,
        notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        current = self.day_state()
        next_state = {
            "energy": energy or current["energy"],
            "overload": int(current["overload"] if overload is None else overload),
            "mode": mode or current["mode"],
            "notes": current["notes"] if notes is None else notes,
        }
        with self.db.connect() as conn:
            conn.execute(
                """
                UPDATE day_state
                SET energy = ?, overload = ?, mode = ?, notes = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = 1
                """,
                (next_state["energy"], next_state["overload"], next_state["mode"], next_state["notes"]),
            )
        return self.day_state()

    def record_analysis(self, kind: str, summary: str, strategy: Dict[str, Any]) -> int:
        with self.db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO analysis_runs (kind, summary, strategy_json) VALUES (?, ?, ?)",
                (kind, summary, json.dumps(strategy, ensure_ascii=False)),
            )
            return int(cur.lastrowid)

    def save_strategy(self, queries: Iterable[str], rationale: str) -> int:
        with self.db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO search_strategies (queries_json, rationale) VALUES (?, ?)",
                (json.dumps(list(queries), ensure_ascii=False), rationale),
            )
            return int(cur.lastrowid)

    def add_candidate(self, item: Dict[str, Any], evaluation: Dict[str, Any]) -> int:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO candidate_materials
                    (title, url, source, snippet, language, score, status, evaluation_json)
                VALUES (?, ?, ?, ?, ?, ?, 'new', ?)
                ON CONFLICT(url) DO UPDATE SET
                    title = excluded.title,
                    snippet = excluded.snippet,
                    source = excluded.source,
                    score = max(candidate_materials.score, excluded.score),
                    evaluation_json = excluded.evaluation_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    item.get("title", ""),
                    item["url"],
                    item.get("source", ""),
                    item.get("snippet", ""),
                    evaluation.get("language", "unknown"),
                    float(evaluation.get("score", 0)),
                    json.dumps(evaluation, ensure_ascii=False),
                ),
            )
            row = conn.execute("SELECT id FROM candidate_materials WHERE url = ?", (item["url"],)).fetchone()
            return int(row["id"])

    def best_candidate(self, min_score: float = 0.68) -> Optional[Dict[str, Any]]:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT * FROM candidate_materials
                WHERE status = 'new' AND score >= ?
                ORDER BY score DESC, discovered_at ASC
                LIMIT 1
                """,
                (min_score,),
            ).fetchone()
            return dict(row) if row else None

    def best_candidate_from_ids(
        self,
        material_ids: Iterable[int],
        min_score: float = 0.68,
        exclude_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        ids = [int(material_id) for material_id in material_ids]
        if not ids:
            return None
        placeholders = ",".join("?" for _ in ids)
        params: List[Any] = [*ids, min_score]
        exclude_clause = ""
        if exclude_id is not None:
            exclude_clause = "AND id != ?"
            params.append(int(exclude_id))
        with self.db.connect() as conn:
            row = conn.execute(
                f"""
                SELECT * FROM candidate_materials
                WHERE id IN ({placeholders}) AND score >= ? {exclude_clause}
                ORDER BY score DESC, discovered_at DESC
                LIMIT 1
                """,
                params,
            ).fetchone()
            return dict(row) if row else None

    def material_for_delivery(self, delivery_id: int) -> Optional[Dict[str, Any]]:
        with self.db.connect() as conn:
            row = conn.execute(
                """
                SELECT candidate_materials.*
                FROM deliveries
                JOIN candidate_materials ON candidate_materials.id = deliveries.material_id
                WHERE deliveries.id = ?
                LIMIT 1
                """,
                (delivery_id,),
            ).fetchone()
            return dict(row) if row else None

    def mark_candidate(self, material_id: int, status: str) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE candidate_materials SET status = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, material_id),
            )

    def queue_delivery(self, material_id: int, message: str) -> int:
        with self.db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO deliveries (material_id, message, status) VALUES (?, ?, 'queued')",
                (material_id, message),
            )
            return int(cur.lastrowid)

    def next_queued_delivery(self) -> Optional[Dict[str, Any]]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT * FROM deliveries WHERE status = 'queued' ORDER BY created_at LIMIT 1"
            ).fetchone()
            return dict(row) if row else None

    def delivery_by_id(self, delivery_id: int) -> Optional[Dict[str, Any]]:
        with self.db.connect() as conn:
            row = conn.execute("SELECT * FROM deliveries WHERE id = ?", (delivery_id,)).fetchone()
            return dict(row) if row else None

    def mark_delivery_sent(self, delivery_id: int) -> None:
        with self.db.connect() as conn:
            conn.execute(
                "UPDATE deliveries SET status = 'sent', sent_at = CURRENT_TIMESTAMP WHERE id = ?",
                (delivery_id,),
            )

    def latest_sent_delivery_at(self) -> Optional[str]:
        with self.db.connect() as conn:
            row = conn.execute(
                "SELECT sent_at FROM deliveries WHERE status = 'sent' AND sent_at IS NOT NULL ORDER BY sent_at DESC LIMIT 1"
            ).fetchone()
            return str(row["sent_at"]) if row else None

    def latest_reaction_at(self) -> Optional[str]:
        with self.db.connect() as conn:
            row = conn.execute("SELECT created_at FROM reactions ORDER BY created_at DESC LIMIT 1").fetchone()
            return str(row["created_at"]) if row else None

    def record_reaction(self, delivery_id: Optional[int], reaction: str, payload: Dict[str, Any]) -> int:
        with self.db.connect() as conn:
            cur = conn.execute(
                "INSERT INTO reactions (delivery_id, reaction, raw_payload) VALUES (?, ?, ?)",
                (delivery_id, reaction, json.dumps(payload, ensure_ascii=False)),
            )
            return int(cur.lastrowid)

    def set_kv(self, key: str, value: Any) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO kv_state (key, value) VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
                """,
                (key, json.dumps(value, ensure_ascii=False)),
            )

    def get_kv(self, key: str, default: Any = None) -> Any:
        with self.db.connect() as conn:
            row = conn.execute("SELECT value FROM kv_state WHERE key = ?", (key,)).fetchone()
            return json.loads(row["value"]) if row else default
