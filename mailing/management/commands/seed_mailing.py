import copy

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.urls import reverse

from core.audit import without_audit_log
from dojos.models import Dojo
from mailing.models import Campaign, Segment, SegmentGroup, SegmentRule
from mailing.seed_templates import CAMPAIGNS, NEW_DOJO


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
                name=spec["name"], segment=self._segment(spec["segment"]),
                template_key=spec["template_key"], context=spec["context"],
            )
            campaigns_created += 1

        self.stdout.write(self.style.SUCCESS(f"Done. campaigns={campaigns_created} (new rows only)."))

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
                (attribute, operator, {**value, "dojo": dojo.pk} if isinstance(value, dict) and value.get("dojo") == NEW_DOJO else value)
                for attribute, operator, value in group["rules"]
            ]
        self.stdout.write(f"“{spec['name']}” uses {dojo.name} ({dojo.get_status_display()}) as the new dojo.")
        return True

    def _segment(self, spec):
        segment, created = Segment.objects.get_or_create(name=spec["name"], defaults={"description": spec["description"]})
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
