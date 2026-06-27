from datetime import date

import pytest

from app import create_app
from extensions import db
from models import Invoice, Site, User


@pytest.fixture()
def client():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")

    with app.app_context():
        db.drop_all()
        db.create_all()

        site = Site(name="Main Site", client_name="Acme", billing_rate=100.0, is_active=True)
        db.session.add(site)
        db.session.flush()

        user = User(
            name="Owner",
            email="owner@secops.example",
            role="owner",
            is_active_account=True,
        )
        user.set_password("Passw0rd!")
        db.session.add(user)

        invoice = Invoice(
            invoice_number="INV-001-202606-001",
            site_id=site.id,
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 7),
            issue_date=date(2026, 6, 8),
            total_amount=120.0,
        )
        db.session.add(invoice)
        db.session.commit()

    with app.test_client() as client:
        yield client


def test_invoice_download_returns_pdf(client):
    login_resp = client.post(
        "/login",
        data={"email": "owner@secops.example", "password": "Passw0rd!"},
        follow_redirects=False,
    )
    assert login_resp.status_code == 302

    resp = client.get("/invoices/1/download", follow_redirects=False)
    assert resp.status_code == 200
    assert resp.mimetype == "application/pdf"
    assert resp.headers["Content-Disposition"].startswith("attachment")


def test_invoice_download_redirects_when_invoice_is_missing(client):
    login_resp = client.post(
        "/login",
        data={"email": "owner@secops.example", "password": "Passw0rd!"},
        follow_redirects=False,
    )
    assert login_resp.status_code == 302

    resp = client.get("/invoices/999999/download", follow_redirects=False)
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/invoices/")
