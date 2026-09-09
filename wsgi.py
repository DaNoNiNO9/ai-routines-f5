"""WSGI entry point for production servers.

Examples:
    waitress-serve --host 0.0.0.0 --port 8000 wsgi:app   (Windows or Linux)
    gunicorn --workers 4 --bind 0.0.0.0:8000 wsgi:app    (Linux)

Set ``FORJA_ENV=production`` and the secrets in the environment or ``.env`` first.
"""

from app import create_app

app = create_app()
