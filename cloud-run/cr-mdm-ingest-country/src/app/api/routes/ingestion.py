from flask import Blueprint, jsonify

from src.app.core.config import LOG_SEPARATOR, SERVICE_NAME
from src.app.integrations.bigquery.main import BigQueryInsertError
from src.app.integrations.countriesdev.main import CountriesApiError
from src.app.services.ingestion_service import run_country_ingestion
from src.app.utils.common import safe_json_dumps
from src.app.utils.logging import get_logger

logger = get_logger(SERVICE_NAME)

ingestion_bp = Blueprint("ingestion", __name__)


@ingestion_bp.route("/", methods=["GET", "POST"])
@ingestion_bp.route("/mdm-ingest-country", methods=["GET", "POST"])
def process_country_ingestion():
    logger.info(LOG_SEPARATOR)
    logger.info("INICIO CR MDM INGEST COUNTRY")
    logger.info(LOG_SEPARATOR)

    try:
        result = run_country_ingestion()

        response = {
            "status": "success",
            "service": SERVICE_NAME,
            "payload": result,
        }

        logger.info("Mensaje exacto de respuesta:")
        logger.info(safe_json_dumps(response))

        logger.info(LOG_SEPARATOR)
        logger.info("FIN CR MDM INGEST COUNTRY OK")
        logger.info(LOG_SEPARATOR)

        return jsonify(response), 200

    except (CountriesApiError, BigQueryInsertError) as e:
        logger.exception("Error de integración en Cloud Run")
        logger.info(LOG_SEPARATOR)
        logger.info("FIN CR MDM INGEST COUNTRY INTEGRATION_ERROR")
        logger.info(LOG_SEPARATOR)
        return jsonify({"error": "Integration Error", "detail": str(e)}), 502

    except Exception as e:
        logger.exception("Error en Cloud Run")
        logger.info(LOG_SEPARATOR)
        logger.info("FIN CR MDM INGEST COUNTRY ERROR")
        logger.info(LOG_SEPARATOR)
        return jsonify({"error": "Internal Error", "detail": str(e)}), 500
