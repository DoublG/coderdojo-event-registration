import django.db.models.deletion
from django.db import migrations, models


def delete_ungrouped_rules(apps, schema_editor):
    # Rules move from the segment to a group; a rule without a group means
    # nothing, and there's no data to keep yet (DATA_MODEL.md §11).
    apps.get_model("mailing", "SegmentRule").objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("mailing", "0003_segment_campaign_segment_snapshot_campaign_segment_and_more"),
    ]

    operations = [
        # Segment groups nest and have a scope; rules hang off a group.
        migrations.AddField(
            model_name="segmentgroup",
            name="parent",
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                related_name="children", to="mailing.segmentgroup",
            ),
        ),
        migrations.AlterField(
            model_name="segmentgroup",
            name="operator",
            field=models.CharField(choices=[("and", "AND"), ("or", "OR")], default="and", max_length=3),
        ),
        migrations.AddField(
            model_name="segmentgroup",
            name="scope",
            field=models.CharField(
                choices=[("user", "Accounts"), ("ninja", "Parents of a child who …")], default="user", max_length=5,
            ),
        ),
        migrations.RunPython(delete_ungrouped_rules, migrations.RunPython.noop),
        migrations.RemoveField(model_name="segmentrule", name="segment"),
        migrations.AddField(
            model_name="segmentrule",
            name="group",
            field=models.ForeignKey(
                null=True, on_delete=django.db.models.deletion.CASCADE, related_name="rules", to="mailing.segmentgroup",
            ),
        ),
        migrations.AlterField(
            model_name="segmentrule",
            name="group",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE, related_name="rules", to="mailing.segmentgroup",
            ),
        ),
        # Campaigns: a mail category and a template key instead of a fixed
        # subject; the snapshot stays empty until launch.
        migrations.RemoveField(model_name="campaign", name="subject"),
        migrations.RemoveField(model_name="campaign", name="email_type"),
        migrations.AddField(
            model_name="campaign",
            name="category",
            field=models.CharField(
                choices=[
                    ("service", "Account and security"), ("registration", "Session bookings"),
                    ("reminder", "Reminders"), ("dojo_news", "News from your dojo"),
                    ("volunteer", "Volunteering"), ("newsletter", "Newsletter and campaigns"),
                ],
                default="newsletter", max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="campaign",
            name="template_key",
            field=models.CharField(
                default="", help_text="EmailTemplate.key; each recipient gets the version in their language.",
                max_length=100,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="campaign",
            name="context",
            field=models.JSONField(
                blank=True, default=dict,
                help_text='Extra template variables for this campaign, e.g. {"signup_url": "https://…"}.',
            ),
        ),
        migrations.AlterField(
            model_name="campaign",
            name="segment_snapshot",
            field=models.JSONField(blank=True, null=True),
        ),
        # Email templates: one row per key and language, with a category.
        migrations.AlterField(
            model_name="emailtemplate",
            name="key",
            field=models.CharField(max_length=100),
        ),
        migrations.AddField(
            model_name="emailtemplate",
            name="language",
            field=models.CharField(
                choices=[("en-us", "English"), ("nl-be", "Nederlands (België)"),
                         ("fr-be", "Français (Belgique)"), ("de", "Deutsch")],
                default="en-us", max_length=10,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="emailtemplate",
            name="category",
            field=models.CharField(
                choices=[
                    ("service", "Account and security"), ("registration", "Session bookings"),
                    ("reminder", "Reminders"), ("dojo_news", "News from your dojo"),
                    ("volunteer", "Volunteering"), ("newsletter", "Newsletter and campaigns"),
                ],
                default="service", max_length=20,
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name="emailtemplate",
            name="description",
            field=models.CharField(blank=True, help_text="When it's sent and which variables it uses.", max_length=255),
        ),
        migrations.AlterModelOptions(name="emailtemplate", options={"ordering": ["key", "language"]}),
        migrations.AddConstraint(
            model_name="emailtemplate",
            constraint=models.UniqueConstraint(fields=("key", "language"), name="unique_email_template_language"),
        ),
    ]
