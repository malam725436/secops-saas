"""Production WSGI entry-point.

Two supported ways to serve the app in production:

1. Run this module directly -- it serves via waitress:
       python wsgi.py
2. Point the waitress CLI at the module-level ``app`` object:
       waitress-serve --host=0.0.0.0 --port=5000 "wsgi:app"

Either way the process runs in production mode (debug off, hardened
session cookies, and a required non-default SECRET_KEY) because we force
the production flag before the app is created.
"""
import os

# Force production hardening in create_app() regardless of how the process is
# launched. Must be set before importing app/config (Config reads env on import).
os.environ.setdefault("APP_ENV", "production")

from app import create_app  # noqa: E402

app = create_app()


def serve():
    from waitress import serve as waitress_serve

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "5000"))
    threads = int(os.environ.get("WAITRESS_THREADS", "8"))

    print(f" * SecOps Hub (production) serving on http://{host}:{port} via waitress ({threads} threads)")
    waitress_serve(app, host=host, port=port, threads=threads)


if __name__ == "__main__":
    serve()
