from datetime import datetime

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models import SITE_MANAGEMENT_ROLES, Guard, Shift, Site

sites_bp = Blueprint("sites", __name__, url_prefix="/sites")


@sites_bp.before_request
@login_required
def _restrict_to_site_management_roles():
    """Your Sites hub: Owners, Ops Managers, and Supervisors only."""
    if current_user.role not in SITE_MANAGEMENT_ROLES:
        abort(403)


def _parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date() if value else None


def _parse_time(value):
    return datetime.strptime(value, "%H:%M").time() if value else None


@sites_bp.route("/")
def list_sites():
    sites = Site.query.order_by(Site.name.asc()).all()
    return render_template("sites/list.html", sites=sites)


@sites_bp.route("/new", methods=["GET", "POST"])
def new_site():
    if request.method == "POST":
        errors = []
        if not request.form.get("name", "").strip():
            errors.append("Site name is required.")
        if not request.form.get("client_name", "").strip():
            errors.append("Client name is required.")

        if errors:
            for message in errors:
                flash(message, "error")
            return render_template("sites/form.html", site=None, form_data=request.form)

        site = Site(
            name=request.form["name"].strip(),
            client_name=request.form["client_name"].strip(),
            address=request.form.get("address", "").strip(),
            site_manager=request.form.get("site_manager", "").strip(),
            pay_rate_default=request.form.get("pay_rate_default") or 0,
            bill_rate_default=request.form.get("bill_rate_default") or 0,
        )
        db.session.add(site)
        db.session.commit()
        flash(f"{site.name} added to Your Sites.", "success")
        return redirect(url_for("sites.detail", site_id=site.id))

    return render_template("sites/form.html", site=None, form_data={})


@sites_bp.route("/<int:site_id>")
def detail(site_id):
    site = Site.query.get_or_404(site_id)
    guards = Guard.query.filter_by(is_active=True).order_by(Guard.first_name.asc()).all()
    roster = sorted(site.shifts, key=lambda s: (s.shift_date, s.start_time), reverse=True)
    return render_template("sites/detail.html", site=site, guards=guards, roster=roster, today=datetime.utcnow().date())


@sites_bp.route("/<int:site_id>/edit", methods=["GET", "POST"])
def edit_site(site_id):
    site = Site.query.get_or_404(site_id)

    if request.method == "POST":
        errors = []
        if not request.form.get("name", "").strip():
            errors.append("Site name is required.")
        if not request.form.get("client_name", "").strip():
            errors.append("Client name is required.")

        if errors:
            for message in errors:
                flash(message, "error")
            return render_template("sites/form.html", site=site, form_data=request.form)

        site.name = request.form["name"].strip()
        site.client_name = request.form["client_name"].strip()
        site.address = request.form.get("address", "").strip()
        site.site_manager = request.form.get("site_manager", "").strip()
        site.pay_rate_default = request.form.get("pay_rate_default") or 0
        site.bill_rate_default = request.form.get("bill_rate_default") or 0
        site.is_active = request.form.get("is_active") == "on"
        db.session.commit()
        flash(f"{site.name} has been updated.", "success")
        return redirect(url_for("sites.detail", site_id=site.id))

    return render_template("sites/form.html", site=site, form_data={})


@sites_bp.route("/<int:site_id>/roster", methods=["POST"])
def assign_roster(site_id):
    site = Site.query.get_or_404(site_id)

    errors = []
    required = ["guard_id", "shift_date", "start_time", "end_time"]
    for field in required:
        if not request.form.get(field, "").strip():
            errors.append("Please complete all required roster fields.")
            break

    if errors:
        for message in errors:
            flash(message, "error")
        return redirect(url_for("sites.detail", site_id=site.id))

    shift = Shift(
        site_id=site.id,
        guard_id=int(request.form["guard_id"]),
        shift_date=_parse_date(request.form["shift_date"]),
        start_time=_parse_time(request.form["start_time"]),
        end_time=_parse_time(request.form["end_time"]),
        role=request.form.get("role", "").strip(),
        pay_rate=request.form.get("pay_rate") or site.pay_rate_default or 0,
        bill_rate=request.form.get("bill_rate") or site.bill_rate_default or 0,
        notes=request.form.get("notes", "").strip(),
    )
    db.session.add(shift)
    db.session.commit()
    flash(f"{shift.guard.full_name} assigned to {site.name} on {shift.shift_date:%d %b %Y}.", "success")
    return redirect(url_for("sites.detail", site_id=site.id))


@sites_bp.route("/<int:site_id>/roster/<int:shift_id>/complete", methods=["POST"])
def complete_shift(site_id, shift_id):
    shift = Shift.query.filter_by(id=shift_id, site_id=site_id).first_or_404()
    shift.status = "completed"
    db.session.commit()
    flash("Shift marked as completed and queued for invoicing.", "success")
    return redirect(url_for("sites.detail", site_id=site_id))


@sites_bp.route("/<int:site_id>/roster/<int:shift_id>/approve", methods=["POST"])
def approve_shift(site_id, shift_id):
    shift = Shift.query.filter_by(id=shift_id, site_id=site_id).first_or_404()
    if shift.status != "completed":
        flash("Only completed shifts can be approved.", "error")
        return redirect(url_for("sites.detail", site_id=site_id))

    shift.approved_by_manager = True
    db.session.commit()
    flash("Shift approved for invoicing and payroll.", "success")
    return redirect(url_for("sites.detail", site_id=site_id))


@sites_bp.route("/<int:site_id>/roster/<int:shift_id>/delete", methods=["POST"])
def delete_shift(site_id, shift_id):
    shift = Shift.query.filter_by(id=shift_id, site_id=site_id).first_or_404()
    if shift.status == "invoiced":
        flash("Invoiced shifts cannot be removed from the roster.", "error")
        return redirect(url_for("sites.detail", site_id=site_id))

    db.session.delete(shift)
    db.session.commit()
    flash("Roster entry removed.", "success")
    return redirect(url_for("sites.detail", site_id=site_id))
