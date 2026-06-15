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
