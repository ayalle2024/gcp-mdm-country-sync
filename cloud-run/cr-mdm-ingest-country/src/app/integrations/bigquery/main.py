"""Cliente para insertar filas en la capa raw de BigQuery."""

from typing import Any, Dict, List

from google.cloud import bigquery

from src.app.core.config import BQ_RAW_DATASET, BQ_RAW_TABLE, PROJECT_ID, SERVICE_NAME
from src.app.utils.logging import get_logger

logger = get_logger(SERVICE_NAME)

_client = None


class BigQueryInsertError(RuntimeError):
    """Error insertando filas en BigQuery."""


def _get_client() -> bigquery.Client:
    global _client
    if _client is None:
        _client = bigquery.Client(project=PROJECT_ID)
    return _client


def insert_country_rows(rows: List[Dict[str, Any]]) -> None:
    if not rows:
        return

    client = _get_client()
    table_id = f"{PROJECT_ID}.{BQ_RAW_DATASET}.{BQ_RAW_TABLE}"

    errors = client.insert_rows_json(table_id, rows)
    if errors:
        raise BigQueryInsertError(f"Fallo insertando en {table_id}: {errors}")

    logger.info("Insertadas %d filas en %s", len(rows), table_id)
