"""Select the queue backend from settings."""

from __future__ import annotations

from servicebus.azure_bus import AzureServiceBusQueue
from servicebus.interface import MessageQueue
from servicebus.local import LocalQueue


def build_queue(settings) -> MessageQueue:
    if settings.queue_backend == "azure":
        return AzureServiceBusQueue(
            connection_string=settings.servicebus_connection_string,
            queue_name=settings.servicebus_queue_name,
        )
    return LocalQueue(
        database_url=settings.database_url,
        queue_name=settings.servicebus_queue_name,
        max_delivery_count=settings.queue_max_delivery_count,
    )
