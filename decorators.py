from functools import wraps

from flask import abort
from flask_login import current_user


def role_required(*allowed_roles):
    """Restrict a view to the given roles, enforcing GDPR data isolation.

    Any authenticated user outside ``allowed_roles`` receives a 403 rather
    than being redirected, so frontline accounts can never enumerate the
    existence of corporate/HR endpoints.
    """

    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if not current_user.is_authenticated:
                abort(401)
            if current_user.role not in allowed_roles:
                abort(403)
            return view(*args, **kwargs)

        return wrapped

    return decorator
