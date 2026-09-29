"""Cliente para la API pública de countries.dev (https://countries.dev)."""

from typing import Any, Dict, List

import requests

from src.app.core.config import COUNTRIES_API_URL, SERVICE_NAME
from src.app.utils.logging import get_logger

logger = get_logger(SERVICE_NAME)


class CountriesApiError(RuntimeError):
    """Error consultando la API de countries.dev (red, timeout o respuesta inválida)."""


def fetch_all_countries(timeout: int = 20) -> List[Dict[str, Any]]:
    logger.info("Consultando countries.dev (%s)", COUNTRIES_API_URL)

    try:
        response = requests.get(COUNTRIES_API_URL, timeout=timeout)
        response.raise_for_status()
    except requests.RequestException as e:
        raise CountriesApiError(f"Fallo de red consultando countries.dev: {e}") from e

    try:
        data = response.json()
    except ValueError as e:
        raise CountriesApiError(f"Respuesta inesperada de countries.dev (no es JSON válido): {e}") from e

    if not isinstance(data, list):
        raise CountriesApiError("Respuesta inesperada de countries.dev (se esperaba un array de países)")

    return data
