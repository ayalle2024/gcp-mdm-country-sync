import pytest
from unittest.mock import patch

from src.app.integrations.bigquery.main import BigQueryInsertError
from src.app.integrations.firestore.main import CountryNotFoundError
from src.app.integrations.pubsub.main import PubSubPublishError
from src.app.services.crud_service import CountryConflictError, InvalidSyncRequestError

ROUTES = "src.app.api.routes.countries"


def test_health_endpoint_returns_ok(client):
    response = client.get("/health")

    assert response.status_code == 200
    body = response.get_json()
    assert body["status"] == "ok"
    assert body["service"] == "cr-crud-mdm-country-api"


@patch(f"{ROUTES}.run_list_countries")
def test_list_countries_endpoint(mock_run, client):
    mock_run.return_value = [{"country_code": "AFG"}]

    response = client.get("/countries")

    assert response.status_code == 200
    assert response.get_json()["payload"] == [{"country_code": "AFG"}]
    mock_run.assert_called_once_with(caller="manual")


@patch(f"{ROUTES}.run_get_country")
def test_get_country_endpoint_success(mock_run, client):
    mock_run.return_value = {"country_code": "AFG", "name": "Afghanistan"}

    response = client.get("/countries/AFG")

    assert response.status_code == 200
    assert response.get_json()["payload"]["name"] == "Afghanistan"


@patch(f"{ROUTES}.run_get_country")
def test_get_country_endpoint_not_found(mock_run, client):
    mock_run.side_effect = CountryNotFoundError("not found")

    assert client.get("/countries/ZZZ").status_code == 404


@patch(f"{ROUTES}.run_get_country")
def test_x_caller_header_is_passed_to_the_service(mock_run, client):
    mock_run.return_value = {}

    client.get("/countries/AFG", headers={"X-Caller": "cf-update-mdm-country"})

    mock_run.assert_called_once_with("AFG", caller="cf-update-mdm-country")


@patch(f"{ROUTES}.run_create_country")
def test_create_country_endpoint_returns_201_when_created(mock_run, client):
    mock_run.return_value = {"country_code": "AFG", "result": "CREATED"}

    response = client.post("/countries/AFG", json={"name": "Afghanistan"})

    assert response.status_code == 201
    mock_run.assert_called_once_with("AFG", {"name": "Afghanistan"}, caller="manual")


@patch(f"{ROUTES}.run_create_country")
def test_create_country_endpoint_returns_200_when_no_change(mock_run, client):
    mock_run.return_value = {"country_code": "AFG", "result": "NO_CHANGE"}

    assert client.post("/countries/AFG", json={"name": "Afghanistan"}).status_code == 200


@patch(f"{ROUTES}.run_create_country")
def test_create_country_endpoint_returns_409_on_conflict(mock_run, client):
    mock_run.side_effect = CountryConflictError("ya existe")

    assert client.post("/countries/AFG", json={"name": "Otro"}).status_code == 409


def test_create_country_endpoint_rejects_invalid_payload(client):
    assert client.post("/countries/AFG", json={"name": ""}).status_code == 400


def test_create_country_endpoint_rejects_an_empty_body(client):
    assert client.post("/countries/AFG", json={}).status_code == 400


@patch(f"{ROUTES}.run_update_country")
def test_update_country_endpoint_success(mock_run, client):
    mock_run.return_value = {"country_code": "AFG", "result": "UPDATED"}

    response = client.put("/countries/AFG", json={"population": 123})

    assert response.status_code == 200
    assert response.get_json()["payload"]["result"] == "UPDATED"
    mock_run.assert_called_once_with("AFG", {"population": 123}, caller="manual")


@patch(f"{ROUTES}.run_update_country")
def test_update_country_endpoint_not_found(mock_run, client):
    mock_run.side_effect = CountryNotFoundError("not found")

    assert client.put("/countries/ZZZ", json={"population": 123}).status_code == 404


@patch(f"{ROUTES}.run_delete_country")
def test_delete_country_endpoint_success(mock_run, client):
    mock_run.return_value = {"country_code": "AFG", "result": "DELETED"}

    response = client.delete("/countries/AFG")

    assert response.status_code == 200
    mock_run.assert_called_once_with("AFG", caller="manual")


@patch(f"{ROUTES}.run_delete_country")
def test_delete_country_endpoint_not_found(mock_run, client):
    mock_run.side_effect = CountryNotFoundError("not found")

    assert client.delete("/countries/ZZZ").status_code == 404


@patch(f"{ROUTES}.run_update_country")
def test_publish_failure_is_reported_as_502(mock_run, client):
    mock_run.side_effect = PubSubPublishError("pubsub down")

    assert client.put("/countries/AFG", json={"population": 1}).status_code == 502


@patch(f"{ROUTES}.run_get_country")
def test_audit_failure_is_reported_as_502(mock_run, client):
    mock_run.side_effect = BigQueryInsertError("bq down")

    assert client.get("/countries/AFG").status_code == 502


@patch(f"{ROUTES}.run_sync_countries")
def test_sync_endpoint_success(mock_run, client):
    mock_run.return_value = {"total": 1, "created": 1, "updated": 0, "unchanged": 0}

    response = client.post(
        "/sync/countries",
        json={"changes": [{"country_code": "AFG", "data": {"name": "Afghanistan"}}]},
        headers={"X-Caller": "cf-update-mdm-country"},
    )

    assert response.status_code == 200
    assert response.get_json()["payload"]["created"] == 1
    mock_run.assert_called_once_with(
        [{"country_code": "AFG", "data": {"name": "Afghanistan"}}], caller="cf-update-mdm-country"
    )


@patch(f"{ROUTES}.run_sync_countries")
def test_sync_endpoint_rejects_invalid_request(mock_run, client):
    mock_run.side_effect = InvalidSyncRequestError("lista vacía")

    assert client.post("/sync/countries", json={"changes": []}).status_code == 400


@pytest.mark.parametrize("body", [[], [{"country_code": "AFG"}], "texto", 5])
@patch(f"{ROUTES}.run_sync_countries")
def test_sync_endpoint_rejects_a_body_that_is_not_an_object(mock_run, body, client):
    assert client.post("/sync/countries", json=body).status_code == 400
    mock_run.assert_not_called()


@patch(f"{ROUTES}.run_sync_countries")
def test_sync_endpoint_unexpected_error_is_500(mock_run, client):
    mock_run.side_effect = RuntimeError("boom")

    assert client.post("/sync/countries", json={"changes": [{}]}).status_code == 500
