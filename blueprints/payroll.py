import csv
import io
from datetime import datetime, timedelta, UTC

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from authz import roles_required
from extensions import db
from models import PAYROLL_ROLES, Guard, PayrollPayout, Shift

payroll_bp = Blueprint("payroll", __name__, url_prefix="/payroll")

# Payroll: Owners and HR/Compliance only.
payroll_bp.before_request(roles_required(*PAYROLL_ROLES))


def _parse_date(value):
    return datetime.strptime(value, "%Y-%m-%d").date() if value else None


def _eligible_shifts(period_start, period_end):
    return Shift.query.filter(
        Shift.guard_id.isnot(None),
        Shift.status.in_(["completed", "invoiced"]),
        Shift.approved_by_manager.is_(True),
        Shift.paid_out.is_(False),
        Shift.shift_date >= period_start,
        Shift.shift_date <= period_end,
    ).all()


def _week_start_for_date(day):
    return day - timedelta(days=day.weekday())


def _calculate_shift_breakdown(shift, fallback_rate, weekly_hours_before_shift=0.0):
    base_rate = float(shift.pay_rate) if getattr(shift, "pay_rate", None) and float(shift.pay_rate) > 0 else fallback_rate
    hours = float(shift.hours)

    if getattr(shift, "is_designated_holiday", False):
        active_rate = round(base_rate * 1.25, 2)
        amount = round(hours * active_rate, 2)
        return active_rate, amount, 0.0, 0.0, hours, 1.25, "holiday"

    normal_hours = max(40.0 - float(weekly_hours_before_shift), 0.0)
    overtime_hours = max(hours - normal_hours, 0.0)
    regular_hours = hours - overtime_hours
    if overtime_hours > 0:
        active_rate = round(base_rate * 1.5, 2)
        amount = round(regular_hours * base_rate + overtime_hours * active_rate, 2)
        return active_rate, amount, regular_hours, overtime_hours, 0.0, 1.5, "overtime"

    amount = round(hours * base_rate, 2)
    return base_rate, amount, hours, 0.0, 0.0, 1.0, None


def _calculate_shift_pay(shift, fallback_rate, weekly_hours_before_shift=0.0):
    active_rate, amount, _, _, _, multiplier, premium_reason = _calculate_shift_breakdown(
        shift, fallback_rate, weekly_hours_before_shift
    )
    return active_rate, amount, multiplier, premium_reason


def _apply_payroll_rules(guard_shifts, fallback_rate):
    weekly_hours = {}
    total_pay = 0.0
    for shift in guard_shifts:
        week_start = _week_start_for_date(shift.shift_date)
        prior_week_hours = weekly_hours.get(week_start, 0.0)
        active_rate, amount, regular_hours, overtime_hours, holiday_hours, multiplier, premium_reason = (
            _calculate_shift_breakdown(shift, fallback_rate, prior_week_hours)
        )
        weekly_hours[week_start] = prior_week_hours + float(shift.hours)
        shift.active_pay_rate = active_rate
        shift.pay_amount = amount
        shift.premium_multiplier = multiplier
        shift.premium_reason = premium_reason
        shift.regular_hours = regular_hours
        shift.overtime_hours = overtime_hours
        shift.holiday_hours = holiday_hours
        total_pay += amount
    return round(total_pay, 2)


@payroll_bp.route("/")
def overview():
    today = datetime.now(UTC).date()
    period_end = _parse_date(request.args.get("period_end", "")) or today
    period_start = _parse_date(request.args.get("period_start", "")) or (period_end - timedelta(days=13))

    shifts = _eligible_shifts(period_start, period_end)

    rows = []
    for guard in Guard.query.order_by(Guard.first_name.asc()).all():
        guard_shifts = [s for s in shifts if s.guard_id == guard.id]
        if not guard_shifts:
            continue
        guard_shifts.sort(key=lambda s: (s.shift_date, s.start_time))
        total_hours = round(sum(s.hours for s in guard_shifts), 2)
        pay_rate = float(guard.pay_rate)
        total_pay = _apply_payroll_rules(guard_shifts, pay_rate)
        rows.append(
            {
                "guard": guard,
                "shifts": guard_shifts,
                "total_hours": total_hours,
                "pay_rate": pay_rate,
                "total_pay": round(total_pay, 2),
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


@payroll_bp.route("/export/csv")
def export_csv():
    today = datetime.now(UTC).date()
    period_end = _parse_date(request.args.get("period_end", "")) or today
    period_start = _parse_date(request.args.get("period_start", "")) or (period_end - timedelta(days=13))

    if not period_start or not period_end or period_start > period_end:
        flash("Please choose a valid payroll period.", "error")
        return redirect(url_for("payroll.overview"))

    shifts = _eligible_shifts(period_start, period_end)
    rows = []
    for guard in Guard.query.order_by(Guard.first_name.asc()).all():
        guard_shifts = [s for s in shifts if s.guard_id == guard.id]
        if not guard_shifts:
            continue
        guard_shifts.sort(key=lambda s: (s.shift_date, s.start_time))
        pay_rate = float(guard.pay_rate)
        _apply_payroll_rules(guard_shifts, pay_rate)
        rows.append(
            {
                "guard": guard,
                "regular_hours": round(sum(getattr(s, "regular_hours", 0.0) for s in guard_shifts), 2),
                "overtime_hours": round(sum(getattr(s, "overtime_hours", 0.0) for s in guard_shifts), 2),
                "holiday_hours": round(sum(getattr(s, "holiday_hours", 0.0) for s in guard_shifts), 2),
                "total_hours": round(sum(s.hours for s in guard_shifts), 2),
                "total_pay": round(sum(getattr(s, "pay_amount", 0.0) for s in guard_shifts), 2),
            }
        )

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["Guard", "Employee number", "Regular hours", "Overtime hours", "Holiday hours", "Total hours", "Total payout"])
    for row in rows:
        writer.writerow(
            [
                row["guard"].full_name,
                row["guard"].employee_number or "",
                f"{row['regular_hours']:.2f}",
                f"{row['overtime_hours']:.2f}",
                f"{row['holiday_hours']:.2f}",
                f"{row['total_hours']:.2f}",
                f"{row['total_pay']:.2f}",
            ]
        )

    csv_bytes = output.getvalue().encode("utf-8")
    response = Response(csv_bytes, mimetype="text/csv; charset=utf-8")
    filename = f"payroll_export_{period_start.strftime('%Y%m%d')}_to_{period_end.strftime('%Y%m%d')}.csv"
    response.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return response


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
    fallback_rate = float(guard.pay_rate)
    total_pay = _apply_payroll_rules(guard_shifts, fallback_rate)

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
