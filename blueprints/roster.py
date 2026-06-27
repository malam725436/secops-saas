from datetime import datetime, timedelta, UTC

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import login_required, current_user

from extensions import db
from models import (
    ROLE_CLEANER,
    ROLE_RECEPTIONIST,
    ROLE_SUPERVISOR,
    ROLE_TO_STAFF_CATEGORY,
    SITE_MANAGEMENT_ROLES,
    STAFF_CATEGORY_COLORS,
    STAFF_CATEGORY_GUARD,
    STAFF_CATEGORY_LABELS,
    Guard,
    Shift,
    Site,
    User,
)

roster_bp = Blueprint("roster", __name__, url_prefix="/roster")

NON_GUARD_ROSTER_ROLES = (ROLE_SUPERVISOR, ROLE_CLEANER, ROLE_RECEPTIONIST)


@roster_bp.before_request
@login_required
def _restrict_to_site_management_roles():
    """Master Roster: Owners, Ops Managers, and Supervisors only."""
    if current_user.role not in SITE_MANAGEMENT_ROLES:
        abort(403)


def _parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date() if value else None


def _parse_time(value):
    return datetime.strptime(value, "%H:%M").time() if value else None


def _week_start(value):
    parsed = _parse_date(value)
    today = datetime.now(UTC).date()
    base = parsed or today
    return base - timedelta(days=base.weekday())


def _staff_roster():
    """All staff eligible for the Master Roster grid, tagged by category."""
    staff = []
    for guard in Guard.query.filter_by(is_active=True).order_by(Guard.first_name.asc()).all():
        staff.append({"type": "guard", "id": guard.id, "name": guard.full_name, "category": STAFF_CATEGORY_GUARD})

    users = (
        User.query.filter(User.role.in_(NON_GUARD_ROSTER_ROLES), User.is_active_account.is_(True))
        .order_by(User.name.asc())
        .all()
    )
    for user in users:
        staff.append({"type": "user", "id": user.id, "name": user.name, "category": ROLE_TO_STAFF_CATEGORY[user.role]})

    return staff


@roster_bp.route("/")
def master():
    week_start = _week_start(request.args.get("week_start", ""))
    week_end = week_start + timedelta(days=6)
    days = [week_start + timedelta(days=i) for i in range(7)]

    shifts = (
        Shift.query.filter(Shift.shift_date >= week_start, Shift.shift_date <= week_end)
        .order_by(Shift.start_time.asc())
        .all()
    )

    staff = _staff_roster()

    grid = []
    for member in staff:
        row_cells = []
        for day in days:
            cell_shifts = [
                shift
                for shift in shifts
                if shift.shift_date == day
                and (
                    (member["type"] == "guard" and shift.guard_id == member["id"])
                    or (member["type"] == "user" and shift.assigned_user_id == member["id"])
                )
            ]
            row_cells.append(cell_shifts)
        grid.append({"member": member, "cells": row_cells})

    sites = Site.query.filter_by(is_active=True).order_by(Site.name.asc()).all()

    return render_template(
        "roster/master.html",
        week_start=week_start,
        week_end=week_end,
        days=days,
        grid=grid,
        sites=sites,
        staff=staff,
        prev_week=(week_start - timedelta(days=7)).isoformat(),
        next_week=(week_start + timedelta(days=7)).isoformat(),
        today=datetime.now(UTC).date(),
        category_labels=STAFF_CATEGORY_LABELS,
        category_colors=STAFF_CATEGORY_COLORS,
    )


@roster_bp.route("/assign", methods=["POST"])
def assign():
    week_start = request.form.get("week_start", "")

    required = ["staff", "site_id", "shift_date", "start_time", "end_time"]
    for field in required:
        if not request.form.get(field, "").strip():
            flash("Please complete all required roster fields.", "error")
            return redirect(url_for("roster.master", week_start=week_start))

    site = Site.query.get_or_404(int(request.form["site_id"]))
    shift_date = _parse_date(request.form["shift_date"])
    start_time = _parse_time(request.form["start_time"])
    end_time = _parse_time(request.form["end_time"])
    role = request.form.get("role", "").strip()

    staff_type, _, staff_id = request.form["staff"].partition(":")
    if staff_type == "guard":
        guard = Guard.query.get_or_404(int(staff_id))
        shift = Shift(
            site_id=site.id,
            guard_id=guard.id,
            staff_category=STAFF_CATEGORY_GUARD,
            shift_date=shift_date,
            start_time=start_time,
            end_time=end_time,
            role=role,
            pay_rate=site.pay_rate_default or 0,
            bill_rate=site.bill_rate_default or 0,
        )
        person_name = guard.full_name
    elif staff_type == "user":
        user = User.query.get_or_404(int(staff_id))
        if user.role not in NON_GUARD_ROSTER_ROLES:
            flash("That staff member cannot be assigned via the Master Roster.", "error")
            return redirect(url_for("roster.master", week_start=week_start))
        shift = Shift(
            site_id=site.id,
            assigned_user_id=user.id,
            staff_category=ROLE_TO_STAFF_CATEGORY[user.role],
            shift_date=shift_date,
            start_time=start_time,
            end_time=end_time,
            role=role,
            pay_rate=0,
            bill_rate=0,
        )
        person_name = user.name
    else:
        flash("Invalid staff selection.", "error")
        return redirect(url_for("roster.master", week_start=week_start))

    db.session.add(shift)
    db.session.commit()
    flash(f"{person_name} assigned to {site.name} on {shift_date:%d %b %Y}.", "success")
    return redirect(url_for("roster.master", week_start=week_start))


@roster_bp.route("/<int:shift_id>/delete", methods=["POST"])
def delete(shift_id):
    shift = Shift.query.get_or_404(shift_id)
    week_start = request.form.get("week_start", "")

    if shift.status == "invoiced":
        flash("Invoiced shifts cannot be removed from the roster.", "error")
        return redirect(url_for("roster.master", week_start=week_start))

    db.session.delete(shift)
    db.session.commit()
    flash("Roster entry removed.", "success")
    return redirect(url_for("roster.master", week_start=week_start))
