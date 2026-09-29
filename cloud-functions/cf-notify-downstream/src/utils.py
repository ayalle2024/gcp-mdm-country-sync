import base64
import json
from typing import Any, Dict

import requests

from src.config import LOGGER_NAME, WEBHOOK_TIMEOUT_SECONDS, WEBHOOK_URL
from src.gcp_logging import GCPLogger

logger = GCPLogger.get_logger(LOGGER_NAME)


def safe_json_dumps(payload: Any) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    except TypeError:
        return json.dumps(str(payload), ensure_ascii=False)


def decode_pubsub_message(event: Dict[str, Any]) -> Dict[str, Any]:
    raw_data = base64.b64decode(event["data"]).decode("utf-8")
    return json.loads(raw_data)


def forward_to_downstream(payload: Dict[str, Any]) -> requests.Response:
    response = requests.post(WEBHOOK_URL, json=payload, timeout=WEBHOOK_TIMEOUT_SECONDS)

    if response.status_code >= 300:
        logger.error("Webhook downstream respondió %s: %s", response.status_code, response.text)
        raise RuntimeError(f"Downstream webhook returned {response.status_code}")

    return response
