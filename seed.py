"""Populate the database with sample data for local development.

Usage: python seed.py
"""
from datetime import date, time, timedelta

import pyotp

from app import create_app
from extensions import db
from models import (
    ROLE_CLEANER,
    ROLE_GUARD,
    ROLE_HR_COMPLIANCE,
    ROLE_OPS_MANAGER,
    ROLE_OWNER,
    ROLE_RECEPTIONIST,
    ROLE_SUPERVISOR,
    STAFF_CATEGORY_CLEANER,
    STAFF_CATEGORY_RECEPTIONIST,
    STAFF_CATEGORY_SUPERVISOR,
    Guard,
    Shift,
    Site,
    User,
)

app = create_app()

DEMO_PASSWORD = "Passw0rd!"

with app.app_context():
    db.drop_all()
    db.create_all()

    today = date.today()

    guards = [
        Guard(
            first_name="Amara",
            last_name="Okafor",
            email="amara.okafor@example.com",
            phone="07700 900111",
            sia_license_number="SIA-1001-2024",
            sia_license_type="Door Supervisor",
            sia_expiry_date=today + timedelta(days=400),
            dbs_expiry_date=today + timedelta(days=600),
            pay_rate=12.50,
            bank_account_number="12345678",
            bank_sort_code="20-00-00",
            next_of_kin_name="Chidi Okafor",
            next_of_kin_relationship="Sibling",
            next_of_kin_contact="07700 900911",
        ),
        Guard(
            first_name="Liam",
            last_name="Whitfield",
            email="liam.whitfield@example.com",
            phone="07700 900222",
            sia_license_number="SIA-1002-2024",
            sia_license_type="Security Guarding",
            sia_expiry_date=today + timedelta(days=18),  # expiring soon
            dbs_expiry_date=today + timedelta(days=300),
            pay_rate=13.00,
            bank_account_number="23456789",
            bank_sort_code="20-00-01",
            next_of_kin_name="Sarah Whitfield",
            next_of_kin_relationship="Spouse",
            next_of_kin_contact="07700 900912",
        ),
        Guard(
            first_name="Priya",
            last_name="Nair",
            email="priya.nair@example.com",
            phone="07700 900333",
            sia_license_number="SIA-1003-2024",
            sia_license_type="CCTV (Public Space Surveillance)",
            sia_expiry_date=today - timedelta(days=5),  # expired
            dbs_expiry_date=today + timedelta(days=120),
            pay_rate=12.00,
            bank_account_number="34567890",
            bank_sort_code="20-00-02",
            next_of_kin_name="Raj Nair",
            next_of_kin_relationship="Parent",
            next_of_kin_contact="07700 900913",
        ),
        Guard(
            first_name="Connor",
            last_name="Reilly",
            email="connor.reilly@example.com",
            phone="07700 900444",
            sia_license_number="SIA-1004-2024",
            sia_license_type="Close Protection",
            sia_expiry_date=today + timedelta(days=200),
            dbs_expiry_date=today + timedelta(days=200),
            pay_rate=15.00,
            bank_account_number="45678901",
            bank_sort_code="20-00-03",
            next_of_kin_name="Maeve Reilly",
            next_of_kin_relationship="Parent",
            next_of_kin_contact="07700 900914",
        ),
    ]
    db.session.add_all(guards)
    db.session.commit()

    sites = [
        Site(
            name="Riverside Business Park",
            client_name="Riverside Holdings Ltd",
            address="12 Riverside Way, Manchester, M1 4AB",
            site_manager="Hannah George",
            pay_rate_default=12.50,
            bill_rate_default=21.00,
            billing_rate=21.00,
        ),
        Site(
            name="Westgate Shopping Centre",
            client_name="Westgate Retail Group",
            address="88 Westgate Road, Leeds, LS1 2QF",
            site_manager="Tomasz Nowak",
            pay_rate_default=13.00,
            bill_rate_default=22.50,
            billing_rate=22.50,
        ),
    ]
    db.session.add_all(sites)
    db.session.commit()

    shifts = [
        Shift(
            site_id=sites[0].id,
            guard_id=guards[0].id,
            shift_date=today - timedelta(days=2),
            start_time=time(18, 0),
            end_time=time(6, 0),
            role="Night Patrol",
            pay_rate=sites[0].pay_rate_default,
            bill_rate=sites[0].bill_rate_default,
            status="completed",
            approved_by_manager=True,
        ),
        Shift(
            site_id=sites[0].id,
            guard_id=guards[1].id,
            shift_date=today - timedelta(days=1),
            start_time=time(6, 0),
            end_time=time(18, 0),
            role="Day Reception",
            pay_rate=sites[0].pay_rate_default,
            bill_rate=sites[0].bill_rate_default,
            status="completed",
            approved_by_manager=True,
        ),
        Shift(
            site_id=sites[1].id,
            guard_id=guards[3].id,
            shift_date=today + timedelta(days=1),
            start_time=time(8, 0),
            end_time=time(20, 0),
            role="Mall Patrol",
            pay_rate=sites[1].pay_rate_default,
            bill_rate=sites[1].bill_rate_default,
            status="scheduled",
        ),
        Shift(
            site_id=sites[1].id,
            guard_id=guards[2].id,
            shift_date=today - timedelta(days=3),
            start_time=time(8, 0),
            end_time=time(20, 0),
            role="Mall Patrol",
            pay_rate=sites[1].pay_rate_default,
            bill_rate=sites[1].bill_rate_default,
            status="completed",
        ),
    ]
    db.session.add_all(shifts)
    db.session.commit()

    owner_mfa_secret = pyotp.random_base32()

    users = [
        User(
            name="Dana Whitcombe",
            email="owner@secops.example",
            role=ROLE_OWNER,
            language="en",
            mfa_secret=owner_mfa_secret,
            mfa_enabled=True,
        ),
        User(
            name="Marcus Adeyemi",
            email="ops.manager@secops.example",
            role=ROLE_OPS_MANAGER,
            language="en",
        ),
        User(
            name="Sofia Mendes",
            email="hr@secops.example",
            role=ROLE_HR_COMPLIANCE,
            language="es",
        ),
        User(
            name="Tomasz Nowak",
            email="supervisor@secops.example",
            role=ROLE_SUPERVISOR,
            language="ro",
        ),
        User(
            name="Aaliyah Hussain",
            email="reception@secops.example",
            role=ROLE_RECEPTIONIST,
            language="bn",
        ),
        User(
            name="Amara Okafor",
            email="guard@secops.example",
            role=ROLE_GUARD,
            language="en",
            guard_id=guards[0].id,
        ),
        User(
            name="Greg Sullivan",
            email="cleaner@secops.example",
            role=ROLE_CLEANER,
            language="en",
        ),
    ]
    for user in users:
        user.set_password(DEMO_PASSWORD)
    db.session.add_all(users)
    db.session.commit()

    # Master Roster demo data - non-guard staff scheduled this week.
    supervisor, receptionist, cleaner = users[3], users[4], users[6]
    roster_shifts = [
        Shift(
            site_id=sites[0].id,
            assigned_user_id=supervisor.id,
            staff_category=STAFF_CATEGORY_SUPERVISOR,
            shift_date=today,
            start_time=time(8, 0),
            end_time=time(16, 0),
            role="Site Supervisor",
        ),
        Shift(
            site_id=sites[0].id,
            assigned_user_id=receptionist.id,
            staff_category=STAFF_CATEGORY_RECEPTIONIST,
            shift_date=today,
            start_time=time(8, 0),
            end_time=time(17, 0),
            role="Front Desk",
        ),
        Shift(
            site_id=sites[1].id,
            assigned_user_id=cleaner.id,
            staff_category=STAFF_CATEGORY_CLEANER,
            shift_date=today + timedelta(days=1),
            start_time=time(6, 0),
            end_time=time(10, 0),
            role="Morning Clean",
        ),
        Shift(
            site_id=sites[1].id,
            assigned_user_id=supervisor.id,
            staff_category=STAFF_CATEGORY_SUPERVISOR,
            shift_date=today + timedelta(days=2),
            start_time=time(8, 0),
            end_time=time(16, 0),
            role="Site Supervisor",
        ),
    ]
    db.session.add_all(roster_shifts)
    db.session.commit()

    print("Seed data created:")
    print(f"  Guards: {Guard.query.count()}")
    print(f"  Sites:  {Site.query.count()}")
    print(f"  Shifts: {Shift.query.count()}")
    print(f"  Users:  {User.query.count()}")
    print()
    print("Demo accounts (password for all: " + DEMO_PASSWORD + "):")
    for user in users:
        print(f"  {user.email:<28} {user.role_label}")
    print()
    print(f"Owner MFA secret (for an authenticator app, e.g. Google Authenticator): {owner_mfa_secret}")
    print(f"Current owner TOTP code: {pyotp.TOTP(owner_mfa_secret).now()}")
