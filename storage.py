"""Хранилище на SQLite: пользователи и счёта. Без внешней БД, файл рядом с ботом."""
import time
from typing import Any

import aiosqlite

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    tg_id      INTEGER PRIMARY KEY,
    username   TEXT,
    first_name TEXT,
    email      TEXT,
    paid       INTEGER NOT NULL DEFAULT 0,
    created_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS invoices (
    id          TEXT PRIMARY KEY,
    tg_id       INTEGER NOT NULL,
    email       TEXT NOT NULL,
    currency    TEXT NOT NULL,
    method      TEXT NOT NULL,
    amount      REAL,
    status      TEXT NOT NULL DEFAULT 'new',
    payment_url TEXT,
    created_at  INTEGER NOT NULL,
    paid_at     INTEGER
);

CREATE INDEX IF NOT EXISTS idx_invoices_status ON invoices(status);
CREATE INDEX IF NOT EXISTS idx_invoices_email  ON invoices(email);
"""


class Storage:
    def __init__(self, path: str):
        self._path = path
        self._db: aiosqlite.Connection | None = None

    async def init(self) -> None:
        self._db = await aiosqlite.connect(self._path)
        self._db.row_factory = aiosqlite.Row
        await self._db.executescript(_SCHEMA)
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()

    @property
    def db(self) -> aiosqlite.Connection:
        assert self._db is not None, "Storage.init() не вызван"
        return self._db

    # --- Пользователи -------------------------------------------------------
    async def upsert_user(self, tg_id: int, username: str | None, first_name: str | None) -> None:
        await self.db.execute(
            """INSERT INTO users (tg_id, username, first_name, created_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(tg_id) DO UPDATE SET username=excluded.username,
                                                first_name=excluded.first_name""",
            (tg_id, username, first_name, int(time.time())),
        )
        await self.db.commit()

    async def set_email(self, tg_id: int, email: str) -> None:
        await self.db.execute("UPDATE users SET email=? WHERE tg_id=?", (email, tg_id))
        await self.db.commit()

    async def get_email(self, tg_id: int) -> str | None:
        async with self.db.execute("SELECT email FROM users WHERE tg_id=?", (tg_id,)) as cur:
            row = await cur.fetchone()
        return row["email"] if row else None

    async def mark_user_paid(self, tg_id: int) -> None:
        await self.db.execute("UPDATE users SET paid=1 WHERE tg_id=?", (tg_id,))
        await self.db.commit()

    async def is_paid(self, tg_id: int) -> bool:
        async with self.db.execute("SELECT paid FROM users WHERE tg_id=?", (tg_id,)) as cur:
            row = await cur.fetchone()
        return bool(row and row["paid"])

    async def stats(self) -> dict[str, int]:
        async with self.db.execute("SELECT COUNT(*) c FROM users") as cur:
            users = (await cur.fetchone())["c"]
        async with self.db.execute("SELECT COUNT(*) c FROM users WHERE paid=1") as cur:
            paid = (await cur.fetchone())["c"]
        async with self.db.execute("SELECT COUNT(*) c FROM invoices") as cur:
            invoices = (await cur.fetchone())["c"]
        return {"users": users, "paid": paid, "invoices": invoices}

    # --- Счёта --------------------------------------------------------------
    async def add_invoice(
        self,
        invoice_id: str,
        tg_id: int,
        email: str,
        currency: str,
        method: str,
        amount: float | None,
        payment_url: str,
    ) -> None:
        await self.db.execute(
            """INSERT OR REPLACE INTO invoices
               (id, tg_id, email, currency, method, amount, status, payment_url, created_at)
               VALUES (?, ?, ?, ?, ?, ?, 'new', ?, ?)""",
            (invoice_id, tg_id, email, currency, method, amount, payment_url, int(time.time())),
        )
        await self.db.commit()

    async def get_invoice(self, invoice_id: str) -> dict[str, Any] | None:
        async with self.db.execute("SELECT * FROM invoices WHERE id=?", (invoice_id,)) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def latest_invoice_by_email(self, email: str) -> dict[str, Any] | None:
        async with self.db.execute(
            "SELECT * FROM invoices WHERE lower(email)=lower(?) ORDER BY created_at DESC LIMIT 1",
            (email,),
        ) as cur:
            row = await cur.fetchone()
        return dict(row) if row else None

    async def pending_invoices(self, ttl_hours: int) -> list[dict[str, Any]]:
        threshold = int(time.time()) - ttl_hours * 3600
        async with self.db.execute(
            "SELECT * FROM invoices WHERE status NOT IN ('completed','failed') AND created_at > ?",
            (threshold,),
        ) as cur:
            rows = await cur.fetchall()
        return [dict(r) for r in rows]

    async def mark_invoice(self, invoice_id: str, status: str) -> bool:
        """Возвращает True, если статус реально изменился на completed (защита от дублей)."""
        async with self.db.execute("SELECT status FROM invoices WHERE id=?", (invoice_id,)) as cur:
            row = await cur.fetchone()
        if row is None:
            return False
        was_completed = row["status"] == "completed"
        await self.db.execute(
            "UPDATE invoices SET status=?, paid_at=? WHERE id=?",
            (status, int(time.time()) if status == "completed" else None, invoice_id),
        )
        await self.db.commit()
        return status == "completed" and not was_completed
