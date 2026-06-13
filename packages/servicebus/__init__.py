"""Async messaging abstraction (Azure Service Bus, mock-first).

The gateway publishes a job message; the worker receives, processes, and either
completes or abandons it. Two backends implement one interface:

* ``LocalQueue``        — a Postgres/SQLite-backed queue with a visibility
                          timeout, delivery counting and a dead-letter status.
                          Lets the full async path run offline.
* ``AzureServiceBusQueue`` — wraps ``azure-servicebus`` (peek-lock semantics,
                          native dead-letter sub-queue, max delivery count).

Both honour the same retry/DLQ contract documented in
``docs/observability.md`` and the async section of the README.
"""

from servicebus.azure_bus import AzureServiceBusQueue
from servicebus.factory import build_queue
from servicebus.interface import Message, MessageQueue
from servicebus.local import LocalQueue, QueueMessage

__all__ = [
    "Message",
    "MessageQueue",
    "LocalQueue",
    "QueueMessage",
    "AzureServiceBusQueue",
    "build_queue",
]
