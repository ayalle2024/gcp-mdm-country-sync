"""Lógica de negocio del CRUD: única vía de escritura al maestro de países.

Cada operación que cambia el maestro hace, en este orden:
  1) escribe en Firestore,
  2) deja la auditoría en BigQuery (trx_crud_action),
  3) publica un evento en Pub/Sub (mdm-country-updates).

Es idempotente: si el dato entrante no cambia ningún campo de negocio respecto al
que ya está guardado, responde NO_CHANGE y no escribe ni publica.
"""

from typing import Any, Dict, List, Optional

from src.app.core.config import SERVICE_NAME, SYNC_MAX_BATCH
from src.app.integrations.bigquery.main import (
    DEFAULT_CALLER,
    build_audit_row,
    log_crud_action,
    log_crud_actions,
)
from src.app.integrations.firestore.main import (
    CountryNotFoundError,
    delete_country,
    get_countries_by_codes,
    get_country,
    list_countries,
    write_countries,
)
from src.app.integrations.pubsub.main import build_event, publish_events

# Campos que cuentan como "cambio" al comparar; el resto (p. ej. last_change_id) se guarda pero no decide.
BUSINESS_FIELDS = ("name", "capital", "population", "region", "currency_code")

CREATED = "CREATED"
UPDATED = "UPDATED"
NO_CHANGE = "NO_CHANGE"
DELETED = "DELETED"


class CountryConflictError(RuntimeError):
    """El país ya existe con datos distintos a los enviados."""


class InvalidSyncRequestError(ValueError):
    """La solicitud de sincronización por lotes no es válida."""


def is_valid_country_payload(data: Dict[str, Any]) -> bool:
    """Regla de calidad mínima para crear/actualizar un país."""
    if not isinstance(data, dict):
        return False
    if "name" in data and not data.get("name"):
        return False
    return True


def is_valid_new_country_payload(data: Dict[str, Any]) -> bool:
    """Para crear un país (POST) el nombre es obligatorio; en una actualización parcial no."""
    return is_valid_country_payload(data) and bool(data.get("name"))


def diff_fields(current: Optional[Dict[str, Any]], incoming: Dict[str, Any]) -> List[str]:
    """Campos de negocio presentes en `incoming` cuyo valor difiere del guardado."""
    current = current or {}
    return [field for field in BUSINESS_FIELDS if field in incoming and incoming.get(field) != current.get(field)]


# -------------------------------------------------------
# Lecturas
# -------------------------------------------------------

def run_list_countries(caller: str = DEFAULT_CALLER) -> List[Dict[str, Any]]:
    countries = list_countries()
    log_crud_action("READ", None, result="OK", caller=caller)
    return countries


def run_get_country(country_code: str, caller: str = DEFAULT_CALLER) -> Dict[str, Any]:
    country = get_country(country_code)
    log_crud_action("READ", country_code, result="OK", caller=caller)
    return country


# -------------------------------------------------------
# Escrituras individuales
# -------------------------------------------------------

def run_create_country(country_code: str, data: Dict[str, Any], caller: str = DEFAULT_CALLER) -> Dict[str, Any]:
    current = get_countries_by_codes([country_code])[country_code]

    if current is None:
        write_countries({country_code: {**data, "country_code": country_code}})
        result = CREATED
    elif not diff_fields(current, data):
        result = NO_CHANGE
    else:
        raise CountryConflictError(f"El país {country_code} ya existe con datos distintos")

    log_crud_action("CREATE", country_code, result=result, caller=caller, payload=data)
    if result == CREATED:
        publish_events([build_event(country_code, "INSERT", None, caller)])

    return {"country_code": country_code, "result": result}


def run_update_country(country_code: str, data: Dict[str, Any], caller: str = DEFAULT_CALLER) -> Dict[str, Any]:
    current = get_countries_by_codes([country_code])[country_code]
    if current is None:
        raise CountryNotFoundError(f"País no encontrado: {country_code}")

    changed = diff_fields(current, data)
    if changed:
        write_countries({country_code: {**data, "country_code": country_code}})
        result = UPDATED
    else:
        result = NO_CHANGE

    log_crud_action("UPDATE", country_code, result=result, caller=caller, payload=data)
    if result == UPDATED:
        publish_events([build_event(country_code, "UPDATE", changed[0], caller)])

    return {"country_code": country_code, "result": result}


def run_delete_country(country_code: str, caller: str = DEFAULT_CALLER) -> Dict[str, Any]:
    delete_country(country_code)

    log_crud_action("DELETE", country_code, result=DELETED, caller=caller)
    publish_events([build_event(country_code, "DELETE", None, caller)])

    return {"country_code": country_code, "result": DELETED}


# -------------------------------------------------------
# Sincronización por lotes (la usa cf-update-mdm-country)
# -------------------------------------------------------

def _normalize_changes(changes: Any) -> List[tuple]:
    if not isinstance(changes, list) or not changes:
        raise InvalidSyncRequestError("'changes' debe ser una lista no vacía")
    if len(changes) > SYNC_MAX_BATCH:
        raise InvalidSyncRequestError(f"Máximo {SYNC_MAX_BATCH} cambios por solicitud")

    normalized = []
    for item in changes:
        code = str((item or {}).get("country_code") or "").strip().upper() if isinstance(item, dict) else ""
        data = item.get("data") if isinstance(item, dict) else None
        if not code or not isinstance(data, dict):
            raise InvalidSyncRequestError("Cada cambio requiere 'country_code' y un objeto 'data'")
        if not is_valid_country_payload(data):
            raise InvalidSyncRequestError(f"El cambio de '{code}' tiene un 'name' vacío")
        normalized.append((code, data))
    return normalized


def run_sync_countries(changes: Any, caller: str) -> Dict[str, int]:
    """Aplica un lote de altas/cambios: crea, actualiza o ignora (NO_CHANGE) cada país."""
    normalized = _normalize_changes(changes)

    existing = get_countries_by_codes(list({code for code, _ in normalized}))

    documents: Dict[str, Dict[str, Any]] = {}
    audit_rows: List[Dict[str, Any]] = []
    events: List[Dict[str, Any]] = []
    counts = {"total": len(normalized), "created": 0, "updated": 0, "unchanged": 0}

    for code, data in normalized:
        current = existing.get(code)

        if current is None:
            result, change_type, field_changed = CREATED, "INSERT", None
        else:
            changed = diff_fields(current, data)
            if changed:
                result, change_type, field_changed = UPDATED, "UPDATE", changed[0]
            else:
                result, change_type, field_changed = NO_CHANGE, None, None

        if result == NO_CHANGE:
            counts["unchanged"] += 1
        else:
            counts["created" if result == CREATED else "updated"] += 1
            documents[code] = {**data, "country_code": code}
            existing[code] = {**(current or {}), **documents[code]}
            events.append(build_event(code, change_type, field_changed, caller))

        audit_rows.append(build_audit_row("CREATE" if result == CREATED else "UPDATE", code, result, caller, data))

    write_countries(documents)
    log_crud_actions(audit_rows)
    publish_events(events)

    return counts
