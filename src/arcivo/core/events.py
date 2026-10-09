"""A tiny thread-safe publish/subscribe bus shared by services, CLI and GUI.

The GUI subscribes and re-emits events as Qt signals on the UI thread, so the
core never imports Qt.
"""

from __future__ import annotations

import logging
import threading
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

log = logging.getLogger(__name__)


@dataclass
class Event:
    topic: str
    payload: dict[str, Any] = field(default_factory=dict)


Handler = Callable[[Event], None]


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Handler]] = defaultdict(list)
        self._lock = threading.Lock()

    def subscribe(self, topic: str, handler: Handler) -> Callable[[], None]:
        with self._lock:
            self._subs[topic].append(handler)

        def unsubscribe() -> None:
            with self._lock:
                if handler in self._subs[topic]:
                    self._subs[topic].remove(handler)

        return unsubscribe

    def publish(self, topic: str, **payload: Any) -> None:
        with self._lock:
            handlers = list(self._subs.get(topic, ())) + list(self._subs.get("*", ()))
        event = Event(topic, payload)
        for h in handlers:
            try:
                h(event)
            except Exception:  # a broken subscriber must never break the core
                log.exception("Event handler failed for %s", topic)


# Well-known topics
SYNC_PROGRESS = "sync.progress"
SYNC_FINISHED = "sync.finished"
JOB_UPDATED = "job.updated"
JOB_FINISHED = "job.finished"
DATA_CHANGED = "data.changed"
TAGS_CHANGED = "tags.changed"
COLLECTIONS_CHANGED = "collections.changed"
AUTH_CHANGED = "auth.changed"
CONNECTION_CHANGED = "connection.changed"
NOTIFY = "notify"
