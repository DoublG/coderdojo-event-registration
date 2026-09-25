"""Existing dojos start with the language of their region: French in the
Walloon provinces ("Province de/du ..."), Dutch in the Flemish ones
("Provincie ..."), both in Brussels (postcodes 1000-1299, no province),
Dutch otherwise. Every dojo can change it on its Settings page."""

from django.db import migrations


def languages_for(dojo):
    province = dojo.province.name if dojo.province_id else ""
    if province.startswith("Province "):
        return ["fr-be"]
    if province.startswith("Provincie "):
        return ["nl-be"]
    postal_code = dojo.municipality.postal_code if dojo.municipality_id else ""
    if postal_code.isdigit() and 1000 <= int(postal_code) <= 1299:
        return ["nl-be", "fr-be"]
    return ["nl-be"]


def forwards(apps, schema_editor):
    Dojo = apps.get_model("dojos", "Dojo")
    for dojo in Dojo.objects.select_related("province", "municipality"):
        dojo.languages = languages_for(dojo)
        dojo.save(update_fields=["languages"])


class Migration(migrations.Migration):
    dependencies = [("dojos", "0003_content_languages")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
