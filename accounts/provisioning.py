from .models import User


def unique_username(base):
    """`base`, or `base2`, `base3`, ... — the first username not taken yet."""
    base = base or "user"
    username = base
    n = 1
    while User.objects.filter(username=username).exists():
        n += 1
        username = f"{base}{n}"
    return username
