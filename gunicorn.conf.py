import multiprocessing
import os

bind = '0.0.0.0:8000'
workers = os.environ.get(
    'GUNICORN_WORKERS', multiprocessing.cpu_count() * 2 + 1
)
worker_class = 'gthread'
raw_env = ['DJANGO_SETTINGS_MODULE=nexus.settings']
capture_output = True
max_requests = 3000
max_requests_jitter = 1000
timeout = 600
preload_app = True
