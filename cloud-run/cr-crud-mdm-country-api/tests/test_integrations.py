import json
from unittest.mock import MagicMock, patch

import pytest

from src.app.integrations.bigquery import main as bq
from src.app.integrations.firestore import main as fs
from src.app.integrations.pubsub import main as ps


# -------------------------------------------------------
# Pub/Sub
# -------------------------------------------------------

def test_build_event_has_the_expected_contract():
    assert ps.build_event("AFG", "UPDATE", "population", "manual") == {
        "country_code": "AFG",
        "change_type": "UPDATE",
        "field_changed": "population",
        "source": "manual",
    }


def test_publish_events_with_no_events_does_nothing():
    with patch.object(ps, "_get_publisher") as mock_get:
        assert ps.publish_events([]) == 0

    mock_get.assert_not_called()


def test_publish_events_can_be_disabled_by_environment():
    with patch.object(ps, "PUBLISH_TO_OUTPUT_TOPIC", False), patch.object(ps, "_get_publisher") as mock_get:
        assert ps.publish_events([{"country_code": "AFG"}]) == 0

    mock_get.assert_not_called()


def test_publish_events_publishes_all_and_waits_for_each():
    publisher = MagicMock()
    publisher.topic_path.return_value = "projects/p/topics/t"
    futures = [MagicMock(), MagicMock()]
    publisher.publish.side_effect = futures

    with patch.object(ps, "_get_publisher", return_value=publisher):
        count = ps.publish_events([{"country_code": "AFG"}, {"country_code": "ALB"}])

    assert count == 2
    assert publisher.publish.call_count == 2
    first_payload = json.loads(publisher.publish.call_args_list[0][0][1].decode("utf-8"))
    assert first_payload == {"country_code": "AFG"}
    for future in futures:
        future.result.assert_called_once()


def test_publish_events_wraps_failures():
    publisher = MagicMock()
    publisher.topic_path.return_value = "projects/p/topics/t"
    publisher.publish.return_value.result.side_effect = RuntimeError("timeout")

    with patch.object(ps, "_get_publisher", return_value=publisher):
        with pytest.raises(ps.PubSubPublishError):
            ps.publish_events([{"country_code": "AFG"}])


# -------------------------------------------------------
# BigQuery (auditoría)
# -------------------------------------------------------

def test_build_audit_row_has_all_columns():
    row = bq.build_audit_row("UPDATE", "AFG", result="UPDATED", caller="cf", payload={"population": 1})

    assert set(row) == {"action_id", "action_type", "country_code", "performed_at", "source", "result", "caller", "payload"}
    assert row["source"] == "cr-crud-mdm-country-api"
    assert row["caller"] == "cf"
    assert json.loads(row["payload"]) == {"population": 1}


def test_build_audit_row_defaults_caller_and_leaves_payload_empty():
    row = bq.build_audit_row("READ")

    assert row["caller"] == "manual"
    assert row["payload"] is None
    assert row["country_code"] is None


def test_log_crud_actions_inserts_all_rows_in_one_call():
    client = MagicMock()
    client.insert_rows_json.return_value = []

    with patch.object(bq, "_get_client", return_value=client):
        bq.log_crud_actions([{"a": 1}, {"a": 2}])

    client.insert_rows_json.assert_called_once()
    assert client.insert_rows_json.call_args[0][1] == [{"a": 1}, {"a": 2}]


def test_log_crud_actions_with_no_rows_does_nothing():
    with patch.object(bq, "_get_client") as mock_get:
        bq.log_crud_actions([])

    mock_get.assert_not_called()


def test_log_crud_actions_raises_when_bigquery_reports_errors():
    client = MagicMock()
    client.insert_rows_json.return_value = [{"errors": ["x"]}]

    with patch.object(bq, "_get_client", return_value=client):
        with pytest.raises(bq.BigQueryInsertError):
            bq.log_crud_actions([{"a": 1}])


# -------------------------------------------------------
# Firestore (lectura y escritura por lotes)
# -------------------------------------------------------

def _snapshot(doc_id, exists, data=None):
    snap = MagicMock()
    snap.id = doc_id
    snap.exists = exists
    snap.to_dict.return_value = data
    return snap


def test_get_countries_by_codes_returns_none_for_missing_documents():
    client = MagicMock()
    client.get_all.return_value = [_snapshot("AFG", True, {"name": "Afghanistan"}), _snapshot("ZZZ", False)]

    with patch.object(fs, "_get_client", return_value=client):
        result = fs.get_countries_by_codes(["AFG", "ZZZ", "ALB"])

    assert result == {"AFG": {"name": "Afghanistan"}, "ZZZ": None, "ALB": None}


def test_write_countries_uses_merge_and_commits_once_for_small_batches():
    client = MagicMock()
    batch = client.batch.return_value

    with patch.object(fs, "_get_client", return_value=client):
        fs.write_countries({"AFG": {"name": "A"}, "ALB": {"name": "B"}})

    assert batch.set.call_count == 2
    assert batch.set.call_args[1] == {"merge": True}
    batch.commit.assert_called_once()


def test_write_countries_splits_into_several_commits():
    client = MagicMock()
    documents = {f"C{i:03d}": {"name": str(i)} for i in range(fs.WRITE_BATCH_SIZE + 5)}

    with patch.object(fs, "_get_client", return_value=client):
        fs.write_countries(documents)

    assert client.batch.call_count == 2
    assert client.batch.return_value.commit.call_count == 2


def test_write_countries_with_no_documents_does_nothing():
    with patch.object(fs, "_get_client") as mock_get:
        fs.write_countries({})

    mock_get.assert_not_called()
