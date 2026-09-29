from src.gcp_logging import GCPLogger


def test_get_logger_returns_logger_with_correct_name():
    logger = GCPLogger.get_logger("some-logger-name")
    assert logger.name == "some-logger-name"


def test_get_logger_does_not_propagate_to_root():
    logger = GCPLogger.get_logger("another-logger-name")
    assert logger.propagate is False


def test_is_running_on_cloudrun_false_when_no_k_service_env(monkeypatch):
    monkeypatch.delenv("K_SERVICE", raising=False)
    assert GCPLogger.is_running_on_cloudrun() is False


def test_is_running_on_cloudrun_true_when_k_service_env_set(monkeypatch):
    monkeypatch.setenv("K_SERVICE", "cf-update-mdm-country")
    assert GCPLogger.is_running_on_cloudrun() is True
