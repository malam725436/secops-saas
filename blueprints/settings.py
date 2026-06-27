from flask import Blueprint, abort, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from flask_mail import Message

from authz import roles_required
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


# System settings: Owners and HR/Compliance only.
settings_bp.before_request(roles_required(*PAYROLL_ROLES))


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


@settings_bp.route("/test-email", methods=["POST"])
def test_email():
    """Send a confirmation email to the default sender using the saved SMTP
    settings, surfacing any live connection failure to the admin.

    The app's before_request hook already syncs app.config and rebuilds the
    Flask-Mail state from the database on every request, so the mail extension
    here reflects the saved configuration without re-reading it manually.
    """
    recipient = (current_app.config.get("MAIL_DEFAULT_SENDER") or "").strip()
    if not current_app.config.get("MAIL_SERVER"):
        flash("Set a mail server before sending a test email.", "error")
        return redirect(url_for("settings.overview"))
    if not recipient:
        flash("Set a default sender address before sending a test email.", "error")
        return redirect(url_for("settings.overview"))

    message = Message(
        subject="SecOps Hub — test email",
        recipients=[recipient],
        sender=recipient,
        body=(
            "This is a test email from SecOps Hub.\n\n"
            "If you received this message, your SMTP settings are working correctly."
        ),
    )

    try:
        mail.send(message)
    except Exception as exc:  # noqa: BLE001 - report any SMTP/socket failure to the admin
        current_app.logger.exception("Test email failed")
        flash(f"Test email failed: {exc}", "error")
        return redirect(url_for("settings.overview"))

    flash(f"Test email sent to {recipient}.", "success")
    return redirect(url_for("settings.overview"))
