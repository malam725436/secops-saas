from datetime import datetime

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models import FINANCE_ROLES, Invoice, Shift, Site

invoices_bp = Blueprint("invoices", __name__, url_prefix="/invoices")


@invoices_bp.before_request
@login_required
def _restrict_to_finance_roles():
    """Shift-to-Invoice: Owners and Ops Managers only.

    HR/Compliance and all frontline roles are explicitly excluded from
    corporate financial/billing data per GDPR data-isolation requirements.
    """
    if current_user.role not in FINANCE_ROLES:
        abort(403)


def _parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date() if value else None


def _next_invoice_number(site):
    count = Invoice.query.filter_by(site_id=site.id).count() + 1
    return f"INV-{site.id:03d}-{datetime.utcnow():%Y%m}-{count:03d}"


@invoices_bp.route("/")
def list_invoices():
    invoices = Invoice.query.order_by(Invoice.issue_date.desc()).all()
    return render_template("invoices/list.html", invoices=invoices)


@invoices_bp.route("/generate", methods=["GET", "POST"])
def generate():
    sites = Site.query.filter_by(is_active=True).order_by(Site.name.asc()).all()

    if request.method == "POST":
        site = Site.query.get_or_404(int(request.form["site_id"]))
        period_start = _parse_date(request.form["period_start"])
        period_end = _parse_date(request.form["period_end"])

        if not period_start or not period_end or period_start > period_end:
            flash("Please choose a valid invoice period.", "error")
            return render_template("invoices/generate.html", sites=sites, form_data=request.form)

        eligible_shifts = (
            Shift.query.filter(
                Shift.site_id == site.id,
                Shift.guard_id.isnot(None),
                Shift.status == "completed",
                Shift.approved_by_manager.is_(True),
                Shift.invoice_id.is_(None),
                Shift.shift_date >= period_start,
                Shift.shift_date <= period_end,
            )
            .order_by(Shift.shift_date.asc())
            .all()
        )

        if not eligible_shifts:
            flash("No completed, un-invoiced shifts found for that site and period.", "error")
            return render_template("invoices/generate.html", sites=sites, form_data=request.form)

        invoice = Invoice(
            invoice_number=_next_invoice_number(site),
            site_id=site.id,
            period_start=period_start,
            period_end=period_end,
            total_amount=0,
        )
        db.session.add(invoice)
        db.session.flush()  # assign invoice.id before linking shifts

        total = 0
        for shift in eligible_shifts:
            role_override = request.form.get(f"role_{shift.id}")
            if role_override is not None:
                shift.role = role_override.strip()

            rate_override = request.form.get(f"rate_{shift.id}")
            if rate_override:
                try:
                    new_rate = float(rate_override)
                    if new_rate >= 0:
                        shift.bill_rate = new_rate
                except ValueError:
                    pass

            hours_override = request.form.get(f"hours_{shift.id}")
            if hours_override:
                try:
                    new_hours = float(hours_override)
                    if new_hours >= 0:
                        shift.total_hours = new_hours
                except ValueError:
                    pass

            shift.invoice_id = invoice.id
            shift.status = "invoiced"
            total += shift.bill_amount

        invoice.total_amount = round(total, 2)
        db.session.commit()

        flash(f"Invoice {invoice.invoice_number} generated from {len(eligible_shifts)} shift(s).", "success")
        return redirect(url_for("invoices.detail", invoice_id=invoice.id))

    return render_template("invoices/generate.html", sites=sites, form_data={})


@invoices_bp.route("/preview")
def preview():
    """JSON endpoint: un-invoiced, approved shift hours/total for a site & period."""
    site_id = request.args.get("site_id", type=int)
    period_start = _parse_date(request.args.get("period_start", ""))
    period_end = _parse_date(request.args.get("period_end", ""))

    site = Site.query.get_or_404(site_id) if site_id else None

    if not site or not period_start or not period_end or period_start > period_end:
        return jsonify(hours=0, billing_rate=0, amount=0, shift_count=0, shifts=[])

    eligible_shifts = Shift.query.filter(
        Shift.site_id == site.id,
        Shift.guard_id.isnot(None),
        Shift.status == "completed",
        Shift.approved_by_manager.is_(True),
        Shift.invoice_id.is_(None),
        Shift.shift_date >= period_start,
        Shift.shift_date <= period_end,
    ).order_by(Shift.shift_date.asc(), Shift.start_time.asc()).all()

    hours = round(sum(s.hours for s in eligible_shifts), 2)
    billing_rate = float(site.billing_rate)

    return jsonify(
        hours=hours,
        billing_rate=billing_rate,
        amount=round(hours * billing_rate, 2),
        shift_count=len(eligible_shifts),
        shifts=[
            {
                "id": shift.id,
                "shift_date": shift.shift_date.strftime("%d %b %Y"),
                "start_time": shift.start_time.strftime("%H:%M"),
                "end_time": shift.end_time.strftime("%H:%M"),
                "hours": shift.hours,
                "guard_name": shift.guard.full_name,
                "role": shift.role or "",
                "bill_rate": float(shift.bill_rate),
                "amount": shift.bill_amount,
            }
            for shift in eligible_shifts
        ],
    )


@invoices_bp.route("/<int:invoice_id>")
def detail(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    shifts = sorted(invoice.shifts, key=lambda s: (s.shift_date, s.start_time))
    return render_template("invoices/detail.html", invoice=invoice, shifts=shifts)


@invoices_bp.route("/<int:invoice_id>/mark-approved", methods=["POST"])
def mark_approved(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    invoice.status = "approved"
    db.session.commit()
    flash(f"Invoice {invoice.invoice_number} approved.", "success")
    return redirect(url_for("invoices.detail", invoice_id=invoice.id))


@invoices_bp.route("/<int:invoice_id>/mark-sent", methods=["POST"])
def mark_sent(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    invoice.status = "sent"
    db.session.commit()
    flash(f"Invoice {invoice.invoice_number} marked as sent.", "success")
    return redirect(url_for("invoices.detail", invoice_id=invoice.id))


@invoices_bp.route("/<int:invoice_id>/mark-paid", methods=["POST"])
def mark_paid(invoice_id):
    invoice = Invoice.query.get_or_404(invoice_id)
    invoice.status = "paid"
    db.session.commit()
    flash(f"Invoice {invoice.invoice_number} marked as paid.", "success")
    return redirect(url_for("invoices.detail", invoice_id=invoice.id))
