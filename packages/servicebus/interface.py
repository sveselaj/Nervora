"""Message + queue interface shared by both backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Message:
    """A queued unit of work.

    ``body`` carries at minimum ``job_id`` and ``idempotency_key`` (see the
    async contract). ``delivery_count`` lets the worker reason about retries.
    ``handle`` is backend-specific (a lock token / row id) used to settle.
    """

    body: dict[str, Any]
    delivery_count: int = 1
    handle: Any = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def job_id(self) -> str | None:
        return self.body.get("job_id")

    @property
    def idempotency_key(self) -> str | None:
        return self.body.get("idempotency_key")


class MessageQueue(ABC):
    @abstractmethod
    def publish(self, body: dict[str, Any]) -> None:
        """Enqueue a message."""

    @abstractmethod
    def receive(self, max_messages: int = 1, visibility_timeout: int = 30) -> list[Message]:
        """Lock and return up to ``max_messages`` (peek-lock semantics)."""

    @abstractmethod
    def complete(self, message: Message) -> None:
        """Settle a successfully-processed message (remove from queue)."""

    @abstractmethod
    def abandon(self, message: Message) -> None:
        """Release the lock for redelivery; dead-letter if max delivery reached."""

    @abstractmethod
    def dead_letter(self, message: Message, *, reason: str = "") -> None:
        """Move a message to the dead-letter queue explicitly."""
