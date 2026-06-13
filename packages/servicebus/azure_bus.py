"""Azure Service Bus backend (prepared; activated with QUEUE_BACKEND=azure).

Maps the abstraction onto native Service Bus peek-lock semantics:

* ``publish``     -> ServiceBusSender.send_messages
* ``receive``     -> ServiceBusReceiver.receive_messages (PEEK_LOCK)
* ``complete``    -> receiver.complete_message
* ``abandon``     -> receiver.abandon_message (broker redelivers; auto
                     dead-letters once MaxDeliveryCount is exceeded)
* ``dead_letter`` -> receiver.dead_letter_message

The Service Bus queue should be provisioned with ``max_delivery_count`` and a
dead-letter queue (the Terraform/Bicep in ``infra/`` does this). We keep the
azure-servicebus import lazy so the package imports cleanly without the SDK.
"""

from __future__ import annotations

import json
from typing import Any

from servicebus.interface import Message, MessageQueue


class AzureServiceBusQueue(MessageQueue):
    def __init__(self, *, connection_string: str, queue_name: str) -> None:
        if not connection_string:
            raise ValueError("AzureServiceBusQueue requires SERVICEBUS_CONNECTION_STRING")
        self._conn = connection_string
        self._queue = queue_name

    def _client(self):
        from azure.servicebus import ServiceBusClient  # lazy import

        return ServiceBusClient.from_connection_string(self._conn)

    def publish(self, body: dict[str, Any]) -> None:
        from azure.servicebus import ServiceBusMessage

        with self._client() as client, client.get_queue_sender(self._queue) as sender:
            sender.send_messages(ServiceBusMessage(json.dumps(body)))

    def receive(self, max_messages: int = 1, visibility_timeout: int = 30) -> list[Message]:
        from azure.servicebus import ServiceBusReceiveMode

        with self._client() as client:
            receiver = client.get_queue_receiver(
                self._queue, receive_mode=ServiceBusReceiveMode.PEEK_LOCK,
                max_wait_time=5,
            )
            with receiver:
                received = receiver.receive_messages(
                    max_message_count=max_messages, max_wait_time=5
                )
                out: list[Message] = []
                for raw in received:
                    out.append(
                        Message(
                            body=json.loads(str(raw)),
                            delivery_count=raw.delivery_count or 1,
                            handle=raw,
                            metadata={"receiver": receiver},
                        )
                    )
                return out

    def complete(self, message: Message) -> None:
        message.metadata["receiver"].complete_message(message.handle)

    def abandon(self, message: Message) -> None:
        message.metadata["receiver"].abandon_message(message.handle)

    def dead_letter(self, message: Message, *, reason: str = "") -> None:
        message.metadata["receiver"].dead_letter_message(
            message.handle, reason=reason or "explicit", error_description=reason
        )
