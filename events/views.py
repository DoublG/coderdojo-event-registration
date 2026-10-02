from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from accounts.models import Ninja
from content.cache import promotions_showing
from content.models import FAQ, Promotion
from core.caching import cached
from dojos.models import Dojo

from . import registrations
from .forms import AGE_RANGES, DOJO_ORGANISATION, EventSearchForm, SignUpForm
from .models import Event, Registration
from .search import (
    EVENT_LIST_CACHE_TIMEOUT,
    EVENT_LIST_FIRST_PAGE_KEY,
    WIDGET_PAGE_SIZE,
    upcoming_available_events,
)

RESULTS_PER_PAGE = 20


def event_list(request):
    form = EventSearchForm(request.GET)
    now = timezone.now()

    events = Event.objects.visible().filter(start_time__gte=now).select_related("dojo").with_confirmed_count()
    if form.is_valid():
        dojo = form.cleaned_data.get("dojo")
        if dojo == DOJO_ORGANISATION:
            events = events.filter(dojo__kind=Dojo.ORGANISATION)
        elif dojo:
            events = events.filter(dojo=dojo)

        location = form.cleaned_data.get("location")
        if location:
            events = events.filter(
                Q(dojo__address__icontains=location) | Q(dojo__municipality__name__icontains=location)
            )

        date_bucket = form.cleaned_data.get("date")
        if date_bucket == "week":
            events = events.filter(start_time__lt=now + timedelta(days=7))
        elif date_bucket == "month":
            events = events.filter(start_time__lt=now + timedelta(days=30))

        language = form.cleaned_data.get("language")
        if language:
            events = events.filter(dojo__languages__contains=[language])

        age_bucket = form.cleaned_data.get("age")
        if age_bucket in AGE_RANGES:
            lo, hi = AGE_RANGES[age_bucket]
            events = events.filter(Q(min_age__isnull=True) | Q(min_age__lte=hi)).filter(
                Q(max_age__isnull=True) | Q(max_age__gte=lo)
            )

    events = events.order_by("start_time")

    def fetch_page(page_number):
        paginator = Paginator(events, RESULTS_PER_PAGE)
        page = paginator.get_page(page_number)
        return {
            "events": list(page.object_list),
            "total_count": paginator.count,
            "next_page": page.next_page_number() if page.has_next() else None,
        }

    if not form.has_changed() and request.GET.get("page") in (None, "", "1"):
        # What most visitors see, the same for all of them (events.search).
        page = cached(EVENT_LIST_FIRST_PAGE_KEY, lambda: fetch_page(1), EVENT_LIST_CACHE_TIMEOUT)
    else:
        page = fetch_page(request.GET.get("page"))

    next_page_url = None
    if page["next_page"]:
        next_params = request.GET.copy()
        next_params["page"] = page["next_page"]
        next_page_url = f"{request.path}?{next_params.urlencode()}"

    context = {
        "form": form,
        "events": page["events"],
        "total_count": page["total_count"],
        "next_page_url": next_page_url,
        # Pinned above the date-ordered list (content.Promotion), on the
        # unfiltered list only: a search shows just what was asked for.
        "promotions": [] if form.has_changed() else promotions_showing(Promotion.EVENT_LIST_TOP),
    }
    # Infinite scroll (htmx "revealed" trigger, see _event_results_page.html):
    # subsequent pages return just the new date-group fragment, not the full page.
    if request.headers.get("HX-Request") == "true":
        return render(request, "events/partials/_event_results_page.html", context)
    return render(request, "events/event_list.html", context)


def upcoming_sessions_widget(request):
    """Lazy-loaded batches for the home page's "Upcoming sessions" carousel.

    Returns just the next batch of cards (see _upcoming_sessions_page.html),
    triggered by htmx as the carousel is scrolled — same paging approach as
    event_list's infinite scroll, but with an `intersect root:...` trigger
    instead of `revealed` since this list scrolls horizontally inside its
    own container rather than the window.
    """
    paginator = Paginator(upcoming_available_events(), WIDGET_PAGE_SIZE)
    page = paginator.get_page(request.GET.get("page"))

    next_page_url = None
    if page.has_next():
        next_page_url = f"{reverse('upcoming_sessions_widget')}?page={page.next_page_number()}"

    return render(
        request,
        "events/partials/_upcoming_sessions_page.html",
        {
            "events": page.object_list,
            "next_page_url": next_page_url,
        },
    )


def event_detail(request, event_id):
    event = get_object_or_404(Event.objects.visible().with_confirmed_count(), id=event_id)
    faqs = FAQ.objects.for_event(event)

    all_registered = False
    if request.user.is_authenticated:
        children = list(Ninja.objects.signable_by(request.user))
        if children:
            registered_count = Registration.objects.filter(event=event, ninja__in=children).count()
            all_registered = registered_count == len(children)

    return render(
        request,
        "events/event_detail.html",
        {
            "event": event,
            "faqs": faqs,
            "all_registered": all_registered,
        },
    )


def _registrations_of(event, account):
    """{ninja_id: Registration} for the children `account` may sign up."""
    return {
        r.ninja_id: r for r in Registration.objects.filter(event=event, ninja__in=Ninja.objects.signable_by(account))
    }


@login_required
def event_signup(request, event_id):
    event = get_object_or_404(Event.objects.visible(), id=event_id)
    if event.registers_externally:
        # Registrations happen elsewhere; its page links there.
        return redirect("event_detail", event_id=event.id)
    # An adult account signs up its own ninjas; a ninja's own login signs up
    # itself (Ninja.objects.signable_by).
    guardian = request.user
    results = error = None

    if request.method == "POST":
        form = SignUpForm(request.POST, children=Ninja.objects.signable_by(guardian))
        if not event.registration_open:
            error = _("Registrations for this session are closed.")
        elif not form.is_valid():
            error = form.non_field_errors()[0]
        else:
            # Places, positions and "already signed up" are decided under the
            # session's lock (events.registrations), not from what this page read.
            try:
                results = registrations.sign_up(event, form.cleaned_data["selected"])
            except registrations.RegistrationError as problem:
                error = str(problem)

    # Read after a sign-up, so the children just signed up show as such
    # (e.g. back on this form through the browser's back button).
    existing_registrations = _registrations_of(event, guardian)
    children = [
        {"child": child, "registration": existing_registrations.get(child.id)}
        for child in Ninja.objects.signable_by(guardian)
    ]
    all_registered = bool(children) and all(entry["registration"] for entry in children)

    any_waitlisted = bool(results) and any(r["waiting_list"] for r in results)
    return render(
        request,
        "events/event_signup.html",
        {
            "event": event,
            "full": event.places_left <= 0,
            "closed": not event.registration_open,
            "guardian": guardian,
            "children": children,
            "all_registered": all_registered,
            "results": results,
            "any_waitlisted": any_waitlisted,
            "error": error,
        },
    )
