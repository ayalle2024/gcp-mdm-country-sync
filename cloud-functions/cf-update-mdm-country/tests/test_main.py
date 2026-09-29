from unittest.mock import patch

import pytest

from src.main import main


@patch("src.main.sync_changes_via_crud")
@patch("src.main.get_changes_since")
def test_main_sends_all_changes_to_the_crud(mock_get, mock_sync, fake_request, sample_change):
    mock_get.return_value = [sample_change, sample_change]
    mock_sync.return_value = {"total": 2, "created": 1, "updated": 0, "unchanged": 1}

    body, status = main(fake_request)

    assert status == 200
    assert body == {"synced": 2, "created": 1, "updated": 0, "unchanged": 1}
    mock_sync.assert_called_once_with([sample_change, sample_change])


@patch("src.main.sync_changes_via_crud")
@patch("src.main.get_changes_since", return_value=[])
def test_main_returns_zero_and_does_not_call_the_crud_when_no_changes(mock_get, mock_sync, fake_request):
    body, status = main(fake_request)

    assert status == 200
    assert body == {"synced": 0, "created": 0, "updated": 0, "unchanged": 0}
    mock_sync.assert_not_called()


@patch("src.main.get_changes_since", side_effect=RuntimeError("bigquery down"))
def test_main_raises_on_query_failure(mock_get, fake_request):
    with pytest.raises(RuntimeError, match="bigquery down"):
        main(fake_request)


@patch("src.main.sync_changes_via_crud", side_effect=RuntimeError("crud down"))
@patch("src.main.get_changes_since")
def test_main_raises_when_the_crud_fails(mock_get, mock_sync, fake_request, sample_change):
    mock_get.return_value = [sample_change]

    with pytest.raises(RuntimeError, match="crud down"):
        main(fake_request)


@patch("src.main.sync_changes_via_crud")
@patch("src.main.get_changes_since")
def test_main_passes_run_start_to_the_query(mock_get, mock_sync, fake_request):
    mock_get.return_value = []

    main(fake_request)

    mock_get.assert_called_once_with("2026-09-25T17:00:00Z")


@pytest.mark.parametrize("body", [{}, None, [], {"since": ""}])
@patch("src.main.get_changes_since")
def test_main_returns_400_without_since(mock_get, body, fake_request):
    fake_request.get_json.return_value = body

    response, status = main(fake_request)

    assert status == 400
    assert "since" in response["error"]
    mock_get.assert_not_called()
