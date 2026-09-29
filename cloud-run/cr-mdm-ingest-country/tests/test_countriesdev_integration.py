from unittest.mock import Mock, patch

import pytest
import requests

from src.app.integrations.countriesdev.main import CountriesApiError, fetch_all_countries


@patch("src.app.integrations.countriesdev.main.requests.get")
def test_fetch_all_countries_returns_results_on_success(mock_get):
    mock_response = Mock()
    mock_response.json.return_value = [{"alpha3Code": "AFG", "name": "Afghanistan"}]
    mock_response.raise_for_status.return_value = None
    mock_get.return_value = mock_response

    result = fetch_all_countries()

    assert result == [{"alpha3Code": "AFG", "name": "Afghanistan"}]


@patch("src.app.integrations.countriesdev.main.requests.get")
def test_fetch_all_countries_raises_error_on_network_failure(mock_get):
    mock_get.side_effect = requests.exceptions.ConnectionError("no network")

    with pytest.raises(CountriesApiError):
        fetch_all_countries()


@patch("src.app.integrations.countriesdev.main.requests.get")
def test_fetch_all_countries_raises_error_on_invalid_json(mock_get):
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.side_effect = ValueError("not json")
    mock_get.return_value = mock_response

    with pytest.raises(CountriesApiError):
        fetch_all_countries()


@patch("src.app.integrations.countriesdev.main.requests.get")
def test_fetch_all_countries_raises_error_when_response_is_not_a_list(mock_get):
    mock_response = Mock()
    mock_response.raise_for_status.return_value = None
    mock_response.json.return_value = {"unexpected": "object"}
    mock_get.return_value = mock_response

    with pytest.raises(CountriesApiError):
        fetch_all_countries()
