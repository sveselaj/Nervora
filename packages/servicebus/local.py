"""Postgres/SQLite-backed local queue.

Implements peek-lock semantics so the worker behaves identically against the
local queue and Azure Service Bus:

* ``publish``  inserts a row with status ``available``.
* ``receive``  atomically claims ``available`` rows whose ``visible_at`` has
               passed, sets status ``locked`` and pushes ``visible_at`` forward
               by the visibility timeout, and increments ``delivery_count``.
* ``complete`` marks the row ``completed``.
* ``abandon``  makes the row visible again — or dead-letters it if
               ``delivery_count`` has reached ``max_delivery_count``.
* ``dead_letter`` marks ``dead_letter`` explicitly.

This is not a high-throughput broker; it is a faithful, inspectable stand-in
that keeps the async demo fully offline.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from audit.db import Base, session_scope
from sqlalchemy import DateTime, Integer, String, Text, select
from sqlalchemy.orm import Mapped, mapped_column

from servicebus.interface import Message, MessageQueue


def _utcnow() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class QueueMessage(Base):
    __tablename__ = "queue_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    queue_name: Mapped[str] = mapped_column(String(128), index=True)
    body: Mapped[str] = mapped_column(Text)  # JSON-encoded
    # status: available | locked | completed | dead_letter
    status: Mapped[str] = mapped_column(String(32), default="available", index=True)
    delivery_count: Mapped[int] = mapped_column(Integer, default=0)
    visible_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    dead_letter_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class LocalQueue(MessageQueue):
    def __init__(self, *, database_url: str, queue_name: str, max_delivery_count: int = 5) -> None:
        self._db = database_url
        self._queue = queue_name
        self._max_delivery = max_delivery_count

    def publish(self, body: dict[str, Any]) -> None:
        import json

        with session_scope(self._db) as s:
            s.add(QueueMessage(queue_name=self._queue, body=json.dumps(body), status="available"))

    def receive(self, max_messages: int = 1, visibility_timeout: int = 30) -> list[Message]:
        import json

        now = _utcnow()
        claimed: list[Message] = []
        with session_scope(self._db) as s:
            stmt = (
                select(QueueMessage)
                .where(
                    QueueMessage.queue_name == self._queue,
                    QueueMessage.status == "available",
                    QueueMessage.visible_at <= now,
                )
                .order_by(QueueMessage.id.asc())
                .limit(max_messages)
                .with_for_update(skip_locked=True)
            )
            try:
                rows = list(s.scalars(stmt))
            except Exception:
                # SQLite has no SELECT ... FOR UPDATE / SKIP LOCKED.
                rows = list(
                    s.scalars(
                        select(QueueMessage)
                        .where(
                            QueueMessage.queue_name == self._queue,
                            QueueMessage.status == "available",
                            QueueMessage.visible_at <= now,
                        )
                        .order_by(QueueMessage.id.asc())
                        .limit(max_messages)
                    )
                )
            for row in rows:
                row.status = "locked"
                row.delivery_count += 1
                row.visible_at = now + dt.timedelta(seconds=visibility_timeout)
                claimed.append(
                    Message(
                        body=json.loads(row.body),
                        delivery_count=row.delivery_count,
                        handle=row.id,
                    )
                )
        return claimed

    def complete(self, message: Message) -> None:
        with session_scope(self._db) as s:
            row = s.get(QueueMessage, message.handle)
            if row is not None:
                row.status = "completed"

    def abandon(self, message: Message) -> None:
        with session_scope(self._db) as s:
            row = s.get(QueueMessage, message.handle)
            if row is None:
                return
            if row.delivery_count >= self._max_delivery:
                row.status = "dead_letter"
                row.dead_letter_reason = "max delivery count exceeded"
            else:
                row.status = "available"
                row.visible_at = _utcnow()  # immediately eligible for retry

    def dead_letter(self, message: Message, *, reason: str = "") -> None:
        with session_scope(self._db) as s:
            row = s.get(QueueMessage, message.handle)
            if row is not None:
                row.status = "dead_letter"
                row.dead_letter_reason = reason or "explicit dead-letter"

    # --- introspection (used by tests + admin endpoint) ------------------
    def stats(self) -> dict[str, int]:
        with session_scope(self._db) as s:
            rows = list(s.scalars(select(QueueMessage).where(QueueMessage.queue_name == self._queue)))
        out: dict[str, int] = {}
        for r in rows:
            out[r.status] = out.get(r.status, 0) + 1
        return out
