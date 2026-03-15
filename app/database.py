from __future__ import annotations

import aiosqlite
from app.config import DB_PATH

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS pages (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    url          TEXT NOT NULL,
    label        TEXT DEFAULT '',
    window_start TEXT NOT NULL,
    window_end   TEXT NOT NULL,
    status       TEXT DEFAULT 'pending',
    last_error   TEXT,
    attempts     INTEGER DEFAULT 0,
    created_at   TEXT DEFAULT (datetime('now')),
    updated_at   TEXT DEFAULT (datetime('now'))
);
"""


async def get_db() -> aiosqlite.Connection:
    db = await aiosqlite.connect(str(DB_PATH))
    db.row_factory = aiosqlite.Row
    return db


async def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = await get_db()
    await db.execute(CREATE_TABLE)
    await db.commit()
    await db.close()


async def insert_page(url: str, label: str, window_start: str, window_end: str) -> dict:
    db = await get_db()
    cursor = await db.execute(
        "INSERT INTO pages (url, label, window_start, window_end) VALUES (?, ?, ?, ?)",
        (url, label, window_start, window_end),
    )
    await db.commit()
    row = await (await db.execute("SELECT * FROM pages WHERE id = ?", (cursor.lastrowid,))).fetchone()
    await db.close()
    return dict(row)


async def get_all_pages() -> list[dict]:
    db = await get_db()
    rows = await (await db.execute("SELECT * FROM pages ORDER BY id DESC")).fetchall()
    await db.close()
    return [dict(r) for r in rows]


async def get_page(page_id: int) -> dict | None:
    db = await get_db()
    row = await (await db.execute("SELECT * FROM pages WHERE id = ?", (page_id,))).fetchone()
    await db.close()
    return dict(row) if row else None


async def delete_page(page_id: int) -> bool:
    db = await get_db()
    cursor = await db.execute("DELETE FROM pages WHERE id = ?", (page_id,))
    await db.commit()
    await db.close()
    return cursor.rowcount > 0


async def update_page_status(page_id: int, status: str, last_error: str | None = None, inc_attempts: bool = False):
    db = await get_db()
    if inc_attempts:
        await db.execute(
            "UPDATE pages SET status = ?, last_error = ?, attempts = attempts + 1, updated_at = datetime('now') WHERE id = ?",
            (status, last_error, page_id),
        )
    else:
        await db.execute(
            "UPDATE pages SET status = ?, last_error = ?, updated_at = datetime('now') WHERE id = ?",
            (status, last_error, page_id),
        )
    await db.commit()
    await db.close()


async def get_pending_scheduled_pages() -> list[dict]:
    db = await get_db()
    rows = await (
        await db.execute("SELECT * FROM pages WHERE status IN ('pending', 'scheduled') ORDER BY window_start")
    ).fetchall()
    await db.close()
    return [dict(r) for r in rows]
