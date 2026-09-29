from unittest.mock import patch

import pytest

from src.app.integrations.firestore.main import CountryNotFoundError
from src.app.services.crud_service import (
    CountryConflictError,
    InvalidSyncRequestError,
    diff_fields,
    is_valid_country_payload,
    is_valid_new_country_payload,
    run_create_country,
    run_delete_country,
    run_get_country,
    run_list_countries,
    run_sync_countries,
    run_update_country,
)

SVC = "src.app.services.crud_service"

AFG = {"name": "Afghanistan", "capital": "Kabul", "population": 100, "region": "Asia", "currency_code": "AFN"}


# -------------------------------------------------------
# Validación y comparación
# -------------------------------------------------------

def test_valid_payload_passes():
    assert is_valid_country_payload({"name": "Afghanistan"}) is True


def test_empty_dict_is_valid_for_partial_update():
    assert is_valid_country_payload({}) is True


def test_payload_with_empty_name_is_rejected():
    assert is_valid_country_payload({"name": ""}) is False


def test_new_country_requires_a_name():
    assert is_valid_new_country_payload({}) is False
    assert is_valid_new_country_payload({"name": ""}) is False
    assert is_valid_new_country_payload({"name": "Afghanistan"}) is True


def test_non_dict_payload_is_rejected():
    assert is_valid_country_payload("not-a-dict") is False


def test_diff_fields_detects_changed_business_field():
    assert diff_fields(AFG, {"population": 200, "name": "Afghanistan"}) == ["population"]


def test_diff_fields_ignores_metadata_and_missing_fields():
    assert diff_fields(AFG, {"last_change_id": "x", "name": "Afghanistan"}) == []


def test_diff_fields_with_no_current_document_lists_every_field_sent():
    assert diff_fields(None, {"name": "Afghanistan"}) == ["name"]


# -------------------------------------------------------
# Lecturas
# -------------------------------------------------------

@patch(f"{SVC}.log_crud_action")
@patch(f"{SVC}.list_countries")
def test_run_list_countries_logs_read(mock_list, mock_log):
    mock_list.return_value = [{"country_code": "AFG"}]

    assert run_list_countries() == [{"country_code": "AFG"}]
    mock_log.assert_called_once_with("READ", None, result="OK", caller="manual")


@patch(f"{SVC}.log_crud_action")
@patch(f"{SVC}.get_country")
def test_run_get_country_logs_read_with_code(mock_get, mock_log):
    mock_get.return_value = {"country_code": "AFG"}

    assert run_get_country("AFG") == {"country_code": "AFG"}
    mock_log.assert_called_once_with("READ", "AFG", result="OK", caller="manual")


# -------------------------------------------------------
# Escrituras individuales
# -------------------------------------------------------

@patch(f"{SVC}.publish_events")
@patch(f"{SVC}.log_crud_action")
@patch(f"{SVC}.write_countries")
@patch(f"{SVC}.get_countries_by_codes", return_value={"AFG": None})
def test_create_new_country_writes_audits_and_publishes(mock_get, mock_write, mock_log, mock_publish):
    outcome = run_create_country("AFG", {"name": "Afghanistan"})

    assert outcome == {"country_code": "AFG", "result": "CREATED"}
    mock_write.assert_called_once_with({"AFG": {"name": "Afghanistan", "country_code": "AFG"}})
    mock_log.assert_called_once_with("CREATE", "AFG", result="CREATED", caller="manual", payload={"name": "Afghanistan"})
    mock_publish.assert_called_once_with(
        [{"country_code": "AFG", "change_type": "INSERT", "field_changed": None, "source": "manual"}]
    )


@patch(f"{SVC}.publish_events")
@patch(f"{SVC}.log_crud_action")
@patch(f"{SVC}.write_countries")
@patch(f"{SVC}.get_countries_by_codes", return_value={"AFG": AFG})
def test_create_existing_identical_country_is_no_change(mock_get, mock_write, mock_log, mock_publish):
    outcome = run_create_country("AFG", {"name": "Afghanistan"})

    assert outcome["result"] == "NO_CHANGE"
    mock_write.assert_not_called()
    mock_publish.assert_not_called()
    mock_log.assert_called_once()


@patch(f"{SVC}.publish_events")
@patch(f"{SVC}.write_countries")
@patch(f"{SVC}.get_countries_by_codes", return_value={"AFG": AFG})
def test_create_existing_different_country_raises_conflict(mock_get, mock_write, mock_publish):
    with pytest.raises(CountryConflictError):
        run_create_country("AFG", {"name": "Otro nombre"})

    mock_write.assert_not_called()
    mock_publish.assert_not_called()


@patch(f"{SVC}.get_countries_by_codes", return_value={"ZZZ": None})
def test_update_missing_country_raises_not_found(mock_get):
    with pytest.raises(CountryNotFoundError):
        run_update_country("ZZZ", {"population": 1})


@patch(f"{SVC}.publish_events")
@patch(f"{SVC}.log_crud_action")
@patch(f"{SVC}.write_countries")
@patch(f"{SVC}.get_countries_by_codes", return_value={"AFG": AFG})
def test_update_changed_country_writes_and_publishes_first_changed_field(mock_get, mock_write, mock_log, mock_publish):
    outcome = run_update_country("AFG", {"population": 200})

    assert outcome == {"country_code": "AFG", "result": "UPDATED"}
    mock_write.assert_called_once_with({"AFG": {"population": 200, "country_code": "AFG"}})
    mock_publish.assert_called_once_with(
        [{"country_code": "AFG", "change_type": "UPDATE", "field_changed": "population", "source": "manual"}]
    )


@patch(f"{SVC}.publish_events")
@patch(f"{SVC}.log_crud_action")
@patch(f"{SVC}.write_countries")
@patch(f"{SVC}.get_countries_by_codes", return_value={"AFG": AFG})
def test_update_with_same_data_is_no_change(mock_get, mock_write, mock_log, mock_publish):
    outcome = run_update_country("AFG", {"population": 100})

    assert outcome["result"] == "NO_CHANGE"
    mock_write.assert_not_called()
    mock_publish.assert_not_called()


@patch(f"{SVC}.publish_events")
@patch(f"{SVC}.log_crud_action")
@patch(f"{SVC}.delete_country")
def test_delete_country_audits_and_publishes(mock_delete, mock_log, mock_publish):
    outcome = run_delete_country("AFG")

    assert outcome == {"country_code": "AFG", "result": "DELETED"}
    mock_delete.assert_called_once_with("AFG")
    mock_log.assert_called_once_with("DELETE", "AFG", result="DELETED", caller="manual")
    mock_publish.assert_called_once_with(
        [{"country_code": "AFG", "change_type": "DELETE", "field_changed": None, "source": "manual"}]
    )


# -------------------------------------------------------
# Sincronización por lotes
# -------------------------------------------------------

@patch(f"{SVC}.publish_events")
@patch(f"{SVC}.log_crud_actions")
@patch(f"{SVC}.write_countries")
@patch(f"{SVC}.get_countries_by_codes")
def test_sync_counts_created_updated_and_unchanged(mock_get, mock_write, mock_log, mock_publish):
    mock_get.return_value = {"AFG": None, "ALB": {**AFG, "name": "Albania"}, "DZA": {**AFG, "name": "Algeria"}}
    changes = [
        {"country_code": "AFG", "data": AFG},
        {"country_code": "ALB", "data": {"name": "Albania", "population": 999}},
        {"country_code": "DZA", "data": {"name": "Algeria"}},
    ]

    counts = run_sync_countries(changes, caller="cf-update-mdm-country")

    assert counts == {"total": 3, "created": 1, "updated": 1, "unchanged": 1}
    written = mock_write.call_args[0][0]
    assert set(written) == {"AFG", "ALB"}
    mock_log.assert_called_once()
    assert len(mock_log.call_args[0][0]) == 3
    events = mock_publish.call_args[0][0]
    assert [(e["country_code"], e["change_type"], e["source"]) for e in events] == [
        ("AFG", "INSERT", "cf-update-mdm-country"),
        ("ALB", "UPDATE", "cf-update-mdm-country"),
    ]


@patch(f"{SVC}.publish_events")
@patch(f"{SVC}.log_crud_actions")
@patch(f"{SVC}.write_countries")
@patch(f"{SVC}.get_countries_by_codes", return_value={"AFG": AFG})
def test_sync_resending_the_same_data_publishes_nothing(mock_get, mock_write, mock_log, mock_publish):
    counts = run_sync_countries([{"country_code": "AFG", "data": AFG}], caller="cf")

    assert counts == {"total": 1, "created": 0, "updated": 0, "unchanged": 1}
    mock_write.assert_called_once_with({})
    mock_publish.assert_called_once_with([])


@patch(f"{SVC}.publish_events")
@patch(f"{SVC}.log_crud_actions")
@patch(f"{SVC}.write_countries")
@patch(f"{SVC}.get_countries_by_codes", return_value={"AFG": None})
def test_sync_duplicate_code_in_same_batch_is_only_created_once(mock_get, mock_write, mock_log, mock_publish):
    counts = run_sync_countries(
        [{"country_code": "afg", "data": AFG}, {"country_code": "AFG", "data": AFG}], caller="cf"
    )

    assert counts == {"total": 2, "created": 1, "updated": 0, "unchanged": 1}


@pytest.mark.parametrize(
    "changes",
    [None, [], "x", [{"country_code": "AFG"}], [{"data": {}}], [{"country_code": "", "data": {}}], ["texto"]],
)
def test_sync_rejects_invalid_requests(changes):
    with pytest.raises(InvalidSyncRequestError):
        run_sync_countries(changes, caller="cf")


def test_sync_rejects_a_change_with_an_empty_name():
    changes = [{"country_code": "AFG", "data": {"name": ""}}]

    with pytest.raises(InvalidSyncRequestError, match="AFG"):
        run_sync_countries(changes, caller="cf")


@patch(f"{SVC}.SYNC_MAX_BATCH", 2)
def test_sync_rejects_more_changes_than_the_maximum():
    changes = [{"country_code": c, "data": {}} for c in ("AFG", "ALB", "DZA")]

    with pytest.raises(InvalidSyncRequestError):
        run_sync_countries(changes, caller="cf")
