from django.db import migrations

# Periodic tasks that only the early Celery scaffolding registered (an hourly
# "hello" test task, and misspelled mailer.* names). The DatabaseScheduler
# never deletes an entry the code stopped defining, so remove them here.
STALE_TASKS = ["website.celery.test", "mailer.tasks.process_bounces", "mailer.tasks.send_pending_emails"]


def remove_stale_periodic_tasks(apps, schema_editor):
    apps.get_model("django_celery_beat", "PeriodicTask").objects.filter(task__in=STALE_TASKS).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("mailing", "0004_segment_scopes_templates_per_language"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.RunPython(remove_stale_periodic_tasks, migrations.RunPython.noop),
    ]
