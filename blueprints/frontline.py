from datetime import datetime, UTC

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from decorators import role_required
from extensions import db
from models import (
    INCIDENT_URGENCY_LEVELS,
    ROLE_CLEANER,
    ROLE_GUARD,
    ROLE_RECEPTIONIST,
    ROLE_SUPERVISOR,
    AttendanceRecord,
    IncidentReport,
    KeyRegisterEntry,
    MaintenanceChecklistEntry,
    ParcelLogEntry,
    Site,
    VisitorLogEntry,
)

frontline_bp = Blueprint("frontline", __name__, url_prefix="/frontline")

# Roles permitted to use the receptionist desk modules.
RECEPTION_ROLES = {ROLE_RECEPTIONIST}
# Roles permitted to file/view incident reports from the field.
SECURITY_ROLES = {ROLE_GUARD, ROLE_SUPERVISOR}
# Roles permitted to log maintenance/patrol checklist entries.
FACILITIES_ROLES = {ROLE_CLEANER}


def _current_site():
    site_id = request.args.get("site_id", type=int) or request.form.get("site_id", type=int)
    if site_id:
        site = db.session.get(Site, site_id)
        if site:
            return site
    return Site.query.filter_by(is_active=True).order_by(Site.name).first()


@frontline_bp.route("/portal")
@login_required
@role_required(ROLE_RECEPTIONIST, ROLE_GUARD, ROLE_CLEANER, ROLE_SUPERVISOR)
def portal():
    sites = Site.query.filter_by(is_active=True).order_by(Site.name).all()
    site = _current_site()

    open_attendance = AttendanceRecord.query.filter_by(
        user_id=current_user.id, clock_out=None
    ).first()

    context = {
        "sites": sites,
        "site": site,
        "open_attendance": open_attendance,
        "urgency_levels": INCIDENT_URGENCY_LEVELS,
    }

    if site and current_user.role in RECEPTION_ROLES:
        context["visitors"] = (
            VisitorLogEntry.query.filter_by(site_id=site.id)
            .order_by(VisitorLogEntry.signed_in_at.desc())
            .limit(15)
            .all()
        )
        context["keys"] = (
            KeyRegisterEntry.query.filter_by(site_id=site.id)
            .order_by(KeyRegisterEntry.issued_at.desc())
            .limit(15)
            .all()
        )
        context["parcels"] = (
            ParcelLogEntry.query.filter_by(site_id=site.id)
            .order_by(ParcelLogEntry.received_at.desc())
            .limit(15)
            .all()
        )

    if site and current_user.role in SECURITY_ROLES:
        context["incidents"] = (
            IncidentReport.query.filter_by(site_id=site.id)
            .order_by(IncidentReport.occurred_at.desc())
            .limit(10)
            .all()
        )

    if site and current_user.role in FACILITIES_ROLES:
        context["checklist_entries"] = (
            MaintenanceChecklistEntry.query.filter_by(site_id=site.id)
            .order_by(MaintenanceChecklistEntry.completed_at.desc())
            .limit(10)
            .all()
        )

    return render_template("frontline/portal.html", **context)


# ---------------------------------------------------------------------------
# Global attendance (all frontline roles)
# ---------------------------------------------------------------------------
@frontline_bp.route("/attendance/clock-in", methods=["POST"])
@login_required
@role_required(ROLE_RECEPTIONIST, ROLE_GUARD, ROLE_CLEANER, ROLE_SUPERVISOR)
def clock_in():
    site = _current_site()
    record = AttendanceRecord(user_id=current_user.id, site_id=site.id if site else None)
    db.session.add(record)
    db.session.commit()
    flash("Clocked in.", "success")
    return redirect(url_for("frontline.portal", site_id=site.id if site else None))


@frontline_bp.route("/attendance/clock-out", methods=["POST"])
@login_required
@role_required(ROLE_RECEPTIONIST, ROLE_GUARD, ROLE_CLEANER, ROLE_SUPERVISOR)
def clock_out():
    record = AttendanceRecord.query.filter_by(user_id=current_user.id, clock_out=None).first()
    if record:
        record.clock_out = datetime.now(UTC)
        db.session.commit()
        flash("Clocked out.", "success")
    return redirect(url_for("frontline.portal", site_id=request.form.get("site_id", type=int)))


# ---------------------------------------------------------------------------
# Receptionist suite
# ---------------------------------------------------------------------------
@frontline_bp.route("/visitors/sign-in", methods=["POST"])
@login_required
@role_required(*RECEPTION_ROLES)
def visitor_sign_in():
    site = _current_site()
    entry = VisitorLogEntry(
        site_id=site.id,
        visitor_name=request.form.get("visitor_name", "").strip(),
        host_name=request.form.get("host_name", "").strip(),
        company=request.form.get("company", "").strip(),
        purpose=request.form.get("purpose", "").strip(),
        recorded_by_id=current_user.id,
    )
    db.session.add(entry)
    db.session.commit()
    flash("Visitor signed in.", "success")
    return redirect(url_for("frontline.portal", site_id=site.id))


@frontline_bp.route("/visitors/<int:entry_id>/sign-out", methods=["POST"])
@login_required
@role_required(*RECEPTION_ROLES)
def visitor_sign_out(entry_id):
    entry = VisitorLogEntry.query.get_or_404(entry_id)
    entry.signed_out_at = datetime.now(UTC)
    db.session.commit()
    flash("Visitor signed out.", "success")
    return redirect(url_for("frontline.portal", site_id=entry.site_id))


@frontline_bp.route("/keys/issue", methods=["POST"])
@login_required
@role_required(*RECEPTION_ROLES)
def key_issue():
    site = _current_site()
    entry = KeyRegisterEntry(
        site_id=site.id,
        key_label=request.form.get("key_label", "").strip(),
        issued_to=request.form.get("issued_to", "").strip(),
        issued_by_id=current_user.id,
    )
    db.session.add(entry)
    db.session.commit()
    flash("Key issued.", "success")
    return redirect(url_for("frontline.portal", site_id=site.id))


@frontline_bp.route("/keys/<int:entry_id>/return", methods=["POST"])
@login_required
@role_required(*RECEPTION_ROLES)
def key_return(entry_id):
    entry = KeyRegisterEntry.query.get_or_404(entry_id)
    entry.returned_at = datetime.now(UTC)
    db.session.commit()
    flash("Key marked as returned.", "success")
    return redirect(url_for("frontline.portal", site_id=entry.site_id))


@frontline_bp.route("/parcels/log", methods=["POST"])
@login_required
@role_required(*RECEPTION_ROLES)
def parcel_log():
    site = _current_site()
    entry = ParcelLogEntry(
        site_id=site.id,
        courier=request.form.get("courier", "").strip(),
        recipient=request.form.get("recipient", "").strip(),
        description=request.form.get("description", "").strip(),
        recorded_by_id=current_user.id,
    )
    db.session.add(entry)
    db.session.commit()
    flash("Parcel logged.", "success")
    return redirect(url_for("frontline.portal", site_id=site.id))


@frontline_bp.route("/parcels/<int:entry_id>/collect", methods=["POST"])
@login_required
@role_required(*RECEPTION_ROLES)
def parcel_collect(entry_id):
    entry = ParcelLogEntry.query.get_or_404(entry_id)
    entry.collected_at = datetime.now(UTC)
    db.session.commit()
    flash("Parcel marked as collected.", "success")
    return redirect(url_for("frontline.portal", site_id=entry.site_id))


# ---------------------------------------------------------------------------
# Security suite
# ---------------------------------------------------------------------------
@frontline_bp.route("/incidents/report", methods=["POST"])
@login_required
@role_required(*SECURITY_ROLES)
def incident_report():
    site = _current_site()
    entry = IncidentReport(
        site_id=site.id,
        reported_by_id=current_user.id,
        category=request.form.get("category", "").strip(),
        urgency=request.form.get("urgency", "low"),
        description=request.form.get("description", "").strip(),
    )
    db.session.add(entry)
    db.session.commit()
    flash("Incident report submitted.", "success")
    return redirect(url_for("frontline.portal", site_id=site.id))


# ---------------------------------------------------------------------------
# Facilities / cleaning suite
# ---------------------------------------------------------------------------
@frontline_bp.route("/maintenance/log", methods=["POST"])
@login_required
@role_required(*FACILITIES_ROLES)
def maintenance_log():
    site = _current_site()
    entry = MaintenanceChecklistEntry(
        site_id=site.id,
        completed_by_id=current_user.id,
        task_name=request.form.get("task_name", "").strip(),
        area=request.form.get("area", "").strip(),
        notes=request.form.get("notes", "").strip(),
    )
    db.session.add(entry)
    db.session.commit()
    flash("Checklist entry logged.", "success")
    return redirect(url_for("frontline.portal", site_id=site.id))
