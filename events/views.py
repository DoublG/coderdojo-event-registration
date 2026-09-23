from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Max, Q
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone

from content.models import FAQ
from dojos.models import Dojo

from .forms import AGE_RANGES, EventSearchForm
from .models import Event, Registration
from .search import WIDGET_PAGE_SIZE, upcoming_available_events

RESULTS_PER_PAGE = 20


def event_list(request):
    form = EventSearchForm(request.GET)
    now = timezone.now()

    base_events = Event.objects.visible().filter(start_time__gte=now)
    dojo_choices = Dojo.objects.filter(event__in=base_events).distinct().order_by("name")

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
    guardian = getattr(request.user, "guardian", None)
    if guardian is not None:
        children = list(guardian.children.all())
        if children:
            registered_count = Registration.objects.filter(event=event, participant__in=children).count()
            all_registered = registered_count == len(children)

    return render(request, "events/event_detail.html", {
        "event": event, "faqs": faqs, "all_registered": all_registered,
    })


@login_required
def event_signup(request, event_id):
    event = get_object_or_404(Event.objects.visible(), id=event_id)
    guardian = getattr(request.user, "guardian", None)
    results = None
    error = None

    existing_registrations = {}
    if guardian:
        existing_registrations = {
            r.participant_id: r
            for r in Registration.objects.filter(event=event, participant__in=guardian.children.all())
        }

    if request.method == "POST" and guardian and not event.registration_open:
        error = "Registrations for this session are closed."
    elif request.method == "POST" and guardian:
        submitted_ids = request.POST.getlist("child")
        # The order children were *checked* in (tracked client-side, since
        # checkbox form submission is always DOM order regardless of click
        # order) — falls back to submission order if JS didn't populate it
        # (or a mismatched/stale value slipped through).
        ordered_ids = [cid for cid in request.POST.get("child_order", "").split(",") if cid]
        if set(ordered_ids) != set(submitted_ids):
            ordered_ids = submitted_ids

        children_by_id = {str(c.id): c for c in guardian.children.filter(id__in=submitted_ids)}
        selected = [children_by_id[cid] for cid in dict.fromkeys(ordered_ids) if cid in children_by_id]
        new_children = [c for c in selected if c.id not in existing_registrations]

        if not selected:
            error = "Please select at least one child."
        elif not new_children:
            error = "The child(ren) you selected are already signed up for this session."
        else:
            with transaction.atomic():
                next_position = Registration.objects.filter(event=event).aggregate(Max("position"))["position__max"] or 0
                confirmed_count = Registration.objects.filter(event=event, waiting_list=False).count()
                results = []
                for child in new_children:
                    next_position += 1
                    waiting_list = confirmed_count >= event.places
                    Registration.objects.create(
                        event=event, participant=child, waiting_list=waiting_list, position=next_position,
                    )
                    if not waiting_list:
                        confirmed_count += 1
                    results.append({"child": child, "waiting_list": waiting_list})
            # Re-fetch: the children just registered above should now show
            # as greyed-out/already-registered if the guardian lands back
            # on this form (e.g. via the browser back button).
            existing_registrations = {
                r.participant_id: r
                for r in Registration.objects.filter(event=event, participant__in=guardian.children.all())
            }

    children = [
        {"child": child, "registration": existing_registrations.get(child.id)}
        for child in guardian.children.all()
    ] if guardian else []
    all_registered = bool(children) and all(entry["registration"] for entry in children)

    any_waitlisted = bool(results) and any(r["waiting_list"] for r in results)
    return render(request, "events/event_signup.html", {
        "event": event, "full": event.places_left <= 0, "closed": not event.registration_open,
        "guardian": guardian, "children": children,
        "all_registered": all_registered,
        "results": results, "any_waitlisted": any_waitlisted, "error": error,
    })
