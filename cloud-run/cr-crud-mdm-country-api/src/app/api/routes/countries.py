from flask import Blueprint, jsonify, request

from src.app.core.config import LOG_SEPARATOR, SERVICE_NAME
from src.app.integrations.bigquery.main import BigQueryInsertError
from src.app.integrations.firestore.main import CountryNotFoundError
from src.app.integrations.pubsub.main import PubSubPublishError
from src.app.services.crud_service import (
    CountryConflictError,
    InvalidSyncRequestError,
    is_valid_country_payload,
    is_valid_new_country_payload,
    run_create_country,
    run_delete_country,
    run_get_country,
    run_list_countries,
    run_sync_countries,
    run_update_country,
)
from src.app.utils.common import safe_json_dumps
from src.app.utils.logging import get_logger

logger = get_logger(SERVICE_NAME)

countries_bp = Blueprint("countries", __name__)


def _caller() -> str:
    """Quién llama: cabecera X-Caller (p. ej. cf-update-mdm-country) o 'manual'."""
    return (request.headers.get("X-Caller") or "manual").strip() or "manual"


def _integration_error(e: Exception):
    logger.exception("Error de integración")
    return jsonify({"error": "Integration Error", "detail": str(e)}), 502


@countries_bp.route("/countries", methods=["GET"])
def list_countries_route():
    logger.info(LOG_SEPARATOR)
    logger.info("GET /countries")
    try:
        result = run_list_countries(caller=_caller())
        return jsonify({"status": "success", "service": SERVICE_NAME, "payload": result}), 200
    except (BigQueryInsertError, PubSubPublishError) as e:
        return _integration_error(e)
    except Exception as e:
        logger.exception("Error inesperado")
        return jsonify({"error": "Internal Error", "detail": str(e)}), 500


@countries_bp.route("/countries/<country_code>", methods=["GET"])
def get_country_route(country_code):
    logger.info(LOG_SEPARATOR)
    logger.info("GET /countries/%s", country_code)
    try:
        result = run_get_country(country_code.upper(), caller=_caller())
        return jsonify({"status": "success", "service": SERVICE_NAME, "payload": result}), 200
    except CountryNotFoundError as e:
        return jsonify({"error": "Not Found", "detail": str(e)}), 404
    except (BigQueryInsertError, PubSubPublishError) as e:
        return _integration_error(e)
    except Exception as e:
        logger.exception("Error inesperado")
        return jsonify({"error": "Internal Error", "detail": str(e)}), 500


@countries_bp.route("/countries/<country_code>", methods=["POST"])
def create_country_route(country_code):
    logger.info(LOG_SEPARATOR)
    logger.info("POST /countries/%s", country_code)
    data = request.get_json(silent=True) or {}

    if not is_valid_new_country_payload(data):
        return jsonify({"error": "Bad Request", "detail": "Payload inválido: 'name' es obligatorio"}), 400

    try:
        outcome = run_create_country(country_code.upper(), data, caller=_caller())
        logger.info(safe_json_dumps({"country_code": country_code, "data": data, "result": outcome["result"]}))
        status = 201 if outcome["result"] == "CREATED" else 200
        return jsonify({"status": "success", "service": SERVICE_NAME, "payload": outcome}), status
    except CountryConflictError as e:
        return jsonify({"error": "Conflict", "detail": str(e)}), 409
    except (BigQueryInsertError, PubSubPublishError) as e:
        return _integration_error(e)
    except Exception as e:
        logger.exception("Error inesperado")
        return jsonify({"error": "Internal Error", "detail": str(e)}), 500


@countries_bp.route("/countries/<country_code>", methods=["PUT"])
def update_country_route(country_code):
    logger.info(LOG_SEPARATOR)
    logger.info("PUT /countries/%s", country_code)
    data = request.get_json(silent=True) or {}

    if not is_valid_country_payload(data):
        return jsonify({"error": "Bad Request", "detail": "Payload inválido"}), 400

    try:
        outcome = run_update_country(country_code.upper(), data, caller=_caller())
        return jsonify({"status": "success", "service": SERVICE_NAME, "payload": outcome}), 200
    except CountryNotFoundError as e:
        return jsonify({"error": "Not Found", "detail": str(e)}), 404
    except (BigQueryInsertError, PubSubPublishError) as e:
        return _integration_error(e)
    except Exception as e:
        logger.exception("Error inesperado")
        return jsonify({"error": "Internal Error", "detail": str(e)}), 500


@countries_bp.route("/countries/<country_code>", methods=["DELETE"])
def delete_country_route(country_code):
    logger.info(LOG_SEPARATOR)
    logger.info("DELETE /countries/%s", country_code)
    try:
        outcome = run_delete_country(country_code.upper(), caller=_caller())
        return jsonify({"status": "success", "service": SERVICE_NAME, "payload": outcome}), 200
    except CountryNotFoundError as e:
        return jsonify({"error": "Not Found", "detail": str(e)}), 404
    except (BigQueryInsertError, PubSubPublishError) as e:
        return _integration_error(e)
    except Exception as e:
        logger.exception("Error inesperado")
        return jsonify({"error": "Internal Error", "detail": str(e)}), 500


@countries_bp.route("/sync/countries", methods=["POST"])
def sync_countries_route():
    """Lote de altas/cambios que envía cf-update-mdm-country. Cuerpo: {"changes": [{"country_code", "data"}]}."""
    logger.info(LOG_SEPARATOR)
    logger.info("POST /sync/countries")
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return jsonify({"error": "Bad Request", "detail": "El cuerpo debe ser un objeto JSON con 'changes'"}), 400

    try:
        counts = run_sync_countries(body.get("changes"), caller=_caller())
        logger.info(safe_json_dumps(counts))
        return jsonify({"status": "success", "service": SERVICE_NAME, "payload": counts}), 200
    except InvalidSyncRequestError as e:
        return jsonify({"error": "Bad Request", "detail": str(e)}), 400
    except (BigQueryInsertError, PubSubPublishError) as e:
        return _integration_error(e)
    except Exception as e:
        logger.exception("Error inesperado")
        return jsonify({"error": "Internal Error", "detail": str(e)}), 500
