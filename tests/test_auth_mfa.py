"""Coverage for the hardened MFA login flow (MFA_REQUIRED_ROLES)."""
from datetime import date, time

import pyotp
import pytest

from app import create_app
from extensions import db
from models import Site, User

OWNER_SECRET = "JBSWY3DPEHPK3PXP"


@pytest.fixture()
def client():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")
    with app.app_context():
        db.drop_all()
        db.create_all()
        owner = User(name="Owner", email="owner@x.com", role="owner",
                     is_active_account=True, mfa_secret=OWNER_SECRET, mfa_enabled=True)
        owner.set_password("Passw0rd!")
        # Supervisor is NOT MFA-required and is non-frontline-blocked from the
        # dashboard, but is a clean "no MFA" control for the login path.
        supervisor = User(name="Sup", email="sup@x.com", role="supervisor", is_active_account=True)
        supervisor.set_password("Passw0rd!")
        # Eligible (ops_manager) but NOT yet provisioned: no mfa_secret -> must
        # be routed through first-time enrollment.
        newadmin = User(name="New Ops", email="newops@x.com", role="ops_manager", is_active_account=True)
        newadmin.set_password("Passw0rd!")
        db.session.add_all([owner, supervisor, newadmin, Site(name="S", client_name="C")])
        db.session.commit()
    client = app.test_client()
    client.application = app
    with client:
        yield client


def test_high_priv_login_redirects_to_mfa_and_is_not_authenticated(client):
    resp = client.post("/login", data={"email": "owner@x.com", "password": "Passw0rd!"})
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/auth/mfa")
    # Not authenticated yet: hitting a protected page bounces back to login.
    protected = client.get("/invoices/", follow_redirects=False)
    assert protected.status_code in (302, 401)
    assert "/auth/mfa" not in protected.headers.get("Location", "/auth/mfa")  # not the dashboard


def test_correct_totp_completes_login(client):
    client.post("/login", data={"email": "owner@x.com", "password": "Passw0rd!"})
    code = pyotp.TOTP(OWNER_SECRET).now()
    resp = client.post("/auth/mfa", data={"code": code}, follow_redirects=False)
    assert resp.status_code == 302
    # Now authenticated: finance area is reachable (200).
    assert client.get("/invoices/").status_code == 200


def test_wrong_totp_is_rejected(client):
    client.post("/login", data={"email": "owner@x.com", "password": "Passw0rd!"})
    resp = client.post("/auth/mfa", data={"code": "000000"}, follow_redirects=False)
    assert resp.status_code == 401
    # Still not authenticated.
    assert client.get("/invoices/").status_code in (302, 401)


def test_non_mfa_role_logs_in_directly(client):
    resp = client.post("/login", data={"email": "sup@x.com", "password": "Passw0rd!"},
                       follow_redirects=False)
    assert resp.status_code == 302
    assert not resp.headers["Location"].endswith("/auth/mfa")
    # Supervisor can reach the roster hub without an MFA step.
    assert client.get("/roster/").status_code == 200


def test_mfa_page_requires_pending_challenge(client):
    # Visiting the MFA page with no pending login bounces to /login.
    resp = client.get("/auth/mfa", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/login")


def test_unprovisioned_eligible_user_is_redirected_to_enrollment(client):
    # Eligible role, no enrolled secret -> login routes straight to enrollment.
    resp = client.post("/login", data={"email": "newops@x.com", "password": "Passw0rd!"},
                       follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/auth/mfa/enroll")

    # The enrollment page renders with a manual-entry key and a QR image.
    page = client.get("/auth/mfa/enroll")
    assert page.status_code == 200
    html = page.get_data(as_text=True)
    assert 'data:image/png;base64,' in html  # QR rendered inline
    with client.session_transaction() as sess:
        assert sess.get("pending_mfa_secret")  # provisional secret issued
        assert sess.get("mfa_verified") is False


def test_enrollment_with_correct_code_saves_secret_and_logs_in(client):
    client.post("/login", data={"email": "newops@x.com", "password": "Passw0rd!"})
    client.get("/auth/mfa/enroll")
    with client.session_transaction() as sess:
        secret = sess["pending_mfa_secret"]

    resp = client.post("/auth/mfa/enroll", data={"code": pyotp.TOTP(secret).now()},
                       follow_redirects=False)
    assert resp.status_code == 302  # enrolled + authenticated -> dashboard

    # Secret persisted and session marked verified; finance area now reachable.
    with client.application.app_context():
        saved = User.query.filter_by(email="newops@x.com").first()
        assert saved.mfa_secret == secret and saved.mfa_enabled is True
    with client.session_transaction() as sess:
        assert sess.get("mfa_verified") is True
    assert client.get("/invoices/").status_code == 200


def test_enrollment_with_wrong_code_keeps_secret_and_does_not_persist(client):
    client.post("/login", data={"email": "newops@x.com", "password": "Passw0rd!"})
    client.get("/auth/mfa/enroll")
    with client.session_transaction() as sess:
        secret = sess["pending_mfa_secret"]

    resp = client.post("/auth/mfa/enroll", data={"code": "000000"})
    assert resp.status_code == 200  # re-rendered with an error, not redirected

    # Provisional secret is retained for another attempt, nothing saved to DB.
    with client.session_transaction() as sess:
        assert sess["pending_mfa_secret"] == secret
    with client.application.app_context():
        assert User.query.filter_by(email="newops@x.com").first().mfa_secret is None
