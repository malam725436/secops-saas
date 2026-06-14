from datetime import datetime, timedelta

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from models import PAYROLL_ROLES, Guard, PayrollPayout, Shift

payroll_bp = Blueprint("payroll", __name__, url_prefix="/payroll")


@payroll_bp.before_request
@login_required
def _restrict_to_payroll_roles():
    """Payroll: Owners and HR/Compliance only."""
    if current_user.role not in PAYROLL_ROLES:
        abort(403)


def _parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date() if value else None


def _eligible_shifts(period_start, period_end):
    return Shift.query.filter(
        Shift.status == "completed",
        Shift.approved_by_manager.is_(True),
        Shift.paid_out.is_(False),
        Shift.shift_date >= period_start,
        Shift.shift_date <= period_end,
    ).all()


@payroll_bp.route("/")
def overview():
    today = datetime.utcnow().date()
    period_end = _parse_date(request.args.get("period_end", "")) or today
    period_start = _parse_date(request.args.get("period_start", "")) or (period_end - timedelta(days=13))

    shifts = _eligible_shifts(period_start, period_end)

    rows = []
    for guard in Guard.query.order_by(Guard.first_name.asc()).all():
        guard_shifts = [s for s in shifts if s.guard_id == guard.id]
        if not guard_shifts:
            continue
        total_hours = round(sum(s.hours for s in guard_shifts), 2)
        pay_rate = float(guard.pay_rate)
        rows.append(
            {
                "guard": guard,
                "total_hours": total_hours,
                "pay_rate": pay_rate,
                "total_pay": round(total_hours * pay_rate, 2),
            }
        )

    recent_payouts = PayrollPayout.query.order_by(PayrollPayout.approved_at.desc()).limit(10).all()

    return render_template(
        "payroll/overview.html",
        rows=rows,
        period_start=period_start,
        period_end=period_end,
        recent_payouts=recent_payouts,
    )


@payroll_bp.route("/payout/<int:guard_id>", methods=["POST"])
def approve_payout(guard_id):
    guard = Guard.query.get_or_404(guard_id)

    period_start = _parse_date(request.form.get("period_start", ""))
    period_end = _parse_date(request.form.get("period_end", ""))
    if not period_start or not period_end or period_start > period_end:
        flash("Please choose a valid payroll period.", "error")
        return redirect(url_for("payroll.overview"))

    guard_shifts = [s for s in _eligible_shifts(period_start, period_end) if s.guard_id == guard.id]
    if not guard_shifts:
        flash("No approved, unpaid hours found for that guard and period.", "error")
        return redirect(url_for("payroll.overview", period_start=period_start, period_end=period_end))

    total_hours = round(sum(s.hours for s in guard_shifts), 2)
    total_pay = round(total_hours * float(guard.pay_rate), 2)

    payout = PayrollPayout(
        guard_id=guard.id,
        period_start=period_start,
        period_end=period_end,
        total_hours=total_hours,
        total_pay=total_pay,
        approved_by_id=current_user.id,
    )
    db.session.add(payout)

    for shift in guard_shifts:
        shift.paid_out = True

    db.session.commit()
    flash(f"Payout of £{total_pay:.2f} approved for {guard.full_name}.", "success")
    return redirect(url_for("payroll.overview", period_start=period_start, period_end=period_end))
