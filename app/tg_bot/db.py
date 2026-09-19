"""SQLite: лимиты бесплатных разборов + безлимит 24ч."""
from __future__ import annotations

import aiosqlite
from datetime import datetime, timezone, timedelta

SCHEMA = """
CREATE TABLE IF NOT EXISTS usage (
    user_id       INTEGER PRIMARY KEY,
    last_date     TEXT,
    count_today   INTEGER NOT NULL DEFAULT 0,
    unlimited_until TEXT
);
CREATE TABLE IF NOT EXISTS payments (
    charge_id   TEXT PRIMARY KEY,
    user_id     INTEGER NOT NULL,
    stars       INTEGER NOT NULL,
    created_at  TEXT NOT NULL
);
"""


class DB:
    def __init__(self, path: str) -> None:
        self.path = path

    async def init(self) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.executescript(SCHEMA)
            await db.commit()

    async def _get(self, user_id: int) -> dict:
        async with aiosqlite.connect(self.path) as db:
            db.row_factory = aiosqlite.Row
            cur = await db.execute(
                "SELECT user_id, last_date, count_today, unlimited_until FROM usage WHERE user_id = ?",
                (user_id,),
            )
            row = await cur.fetchone()
            if not row:
                return {"user_id": user_id, "last_date": None, "count_today": 0, "unlimited_until": None}
            return dict(row)

    async def is_unlimited(self, user_id: int) -> bool:
        row = await self._get(user_id)
        raw = row.get("unlimited_until")
        if not raw:
            return False
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return False
        return dt > datetime.now(timezone.utc)

    async def can_use_free(self, user_id: int, daily_limit: int) -> bool:
        row = await self._get(user_id)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if row["last_date"] != today:
            return True
        return (row["count_today"] or 0) < daily_limit

    async def register_use(self, user_id: int) -> None:
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT last_date, count_today FROM usage WHERE user_id = ?", (user_id,))
            row = await cur.fetchone()
            if row is None:
                await db.execute(
                    "INSERT INTO usage (user_id, last_date, count_today) VALUES (?, ?, 1)",
                    (user_id, today),
                )
            elif row[0] == today:
                await db.execute(
                    "UPDATE usage SET count_today = count_today + 1 WHERE user_id = ?",
                    (user_id,),
                )
            else:
                await db.execute(
                    "UPDATE usage SET last_date = ?, count_today = 1 WHERE user_id = ?",
                    (today, user_id),
                )
            await db.commit()

    async def grant_unlimited(self, user_id: int, hours: int = 24) -> datetime:
        until = datetime.now(timezone.utc) + timedelta(hours=hours)
        async with aiosqlite.connect(self.path) as db:
            cur = await db.execute("SELECT user_id FROM usage WHERE user_id = ?", (user_id,))
            row = await cur.fetchone()
            if row is None:
                await db.execute(
                    "INSERT INTO usage (user_id, unlimited_until) VALUES (?, ?)",
                    (user_id, until.isoformat()),
                )
            else:
                await db.execute(
                    "UPDATE usage SET unlimited_until = ? WHERE user_id = ?",
                    (until.isoformat(), user_id),
                )
            await db.commit()
        return until

    async def save_payment(self, charge_id: str, user_id: int, stars: int) -> None:
        async with aiosqlite.connect(self.path) as db:
            await db.execute(
                "INSERT OR IGNORE INTO payments (charge_id, user_id, stars, created_at) VALUES (?, ?, ?, ?)",
                (charge_id, user_id, stars, datetime.now(timezone.utc).isoformat()),
            )
            await db.commit()
