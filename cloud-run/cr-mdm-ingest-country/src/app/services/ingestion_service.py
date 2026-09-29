"""Lógica de negocio: orquesta fetch -> limpiar -> validar -> insertar."""

from datetime import datetime, timezone
from typing import Any, Dict, List

from src.app.core.config import SERVICE_NAME
from src.app.integrations.bigquery.main import insert_country_rows
from src.app.integrations.countriesdev.main import CountriesApiError, fetch_all_countries
from src.app.utils.logging import get_logger

logger = get_logger(SERVICE_NAME)


def clean_record(raw_country: dict, ingestion_ts: datetime) -> dict:
    """Aplana un país de countries.dev a una fila de la capa raw."""
    currencies = raw_country.get("currencies") or []
    currency_code = currencies[0].get("code") if currencies else None

    return {
        "country_code": raw_country.get("alpha3Code"),
        "name_common": raw_country.get("name"),
        "capital": raw_country.get("capital"),
        "population": raw_country.get("population"),
        "region": raw_country.get("region"),
        "currency_code": currency_code,
        "ingestion_timestamp": ingestion_ts.isoformat(),
    }


def is_valid_record(record: dict) -> bool:
    """Regla de calidad mínima antes de insertar en BigQuery."""
    if not record.get("country_code") or not record.get("name_common"):
        return False
    return True


def run_country_ingestion() -> Dict[str, Any]:
    ingestion_ts = datetime.now(timezone.utc)

    try:
        raw_countries = fetch_all_countries()
    except CountriesApiError as e:
        logger.error("Fallo consultando countries.dev: %s", e)
        raise

    rows: List[dict] = []
    skipped: List[str] = []

    for raw_country in raw_countries:
        record = clean_record(raw_country, ingestion_ts)

        if not is_valid_record(record):
            skipped.append(record.get("country_code") or raw_country.get("name") or "unknown")
            logger.warning("País inválido, se omite: %s", raw_country.get("name"))
            continue

        rows.append(record)

    insert_country_rows(rows)

    return {
        "inserted": len(rows),
        "skipped": len(skipped),
        "ingestion_timestamp": ingestion_ts.isoformat(),
    }
