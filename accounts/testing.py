"""Test helpers for accounts: used by the test modules of several apps; not
imported by the site itself."""


def with_admin_access(user, reason="Fixing a registration"):
    """Open `user`'s time-boxed access to the Django admin (accounts.admin_access,
    DATA_MODEL.md §23), as asked for on the dashboard; returns the account
    fresh (staff status and permission cache). It needs an organisation role."""
    from .admin_access import request_access

    request_access(user, reason)
    return type(user).objects.get(pk=user.pk)
