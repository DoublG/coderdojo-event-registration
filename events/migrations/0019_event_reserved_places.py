from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("events", "0018_event_registration_window"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="reserved_places",
            field=models.PositiveIntegerField(
                default=0,
                help_text="Places held for the children of the dojo's team until they're released (0: none held).",
            ),
        ),
        migrations.AddField(
            model_name="event",
            name="reserved_release_at",
            field=models.DateTimeField(
                blank=True,
                help_text="When the held places open to everyone (blank: when registrations close, or at the start of the session when they don't).",
                null=True,
            ),
        ),
    ]
