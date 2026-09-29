from datetime import datetime, timezone
from unittest.mock import patch

from src.app.services.ingestion_service import clean_record, is_valid_record, run_country_ingestion

SAMPLE_RAW_COUNTRY = {
    "alpha3Code": "AFG",
    "name": "Afghanistan",
    "capital": "Kabul",
    "population": 40218234,
    "region": "Asia",
    "currencies": [{"code": "AFN", "name": "Afghan afghani", "symbol": "؋"}],
}


def test_clean_record_flattens_countriesdev_payload():
    ts = datetime(2024, 1, 15, tzinfo=timezone.utc)

    record = clean_record(SAMPLE_RAW_COUNTRY, ts)

    assert record["country_code"] == "AFG"
    assert record["name_common"] == "Afghanistan"
    assert record["capital"] == "Kabul"
    assert record["population"] == 40218234
    assert record["region"] == "Asia"
    assert record["currency_code"] == "AFN"
    assert record["ingestion_timestamp"] == ts.isoformat()


def test_clean_record_handles_missing_currencies():
    ts = datetime(2024, 1, 15, tzinfo=timezone.utc)
    record = clean_record({"alpha3Code": "ATA", "name": "Antarctica"}, ts)

    assert record["currency_code"] is None


def test_valid_record_passes():
    record = {"country_code": "AFG", "name_common": "Afghanistan"}
    assert is_valid_record(record) is True


def test_missing_country_code_is_rejected():
    record = {"country_code": None, "name_common": "Afghanistan"}
    assert is_valid_record(record) is False


def test_missing_name_is_rejected():
    record = {"country_code": "AFG", "name_common": None}
    assert is_valid_record(record) is False


@patch("src.app.services.ingestion_service.insert_country_rows")
@patch("src.app.services.ingestion_service.fetch_all_countries")
def test_run_country_ingestion_inserts_valid_rows_and_skips_invalid(mock_fetch, mock_insert):
    mock_fetch.return_value = [
        SAMPLE_RAW_COUNTRY,
        {"alpha3Code": None, "name": "InvalidCountry"},
    ]

    result = run_country_ingestion()

    assert result["inserted"] == 1
    assert result["skipped"] == 1
    mock_insert.assert_called_once()
    inserted_rows = mock_insert.call_args[0][0]
    assert inserted_rows[0]["country_code"] == "AFG"
