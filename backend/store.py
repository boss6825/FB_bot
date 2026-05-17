import json
import sqlite3
import threading
from collections.abc import Iterator, MutableMapping
from contextlib import contextmanager
from pathlib import Path
from typing import Any


DB = Path(__file__).parent / "storage" / "tasks.db"


class TaskRecord(dict):
    def __init__(self, store: "TaskStore", task_id: str, data: dict[str, Any]):
        super().__init__(data)
        self._store = store
        self._task_id = task_id

    def __setitem__(self, key: str, value: Any) -> None:
        super().__setitem__(key, value)
        self._store[self._task_id] = dict(self)

    def update(self, *args: Any, **kwargs: Any) -> None:
        super().update(*args, **kwargs)
        self._store[self._task_id] = dict(self)


class TaskStore(MutableMapping[str, dict[str, Any]]):
    """Small SQLite-backed mapping for task status polling."""

    def __init__(self, db_path: Path = DB):
        self.db_path = db_path
        self.db_path.parent.mkdir(exist_ok=True)
        self._lock = threading.RLock()
        self._init_db()

    def _init_db(self) -> None:
        with self._connection() as con:
            con.execute(
                """
                CREATE TABLE IF NOT EXISTS tasks (
                    id TEXT PRIMARY KEY,
                    data TEXT NOT NULL,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path, timeout=10)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        con = self._connect()
        try:
            yield con
            con.commit()
        finally:
            con.close()

    def __getitem__(self, task_id: str) -> TaskRecord:
        with self._lock, self._connection() as con:
            row = con.execute("SELECT data FROM tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise KeyError(task_id)
        return TaskRecord(self, task_id, json.loads(row[0]))

    def __setitem__(self, task_id: str, data: dict[str, Any]) -> None:
        payload = json.dumps(data)
        with self._lock, self._connection() as con:
            con.execute(
                """
                INSERT INTO tasks(id, data)
                VALUES(?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    data = excluded.data,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (task_id, payload),
            )

    def __delitem__(self, task_id: str) -> None:
        with self._lock, self._connection() as con:
            cur = con.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        if cur.rowcount == 0:
            raise KeyError(task_id)

    def __iter__(self) -> Iterator[str]:
        with self._lock, self._connection() as con:
            rows = con.execute("SELECT id FROM tasks ORDER BY updated_at DESC").fetchall()
        return iter(row[0] for row in rows)

    def __len__(self) -> int:
        with self._lock, self._connection() as con:
            row = con.execute("SELECT COUNT(*) FROM tasks").fetchone()
        return int(row[0])

    def __contains__(self, task_id: object) -> bool:
        if not isinstance(task_id, str):
            return False
        with self._lock, self._connection() as con:
            row = con.execute("SELECT 1 FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return row is not None
