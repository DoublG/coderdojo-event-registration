from django.db import migrations


class Migration(migrations.Migration):
    """Redesign phase 7 (naming): the `participant` links become `ninja`."""

    dependencies = [
        ('accounts', '0012_rename_participant_to_ninja'),
        ('events', '0012_redesign_badges_belts'),
    ]

    operations = [
        migrations.AlterUniqueTogether(name='registration', unique_together=set()),
        migrations.RenameField('registration', 'participant', 'ninja'),
        migrations.AlterUniqueTogether(name='registration', unique_together={('event', 'ninja')}),
        migrations.RenameField('event', 'participants', 'ninjas'),
        migrations.AlterUniqueTogether(name='ninjabadge', unique_together=set()),
        migrations.RenameField('ninjabadge', 'participant', 'ninja'),
        migrations.AlterUniqueTogether(name='ninjabadge', unique_together={('ninja', 'badge')}),
        migrations.RenameField('ninjabelt', 'participant', 'ninja'),
    ]
