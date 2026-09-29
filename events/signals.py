"""Clear the public site's cached lists whenever what they show changes, so
a published event or an edited dojo is visible at once: the dojo finder's
default list (dojos.search) and the upcoming-sessions carousel
(events.search). Signals rather than calls in the views, so the dojo team's
pages, the organisation dashboard, the Django admin and the API are all
covered. QuerySet.update() and bulk_create() send no signals; the caches'
short timeouts cover those."""

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from dojos.models import Dojo
from dojos.search import clear_default_search_cache

from .models import Event, Registration
from .search import clear_upcoming_cache


@receiver(post_save, sender=Dojo)
@receiver(post_delete, sender=Dojo)
def dojo_changed(sender, **kwargs):
    # The carousel shows the dojo's name, and only events of active dojos.
    clear_default_search_cache()
    clear_upcoming_cache()


@receiver(post_save, sender=Event)
@receiver(post_delete, sender=Event)
@receiver(post_save, sender=Registration)
@receiver(post_delete, sender=Registration)
def event_changed(sender, **kwargs):
    # A registration changes whether a session still has places left.
    clear_upcoming_cache()
