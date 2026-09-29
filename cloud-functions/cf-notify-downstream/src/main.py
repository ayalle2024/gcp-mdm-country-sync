from src.config import LOG_SEPARATOR, LOGGER_NAME, PROJECT_ID, SERVICE_NAME
from src.gcp_logging import GCPLogger
from src.utils import decode_pubsub_message, forward_to_downstream, safe_json_dumps

logger = GCPLogger.get_logger(LOGGER_NAME)


def main(event, context=None):
    logger.info(LOG_SEPARATOR)
    logger.info("INICIO cf-notify-downstream")
    logger.info("Proyecto: %s", PROJECT_ID)
    logger.info("Servicio: %s", SERVICE_NAME)
    logger.info(LOG_SEPARATOR)
    try:
        payload = decode_pubsub_message(event)
        logger.info("Evento recibido:")
        logger.info(safe_json_dumps(payload))

        forward_to_downstream(payload)
        logger.info("Downstream notificado para country_code=%s", payload.get("country_code"))

        logger.info(LOG_SEPARATOR)
        logger.info("FIN cf-notify-downstream OK")
        logger.info(LOG_SEPARATOR)
        return payload
    except Exception:
        logger.exception("Error en cf-notify-downstream")
        logger.info(LOG_SEPARATOR)
        logger.info("FIN cf-notify-downstream ERROR")
        logger.info(LOG_SEPARATOR)
        raise
