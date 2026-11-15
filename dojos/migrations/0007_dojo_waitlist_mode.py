from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dojos", "0006_default_questions"),
    ]

    operations = [
        migrations.AddField(
            model_name="dojo",
            name="waitlist_mode",
            field=models.CharField(
                choices=[("auto", "Automatic"), ("manual", "The team chooses")],
                default="auto",
                help_text="Automatic: a free place goes to the child waiting longest (the family is mailed). The team chooses: it stays free until the team gives it to a child on the waiting list.",
                max_length=10,
            ),
        ),
    ]
