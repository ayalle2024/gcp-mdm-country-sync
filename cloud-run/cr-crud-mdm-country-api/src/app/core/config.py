import os

# -------------------------------------------------------
# Configuración general
# -------------------------------------------------------

PROJECT_ID = os.environ.get("PROJECT_ID") or os.environ.get("GCP_PROJECT_ID", "arl-dtpr-dev-mdm-country-sync")
SERVICE_NAME = os.environ.get("SERVICE_NAME", "cr-crud-mdm-country-api")

# -------------------------------------------------------
# Firestore
# -------------------------------------------------------

FIRESTORE_COLLECTION = os.environ.get("FIRESTORE_COLLECTION", "countries")

# -------------------------------------------------------
# BigQuery (auditoría CRUD)
# -------------------------------------------------------

BQ_DATASET = os.environ.get("BQ_DATASET", "std_arl_all_restcountries")
BQ_AUDIT_TABLE = os.environ.get("BQ_AUDIT_TABLE", "trx_crud_action")

# -------------------------------------------------------
# Pub/Sub (evento de salida tras cada cambio)
# -------------------------------------------------------

OUTPUT_PUBSUB_TOPIC = os.environ.get("OUTPUT_PUBSUB_TOPIC", "mdm-country-updates")
PUBLISH_TO_OUTPUT_TOPIC = os.environ.get("PUBLISH_TO_OUTPUT_TOPIC", "true").strip().lower() == "true"

# -------------------------------------------------------
# Sincronización por lotes (POST /sync/countries)
# -------------------------------------------------------

SYNC_MAX_BATCH = int(os.environ.get("SYNC_MAX_BATCH", "500"))

# -------------------------------------------------------
# Logging
# -------------------------------------------------------

LOG_SEPARATOR = "======================================"
