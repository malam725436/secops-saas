import os
from datetime import datetime

from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from werkzeug.utils import secure_filename

from extensions import db
from models import HR_ROLES, SIA_LICENSE_TYPES, Guard

guards_bp = Blueprint("guards", __name__, url_prefix="/guards")

ALLOWED_UPLOAD_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "pdf"}


@guards_bp.before_request
@login_required
def _restrict_to_hr_roles():
    """Guard Profile Vault: HR/Compliance, Ops Managers, and Owners only.

    GDPR data isolation - frontline staff (guards, cleaners, receptionists)
    must never be able to query other employees' vetting/compliance files.
    """
    if current_user.role not in HR_ROLES:
        abort(403)


def _parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date() if value else None


def _save_upload(file_storage, guard_id, field_label):
    """Save an uploaded guard document, returning its stored filename or None."""
    if not file_storage or not file_storage.filename:
        return None

    extension = file_storage.filename.rsplit(".", 1)[-1].lower() if "." in file_storage.filename else ""
    if extension not in ALLOWED_UPLOAD_EXTENSIONS:
        flash(f"{field_label}: unsupported file type. Allowed: PNG, JPG, GIF, PDF.", "error")
        return None

    filename = secure_filename(f"guard-{guard_id}-{field_label}.{extension}")
    file_storage.save(os.path.join(current_app.config["UPLOAD_FOLDER"], filename))
    return filename


@guards_bp.route("/")
def list_guards():
    status_filter = request.args.get("status", "all")
    guards = Guard.query.order_by(Guard.sia_expiry_date.asc()).all()

    if status_filter in ("valid", "warning", "expired"):
        guards = [g for g in guards if g.sia_status == status_filter]

    summary = {
        "total": Guard.query.count(),
        "expiring": sum(1 for g in Guard.query.all() if g.sia_status == "warning"),
        "expired": sum(1 for g in Guard.query.all() if g.sia_status == "expired"),
    }

    return render_template(
        "guards/list.html",
        guards=guards,
        status_filter=status_filter,
        summary=summary,
    )


@guards_bp.route("/new", methods=["GET", "POST"])
def new_guard():
    if request.method == "POST":
        errors = _validate(request.form)
        if errors:
            for message in errors:
                flash(message, "error")
            return render_template(
                "guards/form.html",
                guard=None,
                license_types=SIA_LICENSE_TYPES,
                form_data=request.form,
            )

        guard = Guard(
            employee_number=request.form.get("employee_number", "").strip() or None,
            first_name=request.form["first_name"].strip(),
            last_name=request.form["last_name"].strip(),
            email=request.form.get("email", "").strip(),
            phone=request.form.get("phone", "").strip(),
            sia_license_number=request.form["sia_license_number"].strip(),
            sia_license_type=request.form["sia_license_type"],
            sia_expiry_date=_parse_date(request.form["sia_expiry_date"]),
            dbs_expiry_date=_parse_date(request.form.get("dbs_expiry_date")),
            bank_account_number=request.form.get("bank_account_number", "").strip(),
            bank_sort_code=request.form.get("bank_sort_code", "").strip(),
            next_of_kin_name=request.form.get("next_of_kin_name", "").strip(),
            next_of_kin_relationship=request.form.get("next_of_kin_relationship", "").strip(),
            next_of_kin_contact=request.form.get("next_of_kin_contact", "").strip(),
        )
        db.session.add(guard)
        db.session.commit()

        profile_picture = _save_upload(request.files.get("profile_picture"), guard.id, "profile-picture")
        if profile_picture:
            guard.profile_picture_filename = profile_picture
        sia_card_scan = _save_upload(request.files.get("sia_card_scan"), guard.id, "sia-card-scan")
        if sia_card_scan:
            guard.sia_card_scan_filename = sia_card_scan
        if profile_picture or sia_card_scan:
            db.session.commit()

        flash(f"{guard.full_name} added to the Guard Profile Vault.", "success")
        return redirect(url_for("guards.detail", guard_id=guard.id))

    return render_template(
        "guards/form.html", guard=None, license_types=SIA_LICENSE_TYPES, form_data={}
    )


@guards_bp.route("/<int:guard_id>")
def detail(guard_id):
    guard = Guard.query.get_or_404(guard_id)
    return render_template("guards/detail.html", guard=guard)


@guards_bp.route("/<int:guard_id>/edit", methods=["GET", "POST"])
def edit_guard(guard_id):
    guard = Guard.query.get_or_404(guard_id)

    if request.method == "POST":
        errors = _validate(request.form, editing_id=guard.id)
        if errors:
            for message in errors:
                flash(message, "error")
            return render_template(
                "guards/form.html",
                guard=guard,
                license_types=SIA_LICENSE_TYPES,
                form_data=request.form,
            )

        guard.employee_number = request.form.get("employee_number", "").strip() or None
        guard.first_name = request.form["first_name"].strip()
        guard.last_name = request.form["last_name"].strip()
        guard.email = request.form.get("email", "").strip()
        guard.phone = request.form.get("phone", "").strip()
        guard.sia_license_number = request.form["sia_license_number"].strip()
        guard.sia_license_type = request.form["sia_license_type"]
        guard.sia_expiry_date = _parse_date(request.form["sia_expiry_date"])
        guard.dbs_expiry_date = _parse_date(request.form.get("dbs_expiry_date"))
        guard.is_active = request.form.get("is_active") == "on"
        guard.bank_account_number = request.form.get("bank_account_number", "").strip()
        guard.bank_sort_code = request.form.get("bank_sort_code", "").strip()
        guard.next_of_kin_name = request.form.get("next_of_kin_name", "").strip()
        guard.next_of_kin_relationship = request.form.get("next_of_kin_relationship", "").strip()
        guard.next_of_kin_contact = request.form.get("next_of_kin_contact", "").strip()

        profile_picture = _save_upload(request.files.get("profile_picture"), guard.id, "profile-picture")
        if profile_picture:
            guard.profile_picture_filename = profile_picture
        sia_card_scan = _save_upload(request.files.get("sia_card_scan"), guard.id, "sia-card-scan")
        if sia_card_scan:
            guard.sia_card_scan_filename = sia_card_scan

        db.session.commit()
        flash(f"{guard.full_name}'s profile has been updated.", "success")
        return redirect(url_for("guards.detail", guard_id=guard.id))

    return render_template(
        "guards/form.html", guard=guard, license_types=SIA_LICENSE_TYPES, form_data={}
    )


def _validate(form, editing_id=None):
    errors = []
    required = {
        "first_name": "First name",
        "last_name": "Last name",
        "sia_license_number": "SIA licence number",
        "sia_license_type": "SIA licence type",
        "sia_expiry_date": "SIA expiry date",
    }
    for field, label in required.items():
        if not form.get(field, "").strip():
            errors.append(f"{label} is required.")

    license_number = form.get("sia_license_number", "").strip()
    if license_number:
        existing = Guard.query.filter_by(sia_license_number=license_number).first()
        if existing and existing.id != editing_id:
            errors.append("That SIA licence number is already registered to another guard.")

    employee_number = form.get("employee_number", "").strip()
    if employee_number:
        existing = Guard.query.filter_by(employee_number=employee_number).first()
        if existing and existing.id != editing_id:
            errors.append("That employee number is already assigned to another guard.")

    expiry = form.get("sia_expiry_date", "").strip()
    if expiry:
        try:
            _parse_date(expiry)
        except ValueError:
            errors.append("SIA expiry date must be a valid date.")

    return errors
