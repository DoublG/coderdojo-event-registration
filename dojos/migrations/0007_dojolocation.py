import django.contrib.gis.db.models.fields
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dojos", "0006_default_questions"),
    ]

    operations = [
        migrations.CreateModel(
            name="DojoLocation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(help_text='e.g. "Ghent Public Library".', max_length=200)),
                ("address", models.CharField(blank=True, default="", max_length=300)),
                (
                    "location",
                    django.contrib.gis.db.models.fields.PointField(
                        blank=True, null=True, spatial_index=False, srid=4326
                    ),
                ),
                (
                    "dojo",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="locations", to="dojos.dojo"
                    ),
                ),
            ],
            options={
                "ordering": ["name", "id"],
            },
        ),
    ]
