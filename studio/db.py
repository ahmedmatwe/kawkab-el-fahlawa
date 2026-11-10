"""SQLite state. The file lives in data/studio.db and is persisted on the `state` git branch
between cloud runs, so every stage can resume after a crash or a new runner."""
from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

from .config import DATA, redact

SCHEMA = """
CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS trends (
  id INTEGER PRIMARY KEY, day TEXT, title TEXT, source TEXT, url TEXT, published TEXT,
  category TEXT, score REAL, risk TEXT, verified INTEGER DEFAULT 0, evidence TEXT, created REAL);
CREATE TABLE IF NOT EXISTS episodes (
  id INTEGER PRIMARY KEY, day TEXT, status TEXT, mode TEXT, idea TEXT, trend_id INTEGER,
  script TEXT, storyboard TEXT, review TEXT, score REAL, final_path TEXT, error TEXT,
  attempts INTEGER DEFAULT 0, cost_usd REAL DEFAULT 0, created REAL, updated REAL);
CREATE TABLE IF NOT EXISTS ideas (
  id INTEGER PRIMARY KEY, day TEXT, episode_id INTEGER, data TEXT, status TEXT, message_id INTEGER, created REAL);
CREATE TABLE IF NOT EXISTS script_versions (
  id INTEGER PRIMARY KEY, episode_id INTEGER, version INTEGER, data TEXT, review TEXT, score REAL, created REAL);
CREATE TABLE IF NOT EXISTS shots (
  id INTEGER PRIMARY KEY, episode_id INTEGER, idx INTEGER, data TEXT, prompt TEXT, status TEXT,
  attempts INTEGER DEFAULT 0, video_path TEXT, audio_path TEXT, error TEXT, UNIQUE(episode_id, idx));
CREATE TABLE IF NOT EXISTS assets (
  id INTEGER PRIMARY KEY, episode_id INTEGER, shot_idx INTEGER, kind TEXT, path TEXT,
  provider TEXT, meta TEXT, created REAL);
CREATE TABLE IF NOT EXISTS generation_jobs (
  id INTEGER PRIMARY KEY, episode_id INTEGER, provider TEXT, external_id TEXT, status TEXT,
  meta TEXT, started REAL, finished REAL);
CREATE TABLE IF NOT EXISTS agent_tasks (
  id INTEGER PRIMARY KEY, episode_id INTEGER, agent TEXT, status TEXT, decision TEXT,
  output TEXT, error TEXT, started REAL, finished REAL);
CREATE TABLE IF NOT EXISTS approvals (
  id INTEGER PRIMARY KEY, episode_id INTEGER, kind TEXT, decision TEXT, by_whom TEXT, note TEXT, created REAL);
CREATE TABLE IF NOT EXISTS publish_jobs (
  id INTEGER PRIMARY KEY, episode_id INTEGER, platform TEXT, status TEXT, post_id TEXT, url TEXT,
  error TEXT, created REAL, UNIQUE(episode_id, platform));
CREATE TABLE IF NOT EXISTS budget (
  id INTEGER PRIMARY KEY, episode_id INTEGER, provider TEXT, units REAL, usd REAL, note TEXT, created REAL);
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY, episode_id INTEGER, actor TEXT, action TEXT, detail TEXT, created REAL);
"""


def db_path() -> Path:
    return DATA / "studio.db"


@contextmanager
def connect(path: Optional[Path] = None) -> Iterator[sqlite3.Connection]:
    p = path or db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(p)
    con.row_factory = sqlite3.Row
    con.executescript(SCHEMA)
    try:
        yield con
        con.commit()
    finally:
        con.close()


def now() -> float:
    return time.time()


def kv_get(con: sqlite3.Connection, k: str, default: str = "") -> str:
    r = con.execute("SELECT v FROM kv WHERE k=?", (k,)).fetchone()
    return r["v"] if r else default


def kv_set(con: sqlite3.Connection, k: str, v: Any) -> None:
    con.execute("INSERT INTO kv(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, str(v)))


def audit(con: sqlite3.Connection, episode_id: Optional[int], actor: str, action: str, detail: Any = "") -> None:
    if not isinstance(detail, str):
        detail = json.dumps(detail, ensure_ascii=False)
    con.execute("INSERT INTO audit_log(episode_id,actor,action,detail,created) VALUES(?,?,?,?,?)",
                (episode_id, actor, action, redact(detail)[:4000], now()))


def episode(con: sqlite3.Connection, eid: int) -> sqlite3.Row:
    r = con.execute("SELECT * FROM episodes WHERE id=?", (eid,)).fetchone()
    if not r:
        raise KeyError(eid)
    return r


def set_status(con: sqlite3.Connection, eid: int, status: str, **fields: Any) -> None:
    cols = ["status=?", "updated=?"]
    vals: list = [status, now()]
    if "error" not in fields and status not in ("FAILED", "MANUAL_ACTION_REQUIRED"):
        fields["error"] = None  # a stage succeeded → the previous (retried) error is no longer current
    for k, v in fields.items():
        cols.append(f"{k}=?")
        vals.append(json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v)
    vals.append(eid)
    con.execute(f"UPDATE episodes SET {', '.join(cols)} WHERE id=?", vals)
    audit(con, eid, "orchestrator", "status", status)


def jload(s: Optional[str], default: Any = None) -> Any:
    if not s:
        return default
    try:
        return json.loads(s)
    except Exception:
        return default
