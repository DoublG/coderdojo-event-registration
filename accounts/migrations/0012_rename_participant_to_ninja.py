import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Redesign phase 7 (naming): Participant → Ninja."""

    dependencies = [
        ('accounts', '0011_organisation_role'),
        ('dojos', '0013_redesign_pathways'),
        ('events', '0012_redesign_badges_belts'),
    ]

    operations = [
        migrations.RenameModel('Participant', 'Ninja'),
        migrations.AlterField(
            model_name='ninja',
            name='home_dojo',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='home_ninjas', to='dojos.dojo'),
        ),
    ]
