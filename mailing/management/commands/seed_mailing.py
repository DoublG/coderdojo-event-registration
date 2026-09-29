import copy

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.urls import reverse

from core.audit import without_audit_log
from dojos.models import Dojo
from mailing import campaigns as campaign_rules
from mailing.categories import MailCategory
from mailing.models import Campaign, Segment, SegmentGroup, SegmentRule
from mailing.seed_templates import CAMPAIGNS, NEW_DOJO

# A dojo's own mail (DATA_MODEL.md §25): one sent to all its families, one
# still a draft. Found again by dojo and name, never by their texts.
DOJO_MAILINGS = [
    {
        "name": "Seed: thanks for this season",
        "send": True,
        "subject": {
            "en-us": "Thanks for a great season",
            "nl-be": "Bedankt voor een fijn seizoen",
            "fr-be": "Merci pour cette belle saison",
        },
        "message": {
            "en-us": "Hi all,\n\nThanks for coming to our sessions this season. The new sessions are on our page.\n\nSee you soon!",
            "nl-be": "Dag allemaal,\n\nBedankt om dit seizoen naar onze sessies te komen. De nieuwe sessies staan op onze pagina.\n\nTot snel!",
            "fr-be": "Bonjour à tous,\n\nMerci d'être venus à nos sessions cette saison. Les nouvelles sessions sont sur notre page.\n\nÀ bientôt !",
        },
    },
    {
        "name": "Seed: bring a charger",
        "send": False,
        "subject": {
            "en-us": "Bring your laptop charger",
            "nl-be": "Neem je laptoplader mee",
            "fr-be": "Apportez votre chargeur",
        },
        "message": {
            "en-us": "Hi all,\n\nWe're short of sockets: please bring a charged laptop and its charger.",
            "nl-be": "Dag allemaal,\n\nWe hebben te weinig stopcontacten: breng een opgeladen laptop en de lader mee.",
            "fr-be": "Bonjour à tous,\n\nNous manquons de prises : apportez un ordinateur chargé et son chargeur.",
        },
    },
]


class Command(BaseCommand):
    help = (
        "Seed the example email templates (en/nl/fr) and three draft campaigns with their segments: "
        "Coolest Projects (everyone active: champions and mentors of dojos with recent sessions, and parents of children who came to one), CoderDojo Girlz (families with a girl or a "
        "child whose gender isn't listed) and New dojo opening (families within 20 km of a new dojo). "
        "Rerun-safe: only creates what's missing and never overwrites a template, segment or "
        "campaign someone has edited."
    )

    @transaction.atomic
    @without_audit_log
    def handle(self, *args, **options):
        call_command("load_mail_templates", stdout=self.stdout)

        campaigns_created = 0
        for spec in CAMPAIGNS:
            if Campaign.objects.filter(name=spec["name"]).exists():
                continue
            spec = copy.deepcopy(spec)
            if spec["template_key"] == "campaign_new_dojo" and not self._fill_in_new_dojo(spec):
                self.stdout.write(f"Skipped “{spec['name']}”: no dojo with a location to open.")
                continue
            Campaign.objects.create(
                name=spec["name"],
                segment=self._segment(spec["segment"]),
                template_key=spec["template_key"],
                context=spec["context"],
            )
            campaigns_created += 1

        dojo_mailings = self._seed_dojo_mailings()
        self.stdout.write(
            self.style.SUCCESS(f"Done. campaigns={campaigns_created} dojo_mailings={dojo_mailings} (new rows only).")
        )

    def _seed_dojo_mailings(self):
        """A sent and a draft mail from the first public dojo with families
        whose champion can use its admin area. Replies go to the dojo's email address, so a
        dojo without one gets its champion's (seeded data only)."""
        from dojos.access import managing_membership
        from mailing.dojo_families import active_since, family_accounts

        dojo = next(
            (
                d
                for d in Dojo.objects.public().order_by("id")
                if d.champion and managing_membership(d.champion, d) and family_accounts(d, active_since()).exists()
            ),
            None,
        )
        if dojo is None:
            self.stdout.write("Skipped the dojo mailings: no public dojo with a champion and families.")
            return 0
        if not dojo.email:
            dojo.email = dojo.champion.email
            dojo.save(update_fields=["email"])
        created = 0
        for spec in DOJO_MAILINGS:
            if Campaign.objects.filter(dojo=dojo, name=spec["name"]).exists():
                continue
            main, others = dojo.main_language(), dojo.content_languages()[1:]
            campaign = Campaign(
                name=spec["name"],
                dojo=dojo,
                category=MailCategory.DOJO_NEWS,
                template_key=campaign_rules.DOJO_TEMPLATE,
                audience="all_families",
                subject=spec["subject"].get(main, spec["subject"]["en-us"]),
                message=spec["message"].get(main, spec["message"]["en-us"]),
                created_by=dojo.champion,
            )
            for language in others:
                for field in ("subject", "message"):
                    campaign.set_translation(language, field, spec[field].get(language, ""))
            campaign.save()
            created += 1
            if spec["send"] and not campaign_rules.launch_problems(campaign):
                campaign_rules.launch(campaign, dojo.champion)
                campaign_rules.queue_mail(campaign.pk)
        self.stdout.write(f"Dojo mailings: {dojo.name}.")
        return created

    def _fill_in_new_dojo(self, spec):
        """Point the new-dojo campaign at a real dojo: the newest draft dojo
        with a location (one that's about to open), else the newest active
        one. Returns False when there's none."""
        located = Dojo.objects.exclude(location=None).order_by("-id")
        dojo = located.filter(status=Dojo.DRAFT).first() or located.filter(status=Dojo.ACTIVE).first()
        if dojo is None:
            return False
        spec["context"] = {"dojo_name": dojo.name, "dojo_path": reverse("dojo_detail", args=[dojo.pk])}
        for group in spec["segment"]["groups"]:
            group["rules"] = [
                (
                    attribute,
                    operator,
                    {**value, "dojo": dojo.pk} if isinstance(value, dict) and value.get("dojo") == NEW_DOJO else value,
                )
                for attribute, operator, value in group["rules"]
            ]
        self.stdout.write(f"“{spec['name']}” uses {dojo.name} ({dojo.get_status_display()}) as the new dojo.")
        return True

    def _segment(self, spec):
        segment, created = Segment.objects.get_or_create(
            name=spec["name"], defaults={"description": spec["description"]}
        )
        if created:
            for group_spec in spec["groups"]:
                self._group(segment, group_spec)
        return segment

    def _group(self, segment, spec, parent=None):
        group = SegmentGroup(segment=segment, parent=parent, scope=spec["scope"], operator=spec["operator"])
        group.full_clean()
        group.save()
        for attribute, operator, value in spec["rules"]:
            rule = SegmentRule(group=group, attribute=attribute, operator=operator, value=value)
            rule.full_clean()
            rule.save()
        for child_spec in spec.get("children", []):
            self._group(segment, child_spec, parent=group)
