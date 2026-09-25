"""A starting language for a dojo from where it is (Dojo.languages; the dojo
team changes it on its Settings page): French in the Walloon provinces,
Dutch in the Flemish ones, both in Brussels (postcodes 1000-1299, which
has no province), Dutch otherwise. Used by the seeders and the dojo import;
dojos/migrations/0004 applied the same rule to the dojos that existed."""

FRENCH, DUTCH = "fr-be", "nl-be"


def region_languages(dojo):
    province = dojo.province.name if dojo.province_id else ""
    if province.startswith("Province "):
        return [FRENCH]
    if province.startswith("Provincie "):
        return [DUTCH]
    postal_code = dojo.municipality.postal_code if dojo.municipality_id else ""
    if postal_code.isdigit() and 1000 <= int(postal_code) <= 1299:
        return [DUTCH, FRENCH]
    return [DUTCH]
