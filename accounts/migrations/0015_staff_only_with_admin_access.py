"""The Django admin is asked for, 12 hours at a time (DATA_MODEL.md §23): an
organisation role no longer makes an account staff, so every account but a
superuser loses the staff status it held for good. Nobody has an open grant
yet."""

from django.db import migrations


def drop_standing_staff(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    User.objects.filter(is_staff=True, is_superuser=False).update(is_staff=False)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0014_admin_access_grant"),
    ]

    operations = [
        migrations.RunPython(drop_standing_staff, migrations.RunPython.noop),
    ]
