import os

PROJECT_ID = os.environ.get("PROJECT_ID", "arl-dtpr-dev-mdm-country-sync")
REGION = os.environ.get("REGION", "us-central1")
SERVICE_NAME = os.environ.get("SERVICE_NAME", "cf-notify-downstream")

WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "https://webhook.site/CHANGE-ME")
WEBHOOK_TIMEOUT_SECONDS = int(os.environ.get("WEBHOOK_TIMEOUT_SECONDS", "10"))

LOGGER_NAME = f"{SERVICE_NAME}-{PROJECT_ID}"
LOG_SEPARATOR = "======================================"
