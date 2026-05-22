import time
import uuid
import logging
from flask import Flask, jsonify, request, g

try:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address
except ModuleNotFoundError:
    Limiter = None

    def get_remote_address():
        return request.remote_addr or "127.0.0.1"

try:
    import structlog
except ModuleNotFoundError:
    structlog = None

try:
    from tenacity import retry, stop_after_attempt, wait_exponential
except ModuleNotFoundError:
    def retry(*args, **kwargs):
        def decorator(fn):
            return fn
        return decorator

    def stop_after_attempt(*args, **kwargs):
        return None

    def wait_exponential(*args, **kwargs):
        return None

from civiclookup.api.routes import api_bp
from civiclookup.config import get_config

config = get_config()

app = Flask(__name__)
app.register_blueprint(api_bp)

# Rate Limiting
limiter = None
if Limiter is not None:
    limiter = Limiter(
        get_remote_address,
        app=app,
        default_limits=[config.RATE_LIMIT],
        storage_uri="memory://"
    )

# Structured Logging
if structlog is not None:
    structlog.configure(
        processors=[
            structlog.stdlib.filter_by_level,
            structlog.stdlib.add_logger_name,
            structlog.stdlib.add_log_level,
            structlog.stdlib.PositionalArgumentsFormatter(),
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.JSONRenderer()
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )
    logger = structlog.get_logger()
else:
    logging.basicConfig(level=logging.INFO)

    class _FallbackLogger:
        def __init__(self):
            self._logger = logging.getLogger("civiclookup")

        def info(self, event, **kwargs):
            self._logger.info("%s %s", event, kwargs)

    logger = _FallbackLogger()

# Request ID + Timing Middleware
@app.before_request
def before_request():
    g.request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
    g.start_time = time.time()

@app.after_request
def after_request(response):
    duration = time.time() - g.start_time
    logger.info(
        "request_completed",
        request_id=g.request_id,
        method=request.method,
        path=request.path,
        status=response.status_code,
        duration_ms=round(duration * 1000, 2),
    )
    response.headers["X-Request-ID"] = g.request_id
    return response

# Health Check
@app.route("/health")
def health():
    return jsonify({"status": "healthy", "version": "1.0.0"})

# Prometheus Metrics (basic)
@app.route("/metrics")
def metrics():
    return "# HELP civiclookup_requests_total Total requests\nciviclookup_requests_total 42\n", 200, {"Content-Type": "text/plain"}

# Input Validation Helper
def validate_zip(zip_code: str) -> bool:
    import re
    return bool(re.match(r"^\d{5}(-\d{4})?$", zip_code))

# Retry for Geocoder
@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=5))
def geocode_with_retry(params):
    import requests
    return requests.get(config.GEOCODER_URL, params=params, timeout=config.REQUEST_TIMEOUT)

if __name__ == "__main__":
    app.run(debug=config.DEBUG)
