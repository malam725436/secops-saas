"""Coverage for the Stripe payment pipeline (checkout + official webhook)."""
import hashlib
import hmac
import json
import time
from datetime import date

import pyotp
import pytest

from app import create_app
from extensions import db
from models import Invoice, Site, User

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
        site = Site(name="S", client_name="C")
        db.session.add_all([owner, site])
        db.session.flush()
        db.session.add(Invoice(invoice_number="INV-1", site_id=site.id,
                               period_start=date(2026, 1, 1), period_end=date(2026, 1, 31),
                               total_amount=120.0, status="sent"))
        db.session.commit()
    # Keep a handle to the app for config tweaks within tests.
    client = app.test_client()
    client.application = app
    with client:
        yield client


def _login_owner(c):
    c.post("/login", data={"email": "owner@x.com", "password": "Passw0rd!"})
    c.post("/auth/mfa", data={"code": pyotp.TOTP(OWNER_SECRET).now()})


def _stripe_signed_headers(payload: bytes, secret: str):
    ts = int(time.time())
    signed = f"{ts}.".encode() + payload
    sig = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return {"Stripe-Signature": f"t={ts},v1={sig}"}


def test_create_payment_session_requires_stripe_key(client):
    # No STRIPE_SECRET_KEY configured -> graceful 503, never a 500.
    client.application.config["STRIPE_SECRET_KEY"] = None
    _login_owner(client)
    r = client.post("/invoices/1/pay", data={"provider": "stripe"})
    assert r.status_code == 503


def test_stripe_webhook_dev_mock_clears_invoice(client):
    # Dev (non-production) with no webhook secret: unsigned payload accepted.
    client.application.config["STRIPE_WEBHOOK_SECRET"] = None
    client.application.config["IS_PRODUCTION"] = False
    event = {"type": "checkout.session.completed",
             "data": {"object": {"metadata": {"invoice_number": "INV-1"}}}}
    r = client.post("/invoices/webhooks/stripe", json=event)
    assert r.status_code == 200 and r.get_json()["status"] == "paid"


def test_stripe_webhook_valid_signature_clears_invoice(client):
    client.application.config["STRIPE_WEBHOOK_SECRET"] = "whsec_test_secret"
    # Real Stripe events carry a top-level id + object="event".
    payload = json.dumps({"id": "evt_test_1", "object": "event",
                          "type": "checkout.session.completed",
                          "data": {"object": {"metadata": {"invoice_number": "INV-1"}}}}).encode()
    r = client.post("/invoices/webhooks/stripe", data=payload, content_type="application/json",
                    headers=_stripe_signed_headers(payload, "whsec_test_secret"))
    assert r.status_code == 200 and r.get_json()["status"] == "paid"


def test_stripe_webhook_bad_signature_rejected(client):
    client.application.config["STRIPE_WEBHOOK_SECRET"] = "whsec_test_secret"
    payload = json.dumps({"type": "checkout.session.completed",
                          "data": {"object": {"metadata": {"invoice_number": "INV-1"}}}}).encode()
    r = client.post("/invoices/webhooks/stripe", data=payload, content_type="application/json",
                    headers={"Stripe-Signature": "t=1,v1=deadbeef"})
    assert r.status_code == 400
