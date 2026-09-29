from src.app.utils.common import safe_json_dumps, utc_now


def test_utc_now_returns_iso_string_with_timezone():
    result = utc_now()
    assert "T" in result
    assert "+00:00" in result


def test_safe_json_dumps_handles_normal_dict():
    assert safe_json_dumps({"a": 1}) == '{"a": 1}'


def test_safe_json_dumps_handles_non_serializable_value():
    class Weird:
        def __str__(self):
            return "weird-object"

    result = safe_json_dumps({"x": Weird()})
    assert "weird-object" in result
