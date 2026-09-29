from unittest.mock import patch

import pytest

from src.main import main


@patch("src.main.forward_to_downstream")
def test_main_processes_event_successfully(mock_forward, valid_pubsub_event, valid_country_update):
    result = main(valid_pubsub_event)

    assert result == valid_country_update
    mock_forward.assert_called_once_with(valid_country_update)


@patch("src.main.forward_to_downstream", side_effect=RuntimeError("webhook down"))
def test_main_raises_when_webhook_fails(mock_forward, valid_pubsub_event):
    with pytest.raises(RuntimeError, match="webhook down"):
        main(valid_pubsub_event)
