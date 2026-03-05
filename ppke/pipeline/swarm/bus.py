"""Inter-agent communication bus for the Swarm pipeline.

Provides a thread-safe message bus that allows agents to publish results
and subscribe to results from other agents.  This enables handoffs and
cross-referencing between specialised agents.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class Message:
    """A single message on the bus."""

    sender: str
    topic: str
    payload: Any


class MessageBus:
    """Thread-safe communication bus for inter-agent messaging.

    Agents publish results via :meth:`publish` and read other agents'
    messages via :meth:`collect`.  All messages are stored in-memory
    for the duration of a single pipeline run.
    """

    def __init__(self) -> None:
        self._messages: list[Message] = []
        self._lock = threading.Lock()

    def publish(self, sender: str, topic: str, payload: Any) -> None:
        """Publish a message from *sender* on *topic*."""
        msg = Message(sender=sender, topic=topic, payload=payload)
        with self._lock:
            self._messages.append(msg)
        logger.debug("Bus: %s published on '%s'", sender, topic)

    def collect(self, topic: str | None = None, exclude_sender: str | None = None) -> list[Message]:
        """Return messages, optionally filtered by *topic* and excluding *sender*."""
        with self._lock:
            msgs = list(self._messages)
        if topic:
            msgs = [m for m in msgs if m.topic == topic]
        if exclude_sender:
            msgs = [m for m in msgs if m.sender != exclude_sender]
        return msgs

    def context_for(self, agent_role: str) -> dict[str, Any]:
        """Build a context dict for an agent from all other agents' messages."""
        msgs = self.collect(exclude_sender=agent_role)
        context: dict[str, Any] = {}
        for msg in msgs:
            key = f"{msg.sender}:{msg.topic}"
            context[key] = msg.payload
        return context

    @property
    def message_count(self) -> int:
        with self._lock:
            return len(self._messages)

    def clear(self) -> None:
        """Remove all messages from the bus."""
        with self._lock:
            self._messages.clear()
