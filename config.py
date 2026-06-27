import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", f"sqlite:///{os.path.join(BASE_DIR, 'instance', 'secops.db')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Guard Profile Vault document uploads (profile picture, SIA licence scan).
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads", "guards")
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024  # 8MB

    MAIL_SERVER = os.environ.get("MAIL_SERVER", "localhost")
    MAIL_PORT = int(os.environ.get("MAIL_PORT", "25"))
    MAIL_USE_TLS = os.environ.get("MAIL_USE_TLS", "false").lower() == "true"
    MAIL_USE_SSL = os.environ.get("MAIL_USE_SSL", "false").lower() == "true"
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
    MAIL_DEFAULT_SENDER = os.environ.get("MAIL_DEFAULT_SENDER", "no-reply@secops-saas.local")
    INVOICE_EMAIL_RECIPIENT = os.environ.get("INVOICE_EMAIL_RECIPIENT", "billing@secops-saas.local")
