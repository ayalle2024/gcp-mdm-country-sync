import json
from datetime import datetime, timezone


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_json_dumps(payload) -> str:
    """Serializa a JSON sin reventar si el payload trae tipos no serializables
    (ej. datetime) — usado solo para logging, nunca para la respuesta HTTP real.
    """
    try:
        return json.dumps(payload, default=str, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(payload)
