from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Max, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from accounts.home_dojo import assign_on_signup
from accounts.models import Ninja
from content.models import FAQ, Promotion
from dojos.models import Dojo
from mailing.automated import booking_mail

from .forms import AGE_RANGES, EventSearchForm
from .models import Event, Registration
from .search import WIDGET_PAGE_SIZE, upcoming_available_events

RESULTS_PER_PAGE = 20


def event_list(request):
    form = EventSearchForm(request.GET)
    now = timezone.now()

    base_events = Event.objects.visible().filter(start_time__gte=now)
    dojo_choices = Dojo.objects.public().filter(event__in=base_events).distinct().order_by("name")

    events = base_events.select_related("dojo")
    if form.is_valid():
        dojo = form.cleaned_data.get("dojo")
        if dojo:
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

        age_bucket = form.cleaned_data.get("age")
        if age_bucket in AGE_RANGES:
            lo, hi = AGE_RANGES[age_bucket]
            events = events.filter(Q(min_age__isnull=True) | Q(min_age__lte=hi)).filter(
                Q(max_age__isnull=True) | Q(max_age__gte=lo)
            )

    events = events.order_by("start_time")

    paginator = Paginator(events, RESULTS_PER_PAGE)
    page = paginator.get_page(request.GET.get("page"))

    next_page_url = None
    if page.has_next():
        next_params = request.GET.copy()
        next_params["page"] = page.next_page_number()
        next_page_url = f"{request.path}?{next_params.urlencode()}"

    context = {
        "form": form,
        "events": page.object_list,
        "dojo_choices": dojo_choices,
        "total_count": paginator.count,
        "next_page_url": next_page_url,
        # Pinned above the date-ordered list (content.Promotion), on the
        # unfiltered list only: a search shows just what was asked for.
        "promotions": [] if form.has_changed() else Promotion.objects.showing(Promotion.EVENT_LIST_TOP),
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

    return render(request, "events/partials/_upcoming_sessions_page.html", {
        "events": page.object_list,
        "next_page_url": next_page_url,
    })


def event_detail(request, event_id):
    event = get_object_or_404(Event.objects.visible(), id=event_id)
    faqs = FAQ.objects.for_event(event)

    all_registered = False
    if request.user.is_authenticated:
        children = list(Ninja.objects.signable_by(request.user))
        if children:
            registered_count = Registration.objects.filter(event=event, ninja__in=children).count()
            all_registered = registered_count == len(children)

    return render(request, "events/event_detail.html", {
        "event": event, "faqs": faqs, "all_registered": all_registered,
    })


@login_required
def event_signup(request, event_id):
    event = get_object_or_404(Event.objects.visible(), id=event_id)
    if event.registers_externally:
        # Registrations happen elsewhere; its page links there.
        return redirect("event_detail", event_id=event.id)
    # An adult account signs up its own ninjas; a ninja's own login signs up
    # itself (Ninja.objects.signable_by).
    guardian = request.user
    results = None
    error = None

    existing_registrations = {}
    if guardian:
        existing_registrations = {
            r.ninja_id: r
            for r in Registration.objects.filter(event=event, ninja__in=Ninja.objects.signable_by(guardian))
        }

    if request.method == "POST" and guardian and not event.registration_open:
        error = _("Registrations for this session are closed.")
    elif request.method == "POST" and guardian:
        submitted_ids = request.POST.getlist("child")
        # The order children were *checked* in (tracked client-side, since
        # checkbox form submission is always DOM order regardless of click
        # order) — falls back to submission order if JS didn't populate it
        # (or a mismatched/stale value slipped through).
        ordered_ids = [cid for cid in request.POST.get("child_order", "").split(",") if cid]
        if set(ordered_ids) != set(submitted_ids):
            ordered_ids = submitted_ids

        children_by_id = {str(c.id): c for c in Ninja.objects.signable_by(guardian).filter(id__in=submitted_ids)}
        selected = [children_by_id[cid] for cid in dict.fromkeys(ordered_ids) if cid in children_by_id]
        new_children = [c for c in selected if c.id not in existing_registrations]

        if not selected:
            error = _("Please select at least one child.")
        elif not new_children:
            error = _("The child(ren) you selected are already signed up for this session.")
        else:
            with transaction.atomic():
                next_position = Registration.objects.filter(event=event).aggregate(Max("position"))["position__max"] or 0
                confirmed_count = Registration.objects.filter(event=event, waiting_list=False).count()
                results = []
                for child in new_children:
                    next_position += 1
                    waiting_list = confirmed_count >= event.places
                    registration = Registration.objects.create(
                        event=event, ninja=child, waiting_list=waiting_list, position=next_position,
                    )
                    # What the ninja works on starts as everything the session
                    # covers; the dojo team narrows it on the attendance list.
                    registration.pathways.set(event.pathways.all())
                    # A child's first sign-up gives them their home dojo.
                    assign_on_signup(child, event.dojo)
                    if not waiting_list:
                        confirmed_count += 1
                    results.append({"child": child, "waiting_list": waiting_list})
                    # Queued in the same transaction: no mail for a sign-up
                    # that didn't happen, and none lost for one that did.
                    booking_mail(registration)
            # Re-fetch: the children just registered above should now show
            # as greyed-out/already-registered if the guardian lands back
            # on this form (e.g. via the browser back button).
            existing_registrations = {
                r.ninja_id: r
                for r in Registration.objects.filter(event=event, ninja__in=Ninja.objects.signable_by(guardian))
            }

    children = [
        {"child": child, "registration": existing_registrations.get(child.id)}
        for child in Ninja.objects.signable_by(guardian)
    ] if guardian else []
    all_registered = bool(children) and all(entry["registration"] for entry in children)

    any_waitlisted = bool(results) and any(r["waiting_list"] for r in results)
    return render(request, "events/event_signup.html", {
        "event": event, "full": event.places_left <= 0, "closed": not event.registration_open,
        "guardian": guardian, "children": children,
        "all_registered": all_registered,
        "results": results, "any_waitlisted": any_waitlisted, "error": error,
    })
