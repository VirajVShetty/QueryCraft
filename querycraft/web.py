"""Local-only HTTP interface for Querycraft."""
from pathlib import Path
import os
from flask import Flask, jsonify, request

ROOT = Path(__file__).resolve().parent.parent


def create_app(config=None):
    app = Flask(__name__, template_folder=str(ROOT / "templates"), static_folder=str(ROOT / "static"))
    custom = os.environ.get("QUERYCRAFT_DB")
    app.config.update(DATABASE=str(Path(custom).expanduser().resolve()) if custom else str(ROOT / "data" / "demo.sqlite"), IS_DEMO=not bool(custom), MAX_CONTENT_LENGTH=65536)
    if config:
        app.config.update(config)

    @app.before_request
    def local_boundary():
        from urllib.parse import urlsplit
        try:
            host = urlsplit(request.host_url).hostname
        except ValueError:
            host = None
        origin = request.headers.get("Origin")
        if host not in {"localhost", "127.0.0.1", "::1"} or request.headers.get("Sec-Fetch-Site") == "cross-site":
            return jsonify(error="This workspace accepts local, same-origin requests only."), 403
        if origin and origin.rstrip("/") != request.host_url.rstrip("/"):
            return jsonify(error="Cross-origin requests are not permitted."), 403

    @app.after_request
    def security_headers(response):
        response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/")
    def home():
        from flask import render_template
        return render_template("index.html")

    @app.get("/api/health")
    def health():
        return jsonify(status="ok")

    @app.get("/api/status")
    def status():
        from .core import EXAMPLES, settings_status
        settings = settings_status()
        return jsonify(database={"name": "Demo store" if app.config["IS_DEMO"] else Path(app.config["DATABASE"]).name, "kind": "demo" if app.config["IS_DEMO"] else "custom"}, llm_configured=settings["llm_configured"], model=settings.get("model"), examples=list(EXAMPLES) if app.config["IS_DEMO"] else [], max_rows=200)

    def database():
        from .core import initialize_demo
        path = Path(app.config["DATABASE"])
        if app.config["IS_DEMO"]:
            with init_lock:
                initialize_demo(path)
        elif not path.is_file():
            raise ValueError("Configured SQLite database does not exist. Check QUERYCRAFT_DB.")
        return path

    from threading import Lock
    init_lock = Lock()

    @app.get("/api/schema")
    def schema():
        from .core import inspect_schema
        return jsonify(tables=inspect_schema(database()))

    def body_field(name, limit):
        payload = request.get_json()
        if not isinstance(payload, dict):
            raise ValueError("Request must be a JSON object.")
        value = payload.get(name)
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise ValueError("%s must be nonempty text with at most %d characters." % (name, limit))
        return payload, value.strip()

    @app.post("/api/generate")
    def generate_sql():
        payload, question = body_field("question", 4000)
        mode = payload.get("mode", "demo")
        if mode not in ("demo", "llm"):
            raise ValueError("Mode must be demo or llm.")
        if mode == "demo" and not app.config["IS_DEMO"]:
            raise ValueError("Demo templates are available only on the bundled sample database. Configure an AI provider for your own database, or enter SQL manually.")
        from .core import generate
        return jsonify(generate(question, database(), mode=mode))

    @app.post("/api/execute")
    def execute_sql():
        _, sql = body_field("sql", 20000)
        from .core import execute_query
        return jsonify(execute_query(database(), sql, row_limit=200, timeout=2.0))

    @app.errorhandler(ValueError)
    def value_error(error):
        return jsonify(error=str(error)), 400

    from werkzeug.exceptions import HTTPException

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify(error=error.description), error.code

    @app.errorhandler(Exception)
    def unexpected_error(error):
        app.logger.error("Unexpected workspace error: %s", type(error).__name__)
        return jsonify(error="An unexpected server error occurred. Check the local server configuration."), 500

    return app
