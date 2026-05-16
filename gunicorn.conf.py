import os

bind = "0.0.0.0:8000"
workers = int(os.getenv("GUNICORN_WORKERS", "2"))
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 2
accesslog = "-"
errorlog = "-"
loglevel = "info"