from datetime import date, time

from app import create_app
from extensions import db
from models import Guard, Shift, Site, User


def test_payroll_export_returns_csv_for_selected_period():
    app = create_app()
    app.config.update(TESTING=True, SQLALCHEMY_DATABASE_URI="sqlite:///:memory:")

    with app.app_context():
        db.drop_all()
        db.create_all()

        site = Site(name="Main Site", client_name="Acme", billing_rate=100.0, is_active=True)
        guard = Guard(
            first_name="Ada",
            last_name="Lovelace",
            sia_license_number="SIA-001",
            sia_license_type="Security Guarding",
            sia_expiry_date=date(2030, 1, 1),
            pay_rate=15.0,
            is_active=True,
        )
        db.session.add_all([site, guard])
        db.session.flush()

        shift = Shift(
            site_id=site.id,
            guard_id=guard.id,
            shift_date=date(2026, 6, 1),
            start_time=time(9, 0),
            end_time=time(17, 0),
            status="completed",
            approved_by_manager=True,
            paid_out=False,
            pay_rate=15.0,
            bill_rate=100.0,
            total_hours=8.0,
        )
        db.session.add(shift)

        user = User(
            name="Payroll User",
            email="payroll@example.com",
            password_hash="x",
            role="hr_compliance",
            is_active_account=True,
        )
        db.session.add(user)
        db.session.commit()
        user_id = user.id

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["_user_id"] = str(user_id)
            session["_fresh"] = True
        response = client.get("/payroll/export/csv?period_start=2026-06-01&period_end=2026-06-07")

        assert response.status_code == 200
        assert response.headers["Content-Type"].startswith("text/csv")
        content = response.get_data(as_text=True)
        assert "Guard" in content
        assert "Ada Lovelace" in content
        assert "Regular hours" in content
        assert "Overtime hours" in content
        assert "Holiday hours" in content
