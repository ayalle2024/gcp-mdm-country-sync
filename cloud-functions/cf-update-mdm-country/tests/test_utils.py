from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from src.utils import (
    build_country_data,
    chunked,
    get_changes_since,
    sync_changes_via_crud,
)


def test_get_changes_since_returns_rows_from_query_result():
    fake_row = {"change_id": "chg-1", "country_code": "AFG", "change_type": "INSERT"}

    with patch("src.utils.bigquery_client") as mock_client:
        mock_client.query.return_value.result.return_value = [fake_row]

        result = get_changes_since("2026-09-25T17:00:00Z")

    assert result == [dict(fake_row)]


def test_get_changes_since_orders_by_detection_time():
    with patch("src.utils.bigquery_client") as mock_client:
        mock_client.query.return_value.result.return_value = []

        get_changes_since("2026-09-25T17:00:00Z")

    assert "ORDER BY detected_at" in mock_client.query.call_args[0][0]


def test_get_changes_since_filters_by_run_start_not_by_day():
    with patch("src.utils.bigquery_client") as mock_client:
        mock_client.query.return_value.result.return_value = []

        get_changes_since("2026-09-25T17:00:00.123456Z")

        query = mock_client.query.call_args.args[0]
        params = {p.name: p.value for p in mock_client.query.call_args.kwargs["job_config"].query_parameters}

    assert "CURRENT_DATE" not in query
    assert "detected_at >= @since" in query
    assert params["since"] == datetime(2026, 9, 25, 17, 0, 0, 123456, tzinfo=timezone.utc)


def test_build_country_data_maps_the_change_to_a_master_document(sample_change):
    data = build_country_data(sample_change)

    assert data == {
        "country_code": "AFG",
        "name": "Afghanistan",
        "capital": "Kabul",
        "population": 40218234,
        "region": "Asia",
        "currency_code": "AFN",
        "last_change_type": "INSERT",
        "last_change_id": "chg-1",
    }


def test_chunked_splits_a_list_into_groups():
    assert list(chunked([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]


def test_chunked_of_an_empty_list_yields_nothing():
    assert list(chunked([], 100)) == []


def _crud_response(payload, status=200):
    response = MagicMock()
    response.status_code = status
    response.text = "body"
    response.json.return_value = {"payload": payload}
    return response


@patch("src.utils.requests.post")
@patch("src.utils.get_id_token", return_value="token-123")
def test_sync_sends_one_authenticated_request_per_chunk_and_adds_up_totals(mock_token, mock_post, sample_change):
    mock_post.side_effect = [
        _crud_response({"total": 2, "created": 2, "updated": 0, "unchanged": 0}),
        _crud_response({"total": 1, "created": 0, "updated": 1, "unchanged": 0}),
    ]

    with patch("src.utils.CRUD_SYNC_CHUNK_SIZE", 2):
        totals = sync_changes_via_crud([sample_change, sample_change, sample_change])

    assert totals == {"total": 3, "created": 2, "updated": 1, "unchanged": 0}
    assert mock_post.call_count == 2

    mock_token.assert_called_once_with("https://crud.example.run.app")
    args, kwargs = mock_post.call_args_list[0]
    assert args[0] == "https://crud.example.run.app/sync/countries"
    assert kwargs["headers"]["Authorization"] == "Bearer token-123"
    assert kwargs["headers"]["X-Caller"] == "cf-update-mdm-country"
    assert len(kwargs["json"]["changes"]) == 2
    assert kwargs["json"]["changes"][0]["country_code"] == "AFG"
    assert kwargs["json"]["changes"][0]["data"]["name"] == "Afghanistan"


@patch("src.utils.requests.post")
@patch("src.utils.get_id_token", return_value="token-123")
def test_sync_raises_when_the_crud_answers_with_an_error(mock_token, mock_post, sample_change):
    mock_post.return_value = _crud_response({}, status=502)

    with pytest.raises(RuntimeError, match="502"):
        sync_changes_via_crud([sample_change])


@patch("src.utils.requests.post")
@patch("src.utils.get_id_token", return_value="token-123")
def test_sync_strips_the_trailing_slash_of_the_crud_url(mock_token, mock_post, sample_change):
    mock_post.return_value = _crud_response({"total": 1, "created": 1, "updated": 0, "unchanged": 0})

    with patch("src.utils.CRUD_API_URL", "https://crud.example.run.app/"):
        sync_changes_via_crud([sample_change])

    mock_token.assert_called_once_with("https://crud.example.run.app")
    assert mock_post.call_args[0][0] == "https://crud.example.run.app/sync/countries"
