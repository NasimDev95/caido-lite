"""SQLite-backed traffic history (the HTTP History of Caido Lite)."""

import json
import sqlite3
import threading
import time

SCHEMA = """
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created REAL NOT NULL,
    method TEXT NOT NULL,
    scheme TEXT NOT NULL,
    host TEXT NOT NULL,
    port INTEGER NOT NULL,
    path TEXT NOT NULL,
    url TEXT NOT NULL,
    req_headers TEXT NOT NULL,
    req_body BLOB,
    status INTEGER,
    reason TEXT,
    resp_headers TEXT,
    resp_body BLOB,
    duration_ms REAL,
    error TEXT,
    source TEXT NOT NULL DEFAULT 'proxy'
);
CREATE INDEX IF NOT EXISTS idx_tx_created ON transactions(created);
"""

SUMMARY_COLUMNS = (
    "id, created, method, scheme, host, port, path, url, status, reason, "
    "duration_ms, error, source, length(resp_body) AS resp_length, "
    "length(req_body) AS req_length"
)


class Store:
    def __init__(self, path):
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._db.executescript(SCHEMA)

    def _execute(self, sql, params=()):
        with self._lock:
            cur = self._db.execute(sql, params)
            self._db.commit()
            return cur

    def start(self, *, method, scheme, host, port, path, url, req_headers, req_body, source):
        cur = self._execute(
            "INSERT INTO transactions (created, method, scheme, host, port, path, url, "
            "req_headers, req_body, source) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (time.time(), method, scheme, host, port, path, url,
             json.dumps(req_headers), req_body or None, source),
        )
        return cur.lastrowid

    def finish(self, tx_id, *, status, reason, resp_headers, resp_body, duration_ms):
        self._execute(
            "UPDATE transactions SET status=?, reason=?, resp_headers=?, resp_body=?, "
            "duration_ms=? WHERE id=?",
            (status, reason, json.dumps(resp_headers), resp_body, duration_ms, tx_id),
        )

    def fail(self, tx_id, error, duration_ms):
        self._execute(
            "UPDATE transactions SET error=?, duration_ms=? WHERE id=?",
            (error, duration_ms, tx_id),
        )

    def search(self, *, query="", method="", limit=500, offset=0):
        clauses, params = [], []
        if query:
            clauses.append("(url LIKE ? OR host LIKE ? OR path LIKE ?)")
            like = "%" + query + "%"
            params += [like, like, like]
        if method:
            clauses.append("method = ?")
            params.append(method.upper())
        sql = "SELECT " + SUMMARY_COLUMNS + " FROM transactions"
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY id DESC LIMIT ? OFFSET ?"
        params += [int(limit), int(offset)]
        with self._lock:
            rows = self._db.execute(sql, params).fetchall()
        return [dict(row) for row in rows]

    def get(self, tx_id):
        with self._lock:
            row = self._db.execute("SELECT * FROM transactions WHERE id = ?", (tx_id,)).fetchone()
        if row is None:
            return None
        data = dict(row)
        data["req_headers"] = json.loads(data["req_headers"] or "[]")
        data["resp_headers"] = json.loads(data["resp_headers"]) if data["resp_headers"] else None
        return data

    def count(self):
        with self._lock:
            return self._db.execute("SELECT COUNT(*) FROM transactions").fetchone()[0]

    def clear(self):
        self._execute("DELETE FROM transactions")
