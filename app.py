import os
from datetime import date, datetime, timedelta, timezone, UTC

from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required

from blueprints.auth import LAST_ACTIVITY_KEY, auth_bp
from blueprints.frontline import frontline_bp
from blueprints.guards import guards_bp
from blueprints.invoices import invoices_bp
from blueprints.payroll import payroll_bp
from blueprints.roster import roster_bp
from blueprints.sites import sites_bp
from config import Config
from extensions import csrf, db, login_manager, mail
from i18n import SUPPORTED_LANGUAGES, translate
from models import AuditLog, FINANCE_ROLES, SESSION_TIMEOUT_MINUTES, Guard, Invoice, Shift, Site, User


def _current_week_range(today=None):
    today = today or date.today()
    start = today - timedelta(days=today.weekday())
    end = start + timedelta(days=6)
    return start, end


def _executive_metrics(sites):
    """Revenue, payroll, profit and weekly staffing snapshot for the executive dashboard."""
    total_revenue = float(sum(invoice.total_amount for invoice in Invoice.query.all()))
    total_payroll = round(
        sum(shift.pay_amount for shift in Shift.query.filter(Shift.guard_id.isnot(None)).all()), 2
    )
    net_profit = round(total_revenue - total_payroll, 2)
    profit_margin = round((net_profit / total_revenue) * 100, 1) if total_revenue else 0.0

    week_start, week_end = _current_week_range()
    week_shifts = Shift.query.filter(Shift.shift_date >= week_start, Shift.shift_date <= week_end).all()

    staff_ids = set()
    site_hours = {site.id: 0.0 for site in sites}
    for shift in week_shifts:
        if shift.guard_id is not None:
            staff_ids.add(("guard", shift.guard_id))
        elif shift.assigned_user_id is not None:
            staff_ids.add(("user", shift.assigned_user_id))
        if shift.site_id in site_hours:
            site_hours[shift.site_id] += shift.hours

    active_sites = [{"site": site, "hours": round(site_hours[site.id], 2)} for site in sites]

    week_guard_ids = {shift.guard_id for shift in week_shifts if shift.guard_id is not None}
    approved_hours_awaiting_payout = round(
        sum(
            shift.hours
            for shift in Shift.query.filter(
                Shift.guard_id.isnot(None),
                Shift.status.in_(["completed", "invoiced"]),
                Shift.approved_by_manager.is_(True),
                Shift.paid_out.is_(False),
            ).all()
        ),
        2,
    )
    estimated_weekly_payroll_liability = round(
        sum(
            round(
                shift.hours
                * (
                    float(shift.pay_rate)
                    if float(shift.pay_rate) > 0
                    else float(shift.guard.pay_rate)
                ),
                2,
            )
            for shift in week_shifts
            if shift.guard_id is not None
        ),
        2,
    )

    return {
        "total_revenue": total_revenue,
        "total_payroll": total_payroll,
        "net_profit": net_profit,
        "profit_margin": profit_margin,
        "scheduled_staff_count": len(staff_ids),
        "active_sites": active_sites,
        "active_guards_this_week": len(week_guard_ids),
        "approved_hours_awaiting_payout": approved_hours_awaiting_payout,
        "estimated_weekly_payroll_liability": estimated_weekly_payroll_liability,
        "week_start": week_start,
        "week_end": week_end,
    }


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.permanent_session_lifetime = timedelta(minutes=SESSION_TIMEOUT_MINUTES)

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    mail.init_app(app)

    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    app.register_blueprint(auth_bp)
    app.register_blueprint(frontline_bp)
    app.register_blueprint(guards_bp)
    app.register_blueprint(sites_bp)
    app.register_blueprint(invoices_bp)
    app.register_blueprint(payroll_bp)
    app.register_blueprint(roster_bp)

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    # ------------------------------------------------------------------
    # GDPR safeguard: enforce a 15-minute inactivity timeout and require
    # authentication on every page load (except the login routes/static).
    # ------------------------------------------------------------------
    @app.before_request
    def enforce_session_policy():
        if request.endpoint in (None, "static", "auth.login", "auth.mfa"):
            return None

        if not current_user.is_authenticated:
            return redirect(url_for("auth.login"))

        now = datetime.now(timezone.utc)
        last_activity_raw = session.get(LAST_ACTIVITY_KEY)
        if last_activity_raw:
            last_activity = datetime.fromisoformat(last_activity_raw)
            if now - last_activity > timedelta(minutes=SESSION_TIMEOUT_MINUTES):
                from flask_login import logout_user

                logout_user()
                session.clear()
                flash("login.session_expired", "error")
                return redirect(url_for("auth.login"))

        session[LAST_ACTIVITY_KEY] = now.isoformat()
        session.permanent = True
        return None

    @app.route("/")
    @login_required
    def dashboard():
        if current_user.is_frontline:
            return redirect(url_for("frontline.portal"))

        guards = Guard.query.all()
        expiring = [g for g in guards if g.sia_status == "expiring"]
        expired = [g for g in guards if g.sia_status == "expired"]
        sites = Site.query.filter_by(is_active=True).all()
        sites_with_pending = [s for s in sites if s.uninvoiced_shifts]
        recent_invoices = Invoice.query.order_by(Invoice.issue_date.desc()).limit(5).all()
        recent_activities = AuditLog.query.order_by(AuditLog.timestamp.desc()).limit(5).all()

        # Executive analytics (revenue/payroll/profit) are corporate financial
        # data - restricted to Owners and Ops Managers per GDPR data isolation.
        metrics = _executive_metrics(sites) if current_user.role in FINANCE_ROLES else None

        return render_template(
            "index.html",
            guard_count=len(guards),
            expiring=expiring,
            expired=expired,
            site_count=len(sites),
            sites_with_pending=sites_with_pending,
            recent_invoices=recent_invoices,
            recent_activities=recent_activities,
            metrics=metrics,
        )

    @app.errorhandler(403)
    def forbidden(_error):
        return render_template("errors/error.html", code=403, message="You don't have permission to view this page."), 403

    @app.errorhandler(404)
    def not_found(_error):
        return render_template("errors/error.html", code=404, message="That page could not be found."), 404

    @app.context_processor
    def inject_now():
        language = current_user.language if current_user.is_authenticated else "en"
        return {
            "current_year": datetime.now(UTC).year,
            "t": lambda key: translate(key, language),
            "current_language": language,
            "supported_languages": SUPPORTED_LANGUAGES,
        }

    with app.app_context():
        db.create_all()

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(debug=True)
