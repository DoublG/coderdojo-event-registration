from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0017_event_cancelled_status"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="registration_opens_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Registrations open from this moment (blank: as soon as the session is open).",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="registration_closes_at",
            field=models.DateTimeField(
                blank=True,
                help_text="Registrations close at this moment (blank: only the status closes them).",
                null=True,
            ),
        ),
    ]
