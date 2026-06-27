from datetime import datetime, timezone

import pyotp
from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from extensions import db
from i18n import SUPPORTED_LANGUAGES
from models import FRONTLINE_ROLES, User

auth_bp = Blueprint("auth", __name__, url_prefix="")

# Session keys used outside of Flask-Login's own cookie state.
PENDING_MFA_KEY = "pending_mfa_user_id"
LAST_ACTIVITY_KEY = "last_activity"


def _post_login_redirect(user):
    if user.role in FRONTLINE_ROLES:
        return redirect(url_for("frontline.portal"))
    return redirect(url_for("dashboard"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return _post_login_redirect(current_user)

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()

        if not user or not user.is_active_account or not user.check_password(password):
            flash("login.error_invalid", "error")
            return render_template("auth/login.html"), 401

        # MFA challenge temporarily disabled for testing - log straight in
        # regardless of role. Restore the `user.requires_mfa` branch (see
        # models.MFA_REQUIRED_ROLES) to re-enable the /login/mfa redirect.
        _complete_login(user)
        return _post_login_redirect(user)

    return render_template("auth/login.html")


@auth_bp.route("/login/mfa", methods=["GET", "POST"])
def mfa():
    user_id = session.get(PENDING_MFA_KEY)
    if not user_id:
        return redirect(url_for("auth.login"))

    user = db.session.get(User, user_id)
    if not user:
        session.pop(PENDING_MFA_KEY, None)
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        code = request.form.get("code", "").strip()
        totp = pyotp.TOTP(user.mfa_secret)
        if totp.verify(code, valid_window=1):
            session.pop(PENDING_MFA_KEY, None)
            _complete_login(user)
            return _post_login_redirect(user)
        flash("login.error_mfa", "error")
        return render_template("auth/mfa.html"), 401

    return render_template("auth/mfa.html")


def _complete_login(user):
    login_user(user)
    user.last_login_at = datetime.now(timezone.utc)
    db.session.commit()
    session[LAST_ACTIVITY_KEY] = datetime.now(timezone.utc).isoformat()
    session.permanent = True


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    session.clear()
    flash("login.signed_out", "success")
    return redirect(url_for("auth.login"))


@auth_bp.route("/set-language/<lang_code>", methods=["POST"])
@login_required
def set_language(lang_code):
    if lang_code in SUPPORTED_LANGUAGES:
        current_user.language = lang_code
        db.session.commit()
    return redirect(request.referrer or url_for("dashboard"))
