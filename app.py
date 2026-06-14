from datetime import datetime, timedelta, timezone

from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required

from blueprints.auth import LAST_ACTIVITY_KEY, auth_bp
from blueprints.frontline import frontline_bp
from blueprints.guards import guards_bp
from blueprints.invoices import invoices_bp
from blueprints.payroll import payroll_bp
from blueprints.sites import sites_bp
from config import Config
from extensions import csrf, db, login_manager
from i18n import SUPPORTED_LANGUAGES, translate
from models import SESSION_TIMEOUT_MINUTES, Guard, Invoice, Site, User


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    app.permanent_session_lifetime = timedelta(minutes=SESSION_TIMEOUT_MINUTES)

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)

    app.register_blueprint(auth_bp)
    app.register_blueprint(frontline_bp)
    app.register_blueprint(guards_bp)
    app.register_blueprint(sites_bp)
    app.register_blueprint(invoices_bp)
    app.register_blueprint(payroll_bp)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

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

        return render_template(
            "dashboard.html",
            guard_count=len(guards),
            expiring=expiring,
            expired=expired,
            site_count=len(sites),
            sites_with_pending=sites_with_pending,
            recent_invoices=recent_invoices,
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
            "current_year": datetime.utcnow().year,
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
