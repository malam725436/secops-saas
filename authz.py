"""Reusable role/credential verification for admin & owner surfaces.

Centralises the access-control pattern so every privileged blueprint declares
its allowed roles in one robust, auditable line instead of re-implementing the
same authenticated-and-role-checked guard:

    my_bp.before_request(roles_required(*FINANCE_ROLES))

Standard (frontline) user credentials cannot step into high-level dashboard
features: unauthenticated requests are bounced to login by Flask-Login, and
authenticated users without an allowed role get a hard 403.
"""
from flask import abort
from flask_login import current_user, login_required


def roles_required(*roles):
    """Build a ``before_request`` guard that allows only the given roles.

    Authentication is enforced first (Flask-Login); an authenticated user whose
    role is not in ``roles`` is rejected with 403.
    """
    allowed = frozenset(roles)

    @login_required
    def guard():
        if current_user.role not in allowed:
            abort(403)

    return guard
