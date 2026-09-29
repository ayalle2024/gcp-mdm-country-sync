from src.config import LOG_SEPARATOR, LOGGER_NAME, PROJECT_ID, SERVICE_NAME
from src.gcp_logging import GCPLogger
from src.utils import get_changes_since, sync_changes_via_crud

logger = GCPLogger.get_logger(LOGGER_NAME)


def main(request):
    logger.info(LOG_SEPARATOR)
    logger.info("INICIO cf-update-mdm-country")
    logger.info("Proyecto: %s", PROJECT_ID)
    logger.info("Servicio: %s", SERVICE_NAME)
    logger.info(LOG_SEPARATOR)
    body = request.get_json(silent=True)
    since = body.get("since") if isinstance(body, dict) else None
    if not since:
        logger.error("Falta since en el cuerpo de la petición")
        return {"error": "since es obligatorio"}, 400

    try:
        logger.info("Cambios detectados desde: %s", since)
        changes = get_changes_since(since)
        logger.info("Cambios de esta ejecución: %d", len(changes))

        result = sync_changes_via_crud(changes) if changes else {"total": 0, "created": 0, "updated": 0, "unchanged": 0}
        logger.info("Resultado de la sincronización vía CRUD: %s", result)

        logger.info(LOG_SEPARATOR)
        logger.info("FIN cf-update-mdm-country OK")
        logger.info(LOG_SEPARATOR)
        return {
            "synced": len(changes),
            "created": result["created"],
            "updated": result["updated"],
            "unchanged": result["unchanged"],
        }, 200
    except Exception:
        logger.exception("Error en cf-update-mdm-country")
        logger.info(LOG_SEPARATOR)
        logger.info("FIN cf-update-mdm-country ERROR")
        logger.info(LOG_SEPARATOR)
        raise
