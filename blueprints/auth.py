from datetime import datetime, timezone

import pyotp
import segno
from flask import Blueprint, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from extensions import db
from i18n import SUPPORTED_LANGUAGES
from models import FRONTLINE_ROLES, User

auth_bp = Blueprint("auth", __name__, url_prefix="")

# Identity shown in authenticator apps for the TOTP account label.
MFA_ISSUER = "SecOps Hub"

# Session keys used outside of Flask-Login's own cookie state.
PENDING_MFA_KEY = "pending_mfa_user_id"
PENDING_MFA_SECRET_KEY = "pending_mfa_secret"
MFA_VERIFIED_KEY = "mfa_verified"
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

        # High-privilege roles must clear an MFA challenge before any
        # authenticated session is granted. We deliberately do NOT call
        # login_user() here: the user stays anonymous (no dashboard access)
        # and is flagged unverified until the TOTP step succeeds.
        if user.requires_mfa:
            session.clear()  # session-fixation defence before storing pending state
            session[PENDING_MFA_KEY] = user.id
            session[MFA_VERIFIED_KEY] = False
            # Unprovisioned eligible users are sent to first-time enrollment;
            # already-enrolled users go straight to the TOTP challenge.
            if not user.mfa_secret:
                return redirect(url_for("auth.mfa_enroll"))
            return redirect(url_for("auth.mfa"))

        _complete_login(user)
        return _post_login_redirect(user)

    return render_template("auth/login.html")


@auth_bp.route("/auth/mfa", methods=["GET", "POST"])
def mfa():
    user_id = session.get(PENDING_MFA_KEY)
    if not user_id:
        return redirect(url_for("auth.login"))

    user = db.session.get(User, user_id)
    if not user:
        session.pop(PENDING_MFA_KEY, None)
        return redirect(url_for("auth.login"))

    if not user.mfa_secret:
        # Role demands MFA but the account has no enrolled authenticator yet:
        # send them through first-time enrollment rather than locking them out.
        return redirect(url_for("auth.mfa_enroll"))

    if request.method == "POST":
        code = request.form.get("code", "").strip()
        if pyotp.TOTP(user.mfa_secret).verify(code, valid_window=1):
            session.pop(PENDING_MFA_KEY, None)
            _complete_login(user)             # rotates session + logs the user in
            session[MFA_VERIFIED_KEY] = True  # set AFTER the session rotation
            return _post_login_redirect(user)
        flash("login.error_mfa", "error")
        return render_template("auth/mfa.html"), 401

    return render_template("auth/mfa.html")


def _mfa_qr_data_uri(totp_uri):
    """Render the otpauth URI to a base64 PNG data URI (generated locally so the
    TOTP secret never leaves the server)."""
    return segno.make(totp_uri, error="m").png_data_uri(scale=5, border=2)


@auth_bp.route("/auth/mfa/enroll", methods=["GET", "POST"])
def mfa_enroll():
    user_id = session.get(PENDING_MFA_KEY)
    if not user_id:
        return redirect(url_for("auth.login"))

    user = db.session.get(User, user_id)
    if not user or not user.requires_mfa:
        session.pop(PENDING_MFA_KEY, None)
        return redirect(url_for("auth.login"))

    if user.mfa_secret:
        # Already enrolled: nothing to set up, go to the verification challenge.
        return redirect(url_for("auth.mfa"))

    # Hold a provisional secret in the session until the user proves possession
    # with a valid code. It is NOT persisted until verification succeeds, so an
    # abandoned enrollment never locks the account.
    secret = session.get(PENDING_MFA_SECRET_KEY)
    if not secret:
        secret = pyotp.random_base32()
        session[PENDING_MFA_SECRET_KEY] = secret

    if request.method == "POST":
        code = request.form.get("code", "").strip()
        if pyotp.TOTP(secret).verify(code, valid_window=1):
            user.mfa_secret = secret
            user.mfa_enabled = True
            session.pop(PENDING_MFA_SECRET_KEY, None)
            session.pop(PENDING_MFA_KEY, None)
            _complete_login(user)             # commits the secret, rotates session, logs in
            session[MFA_VERIFIED_KEY] = True  # set AFTER the session rotation
            flash("Two-factor authentication is now enabled.", "success")
            return _post_login_redirect(user)
        # Reject without discarding the provisional secret so the same QR/key
        # stays valid for another attempt.
        flash("That code didn't match. Scan the QR code or enter the key, then try again.", "error")

    totp_uri = pyotp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=MFA_ISSUER)
    return render_template(
        "auth/mfa_enroll.html",
        secret=secret,
        totp_uri=totp_uri,
        qr_data_uri=_mfa_qr_data_uri(totp_uri),
        account_email=user.email,
    )


def _complete_login(user):
    # Session-fixation defence: discard any pre-authentication session state
    # (e.g. an attacker-planted session) so a fresh, authenticated session is
    # issued the moment privileges are granted. This keeps low-privilege or
    # anonymous session data from carrying into an owner/admin session.
    session.clear()
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
