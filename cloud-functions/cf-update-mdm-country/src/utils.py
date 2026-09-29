import json
from typing import Any, Dict, Iterator, List

import google.auth.transport.requests
import google.oauth2.id_token
import requests
from google.cloud import bigquery

from src.config import (
    BQ_CHANGE_TABLE,
    BQ_DATASET,
    CRUD_API_URL,
    CRUD_SYNC_CHUNK_SIZE,
    CRUD_TIMEOUT_SECONDS,
    LOGGER_NAME,
    PROJECT_ID,
    SERVICE_NAME,
)
from src.gcp_logging import GCPLogger

logger = GCPLogger.get_logger(LOGGER_NAME)

bigquery_client = bigquery.Client(project=PROJECT_ID)


def safe_json_dumps(payload: Any) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    except TypeError:
        return json.dumps(str(payload), ensure_ascii=False)


def get_changes_since(since: str) -> List[Dict[str, Any]]:
    query = f"""
        SELECT change_id, country_code, change_type, field_changed, new_value, detected_at
        FROM `{PROJECT_ID}.{BQ_DATASET}.{BQ_CHANGE_TABLE}`
        WHERE detected_at >= @since
        ORDER BY detected_at
    """
    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("since", "TIMESTAMP", since)]
    )
    rows = bigquery_client.query(query, job_config=job_config).result()
    return [dict(row) for row in rows]


def build_country_data(change: Dict[str, Any]) -> Dict[str, Any]:
    """Convierte un cambio de trx_country_change en el documento del maestro."""
    new_value = json.loads(change["new_value"])

    return {
        "country_code": new_value.get("country_code"),
        "name": new_value.get("name_common"),
        "capital": new_value.get("capital"),
        "population": new_value.get("population"),
        "region": new_value.get("region"),
        "currency_code": new_value.get("currency_code"),
        "last_change_type": change["change_type"],
        "last_change_id": change["change_id"],
    }


def get_id_token(audience: str) -> str:
    """Token de identidad de la cuenta de la función, con la URL del CRUD como audiencia."""
    return google.oauth2.id_token.fetch_id_token(google.auth.transport.requests.Request(), audience)


def chunked(items: List[Any], size: int) -> Iterator[List[Any]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def sync_changes_via_crud(changes: List[Dict[str, Any]]) -> Dict[str, int]:
    """Envía los cambios al CRUD en lotes; el CRUD escribe el maestro, audita y publica."""
    base_url = CRUD_API_URL.rstrip("/")
    headers = {
        "Authorization": f"Bearer {get_id_token(base_url)}",
        "Content-Type": "application/json",
        "X-Caller": SERVICE_NAME,
    }
    totals = {"total": 0, "created": 0, "updated": 0, "unchanged": 0}

    for chunk in chunked(changes, CRUD_SYNC_CHUNK_SIZE):
        body = {
            "changes": [
                {"country_code": change["country_code"], "data": build_country_data(change)} for change in chunk
            ]
        }
        response = requests.post(f"{base_url}/sync/countries", json=body, headers=headers, timeout=CRUD_TIMEOUT_SECONDS)

        if response.status_code >= 300:
            logger.error("El CRUD respondió %s: %s", response.status_code, response.text)
            raise RuntimeError(f"cr-crud-mdm-country-api respondió {response.status_code}")

        payload = response.json().get("payload", {})
        for key in totals:
            totals[key] += int(payload.get(key, 0))

        logger.info("Lote enviado al CRUD (%d cambios): %s", len(chunk), safe_json_dumps(payload))

    return totals
