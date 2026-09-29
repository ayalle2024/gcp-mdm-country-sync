"""Cliente para registrar auditoría de acciones CRUD en BigQuery."""

import json
from typing import Any, Dict, List, Optional

from google.cloud import bigquery

from src.app.core.config import BQ_AUDIT_TABLE, BQ_DATASET, PROJECT_ID, SERVICE_NAME
from src.app.utils.common import new_id, utc_now
from src.app.utils.logging import get_logger

logger = get_logger(SERVICE_NAME)

_client = None

DEFAULT_CALLER = "manual"


class BigQueryInsertError(RuntimeError):
    """Error insertando una fila de auditoría en BigQuery."""


def _get_client() -> bigquery.Client:
    global _client
    if _client is None:
        _client = bigquery.Client(project=PROJECT_ID)
    return _client


def build_audit_row(
    action_type: str,
    country_code: Optional[str] = None,
    result: Optional[str] = None,
    caller: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    return {
        "action_id": new_id(),
        "action_type": action_type,
        "country_code": country_code,
        "performed_at": utc_now(),
        "source": SERVICE_NAME,
        "result": result,
        "caller": caller or DEFAULT_CALLER,
        "payload": json.dumps(payload, default=str, ensure_ascii=False) if payload is not None else None,
    }


def log_crud_actions(rows: List[Dict[str, Any]]) -> None:
    """Inserta varias filas de auditoría en una sola llamada."""
    if not rows:
        return

    table_id = f"{PROJECT_ID}.{BQ_DATASET}.{BQ_AUDIT_TABLE}"
    errors = _get_client().insert_rows_json(table_id, rows)
    if errors:
        raise BigQueryInsertError(f"Fallo insertando auditoría en {table_id}: {errors}")

    logger.info("Auditoría registrada: %d filas", len(rows))


def log_crud_action(
    action_type: str,
    country_code: Optional[str] = None,
    result: Optional[str] = None,
    caller: Optional[str] = None,
    payload: Optional[Dict[str, Any]] = None,
) -> None:
    log_crud_actions([build_audit_row(action_type, country_code, result, caller, payload)])
