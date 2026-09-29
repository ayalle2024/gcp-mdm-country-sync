"""Cliente para leer/escribir el maestro de países en Firestore."""

from typing import Any, Dict, List, Optional

from google.cloud import firestore

from src.app.core.config import FIRESTORE_COLLECTION, PROJECT_ID, SERVICE_NAME
from src.app.utils.logging import get_logger

logger = get_logger(SERVICE_NAME)

_client = None


class CountryNotFoundError(RuntimeError):
    """El país solicitado no existe en el maestro."""


def _get_client() -> firestore.Client:
    global _client
    if _client is None:
        _client = firestore.Client(project=PROJECT_ID)
    return _client


WRITE_BATCH_SIZE = 450  # Firestore admite 500 operaciones por lote


def get_countries_by_codes(codes: List[str]) -> Dict[str, Optional[Dict[str, Any]]]:
    """Lee varios países en una sola llamada. Devuelve {codigo: documento o None}."""
    client = _get_client()
    collection = client.collection(FIRESTORE_COLLECTION)
    result: Dict[str, Optional[Dict[str, Any]]] = {code: None for code in codes}

    for snapshot in client.get_all([collection.document(code) for code in codes]):
        if snapshot.exists:
            result[snapshot.id] = snapshot.to_dict()
    return result


def write_countries(documents: Dict[str, Dict[str, Any]]) -> None:
    """Escribe (merge) varios países en lotes de escritura."""
    if not documents:
        return

    client = _get_client()
    collection = client.collection(FIRESTORE_COLLECTION)
    batch = client.batch()
    pending = 0

    for code, data in documents.items():
        batch.set(collection.document(code), data, merge=True)
        pending += 1
        if pending >= WRITE_BATCH_SIZE:
            batch.commit()
            batch = client.batch()
            pending = 0

    if pending:
        batch.commit()


def list_countries() -> List[Dict[str, Any]]:
    docs = _get_client().collection(FIRESTORE_COLLECTION).stream()
    return [doc.to_dict() for doc in docs]


def get_country(country_code: str) -> Dict[str, Any]:
    doc = _get_client().collection(FIRESTORE_COLLECTION).document(country_code).get()
    if not doc.exists:
        raise CountryNotFoundError(f"País no encontrado: {country_code}")
    return doc.to_dict()


def create_country(country_code: str, data: Dict[str, Any]) -> None:
    document = {**data, "country_code": country_code}
    _get_client().collection(FIRESTORE_COLLECTION).document(country_code).set(document)


def update_country(country_code: str, data: Dict[str, Any]) -> None:
    doc_ref = _get_client().collection(FIRESTORE_COLLECTION).document(country_code)
    if not doc_ref.get().exists:
        raise CountryNotFoundError(f"País no encontrado: {country_code}")
    doc_ref.set(data, merge=True)


def delete_country(country_code: str) -> None:
    doc_ref = _get_client().collection(FIRESTORE_COLLECTION).document(country_code)
    if not doc_ref.get().exists:
        raise CountryNotFoundError(f"País no encontrado: {country_code}")
    doc_ref.delete()
