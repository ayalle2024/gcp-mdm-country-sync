from unittest.mock import patch


def test_health_endpoint_returns_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "ok"
    assert body["service"] == "cr-mdm-ingest-country"


@patch("src.app.api.routes.ingestion.run_country_ingestion")
def test_ingestion_endpoint_success(mock_run, client):
    mock_run.return_value = {
        "inserted": 250,
        "skipped": 0,
        "ingestion_timestamp": "2024-01-15T10:00:00+00:00",
    }

    response = client.post("/")

    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "success"
    assert body["payload"]["inserted"] == 250


@patch("src.app.api.routes.ingestion.run_country_ingestion")
def test_ingestion_endpoint_handles_integration_error(mock_run, client):
    from src.app.integrations.countriesdev.main import CountriesApiError

    mock_run.side_effect = CountriesApiError("api down")

    response = client.post("/")

    assert response.status_code == 502
    assert response.get_json()["error"] == "Integration Error"


@patch("src.app.api.routes.ingestion.run_country_ingestion")
def test_ingestion_endpoint_handles_unexpected_error(mock_run, client):
    mock_run.side_effect = RuntimeError("boom")

    response = client.post("/")

    assert response.status_code == 500
    assert response.get_json()["error"] == "Internal Error"
