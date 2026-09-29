"""Cliente para publicar el evento de cambio en Pub/Sub."""

import json
from typing import Any, Dict, List, Optional

from google.cloud import pubsub_v1

from src.app.core.config import (
    OUTPUT_PUBSUB_TOPIC,
    PROJECT_ID,
    PUBLISH_TO_OUTPUT_TOPIC,
    SERVICE_NAME,
)
from src.app.utils.logging import get_logger

logger = get_logger(SERVICE_NAME)

_publisher = None


class PubSubPublishError(RuntimeError):
    """Error publicando un evento en Pub/Sub."""


def _get_publisher() -> pubsub_v1.PublisherClient:
    global _publisher
    if _publisher is None:
        _publisher = pubsub_v1.PublisherClient()
    return _publisher


def build_event(country_code: str, change_type: str, field_changed: Optional[str], source: str) -> Dict[str, Any]:
    """Mismo contrato que publicaba cf-update-mdm-country, más el origen del cambio."""
    return {
        "country_code": country_code,
        "change_type": change_type,
        "field_changed": field_changed,
        "source": source,
    }


def publish_events(events: List[Dict[str, Any]], timeout: int = 30) -> int:
    """Publica todos los eventos y espera la confirmación de cada uno al final."""
    if not events or not PUBLISH_TO_OUTPUT_TOPIC:
        return 0

    publisher = _get_publisher()
    topic_path = publisher.topic_path(PROJECT_ID, OUTPUT_PUBSUB_TOPIC)

    try:
        futures = [
            publisher.publish(topic_path, json.dumps(event, ensure_ascii=False).encode("utf-8"), origin=SERVICE_NAME)
            for event in events
        ]
        for future in futures:
            future.result(timeout=timeout)
    except Exception as e:  # noqa: BLE001
        raise PubSubPublishError(f"Fallo publicando en {topic_path}: {e}") from e

    logger.info("Publicados %d eventos en %s", len(events), topic_path)
    return len(events)
