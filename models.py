from datetime import date, datetime, timedelta, timezone, UTC

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from extensions import db

# ---------------------------------------------------------------------------
# Roles & RBAC groupings
# ---------------------------------------------------------------------------
ROLE_OWNER = "owner"
ROLE_OPS_MANAGER = "ops_manager"
ROLE_HR_COMPLIANCE = "hr_compliance"
ROLE_SUPERVISOR = "supervisor"
ROLE_RECEPTIONIST = "receptionist"
ROLE_GUARD = "guard"
ROLE_CLEANER = "cleaner"

ROLE_LABELS = {
    ROLE_OWNER: "Owner / Director",
    ROLE_OPS_MANAGER: "Operations Manager",
    ROLE_HR_COMPLIANCE: "HR / Compliance",
    ROLE_SUPERVISOR: "On-Site Supervisor",
    ROLE_RECEPTIONIST: "Receptionist / Concierge",
    ROLE_GUARD: "Security Guard",
    ROLE_CLEANER: "Cleaner / Facilities",
}

ALL_ROLES = list(ROLE_LABELS.keys())

# Roles with access to corporate financial data (invoices, billing margins).
FINANCE_ROLES = {ROLE_OWNER, ROLE_OPS_MANAGER}

# Roles with read/write access to the Guard Profile Vault (SIA/vetting data).
HR_ROLES = {ROLE_OWNER, ROLE_OPS_MANAGER, ROLE_HR_COMPLIANCE}

# Roles with access to the "Your Sites" roster hub.
SITE_MANAGEMENT_ROLES = {ROLE_OWNER, ROLE_OPS_MANAGER, ROLE_SUPERVISOR}

# Roles with access to the payroll management interface.
PAYROLL_ROLES = {ROLE_OWNER, ROLE_HR_COMPLIANCE}

# Roles who land on the mobile frontline portal rather than the back-office UI.
FRONTLINE_ROLES = {ROLE_RECEPTIONIST, ROLE_GUARD, ROLE_CLEANER, ROLE_SUPERVISOR}

# Roles required to complete an MFA challenge at login (GDPR hardening for
# accounts with organisation-wide financial visibility).
# Temporarily disabled for testing - re-add ROLE_OWNER to re-enable MFA.
MFA_REQUIRED_ROLES = set()

# Inactivity timeout (GDPR safeguard for unattended office/control-room screens).
SESSION_TIMEOUT_MINUTES = 15

# Master Roster staff categories - drive the color-coded roster grid.
STAFF_CATEGORY_GUARD = "guard"
STAFF_CATEGORY_SUPERVISOR = "supervisor"
STAFF_CATEGORY_CLEANER = "cleaner"
STAFF_CATEGORY_RECEPTIONIST = "receptionist"

STAFF_CATEGORY_LABELS = {
    STAFF_CATEGORY_GUARD: "Guard",
    STAFF_CATEGORY_SUPERVISOR: "Supervisor",
    STAFF_CATEGORY_CLEANER: "Cleaner",
    STAFF_CATEGORY_RECEPTIONIST: "Receptionist",
}

# CSS colour key for each category - see badge--cat-* in styles.css.
STAFF_CATEGORY_COLORS = {
    STAFF_CATEGORY_GUARD: "blue",
    STAFF_CATEGORY_SUPERVISOR: "purple",
    STAFF_CATEGORY_CLEANER: "green",
    STAFF_CATEGORY_RECEPTIONIST: "yellow",
}

ROLE_TO_STAFF_CATEGORY = {
    ROLE_GUARD: STAFF_CATEGORY_GUARD,
    ROLE_SUPERVISOR: STAFF_CATEGORY_SUPERVISOR,
    ROLE_CLEANER: STAFF_CATEGORY_CLEANER,
    ROLE_RECEPTIONIST: STAFF_CATEGORY_RECEPTIONIST,
}

SIA_LICENSE_TYPES = [
    "Door Supervisor",
    "Security Guarding",
    "CCTV (Public Space Surveillance)",
    "Close Protection",
    "Cash and Valuables in Transit",
    "Vehicle Immobilisation",
]

# Days before SIA expiry at which a guard is flagged as "expiring soon".
SIA_EXPIRY_WARNING_DAYS = 30

# Common annual holidays that trigger holiday premium pay.
DESIGNATED_HOLIDAYS = {
    (1, 1),
    (12, 25),
    (12, 26),
}


class Guard(db.Model):
    __tablename__ = "guards"

    id = db.Column(db.Integer, primary_key=True)
    employee_number = db.Column(db.String(40), unique=True)
    first_name = db.Column(db.String(80), nullable=False)
    last_name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120))
    phone = db.Column(db.String(30))
    sia_license_number = db.Column(db.String(40), nullable=False, unique=True)
    sia_license_type = db.Column(db.String(60), nullable=False)
    sia_expiry_date = db.Column(db.Date, nullable=False)
    dbs_expiry_date = db.Column(db.Date)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    pay_rate = db.Column(db.Numeric(8, 2), default=12.00, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Compliant Guard Vault: payroll and emergency-contact details.
    bank_account_number = db.Column(db.String(20))
    bank_sort_code = db.Column(db.String(10))
    next_of_kin_name = db.Column(db.String(120))
    next_of_kin_relationship = db.Column(db.String(80))
    next_of_kin_contact = db.Column(db.String(30))

    # Uploaded document filenames (stored under static/uploads/guards/).
    profile_picture_filename = db.Column(db.String(255))
    sia_card_scan_filename = db.Column(db.String(255))

    shifts = db.relationship("Shift", back_populates="guard")

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def sia_days_remaining(self):
        return (self.sia_expiry_date - date.today()).days

    @property
    def sia_status(self):
        days = self.sia_days_remaining
        if days < 0:
            return "expired"
        if days <= SIA_EXPIRY_WARNING_DAYS:
            return "warning"
        return "valid"


class Site(db.Model):
    __tablename__ = "sites"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    client_name = db.Column(db.String(120), nullable=False)
    address = db.Column(db.String(255))
    site_manager = db.Column(db.String(120))
    pay_rate_default = db.Column(db.Numeric(8, 2), default=0)
    bill_rate_default = db.Column(db.Numeric(8, 2), default=0)
    billing_rate = db.Column(db.Numeric(8, 2), default=18.00, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    shifts = db.relationship("Shift", back_populates="site")
    invoices = db.relationship("Invoice", back_populates="site")

    @property
    def uninvoiced_shifts(self):
        return [
            s
            for s in self.shifts
            if s.guard_id is not None
            and s.status == "completed"
            and s.invoice_id is None
            and s.approved_by_manager
        ]


class AuditLog(db.Model):
    __tablename__ = "audit_logs"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(120), nullable=False)
    details = db.Column(db.Text)
    timestamp = db.Column(db.DateTime, nullable=False, default=lambda: datetime.now(UTC))

    user = db.relationship("User")

    def __repr__(self):
        return f"<AuditLog {self.id} {self.action}>"


class Shift(db.Model):
    __tablename__ = "shifts"

    id = db.Column(db.Integer, primary_key=True)
    site_id = db.Column(db.Integer, db.ForeignKey("sites.id"), nullable=False)
    guard_id = db.Column(db.Integer, db.ForeignKey("guards.id"), nullable=True)
    # Master Roster: non-guard staff (supervisors/cleaners/receptionists) are
    # scheduled via a linked User instead of a Guard profile.
    assigned_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    staff_category = db.Column(db.String(20), default=STAFF_CATEGORY_GUARD, nullable=False)
    shift_date = db.Column(db.Date, nullable=False)
    start_time = db.Column(db.Time, nullable=False)
    end_time = db.Column(db.Time, nullable=False)
    role = db.Column(db.String(80))
    pay_rate = db.Column(db.Numeric(8, 2), default=0, nullable=False)
    bill_rate = db.Column(db.Numeric(8, 2), default=0, nullable=False)
    # scheduled -> completed -> invoiced
    status = db.Column(db.String(20), default="scheduled", nullable=False)
    invoice_id = db.Column(db.Integer, db.ForeignKey("invoices.id"), nullable=True)
    notes = db.Column(db.String(255))

    # Frontline clock-in/out timestamps for this roster slot, if recorded.
    clock_in = db.Column(db.DateTime, nullable=True)
    clock_out = db.Column(db.DateTime, nullable=True)
    total_hours = db.Column(db.Numeric(6, 2), nullable=True)

    # Set by a site manager/supervisor once they've verified the shift was
    # worked as scheduled - gates both invoicing and payroll payout.
    approved_by_manager = db.Column(db.Boolean, default=False, nullable=False)
    paid_out = db.Column(db.Boolean, default=False, nullable=False)

    site = db.relationship("Site", back_populates="shifts")
    guard = db.relationship("Guard", back_populates="shifts")
    invoice = db.relationship("Invoice", back_populates="shifts")
    assigned_user = db.relationship("User", foreign_keys=[assigned_user_id])

    @property
    def hours(self):
        if self.total_hours is not None:
            return float(self.total_hours)
        start = datetime.combine(self.shift_date, self.start_time)
        end = datetime.combine(self.shift_date, self.end_time)
        if end <= start:
            end += timedelta(days=1)  # overnight shift
        return round((end - start).total_seconds() / 3600, 2)

    def has_conflict_with(self, other):
        if self.shift_date != other.shift_date:
            return False
        if self.guard_id is None or other.guard_id is None:
            return False
        if self.guard_id != other.guard_id:
            return False
        start_a = datetime.combine(self.shift_date, self.start_time)
        end_a = datetime.combine(self.shift_date, self.end_time)
        start_b = datetime.combine(other.shift_date, other.start_time)
        end_b = datetime.combine(other.shift_date, other.end_time)
        if end_a <= start_a:
            end_a += timedelta(days=1)
        if end_b <= start_b:
            end_b += timedelta(days=1)
        return start_a < end_b and start_b < end_a

    @property
    def pay_amount(self):
        return round(float(self.pay_rate) * self.hours, 2)

    @property
    def is_designated_holiday(self):
        return (self.shift_date.month, self.shift_date.day) in DESIGNATED_HOLIDAYS

    @property
    def bill_amount(self):
        return round(float(self.bill_rate) * self.hours, 2)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(30), nullable=False)
    language = db.Column(db.String(10), default="en", nullable=False)
    is_active_account = db.Column(db.Boolean, default=True, nullable=False)

    # MFA (TOTP) - required for owners/directors per GDPR hardening policy.
    mfa_secret = db.Column(db.String(32))
    mfa_enabled = db.Column(db.Boolean, default=False, nullable=False)

    # Linked guard profile, if this account belongs to a frontline guard.
    guard_id = db.Column(db.Integer, db.ForeignKey("guards.id"), nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_login_at = db.Column(db.DateTime)

    guard = db.relationship("Guard")

    def set_password(self, raw_password):
        self.password_hash = generate_password_hash(raw_password)

    def check_password(self, raw_password):
        return check_password_hash(self.password_hash, raw_password)

    @property
    def role_label(self):
        return ROLE_LABELS.get(self.role, self.role)

    @property
    def is_frontline(self):
        return self.role in FRONTLINE_ROLES

    @property
    def requires_mfa(self):
        return self.role in MFA_REQUIRED_ROLES

    def get_id(self):
        # Required by Flask-Login - must return a unicode string.
        return str(self.id)


class AttendanceRecord(db.Model):
    """Frontline clock-in / clock-out log."""

    __tablename__ = "attendance_records"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    site_id = db.Column(db.Integer, db.ForeignKey("sites.id"), nullable=True)
    clock_in = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    clock_out = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User")
    site = db.relationship("Site")

    @property
    def is_open(self):
        return self.clock_out is None


class VisitorLogEntry(db.Model):
    """Receptionist suite: visitor sign-in / sign-out register."""

    __tablename__ = "visitor_log_entries"

    id = db.Column(db.Integer, primary_key=True)
    site_id = db.Column(db.Integer, db.ForeignKey("sites.id"), nullable=False)
    visitor_name = db.Column(db.String(120), nullable=False)
    host_name = db.Column(db.String(120))
    company = db.Column(db.String(120))
    purpose = db.Column(db.String(255))
    signed_in_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    signed_out_at = db.Column(db.DateTime, nullable=True)
    recorded_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    site = db.relationship("Site")
    recorded_by = db.relationship("User")


class KeyRegisterEntry(db.Model):
    """Receptionist suite: building key issue/return register."""

    __tablename__ = "key_register_entries"

    id = db.Column(db.Integer, primary_key=True)
    site_id = db.Column(db.Integer, db.ForeignKey("sites.id"), nullable=False)
    key_label = db.Column(db.String(120), nullable=False)
    issued_to = db.Column(db.String(120), nullable=False)
    issued_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    returned_at = db.Column(db.DateTime, nullable=True)
    issued_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    site = db.relationship("Site")
    issued_by = db.relationship("User")


class ParcelLogEntry(db.Model):
    """Receptionist suite: parcel delivery tracker."""

    __tablename__ = "parcel_log_entries"

    id = db.Column(db.Integer, primary_key=True)
    site_id = db.Column(db.Integer, db.ForeignKey("sites.id"), nullable=False)
    courier = db.Column(db.String(120))
    recipient = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(255))
    received_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    collected_at = db.Column(db.DateTime, nullable=True)
    recorded_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)

    site = db.relationship("Site")
    recorded_by = db.relationship("User")


INCIDENT_URGENCY_LEVELS = ["low", "medium", "high", "critical"]


class IncidentReport(db.Model):
    """Security suite: digital incident reporting form."""

    __tablename__ = "incident_reports"

    id = db.Column(db.Integer, primary_key=True)
    site_id = db.Column(db.Integer, db.ForeignKey("sites.id"), nullable=False)
    reported_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    category = db.Column(db.String(80), nullable=False)
    urgency = db.Column(db.String(20), default="low", nullable=False)
    description = db.Column(db.Text, nullable=False)
    occurred_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    status = db.Column(db.String(20), default="open", nullable=False)

    site = db.relationship("Site")
    reported_by = db.relationship("User")


class MaintenanceChecklistEntry(db.Model):
    """Facilities/cleaning suite: property maintenance & patrol checklist."""

    __tablename__ = "maintenance_checklist_entries"

    id = db.Column(db.Integer, primary_key=True)
    site_id = db.Column(db.Integer, db.ForeignKey("sites.id"), nullable=False)
    completed_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    task_name = db.Column(db.String(120), nullable=False)
    area = db.Column(db.String(120))
    notes = db.Column(db.String(255))
    completed_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    site = db.relationship("Site")
    completed_by = db.relationship("User")


class Invoice(db.Model):
    __tablename__ = "invoices"

    id = db.Column(db.Integer, primary_key=True)
    invoice_number = db.Column(db.String(30), unique=True, nullable=False)
    site_id = db.Column(db.Integer, db.ForeignKey("sites.id"), nullable=False)
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    issue_date = db.Column(db.Date, default=date.today, nullable=False)
    # draft -> sent -> paid
    status = db.Column(db.String(20), default="draft", nullable=False)
    total_amount = db.Column(db.Numeric(10, 2), default=0)

    site = db.relationship("Site", back_populates="invoices")
    shifts = db.relationship("Shift", back_populates="invoice")

    @property
    def total_hours(self):
        return round(sum(s.hours for s in self.shifts), 2)


class PayrollPayout(db.Model):
    """A record of an approved payroll payout for a guard's worked hours."""

    __tablename__ = "payroll_payouts"

    id = db.Column(db.Integer, primary_key=True)
    guard_id = db.Column(db.Integer, db.ForeignKey("guards.id"), nullable=False)
    period_start = db.Column(db.Date, nullable=False)
    period_end = db.Column(db.Date, nullable=False)
    total_hours = db.Column(db.Numeric(8, 2), nullable=False)
    total_pay = db.Column(db.Numeric(10, 2), nullable=False)
    approved_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    approved_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    guard = db.relationship("Guard")
    approved_by = db.relationship("User")
