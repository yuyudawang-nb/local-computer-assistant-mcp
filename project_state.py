"""Durable, workspace-scoped tasks and explicitly saved project notes."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class ProjectState:
    def __init__(self, root: Path, base_dir: Path | None = None):
        digest = hashlib.sha256(str(root.resolve()).encode()).hexdigest()[:16]
        base = base_dir or Path.home() / ".local/share/local_research_mcp"
        self.directory = base / digest
        self.directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.directory.chmod(0o700)
        self.path = self.directory / "state.sqlite3"
        self.root = root.resolve()
        self._lock = threading.RLock()
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, detail TEXT NOT NULL,
                    status TEXT NOT NULL, worktree TEXT, created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS task_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT NOT NULL,
                    note TEXT NOT NULL, created_at TEXT NOT NULL,
                    FOREIGN KEY(task_id) REFERENCES tasks(id)
                );
                CREATE TABLE IF NOT EXISTS memories (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, content TEXT NOT NULL,
                    source TEXT NOT NULL, created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
            """)
        self.path.chmod(0o600)

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _task(row) -> dict:
        return dict(row)

    def create_task(self, title: str, detail: str = "") -> dict:
        title = title.strip()
        if not 1 <= len(title) <= 160 or len(detail) > 4000:
            raise ValueError("Task title must be 1-160 chars and detail at most 4000")
        task_id, now = uuid.uuid4().hex[:12], _now()
        with self._lock, self._connect() as db:
            db.execute("INSERT INTO tasks VALUES (?,?,?,?,?,?,?)",
                       (task_id, title, detail, "todo", None, now, now))
        return self.get_task(task_id)

    def get_task(self, task_id: str) -> dict:
        with self._lock, self._connect() as db:
            row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise ValueError("Unknown task ID")
            task = self._task(row)
            task["events"] = [dict(item) for item in db.execute(
                "SELECT note, created_at FROM task_events WHERE task_id=? ORDER BY id", (task_id,))]
            return task

    def list_tasks(self, status: str = "", limit: int = 50) -> list[dict]:
        if status and status not in {"todo", "in_progress", "done", "blocked"}:
            raise ValueError("Invalid task status")
        with self._lock, self._connect() as db:
            sql = "SELECT * FROM tasks" + (" WHERE status=?" if status else "") + " ORDER BY updated_at DESC, rowid DESC LIMIT ?"
            return [dict(row) for row in db.execute(sql, ((status,) if status else ()) + (max(1, min(limit, 100)),))]

    def update_task(self, task_id: str, status: str | None = None, note: str = "",
                    worktree: str | None = None) -> dict:
        if status is not None and status not in {"todo", "in_progress", "done", "blocked"}:
            raise ValueError("Invalid task status")
        if len(note) > 4000 or (worktree is not None and len(worktree) > 1000):
            raise ValueError("Note or worktree too long")
        with self._lock, self._connect() as db:
            row = db.execute("SELECT id FROM tasks WHERE id=?", (task_id,)).fetchone()
            if row is None:
                raise ValueError("Unknown task ID")
            now = _now()
            if status is not None:
                db.execute("UPDATE tasks SET status=?, updated_at=? WHERE id=?", (status, now, task_id))
            if worktree is not None:
                db.execute("UPDATE tasks SET worktree=?, updated_at=? WHERE id=?", (worktree, now, task_id))
            if note.strip():
                db.execute("INSERT INTO task_events(task_id,note,created_at) VALUES(?,?,?)",
                           (task_id, note.strip(), now))
                db.execute("UPDATE tasks SET updated_at=? WHERE id=?", (now, task_id))
        return self.get_task(task_id)

    def save_memory(self, title: str, content: str, source: str = "user") -> dict:
        title, content, source = title.strip(), content.strip(), source.strip()
        if not 1 <= len(title) <= 160 or not 1 <= len(content) <= 8000 or len(source) > 500:
            raise ValueError("Memory requires title 1-160, content 1-8000, source <=500 chars")
        memory_id, now = uuid.uuid4().hex[:12], _now()
        with self._lock, self._connect() as db:
            db.execute("INSERT INTO memories VALUES(?,?,?,?,?,?)",
                       (memory_id, title, content, source, now, now))
        return {"id": memory_id, "title": title, "content": content, "source": source,
                "created_at": now, "updated_at": now}

    def search_memories(self, query: str = "", limit: int = 20) -> list[dict]:
        query = query.strip().lower()[:200]
        with self._lock, self._connect() as db:
            rows = db.execute("SELECT * FROM memories ORDER BY updated_at DESC LIMIT 1000").fetchall()
        result = [dict(row) for row in rows if not query or query in (row["title"] + " " + row["content"] + " " + row["source"]).lower()]
        return result[:max(1, min(limit, 100))]

    def delete_memory(self, memory_id: str) -> dict:
        with self._lock, self._connect() as db:
            result = db.execute("DELETE FROM memories WHERE id=?", (memory_id,))
        return {"deleted": result.rowcount == 1, "id": memory_id}

    def export_context(self, max_chars: int = 12000) -> dict:
        tasks = self.list_tasks(limit=20)
        memories = self.search_memories(limit=50)
        payload = {"workspace": str(self.root), "tasks": tasks, "memories": memories,
                   "note": "Saved project context is user-managed; verify it against current files before editing."}
        encoded = json.dumps(payload, ensure_ascii=False)
        if len(encoded) > max_chars:
            payload["memories"] = memories[:10]
            payload["truncated"] = True
        return payload
