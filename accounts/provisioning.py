import secrets

from django.conf import settings
from django.core.mail import send_mail
from django.utils.text import slugify

from .models import User


def unique_username(base):
    base = base or "user"
    username = base
    n = 1
    while User.objects.filter(username=username).exists():
        n += 1
        username = f"{base}{n}"
    return username


def provision_account(account_model, name, email, login_url):
    """Create a `account_model` instance (DojoOwner or HelperAccount) with
    a random temporary password and must_change_password=True, then email
    that password to `email`. Used by applications.admin's "approve"
    actions — dojo owners and helpers never set their own password; an
    admin approves their application and this is what provisions the
    login ForcePasswordChangeMiddleware will insist they replace it on
    first use."""
    first_name, _, last_name = name.partition(" ")
    username = unique_username(slugify(name) or slugify(email.split("@")[0]))
    temp_password = secrets.token_urlsafe(9)

    account = account_model(
        username=username, email=email, first_name=first_name, last_name=last_name,
        must_change_password=True,
    )
    account.set_password(temp_password)
    account.save()

    send_mail(
        subject="Activate your CoderDojo account",
        message=(
            f"Hi {first_name or name},\n\n"
            "Your application has been approved. Activate your account by logging in with "
            "the temporary password below, then choose your own — you'll be asked to set a "
            "new one the moment you log in.\n\n"
            f"  Login: {login_url}\n"
            f"  Email: {email}\n"
            f"  Temporary password: {temp_password}\n"
        ),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
    )
    return account


def attach_role(user, role_model, **extra_fields):
    """Adds `role_model` (DojoOwner/HelperAccount) to `user`'s existing pk instead of
    provisioning a disconnected new User row — used when someone who's already logged in (as
    another role, or as this same one — e.g. a DojoOwner starting a second dojo) gains a role
    rather than applying as a stranger. Copies User's own fields (password, email, etc.) onto the
    new instance field-by-field via getattr/setattr — NOT `role_obj.__dict__.update(user.__dict__)`,
    which looks equivalent but silently corrupts the account (blanks password and logs the caller
    out) when `user` is `request.user`: that's a SimpleLazyObject proxy, and `.__dict__` on it
    returns the *proxy's own* internal attributes, not the wrapped User's field values, since
    `__dict__` access bypasses `__getattr__`. getattr()/setattr() go through the proxy correctly.
    `role_model`'s own table then gets a fresh INSERT for that same pk (or, if a row already
    exists there — e.g. re-attaching a role the account already has — a harmless UPDATE, never a
    duplicate-row error: see Model._save_table's insert-on-update-affecting-0-rows fallback for
    why a fresh row inserts cleanly here)."""
    role_obj = role_model(user_ptr_id=user.pk)
    for field in User._meta.concrete_fields:
        setattr(role_obj, field.attname, getattr(user, field.attname))
    for field, value in extra_fields.items():
        setattr(role_obj, field, value)
    role_obj.save()
    return role_obj
