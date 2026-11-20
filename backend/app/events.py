"""Domain events and outbound publishers.

Routes publish events like ``tread_measured`` after their changes are committed. Every
registered publisher receives every event. Today there is a logging publisher and an
optional Home Assistant webhook publisher; an MQTT publisher (with HA discovery) can be
added later by implementing :class:`Publisher` and registering it in :func:`get_bus`.
"""

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from functools import lru_cache
from typing import Any, Protocol

import httpx
from fastapi import BackgroundTasks
from fastapi.encoders import jsonable_encoder

from app.config import get_settings

log = logging.getLogger("cct.events")


@dataclass
class Event:
    type: str  # e.g. "vehicle_created", "tread_measured", "oil_added"
    vehicle_id: int | None
    data: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_payload(self) -> dict[str, Any]:
        return jsonable_encoder({"source": "car_consumable_tracker", **asdict(self)})


class Publisher(Protocol):
    def publish(self, event: Event) -> None: ...


class LogPublisher:
    def publish(self, event: Event) -> None:
        log.info("event %s vehicle=%s", event.type, event.vehicle_id)


class WebhookPublisher:
    """POSTs events as JSON to a URL, e.g. a Home Assistant webhook trigger."""

    def __init__(self, url: str, timeout_s: float = 5.0) -> None:
        self.url = url
        self.timeout_s = timeout_s

    def publish(self, event: Event) -> None:
        try:
            httpx.post(self.url, json=event.to_payload(), timeout=self.timeout_s)
        except httpx.HTTPError as exc:  # never let a down HA instance break the API
            log.warning("webhook delivery of %s failed: %s", event.type, exc)


class EventBus:
    def __init__(self, publishers: list[Publisher] | None = None) -> None:
        self.publishers: list[Publisher] = publishers or []

    def dispatch(self, event: Event) -> None:
        for publisher in self.publishers:
            try:
                publisher.publish(event)
            except Exception:  # noqa: BLE001 - isolate publishers from each other
                log.exception("publisher %r failed for %s", publisher, event.type)

    def publish(self, background: BackgroundTasks, event: Event) -> None:
        """Deliver after the response has been sent, so slow publishers don't block the API."""
        background.add_task(self.dispatch, event)


@lru_cache
def get_bus() -> EventBus:
    settings = get_settings()
    publishers: list[Publisher] = [LogPublisher()]
    if settings.ha_webhook_url:
        publishers.append(WebhookPublisher(settings.ha_webhook_url, settings.webhook_timeout_s))
    return EventBus(publishers)
