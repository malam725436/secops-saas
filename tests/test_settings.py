from datetime import date

from app import create_app
from extensions import db
from models import Setting, User


def test_settings_form_persists_mail_config_and_refreshes_app_config():
    app = create_app()
    app.config.update(
        TESTING=True,
        WTF_CSRF_ENABLED=False,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
    )

    with app.app_context():
        db.drop_all()
        db.create_all()

        user = User(
            name="Owner",
            email="owner@example.com",
            role="owner",
            is_active_account=True,
        )
        user.set_password("Password1!")
        db.session.add(user)
        db.session.commit()

    with app.test_client() as client:
        login_resp = client.post(
            "/login",
            data={"email": "owner@example.com", "password": "Password1!"},
            follow_redirects=False,
        )
        assert login_resp.status_code == 302

        response = client.post(
            "/settings",
            data={
                "MAIL_SERVER": "smtp.example.com",
                "MAIL_PORT": "2525",
                "MAIL_USE_TLS": "on",
                "MAIL_USERNAME": "mailer",
                "MAIL_PASSWORD": "secret",
            },
            follow_redirects=False,
        )

        assert response.status_code == 302

        with app.app_context():
            server = Setting.query.filter_by(key="MAIL_SERVER").first()
            port = Setting.query.filter_by(key="MAIL_PORT").first()
            assert server.value == "smtp.example.com"
            assert port.value == "2525"

            assert app.config["MAIL_SERVER"] == "smtp.example.com"
            assert app.config["MAIL_PORT"] == 2525
            assert app.config["MAIL_USE_TLS"] is True
