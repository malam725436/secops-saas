from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db, mail
from models import PAYROLL_ROLES, Setting

settings_bp = Blueprint("settings", __name__, url_prefix="/settings")

_MAIL_KEYS = [
    "MAIL_SERVER",
    "MAIL_PORT",
    "MAIL_USE_TLS",
    "MAIL_USERNAME",
    "MAIL_PASSWORD",
    "MAIL_DEFAULT_SENDER",
    "INVOICE_EMAIL_RECIPIENT",
]


@settings_bp.before_request
@login_required
def _restrict_to_admin_roles():
    if current_user.role not in PAYROLL_ROLES:
        abort(403)


def _coerce(key, raw_value):
    """Return the Python-typed value for a mail config key."""
    if key == "MAIL_PORT":
        try:
            return int(raw_value)
        except (ValueError, TypeError):
            return raw_value
    if key == "MAIL_USE_TLS":
        return str(raw_value).lower() in {"1", "true", "yes", "on"}
    return raw_value


@settings_bp.route("", methods=["GET", "POST"])
def overview():
    if request.method == "POST":
        raw = {
            "MAIL_SERVER": request.form.get("MAIL_SERVER", "").strip(),
            "MAIL_PORT": request.form.get("MAIL_PORT", "").strip(),
            "MAIL_USE_TLS": "1" if request.form.get("MAIL_USE_TLS") == "on" else "0",
            "MAIL_USERNAME": request.form.get("MAIL_USERNAME", "").strip(),
            "MAIL_PASSWORD": request.form.get("MAIL_PASSWORD", "").strip(),
            "MAIL_DEFAULT_SENDER": request.form.get("MAIL_DEFAULT_SENDER", "").strip(),
            "INVOICE_EMAIL_RECIPIENT": request.form.get("INVOICE_EMAIL_RECIPIENT", "").strip(),
        }

        for key, str_value in raw.items():
            row = Setting.query.filter_by(key=key).first()
            if row is None:
                db.session.add(Setting(key=key, value=str_value))
            else:
                row.value = str_value
            # Mirror into the running config so other config readers see the
            # new value within this request cycle.
            current_app.config[key] = _coerce(key, str_value)

        db.session.commit()

        # Flask-Mail snapshots its config into app.extensions["mail"] at
        # init time and reads from that snapshot (not app.config) on every
        # send. Updating the config alone is therefore not enough -- rebuild
        # the mail state so outbound email uses the just-saved credentials.
        mail.init_app(current_app._get_current_object())

        flash("Mail settings saved successfully.", "success")
        return redirect(url_for("settings.overview"))

    stored = {s.key: s.value for s in Setting.query.all()}
    return render_template("settings/overview.html", settings=stored)
