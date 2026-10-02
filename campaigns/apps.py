from django.apps import AppConfig


class CampaignsConfig(AppConfig):
    """Campaigns, segments and journeys (DATA_MODEL.md §11) and a dojo's own
    mail to its families (§25): who mail goes to and what it sends, through
    the mail engine (the mailing app), which never depends on this app
    (CODING_STANDARDS.md, "Layers")."""

    name = "campaigns"

    def ready(self):
        from mailing import template_users

        from .models import Campaign

        def names_by_key():
            used_by = {}
            for campaign in Campaign.objects.exclude(status=Campaign.Status.CANCELLED).only("name", "template_key"):
                used_by.setdefault(campaign.template_key, []).append(campaign.name)
            return used_by

        def blocking(key):
            open_statuses = [Campaign.Status.DRAFT, Campaign.Status.QUEUED]
            return Campaign.objects.filter(template_key=key, status__in=open_statuses).exists()

        # The Mail templates pages show which campaigns use a template, and
        # keep one a campaign not yet sent still needs.
        template_users.register(names_by_key, blocking)
