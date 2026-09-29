import os
from unittest.mock import MagicMock, patch

import pytest

os.environ.setdefault("PROJECT_ID", "arl-dtpr-dev-mdm-country-sync")
os.environ.setdefault("REGION", "us-central1")
os.environ.setdefault("SERVICE_NAME", "cf-update-mdm-country")
os.environ.setdefault("BQ_DATASET", "std_arl_all_restcountries")
os.environ.setdefault("BQ_CHANGE_TABLE", "trx_country_change")
os.environ.setdefault("CRUD_API_URL", "https://crud.example.run.app")

_bigquery_patcher = patch("google.cloud.bigquery.Client", return_value=MagicMock())

_bigquery_patcher.start()


def pytest_sessionfinish(session, exitstatus):
    _bigquery_patcher.stop()


@pytest.fixture()
def fake_request():
    request = MagicMock()
    request.get_json.return_value = {"since": "2026-09-25T17:00:00Z"}
    return request


@pytest.fixture()
def sample_change():
    return {
        "change_id": "chg-1",
        "country_code": "AFG",
        "change_type": "INSERT",
        "field_changed": None,
        "new_value": '{"country_code":"AFG","name_common":"Afghanistan","capital":"Kabul","population":40218234,"region":"Asia","currency_code":"AFN"}',
        "detected_at": "2026-09-18T00:00:00+00:00",
    }
