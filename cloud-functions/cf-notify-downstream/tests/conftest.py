import base64
import json
import os

import pytest

os.environ.setdefault("PROJECT_ID", "arl-dtpr-dev-mdm-country-sync")
os.environ.setdefault("REGION", "us-central1")
os.environ.setdefault("SERVICE_NAME", "cf-notify-downstream")
os.environ.setdefault("WEBHOOK_URL", "https://webhook.site/test-fake-url")
os.environ.setdefault("WEBHOOK_TIMEOUT_SECONDS", "10")


@pytest.fixture()
def valid_country_update():
    return {"country_code": "AFG", "change_type": "INSERT", "field_changed": None}


@pytest.fixture()
def valid_pubsub_event(valid_country_update):
    encoded = base64.b64encode(json.dumps(valid_country_update).encode("utf-8"))
    return {"data": encoded}
