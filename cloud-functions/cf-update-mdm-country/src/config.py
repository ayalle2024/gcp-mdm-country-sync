import os

PROJECT_ID = os.environ.get("PROJECT_ID", "arl-dtpr-dev-mdm-country-sync")
REGION = os.environ.get("REGION", "us-central1")
SERVICE_NAME = os.environ.get("SERVICE_NAME", "cf-update-mdm-country")

BQ_DATASET = os.environ.get("BQ_DATASET", "std_arl_all_restcountries")
BQ_CHANGE_TABLE = os.environ.get("BQ_CHANGE_TABLE", "trx_country_change")

# La función ya no escribe en Firestore ni publica en Pub/Sub: lo hace el CRUD, única vía de escritura al maestro.
CRUD_API_URL = os.environ.get("CRUD_API_URL", "https://cr-crud-mdm-country-api-<PROJECT_NUMBER>.us-central1.run.app")
CRUD_SYNC_CHUNK_SIZE = int(os.environ.get("CRUD_SYNC_CHUNK_SIZE", "100"))
CRUD_TIMEOUT_SECONDS = int(os.environ.get("CRUD_TIMEOUT_SECONDS", "120"))

LOGGER_NAME = f"{SERVICE_NAME}-{PROJECT_ID}"
LOG_SEPARATOR = "======================================"
