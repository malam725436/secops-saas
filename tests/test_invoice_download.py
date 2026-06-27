import pytest

from app import create_app


@pytest.fixture()
def client():
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
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
