"""SQLite（aiosqlite + WAL）连接与轻量 DAO。

单机单用户场景，不引入 ORM；表结构一次性建齐（含后续里程碑需要的表）。
"""
import json
from contextlib import asynccontextmanager
from typing import Any

import aiosqlite

from .config import DB_PATH, ensure_dirs

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS voices (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    description   TEXT DEFAULT '',
    gender        TEXT DEFAULT '',
    tags          TEXT DEFAULT '[]',
    source        TEXT DEFAULT 'uploaded',   -- builtin | uploaded | cloned
    ref_audio_path   TEXT DEFAULT '',
    aux_refs         TEXT DEFAULT '[]',
    prompt_text      TEXT DEFAULT '',
    prompt_lang      TEXT DEFAULT 'zh',
    sample_audio_path TEXT DEFAULT '',
    provider_assets  TEXT DEFAULT '{}',
    created_at    TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at    TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS tasks (
    id            TEXT PRIMARY KEY,
    title         TEXT NOT NULL,
    mode          TEXT NOT NULL DEFAULT 'script',  -- script | dialogue
    voice_id      TEXT DEFAULT '',
    global_params TEXT DEFAULT '{}',
    created_at    TEXT DEFAULT (datetime('now', 'localtime')),
    updated_at    TEXT DEFAULT (datetime('now', 'localtime'))
);

CREATE TABLE IF NOT EXISTS roles (
    id       TEXT PRIMARY KEY,
    task_id  TEXT NOT NULL,
    name     TEXT NOT NULL,
    color    TEXT DEFAULT '#6366f1',
    voice_id TEXT DEFAULT '',
    params   TEXT DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS lines (
    id               TEXT PRIMARY KEY,
    task_id          TEXT NOT NULL,
    idx              INTEGER NOT NULL,
    role_id          TEXT DEFAULT '',
    text             TEXT NOT NULL,
    emotion          TEXT DEFAULT '',
    instruct         TEXT DEFAULT '',
    speed            REAL,
    pitch            REAL,
    volume           REAL,
    gap_after_ms     INTEGER,
    voice_override_id TEXT DEFAULT '',
    ai_suggestion    TEXT DEFAULT '',
    status           TEXT DEFAULT 'pending',  -- pending | synthesizing | done | failed
    audio_path       TEXT DEFAULT '',
    duration_ms      INTEGER,
    error            TEXT DEFAULT '',
    updated_at       TEXT DEFAULT (datetime('now', 'localtime'))
);
CREATE INDEX IF NOT EXISTS idx_lines_task ON lines(task_id, idx);

CREATE TABLE IF NOT EXISTS pronunciations (
    id        TEXT PRIMARY KEY,
    scope     TEXT NOT NULL DEFAULT 'global',  -- global | task
    task_id   TEXT DEFAULT '',
    find      TEXT NOT NULL,
    replace   TEXT NOT NULL,
    created_at TEXT DEFAULT (datetime('now', 'localtime'))
);
"""


@asynccontextmanager
async def connect():
    ensure_dirs()
    db = await aiosqlite.connect(DB_PATH)
    db.row_factory = aiosqlite.Row
    try:
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        yield db
        await db.commit()
    finally:
        await db.close()


async def init_db() -> None:
    async with connect() as db:
        await db.executescript(SCHEMA)


async def get_setting(key: str, default: Any = None) -> Any:
    async with connect() as db:
        cur = await db.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = await cur.fetchone()
    if row is None:
        return default
    return json.loads(row["value"])


async def set_setting(key: str, value: Any) -> None:
    async with connect() as db:
        await db.execute(
            "INSERT INTO settings(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value, ensure_ascii=False)),
        )


async def get_provider_config(provider_id: str) -> dict:
    return await get_setting(f"provider:{provider_id}", {}) or {}


async def save_provider_config(provider_id: str, config: dict) -> None:
    await set_setting(f"provider:{provider_id}", config)
