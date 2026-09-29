from flask import Flask, jsonify

from src.app.api.routes.countries import countries_bp
from src.app.core.config import PROJECT_ID, SERVICE_NAME
from src.app.utils.common import utc_now

app = Flask(__name__)

# -------------------------------------------------------
# Registro de rutas
# -------------------------------------------------------

app.register_blueprint(countries_bp)


# -------------------------------------------------------
# Health check
# -------------------------------------------------------

@app.route("/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "service": SERVICE_NAME,
        "project_id": PROJECT_ID,
        "timestamp": utc_now(),
    }), 200
