"""Make the seeded demo site multilingual, the way a real one would be
(DATA_MODEL.md §19). Rerun-safe: every choice is deterministic per row,
and a text is only touched while it's still the English seed text.

- Dojo languages by region: Wallonia French, or French and English;
  Brussels and the dojos within AROUND_BRUSSELS_KM of it all three
  languages; Flanders mostly Dutch, some Dutch and English, a few Dutch and
  French. Only for dojos still on their region default (untouched).
- A dojo's own seeded texts (profile, sessions, updates, its FAQs) are
  written in its main language, with versions in its other languages.
- The organisation's content (pathways and their steps, projects, skills
  and FAQs, the global FAQs and testimonials, belts, badges, the team
  listing, promotions) gets its Dutch and French versions.
"""

import random

from django.contrib.gis.geos import Point
from django.core.management.base import BaseCommand
from django.db.models import F, FloatField
from django.db.models.expressions import ExpressionWrapper

from content.models import FAQ, Announcement, OrganisationTeamMember, Promotion, Testimonial
from core.audit import without_audit_log
from core.seed_translations import EN, FR, GIRLZ_PREFIX, NL, translate, translate_session_description
from dojos.languages import region_languages
from dojos.models import Dojo
from events.models import Badge, Belt, Event
from geo.functions import DistanceSphere
from pathways.models import Pathway, PathwayProject, PathwayStep, Skill

BRUSSELS = Point(4.3517, 50.8503, srid=4326)
AROUND_BRUSSELS_KM = 15


def seeded_languages(dojo, km_from_brussels):
    """A realistic language setup for a seeded dojo (main language first)."""
    rng = random.Random(f"dojo-languages-{dojo.pk}")
    region = region_languages(dojo)
    if len(region) > 1 or (km_from_brussels is not None and km_from_brussels <= AROUND_BRUSSELS_KM):
        main = region[0] if len(region) == 1 else rng.choice([NL, FR])
        return [main] + [code for code in (NL, FR, EN) if code != main]
    if region == [FR]:
        return [FR] if rng.random() < 0.5 else [FR, EN]
    roll = rng.random()
    return [NL] if roll < 0.6 else [NL, EN] if roll < 0.85 else [NL, FR]


def localize(obj, fields, translator=None):
    """Write `obj`'s English seed texts in its main language and add its
    other languages. Returns whether anything changed."""
    translator = translator or (lambda field, text, language: translate(text, language))
    languages = obj.content_languages()
    main = languages[0]
    changed = []
    for field in fields:
        base = getattr(obj, field)
        if not base:
            continue
        versions = {language: translator(field, base, language) for language in set(languages) | {EN}}
        if versions.get(main) is None or versions.get(EN) != base:
            continue  # not (or no longer) an English seed text
        touched = versions[main] != base
        setattr(obj, field, versions[main])
        for language in languages[1:]:
            if versions.get(language) and not obj.translation_for(language, field):
                obj.set_translation(language, field, versions[language])
                touched = True
        if touched:
            changed.append(field)
    if changed:
        obj.save(update_fields=changed + ["translations"])
    return bool(changed)


class Command(BaseCommand):
    help = "Give the seeded dojos languages by region and the seeded texts their Dutch and French versions (rerun-safe)."

    @without_audit_log
    def handle(self, *args, **options):
        counts = {}

        dojos = Dojo.objects.filter(kind=Dojo.DOJO).select_related("province", "municipality").annotate(
            km=ExpressionWrapper(DistanceSphere(F("location"), BRUSSELS) / 1000.0, output_field=FloatField()),
        )
        for dojo in dojos:
            if dojo.languages == region_languages(dojo) and not dojo.translations:
                languages = seeded_languages(dojo, dojo.km)
                if languages != dojo.languages:
                    dojo.languages = languages
                    dojo.save(update_fields=["languages"])
                    counts["dojo languages"] = counts.get("dojo languages", 0) + 1

        def run(label, queryset, fields, translator=None):
            n = sum(localize(obj, fields, translator) for obj in queryset)
            counts[label] = n

        run("dojos", Dojo.objects.all(), ["tagline", "description", "visit_notes", "schedule_description"])

        def event_translator(event):
            english_name = event.name
            base_name = english_name[len(GIRLZ_PREFIX[EN]):] if english_name.startswith(GIRLZ_PREFIX[EN]) else english_name

            def translator(field, text, language):
                if field == "name":
                    return translate(text, language)
                return translate_session_description(text, base_name, language) or translate(text, language)
            return translator

        n = 0
        for event in Event.objects.select_related("dojo"):
            n += localize(event, ["description", "name"], event_translator(event))
        counts["sessions"] = n

        n = 0
        for announcement in Announcement.objects.select_related("dojo"):
            n += localize(announcement, ["text"], lambda f, text, language, a=announcement: translate(text, language, a.dojo.name))
        counts["updates"] = n

        run("FAQs", FAQ.objects.select_related("dojo", "event__dojo"), ["question", "answer"])
        run("testimonials", Testimonial.objects.select_related("dojo"), ["quote", "role"])
        run("pathways", Pathway.objects.all(), ["name", "subtitle", "description"])
        run("pathway steps", PathwayStep.objects.all(), ["title", "description"])
        run("pathway projects", PathwayProject.objects.all(), ["title", "description"])
        run("skills", Skill.objects.all(), ["name"])
        run("belts", Belt.objects.all(), ["name", "requirements"])
        run("badges", Badge.objects.all(), ["name", "description", "criteria"])
        run("team listing", OrganisationTeamMember.objects.all(), ["position", "bio", "focus_areas"])
        run("promotions", Promotion.objects.select_related("event"), ["title", "text"])

        self.stdout.write(self.style.SUCCESS("Done. " + ", ".join(f"{k}={v}" for k, v in counts.items())))
