import os

# -------------------------------------------------------
# Configuración general
# -------------------------------------------------------

PROJECT_ID = os.environ.get("PROJECT_ID") or os.environ.get("GCP_PROJECT_ID", "arl-dtpr-dev-mdm-country-sync")
SERVICE_NAME = os.environ.get("SERVICE_NAME", "cr-mdm-ingest-country")

# -------------------------------------------------------
# countries.dev
# -------------------------------------------------------

COUNTRIES_API_URL = os.environ.get("COUNTRIES_API_URL", "https://countries.dev/countries")

# -------------------------------------------------------
# BigQuery
# -------------------------------------------------------

BQ_RAW_DATASET = os.environ.get("BQ_RAW_DATASET", "raw_arl_all_restcountries")
BQ_RAW_TABLE = os.environ.get("BQ_RAW_TABLE", "country_raw")

# -------------------------------------------------------
# Logging
# -------------------------------------------------------

LOG_SEPARATOR = "======================================"
